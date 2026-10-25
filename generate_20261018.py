# -*- coding: utf-8 -*-
"""
生成 2026-10-18 矿业资讯速览 index.html（周日）
- 10-17 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-19）回补历史条目
- 换入 10-18 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-16 收盘 + LME 10-16 收盘（10-18 周日休市），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，tmp/add_rights_1018.py 注入），不进主页列表
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信 / 价格三视图
- 境外条目保留英文原题（data-orig-title + 摘要末尾「原题：…」）
"""
import re, datetime, json, glob, os
from source_whitelist import is_allowed
from generate_common import (
    ni, card, _replace_block, split_items, item_url, strip_new, _esc, render_cat_groups,
    UP, DOWN, FLAT, TAG_TODAY, TAG_ARCH, TAG_RIGHTS,
    CAT_KQ, CAT_ZK, CAT_HY, CAT_GJ, CAT_MA, CAT_ZC, CAT_SC, MA_REQUIRE, window,
    THEME_BUCKET, LEGACY_BUCKET, bucket,
    item_after_cutoff as _item_after_cutoff,
    _lib_item as _lib_item_raw,
    _reclassify_ma as _reclassify_ma_raw,
    dedup_same_event, item_title, same_event,
    unit_class, UNIT_SHFE_GROUP, UNIT_LME_GROUP,
)
from functools import partial


SITE_NAME = '矿业资讯速览'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()
_ORIG_SIZE = len(html)

REPORT = '2026-10-18'
GRAB = '2026-10-18'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年10月\d{2}日 星期.',
                         r'\g<1>2026年10月18日 星期日', html)
assert _n_badge == 1, 'date-badge 替换次数异常: %d' % _n_badge
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'今日新增（2026-\d{2}-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-\d{2}-\d{2} 更新',
              'id="priceStripNote">%s 更新' % REPORT, html)
html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
              'name="build-version" content="%s-%s"' % (REPORT.replace('-', ''), now.replace(':', '')), html)

# ============ 2. 价格卡刷新（全部现算，禁止手抄） ============
_ph = json.load(open('price_history_detail.json', encoding='utf-8'))['series']

SHFE_DEFS = [
    ('cum', '沪铜', 'SHFE', '元/吨', 0),
    ('alm', '沪铝', 'SHFE', '元/吨', 0),
    ('pbm', '沪铅', 'SHFE', '元/吨', 0),
    ('znm', '沪锌', 'SHFE', '元/吨', 0),
    ('snm', '沪锡', 'SHFE', '元/吨', 0),
    ('nim', '沪镍', 'SHFE', '元/吨', 0),
    ('au9999', '上海金', 'Au99.99', '元/克', 2),
    ('agtd', '白银', 'Ag(T+D)', '元/千克', 0),
    ('lcm', '碳酸锂', '主力连续', '元/吨', 0),
]
shfe_cards = []
for slug, name, tag, unit, nd in SHFE_DEFS:
    pts = _ph[slug]['points']
    prev, cur = pts[-2][1], pts[-1][1]
    chg = cur - prev
    pct = chg / prev * 100.0 if prev else 0.0
    val = format(cur, ',.%df' % nd)
    arrow = UP if chg >= 0 else DOWN
    sign = '+' if chg >= 0 else ''
    chgtxt = '%s %s%s (%s%.2f%%)' % (arrow, sign, format(chg, ',.%df' % nd), sign, pct)
    shfe_cards.append(card(slug, name, tag, val, unit, chgtxt, 'up' if chg >= 0 else 'down',
                           group_unit=UNIT_SHFE_GROUP))
shfe_html = ''.join(shfe_cards)
# 电解钴：无当日源，保留上日 SMM 值并标注
shfe_html += ('<div class="price-card "><div class="pc-name">电解钴 <span class="pc-tag">SMM %s</span></div>'
              '<div class="pc-value">304,940</div><div class="%s">元/吨</div>'
              '<div class="pc-chg">上日 304,940（SMM 未更新）</div></div>'
              % (DATA_ASOF, unit_class('元/吨', UNIT_SHFE_GROUP)))

_lme = json.load(open('lme_data.json', encoding='utf-8'))['metals']
_lme_map = {m['slug']: m for m in _lme}
LME_DEFS = [
    ('lcpt', 'LME 铜'), ('lalt', 'LME 铝'), ('lznt', 'LME 锌'),
    ('lldt', 'LME 铅'), ('lnkt', 'LME 镍'), ('ltnt', 'LME 锡'),
]
lme_list = []
for slug, name in LME_DEFS:
    m = _lme_map[slug]
    if m['price'] is None:
        lme_list.append((slug, name, 'LME', '--', '美元/吨', '暂无数据', 'flat'))
        continue
    arrow = UP if m['chg'] >= 0 else DOWN
    val = format(m['price'], ',.2f')
    sign = '+' if m['chg'] >= 0 else ''
    chg = '%s %s (%s%.2f%%)' % (arrow, sign + format(m['chg'], ',.2f'), sign, m['chg_pct'])
    lme_list.append((slug, name, 'LME', val, '美元/吨', chg, 'up' if m['chg'] >= 0 else 'down'))
lme_html = ''.join(card(*c, group_unit=UNIT_LME_GROUP) for c in lme_list)

html = _replace_block(html, '<div class="price-cards" id="priceCardsShfe">', shfe_html)
html = _replace_block(html, '<div class="price-cards price-cards-lme" id="priceCardsLme">', lme_html)

# ============ 3. 解析今日/往期两个区 ============
i_t = html.find(TAG_TODAY)
i_a = html.find(TAG_ARCH)
i_r = html.find(TAG_RIGHTS)
assert 0 <= i_t < i_a < i_r, 'markers not found'

m_today = html.find('<!-- ==================== 今日新增')
assert m_today != -1, '今日新增 marker missing'

today_raw = html[i_t:i_a]
arch_raw = html[i_a:i_r]

today_items = split_items(today_raw)
arch_items = split_items(arch_raw)

prev_today = [(cat, strip_new(it)) for cat, it in today_items if '<div class="news-item' in it and cat != CAT_KQ]
arch_keep = [(cat, strip_new(it)) for cat, it in arch_items
             if '<div class="news-item' in it and cat != CAT_KQ and item_after_cutoff(it)]

# ── URL → (内容类, 地域) 索引：让存量条目也能按新分类体系重新分桶 ──
_url_theme = {}
for _fn in sorted(glob.glob('data/news_????-??.json')):
    try:
        _lib = json.load(open(_fn, encoding='utf-8'))['news']
    except Exception:
        continue
    for _e in _lib:
        _u = _e.get('url', '')
        if _u and _e.get('region'):
            _url_theme[_u] = (_e.get('category', ''), _e.get('region', ''))


def _reclassify_by_url(cat, it):
    """用月库里的 LLM 分类结果覆盖旧桶名。查不到则原样返回。"""
    th_rg = _url_theme.get(item_url(it))
    return bucket(th_rg[0], th_rg[1]) if th_rg else cat


merge_seq = []
seen_url = set()
for cat, it in prev_today + arch_keep:
    url = item_url(it)
    if url in seen_url:
        continue
    seen_url.add(url)
    merge_seq.append((_reclassify_by_url(cat, it), it))

merge_seq = dedup_same_event(merge_seq)

# ============ 3.5 从累计库回补 30 天窗口 ============
CAT_MAP = dict(LEGACY_BUCKET)
CAT_MAP.update(THEME_BUCKET)
LIB_SKIP = {'矿权交易', '并购与投资'}
_lib_item = partial(_lib_item_raw, cat_map=CAT_MAP)

_lib_pool = []
for _fn in sorted(glob.glob('data/news_????-??.json')):
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
    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474572',
                '中国有色金属报', '10-13',
                '江西于山矿集区找矿项目获江西省科技进步二等奖',
                '中国有色金属报报道，由江西省地质局第七地质大队牵头，联合中国地质科学院矿产资源研究所、南京大学等单位完成的「南岭于山矿集区钨钼和银金铅锌成矿关键理论创新与找矿突破」项目获江西省科学技术进步奖二等奖。项目针对赣南老矿山资源枯竭、深部找矿久攻未克的难题，首次在矿集区内识别发现燕山晚期钨钼矿成矿花岗岩，构建两类矿床「三位一体」找矿预测模型，提交多处大中型矿床并圈定一批找矿靶区。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474633',
                '中国有色金属报', '10-15',
                '江西地调院新疆分院在帕米尔高原持续推进地质找矿',
                '中国有色金属报报道，江西省地调院基础所新疆分院地质队员在帕米尔高原高海拔区持续开展地质找矿，阿克陶巴牙斯坦铬铁矿调查评价项目已完成野外地质填图。该院自 23 年前首次进入西昆仑—西南天山一带，从一张图、一双脚起步，逐步在区内推进铬铁矿等战略性矿产调查评价。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/en/newscontent/104162853-china-proposes-tighter-solar-technology-export-controls-what-next-for-the-ex-china-region-smm-analysis',
                'SMM 国际站', '10-16',
                '两部门就技术出口目录修订征求意见，光伏 12 项技术拟设出口前登记',
                '商务部、科技部 10 月 16 日就《中国禁止出口限制出口技术目录》修订公开征求意见，并对相关技术设置出口前临时登记要求；光伏领域涉及多晶硅、硅片、电池制造等 12 项技术，含采用上述技术的关键核心装备。SMM 分析认为，需关注该调整对海外光伏产能布局及用铝需求的传导。',
                orig_title='China Proposes Tighter Solar Technology Export Controls: What Next for the Ex-China Region?')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104162865-30000-mt-alumina-traded-at-426mt-fob-brazil-for-november-2026-shipment',
                'SMM 国际站', '10-16',
                '海外氧化铝现货：3 万吨巴西货 426 美元/吨成交，11 月装运',
                'SMM 报道，2026 年 10 月 16 日 3 万吨氧化铝以 426 美元/吨 FOB 巴西成交，船期为 11 月。',
                orig_title='30,000 mt Alumina Traded at $426/mt FOB Brazil for November 2026 Shipment')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104162863-national-magnesium-inventory-down-352-mom-prices-hit-year-low-prompting-smelter-closures',
                'SMM 国际站', '10-16',
                '全国镁锭库存环比降 3.52%，价格创年内新低、两家原镁厂停产',
                'SMM 周度快报显示，10 月 9 日至 15 日全国样本镁厂周产量 22176 吨，周开工率 72.76%、环比下降 0.88%；全国镁锭库存环比下降 3.52%，价格创年内新低。国庆期间两家原镁冶炼企业停产检修、一家减产，但被其他厂家增产抵消，整体减产有限。',
                orig_title='National Magnesium Inventory Down 3.52% MoM, Prices Hit Year Low Prompting Smelter Closures')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104162326-rare-earth-prices-move-sideways-inquiry-activity-shows-no-improvement-smm-rare-earth-daily-review',
                'SMM 国际站', '10-16',
                '稀土价格横盘，询单活跃度未见改善',
                'SMM 稀土日评显示，主流稀土产品价格横盘运行，市场询单活跃度未见改善。',
                orig_title='Rare earth prices move sideways, inquiry activity shows no improvement')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104161994-tungsten-sharp-price-drop-amid-bearish-factors-awaiting-destocking-demand-recovery',
                'SMM 国际站', '10-16',
                '钨价大幅回落，市场等待去库完成与需求修复',
                'SMM 报道，钨价在利空因素集中释放下大幅下跌，市场等待下游完成去库、需求端回暖。',
                orig_title='Tungsten: Sharp Price Drop Amid Bearish Factors, Awaiting Destocking & Demand Recovery')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/104157303',
                '上海有色网', '10-17',
                '中钨高新预计前三季度净利润同比增 219%~241%',
                '上海有色网报道，中钨高新发布业绩预告，预计 2026 年前三季度归属于上市公司股东的净利润同比增长 219%~241%，主要因钨精矿均价同比上涨，带动产品盈利明显改善。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-16/1225607406.PDF',
                '巨潮资讯网', '10-16',
                '中铝国际前三季度新签合同 217.88 亿元，海外同比增 14.76%',
                '巨潮资讯网披露，中铝国际 2026 年前三季度新签合同总额 217.88 亿元、同比增加 1.53%；其中新签工业合同 214.55 亿元、占总额 98.47%，设计咨询 26.39 亿元、同比增 44.87%，装备制造 16.96 亿元、同比增 21.95%，海外合同 57.61 亿元、同比增 14.76%。截至 9 月 30 日存量合同 514.25 亿元。',
                embed='pdf')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474627',
                '中国有色金属报', '10-15',
                '西北有色地矿集团赴津巴布韦考察地质矿业市场',
                '中国有色金属报报道，西北有色地矿集团代表团赴津巴布韦开展地质矿业市场考察，实地走访 MDL 金矿、One Step 金矿及环球铂业津巴布韦铂金矿等项目，围绕矿权办理、找矿增储、开发利用、矿业政策与劳动用工深入交流。代表团认为该国金等战略性矿产需求旺盛、成矿地质条件优越、找矿空间广阔，但基础地质调查和矿产勘查投入不足，拟将津巴布韦打造成集团海外地质矿业市场的重要支点。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474630',
                '中国有色金属报', '10-15',
                '国际钨业协会柏林会议：中国目标 2030 年钨回收率提至 45%',
                '中国有色金属报报道，9 月在柏林举行的国际钨业协会会议上，中方代表披露中国已设定目标，到 2030 年将钨回收率提高至 45%。按报废回收率口径，当前全球钨报废回收率约三成，欧美接近五成、日本约三成、中国约二成；提升回收率意味着同等消费规模下对原生矿的依赖度下降，尾矿与废渣中的钨价值将被重新激活。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474558',
                '中国有色金属报', '10-13',
                '长沙有色院三项技术入选湖南省绿色低碳先进适用新技术目录',
                '中国有色金属报报道，湖南省工业和信息化领域鼓励发展的绿色低碳先进适用新技术、新装备和新产品目录（2026 年版）公布，共 45 项入选，长沙有色冶金设计研究院三项冶炼减污降碳技术位列其中。')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/greenland-to-introduce-ban-on-seabed-mining',
                'MINING.COM', '10-17',
                '格陵兰议会一致通过海底采矿禁令，效力延续至 2029 年底',
                'MINING.COM 报道，格陵兰议会一致通过决议，禁止海底矿产开采，相关备忘录有效期至 2029 年底、可按两年一期延长，立法预计 2027 年上半年通过。该决议出台于美国总统特朗普宣布将在格陵兰启动大规模油气与矿产勘探的次日；格陵兰 Tanbreez 项目拥有 2820 万吨 TREO 资源量。',
                orig_title='Greenland to introduce ban on seabed mining')),
]

# ============ 并购关键词重归类 ============

CAT_MA2 = CAT_MA
_reclassify_ma = partial(_reclassify_ma_raw, cat_ma=CAT_MA2, ma_require=MA_REQUIRE)

unique_new = []
new_seen_url = set()
for cat, it in new_items:
    url = item_url(it)
    if url in new_seen_url:
        continue
    new_seen_url.add(url)
    unique_new.append((_reclassify_ma(_reclassify_by_url(cat, it), it), it))
new_items = unique_new

merge_seq = [x for x in merge_seq if item_url(x[1]) not in new_seen_url]
merge_seq = dedup_same_event(merge_seq)

# ============ 3.6 数字落地校验（复用 verify_numbers） ============
try:
    from verify_numbers import verify_new_items
    _num_issues = verify_new_items(new_items, REPORT,
                                   strict=os.environ.get('VERIFY_NUMBERS_STRICT') == '1')
    if _num_issues:
        print('[num-warn] 共 %d 条摘要存在数字未在源文找到，请人工核对' % len(_num_issues))
except Exception as _e:
    print('[verify_numbers] 跳过: %s' % _e)
_new_titles = [item_title(it) for _c, it in new_items]
if _new_titles:
    merge_seq = [x for x in merge_seq
                 if not any(same_event(item_title(x[1]), _t) for _t in _new_titles)]
for _i in range(len(new_items)):
    for _j in range(_i + 1, len(new_items)):
        if same_event(item_title(new_items[_i][1]), item_title(new_items[_j][1])):
            print('[warn] 今日新增内部疑似同事件重复: %s <-> %s'
                  % (item_title(new_items[_i][1])[:40], item_title(new_items[_j][1])[:40]))

arch_groups = render_cat_groups(merge_seq, mark_new=False)
today_groups = render_cat_groups(new_items, mark_new=True)

# ============ 5. 拼装新区 ============
n_today = len(new_items)
arch_n = len(merge_seq)
all_n = n_today + arch_n

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

html = html[:m_today] + new_today_block + new_arch_block + html[i_r:]
html = html.replace('<!-- ==================== 今日新增 ==================== -->', '', 1)

# ============ 6. 更新计数与 AI 提示 ============
html = re.sub(r'id="tocAllCount"[^>]*>\d+<', 'id="tocAllCount">%d<' % all_n, html)
html = re.sub(r'id="tocTodayCount"[^>]*>\d+<', 'id="tocTodayCount">%d<' % n_today, html)
html = re.sub(r'id="tocArchiveCount"[^>]*>\d+<', 'id="tocArchiveCount">%d<' % arch_n, html)
html = re.sub(r'今日 \d+ 条新闻的智能解读', '今日 %d 条新闻的智能解读' % n_today, html)

# ============ 7. div 收支自检 ============
_body = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', '', html)
_open = len(re.findall(r'<div\b', _body))
_close = len(re.findall(r'</div>', _body))
assert _open == _close, 'div 收支不平衡: open=%d close=%d' % (_open, _close)

_buf = html.encode('utf-8')
assert len(_buf) > _ORIG_SIZE * 0.9, 'refuse to write suspiciously small index.html: %d bytes (orig %d)' % (len(_buf), _ORIG_SIZE)
with open(SRC + '.tmp', 'w', encoding='utf-8') as f:
    f.write(html)
os.replace(SRC + '.tmp', SRC)

print('OK index.html -> today=%d archive=%d all=%d size=%d div=%d/%d'
      % (n_today, arch_n, all_n, len(html), _open, _close))
