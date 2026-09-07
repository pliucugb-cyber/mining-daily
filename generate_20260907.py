# -*- coding: utf-8 -*-
"""
生成 2026-09-07 矿业新闻日报 index.html（原地更新）
- 09-06 的"今日新增"条目滚入"往期内容"（去 NEW 标记、按同类目合并）
- 按 30 天窗口（滚动保留最近30天）剔除往期条目（保留 >= 今日-29 天），月度全量在 data/news_*.json
- 换入 09-07 抓取的最新条目（is-new + NEW），更新各计数与 AI 区条数
- 周一交易时段进行中，国内上期所最新收盘仍为 09-04（上周五），价格卡沿用并标注；LME 09-07 电子盘由前端 JS 填充
- 矿权条目按规范仅入 rightsSection 数据层（data/news_2026-09.json），不进主页列表
- 保留：data-slug / digestStrip / qaFab / pchartMask / themeToggle / rightsSection
修复：sub-cat/sp-cat 现在带 data-page-node-id 属性，正则需容错 [^>]*
"""
import re, datetime, json, glob
from source_whitelist import is_allowed


def ni(url, src, date, title, summary, embed='ok'):
    """构造今日新增条目，并强制校验 URL 在白名单内。"""
    if not is_allowed(url):
        raise ValueError(f"URL 不在允许信源白名单内: {url}")
    return ('<div class="news-item is-new" data-url="%s" data-embed="%s"><div class="news-head"><span class="dot"></span>'
            '<span class="badge-new">NEW</span><a class="news-title" href="%s" target="_blank">%s</a></div>'
            '<div class="news-meta"><span class="src">%s</span> · %s</div><div class="news-summary">%s</div>'
            '</div>'
            % (url, embed, url, title, src, date, summary))

SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()

REPORT = '2026-09-07'
GRAB = '2026-09-07'
ARCHIVE_DAYS = 30         # 往期展示窗口（天）
REPORT_DT = datetime.date.fromisoformat(REPORT)
CUTOFF_DT = REPORT_DT - datetime.timedelta(days=ARCHIVE_DAYS - 1)   # 往期最早日期（含）= 08-09
DATA_ASOF = '09-04'       # 周一交易时段进行中，国内最新收盘仍为 09-04（上周五）

# ============ 1. 标题 / 日期 / 更新时间 ============
html = re.sub(r'<title>\d{4}-\d{2}-\d{2}</title>', '<title>%s</title>' % REPORT, html)
html = html.replace('2026年09月06日 星期日', '2026年09月07日 星期一')
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'更新时间：2026-09-\d{2} \d{2}:\d{2}', '更新时间：%s %s' % (REPORT, now), html)
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-09-\d{2} 更新', 'id="priceStripNote">%s 更新' % REPORT, html)
html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
              'name="build-version" content="%s-%s"' % (REPORT.replace('-', ''), now.replace(':', '')), html)

# ============ 2. 价格卡（不重建，沿用 09-04 收盘 + LME 前端填充；仅刷新提示日期） ============
# 国内 10 卡与 LME 6 卡保持原样（值与 09-06 一致，因周一尚无新收盘）

# ============ 3. 解析今日/往期两个区（容错 data-page-node-id） ============
TAG_TODAY = '<div class="section" id="todaySection"'
TAG_ARCH  = '<div class="section" id="archiveSection"'
TAG_RIGHTS= '<div class="section" id="rightsSection"'
i_t = html.find(TAG_TODAY)
i_a = html.find(TAG_ARCH)
i_r = html.find(TAG_RIGHTS)
assert 0 <= i_t < i_a < i_r, 'markers not found'

# 用 marker 注释（而非 div 起点）作边界，避免把旧 marker 带入导致重复
m_today = html.find('<!-- ==================== 今日新增')
assert m_today != -1, '今日新增 marker missing'

# 保留找矿专项容器（位于今日区与往期区之间，由前端 initSpecial 运行时填充，重建时不能丢弃）
# 注意：专项容器之后紧跟着「往期内容」marker 注释，须截断在 marker 之前，否则会与 new_arch_block 的 marker 重复
sp_start = html.find('<div class="section" id="specialSection"')
arch_marker_pos = html.find('<!-- ==================== 往期内容')
if sp_start != -1 and arch_marker_pos != -1 and arch_marker_pos > sp_start:
    special_block = html[sp_start:arch_marker_pos]
elif sp_start != -1:
    special_block = html[sp_start:i_a]
else:
    special_block = ''

today_raw = html[i_t:i_a]
arch_raw  = html[i_a:i_r]

def split_items(block):
    """按 (cat, subcount) 与 news-item 顺序切分，返回 items[(cat, htmlitem)] 序列"""
    out = []
    cat = None
    for mm in re.finditer(r'<div class="sub-cat"[^>]*>([^<]*)<span class="sub-count"[^>]*>([^<]*)</span></div>'
                          r'|<div class="sp-cat"[^>]*>([^<]*)</div>'
                          r'|<div class="news-item[^>]*>.*?</div>\s*</div>',
                          block, re.S):
        if mm.group(1) is not None:
            cat = mm.group(1).strip()
        elif mm.group(3) is not None:
            cat = mm.group(3).strip()
        else:
            if cat:
                out.append((cat, mm.group(0)))
    return out

today_items = split_items(today_raw)
arch_items  = split_items(arch_raw)

def item_after_cutoff(it):
    """条目是否在 7 日往期窗口内（含 CUTOFF_DT）。无日期的条目保留。"""
    m = re.search(r'</span>\s*·\s*([0-9]{2})-([0-9]{2})', it)
    if not m:
        return True
    im, id_ = int(m.group(1)), int(m.group(2))
    iy = REPORT_DT.year if im <= REPORT_DT.month else REPORT_DT.year - 1
    return (iy, im, id_) >= (CUTOFF_DT.year, CUTOFF_DT.month, CUTOFF_DT.day)

def item_url(it):
    m = re.search(r'data-url="([^"]+)"', it)
    return m.group(1) if m else it

def strip_new(it):
    it = it.replace(' is-new', '')
    it = re.sub(r'<span class="badge-new"[^>]*>NEW</span>', '', it)   # 含 data-page-node-id 属性形式
    it = re.sub(r'<a class="btn-read"[^>]*>查看原文 →</a>', '', it)   # 合规：去除 btn-read
    return it

CAT_KQ = '💼 矿权交易'

prev_today = [(cat, strip_new(it)) for cat, it in today_items if '<div class="news-item' in it and cat != CAT_KQ]
arch_keep = [(cat, strip_new(it)) for cat, it in arch_items
            if '<div class="news-item' in it and cat != CAT_KQ and item_after_cutoff(it)]

merge_seq = []
seen_url = set()
for cat, it in prev_today + arch_keep:
    url = item_url(it)
    if url in seen_url:
        continue
    seen_url.add(url)
    merge_seq.append((cat, it))

# ============ 4. 今日新增条目（09-07 抓取，均逐页核实标题/日期/正文） ============
# 信源白名单已固化在 source_whitelist.py；构造条目 ni() 会自动校验 URL，
# 非白名单 URL 会抛 ValueError，避免把未知来源写入日报。

CAT_ZK = '🔍 找矿成果与勘查技术'
CAT_HY = '🏭 行业动态'
CAT_GJ = '🌐 国际矿业动态'

# ============ 3.5 从累计库回补 30 天窗口（防止历史条目因窗口滚动丢失） ============
CAT_MAP = {
    '行业动态': CAT_HY,
    '国际矿业动态': CAT_GJ,
    '找矿成果与勘查技术': CAT_ZK,
    '培训与学术': CAT_HY,
    '政策法规': CAT_HY,
}
LIB_SKIP = {'矿权交易', '并购与投资'}   # 矿权→rightsSection（前端渲染）；并购→inject_ma 独立子分类

def _esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def _lib_item(e):
    url = e.get('url', '')
    if not url:
        return None
    cat = CAT_MAP.get(e.get('category', ''))
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

_lib_pool = []
for _fn in sorted(glob.glob('data/news_2026-*.json')):
    try:
        _lib = json.load(open(_fn, encoding='utf-8'))['news']
    except Exception:
        continue
    for _e in _lib:
        if _e.get('category') in LIB_SKIP:
            continue
        _odf = _e.get('orig_date_full', '') or ''
        if _odf < CUTOFF_DT.isoformat():
            continue
        _url = _e.get('url', '')
        if not _url or _url in seen_url:
            continue
        _it = _lib_item(_e)
        if not _it:
            continue
        _lib_pool.append((_odf, _url, _it))
_lib_pool.sort(key=lambda t: t[0], reverse=True)
for _odf, _url, _it in _lib_pool:
    seen_url.add(_url)
    merge_seq.append(_it)
print('library backfill added:', len(_lib_pool))

new_items = [
    (CAT_ZK, ni('http://www.xgsnrc.cgs.gov.cn/gzdt/aqsc/202609/t20260905_867989.html', '中国地质调查局西宁中心', '09-05',
        '以案为鉴筑牢安全防线 精细钻探夯实开发根基——柳园铭扬铜镍矿第三孔支撑性勘探顺利开钻',
        '柳园铭扬铜镍矿5号机台MZK002号勘探孔正式开孔，为本轮专项勘探第三孔，在前两孔基础上加密勘探剖面、完善地质数据，为资源储量核实与灾害隐患排查提供依据；施工结合西藏吉隆泥石流教训，全程强化安全管控与地质灾害防控。')),
    # 以下条目因来源不在白名单内已删除（2026-09-07 用户要求收紧信源）：
    # - 华夏时报 news.qq.com
    # - 中国网 chinagate.cn
    # - 上海证券报 cnstock.com
    # - 和讯 hexun.com
    # - 华安期货 haqh.com
    # - mining.com
    # - Stockhead/news.com.au
    # - miningsee.eu
    # 如需补充国际/行业动态，请从白名单域名（mnr.gov.cn / cgs.gov.cn / chinania.org.cn /
    # cnmn.com.cn / geoglobal.mnr.gov.cn / cngold.org.cn）中选取真实链接替换。
]

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

unique_new = []
new_seen_url = set()
for cat, it in new_items:
    url = item_url(it)
    if url in new_seen_url:
        continue
    new_seen_url.add(url)
    unique_new.append((cat, it))
new_items = unique_new

merge_seq = [x for x in merge_seq if item_url(x[1]) not in new_seen_url]

arch_groups = render_cat_groups(merge_seq, mark_new=False)
today_groups = render_cat_groups(new_items, mark_new=True)

# ============ 5. 拼装新区 ============
n_today = len(new_items)
arch_n  = len(merge_seq)
all_n   = n_today + arch_n

new_today_block = ('<!-- ==================== 今日新增（%s 抓取） ==================== -->\n' % GRAB +
    '<div class="section" id="todaySection">\n'
    '<div class="section-title today"><span class="icon">🔥</span> 今日新增（%s 抓取）<span class="news-count" id="todayCount">%d条</span></div>\n'
    % (GRAB, n_today) + ''.join(today_groups) + '</div>\n')

new_arch_block = ('<!-- ==================== 往期内容 ==================== -->\n'
    '<div class="section" id="archiveSection">\n'
    '<div class="section-title"><span class="icon">📰</span> 往期内容（滚动保留最近30天）'
    '<span class="news-count" id="archiveCount">%d条</span></div>\n'
    '<div class="fold-toggle" id="foldToggle" style="display:none" onclick="toggleOldFold()">▸ 展开更早内容</div>\n'
    % arch_n + ''.join(arch_groups) + '</div>\n')

# 以 rightsSection 为界重建今日/往期区，保留找矿专项容器、矿权专区容器与「详细安装指引」注释 marker
html = html[:m_today] + new_today_block + special_block + new_arch_block + html[i_r:]
# 移除旧的 canon 今日新增注释标记，避免最终出现两个「今日新增」marker 触发 preflight 失败
html = html.replace('<!-- ==================== 今日新增 ==================== -->', '', 1)

# ============ 6. 更新计数与 AI 提示 ============
html = re.sub(r'id="tocAllCount"[^>]*>\d+<', 'id="tocAllCount">%d<' % all_n, html)
html = re.sub(r'id="tocTodayCount"[^>]*>\d+<', 'id="tocTodayCount">%d<' % n_today, html)
html = re.sub(r'id="tocArchiveCount"[^>]*>\d+<', 'id="tocArchiveCount">%d<' % arch_n, html)
html = re.sub(r'今日 \d+ 条新闻的智能解读', '今日 %d 条新闻的智能解读' % n_today, html)

with open(SRC, 'w', encoding='utf-8') as f:
    f.write(html)

print('OK index.html -> today=%d archive=%d all=%d size=%d' % (n_today, arch_n, all_n, len(html)))
