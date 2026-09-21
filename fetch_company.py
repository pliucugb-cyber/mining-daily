# -*- coding: utf-8 -*-
"""
fetch_company.py — 矿业公司动态板块数据采集（v2：官网新闻，非公告）

数据来源：32 家矿业龙头「官方网站新闻栏目」（非 cninfo/SEC 公告）。
  - 国内 25 家 A股：各公司官网新闻列表页
  - 海外 7 家（纽蒙特/巴里克/自由港/南方铜业/泰克/阿格尼科/雅保）：官网 News/IR 栏目，英文标题经 MyMemory 译中

采集策略：
  - 静态 HTML 站点：Python urllib 走本机 http 代理（http/https 均可用）抓取后正则抽取新闻条目
  - JS 渲染站点：headless Chrome --dump-dom 渲染后再抽取（method='chrome'；其余站点静态抓取若 <3 条自动回退 Chrome）
  - 海外英文标题：MyMemory 免费接口译中（langpair=en|zh-CN），失败回退原文
  - 容错：某站点抓取失败（网络/Chrome 不可用）时，复用 company_news.json 中该公司上一次成功的数据并标 stale，避免每日重建把整块清空

缓存：原始 HTML/DOM 落盘到 tmp/co_cache/<slug>.html，24h 内且非 --force 时直接复用，避免每天重复 Chrome 渲染。

用法：
  python fetch_company.py                 # 全量采集
  python fetch_company.py --only 铜陵有色,西部矿业   # 仅重采指定公司（合并进现有 JSON）
  python fetch_company.py --force         # 忽略缓存全量重采
"""
import os, re, json, time, ssl, html, socket, shutil, urllib.request, urllib.parse, subprocess, sys

# 控制台为 GBK 时，标题里的 U+00A0 等字符会让 print 直接抛 UnicodeEncodeError 崩进程。
# 重配置 stdout 为 utf-8 + 替换，打印永不因编码中断（数据写文件本就是 utf-8，无影响）。
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

def clean_ws(s):
    """把 NBSP/U+00A0 等非断空格统一成普通空格，并压扁连续空白。"""
    if not s:
        return ''
    s = s.replace('\xa0', ' ').replace('\u2007', ' ').replace('\u202f', ' ')
    return re.sub(r'\s+', ' ', s).strip()

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'company_news.json')
CACHE = os.path.join(HERE, 'tmp', 'co_cache')
os.makedirs(CACHE, exist_ok=True)

# ============================ 0. 网络 ============================
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
PROXY = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY') or 'http://127.0.0.1:55483'
CHROME = (os.environ.get('CHROME_BIN')
          or r'C:/Program Files/Google/Chrome/Application/chrome.exe'
          or r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')

# 本机代理（企业网）时通时断：启动时探测端口是否存活，活着优先走代理，否则直连兜底。
def _probe_proxy():
    try:
        s = socket.create_connection(('127.0.0.1', 55483), timeout=2)
        s.close()
        return True
    except Exception:
        return False
PROXY_OK = _probe_proxy()

DATE_RE = re.compile(r'(20\d{2})[-/.年](1[0-2]|0?[1-9])[-/.月](3[01]|[12]\d|0?[1-9])日?')
DATE_RE2 = re.compile(r'(20\d{2})\.(\d{1,2})\.(\d{1,2})')
ANCHOR_RE = re.compile(r'<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
NAV_WORDS = set('首页 主页 关于我们 公司简介 联系我们 联系方式 加入我们 招贤纳士 招聘 投资者关系 '
                'English 中文 隐私政策 法律声明 网站地图 设为首页 收藏 登录 注册 搜索 新闻中心 媒体中心 '
                '更多 更多>> 详细 详情 查看 返回 上一页 下一页 首页 末页'.split())

# 栏目/板块/功能性页面（非新闻），作为标题出现时直接丢弃。命中整词或强特征子串。
GENERIC_TITLES = set('董事长致辞 总经理致辞 总裁致辞 公司简介 企业简介 关于我们 关于集团 '
    '联系我们 联系方式 人才招聘 招贤纳士 诚聘英才 加入我们 招聘 投资者关系 '
    '企业文化 发展历程 组织架构 领导班子 荣誉资质 社会责任 产品与服务 产品中心 '
    '业务领域 业务板块 我们的宗旨 我们的价值观 使命愿景 新闻中心 媒体中心 网站地图 '
    '首页 更多 详情 查看更多'.split())
def is_generic_title(title):
    t = title.strip()
    if t in GENERIC_TITLES:
        return True
    for kw in ('致辞', '招聘', '简介', '联系我们', '合规建议', '新思想', '宗旨', '价值观',
              '企业文化', '发展历程', '组织架构', '社会责任', '产品与服务', '产品中心',
              '业务领域', '业务板块', '新闻中心', '媒体中心', '网站地图'):
        if kw in t:
            return True
    return False
ASSET_EXT = ('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.pdf',
             '.zip', '.doc', '.docx', '.xls', '.xlsx', '.mp4', '.mp3', '.rar', '.exe')
NAV_HREF = ('index', 'about', 'contact', 'login', 'search', 'sitemap', 'privacy',
            'english', 'home', 'column', 'category', 'channel', 'list', 'menu',
            'wechat', 'weibo', 'app', 'join', 'job', 'recruit')

CACHE_TTL = 24 * 3600  # 秒

def http_get(url, timeout=8, retries=0):
    # 代理优先（PROXY_OK 时），否则/失败后直连兜底；自动适配"代理与直连来回切换"的网络。
    openers = []
    if PROXY_OK and PROXY:
        openers.append(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))
    openers.append(urllib.request.ProxyHandler({}))  # 直连
    last = None
    for ph in openers:
        op = urllib.request.build_opener(ph)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA,
                  'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'})
            r = op.open(req, timeout=timeout)
            data = r.read()
            return r.status, data
        except Exception as e:
            last = e
    return None, last

def _flip(url):
    if url.startswith('https://'):
        return url.replace('https://', 'http://', 1)
    if url.startswith('http://'):
        return url.replace('http://', 'https://', 1)
    return url

# 代理/网关劫持错误页 与 Chrome 无法访问页 特征
_BLOCK_RE = re.compile(
    r'检查代理服务器|Windows 网络诊断|DrcomServer|Dr\.COM|navigate to the billing|认证网关|'
    r'proxy server isn|proxy server is not|无法访问此网站|ERR_|net::ERR|refused to connect|'
    r'took too long|connection (was reset|refused)|502 Bad Gateway|504 Gateway|'
    r'故障排除|此站点无法|找不到该网页', re.I)
def is_blocked(txt):
    if not txt or len(txt) < 200:
        return True
    return bool(_BLOCK_RE.search(txt))

def fetch_html(url, timeout=25):
    """尝试给定 url，被代理错误页劫持则翻转 http/https 方案再试一次。"""
    cands = [url]
    fl = _flip(url)
    if fl != url:
        cands.append(fl)
    for u in cands:
        st, data = http_get(u, timeout)
        if st == 200 and data and len(data) > 300:
            txt = data.decode('utf-8', 'replace')
            if not is_blocked(txt):
                return txt
    return ''

def chrome_dump(url, timeout=20, budget=4000):
    if not os.path.exists(CHROME):
        return ''
    # 每次独立 profile，避免被杀遗留的孤儿 Chrome 占锁导致后续启动卡死
    prof = os.path.join(CACHE, 'cp_%d_%d' % (os.getpid(), int(time.time() * 1000)))
    dom_path = os.path.join(CACHE, 'dom_%d_%d.html' % (os.getpid(), int(time.time() * 1000)))
    cands = [url]
    fl = _flip(url)
    if fl != url:
        cands.append(fl)
    # 代理活着：先代理后直连；代理死了：只直连
    proxy_opts = (['--proxy-server=' + PROXY, '--no-proxy-server']
                  if (PROXY_OK and PROXY) else ['--no-proxy-server'])
    out = ''
    try:
        for u in cands:
            for po in proxy_opts:
                # 关键：Chrome 输出重定向到文件而非 PIPE。否则页面永不加载完时，
                # Chrome 子进程会攥住 stdout 管道导致 read 永久阻塞、进程卡死。
                try:
                    with open(dom_path, 'wb') as domf:
                        p = subprocess.Popen([CHROME, '--headless', '--no-sandbox', '--disable-gpu',
                                              '--user-data-dir=' + prof, po,
                                              '--virtual-time-budget=' + str(budget), '--dump-dom', u],
                                             stdout=domf, stderr=subprocess.DEVNULL, cwd=CACHE)
                        try:
                            p.wait(timeout=timeout)
                        except subprocess.TimeoutExpired:
                            p.kill()
                            try:
                                p.wait(timeout=5)
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    with open(dom_path, 'r', encoding='utf-8', errors='replace') as f:
                        out = f.read()
                except Exception:
                    out = ''
                if out and not is_blocked(out):
                    return out
    finally:
        try:
            shutil.rmtree(prof, ignore_errors=True)
        except Exception:
            pass
        try:
            os.remove(dom_path)
        except Exception:
            pass
    return ''

def slug_of(name):
    return re.sub(r'[^0-9A-Za-z\u4e00-\u9fff]+', '_', name)

def cache_path(name):
    return os.path.join(CACHE, slug_of(name) + '.html')

def cache_get(name, force):
    if force:
        return None
    p = cache_path(name)
    if os.path.exists(p) and (time.time() - os.path.getmtime(p)) < CACHE_TTL:
        try:
            with open(p, encoding='utf-8') as f:
                return f.read()
        except Exception:
            return None
    return None

def cache_put(name, raw):
    try:
        with open(cache_path(name), 'w', encoding='utf-8') as f:
            f.write(raw)
    except Exception:
        pass

# ============================ 1. 条目抽取 ============================
def strip_tags(s):
    s = re.sub(r'<[^>]+>', ' ', s or '')
    return html.unescape(clean_ws(s))

def host_of(u):
    try:
        return urllib.parse.urlparse(u).netloc.lower()
    except Exception:
        return ''

def same_host(h, base):
    if not h or not base:
        return False
    return h == base or h.endswith('.' + base) or base.endswith('.' + h)

def norm_date(m):
    y, mo, d = m.group(1), m.group(2), m.group(3)
    try:
        return '%04d-%02d-%02d' % (int(y), int(mo), int(d))
    except Exception:
        return ''

def find_date(raw, pos_start, pos_end):
    # 在锚点前后各 1500 字符（覆盖同列表项/单元格内的独立日期 span）内找日期
    fwd = raw[pos_end:pos_end + 1500]
    bwd = raw[max(0, pos_start - 1500):pos_start]
    for seg in (fwd, bwd):
        m = DATE_RE.search(seg) or DATE_RE2.search(seg)
        if m:
            nd = norm_date(m)
            if nd:
                return nd
    return ''

def looks_like_news(title):
    """过滤导航/按钮/纯 URL/CSS 类名/过短标题。"""
    if not title:
        return False
    low_t = title.lower()
    if ('http://' in low_t or 'https://' in low_t or low_t.startswith('www.')
            or title.startswith('//') or '@' in title):
        return False
    # 过滤 CSS / 内联样式 / SVG class 之类非文本（如 ".cls-1{fill:#140700;}"）
    if '{' in title or '}' in title or title.startswith('.') or 'cls-' in low_t \
            or 'style=' in low_t or low_t.startswith('svg') or low_t.startswith('path'):
        return False
    if is_generic_title(title):
        return False
    if title in NAV_WORDS or low_t in NAV_WORDS:
        return False
    cjk = len(re.findall(r'[\u4e00-\u9fff]', title))
    if cjk == 0 and len(title) < 12:
        return False
    if cjk > 0 and len(title) < 5:
        return False
    return True

def extract_items(raw, base_url, max_items=18, require_date=True):
    if not raw:
        return []
    base_host = host_of(base_url)
    items = []
    seen = set()
    for m in ANCHOR_RE.finditer(raw):
        href = m.group(1).strip()
        if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:', '//')):
            continue
        low = href.lower()
        if low.endswith(ASSET_EXT):
            continue
        if any(k in low for k in NAV_HREF) and len(strip_tags(m.group(2))) < 20:
            continue
        absurl = urllib.parse.urljoin(base_url, href)
        if not same_host(host_of(absurl), base_host):
            continue
        title = strip_tags(m.group(2))
        if not looks_like_news(title):
            continue
        if absurl in seen:
            continue
        d = find_date(raw, m.start(), m.end())
        if require_date and not d:
            continue
        # 摘要：</a> 之后到下一个列表项边界之间的文本（尽力）
        s = ''
        tail = raw[m.end():m.end() + 700]
        cut = re.search(r'</?(li|ul|ol|div|p|tr|td|h\d)\b', tail)
        seg = tail[:cut.start()] if cut else tail
        seg = strip_tags(seg)
        if 14 <= len(seg) <= 240 and seg != title:
            s = seg[:150]
        seen.add(absurl)
        items.append({'t': title, 'd': d or '', 'u': absurl, 's': s})
    # 有日期在前，无日期在后；各自按日期倒序
    items.sort(key=lambda x: (x['d'] == '', x['d']), reverse=True)
    return items[:max_items]

# ============================ 2. 翻译 ============================
TRANS_CACHE_PATH = os.path.join(CACHE, 'co_trans.json')
def _load_trans_cache():
    try:
        if os.path.exists(TRANS_CACHE_PATH):
            return json.load(open(TRANS_CACHE_PATH, encoding='utf-8')) or {}
    except Exception:
        pass
    return {}
_trans_cache = _load_trans_cache()
def translate(text):
    if not text:
        return text
    if text in _trans_cache:
        return _trans_cache[text]
    u = ('https://api.mymemory.translated.net/get?q=%s&langpair=en|zh-CN'
         % urllib.parse.quote(text[:300]))
    try:
        st, data = http_get(u, timeout=8)
        if st == 200 and data:
            j = json.loads(data.decode('utf-8', 'replace'))
            t = (j.get('responseData') or {}).get('translatedText') or ''
            if t and t.lower() != text.lower():
                _trans_cache[text] = t
                return t
    except Exception:
        pass
    _trans_cache[text] = text
    return text
def _save_trans_cache():
    try:
        with open(TRANS_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(_trans_cache, f, ensure_ascii=False)
    except Exception:
        pass

# ============================ 3. 公司花名册 + 新闻源 ============================
# method: 'html' 静态优先（不足 3 条自动回退 chrome）；'chrome' 直接渲染
SITES = [
    # —— 铜 ——
    {'name':'紫金矿业','code':'601899','sector':'铜','region':'CN','exchange':'A股',
     'url':'https://www.zjky.cn/news/news_list.jsp','method':'html'},
    {'name':'江西铜业','code':'600362','sector':'铜','region':'CN','exchange':'A股',
     'url':'https://www.jxcc.com/news.html','method':'chrome'},
    {'name':'铜陵有色','code':'000630','sector':'铜','region':'CN','exchange':'A股',
     'url':'http://www.tlys.cn/news.aspx?cid=383','method':'html'},
    {'name':'云南铜业','code':'000878','sector':'铜','region':'CN','exchange':'A股',
     'url':'https://www.ynfc.com.cn/','method':'html'},
    {'name':'西部矿业','code':'601168','sector':'铜','region':'CN','exchange':'A股',
     'url':'https://www.westmining.com/mtzx/xkxw/','method':'html'},
    # —— 钼 ——
    {'name':'洛阳钼业','code':'603993','sector':'钼','region':'CN','exchange':'A股',
     'url':'https://www.cmoc.com/html/Media/','method':'chrome'},
    # —— 铝 ——
    {'name':'中国铝业','code':'601600','sector':'铝','region':'CN','exchange':'A股',
     'url':'https://www.chalco.com.cn/','method':'chrome'},
    {'name':'南山铝业','code':'600219','sector':'铝','region':'CN','exchange':'A股',
     'url':'https://www.nanshan.com.cn/news.html','method':'html'},
    {'name':'云铝股份','code':'000807','sector':'铝','region':'CN','exchange':'A股',
     'url':'http://www.ylgf.com.cn/','method':'html'},
    {'name':'神火股份','code':'000933','sector':'铝','region':'CN','exchange':'A股',
     'url':'http://www.shenhuo.com/home/newslist/newslist?categoryId=3','method':'html'},
    {'name':'天山铝业','code':'002532','sector':'铝','region':'CN','exchange':'A股',
     'url':'http://www.tslyjt.com/node/48','method':'html'},
    # —— 黄金 ——
    {'name':'山东黄金','code':'600547','sector':'黄金','region':'CN','exchange':'A股',
     'url':'https://www.sd-gold.com/column/81/','method':'chrome'},
    {'name':'中金黄金','code':'600489','sector':'黄金','region':'CN','exchange':'A股',
     'url':'http://www.zjgold.com.cn/','method':'chrome'},
    {'name':'赤峰黄金','code':'600988','sector':'黄金','region':'CN','exchange':'A股',
     'url':'https://www.cfgold.com/col36/list','method':'html'},
    {'name':'湖南黄金','code':'002155','sector':'黄金','region':'CN','exchange':'A股',
     'url':'https://www.hngold.com.cn/','method':'html'},
    # —— 锂 ——
    {'name':'天齐锂业','code':'002466','sector':'锂','region':'CN','exchange':'A股',
     'url':'https://www.tianqilithium.com/news.aspx?t=27','method':'html'},
    {'name':'赣锋锂业','code':'002460','sector':'锂','region':'CN','exchange':'A股',
     'url':'https://www.ganfenglithium.com/news.html','method':'chrome'},
    {'name':'华友钴业','code':'603799','sector':'钴','region':'CN','exchange':'A股',
     'url':'https://www.huayou.com/news/corporate-news','method':'html'},
    {'name':'藏格矿业','code':'000408','sector':'锂','region':'CN','exchange':'A股',
     'url':'http://www.zanggekuangye.com/news/cropnews/index.html','method':'html'},
    # —— 稀土 ——
    {'name':'北方稀土','code':'600111','sector':'稀土','region':'CN','exchange':'A股',
     'url':'https://www.reht.com/','method':'html'},
    {'name':'中国稀土','code':'000831','sector':'稀土','region':'CN','exchange':'A股',
     'url':'https://www.regcc.cn/zgxtjt/jtnew/list_9.shtml','method':'html'},
    # —— 铅锌 ——
    {'name':'驰宏锌锗','code':'600497','sector':'铅锌','region':'CN','exchange':'A股',
     'url':'http://www.chxz.com/xwzx/zhxw/','method':'html'},
    {'name':'中金岭南','code':'000060','sector':'铅锌','region':'CN','exchange':'A股',
     'url':'https://www.nonfemet.com/channel/74','method':'html'},
    # —— 锡 / 钨 ——
    {'name':'锡业股份','code':'000960','sector':'锡','region':'CN','exchange':'A股',
     'url':'https://www.ytc.cn/xwdt1/gsxw.htm','method':'html'},
    {'name':'厦门钨业','code':'600549','sector':'钨','region':'CN','exchange':'A股',
     'url':'https://www.cxtc.com/News.aspx','method':'chrome'},
    # —— 海外 7 家（JS 重站，统一走 chrome；http 方案重试由 chrome_dump 处理）——
    {'name':'Newmont','code':'NEM','sector':'黄金','region':'NA','exchange':'NYSE',
     'url':'https://www.newmont.com/news/','method':'chrome'},
    {'name':'Barrick','code':'B','sector':'黄金','region':'NA','exchange':'NYSE',
     'url':'https://www.barrick.com/English/News/default.aspx','method':'chrome'},
    {'name':'Freeport-McMoRan','code':'FCX','sector':'铜','region':'NA','exchange':'NYSE',
     'url':'https://www.fcx.com/news','method':'chrome'},
    {'name':'Southern Copper','code':'SCCO','sector':'铜','region':'NA','exchange':'NYSE',
     'url':'https://www.southerncopper.com/','method':'chrome'},
    {'name':'Teck Resources','code':'TECK','sector':'铅锌','region':'NA','exchange':'TSX',
     'url':'https://www.teck.com/news/','method':'chrome'},
    {'name':'Agnico Eagle','code':'AEM','sector':'黄金','region':'NA','exchange':'TSX',
     'url':'https://www.agnicoeagle.com/English/news/default.aspx','method':'chrome'},
    {'name':'Albemarle','code':'ALB','sector':'锂','region':'NA','exchange':'NYSE',
     'url':'https://www.albemarle.com/news','method':'chrome'},
]

INDEX = {s['name']: s for s in SITES}

# ============================ 4. 单公司采集 ============================
def fetch_one(site, force=False):
    name = site['name']
    url = site['url']
    method = site.get('method', 'html')
    raw = cache_get(name, force)
    cached = raw is not None
    used_method = method
    if raw is None:
        if method == 'chrome':
            raw = chrome_dump(url)
            used_method = 'chrome'
            if not raw:
                raw = fetch_html(url)  # 回退静态
                if raw:
                    used_method = 'html'
        else:
            raw = fetch_html(url)
            used_method = 'html'
            # 静态站不再回退 Chrome（省时）；方法标错或真 JS 站由 method='chrome' 处理
        if raw:
            cache_put(name, raw)
    items = extract_items(raw, url, require_date=False) if raw else []
    # 海外译中
    if site.get('region') == 'NA':
        for it in items:
            en = it['t']
            zh = translate(en)
            it['t_en'] = clean_ws(en)
            it['t'] = clean_ws(zh)
    return items, used_method, cached

# ============================ 5. 主流程 ============================
def load_old():
    old = {}
    if os.path.exists(OUT):
        try:
            od = json.load(open(OUT, encoding='utf-8'))
            for c in (od.get('companies') or []):
                old[c.get('name')] = c
        except Exception:
            pass
    return old

def is_v2(items):
    return bool(items) and all(('lv' not in it) and ('c' not in it) for it in items)

def collect(site, old, force):
    name = site['name']
    try:
        items, used, cached = fetch_one(site, force)
    except Exception as e:
        items, used, cached = [], 'err', False
        print('  [ERR] %s %s' % (name, repr(e)[:80]))
    # 不再回退旧 company_news.json（旧数据是 v1 公告，属污染源）。
    # 只信本次真实抓取（或同次运行内的 raw-HTML 缓存）；抓不到就诚实标空。
    stale = False
    reuse = False
    return {
        'name': name, 'code': site['code'], 'sector': site['sector'],
        'region': site['region'], 'exchange': site['exchange'],
        'home': site['url'], 'news_url': site['url'], 'method': used,
        'stale': stale, 'items': items,
    }, items, stale, reuse, cached

def _write_json(companies):
    domestic = [c for c in companies if c['region'] == 'CN']
    foreign = [c for c in companies if c['region'] == 'NA']
    real_total = sum(len(c['items']) for c in companies)
    data = {
        'updated_at': time.strftime('%Y-%m-%d'),
        'companies': companies,
        'counts': {
            'domestic': len(domestic), 'foreign': len(foreign),
            'total': len(companies), 'items': real_total,
        },
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return real_total

def main():
    only = None
    force = False
    for a in sys.argv[1:]:
        if a.startswith('--only='):
            only = [x.strip() for x in a.split('=', 1)[1].split(',') if x.strip()]
        elif a == '--force':
            force = True
    old = load_old()
    if only:
        targets = [INDEX[n] for n in only if n in INDEX]
        print('[--only] 重采 %d 家：%s' % (len(targets), '、'.join(only)))
    else:
        targets = SITES
    companies = []
    for site in targets:
        c, items, stale, reuse, cached = collect(site, old, force)
        companies.append(c)
        src = 'cache' if cached else 'net'
        if items:
            sample = items[0]['t'][:34]
        elif reuse:
            sample = '（沿用旧官网新闻）'
        else:
            sample = '（官网暂不可达）'
        print('  %-16s %-5s %-3s 条 %-7s %-5s %s' % (c['name'], site['code'], len(items), c['method'], src, sample))
        time.sleep(0.15)
        # 增量落盘：每采一家写一次，进程被杀也不丢已采集结果（旧公告数据不会回填）
        try:
            _write_json(companies)
        except Exception:
            pass
    # --only：未重采的公司保留旧 JSON 中的对应条目（旧数据干净时才安全）
    if only:
        for s in SITES:
            if not any(c['name'] == s['name'] for c in companies):
                companies.append(old.get(s['name']) or {
                    'name': s['name'], 'code': s['code'], 'sector': s['sector'],
                    'region': s['region'], 'exchange': s['exchange'],
                    'home': s['url'], 'news_url': s['url'], 'method': '',
                    'stale': False, 'items': []})
    real_total = _write_json(companies)
    _save_trans_cache()
    domestic = [c for c in companies if c['region'] == 'CN']
    foreign = [c for c in companies if c['region'] == 'NA']
    print('\n国内 %d / 海外 %d / 合计 %d 家，条目 %d'
          % (len(domestic), len(foreign), len(companies), real_total))
    print('saved', OUT)

if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        cl = os.path.join(CACHE, 'crash.log')
        with open(cl, 'a', encoding='utf-8') as f:
            f.write('\n=== crash %s ===\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
            f.write(traceback.format_exc())
        # 崩溃前若已部分采集，仍尝试落盘，避免整块清空
        try:
            _save_trans_cache()
        except Exception:
            pass
        print('CRASH -> see', cl)
        raise
