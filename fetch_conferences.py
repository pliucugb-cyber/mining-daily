# -*- coding: utf-8 -*-
"""fetch_conferences.py —— 「会议日程」多源自动抓取器（2026-10-21）

为什么需要它
    右栏「会议日程」的会议预告不该靠"等新闻"填。会议通知天然分散在**各主办方自己的官网**，
    只盯一个发布方（如中国地质学会）必然漏。本脚本按「多源注册表 + 分层适配器」抓取：

      L1 专用适配器   结构稳定的源，逐字段精确解析
                      （Mining Journal 会议日历 / Global Mining Review 会议日历 /
                        中国地质学会·会议通知公告 / 中国有色网·会展信息）
      L2 通用列表抓取  任何"会议通知/会展信息"列表页 → 抽 <a> 标题，标题里正则抽日期
      L3 详情页补字段   列表页只有标题时，抓详情页正文抽「会议时间 / 地点」

    三条硬规矩：
      ① 绝不猜日期。抽不到就是 tbd（"日期待定"），由人工补。
      ② 人工条目优先。data/conferences.json 的 manual 区脚本永不覆盖、也永不删除。
      ③ 抓取失败不退化。任一源失败只跳过该源；全部源失败则**保留上一次数据不动**并以非零码退出。

数据流
    data/conference_sources.json  源注册表（增源＝加一条配置，不用改代码）
    data/conferences.json          唯一数据源（manual 人工 + auto 自动）
    conference-data.js             生成产物（window.CONFERENCE_DATA），勿直接改

用法
    python fetch_conferences.py              # 全量抓取 → 更新 conferences.json → 重新生成 conference-data.js
    python fetch_conferences.py --dry-run    # 只抓取与解析，打印结果，不落盘
    python fetch_conferences.py --export-only  # 不抓取，仅由 conferences.json 重新生成 conference-data.js
    python fetch_conferences.py --source gmr # 只跑指定源
"""
import datetime
import gzip
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_FILE = os.path.join(ROOT, 'data', 'conference_sources.json')
DATA_FILE = os.path.join(ROOT, 'data', 'conferences.json')
OUT_JS = os.path.join(ROOT, 'conference-data.js')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
HEADERS = {
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'close',
}
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

# ────────────────────────────── HTTP ──────────────────────────────


def fetch(url, timeout=30, retries=2):
    """抓网页；返回 text，失败抛异常。"""
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                raw = r.read()
                if r.headers.get('Content-Encoding', '') == 'gzip':
                    try:
                        raw = gzip.decompress(raw)
                    except OSError:
                        pass
                for enc in ('utf-8', 'gb18030', 'latin-1'):
                    try:
                        return raw.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return raw.decode('utf-8', 'replace')
        except Exception as e:          # noqa: BLE001 - 网络异常一律重试
            last = e
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError('fetch failed: %s (%s)' % (url, last))


def strip_tags(html):
    """去标签 → 纯文本（保留空白折叠），用于正文里找日期/地点。"""
    t = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', html)
    t = re.sub(r'(?s)<[^>]+>', ' ', t)
    t = t.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    t = re.sub(r'&[a-zA-Z#0-9]{2,8};', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


# ────────────────────────────── 日期解析 ──────────────────────────────
MON_EN = {m.lower(): i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'], 1)}
MON_EN.update({m[:3].lower(): i for m, i in list(MON_EN.items())})


def _iso(y, m, d):
    try:
        if not (1 <= m <= 12 and 1 <= d <= 31):
            return None
        return '%04d-%02d-%02d' % (y, m, d)
    except Exception:
        return None


def parse_cn_date(text, default_year=None):
    """中文日期：2026年11月16日-18日 / 2026年11月16日至18日 / 11月16-18日 / 11月16日
    返回 (start_iso, end_iso)，抽不到返回 (None, None)"""
    if not text:
        return None, None
    y0 = default_year or datetime_now().year
    # 1) 2026年11月16日-18日 / 2026年11月16日至18日 / 2026年11月18-21日
    m = re.search(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*[-—－~至到]?\s*'
                  r'(?:(\d{1,2})\s*月\s*)?(\d{1,2})?\s*日?', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if m.group(5):
            em, ed = mo, int(m.group(5))
        elif m.group(4):
            em, ed = int(m.group(4)), d
        else:
            em, ed = mo, d
        return _iso(y, mo, d), _iso(y, em, ed)
    # 2) 11月16-18日（无年份）
    m = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*[-—－~至到]\s*(\d{1,2})\s*日', text)
    if m:
        mo, d, d2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _iso(y0, mo, d), _iso(y0, mo, d2)
    # 3) 11月16日（单日）
    m = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日', text)
    if m:
        return _iso(y0, int(m.group(1)), int(m.group(2))), _iso(y0, int(m.group(1)), int(m.group(2)))
    return None, None


def parse_en_date(text, ctx_month=None, ctx_year=None):
    """英文日期：08 February 2027 - 11 February 2027 / 27 - 29 Oct 2026 / October 27 – 29
    返回 (start_iso, end_iso)"""
    if not text:
        return None, None
    t = text.replace('\u2013', '-').replace('\u2014', '-')
    # 1) 08 February 2027 - 11 February 2027
    m = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*-\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', t)
    if m and m.group(2).lower() in MON_EN:
        mo = MON_EN[m.group(2).lower()]
        return _iso(int(m.group(3)), mo, int(m.group(1))), \
            _iso(int(m.group(6)), MON_EN[m.group(5).lower()], int(m.group(4)))
    # 2) 27 - 29 Oct 2026
    m = re.search(r'(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', t)
    if m and m.group(3).lower() in MON_EN:
        mo = MON_EN[m.group(3).lower()]
        return _iso(int(m.group(4)), mo, int(m.group(1))), _iso(int(m.group(4)), mo, int(m.group(2)))
    # 3) October 27 - 29（需上下文月/年）
    m = re.search(r'([A-Za-z]+)\s+(\d{1,2})\s*-\s*(\d{1,2})', t)
    if m and m.group(1).lower() in MON_EN and ctx_month:
        mo = MON_EN[m.group(1).lower()]
        y = ctx_year or datetime_now().year
        return _iso(y, mo, int(m.group(2))), _iso(y, mo, int(m.group(3)))
    # 4) 27 October 2026（单日）
    m = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', t)
    if m and m.group(2).lower() in MON_EN:
        mo = MON_EN[m.group(2).lower()]
        return _iso(int(m.group(3)), mo, int(m.group(1))), _iso(int(m.group(3)), mo, int(m.group(1)))
    # 5) October 27（单日，需上下文年）
    m = re.search(r'([A-Za-z]+)\s+(\d{1,2})(?![\d-])', t)
    if m and m.group(1).lower() in MON_EN and ctx_year:
        mo = MON_EN[m.group(1).lower()]
        return _iso(ctx_year, mo, int(m.group(2))), _iso(ctx_year, mo, int(m.group(2)))
    return None, None


def datetime_now():
    return datetime.date.today()


# ────────────────────────────── 标题归一化 / 去重 ──────────────────────────────
# 归一化只做「可证明等价」的剥离，绝不吞掉会议名本体
#   （旧版 `关于(召开|...)[^，,。；;]{0,30}` 会把整条会议名吃掉 → 归一后为空 → 判重失效）
_NOISE = re.compile(r'[（(【\[][^）)】\]]{0,20}[）)】\]]'
                    r'|第[一二三四五六七八九十百零\d]+届'
                    r"|[\s、,，。；;：:·!！?？\-—－_\"'“”‘’]+")
_NOISE_PREFIX = re.compile(r'^关于(召开|举办|组织参加|报送|开展|举办|主办)')
_NOISE_SUFFIX = re.compile(r'(的)?(通知|公告)(（[一二三四五六七八九十]?号通知?）)?\s*$')


def norm_title(t):
    """归一化标题用于跨源判重（去掉届次/通知后缀/标点）"""
    if not t:
        return ''
    s = t.strip()
    s = re.sub(r'[（(](?:一号|二号|三号|四号|五号)?通知[）)]\s*$', '', s)
    s = _NOISE_PREFIX.sub('', s)
    s = _NOISE_SUFFIX.sub('', s)
    s = _NOISE.sub('', s)
    return s.lower()


def clean_cn_title(t):
    """中文会议通知标题 → 展示用会议名
       "关于召开2026年全国城市地质学术年会的通知（二号通知）" → "2026年全国城市地质学术年会"
       原始标题保留在 note 里（便于回溯与去重）。"""
    if not t:
        return t
    s = t.strip()
    s = re.sub(r'[（(](?:第?[一二三四五六七八九十\d]+号(?:通知)?)?[）)]\s*$', '', s)
    s = re.sub(r'^关于(召开|举办|组织参加|报送|开展)', '', s)
    s = re.sub(r'(的)?第?[一二三四五六七八九十\d]*轮?(通知|公告)?\s*$', '', s)
    s = re.sub(r'(的)?(通知|公告)\s*$', '', s)
    s = re.sub(r'^[“"\'「『]', '', s)
    s = re.sub(r'[”"\'」』]\s*$', '', s)
    return s.strip()


_ACRONYM = re.compile(r'\b([A-Z]{2,6})\b')
_ACRONYM_STOP = set(['THE', 'AND', 'FOR', 'INC', 'LTD', 'USA', 'CEO', 'Q&A'])


def conf_acronyms(t):
    """取标题里的大写缩写（PDAC / IMARC / MRMR / GAC …），用于跨语种识别同一场会"""
    if not t:
        return set()
    out = set()
    for a in _ACRONYM.findall(t):
        if a not in _ACRONYM_STOP:
            out.add(a)
    return out


def _date_of(it):
    s = it.get('s') or ''
    try:
        return datetime.date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except Exception:
        return None


def same_event2(it1, it2):
    """条目级判重：在标题相似度之外，补「共享缩写 + 日期接近」规则"""
    if same_event(it1.get('t', ''), it2.get('t', '')):
        return True
    ac1, ac2 = conf_acronyms(it1.get('t', '')), conf_acronyms(it2.get('t', ''))
    if not (ac1 & ac2):
        return False
    d1, d2 = _date_of(it1), _date_of(it2)
    if not d1 or not d2:
        return False
    return abs((d1 - d2).days) <= 3


def same_event(a, b):
    """判两场会是否同一场：标题相似度高，或标题核心词相同"""
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    r = SequenceMatcher(None, na, nb).ratio()
    if r >= 0.86:
        return True
    # 核心词包含（去掉年份后互为子串且长度够）
    ca = re.sub(r'20\d{2}', '', na).strip()
    cb = re.sub(r'20\d{2}', '', nb).strip()
    if len(ca) >= 6 and len(cb) >= 6 and (ca in cb or cb in ca):
        return True
    return False


# ────────────────────────────── 源适配器 ──────────────────────────────
def _abs(base, href):
    if not href:
        return ''
    if href.startswith('http'):
        return href
    if href.startswith('//'):
        return 'https:' + href
    if href.startswith('/'):
        from urllib.parse import urljoin
        return urljoin(base, href)
    from urllib.parse import urljoin
    return urljoin(base, href)


def parse_miningjournal(html, src):
    """Mining Journal 会议日历：结构化（event-name / event-date / event-location）"""
    out = []
    chunks = html.split('<div class="event bottom-border">')[1:]
    for ch in chunks:
        m = re.search(r'<h5 class="event-name">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', ch, re.S)
        if not m:
            continue
        title = strip_tags(m.group(2))
        if not title:
            continue
        dm = re.search(r'class="event-date"[^>]*>(.*?)</h4>', ch, re.S)
        lm = re.search(r'class="event-location"[^>]*>(.*?)</p>', ch, re.S)
        dtext = strip_tags(dm.group(1)).replace('Event Date:', '') if dm else ''
        place = strip_tags(lm.group(1)).replace('Event Location:', '') if lm else ''
        s, e = parse_en_date(dtext)
        out.append({
            't': title, 's': s or '', 'e': e or '',
            'p': place.strip(), 'o': src.get('publisher', ''),
            'tag': '国际矿业', 'u': _abs(src['url'], m.group(1)),
            'note': src.get('note', ''),
            'v': 'ok' if s else 'tbd',
            'src': src['id'],
        })
    return out


def parse_gmr(html, src):
    """Global Mining Review 会议日历：Next.js RSC payload
       /events/<slug>/ 之后依次是：img 的 alt(=完整会议名) → event-card-day/month → 日期串
       "27 - 29 Oct 2026"。取 alt 拿全名，不靠 slug 猜标题。"""
    out = []
    for m in re.finditer(r'"(/events/[a-z0-9\-]+)/"', html):
        href = m.group(1)
        win = html[m.start():m.start() + 3000]
        # 兼容两种渲染形态：服务端 HTML 的 alt="v" 与 RSC 的 \"alt\":\"v\"
        tm = re.search(r'alt="([^"]{6,160})"', win[:2200])
        if not tm:
            tm = re.search(r'\\"alt\\":\\"([^"\\]{6,160})', win[:2200])
        if not tm:
            tm = re.search(r'\\?"children\\?":\\?"([A-Z][^"\\]{8,160})', win[:2200])
        dm = re.search(r'(\d{1,2}\s*-\s*\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})', win)
        if not tm or not dm:
            continue
        title = tm.group(1).strip()
        s, e = parse_en_date(dm.group(1))
        if not s or not title:
            continue
        out.append({
            't': title, 's': s, 'e': e or s, 'p': '', 'o': src.get('publisher', ''),
            'tag': '国际矿业', 'u': _abs(src['url'], href), 'note': src.get('note', ''),
            'v': 'ok', 'src': src['id'],
        })
    seen, uniq = set(), []
    for it in out:
        if it['u'] in seen:
            continue
        seen.add(it['u'])
        uniq.append(it)
    return uniq

_CN_CONF = re.compile(r'(关于召开|关于举办|关于组织参加|关于报送|学术会议|研讨会|年会|论坛|大会|展览会|博览会|交流会|年会)')
# 事后报道特征（已发生的会议）→ 不进「会议日程」
_PAST_REPORT = re.compile(r'(在[^，。]{0,25}(召开|举行|开幕)|圆满|落幕|闭幕|收官|成功举办|正式召开|隆重开幕|亮相|圆满举办)')
# 预告特征（含"将于/定于"等明确未来表述）
_UPCOMING_HINT = re.compile(r'(将于|拟于|定于|即将|即将于|日前召开|定档|通知|预登记|注册|征稿)')
# 值得抓详情页补日期的标题特征：官方通知 或 明确的未来预告
_FUTURE_HINT = re.compile(r'(通知|将于|拟于|定于|定档|举办|即将|预告|征稿|预登记)')


def parse_cn_list(html, src):
    """通用中文列表页：抽 <a> 标题（命中会议关键词的才留），日期从标题正则抽
    geosociety 的通知列表（中国地质学会）与 cnmn 的会展信息（中国有色网）都走这里。"""
    out = []
    for m in re.finditer(r'<a\b[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', html, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        title = strip_tags(inner)
        if not title or len(title) > 90 or not _CN_CONF.search(title):
            continue
        # 排除纯栏目导航
        if len(title) < 8:
            continue
        # 事后报道（"…在烟台召开"「圆满/落幕/收官/亮相」）不是预告 → 不进日程
        if _PAST_REPORT.search(title) and not _UPCOMING_HINT.search(title):
            continue
        s, e = parse_cn_date(title)
        disp = clean_cn_title(title)
        note = src.get('note', '')
        if disp != title:
            note = (note + ' · ' if note else '') + '原标题：' + title
        out.append({
            't': disp, 's': s or '', 'e': e or '', 'p': '', 'o': src.get('publisher', ''),
            'tag': src.get('tag', '会议'), 'u': _abs(src['url'], href),
            'note': note, 'v': 'ok' if s else 'tbd', 'src': src['id'],
        })
    return out


def parse_geo_list(html, src):
    """中国地质学会会议通知公告：只取 v6=1 的详情链接，标题含「关于召开/举办/组织参加…通知」"""
    out = []
    for m in re.finditer(r'<a\b[^>]*href=[\'"](\?[^"\']*v6=1[^\'"]*)[\'"][^>]*>(.*?)</a>', html, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        title = strip_tags(inner)
        if not title or not re.search(r'(关于召开|关于举办|关于组织参加)', title):
            continue
        if '通知' not in title:
            continue
        disp = clean_cn_title(title)
        out.append({
            't': disp, 's': '', 'e': '', 'p': '', 'o': '中国地质学会',
            'tag': '会议通知', 'u': _abs(src['url'], href),
            'note': '官方通知 · 日期待定 · 原标题：' + title,
            'v': 'tbd', 'src': src['id'],
        })
    return out


PARSERS = {
    'miningjournal': parse_miningjournal,
    'gmr': parse_gmr,
    'cn_list': parse_cn_list,
    'geo_notice': parse_geo_list,
}


# ────────────────────────────── 详情页补字段（L3） ──────────────────────────────
_ANCHOR_DATE = [
    r'将于\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*[-—－~至到]?\s*(?:(\d{1,2})\s*月\s*)?(\d{1,2})?\s*日?',
    r'(?:会议|会展|活动)(?:时间|日期)[：:]\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?',
    r'定于\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?',
    r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[-—－~至到]\s*(\d{1,2})\s*日',
    r'于\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日[^，。]{0,20}(?:召开|举办|举行)',
    r'定档[^，。]{0,12}?(\d{1,2})\s*月\s*(\d{1,2})\s*日?',
]


def parse_anchored_cn_date(text):
    """锚定式抽会议时间：只认「将于…」「会议时间：」「定于…」「…日-…日」「于…日…召开」
    这些明确表述，**不取正文第一个日期**（那通常是发布日期/报名截止日）。"""
    if not text:
        return None, None
    for pat in _ANCHOR_DATE:
        m = re.search(pat, text)
        if not m:
            continue
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        em = ed = None
        if m.lastindex and m.lastindex >= 5:
            if m.group(5):
                em, ed = mo, int(m.group(5))
            elif m.group(4):
                em, ed = int(m.group(4)), d
        s = _iso(y, mo, d)
        e = _iso(y, em, ed) if em else s
        if s and (not e or e >= s):
            return s, e
    return None, None


def enrich_from_detail(item, max_fetch=25, sleep=0.6):
    """列表页只有标题时抓详情页补时间/地点。
    只对「通知」类标题做 —— 普通新闻（"…在烟台召开"）正文里的日期不可信，且它们本就不是预告。"""
    if not item.get('u') or item.get('s'):
        return item
    if not _FUTURE_HINT.search(item.get('t') or ''):
        return item
    try:
        html = fetch(item['u'], timeout=25, retries=1)
    except Exception:
        return item
    text = strip_tags(html)
    s, e = parse_anchored_cn_date(text)
    if s:
        item['s'], item['e'] = s, e or s
        item['v'] = 'ok'
    m = re.search(r'在\s*([一-龥A-Za-z]{2,18}?)\s*(?:召开|举行|举办|开幕)', text)
    if m and not item.get('p'):
        item['p'] = m.group(1)
    m2 = re.search(r'(?:会议地点|举办地点|地点)[：:]\s*([^\s，,。；;]{2,24})', text)
    if m2 and not item.get('p'):
        item['p'] = m2.group(1)
    return item

def filter_items(items):
    """清洗候选：
       ① 日期自洽（e >= s，否则视为解析失败 → tbd）
       ② 明显过期（开始日早于今天 60 天以上）→ 丢弃；若是官方通知则降级为 tbd 保留
       ③ 无日期的：只保留官方「通知」类（其余是资讯/事后报道，不构成日程）"""
    out = []
    today = datetime_now()
    for it in items:
        s, e = it.get('s') or '', it.get('e') or ''
        title = it.get('t') or ''
        if s and e and e < s:
            s, e = '', ''
        if s:
            try:
                sd = datetime.date(int(s[:4]), int(s[5:7]), int(s[8:10]))
                ed = datetime.date(int(e[:4]), int(e[5:7]), int(e[8:10])) if e else sd
                if ed < today:
                    # 会议已结束 → 不进日程（官方通知降级为 tbd 保留，其余丢弃）
                    if _FUTURE_HINT.search(title + ' ' + (it.get('note') or '')):
                        s, e = '', ''
                    else:
                        continue
            except Exception:
                pass
        # 判定"是否官方通知"：标题可能已被清洗掉「通知」二字，原标题在 note 里
        blob = title + ' ' + (it.get('note') or '')
        if not s and not _FUTURE_HINT.search(blob):
            continue
        it['s'], it['e'] = s, e
        if not s:
            it['v'] = 'tbd'
        out.append(it)
    return out


# ────────────────────────────── 主流程 ──────────────────────────────
def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with io.open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, obj):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))


def sort_key(it):
    s = it.get('s') or '9999-12-31'
    return (s, it.get('t', ''))


def dedup(items, keep=()):
    """跨源判重：keep 里的条目（人工）优先，自动条目与之重复则丢弃"""
    out = list(keep)
    for it in items:
        dup = False
        for k in out:
            if same_event2(it, k):
                dup = True
                # 补齐：人工缺日期而自动有 → 补上；反之不覆盖人工
                if not k.get('s') and it.get('s'):
                    k['s'], k['e'] = it['s'], it.get('e') or it['s']
                    k['v'] = 'ok'
                if not k.get('p') and it.get('p'):
                    k['p'] = it['p']
                if not k.get('u') and it.get('u'):
                    k['u'] = it['u']
                break
        if not dup:
            out.append(it)
    return out


def render_js(data):
    """生成 conference-data.js（window.CONFERENCE_DATA）"""
    items = dedup(list(data.get('manual', [])) + list(data.get('auto', [])))
    items = sorted(items, key=sort_key)
    lines = []
    for it in items:
        parts = []
        for k in ('s', 'e', 't', 'p', 'o', 'tag', 'u', 'note', 'v'):
            v = it.get(k, '')
            if v == '' or v is None:
                continue
            parts.append("%s:'%s'" % (k, str(v).replace('\\', '\\\\').replace("'", "\\'")))
        lines.append('    { ' + ', '.join(parts) + ' }')
    updated = data.get('updated', '')
    body = "\n".join(lines)
    return (
        "/* conference-data.js —— 【自动生成，勿直接改】\n"
        " * 数据源：data/conferences.json（manual 人工 + auto 自动）\n"
        " * 生成器：fetch_conferences.py（python fetch_conferences.py --export-only 可重新生成）\n"
        " * 维护：人工条目请改 data/conferences.json 的 manual 区，脚本永不覆盖该区。\n"
        " * 字段：s/e 起止日期 · t 标题 · p 地点 · o 主办方 · tag 分类 · u 官方链接\n"
        " *       note 补充信息 · v 日期可信度（ok/tbd）\n"
        " */\n"
        "window.CONFERENCE_DATA = {\n"
        "  updated: '%s',\n"
        "  source: '多源自动抓取 + 人工维护（详见 data/conference_sources.json）',\n"
        "  items: [\n%s\n  ]\n"
        "};\n" % (updated, body)
    )


def main():
    args = sys.argv[1:]
    dry = '--dry-run' in args
    export_only = '--export-only' in args
    only = None
    if '--source' in args:
        only = args[args.index('--source') + 1]

    data = load_json(DATA_FILE, {'updated': '', 'manual': [], 'auto': []})
    manual = data.get('manual', [])

    if export_only:
        js = render_js(data)
        if not dry:
            with io.open(OUT_JS, 'w', encoding='utf-8', newline='\n') as f:
                f.write(js)
        print('[export] conference-data.js 已生成（%d 条）' % (len(manual) + len(data.get('auto', []))))
        return 0

    src_cfg = load_json(SRC_FILE, {'sources': []})
    sources = src_cfg.get('sources', [])
    if only:
        sources = [s for s in sources if s['id'] == only]
        if not sources:
            print('[error] 没有 id=%s 的源' % only)
            return 2

    collected, per_source, failed = [], [], []
    for src in sources:
        if not src.get('enabled', True):
            per_source.append((src['id'], 'SKIP(未启用)', 0))
            continue
        parser = PARSERS.get(src.get('parser', ''))
        if not parser:
            per_source.append((src['id'], 'SKIP(无适配器)', 0))
            continue
        try:
            html = fetch(src['url'], timeout=src.get('timeout', 30))
        except Exception as e:                     # noqa: BLE001
            failed.append(src['id'])
            per_source.append((src['id'], 'FAIL(%s)' % str(e)[:60], 0))
            continue
        try:
            items = parser(html, src)
        except Exception as e:                     # noqa: BLE001
            failed.append(src['id'])
            per_source.append((src['id'], 'PARSE-ERR(%s)' % str(e)[:50], 0))
            continue
        per_source.append((src['id'], 'OK', len(items)))
        collected.extend(items)

    # L3：详情页补日期/地点（只对没日期的候选，且限量）
    need = [it for it in collected if not it.get('s')][:60]
    enriched = 0
    for it in need:
        before = bool(it.get('s'))
        it = enrich_from_detail(it)
        if it.get('s') and not before:
            enriched += 1
        time.sleep(0.5)

    # 清洗候选（日期自洽 / 过期 / tbd 只留通知类）
    collected = filter_items(collected)

    # 判重：人工优先
    merged = dedup(collected, keep=manual)
    auto = [it for it in merged if it not in manual]
    # 去掉与人工重复的（merged 里已按 keep 优先处理，这里再滤一次保险）
    auto = [it for it in auto if not any(same_event2(it, m) for m in manual)]

    print('\n===== 各源抓取结果 =====')
    for sid, st, n in per_source:
        print('  %-16s %-46s %d 条' % (sid, st, n))
    print('  抓取候选 %d 条 → 详情页补全日期 %d 条 → 判重后自动条目 %d 条' % (len(collected), enriched, len(auto)))
    dated = [i for i in auto if i.get('s')]
    tbd = [i for i in auto if not i.get('s')]
    print('  其中有明确日期 %d 条 / 日期待定 %d 条' % (len(dated), len(tbd)))

    if not sources or all(st.startswith(('FAIL', 'PARSE-ERR', 'SKIP')) for _, st, _ in per_source):
        print('[error] 所有源都失败 → 保留原数据不动，不落盘。请检查网络或源配置。')
        return 1

    if dry:
        print('\n----- dry-run：不落盘。前 15 条 -----')
        for it in sorted(dated + tbd, key=sort_key)[:15]:
            print('  %s ~ %s | %-46s | %s | %s' % (it.get('s') or '待定', it.get('e') or '待定',
                                                  it.get('t', '')[:46], it.get('p', '')[:18], it.get('v')))
        return 0

    data['manual'] = manual
    data['auto'] = auto
    data['updated'] = datetime_now().isoformat()
    data['source_stats'] = [{'id': s, 'status': st, 'count': n} for s, st, n in per_source]
    save_json(DATA_FILE, data)
    with io.open(OUT_JS, 'w', encoding='utf-8', newline='\n') as f:
        f.write(render_js(data))
    print('\n[ok] 已更新 data/conferences.json（auto %d 条）并重新生成 conference-data.js' % len(auto))
    if failed:
        print('[warn] 失败源：%s（已跳过，保留人工数据）' % ', '.join(failed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
