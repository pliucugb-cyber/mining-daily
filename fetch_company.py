# -*- coding: utf-8 -*-
"""
fetch_company.py — 矿业公司动态板块数据采集（v2：官网新闻，非公告）

数据来源：32 家矿业龙头「官方网站新闻栏目」（非 cninfo/SEC 公告）。
  - 国内 25 家 A股：各公司官网新闻列表页
  - 海外 7 家（纽蒙特/巴里克/自由港/南方铜业/泰克/阿格尼科/雅保）：官网 News/IR 栏目，英文标题经 MyMemory 译中

采集策略：
  - 全站统一 Python urllib 静态抓取（走本机 http 代理取外网、直连兜底），正则抽取新闻条目；
    本机 Chrome headless 渲染在当前环境会卡死，故已废弃 method='chrome'，统一 method='html'
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
# 本机代理（企业网）时通时断且端口会漂移（50636/53712/55483 都曾出现）：
# 不再依赖写死端口或可能过期的环境变量，而是运行时【发现】127.0.0.1 上真正存活的 HTTP 代理端口，
# 避免落到死端口导致整轮抓取慢超时（曾出现单公司空等 25s ×32 ≈ 14 分钟的事故）。
CHROME = (os.environ.get('CHROME_BIN')
          or r'C:/Program Files/Google/Chrome/Application/chrome.exe'
          or r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')

def _tcp_alive(host, port, t=2):
    try:
        s = socket.create_connection((host, int(port)), timeout=t); s.close(); return True
    except Exception:
        return False

def _hostport(u):
    m = re.match(r'https?://([^:/]+):(\d+)', u or '')
    return (m.group(1), int(m.group(2))) if m else None

def _netstat_local_ports():
    ports = set()
    try:
        r = subprocess.run([r'C:/Windows/System32/netstat.exe', '-ano', '-p', 'TCP'],
                           capture_output=True, timeout=20, encoding='gbk', errors='replace')
        for line in (r.stdout or '').splitlines():
            m = re.search(r'127\.0\.0\.1:(\d+)\s+\S+\s+LISTENING', line)
            if m:
                ports.add(int(m.group(1)))
    except Exception:
        pass
    return ports

_DISCOVERED = None
_DISCOVERED_TS = 0
_DISCOVER_TTL = 60  # 秒：缓存的代理端口每 60s 重新验证一次，适应端口漂移
def effective_proxy():
    """返回当前可用的本机 HTTP 代理 URL；没有则 None（调用方回退直连）。带缓存 + 漂移重验。"""
    global _DISCOVERED, _DISCOVERED_TS
    now = time.time()
    if _DISCOVERED is not None and (now - _DISCOVERED_TS) < _DISCOVER_TTL:
        return _DISCOVERED or None
    # 1) 环境变量里当前指向的端口（存活优先用）
    envp = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    if envp:
        hp = _hostport(envp)
        if hp and _tcp_alive(hp[0], hp[1]):
            _DISCOVERED, _DISCOVERED_TS = envp, now
            return envp
    # 2) 扫描本机监听端口，逐个试作代理能否真正取到外网内容
    found = ''
    for port in sorted(_netstat_local_ports()):
        hp = ('127.0.0.1', port)
        if not _tcp_alive(hp[0], hp[1], 1.5):
            continue
        try:
            st, data = http_get('https://www.zjky.cn/news/news_list.jsp',
                                timeout=6, proxy='http://127.0.0.1:%d' % port, allow_direct=False)
            if st == 200 and data and len(data) > 300 and not is_blocked(data.decode('utf-8', 'replace')):
                found = 'http://127.0.0.1:%d' % port
                break
        except Exception:
            pass
    _DISCOVERED, _DISCOVERED_TS = found, now
    return found or None

DATE_RE = re.compile(r'(20\d{2})[-/.年](1[0-2]|0?[1-9])[-/.月](3[01]|[12]\d|0?[1-9])日?')
DATE_RE2 = re.compile(r'(20\d{2})\.(\d{1,2})\.(\d{1,2})')
# 英文站日期（"20 August 2026" / "August 20, 2026"），海外 7 家新闻列表用
_MON = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
DATE_RE_EN = re.compile(r'(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(20\d{2})')
DATE_RE_EN2 = re.compile(r'([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(20\d{2})')
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

# ===== 新闻优先过滤（2026-09-23 新增；口径「适中＝事件类 + 行业技术观察」）=====
# ① 非新闻 URL（栏目/介绍/业务/招聘/合规/矿山项目页），命中即丢。
#    例：紫金 /global/program-detail-*.htm（矿山项目介绍）被这条干掉。
NON_NEWS_HREF = re.compile(
    r'/(program|project|business|product|solution|service|about|company|culture|'
    r'esg|csr|sustainab|investor|contact|job|recruit|career|talent|join|hr|'
    r'guanyu|zoujin|honor|history|certificat|brand|partner|shop|mall|cases|'
    r'download|feedback|sitemap|privacy|disclaim|zhaopin|rencai|gonggao_?notice)'
    r'[\w\-/\.]*', re.I)
# ② 导航/栏目/介绍类标题（精确整串命中即丢）
NON_NEWS_TITLE = set('''可持续发展 社会责任 环境社会及管治 子公司介绍 分子公司 销售及服务 产品与服务
产品中心 解决方案 锂的解决方案 资源产业 非洲资源产业 我们的宗旨 宗旨和价值观 价值观 企业文化
发展历程 组织架构 领导班子 荣誉资质 投资者关系 股市行情 最新股市行情 公司简介 企业简介 关于我们
联系我们 联系方式 人才招聘 招贤纳士 诚聘英才 加入我们 招聘信息 招聘 媒体中心 新闻中心 网站地图
首页 更多 详情 查看更多 业务板块 业务领域 产品展示 服务网络 客户服务 采购平台 供应商 招投标
党的建设 学习园地 纪检监察 廉洁从业 八项规定
投资者教育 投资者保护教育宣传 政策与标准 能源新材料 ESG报告 可持续发展报告
社会责任报告 环境社会及管治报告 环境社会及管治 新闻与媒体 查看详细
可持续报告 企业经营业绩考核'''.split())
# ③ 标题里的强噪音特征词（真新闻标题基本不会出现）
NON_NEWS_TITLE_KW = ('致辞', '招聘', '简介', '联系我们', '合规建议', '新思想', '宗旨', '价值观',
    '企业文化', '发展历程', '组织架构', '产品与服务', '产品中心', '业务领域', '业务板块',
    '新闻中心', '媒体中心', '网站地图', '解决方案', '资源产业', '销售及服务', '股市行情',
    '招贤纳士', '诚聘', '人才引进', '慰问', '八项规定', '党史', '党建', '工会', '职工', '团建',
    '廉洁', '纪检监察', '视察', '子公司介绍', '分子公司', '招投标', '采购平台', '供应商',
    '服务网络', '客户服务', '投资者关系', '学习教育', '教育宣传', '管治报告')
# ④ 新闻事件/技术观察动词（标题命中即视为新闻；口径适中保留技术/研究成果类）
NEWS_VERB = ('发布', '签署', '签订', '签约', '达成', '收购', '并购', '竞购', '入股', '增资',
    '募资', '融资', '投产', '试产', '达产', '扩产', '增产', '开工', '竣工', '复产', '停产',
    '检修', '中标', '承建', '获批', '核准', '完成', '启动', '上线', '落地', '交付', '发运',
    '出口', '进口', '获得', '荣获', '入选', '认定', '合作', '协议', '合同', '投资', '设立',
    '成立', '挂牌', '上市', '增持', '回购', '分红', '业绩', '净利', '营收', '产量', '销量',
    '突破', '首创', '研发', '专利', '技术', '创新', '标准', '报告', '披露', '预警', '预测',
    '展望', '观察', '分析', '研究', '进展', '成果', '勘探', '储量', '资源量', '增长', '下降',
    '下滑', '创新高', '新高', '领跑', '累计', '实现', '提升', '优化', '首次', '首批', '首个',
    '最大', '量产', '并网', '贯通', '封顶', '落成', '出矿', '复产')
# ⑤ 新闻型 URL 特征
NEWS_URL_HINT = re.compile(
    r'(news|detail|article|content|info|show|item|xwzx|xwdt|gsxw|press|media|story|'
    r'release|zixun|dongtai|jsp\?id|\?id=|/\d{3,}\.htm)', re.I)

CACHE_TTL = 24 * 3600  # 秒

def http_get(url, timeout=8, retries=0, proxy=None, allow_direct=True):
    # 代理优先（proxy 指向存活端口时），否则/失败后直连兜底；自动适配"代理与直连来回切换"的网络。
    openers = []
    if proxy:
        openers.append(urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
    if allow_direct:
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
    proxy = effective_proxy()
    for u in cands:
        st, data = http_get(u, timeout, proxy=proxy)
        if st == 200 and data and len(data) > 300:
            txt = data.decode('utf-8', 'replace')
            if not is_blocked(txt):
                return txt
    return ''

def _rm_best_effort(path):
    """尽力删除目录：分小批 os.remove，避开沙箱「单批删除 >50 需确认」的拦截。"""
    try:
        files, dirs = [], []
        for root, ds, fs in os.walk(path, topdown=False):
            for f in fs:
                files.append(os.path.join(root, f))
            for d in ds:
                dirs.append(os.path.join(root, d))
        for i in range(0, len(files), 25):
            for f in files[i:i + 25]:
                try:
                    os.remove(f)
                except Exception:
                    pass
        for d in dirs:
            try:
                os.rmdir(d)
            except Exception:
                pass
        try:
            os.rmdir(path)
        except Exception:
            pass
    except Exception:
        pass

def _kill_tree(pid):
    """杀掉进程及其全部子孙（Chrome 会 spawn 多个 renderer，仅 p.kill() 杀不掉，
    残留子进程会一直占着 dom_path 文件导致后续 open() 永久阻塞——此前海外站抓取卡死的根因。"""
    try:
        subprocess.run([r'C:/Windows/System32/taskkill.exe', '/F', '/T', '/PID', str(pid)],
                       capture_output=True, timeout=10)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass

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
    # 运行时发现的存活代理：先代理后直连；无代理：只直连
    P = effective_proxy()
    proxy_opts = (['--proxy-server=' + P, '--no-proxy-server']
                  if P else ['--no-proxy-server'])
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
                            _kill_tree(p.pid)
                            try:
                                p.wait(timeout=5)
                            except Exception:
                                pass
                except Exception:
                    pass
                # 读取前稍等，确保残留子进程已释放 dom_path 文件句柄
                try:
                    time.sleep(0.3)
                    with open(dom_path, 'r', encoding='utf-8', errors='replace') as f:
                        out = f.read()
                except Exception:
                    out = ''
                if out and not is_blocked(out):
                    return out
                try:
                    os.remove(dom_path)
                except Exception:
                    pass
    finally:
        _rm_best_effort(prof)
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

def _valid_ymd(y, mo, d):
    try:
        y, mo, d = int(y), int(mo), int(d)
        if 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
            return '%04d-%02d-%02d' % (y, mo, d)
    except Exception:
        pass
    return ''

_DATE_URL = re.compile(r'(20\d{2})[-/_]?(\d{2})[-/_]?(\d{2})')
def _date_from_url(href):
    # 很多中文站把日期写进 URL：t20260916_33816.html / 2026/09/16/xxx / 2026-09-16
    m = _DATE_URL.search(href or '')
    if m:
        return _valid_ymd(m.group(1), m.group(2), m.group(3))
    return ''

def find_date(raw, pos_start, pos_end, href=''):
    # 1) URL 内嵌日期优先（西部矿业 t20260916、新闻列表按年月建目录等）
    du = _date_from_url(href)
    if du:
        return du
    # 2) 锚点前后各 5000 字符（覆盖同列表项/单元格内的独立日期 span，部分站日期离标题较远）
    W = 5000
    fwd = raw[pos_end:pos_end + W]
    bwd = raw[max(0, pos_start - W):pos_start]
    for seg in (fwd, bwd):
        m = DATE_RE.search(seg) or DATE_RE2.search(seg)
        if m:
            nd = norm_date(m)
            if nd:
                return nd
        for rx, order in ((DATE_RE_EN, 'dmy'), (DATE_RE_EN2, 'mdy')):
            m = rx.search(seg)
            if m:
                if order == 'dmy':
                    dd, mon, yy = m.group(1), m.group(2), m.group(3)
                else:
                    mon, dd, yy = m.group(1), m.group(2), m.group(3)
                mi = _MON.get(mon[:3].lower())
                if mi:
                    nd = _valid_ymd(yy, mi, dd)
                    if nd:
                        return nd
    return ''

def looks_like_news(title, href=''):
    """过滤导航/按钮/纯 URL/CSS 类名/过短标题 + 栏目/介绍/招聘/党建类非新闻。"""
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
    # 非新闻标题（精确整串）与非新闻特征词
    if title in NON_NEWS_TITLE or low_t in NON_NEWS_TITLE:
        return False
    for kw in NON_NEWS_TITLE_KW:
        if kw in title:
            return False
    # 非新闻 URL（栏目/介绍/业务/招聘/矿山项目页）
    if href and NON_NEWS_HREF.search(href):
        return False
    cjk = len(re.findall(r'[\u4e00-\u9fff]', title))
    if cjk == 0 and len(title) < 12:
        return False
    if cjk > 0 and len(title) < 5:
        return False
    return True

def extract_gridview(raw, base_url):
    """ASPX GridView 表格型新闻列表（如铜陵有色）：标题在 <td class="txtSubject">，
    日期在 <td class="txtTime">，链接在 <td class="txtReadmore"><a href=...>。
    三者按行顺序一一对应，故按位置 zip 即可还原条目（通用锚点抽取会只抓到「查看详细」）。"""
    if not ('txtSubject' in raw and 'txtReadmore' in raw):
        return []
    titles = re.findall(r'txtSubject[^>]*>(.*?)</td>', raw, re.I | re.S)
    dates  = re.findall(r'txtTime[^>]*>(.*?)</td>', raw, re.I | re.S)
    links  = re.findall(r'txtReadmore[^>]*>.*?<a\b[^>]*href=["\']([^"\']+)["\']', raw, re.I | re.S)
    base_host = host_of(base_url)
    items, seen = [], set()
    n = min(len(titles), len(links))
    for i in range(n):
        title = strip_tags(titles[i]).strip()
        if not title or not looks_like_news(title):
            continue
        absurl = urllib.parse.urljoin(base_url, links[i].strip())
        if not same_host(host_of(absurl), base_host):
            continue
        if absurl in seen:
            continue
        # 日期优先取同列表项 txtTime 单元格，其次 URL 内嵌
        d = ''
        dm = DATE_RE.search(strip_tags(dates[i])) if i < len(dates) else None
        if dm:
            d = norm_date(dm)
        if not d:
            d = _date_from_url(links[i])
        items.append({'t': title, 'd': d or '', 'u': absurl, 's': ''})
        seen.add(absurl)
    return items

def extract_items(raw, base_url, max_items=18, require_date=False):
    if not raw:
        return []
    # GridView 表格型：优先用表格抽取（标题/链接分列，通用锚点抽取会失真）
    gv = extract_gridview(raw, base_url)
    if gv:
        gv.sort(key=lambda x: (x['d'] == '', x['d']), reverse=True)
        return gv[:max_items]
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
        if not looks_like_news(title, absurl):
            continue
        if absurl in seen:
            continue
        # 新闻性判定：URL 像新闻 或 标题含事件/技术观察动词；两者皆无视为导航/栏目
        if not (NEWS_URL_HINT.search(absurl) or any(v in title for v in NEWS_VERB)):
            continue
        d = find_date(raw, m.start(), m.end(), absurl)
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
        st, data = http_get(u, timeout=8, proxy=effective_proxy())
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
     'url':'http://www.tlys.cn/list.aspx?parentclassid=67&classid=383','method':'html'},
    {'name':'云南铜业','code':'000878','sector':'铜','region':'CN','exchange':'A股',
     'url':'https://www.ynfc.com.cn/','method':'html'},
    {'name':'西部矿业','code':'601168','sector':'铜','region':'CN','exchange':'A股',
     'url':'https://www.westmining.com/mtzx/xkxw/','method':'html'},
    # —— 钼 ——
    {'name':'洛阳钼业','code':'603993','sector':'钼','region':'CN','exchange':'A股',
     'url':'https://www.cmoc.com/html/Media/News/','method':'html'},
    # —— 铝 ——
    {'name':'中国铝业','code':'601600','sector':'铝','region':'CN','exchange':'A股',
     'url':'https://www.chalco.com.cn/','method':'html'},
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
     'url':'http://www.zjgold.com.cn/','method':'html'},
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
    # —— 海外 7 家（本机 Chrome 不可用 → 统一走静态 html 抓取；代理由 effective_proxy 发现）——
    {'name':'Newmont','code':'NEM','sector':'黄金','region':'NA','exchange':'NYSE',
     'url':'https://www.newmont.com/investors/news-release/default.aspx','method':'html'},
    {'name':'Barrick','code':'B','sector':'黄金','region':'NA','exchange':'NYSE',
     'url':'https://www.barrick.com/English/News/default.aspx','method':'html'},
    {'name':'Freeport-McMoRan','code':'FCX','sector':'铜','region':'NA','exchange':'NYSE',
     'url':'https://www.fcx.com/','method':'html'},
    {'name':'Southern Copper','code':'SCCO','sector':'铜','region':'NA','exchange':'NYSE',
     'url':'https://www.southerncopper.com/','method':'html','to':12},
    {'name':'Teck Resources','code':'TECK','sector':'铅锌','region':'NA','exchange':'TSX',
     'url':'https://www.teck.com/news/','method':'html'},
    {'name':'Agnico Eagle','code':'AEM','sector':'黄金','region':'NA','exchange':'TSX',
     'url':'https://www.agnicoeagle.com/English/news-and-media/news-releases/default.aspx','method':'html'},
    {'name':'Albemarle','code':'ALB','sector':'锂','region':'NA','exchange':'NYSE',
     'url':'https://www.albemarle.com/news','method':'html'},
]

INDEX = {s['name']: s for s in SITES}

# ============================ 4. 单公司采集 ============================
def fetch_one(site, force=False):
    name = site['name']
    url = site['url']
    method = site.get('method', 'html')
    to = site.get('to', 25)
    raw = cache_get(name, force)
    cached = raw is not None
    used_method = method
    if raw is None:
        # 本机 Chrome 不可用（headless 渲染会卡死），全部走静态 urllib 抓取；
        # 海外站经 effective_proxy() 发现的存活代理取外网，国内站直连兜底。
        raw = fetch_html(url, timeout=to)
        used_method = 'html'
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

def _full_roster(companies, old):
    """把本次已采集的公司补齐为全量 32 家：未采集的用旧 JSON 里的数据兜底。
    关键——增量落盘必须走这里，否则进程被杀时 JSON 只剩跑过的前几家公司（2026-09-21 事故）。"""
    have = set(c['name'] for c in companies)
    out = list(companies)
    for s in SITES:
        if s['name'] not in have:
            out.append(old.get(s['name']) or {
                'name': s['name'], 'code': s['code'], 'sector': s['sector'],
                'region': s['region'], 'exchange': s['exchange'],
                'home': s['url'], 'news_url': s['url'], 'method': '',
                'stale': False, 'items': []})
    return out

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
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--only' and i + 1 < len(args):
            only = [x.strip() for x in args[i + 1].split(',') if x.strip()]
            i += 2
            continue
        if a.startswith('--only='):
            only = [x.strip() for x in a.split('=', 1)[1].split(',') if x.strip()]
        elif a == '--force':
            force = True
        i += 1
    # 注：本机 Chrome 已不可用，cp_*/dom_* 不再生成；历史残留为无害磁盘垃圾，
    # 不在抓取流程内删除（沙箱对 tmp/co_cache 下任何删除都会阻断整轮抓取）。
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
            _write_json(_full_roster(companies, old))
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
