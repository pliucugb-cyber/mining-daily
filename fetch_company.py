# -*- coding: utf-8 -*-
"""
fetch_company.py — 矿业公司动态板块数据采集（v2：官网新闻，非公告）

数据来源：32 家矿业龙头「官方网站新闻栏目」（非 cninfo/SEC 公告）。
  - 国内 25 家 A股：各公司官网新闻列表页
  - 海外 7 家（纽蒙特/巴里克/自由港/南方铜业/泰克/阿格尼科/雅保）：官网 News/IR 栏目，英文标题经 MyMemory 译中

采集策略：
  - 国内/海外站：Python urllib 静态抓取（走本机 http 代理取外网、直连兜底），正则抽取新闻条目；
    个别 SPA 动态站（如中国铝业官网）method='chrome'，用系统 Chrome 无头渲染后再抽，无 Chrome 环境时安全降级静态抓取
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
    r'download|feedback|sitemap|privacy|disclaim|zhaopin|rencai|gonggao_?notice|'
    # 2026-09-24 新增：分支机构 / 下属单位 / 成员企业栏目（中矿资源页脚「分支机构」列表
    # 里的 fzjg/175.html 之类被误当新闻抓入，摘要变成子公司简介）
    r'fzjg|fenzhi|branch|subsidiar|member|jigou|'
    # 2026-09-26 新增：栏目/介绍页 URL 的**拼音**写法。白银有色 /yewulingyu/haiwaibankuai/
    #（业务领域-海外板块）这类路径此前漏网，把公司业务介绍抓成了新闻（用户截图红框那条）。
    r'yewu|lianxi|jianjie|jieshao|wenhua|rongyu|jiangli|bankuai|zhaopin|peixun|'
    r'dangjian|gonghui|tuandui|zuzhi|qiye)'
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

# ===== 采集口径（2026-09-26 用户拍板「直接删掉」）=====
# 用户原话：「我不是所有内容都想要抓过来，我是想通过矿业公司这个模块快速浏览每家公司近期发生的
# 重要新闻」。故：非「公司发生的新闻」的站务/活动内容命中 DROP 即丢；命中 KEEP（重大事件）则豁免。
DROP_TITLE_KW = (
    # ① 党务 / 意识形态
    '党委','党组','党支部','党建','党群','纪委','纪检','监察','廉洁','党课','四中全会',
    '总书记','宣讲','学习传达','传达学习','宣传思想','统战','精神文明','政治生态','党旗',
    '巾帼','青年文明号','主题教育','民主生活会','组织生活会','理论中心组',
    # ② 工会 / 职工 / 文体 / 节庆活动
    '劳模','工会','职工','疗休养','慰问','献血','志愿','运动会','球赛','征文','书法',
    '合唱','文艺','汇演','联欢','开学典礼','教师节','中秋','国庆','元旦','五一','端午',
    '春节','迎新','团建','生日','颁奖典礼','表彰','先进人物','优秀员工','技能大赛',
    # ③ 领导视察 / 调研 / 会见 / 出席
    '调研','视察','莅临','到访','会见','座谈','督导','检查指导','走访','拜会','考察','出席',
    # ④ 荣誉 / 榜单 / 评级
    '位列','排名','排行榜','500强','2000强','中企全球','影响力榜','获评','荣获','获奖',
    '摘金','摘得','摘冠','上榜','称号','领跑者','金奖','银奖','冠军','五星佳','最高评级',
    '先进个人','模范',
    # ⑤ 招聘 / 培训 / 公示 / 招标
    '招聘','招贤','诚聘','人才引进','公示','环评','环境影响','水土保持','招标','询价',
    '采购结果','废标','培训','演练','安全生产月','合规管理','结业','安委会','工作会议',
)
# 命中即丢（**先于** KEEP 判定）：这些词只在荣誉/活动标题里出现，免得被 KEEP 的
# 「认证/注册」之类宽词救回来（如「蝉联卓越职场认证」不是公司新闻）。
DROP_TITLE_HARD = (
    '卓越职场','最佳雇主','示范单位','文明单位','先进基层党组织','获奖','摘金','摘冠',
    '颁奖','疗休养','慰问','献血','运动会','开学典礼','教师节','新春','元宵','团拜',
    '开讲啦','能效“领跑者”','单项冠军',
)
# 重大事件保护名单（用户 2026-09-26 圈定的「要闻」范围）：命中即**不删**，
# 避免「党委 + 签约」「出席 + 投产」这类真事件新闻被误杀。
KEEP_TITLE_KW = (
    # 资本运作与股权 / 投资并购
    '收购','并购','竞购','增资','募资','融资','股权','重组','分拆','剥离','合资','注资',
    '增发','可转债','要约','分红','回购','增持','减持','举牌','控股','上市','IPO',
    # 生产运营与项目
    '投产','试产','达产','扩产','增产','减产','开工','竣工','复产','停产','检修','技改',
    '中标','承建','签约','签署','签订','合同','协议','订单','交付','发运','出口','进口',
    '并网','贯通','封顶','落成','出矿','选厂','冶炼厂','产能',
    # 业绩与资源储量
    '净利','营收','业绩','财报','年报','季报','预告','预增','预亏','盈利','亏损','减值',
    '产量','销量','储量','资源量','品位','勘探','增储','探矿权','采矿权','采矿许可','矿权',
    # 技术突破
    '专利','研发','首创','创新','认证','注册','突破','量产',
    # 风险事件
    '事故','伤亡','环保处罚','整顿','诉讼','仲裁','制裁','罢工','停牌','退市','处罚',
)
# 窄口径 URL 栏目规则：用于对**既有 JSON** 重洗，避免宽表 NON_NEWS_HREF 误伤真实新闻 URL
URL_COL_JUNK = re.compile(
    r'/(yewu|lianxi|jianjie|jieshao|wenhua|rongyu|jiangli|bankuai|zhaopin|peixun|'
    r'dangjian|gonghui|tuandui|zuzhi|honor|about)[\w\-/\.]*', re.I)

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

def fetch_render(url, wait=3.0, timeout=30):
    """无头渲染抓取（method='chrome' 真正生效）：用系统 Chrome 打开页面、等 JS 跑完再读 HTML。
    本机装有 Chrome 时可用；自动化 / 无 Chrome 环境会 ImportError 或路径缺失，返回 '' 由调用方降级静态抓取。"""
    try:
        import os as _os
        _exe = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
        if not _os.path.exists(_exe):
            return ''
        from playwright.sync_api import sync_playwright
        with sync_playwright() as _p:
            _b = _p.chromium.launch(executable_path=_exe, headless=True,
                                    args=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'])
            _pg = _b.new_page(user_agent=UA)
            # 不阻塞在 load：部分官网会注入慢速第三方脚本（如 hq.sinajs.cn），
            # 等到 load 会触发 25s 超时 → 整次渲染失败。domcontentloaded + 固定 settle 更稳。
            _pg.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
            _pg.wait_for_timeout(int(wait * 1000))
            _html = _pg.content()
            _b.close()
            return _html or ''
    except Exception:
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
def strip_comments(s):
    """剥离 HTML 注释（成对 / 悬空 / 孤立 -->），修华友钴业标题里的注释泄漏。"""
    s = re.sub(r'<!--.*?-->', ' ', s or '', flags=re.S)
    s = re.sub(r'<!--.*', ' ', s, flags=re.S)
    return s.replace('-->', ' ')

def strip_tags(s):
    s = re.sub(r'<!--.*?-->', ' ', s or '', flags=re.S)   # 成对注释
    s = re.sub(r'<!--.*', ' ', s, flags=re.S)              # 悬空 <!--（无闭合）
    s = s.replace('-->', ' ')
    s = re.sub(r'<[^>]+>', ' ', s)
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

# 2026-09-26：原正则要求月/日都是 2 位数，`/.../2026/9/I155279944712`（中金黄金）这类
# **1 位月份**路径匹配不上 → 回落到列表页日期（常是页脚/相邻条目日期）→ 日期整月错位。
_DATE_URL = re.compile(r'(20\d{2})[-/_](\d{1,2})(?:[-/_](\d{1,2}))?')
_DATE_URL_C = re.compile(r'(20\d{2})(\d{2})(\d{2})')
def _date_from_url(href):
    # 很多中文站把日期写进 URL：t20260916_33816.html / 2026/09/16/xxx / 2026-09-16 / 2026/9/
    m = _DATE_URL.search(href or '')
    if m:
        return _valid_ymd(m.group(1), m.group(2), m.group(3) or '1')
    m = _DATE_URL_C.search(href or '')
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
    # 非公司新闻（党务/工会文体/领导视察/荣誉榜单/招聘培训公示）—— 见 DROP_TITLE_KW
    if is_droppable_title(title):
        return False
    cjk = len(re.findall(r'[\u4e00-\u9fff]', title))
    if cjk == 0 and len(title) < 12:
        return False
    if cjk > 0 and len(title) < 5:
        return False
    return True

def is_droppable_title(title):
    """DROP_TITLE_HARD（荣誉/活动独有）→ 立即丢；否则命中 KEEP 保留、命中 DROP 丢。"""
    t = clean_ws(title)
    if not t:
        return False
    for kw in DROP_TITLE_HARD:
        if kw in t:
            return True
    for kw in KEEP_TITLE_KW:
        if kw in t:
            return False
    for kw in DROP_TITLE_KW:
        if kw in t:
            return True
    return False

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

# ============================ 1.5 条目清洗 / 摘要（v6, 2026-09-23）============================
# 列表页常把「导航项 / 栏目名 / 模板文字」混进条目，也常把「标题 + 正文开头 + 日期」粘成一条。
# 这里统一规整：① 摘出并剥离混进标题的日期；② 拆开「标题 + 正文」；③ 丢弃导航/模板/重复/超旧条目；
# ④ 给每条抽一句内容（先本地拆出的正文，其次抓文章页 meta/首段），使前端每条不再「光一个标题」。

JUNK_TITLE_EXACT = set("""储量与资源量 紫金blog 紫金全媒体 创新&数字化 新闻发布 最新故事 最新新闻稿
查看详细 查看更多 更多 详情 下载pdf 首页 网站地图 联系我们 隐私政策 版权所有 版权声明""".split())
JUNK_TITLE_KW = ('查看详细', '订阅（', '下载pdf', '在新标签页', '在新窗口', 'the eagle博客',
                 '利益相关方承诺书', '我们使用cookie')
# 机构/下属单位后缀（2026-09-24 新增）：真新闻标题几乎不以这些词结尾，且必然带事件动词。
# 命中「以机构后缀结尾 且 无新闻动词」即判为介绍性条目（如「津巴布韦Bikita矿业有限公司」）。
ORG_SUFFIX = ('有限公司', '有限责任公司', '股份有限公司', '集团有限公司', '分公司', '子公司',
              '冶炼厂', '选矿厂', '矿业公司', '项目部', '办事处', '工作组')
BOILER_PAT = re.compile(
    r'(发布人\s*[:：]|发布时间\s*[:：]|当您浏览、阅读或下载本网站|connect with us|'
    r'follow our social media|find albemarle|learn about teck|we use cookies|accept cookies|'
    r'版权所有|保留所有权利|copyright|all rights reserved|all rights|订阅（在新标签页中打开）|下载pdf)', re.I)

# 文章页「首段候选」阶段的模板段落特征（2026-09-24 新增，补 BOILER_PAT）。
# 原抽取器只取全文前 6 个 <p>，而页头/页脚的公司简介与免责声明常排在最前，
# 会把真实正文（如 Teck 新闻稿第 22 段）挤出候选 → 摘要恒空。
LEAD_BOIL_PAT = re.compile(
    r'(forward[- ]looking|前瞻性陈述|免责声明|风险提示|about\s+(teck|us|the\s+company)|'
    r'investor\s+contact|media\s+contact|投资者联系|媒体联系|扫码关注|扫描二维码|'
    r'关注我们|订阅我们|未经授权|转载请注明|责任编辑|上一篇|下一篇|'
    r'同意书征集|征集代理|proxy\s+solicitation|solicitation|'
    r'演示文稿将通过|网播|webcast|将通过以下链接|持有股票或\s*DRS|电/?(PRNewswire|美通社|新华美通))', re.I)

# 新闻稿「电头 / 署名行」：如「温哥华，不列颠哥伦比亚省 – Teck Resources Limited（TSX: TECK.A…）」，
# 是稿件的日期+公司署名，不是新闻内容，绝不能当摘要。结构固定：地点 – 公司（交易所代码…）。
DATELINE_PAT = re.compile(
    r'^\s*[^。！？；;]{0,40}[-–—]\s*[^。！？；;]{0,55}'
    r'(TSX|NYSE|LSE|ASX|TSE|HKEX|SHA|SZSE|NASDAQ|多伦多证券交易所|纽约证券交易所|伦敦证券交易所)\b',
    re.I)

# 摘要里「正文 + 末尾电头残片」粘连：如「…执行主席 ， 2026年 9月 3日/美通社/-- Albemarle Corporation (NYSE: ALB) …」。
# 真实内容在前，电头残片在后，需从电头处截断，保留前半段真实摘要。
STRIP_TAIL_PAT = re.compile(
    r'(?:^|\s)\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*/?\s*(?:PRNewswire|美通社|新华美通)'
    r'|电/?(?:PRNewswire|美通社|新华美通)'
    r'|[-–—]\s*[A-Za-z][A-Za-z\s.]*(?:Resources|Limited|Inc\.?|Corp|Corporation|Company|Ltd|PLC)\b[^。！？；;]{0,6}\(?(?:TSX|NYSE|LSE|ASX|HKEX|SHA|SZSE)\b')

def is_boilerplate_summary(s):
    """已落库的 `s` 若是电头/署名行/征集代理/网播链接等非内容文本 → True（让 finalize 重抓）。"""
    if not s:
        return False
    if DATELINE_PAT.search(s) or LEAD_BOIL_PAT.search(s) or BOILER_PAT.search(s) or ADDR_PAT.search(s):
        return True
    return False


# 稿尾「地址 / 联系方式」块：如「Suite 3300, Bentall 5 ... Vancouver, B.C. / t: 604... / @teck.com」，
# 是页脚联系方式，不是新闻内容，绝不能当摘要。
ADDR_PAT = re.compile(
    r'(suite\s*\d|burrard|v6c|t:\s*\d|f:\s*\d|\bstreet\b|\bavenue\b|\bphone\b|邮箱|地址|邮编|'
    r'media\s+relations|investor\s+relations|@teck\.com|www\.teck|teck\.com)', re.I)

def pick_lead(cands, title='', freq=None):
    """从候选里挑一条最像「新闻内容摘要」的：排除地址/电头/模板/标题复述，按长度与句式打分。"""
    freq = freq or {}
    title_l = clean_ws(title or '').lower()
    best, best_score = '', -1
    for t in cands:
        tt = clean_ws(t)
        if len(tt) < 40 or len(tt) > 400:
            continue
        if ADDR_PAT.search(tt) or DATELINE_PAT.search(tt) or LEAD_BOIL_PAT.search(tt) or BOILER_PAT.search(tt):
            continue
        if title_l and tt.lower() == title_l:
            continue
        score = 0
        L = len(tt)
        if 60 <= L <= 240:
            score += 3
        elif 40 <= L < 60 or 240 < L <= 300:
            score += 1
        if tt.rstrip().endswith(('。', '.', '！', '!', '？', '?')):
            score += 2
        if 'http' in tt or '@' in tt:
            score -= 5
        if freq.get(tt, 0) > 1:        # 同站多次出现 = 模板，强烈降权
            score -= 10
        if re.search(r'(宣布|报告|签署|达成|收购|投产|增产|减产|派发|任命|发布|建设|提供|支持|推进|discover|report|announce|sign|agree|acquire|produce|appoint|complete|approve|increase|decrease)', tt, re.I):
            score += 2
        if score > best_score:
            best_score, best = score, tt
    return best


# 标题里被列表页混入的日期：前缀「2026-02 05」/「2026.09.05」/「05/12 2026」(MM/DD YYYY)，尾缀日期
_TD_PREFIX      = re.compile(r'^(20\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})日?[\s\u3000]+')
_TD_PREFIX_YM   = re.compile(r'^(20\d{2})[.\-/年](\d{1,2})[\s\u3000]+(\d{1,2})[\s\u3000]+')
_TD_PREFIX_MDY  = re.compile(r'^(\d{1,2})[/.](\d{1,2})[\s.]*(20\d{2})[\s\u3000]+')
_TD_TAIL        = re.compile(r'[\s\u3000]+(20\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})日?\s*$')
# 2026-09-26 新增：先「列表序号 + 年月」再标题（赤峰黄金「06 2026.06 中国恩菲董事长刘诚一行到访…」）
_TD_SEQ         = re.compile(r'^\d{1,2}[\s\u3000]+(20\d{2})[.\-/](\d{1,2})[\s\u3000]+')

def title_date(t):
    """把列表页混进标题的日期摘出来 → (日期, 去日期标题)。摘不到返回 ('', 原标题)。"""
    x = clean_ws(t)
    m = _TD_PREFIX_MDY.match(x)          # 天山铝业式：「05/12 2026 …」（MM/DD YYYY）
    if m:
        d = _valid_ymd(m.group(3), m.group(1), m.group(2))
        if d:
            return d, x[m.end():].strip()
    m = _TD_SEQ.match(x)                 # 「06 2026.06 …」→ 年月可用（日未知，置 01，后面文章页会精修）
    if m:
        d = _valid_ymd(m.group(1), m.group(2), '1')
        if d:
            return d, x[m.end():].strip()
    for rx in (_TD_PREFIX, _TD_PREFIX_YM):
        m = rx.match(x)
        if m:
            g = m.groups()
            d = _valid_ymd(g[0], g[1], g[2])
            if d:
                return d, x[m.end():].strip()
    m = _TD_TAIL.search(x)
    if m:
        d = _valid_ymd(m.group(1), m.group(2), m.group(3))
        if d:
            return d, x[:m.start()].strip()
    return '', x

def split_title_body(t, head_max=64):
    """「标题 + 正文开头」粘成一条时拆开 → (标题, 正文)。与前端 splitTB() 同算法。"""
    x = clean_ws(t)
    if len(x) <= head_max:
        return x, ''
    cut = -1
    for i in range(min(len(x), head_max)):
        if x[i] in '。！？；!?;' and i + 1 >= 14:
            cut = i + 1
            break
    if cut < 0:
        sp = x.rfind(' ', 0, head_max)
        if sp < 14:
            sp = x.rfind('，', 0, head_max)
        cut = sp if sp >= 14 else head_max
    head = x[:cut].rstrip('，、, ')
    body = x[cut:].strip()
    if body == head:
        body = ''
    return (head or x[:head_max]), body

def trim_summary(x, limit=150):
    """摘要定长：去栏目前缀/尾部「详情」，超长在句读处收口。"""
    x = clean_ws(x)
    x = re.sub(r'^(【[^】]{0,14}】|\[[^\]]{0,14}\])\s*', '', x)
    x = re.sub(r'[\s\u3000]*(详情|查看更多|查看详细|了解|了解更多|more)[\s\u3000]*$', '', x, flags=re.I)
    if len(x) > limit:
        cut = -1
        for i in range(min(len(x), limit)):
            if x[i] in '。！？；.!?;' and i + 1 >= 40:
                cut = i + 1
        x = x[:cut] if cut > 0 else x[:limit] + '…'
    return x.strip()

def is_junk_item(title, url, date=''):
    """导航项 / 栏目名 / 模板文字 → 丢弃（这些是旧版「有的只有一个标题」的来源）。"""
    t = clean_ws(title)
    if not t:
        return True
    low = t.strip().lower()
    if low in JUNK_TITLE_EXACT:
        return True
    for kw in JUNK_TITLE_KW:
        if kw.lower() in low:
            return True
    has_verb = any(v in t for v in NEWS_VERB)
    if len(t) <= 6 and not re.search(r'[A-Za-z0-9]{3,}', t) and not has_verb:
        return True
    if len(t) <= 14 and not NEWS_URL_HINT.search(url or '') and not has_verb:
        return True
    # 机构/下属单位介绍（2026-09-24 新增）：官网页脚「分支机构 / 下属企业」列表被误当新闻，
    # 这类条目只有公司名 + 公司简介，不是「公司发生的新闻」，命中即丢。
    if not has_verb and t.endswith(ORG_SUFFIX):
        return True
    # 2026-09-26：对**既有 JSON** 重洗时也走「非新闻」判定 —— 既有条目不经过 looks_like_news，
    # 只经过 normalize_item + prune_items/is_junk_item，故必须在这里再拦一道。
    if is_droppable_title(t):
        return True
    if url and URL_COL_JUNK.search(html.unescape(url)):
        return True
    return False

# 文章页候选摘要（优先级：meta description → 正文容器首段 → 全文前几段）
META_PATS = [
    r'<meta[^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\'][^>]*content=["\'](.*?)["\']',
    r'<meta[^>]+content=["\'](.*?)["\'][^>]*(?:name|property)=["\'](?:description|og:description|twitter:description)["\']',
]
PARA_RE = re.compile(r'<p\b[^>]*>(.*?)</p>', re.I | re.S)
CTN_RE = re.compile(
    r'<(?:div|section|article)[^>]+(?:class|id)=["\'][^"\']*'
    r'(?:article|content|detail|newstxt|news_txt|txt|zoom|trs_editor|main)[^"\']*["\'][^>]*>(.*?)</(?:div|section|article)>',
    re.I | re.S)

def lead_candidates(raw):
    """从文章页 HTML 里抽候选摘要（已过滤模板文字，去重保序）。

    2026-09-24 重写（原版只取全文前 6 个 <p>，页面头部/页脚模板段落会把真实正文挤出候选）：
      ① 全文档段落参与候选（不再只取前 6 个）；
      ② 页内出现 >=2 次的段落判为站点模板，候选阶段即剔除（对 META / 容器 / 全文三类候选统一生效）
         （原先只在 finalize 里做跨条目去重，对「同一条目自己页内的模板段」无效）；
      ③ 追加 LEAD_BOIL_PAT 尾部模板词表（前瞻性陈述 / About XX / 联系方式 / cookie 等）。
    """
    body = re.sub(r'<(script|style)\b.*?</\1>', ' ', raw, flags=re.I | re.S)
    # 段落频次：同一页里重复出现的段落必是模板（页头标语、页脚简介…）
    para = [strip_tags(m.group(1)).strip() for m in PARA_RE.finditer(body)]
    freq = {}
    for t in para:
        if t:
            freq[t] = freq.get(t, 0) + 1
    cands = []
    # ① meta description
    for pat in META_PATS:
        m = re.search(pat, raw, re.I | re.S)
        if m:
            t = strip_tags(m.group(1))
            if 24 <= len(t) <= 400:
                cands.append(t)
            break
    # ② 正文容器内的段落
    for m in list(CTN_RE.finditer(raw))[:3]:
        for pm in list(PARA_RE.finditer(m.group(1)))[:3]:
            t = strip_tags(pm.group(1))
            if 30 <= len(t) <= 400:
                cands.append(t)
    # ③ 全文档段落（顺序保序，页内重复段落 = 模板先剔除）
    for t in para[:400]:
        if 30 <= len(t) <= 400 and freq.get(t, 0) <= 1:
            cands.append(t)
    out = []
    for t in cands:
        if t in out:
            continue
        # 页内重复 = 站点模板。必须对「全部候选」生效（含 META 与容器段落）：
        #   · Teck：容器里 2 次的「We are a leading Canadian resource company…」曾被当成摘要；
        #   · 江铜：META 的「江西铜业集团成立于1979年…」正文字段里也重复 2 次 → 同样属公司简介。
        if freq.get(t, 0) > 1:
            continue
        if BOILER_PAT.search(t) or LEAD_BOIL_PAT.search(t) or DATELINE_PAT.search(t):
            continue
        out.append(t)
    return out



LEAD_CACHE_VER = 'v4'   # 摘要抽取器/词表变更时 bump：避免旧的「空结果」缓存挡住重新抽取
                        # v4（2026-09-26）：缓存结构由 list 改为 {c:[摘要候选], d:发布日期}

def _art_cache(url):
    import hashlib
    key = (LEAD_CACHE_VER + url).encode('utf-8')
    return os.path.join(CACHE, 'art_%s_%s.json' % (LEAD_CACHE_VER, hashlib.md5(key).hexdigest()[:16]))

# 文章页发布日期（2026-09-26 新增）：54 条条目无日期 → 默认范围（近 90 天）下不可见，
# 而公司徽标按总条数显示 → 用户看到「洛阳钼业 9 条，点进去只有 2 条」。文章页 meta 最可靠。
ART_DATE_PATS = (
    r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|og:published_time|pubdate|'
    r'publishdate|publish_time|published_time|datePublished|og:release_date|'
    r'weibo:article:create_at)["\'][^>]*content=["\']([^"\']{4,40})["\']',
    r'<meta[^>]+content=["\']([^"\']{4,40})["\'][^>]*(?:property|name)=["\']'
    r'(?:article:published_time|pubdate|publishdate|published_time|datePublished)["\']',
    r'(?:发布时间|发布日期|发表时间)[\s\u3000]*[:：][\s\u3000]*([^<\n]{4,30})',
    r'"pubDate"[\s\u3000]*:[\s\u3000]*"([^"]{4,40})"',
)

def _parse_any_date(s):
    """从任意日期串取 YYYY-MM-DD（兼容 2026-09-19T10:00 / 2026年9月19日 / 09/19/2026 / 2026-09）。"""
    s = html.unescape(str(s or ''))
    m = re.search(r'(20\d{2})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})', s)
    if m:
        return _valid_ymd(m.group(1), m.group(2), m.group(3))
    m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](20\d{2})', s)
    if m:
        return _valid_ymd(m.group(3), m.group(1), m.group(2))
    m = re.search(r'(20\d{2})[-/](\d{1,2})', s)
    if m:
        return _valid_ymd(m.group(1), m.group(2), '1')
    return ''

def art_date_of(raw):
    """从文章页 HTML 抽发布日期；抽不到返回 ''。只认显式 meta / 「发布时间：」，
    ／不做全页日期兜底（页面侧栏的新闻列表会带来随机日期）。"""
    for pat in ART_DATE_PATS:
        m = re.search(pat, raw, re.I | re.S)
        if m:
            d = _parse_any_date(m.group(1))
            if d:
                return d
    return ''

def lead_of_article(url, timeout=12, ttl=7 * 24 * 3600):
    """抓文章页 → (候选摘要, 发布日期)。带磁盘缓存。抓不到返回 ([], '')。"""
    p = _art_cache(url)
    try:
        if os.path.exists(p) and (time.time() - os.path.getmtime(p)) < ttl:
            o = json.load(open(p, encoding='utf-8'))
            if isinstance(o, dict):
                return o.get('c') or [], o.get('d') or ''
            if isinstance(o, list):        # 兼容 v3 旧缓存形状
                return o, ''
    except Exception:
        pass
    cands, dt = [], ''
    try:
        raw = fetch_html(url, timeout=timeout)
        if raw:
            cands = lead_candidates(raw)
            dt = art_date_of(raw)
    except Exception:
        cands, dt = [], ''
    try:
        json.dump({'c': cands, 'd': dt}, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception:
        pass
    return cands, dt

def _age_days(d, base):
    """条目距基准日的天数；日期缺失返回 None。"""
    try:
        import datetime
        a = datetime.date(*[int(x) for x in d.split('-')[:3]])
        b = datetime.date(*[int(x) for x in base.split('-')[:3]])
        return (b - a).days
    except Exception:
        return None

# 标题里的站务残片（2026-09-26 新增）：
#   ① `"\s*>` —— 列表页把标题截断后又把完整标题塞进 title 属性，抽取时两段粘连
#      （中金黄金 16 条：`集团公司党委传达学习…精... "> 集团公司党委传达学习习近平总书记`）
#   ② 栏目前缀 —— 江西铜业 `公司新闻 ｜ 2026/07/02 江铜贵冶…`、`媒体报道 ｜ 2026/08/04 …`
_TD_COL_PREFIX = re.compile(
    r'^(?:公司新闻|集团新闻|企业新闻|媒体报道|媒体聚焦|新闻中心|集团要闻|公司要闻|'
    r'基层动态|行业动态|图片新闻|视频新闻|最新动态|媒体关注|要闻|动态)'
    r'[\s\u3000]*[｜|丨:：\-–—]*[\s\u3000]*')
_TD_HTML_JUNK = re.compile(r'["\']\s*>')

def clean_title_artifacts(t):
    """剥标题里的站务残片；含 `">` 时取更长的一侧（截断版 vs 完整版）。"""
    x = clean_ws(strip_comments(t))
    if _TD_HTML_JUNK.search(x):
        parts = [p.strip() for p in _TD_HTML_JUNK.split(x) if p.strip()]
        if parts:
            x = max(parts, key=len)
    return _TD_COL_PREFIX.sub('', x)

def normalize_item(it):
    """就地规整一条：剥站务残片 → 剥日期前缀 → 拆标题/正文 → 填摘要 → 纠偏链接/日期。"""
    it['u'] = html.unescape(it.get('u') or '')   # 落库前解净字面 `&amp;`（神火/铜陵/Teck 等 24 条）
    raw = clean_title_artifacts(it.get('t') or '')
    tdate, t1 = title_date(raw)
    head, body = split_title_body(t1)
    head = re.sub(r'[\s\u3000]+(详情|查看更多|查看详细|了解|了解更多)$', '', head).strip()
    it['t'] = head or clean_ws(t1)
    d = clean_ws(it.get('d') or '')
    du = _date_from_url(it['u'])
    if tdate:                                  # 标题内嵌日期最明确
        it['d'] = tdate
    elif du and (not d or du[:7] != d[:7]):    # URL 年月与列表页不一致 → 信 URL
        it['d'] = du                            #（finalize 会再用文章页日期精修）
    elif d:
        it['d'] = d
    s = clean_ws(it.get('s') or '')
    if s:
        s = STRIP_TAIL_PAT.split(s)[0].strip()   # 剥末尾「日期/美通社/--公司(NYSE)」等电头残片
    if not s and len(body) >= 30:
        s = trim_summary(body)
    if s and is_boilerplate_summary(s):   # 电头/征集代理/网播链接等非内容文本，清掉让 finalize 重抓
        s = ''
    if s:
        it['s'] = s
    else:
        it['s'] = ''   # 显式清空（否则保留原电头等非内容摘要）
    return it

def prune_items(items, base):
    """丢导航/模板/重复/超旧（>2 年）条目，并按日期倒序。"""
    keep, seen = [], set()
    for it in items or []:
        t = it.get('t') or ''
        u = html.unescape(it.get('u') or '')
        if is_junk_item(t, u, it.get('d')):
            continue
        # 2026-09-26：同公司内**标题完全相同**即视为同一条。原键是 (标题,日期)，导致同一篇文章
        # 因列表页日期不同而重复入库（驰宏锌锗「精准到“厘米”，安全“看得见”」曾同题 3 条）。
        k = clean_ws(t)
        if k in seen:
            continue
        seen.add(k)
        age = _age_days(it.get('d') or '', base)
        if age is not None and age > 730:
            continue
        keep.append(it)
    keep.sort(key=lambda x: (x.get('d') == '', x.get('d') or ''), reverse=True)
    return keep

def _mostly_ascii(s):
    """判断文本是否以 ASCII（英文）为主——用于决定是否译中。"""
    if not s:
        return False
    return sum(1 for ch in s if ord(ch) < 128) / max(1, len(s)) > 0.55

def finalize(companies, base, net=True, workers=4, quiet=False):
    """统一收尾：规整 + 清洗 + 摘要（含抓文章页）。net=False 时纯本地。"""
    for c in companies:
        c['rank'] = RANK.get(c.get('name'), c.get('rank', 99))
        for it in (c.get('items') or []):
            normalize_item(it)
        c['items'] = prune_items(c.get('items') or [], base)
    if not net:
        return companies
    from concurrent.futures import ThreadPoolExecutor
    todo = []
    for c in companies:
        # 2026-09-26：除「缺摘要」外，把「缺日期」与「URL 只到年月的占位日期(YYYY-MM-01)」也排进队列
        # —— 日期缺失会让条目在默认范围（近 90 天）下不可见。
        miss = [it for it in (c.get('items') or [])
                if not clean_ws(it.get('s') or '')
                or not clean_ws(it.get('d') or '')
                or clean_ws(it.get('d') or '').endswith('-01')]
        if miss:
            todo.append((c, miss))
    if not todo:
        return companies
    if not quiet:
        print('[摘要] 待抓文章页 %d 家 / %d 条' % (len(todo), sum(len(m) for _, m in todo)))
    def work(pair):
        c, miss = pair
        out = []
        for it in miss:
            u = html.unescape(it.get('u') or '').strip()
            out.append(lead_of_article(u) if u.startswith('http') else ([], ''))
        return out
    with ThreadPoolExecutor(max_workers=workers) as ex:
        got = list(ex.map(work, todo))
    filled = 0
    for (c, miss), cands_list in zip(todo, got):
        freq = {}
        for cs, _ad in cands_list:
            for t in cs:
                freq[t] = freq.get(t, 0) + 1
        for it, (cs, ad) in zip(miss, cands_list):
            t = pick_lead(cs, it.get('t'), freq)   # 挑最像内容摘要的候选，而非首条
            if t:
                it['s'] = trim_summary(t)
                filled += 1
            # 文章页日期：缺失直接用；占位(YYYY-MM-01)或与列表页相差 >45 天则以文章页为准
            if ad:
                cur = clean_ws(it.get('d') or '')
                if (not cur) or cur.endswith('-01'):
                    it['d'] = ad
                else:
                    try:
                        import datetime
                        a = datetime.date(*[int(x) for x in cur.split('-')[:3]])
                        b = datetime.date(*[int(x) for x in ad.split('-')[:3]])
                        if abs((b - a).days) > 45:
                            it['d'] = ad
                    except Exception:
                        pass
    if not quiet:
        print('[摘要] 填充 %d 条' % filled)
    # 海外公司摘要译中（best-effort，失败/受限保留英文，绝不阻塞整轮）
    if net:
        fx = [it for c in companies if c.get('region') == 'NA'
              for it in (c.get('items') or [])
              if _mostly_ascii(clean_ws(it.get('s') or ''))]
        if fx:
            if not quiet:
                print('[译中] 海外摘要 %d 条' % len(fx))
            def _tw(it):
                try:
                    z = translate(it.get('s') or '')
                    if z and z != it.get('s'):
                        it['s'] = z
                except Exception:
                    pass
            with ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(_tw, fx))
    return companies

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
     'url':'https://www.jxcc.com/news.html','method':'html'},
    {'name':'铜陵有色','code':'000630','sector':'铜','region':'CN','exchange':'A股',
     'url':'http://www.tlys.cn/list.aspx?parentclassid=67&classid=383','method':'html'},
    {'name':'云南铜业','code':'000878','sector':'铜','region':'CN','exchange':'A股',
     'url':'https://www.ynfc.com.cn/','method':'html','unreach':'dead'},
    {'name':'西部矿业','code':'601168','sector':'铜','region':'CN','exchange':'A股',
     'url':'https://www.westmining.com/mtzx/xkxw/','method':'html'},
    # —— 钼 ——
    {'name':'洛阳钼业','code':'603993','sector':'钼','region':'CN','exchange':'A股',
     'url':'https://www.cmoc.com/html/Media/News/','method':'html'},
    # —— 铝 ——
    {'name':'中国铝业','code':'601600','sector':'铝','region':'CN','exchange':'A股',
     'url':'https://www.chalco.com.cn/','method':'chrome','unreach':'spa'},
    {'name':'南山铝业','code':'600219','sector':'铝','region':'CN','exchange':'A股',
     'url':'https://www.nanshan.com.cn/news.html','method':'html'},
    {'name':'云铝股份','code':'000807','sector':'铝','region':'CN','exchange':'A股',
     'url':'http://www.ylgf.com.cn/','method':'html','unreach':'dead'},
    {'name':'神火股份','code':'000933','sector':'铝','region':'CN','exchange':'A股',
     'url':'http://www.shenhuo.com/home/newslist/newslist?categoryId=3','method':'html'},
    {'name':'天山铝业','code':'002532','sector':'铝','region':'CN','exchange':'A股',
     'url':'http://www.tslyjt.com/node/48','method':'html'},
    # —— 黄金 ——
    {'name':'山东黄金','code':'600547','sector':'黄金','region':'CN','exchange':'A股',
     'url':'https://www.sd-gold.com/column/81/','method':'html'},
    {'name':'中金黄金','code':'600489','sector':'黄金','region':'CN','exchange':'A股',
     # v7：上市公司官网域名 zjgold.com.cn 已被域名商挂牌转让（死站），改用集团站 chinagoldgroup.com 兜底采集团新闻
     'url':'https://www.chinagoldgroup.com/','method':'html'},
    {'name':'赤峰黄金','code':'600988','sector':'黄金','region':'CN','exchange':'A股',
     'url':'https://www.cfgold.com/col36/list','method':'html'},
    {'name':'湖南黄金','code':'002155','sector':'黄金','region':'CN','exchange':'A股',
     'url':'https://www.hngold.com.cn/','method':'html','unreach':'spa'},
    # —— 锂 ——
    {'name':'天齐锂业','code':'002466','sector':'锂','region':'CN','exchange':'A股',
     'url':'https://www.tianqilithium.com/news.aspx?t=27','method':'html'},
    {'name':'赣锋锂业','code':'002460','sector':'锂','region':'CN','exchange':'A股',
     'url':'https://www.ganfenglithium.com/news.html','method':'html'},
    {'name':'华友钴业','code':'603799','sector':'钴','region':'CN','exchange':'A股',
     'url':'https://www.huayou.com/news/corporate-news','method':'html'},
    {'name':'藏格矿业','code':'000408','sector':'锂','region':'CN','exchange':'A股',
     'url':'http://www.zanggekuangye.com/news/cropnews/index.html','method':'html'},
    # —— 稀土 ——
    {'name':'北方稀土','code':'600111','sector':'稀土','region':'CN','exchange':'A股',
     # 根域 reht.com 与 newscenter.do 均为 JS/AJAX 外壳页，静态抓取抽不到新闻列表；
     # 维持官网根域（点公司名可直达），内容发现走前端「搜新闻」兜底
     'url':'https://www.reht.com/','method':'html','unreach':'spa'},
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
     'url':'https://www.cxtc.com/News.aspx','method':'html'},
    # —— 海外 7 家（本机 Chrome 不可用 → 统一走静态 html 抓取；代理由 effective_proxy 发现）——
    {'name':'Newmont','code':'NEM','sector':'黄金','region':'NA','exchange':'NYSE',
     'url':'https://www.newmont.com/investors/news-release/default.aspx','method':'html','unreach':'spa'},
    {'name':'Barrick','code':'B','sector':'黄金','region':'NA','exchange':'NYSE',
     'url':'https://www.barrick.com/English/News/default.aspx','method':'html','unreach':'spa'},
    {'name':'Freeport-McMoRan','code':'FCX','sector':'铜','region':'NA','exchange':'NYSE',
     'url':'https://www.fcx.com/','method':'html','unreach':'spa'},
    {'name':'Southern Copper','code':'SCCO','sector':'铜','region':'NA','exchange':'NYSE',
     'url':'https://www.southerncopper.com/','method':'html','unreach':'spa','to':12},
    {'name':'Teck Resources','code':'TECK','sector':'铅锌','region':'NA','exchange':'TSX',
     'url':'https://www.teck.com/news/','method':'html'},
    {'name':'Agnico Eagle','code':'AEM','sector':'黄金','region':'NA','exchange':'TSX',
     'url':'https://www.agnicoeagle.com/English/news-and-media/news-releases/default.aspx','method':'html','unreach':'spa'},
    {'name':'Albemarle','code':'ALB','sector':'锂','region':'NA','exchange':'NYSE',
     'url':'https://www.albemarle.com/news','method':'html'},
    {'name':'盐湖股份','code':'000792','sector':'锂','region':'CN','exchange':'A股',
     'url':'http://www.qhyhgf.com/','method':'html'},
    {'name':'中矿资源','code':'002738','sector':'锂','region':'CN','exchange':'A股',
     'url':'http://www.sinomine.cn/','method':'html'},
    {'name':'永兴材料','code':'002756','sector':'锂','region':'CN','exchange':'A股',
     'url':'http://www.yongxing.com.cn/','method':'html'},
    {'name':'白银有色','code':'601212','sector':'铜铅锌','region':'CN','exchange':'A股',
     'url':'http://www.bynmc.com/','method':'html'},
    {'name':'中色股份','code':'000758','sector':'海外工程','region':'CN','exchange':'A股',
     'url':'http://www.nfc.com.cn/','method':'html'},
    {'name':'株冶集团','code':'600961','sector':'铅锌','region':'CN','exchange':'A股',
     'url':'http://www.zygroup.com.cn/','method':'html','unreach':'spa'},
    {'name':'广晟有色','code':'600259','sector':'稀土','region':'CN','exchange':'A股',
     'url':'http://www.graset.com/','method':'html','unreach':'spa'},
    {'name':'五矿资源','code':'1208','sector':'铜锌','region':'NA','exchange':'HK',
     'url':'https://www.mmg.com/','method':'html','unreach':'spa'},
    {'name':'中国有色矿业','code':'1258','sector':'铜','region':'NA','exchange':'HK',
     'url':'https://www.cnmc.com.hk/','method':'html','unreach':'spa'},
    {'name':'力拓','code':'RIO','sector':'综合','region':'NA','exchange':'LSE',
     'url':'https://www.riotinto.com/','method':'html','unreach':'spa'},
    {'name':'必和必拓','code':'BHP','sector':'综合','region':'NA','exchange':'LSE',
     'url':'https://www.bhp.com/','method':'html','unreach':'spa'},
    {'name':'淡水河谷','code':'VALE','sector':'综合','region':'NA','exchange':'NYSE',
     'url':'https://www.vale.com/','method':'html','unreach':'spa'},
    {'name':'嘉能可','code':'GLEN','sector':'综合','region':'NA','exchange':'LSE',
     'url':'https://www.glencore.com/','method':'html','unreach':'spa'},
    {'name':'英美资源','code':'AAL','sector':'综合','region':'NA','exchange':'LSE',
     'url':'https://www.angloamerican.com/','method':'html','unreach':'spa'},
    {'name':'第一量子','code':'FM','sector':'铜','region':'NA','exchange':'TSX',
     'url':'https://www.first-quantum.com/','method':'html','unreach':'spa'},
]

INDEX = {s['name']: s for s in SITES}

# ============================ 3.5 展示序（前端导航排序，2026-09-23 v6）============================
# 「市值 + 知名度」综合排序（人工维护，越靠前数值越小）。前端导航按国内 / 海外分两组，
# 组内按 rank 升序；无 rank 的公司退回「条目数降序」。改排序只改这张表即可。
# 说明：市值逐日波动，故这里用稳定的「量级 + 行业地位」档位，不写死当日市值数字。
PROMINENCE = [
    # —— 国内 A 股 ——
    '紫金矿业', '中国铝业', '北方稀土', '洛阳钼业', '山东黄金',
    '江西铜业', '中金黄金', '华友钴业', '天齐锂业', '赣锋锂业',
    '铜陵有色', '赤峰黄金', '云铝股份', '南山铝业', '神火股份',
    '西部矿业', '藏格矿业', '锡业股份', '云南铜业', '天山铝业',
    '驰宏锌锗', '中国稀土', '厦门钨业', '湖南黄金', '中金岭南',
    # —— 海外 ——
    'Newmont', 'Freeport-McMoRan', 'Barrick', 'Southern Copper',
    'Agnico Eagle', 'Teck Resources', 'Albemarle',
]
RANK = {n: i + 1 for i, n in enumerate(PROMINENCE)}

def _stub(site):
    """未采集公司的占位记录（保持全量 32 家花名册）。"""
    return {'name': site['name'], 'code': site['code'], 'sector': site['sector'],
            'region': site['region'], 'exchange': site['exchange'],
            'home': site['url'], 'news_url': site['url'], 'method': '',
            'unreach': site.get('unreach', ''),
            'stale': False, 'rank': RANK.get(site['name'], 99), 'items': []}

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
        if method == 'chrome':
            raw = fetch_render(url, wait=4.0, timeout=45)
            used_method = 'chrome' if raw else 'html'
            if not raw:
                raw = fetch_html(url, timeout=to)
                used_method = 'html'
        else:
            # 海外站经 effective_proxy() 发现的存活代理取外网，国内站直连兜底。
            raw = fetch_html(url, timeout=to)
            used_method = 'html'
        if raw:
            cache_put(name, raw)
    items = extract_items(raw, url, require_date=(method == 'chrome')) if raw else []
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
    # v6：本次 0 条时，用上一次 JSON 里同一公司的条目兜底并标 stale=True（前端显示「数据暂缓」）。
    # 旧数据现在已是「官网新闻」（v2），不再有 v1 公告污染，所以兜底是安全的；
    # 这样单站偶发抓取失败不会让整块变空——但仍会明确标注数据暂缓，不冒充当日新数据。
    stale, reuse = False, False
    if not items:
        prev = (old or {}).get(name) or {}
        pitems = prev.get('items') or []
        if pitems:
            items, stale, reuse = pitems, True, True
    return {
        'name': name, 'code': site['code'], 'sector': site['sector'],
        'region': site['region'], 'exchange': site['exchange'],
        'home': site['url'], 'news_url': site['url'], 'method': used,
        'unreach': site.get('unreach', ''),
        'stale': stale, 'rank': RANK.get(name, 99), 'items': items,
    }, items, stale, reuse, cached

def _full_roster(companies, old):
    """把本次已采集的公司补齐为全量 32 家：未采集的用旧 JSON 里的数据兜底。
    关键——增量落盘必须走这里，否则进程被杀时 JSON 只剩跑过的前几家公司（2026-09-21 事故）。"""
    have = set(c['name'] for c in companies)
    out = list(companies)
    for s in SITES:
        if s['name'] not in have:
            out.append(old.get(s['name']) or _stub(s))
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
    enrich_only = False   # 只对现有 company_news.json 做清洗 + 摘要（不重抓列表页）
    no_net = False        # 连文章页也不抓（纯本地清洗）
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
        elif a == '--enrich-only':
            enrich_only = True
        elif a == '--no-net':
            no_net = True
        i += 1
    # 注：本机 Chrome 已不可用，cp_*/dom_* 不再生成；历史残留为无害磁盘垃圾，
    # 不在抓取流程内删除（沙箱对 tmp/co_cache 下任何删除都会阻断整轮抓取）。
    old = load_old()
    if enrich_only:
        # 只规整 + 抽摘要，绝不重抓列表页（网络差时也不会把已有条目洗掉）
        base = (json.load(open(OUT, encoding='utf-8')).get('updated_at')
                if os.path.exists(OUT) else time.strftime('%Y-%m-%d'))
        order = {s['name']: i for i, s in enumerate(SITES)}
        companies = sorted(list(old.values()), key=lambda c: order.get(c.get('name'), 999))
        finalize(companies, base, net=(not no_net))
        real_total = _write_json(companies)
        print('[enrich-only] %d 家 / %d 条，saved %s' % (len(companies), real_total, OUT))
        return
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
        # 增量落盘：每采一家写一次，进程被杀也不丢已采集结果（旧公告数据不会回填）。
        # 2026-09-26 修 bug：原实现写的是**未规整**数据 —— 采集中途被网络中断/超时杀掉时，
        # 线上留下的就是「标题内嵌日期、字面 &amp;、`">` 残片、未去重、未过滤」的脏快照
        # （这正是线上 company_news.json 与 normalize_item 输出长期不一致的根因）。
        try:
            snap = _full_roster(companies, old)
            for _c in snap:
                for _it in (_c.get('items') or []):
                    normalize_item(_it)
                _c['items'] = prune_items(_c.get('items') or [], time.strftime('%Y-%m-%d'))
            _write_json(snap)
        except Exception:
            pass
    # --only：未重采的公司保留旧 JSON 中的对应条目（旧数据干净时才安全）
    if only:
        for s in SITES:
            if not any(c['name'] == s['name'] for c in companies):
                companies.append(old.get(s['name']) or _stub(s))
    finalize(companies, time.strftime('%Y-%m-%d'), net=(not no_net))
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
