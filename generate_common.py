# -*- coding: utf-8 -*-
"""
generate_common.py — generate_YYYYMMDD.py 系列生成器的公共骨架。

背景
----
generate_2026MMDD.py 是「每天复制一份、改数据」的产物：11 份脚本 4633 行，
其中约 200 行是逐字重复的骨架（条目渲染、价格卡渲染、区块定位、计数同步…）。
本模块把这部分抽出来，供生成器 import。

约束（改这里前先看）
--------------------
1. **旧脚本不动。** generate_20260830 ~ generate_20260909 是历史产物，保持原样，
   它们是「当天产出可复现」的依据。只有新增/改动的生成器才 import 本模块。
2. **不改调用方式。** 06:00 自动化 prompt 写死了「重建页面必须用当日的
   generate_YYYYMMDD.py」，所以文件名与 `python generate_YYYYMMDD.py` 的调用
   方式不能变——本模块只是被 import，不改变任何外部接口。
3. **抽出的是纯函数。** 依赖当日全局量（REPORT_DT / CUTOFF_DT / CAT_MAP /
   CAT_MA / MA_REQUIRE）的三个函数改为显式传参，生成器用 functools.partial
   绑定，语义与原来读全局变量完全一致。

已按此模式改造的示范脚本：generate_20260910.py
"""
import datetime
import re

from source_whitelist import is_allowed

# ---- 价格卡涨跌符号（中国市场约定：涨红跌绿，符号只是方向） ----
UP, DOWN, FLAT = '&#9650;', '&#9660;', '■'

# ---- 三锚点：生成器靠它们切分区块，字符串不可动 ----
TAG_TODAY = '<div class="section" id="todaySection"'
TAG_ARCH = '<div class="section" id="archiveSection"'
TAG_RIGHTS = '<div class="section" id="rightsSection"'

# ---- 类目常量（展示层 7 个桶；emoji 是桶名的一部分，不可随意改） ----
CAT_KQ = '💼 矿权交易'
CAT_ZK = '🔍 找矿成果与勘查技术'
CAT_ZC = '📜 政策与监管'
CAT_SC = '📊 市场与价格'
CAT_HY = '🏭 行业动态'
CAT_GJ = '🌐 国际矿业动态'
CAT_MA = '💰 并购与投资'

# ---- 内容类（数据层 8 类，由 LLM 分类写入 category 字段）+ 地域 → 展示桶 ----
# 为什么分两层：数据层只记「这条讲什么 + 发生在哪」，展示层决定「页面上归到哪一栏」。
# 这样以后要调整页面分栏，不用再动存量数据。
THEME_BUCKET = {
    ('矿权出让', '国内'): CAT_KQ, ('矿权出让', '国际'): CAT_KQ,
    ('并购与投资', '国内'): CAT_MA, ('并购与投资', '国际'): CAT_MA,
    ('政策与监管', '国内'): CAT_ZC, ('政策与监管', '国际'): CAT_ZC,
    ('市场与价格', '国内'): CAT_SC, ('市场与价格', '国际'): CAT_SC,
    ('技术与勘查', '国内'): CAT_ZK, ('技术与勘查', '国际'): CAT_ZK,
    ('会议会展', '国内'): CAT_HY, ('会议会展', '国际'): CAT_GJ,
    ('项目与产能', '国内'): CAT_HY, ('项目与产能', '国际'): CAT_GJ,
    ('企业经营', '国内'): CAT_HY, ('企业经营', '国际'): CAT_GJ,
    ('行业动态', '国内'): CAT_HY, ('行业动态', '国际'): CAT_GJ,
}

# 旧分类名（按信源硬编码，2026-09-10 前的存量）→ 展示桶。
# 没有 region 字段的旧数据走这张表，保证新老数据混跑时都不丢条目。
LEGACY_BUCKET = {
    '行业动态': CAT_HY,
    '国际矿业动态': CAT_GJ,
    '找矿成果与勘查技术': CAT_ZK,
    '并购与投资': CAT_MA,
    '矿权交易': CAT_KQ,
    '矿权市场': CAT_KQ,
    '培训与学术': CAT_HY,
    '政策法规': CAT_ZC,
    '市场行情与价格异动': CAT_SC,
    '贸易进出口与库存': CAT_SC,
    '环保安全': CAT_HY,
    '上市公司经营动态': CAT_HY,
    '上市公司公告': CAT_HY,
    '政策与监管': CAT_ZC,
}


def bucket(theme, region=''):
    """(内容类, 地域) → 展示桶。查不到就回落旧分类表，再查不到给 CAT_HY，绝不返回 None。

    历史教训：早期 _lib_item 用 cat_map.get(...)，未知分类直接 return None，
    结果整批条目在生成时静默消失。这里保证永远有出路。
    """
    if (theme, region) in THEME_BUCKET:
        return THEME_BUCKET[(theme, region)]
    if theme in LEGACY_BUCKET:
        return LEGACY_BUCKET[theme]
    if (theme, '国内') in THEME_BUCKET:
        return THEME_BUCKET[(theme, '国内')]
    return CAT_HY

# ---- 并购重归类关键词（inject_ma.py 注入后再次归类用） ----
MA_REQUIRE = ['收购', '并购', '受让', '股权转让', '资产重组', '资产购买', '资产出售',
              '增资', '认购', '合资', '定增', '资产置换', '向特定对象发行', '拟收购', '拟转让', '要约收购']


def window(report, archive_days=30):
    """按报告日推算归档窗口，返回 (REPORT_DT, CUTOFF_DT)。

    历史上出现过「复制旧脚本把窗口带回 7 天」的坑，故窗口必须由报告日推算，
    不要在脚本里写死日期。
    """
    report_dt = datetime.date.fromisoformat(report)
    cutoff_dt = report_dt - datetime.timedelta(days=archive_days - 1)
    return report_dt, cutoff_dt


# ============================ 条目 / 区块渲染 ============================

def ni(url, src, date, title, summary, embed='ok', orig_title=''):
    """构造今日新增条目，并强制校验 URL 在白名单内。境外条目保留英文原题。"""
    if not is_allowed(url):
        raise ValueError("URL 不在允许信源白名单内: %s" % url)
    ot = ' data-orig-title="%s"' % orig_title if orig_title else ''
    if orig_title:
        summary = '%s（原题：%s）' % (summary, orig_title)
    return ('<div class="news-item is-new"%s data-url="%s" data-embed="%s"><div class="news-head"><span class="dot"></span>'
            '<span class="badge-new">NEW</span><a class="news-title" href="%s" target="_blank">%s</a></div>'
            '<div class="news-meta"><span class="src">%s</span> · %s</div><div class="news-summary">%s</div>'
            '</div>'
            % (ot, url, embed, url, title, src, date, summary))


def card(slug, name, tag, value, unit, chg_text, cls):
    return ('<div data-slug="%s" class="price-card %s"><div class="pc-name">%s <span class="pc-tag">%s</span></div>'
            '<div class="pc-value">%s</div><div class="pc-unit">%s</div><div class="pc-chg">%s</div></div>'
            % (slug, cls, name, tag, value, unit, chg_text))


def _replace_block(h, tag, inner_html):
    """按 div 深度匹配替换整个块，避免非贪婪正则在第一张卡片处提前截断。"""
    i = h.find(tag)
    assert i != -1, 'block not found: %s' % tag
    j = h.find('>', i) + 1
    depth = 1
    n = len(h)
    while j < n and depth > 0:
        if h.startswith('<div', j):
            depth += 1
            k = h.find('>', j)
            j = (k + 1) if k != -1 else n
        elif h.startswith('</div>', j):
            depth -= 1
            j += 6
        else:
            j += 1
    return h[:i] + tag + inner_html + '</div>' + h[j:]


def split_items(block):
    out = []
    cat = None
    for mm in re.finditer(r'<div class="sub-cat"[^>]*>([^<]*)<span class="sub-count"[^>]*>([^<]*)</span></div>'
                          r'|<div class="news-item[^>]*>.*?</div>\s*</div>', block, re.S):
        if mm.group(1) is not None:
            cat = mm.group(1).strip()
        elif mm.group(0).startswith('<div class="news-item'):
            if cat:
                out.append((cat, mm.group(0)))
    return out


def item_url(it):
    m = re.search(r'data-url="([^"]+)"', it)
    return m.group(1) if m else it


def strip_new(it):
    it = it.replace(' is-new', '')
    it = re.sub(r'<span class="badge-new"[^>]*>NEW</span>', '', it)
    it = re.sub(r'<a class="btn-read"[^>]*>查看原文 →</a>', '', it)
    return it


def _esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# ============ 2026-09-11 新增：跨源同事件去重 ============
# 背景：同一条事件常被多家源同时报道（如「2026中国国际矿业大会将于9月10日开幕」
# 被 自然资源部/中国地质调查局/中国有色金属报 三家同题转发；SMM 中英文站
# news.smm.cn 与 news.metal.com 同题双语发布）。旧流程只按 URL 去重，
# 结果往期区长期残留 6 组同事件重复（08-24~09-10 累积）。
# 判定：标题归一化后完全相同，或相似度 ≥ SAME_EVENT_SIM。
SAME_EVENT_SIM = 0.62


def title_key(t):
    """标题归一化：去掉标点/空白，只留中英文与数字，用于同事件比较"""
    return re.sub(r'[^\w\u4e00-\u9fff]', '', t or '')


def item_title(it):
    m = re.search(r'class="news-title"[^>]*>([\s\S]*?)</a>', it)
    if not m:
        return ''
    return re.sub(r'<[^>]+>', '', m.group(1)).strip()


def same_event(t1, t2):
    """两条标题是否在讲同一件事。短标题（<8 字，多为无信息量标题）一律判否。"""
    import difflib
    a, b = title_key(t1), title_key(t2)
    if not a or not b:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) < 8:
        return False
    if len(a) >= 10 and (a in b or b in a):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= SAME_EVENT_SIM


def dedup_same_event(seq, key=None):
    """按「同事件」去重，保留先出现的（调用方应按质量/时间排好序）。
    seq 元素为 (cat, item_html)；key(item) 可自定义取标题的函数。"""
    _key = key or item_title
    out, kept = [], []
    for cat, it in seq:
        t = _key(it)
        if any(same_event(t, k) for k in kept):
            continue
        kept.append(t)
        out.append((cat, it))
    return out


def render_cat_groups(seq, mark_new=False):
    suffix = '条新增' if mark_new else '条'
    order, groups = [], {}
    for cat, it in seq:
        if cat not in groups:
            groups[cat] = []
            order.append(cat)
        groups[cat].append(it)
    out = []
    for cat in order:
        items = groups[cat]
        n = len(items)
        out.append('<div class="sub-cat" data-page-node-id="">%s<span class="sub-count" data-page-node-id="">%d%s</span></div>\n' % (cat, n, suffix))
        out.extend(items)
    return out


# ============ 依赖当日全局量的函数：改为显式传参，由生成器 partial 绑定 ============

def item_after_cutoff(it, report_dt, cutoff_dt):
    m = re.search(r'</span>\s*·\s*([0-9]{2})-([0-9]{2})', it)
    if not m:
        return True
    im, id_ = int(m.group(1)), int(m.group(2))
    iy = report_dt.year if im <= report_dt.month else report_dt.year - 1
    return (iy, im, id_) >= (cutoff_dt.year, cutoff_dt.month, cutoff_dt.day)


def _lib_item(e, cat_map):
    url = e.get('url', '')
    if not url:
        return None
    # 先按 (内容类, 地域) 查；旧数据没有 region，退回按分类名查；都没有则 bucket() 给兜底桶。
    # 不要在这里 return None —— 未知分类会让整批条目在生成时静默消失（踩过）。
    theme = e.get('category', '') or ''
    region = e.get('region', '') or ''
    cat = cat_map.get((theme, region)) or cat_map.get(theme) or bucket(theme, region)
    if not cat:
        return None
    title = _esc(e.get('title', ''))
    src = _esc(e.get('source', ''))
    od = e.get('orig_date', '') or (e.get('orig_date_full', '') or '')[5:]
    summary = _esc(e.get('summary', ''))
    embed = e.get('embed', 'ok') or 'ok'
    return (cat,
            '<div class="news-item" data-url="%s" data-embed="%s"><div class="news-head"><span class="dot"></span>'
            '<a class="news-title" href="%s" target="_blank">%s</a></div>'
            '<div class="news-meta"><span class="src">%s</span> · %s</div><div class="news-summary">%s</div></div>'
            % (url, embed, url, title, src, od, summary))


def _reclassify_ma(cat, it, cat_ma, ma_require):
    if cat in (CAT_KQ, cat_ma):
        return cat
    title = (re.search(r'class="news-title"[^>]*>([^<]+)</a>', it) or [None, ''])[1]
    sum_m = re.search(r'class="news-summary">([^<]+)</div>', it)
    summary = sum_m.group(1) if sum_m else ''
    text = title + ' ' + summary
    if any(k in text for k in ma_require):
        return cat_ma
    return cat
