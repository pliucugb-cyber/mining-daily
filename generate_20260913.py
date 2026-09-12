# -*- coding: utf-8 -*-
"""
生成 2026-09-13 矿业新闻日报 index.html
- 09-12 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-15）回补历史条目
- 换入 09-13 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所 09-11 收盘（周日休市）+ LME 09-11 收盘，全部由 price_history_detail.json /
  lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层，不进主页列表
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信
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
)
from functools import partial


SITE_NAME = '矿业新闻日报'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()
_ORIG_SIZE = len(html)

REPORT = '2026-09-13'
GRAB = '2026-09-13'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
# 站点名固定「矿业新闻日报」，标题统一写成「矿业新闻日报 · YYYY-MM-DD」。
# 用宽松匹配吃掉落点前的任意旧标题，可覆盖三种历史写法：
#   纯日期（2026-09-07~09-12，站名丢失）／「站名 日期」（09-04~09-06）／「站名 · 日期」。
# 2026-09-12 修复：此前 09-07 起写成纯日期，浏览器标签页只剩一个光秃秃的日期，看不出是什么站。
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月13日 星期日', html)
assert _n_badge == 1, 'date-badge 替换次数异常: %d' % _n_badge
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-09-\d{2} 更新',
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
    shfe_cards.append(card(slug, name, tag, val, unit, chgtxt, 'up' if chg >= 0 else 'down'))
shfe_html = ''.join(shfe_cards)
# 电解钴：无当日源，保留上日 SMM 值并标注
shfe_html += ('<div class="price-card "><div class="pc-name">电解钴 <span class="pc-tag">SMM %s</span></div>'
              '<div class="pc-value">304,940</div><div class="pc-unit">元/吨</div>'
              '<div class="pc-chg">上日 304,940（SMM 未更新）</div></div>' % DATA_ASOF)

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
lme_html = ''.join(card(*c) for c in lme_list)

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
for _fn in sorted(glob.glob('data/news_2026-*.json')):
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

# ============ 4. 今日新增条目（09-13 抓取，均逐源核实） ============
new_items = [
    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260912_2938231.html',
                '自然资源部', '09-12',
                '中沙地学合作首批 24 幅 1:10 万精细地质填图成果发布',
                '​9 月 11 日，在 2026 中国国际矿业大会中亚西亚矿业投资推介会上，沙特地质调查局发布由中国地质调查局牵头实施的沙特阿拉伯地盾首批 24 幅 1∶10 万精细地质填图成果，总面积 7.08 万平方千米，覆盖阿拉伯地盾区重要金、铜、锌、铬及稀有金属成矿带，每幅配套专业地质图、成果报告书与空间数据库。阿拉伯地盾区 1∶10 万精细地质填图项目覆盖约 60 万平方千米，是本世纪全球规模最大的地质填图技术服务项目；本次成果填补该区域精细地质资料空白，填图过程中新识别出一批矿化异常与找矿线索，并圈定系列成矿远景区，数据已接入沙特国家地学数据库门户开放共享。项目采用数字化、智能化填图技术路线，依托自主研发的 GoField 野外采集软件融合遥感、物探、化探多源地学数据，成果通过国际第三方监理全过程验收。')),

    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260912_2938230.html',
                '自然资源部', '09-12',
                '自然资源部领导在天津会见多国矿业部长 中苏签署地学合作备忘录',
                '​9 月 10 日至 11 日 2026 中国国际矿业大会期间，自然资源部党组书记刘国洪，自然资源部副部长、国家海洋局局长孙书贤，自然资源部副部长、中国地质调查局局长许大纯分别与多国矿业部长开展双边会见。刘国洪会见哈萨克斯坦工业和建设部部长叶尔赛因·纳加斯帕耶夫、刚果（金）矿业部长路易·卡班巴·瓦图姆；孙书贤会见加纳、蒙古、加蓬、尼日尔矿业部长；许大纯会见俄罗斯自然资源与生态部副部长德米特里·捷坚金、苏丹矿业部部长努尔达伊姆·塔哈、坦桑尼亚矿业部部长安东尼·彼得·马文德。各方围绕基础地质调查、地质编图、地球化学等领域务实合作深入交换意见，并就深化地质矿产调查合作、加强绿色智能矿业技术研发应用、共享绿色矿山建设标准与实践经验、支持企业开展务实投资合作等达成多项共识。期间中国地质调查局与苏丹地质调查部门签署了地学合作谅解备忘录。')),
    (CAT_ZC, ni('https://www.mining.com/us-department-of-energy-grants-73m-to-advance-domestic-mining-technology',
                'MINING.COM', '09-11',
                '美国能源部拨款 7300 万美元建四处采矿技术测试场',
                '美国能源部关键矿产与能源创新办公室（CMEI）本周通过「未来矿山」（Mine of the Future）计划选定 4 个项目、拨款 7300 万美元，用于建设国内创新采矿技术测试场，加速采矿技术商业化并强化关键矿产供应链。入选项目包括：总部位于林奇堡的 Innovative Wireless Technologies（项目地点在西弗吉尼亚州 Julian、Blacksburg 与科罗拉多州 Idaho Springs，建国家级测试场验证数字化、连接与自动化方案）、亚利桑那大学（萨瓦里塔地下测试场）、密苏里大学校董会（罗拉，多功能采矿技术验证场）、南方卫理公会大学（得州 Navasota，在先进钻探与传感试验设施内建全球首个「合成矿山」）。能源部长克里斯·赖特称，把前沿技术从实验室推向现场有助于释放美国矿产资源。',
                orig_title='US Department of Energy grants $73M to advance domestic mining technology')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104111533',
                '上海有色网', '09-12',
                'LME 期铜持稳但周线 6 月以来首次下跌 沪铜库存降至 2024 年 1 月来最低',
                '9 月 11 日（周五）伦敦金属交易所三个月期铜收报 14,240.0 美元/吨、涨 0.05%，但周线下跌 1.2%，终结连续 10 周上涨；此前周四铜价触及 14,875 美元/吨纪录高位后单日回落 3.6%，报道称白宫尚未决定是否对铜加征关税。其他基本金属普遍下跌：三个月期铝 3,253.0 美元/吨（-1.23%）、期锌 3,881.0 美元/吨（-0.28%）、期铅 1,892.0 美元/吨（-0.47%）、期镍 16,469.0 美元/吨（-1.18%，两个月低位）、期锡 53,364.0 美元/吨（-1.8%，7 月 28 日以来最低）。LME 可用铜库存 117,600 吨不变，但上期所铜库存连降两周、骤降 13% 至 54,780 吨，为 2024 年 1 月以来最低；Marex 策略师认为当前多头仓位过重、铜库存仍偏紧，短期重点是风险管理。')),
    (CAT_SC, ni('https://news.smm.cn/news/104111534',
                '上海有色网', '09-12',
                '花旗重申未来三个月铜价目标 15,000 美元/吨',
                '9 月 11 日（周五），花旗重申未来三个月铜价目标为 15,000 美元/吨。该行认为，近期因关税疑虑引发的任何进一步避险情绪，在更广泛的铜价看涨驱动因素和主题背景下仅属于暂时性回调，这为增加铜价风险敞口提供了机会。（来源：文华财经）')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104111484-copper-wire-and-cable-operating-rate-falls-to-6371-amid-high-prices-and-weak-demand',
                'SMM 国际站', '09-11',
                '铜价高位抑制订单 铜线缆企业开工率降至 63.71%',
                'SMM 调研显示，9 月 4 日至 10 日当周国内铜线缆企业开工率 63.71%，环比下降 2.93 个百分点、同比下降 3.91 个百分点。周内铜价整体高位震荡，持续压制下游订单释放；高铜价削弱线缆企业原料备库意愿，原料库存天数环比下降 2.93%；终端需求疲弱、提货意愿不足，成品库存天数环比上升 2.63%。',
                orig_title='Copper Wire and Cable Operating Rate Falls to 63.71% Amid High Prices and Weak Demand')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104111556-yingkou-jianfa-shenghai-phase-i-300000-mt-copper-cathode-project-smelting-furnace-starts-production-pyrometallurgy-system-enters-furnace-drying-stage',
                'SMM 国际站', '09-12',
                '营口建发盛海一期 30 万吨阴极铜项目熔炼炉点火 进入烘炉阶段',
                '9 月 12 日 9 时 58 分，营口建发盛海有色金属化工有限公司多金属综合回收项目火法系统核心熔炼炉点火成功，正式进入烘炉阶段。该项目为多金属复杂金银矿综合回收技术升级搬迁扩建工程，以铜精矿为主要原料，规划总产能 60 万吨/年阴极铜、分两期各 30 万吨；一期设计年产阴极铜 30 万吨、硫酸 118 万吨，配套熔炼、吹炼、阳极精炼、电解、选渣与贵金属回收系统。项目尚未正式投料生产，烘炉与全系统热态联动试车完成后将进一步推进一期产能投运，有望提升华北地区铜冶炼产能、进一步拉动国内铜精矿原料需求。',
                orig_title='Yingkou Jianfa Shenghai Phase I 300,000 mt Copper Cathode Project Smelting Furnace Starts Production, Pyrometallurgy System Enters Furnace Drying Stage')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104111486-zambias-refined-copper-exports-rise-74-in-h1-2026-as-domestic-copper-production-grows-045',
                'SMM 国际站', '09-11',
                '赞比亚上半年精炼铜出口增 7.4% 国内产量仅增 0.45%',
                '赞比亚统计局数据显示，2026 年上半年赞比亚精炼铜出口 44.61 万吨、同比增长 7.4%（上年同期 41.52 万吨），增量集中在 6 月；同期矿业与矿产发展部统计的全国铜产量 44.72 万吨、仅同比增长 0.45%（上年同期 44.52 万吨）。SMM 分析认为，出口与产量增长的背离源于发运时点、第三方原料及矿山表现不均：Kansanshi、Sentinel、Lumwana 的增产被其他矿山减产部分抵消，上半年小型铜矿产量同比下降 35.2%。赞比亚 2031 年铜产量目标为 300 万吨，当前产量增长相对该目标仍显温和。',
                orig_title="Zambia's Refined Copper Exports Rise 7.4% in H1 2026 as Domestic Copper Production Grows 0.45%")),
    (CAT_GJ, ni('https://www.mining.com/site-visit-cyclic-materials-opens-commercial-scale-rare-earth-recycling-plant-in-arizona',
                'MINING.COM', '09-11',
                'Cyclic Materials 在亚利桑那投运商业规模稀土磁材回收厂',
                'Cyclic Materials 于 9 月 9 日在美国亚利桑那州梅萨为其首个商业规模稀土磁材回收工厂举行开业仪式，厂房面积 14.4 万平方英尺，年处理含磁体报废产品能力最高 2.5 万吨，公司称其为同类设施中规模最大者。该厂是 Cyclic 专有 MagCycle 技术的首次商业化部署，通过机械方式从报废产品中分离永磁体，构成其一体化稀土回收平台的前端；工厂生产 Mag-Xtract 稀土磁材原料，同时回收铜、铝、钢等材料，目前已进入商业运营。该设施为美国企业提供了本地的含磁体废料处理去向，此前这类物料多作为废物出口。',
                orig_title='Site visit: Cyclic Materials opens commercial-scale rare earth recycling plant in Arizona')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104111529-smm-analysis-stronger-profits-yet-limited-supply-elasticity-h1-2026-americas-moly-mine-review',
                'SMM 国际站', '09-12',
                'SMM：美洲钼矿上半年产量降 3.2% 供给弹性仍受限',
                'SMM 基于海外主要铜钼矿与原生钼矿企业半年报估算，2026 年上半年其跟踪样本矿山钼产量约 6.59 万吨，较上年同期的约 6.8 万吨减少约 2,100 吨、同比降幅约 3.2%。分国别看，智利、秘鲁产量同比下降，美国增长，SMM 墨西哥样本矿山亦下降；矿山层面产量变化高度集中于少数大型项目。SMM 认为，尽管主要矿企利润改善，美洲钼供给弹性依然受限，下半年仅个别大型矿山存在恢复可能，增量将进一步集中。',
                orig_title='[SMM Analysis] Stronger Profits, Yet Limited Supply Elasticity: H1 2026 Americas Moly Mine Review')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('https://www.mining.com/mining-leads-canadian-prime-ministers-c1t-investor-pitchbook',
                'MINING.COM', '09-11',
                '加拿大总理万亿加元引资清单中矿业占 63 项居首',
                '加拿大总理马克·卡尼将于下周在多伦多举行的加拿大投资峰会（9 月 14—15 日）上向全球投资者推介一份 66 页投资手册，矿业项目占其中 167 项机会的 63 项。LithiumBank Resources（TSXV: LBNK）上周五确认其位于埃德蒙顿西北 270 公里的 Boardwalk 锂卤水项目入选。卡尼的目标是在五年内为加拿大引入 1 万亿加元（约 7,230 亿美元）投资；此次峰会旨在检验渥太华能否把投资者对加拿大矿业权益的强劲需求转化为新矿山与加工厂的长期融资。',
                orig_title="Mining leads Canadian Prime Minister's C$1T investor pitchbook")),
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

# ============ 7. div 收支自检（2026-09-11 破损教训） ============
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
