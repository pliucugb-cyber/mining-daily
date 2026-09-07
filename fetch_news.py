#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_news.py — 有色金属行业新闻自动爬虫（P3 产能瓶颈根本解）

设计定位
--------
**爬虫负责"发现候选"，AI 负责"审核 + 翻译"。**
不是全自动发布——那样会牺牲"信息来源必须可靠"这条底线（用户 2026-09-07 明确要求）。
爬虫把「从零找新闻」变成「从几十条候选里挑」，产能提升但质量不降。

设计要点
--------
1. **零第三方依赖**：仅标准库（urllib/ssl/re/xml.etree/gzip），与 fetch_ma.py 一致。
   环境实测无 requests/bs4/lxml，禁止引入。
2. **源配置化**：新增源只需往 SOURCES 加一条配置，不改解析逻辑。
3. **三重过滤**：白名单域校验 → 有色相关性（须命中）→ 噪声排除（时政/广告/招聘）。
4. **去重**：URL 规范化去重 + 标题相似度去重（同一事件多源报道只留一条）。
5. **境外源单独标记**（foreign=True），提示 AI 需走英文翻译规范与可达性复检。

产出
----
默认写候选池 `data/news_candidates_YYYY-MM-DD.json`；
加 `--merge` 则同时并入 `data/news_YYYY-MM.json`（与 fetch_ma.py 同 schema）。

用法
----
    python fetch_news.py                          # 抓今日，写候选池
    python fetch_news.py --days 3                 # 抓最近 3 天
    python fetch_news.py --merge                  # 抓完并入月度库
    python fetch_news.py --source smm             # 只跑指定源
    python fetch_news.py --fetch-detail           # 逐条抓正文补摘要（慢）
    python fetch_news.py --dry-run                # 只打印不落盘
"""
import argparse
import datetime
import gzip
import hashlib
import html as htmllib
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

TIMEOUT = 20
MAX_PER_SOURCE = 40          # 单源最多取多少条候选
DETAIL_LIMIT = 12            # --fetch-detail 时最多抓多少条正文（防拖慢）

# ============================================================================
# 源配置（2026-09-08 实测标定：每个源的链接模式都经真实抓取验证）
# 字段：key/name/list_url/kind/link_re/category/source/foreign/enabled
#   kind     : 'rss' 走 XML 解析；'html' 走正则提取 <a>
#   link_re  : 从列表页 HTML 中筛出「新闻详情链接」的正则（必含一个分组用于拼 URL）
#   foreign  : True 表示境外/英文源，AI 采编时须走翻译规范 + 可达性复检
# ============================================================================
SOURCES = [
    {
        "key": "smm",
        "name": "上海有色网 SMM",
        "list_url": "https://news.smm.cn/",
        "kind": "html",
        "link_re": r"/news/(\d+)",
        "href_tpl": "https://news.smm.cn/news/{g1}",
        "category": "行业动态",
        "source": "上海有色网",
        "foreign": False,
        "enabled": True,
        "note": "有色行业最对口，实测链接模式 /news/数字，内容为镍钴锂锌金等品种动态",
    },
    {
        "key": "metal",
        "name": "SMM 国际站（英文）",
        "list_url": "https://news.metal.com/en",
        "kind": "html",
        "link_re": r"/en/newscontent/(\d+-[A-Za-z0-9\-]+)",
        "href_tpl": "https://news.metal.com/en/newscontent/{g1}",
        "category": "国际矿业动态",
        "source": "SMM 国际站",
        "foreign": True,
        "enabled": True,
        "note": "中国团队运营、境内直连无墙的英文源，补国际视角且无需翻墙",
    },
    {
        "key": "geoglobal",
        "name": "全球矿产资源信息系统",
        "list_url": "https://geoglobal.mnr.gov.cn/",
        "kind": "html",
        "link_re": r"\./zx/[\w/]+/(t\d{8}_\d+\.htm)",
        "href_tpl": "https://geoglobal.mnr.gov.cn/zx/{g1}",
        "category": "国际矿业动态",
        "source": "全球矿产资源信息系统",
        "foreign": False,
        "enabled": True,
        "note": "自然资源部旗下，国际矿业动态为主",
    },
    {
        "key": "mining",
        "name": "MINING.COM",
        "list_url": "https://www.mining.com/feed/",
        "kind": "rss",
        "category": "国际矿业动态",
        "source": "MINING.COM",
        "foreign": True,
        "enabled": True,
        "note": "实测唯一的真 RSS 源；需排除 /sponsored-content/ 广告路径",
    },
    {
        "key": "chinania",
        "name": "中国有色金属工业协会",
        "list_url": "https://www.chinania.org.cn/",
        "kind": "html",
        # 实测详情页为 5 段路径且以 数字.html 结尾（如 /html/a/b/2022/1207/154.html），
        # 栏目页是目录无 .html —— 用「数字.html 结尾」可精确区分详情与栏目。
        "link_re": r"(/html/[\w\-/]+?/\d+\.html?)",
        "href_tpl": "https://www.chinania.org.cn{g1}",
        "category": "行业动态",
        "source": "中国有色金属工业协会",
        "foreign": False,
        "enabled": True,
        "note": "首页混入 news.cn 时政链接，靠 NOISE_KEYWORDS 过滤",
    },
    {
        "key": "cnmn",
        "name": "中国有色金属报",
        "list_url": "https://www.cnmn.com.cn/",
        "kind": "html",
        "link_re": r"(/ShowNews1\.aspx\?id=\d+)",
        "href_tpl": "https://www.cnmn.com.cn{g1}",
        "category": "行业动态",
        "source": "中国有色金属报",
        "foreign": False,
        "enabled": True,
        "note": "首页混入时政，需过滤",
    },
    {
        "key": "cgs",
        "name": "中国地质调查局",
        "list_url": "https://www.cgs.gov.cn/",
        "kind": "html",
        "link_re": r"\./(ywdt/[\w/]+/t\d{8}_\d+\.html)",
        "href_tpl": "https://www.cgs.gov.cn/{g1}",
        "category": "找矿成果与勘查技术",
        "source": "中国地质调查局",
        "foreign": False,
        "enabled": True,
        "note": "首页多为时政/旧闻，靠相关性+噪声双重过滤",
    },
    # 2026-09-08 实测 502 不可达，暂禁用；恢复后把 enabled 改 True 即可
    {
        "key": "chinamining",
        "name": "中国矿业网",
        "list_url": "https://www.chinamining.org.cn/",
        "kind": "html",
        "link_re": r"(https?://www\.chinamining\.org\.cn/[\w\-/]+\.html?)",
        "href_tpl": "{g1}",
        "category": "行业动态",
        "source": "中国矿业网",
        "foreign": False,
        "enabled": False,
        "note": "2026-09-08 实测 Tunnel 502，暂不可抓",
    },
    {
        "key": "zgkyb",
        "name": "中国矿业报",
        "list_url": "https://www.zgkyb.com/",
        "kind": "html",
        "link_re": r"([\w\-/]*\d{4}/\w+\.html?)",
        "href_tpl": "https://www.zgkyb.com/{g1}",
        "category": "行业动态",
        "source": "中国矿业报",
        "foreign": False,
        "enabled": False,
        "note": "2026-09-08 实测 Tunnel 502，暂不可抓",
    },
]

# ---------------------------------------------------------------------------
# 相关性：命中任一即视为有色金属行业相关（用于从混杂列表页里捞出目标）
# ---------------------------------------------------------------------------
METALS = ["铜", "铝", "铅", "锌", "镍", "锡", "金", "银", "稀土", "钨", "钼",
          "锑", "锂", "钴", "钛", "镁", "锰", "硅", "铂", "钯", "锆", "铍",
          "铟", "锗", "镓", "铌", "钽", "钒", "石墨"]
INDUSTRY_KW = [
    "有色", "金属", "矿业", "矿山", "矿产", "矿床", "矿权", "采矿", "选矿", "冶炼",
    "精炼", "电解", "勘查", "勘探", "找矿", "钻探", "见矿", "储量", "资源量",
    "地质", "矿", "冶炼厂", "精矿", "矿石", "品位", "产能", "产量", "复产", "投产",
    "进出口", "关税", "库存", "供需", "现货", "期货", "升水", "加工费",
]
# 英文关键词（2026-09-08 补）：境外源标题为英文，只有中文词表会让英文源 100% 被误滤。
# 实测 SMM 国际站 64 条 raw 曾全军覆没，即此原因。
METALS_EN = [
    "copper", "aluminium", "aluminum", "lead", "zinc", "nickel", "tin", "gold",
    "silver", "lithium", "cobalt", "tungsten", "molybdenum", "antimony", "titanium",
    "magnesium", "manganese", "silicon", "platinum", "palladium", "zirconium",
    "indium", "germanium", "gallium", "niobium", "tantalum", "vanadium", "graphite",
    "rare earth", "rare-earth", "bauxite", "alumina", "cathode", "anode",
    # 注：刻意不收 "REE" 等超短缩写 —— 子串会误命中 agreement/free/three。
    # 所有英文词一律走词边界匹配（见 _RE_METALS_EN）。
]
INDUSTRY_KW_EN = [
    "mining", "mine", "miner", "mines", "ore", "mineral", "smelter", "smelting",
    "refinery", "refining", "exploration", "drilling", "deposit", "reserve",
    "resource", "output", "production", "supply", "demand", "inventory", "stock",
    "stockpile", "export", "import", "tariff", "concentrate", "grade", "assay",
    "metal", "metals", "nonferrous", "non-ferrous", "critical minerals",
    "shipment", "premium", "discount", "surplus", "deficit", "smelter",
]
# 英文金属名 → 中文标签（保证入库 tags 与站内中文体系一致）
METAL_EN2CN = {
    "copper": "铜", "aluminium": "铝", "aluminum": "铝", "lead": "铅", "zinc": "锌",
    "nickel": "镍", "tin": "锡", "gold": "金", "silver": "银", "lithium": "锂",
    "cobalt": "钴", "tungsten": "钨", "molybdenum": "钼", "antimony": "锑",
    "titanium": "钛", "magnesium": "镁", "manganese": "锰", "silicon": "硅",
    "platinum": "铂", "palladium": "钯", "zirconium": "锆", "indium": "铟",
    "germanium": "锗", "gallium": "镓", "niobium": "铌", "tantalum": "钽",
    "vanadium": "钒", "graphite": "石墨", "rare earth": "稀土", "rare-earth": "稀土",
    "bauxite": "铝", "alumina": "铝",
}


def _compile_words(words):
    """英文关键词一律转为「词边界」正则。
    2026-09-08 修复：子串匹配会把 agreement→ree(稀土)、listing→tin(锡)、
    leading→lead(铅)、before/core→ore(矿石) 全部误判。加 \\b 后可精确命中单词。"""
    return [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in words]


_RE_METALS_EN = _compile_words(METALS_EN)
_RE_INDUSTRY_EN = _compile_words(INDUSTRY_KW_EN)
# ---------------------------------------------------------------------------
# 金融噪声：单看「银」会误判成「银行」，单看「期货」会误判成「纳指期货」。
# 故用组合判断——命中金融主体词 **且** 不含其他明确金属词时，才判为噪声。
# 这样「央行连续增持黄金」保留（无"银行"二字且含"金"），「财政部注资银行、险企」剔除。
# ---------------------------------------------------------------------------
FIN_NOISE = ["银行", "险企", "券商", "纳指", "道指", "美股", "港股", "A股",
             "股指", "理财", "信托", "债券", "银保", "银监", "证券", "IPO",
             "涨停", "跌停", "市值", "市盈率"]
# 这些金属词出现时，即使有金融词也倾向于是真行业新闻
_STRONG_METALS = [m for m in METALS if m not in ("银", "金")]


def is_fin_noise(title):
    if not any(k in title for k in FIN_NOISE):
        return False
    return not any(m in title for m in _STRONG_METALS)


# ---------------------------------------------------------------------------
# 噪声：命中任一即丢弃（列表页实测混入大量时政/服务类内容）
# ---------------------------------------------------------------------------
NOISE_KEYWORDS = [
    "习近平", "总书记", "主席", "总理", "委员长", "政协", "人大", "党中央", "国务院常务",
    "党建", "党史", "主题教育", "巡视", "纪检", "廉政", "任命", "免去", "同志",
    "招聘", "报名", "招生", "考试", "培训通知", "缴费", "公示（人事）",
    "天气预报", "彩票", "养生", "讣告", "悼", "开幕致辞", "贺信", "慰问",
    "登录", "注册", "订阅", "下载 APP", "隐私政策", "版权声明", "联系我们",
]
# 境外源广告/赞助路径（与 source_whitelist.FOREIGN_SPONSORED_PATTERNS 对应）
SPONSOR_PAT = re.compile(
    r"mining\.com/(sponsored-content|joint-venture)/|servedbyadbutler\.com", re.I)

# ---------------------------------------------------------------------------
# 黑色/能源排除：站内定位是「聚焦有色金属 … 排除：煤炭、石油、天然气、钢铁、铁矿」
# （见 index.html 底部）。境外源尤其容易混入 iron ore / coal，必须显式排除，
# 否则 INDUSTRY_KW_EN 里的 "ore"/"mine" 会把铁矿新闻当有色捞进来。
# ---------------------------------------------------------------------------
EXCLUDE_KW = ["铁矿", "煤炭", "钢铁", "石油", "天然气", "原油", "焦炭", "炼铁", "高炉"]
EXCLUDE_KW_EN = ["iron ore", "iron-ore", "iron", "coal", "steel", "crude oil",
                 "natural gas", "coking coal", "metallurgical coal", "pellet"]
_RE_EXCLUDE_EN = _compile_words(EXCLUDE_KW_EN)   # 须在 EXCLUDE_KW_EN 定义之后


# ============================================================================
# 网络层（与 fetch_ma.py 同风格：标准库 + 免验证 ssl + gzip + 多编码回退）
# ============================================================================
def http_get(url, timeout=TIMEOUT, retries=2):
    last = ""
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                for enc in ("utf-8", "gbk", "gb18030"):
                    try:
                        return raw.decode(enc)
                    except Exception:
                        continue
                return raw.decode("utf-8", "ignore")
        except Exception as e:
            last = str(e)
            if i < retries:
                continue
    return "__ERR__" + last


def clean_text(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = htmllib.unescape(s)
    s = s.replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


# ============================================================================
# 解析层
# ============================================================================
def parse_rss(xml_text, cfg):
    """解析 RSS/Atom，返回 [{title,url,date,summary}]"""
    out = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    nodes = root.findall(".//item")
    if not nodes:
        nodes = root.findall(".//atom:entry", ns)
    for it in nodes:
        def sub(tag, ns_tag=None):
            # 2026-09-08 修复：原写法 `it.find(tag) if ns_tag is None else it.find(ns_tag, ns)`
            # 对 RSS 2.0 会直接跳去 Atom 分支导致全部取空（mining.com 曾解析出 0 条）。
            # 正确顺序：先普通 tag，取不到再退回 Atom 命名空间。
            el = it.find(tag)
            if el is None and ns_tag:
                el = it.find(ns_tag, ns)
            return (el.text or "").strip() if el is not None and el.text else ""
        title = clean_text(sub("title", "atom:title"))
        link = sub("link", "atom:link")
        if not link:
            el = it.find("link")
            if el is not None:
                link = (el.get("href") or "").strip()
            if not link:
                el = it.find("atom:link", ns)
                if el is not None:
                    link = (el.get("href") or "").strip()
        # Atom 的 summary 常带 HTML
        summary = clean_text(sub("description", "atom:summary"))[:300]
        date = sub("pubDate", "atom:updated") or sub("pubDate") or sub("atom:updated", "atom:updated")
        if title and link:
            out.append({"title": title, "url": link, "date": date, "summary": summary})
    return out


def parse_html(html_text, cfg):
    """从列表页正则提取 链接+标题，返回 [{title,url,date,summary}]"""
    out = []
    link_re = re.compile(cfg["link_re"])
    tpl = cfg.get("href_tpl", "{g1}")
    base = cfg["list_url"]
    # 逐个 <a> 匹配，避免跨标签误配
    for m in re.finditer(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
                         html_text, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        title = clean_text(inner)
        if len(title) < 8:
            continue
        lm = link_re.search(href)
        if not lm:
            continue
        try:
            url = tpl.format(g1=lm.group(1), g0=lm.group(0))
        except Exception:
            url = urllib.parse.urljoin(base, href)
        if not url.startswith("http"):
            url = urllib.parse.urljoin(base, url)
        out.append({"title": title, "url": url, "date": "", "summary": ""})
    return out


# ============================================================================
# 过滤层
# ============================================================================
def is_allowed_domain(url):
    """复用 source_whitelist 的白名单，确保爬虫绝不会引入非授权源。"""
    try:
        sys.path.insert(0, BASE_DIR)
        import source_whitelist as sw
        return sw.is_allowed(url)
    except Exception:
        return False


def is_relevant(title):
    """中英文双语判定：中文子串匹配，英文词边界正则匹配。"""
    if any(m in title for m in METALS):
        return True
    if any(k in title for k in INDUSTRY_KW):
        return True
    if any(p.search(title) for p in _RE_METALS_EN):
        return True
    return any(p.search(title) for p in _RE_INDUSTRY_EN)


def extract_tags(title):
    """标签提取：中文金属词 + 英文金属词映射为中文，保证与站内 tag 体系一致。"""
    tags = {m for m in METALS if m in title}
    for en, cn in METAL_EN2CN.items():
        if re.search(r"\b" + re.escape(en) + r"\b", title or "", re.I):
            tags.add(cn)
    return sorted(tags) or ["有色"]


def is_noise(title, url):
    if SPONSOR_PAT.search(url or ""):
        return True
    for k in NOISE_KEYWORDS:
        if k in title:
            return True
    if is_fin_noise(title):
        return True
    # 黑色/能源排除（中英文；英文走词边界，避免 iron 命中 ironic 之类）
    for k in EXCLUDE_KW:
        if k in title:
            return True
    if any(p.search(title) for p in _RE_EXCLUDE_EN):
        return True
    # 境外源的赞助内容标题特征
    if re.search(r"^\s*(Sponsored|AD|Advertisement)\b", title, re.I):
        return True
    return False


def extract_date(url, rss_date, fallback, text=""):
    """日期提取优先级：RSS pubDate > URL 里的 8 位日期 > 正文日期 > fallback"""
    if rss_date:
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                dt = datetime.datetime.strptime(rss_date.strip()[:31], fmt)
                if dt.tzinfo:
                    dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
                return dt.strftime("%Y-%m-%d")
            except Exception:
                continue
    m = re.search(r"(20\d{2})[-/]?(0[1-9]|1[0-2])[-/]?(0[1-9]|[12]\d|3[01])", url or "")
    if m:
        return "%s-%s-%s" % (m.group(1), m.group(2), m.group(3))
    m = re.search(r"/t(20\d{6})", url or "")
    if m:
        d = m.group(1)
        return "%s-%s-%s" % (d[:4], d[4:6], d[6:8])
    blob = text or ""
    m = re.search(r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})", blob)
    if m:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    return fallback


def norm_title(t):
    """标题归一：去标点空白，用于跨源去重（同一事件多源报道只留一条）"""
    return re.sub(r"[\s\W_]+", "", t or "").lower()


def fetch_detail_summary(url, limit=180):
    """抓正文页补摘要（慢，默认关闭）"""
    h = http_get(url, timeout=15, retries=1)
    if h.startswith("__ERR__"):
        return ""
    h = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", h)
    # 优先取 meta description
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', h, re.I)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']', h, re.I)
    if m and len(clean_text(m.group(1))) > 20:
        return clean_text(m.group(1))[:limit]
    body = clean_text(h)
    return body[:limit]


# ============================================================================
# 主流程
# ============================================================================
def run_source(cfg, report_date, days, use_detail):
    if not cfg.get("enabled"):
        return [], "disabled"
    html_text = http_get(cfg["list_url"])
    if html_text.startswith("__ERR__"):
        return [], "fetch-fail: " + html_text[7:][:60]
    if cfg["kind"] == "rss":
        raw = parse_rss(html_text, cfg)
    else:
        raw = parse_html(html_text, cfg)

    cutoff = (datetime.date.fromisoformat(report_date)
              - datetime.timedelta(days=max(0, days - 1))).isoformat()
    items, seen_url, seen_title = [], set(), set()
    for r in raw:
        if len(items) >= MAX_PER_SOURCE:
            break
        url = r["url"].split("#")[0].rstrip("/")
        title = clean_text(r["title"])
        if not title or len(title) < 8:
            continue
        if not is_allowed_domain(url):
            continue
        if is_noise(title, url):
            continue
        if not is_relevant(title):
            continue
        nt = norm_title(title)
        if url in seen_url or nt in seen_title:
            continue
        seen_url.add(url)
        seen_title.add(nt)

        d = extract_date(url, r.get("date", ""), report_date, title)
        if d < cutoff:
            continue
        summary = r.get("summary") or ""
        if use_detail and not summary and len(items) < DETAIL_LIMIT:
            summary = fetch_detail_summary(url)
        items.append({
            "id": hashlib.md5(url.encode("utf-8")).hexdigest()[:12],
            "url": url,
            "title": title,
            "source": cfg["source"],
            "orig_date": d[5:],
            "orig_date_full": d,
            "report_date": report_date,
            "category": cfg["category"],
            "is_new": d == report_date,
            "summary": summary or title,
            "embed": "ok",
            "tags": extract_tags(title),
            "first_seen": report_date,
            "last_seen": report_date,
            "foreign": bool(cfg.get("foreign")),
            "fetch_src": cfg["key"],
        })
    return items, "ok(%d raw -> %d kept)" % (len(raw), len(items))


def merge_into_month(items, report_date):
    """并入 data/news_YYYY-MM.json（与 fetch_ma.py 的入库方式一致，幂等）"""
    month = report_date[:7]
    path = os.path.join(DATA_DIR, "news_%s.json" % month)
    data = {"month": month, "updated_at": "", "count": 0, "news": []}
    if os.path.exists(path):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    existing = {n.get("url"): n for n in data.get("news", [])}
    added = 0
    for it in items:
        if it["url"] in existing:
            existing[it["url"]]["last_seen"] = report_date
            continue
        data.setdefault("news", []).append(it)
        existing[it["url"]] = it
        added += 1
    data["count"] = len(data.get("news", []))
    data["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path, added, data["count"]


def main():
    ap = argparse.ArgumentParser(description="有色金属行业新闻自动爬虫（零依赖）")
    ap.add_argument("--report-date", default=datetime.date.today().isoformat(),
                    help="报告日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--days", type=int, default=1, help="回看天数，默认 1（只要当天）")
    ap.add_argument("--source", default="", help="只跑指定源 key，逗号分隔")
    ap.add_argument("--merge", action="store_true", help="抓完并入 data/news_YYYY-MM.json")
    ap.add_argument("--fetch-detail", action="store_true",
                    help="逐条抓正文补摘要（慢，默认关）")
    ap.add_argument("--dry-run", action="store_true", help="只打印不落盘")
    ap.add_argument("--list-sources", action="store_true", help="列出源配置")
    args = ap.parse_args()

    if args.list_sources:
        print("%-12s %-22s %-8s %-8s %s" % ("KEY", "名称", "类型", "启用", "境外"))
        for c in SOURCES:
            print("%-12s %-22s %-8s %-8s %s" % (
                c["key"], c["name"], c["kind"],
                "✔" if c.get("enabled") else "✘",
                "是" if c.get("foreign") else "否"))
        return

    keys = {k.strip() for k in args.source.split(",") if k.strip()}
    targets = [c for c in SOURCES if not keys or c["key"] in keys]

    print("=" * 72)
    print("fetch_news.py | 报告日期 %s | 回看 %d 天 | 源 %d 个"
          % (args.report_date, args.days, len(targets)))
    print("=" * 72)

    all_items, report = [], []
    for cfg in targets:
        items, status = run_source(cfg, args.report_date, args.days, args.fetch_detail)
        report.append((cfg["key"], cfg["name"], len(items), status))
        all_items.extend(items)

    print()
    print("%-12s %-22s %-5s %s" % ("KEY", "名称", "条数", "状态"))
    for k, n, c, s in report:
        print("%-12s %-22s %-5d %s" % (k, n, c, s))
    print("-" * 72)
    print("候选合计：%d 条（境外 %d 条）"
          % (len(all_items), sum(1 for i in all_items if i.get("foreign"))))

    if args.dry_run or not all_items:
        for i in all_items[:25]:
            print("  [%s|%s] %s" % (i["fetch_src"], i["orig_date"], i["title"][:52]))
            print("      %s" % i["url"][:96])
        if not all_items:
            print("  （无候选：可能是当天确实无新内容，或源结构变化需调整 link_re）")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    cand_path = os.path.join(DATA_DIR, "news_candidates_%s.json" % args.report_date)
    with open(cand_path, "w", encoding="utf-8") as f:
        json.dump({"report_date": args.report_date, "count": len(all_items),
                   "news": all_items}, f, ensure_ascii=False, indent=2)
    print()
    print("候选池已写入：%s" % cand_path)
    print("提示：AI 采编时读取该候选池挑选，境外条目（foreign=true）须走英文翻译规范。")

    if args.merge:
        path, added, total = merge_into_month(all_items, args.report_date)
        print("已并入月度库：%s（新增 %d，总计 %d）" % (path, added, total))

    print()
    print("候选条目预览（前 25 条）：")
    for i in all_items[:25]:
        flag = "🌍" if i.get("foreign") else "  "
        print("  %s[%s] %s | %s" % (flag, i["orig_date"], i["title"][:50], i["source"]))
        print("        %s" % i["url"][:92])


if __name__ == "__main__":
    main()
