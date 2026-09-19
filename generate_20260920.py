# -*- coding: utf-8 -*-
"""
生成 2026-09-20 矿业资讯速览 index.html
- 09-19 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-21）回补历史条目
- 换入 09-18~09-19 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-18 收盘 + LME 09-16 收盘（东财日K末点连续第 3 日滞后，卡片=走势图口径），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
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
    unit_class, UNIT_SHFE_GROUP, UNIT_LME_GROUP,
)
from functools import partial


SITE_NAME = '矿业资讯速览'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()
_ORIG_SIZE = len(html)

REPORT = '2026-09-20'
GRAB = '2026-09-20'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
# 站点名固定「矿业资讯速览」，标题统一写成「矿业资讯速览 · YYYY-MM-DD」。
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月20日 星期日', html)
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
    shfe_cards.append(card(slug, name, tag, val, unit, chgtxt, 'up' if chg >= 0 else 'down',
                           group_unit=UNIT_SHFE_GROUP))
shfe_html = ''.join(shfe_cards)
# 电解钴：无当日源，保留上日 SMM 值并标注
# 单位同为「元/吨」= 国内盘分组单位 -> 走 unit_class 隐藏重复单位（2026-09-13 契约）
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

new_items = [
    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://news.metal.com/en/newscontent/104117798-smm-analysis-indonesia-revises-nickel-ore-hpm-once-again-pulling-limonite-prices-toward-market-levels',
                'SMM 国际站', '09-16',
                '印尼再度修订镍矿内贸基准价 低品位褐铁矿税费负担大幅减轻',
                '印尼能矿部以 363.K/MB.01/MEM.B/2026 号令再次修订镍矿内贸基准价（HPM）公式，自 2026 年 9 月 15 日起生效，重点下调 1.2% 品位褐铁矿的镍修正系数（由 4 月 144 号令下的 26% 降至 14%）与钴系数，其余参数不变。以 1.2% 镍矿为例，新 HPM 为 24.89 美元/湿吨，较 144 号令下的 44.97 美元/湿吨下降 20.08 美元/湿吨、降幅 45%，已回到实际成交价（约 27 美元/湿吨）下方。按 14% 权利金率测算，每湿吨权利金由 6.39 美元降至 3.48 美元，此前较实际成交价多缴约 2.61 美元/湿吨（高 41%）的负担基本消除。',
                orig_title='[SMM Analysis] Indonesia Revises Nickel Ore HPM Once Again, Pulling Limonite Prices Toward Market Levels')),
    (CAT_ZC, ni('https://news.metal.com/en/newscontent/104123729-miit-ndrc-push-industrialization-of-solid-state-sodium-ion-flow-batteries-and-fuel-cells-in-new-plan',
                'SMM 国际站', '09-19',
                '工信部、发改委推动固态电池、钠离子电池等新型电池产业化',
                '工业和信息化部、国家发展改革委联合印发《电子信息制造业「十五五」发展规划》，提出巩固锂电池竞争优势，继续推动固态电池、钠离子电池、液流电池和燃料电池产业化，推动新型电池智能化、绿色化、融合化发展，并支持其在智能终端、新能源汽车、船舶、航空、智能机器人、工程机械和农业机械等场景应用。规划同时要求推进高效晶硅光伏电池技术迭代升级，发展钙钛矿叠层电池等新一代高效光伏电池技术和配套设备材料。',
                orig_title='MIIT, NDRC Push Industrialization of Solid-State, Sodium-Ion, Flow Batteries, and Fuel Cells in New Plan')),

    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260916_10313847.htm',
                '全球矿产资源信息系统', '09-16',
                '马拉维南部通杜卢稀土矿钻探见富矿 重稀土钇品位异常高',
                '据矿业新闻网（Miningnews.net）报道，金王矿业公司（AuKing Mining）在马拉维南部通杜卢（Tundulu）稀土矿初步钻探样品分析结果好于预期，且见到「超常富集的重稀土」。40 米深处见矿 91 米、总稀土氧化物（TREO）品位 1.51%，其中 15 米厚段品位 3.4%；自地表见矿 80 米、TREO 品位 1.54%，其中 11 米厚段品位 4.33%。重稀土—钇（HREE-Y）矿段品位异常高，首个钻孔 68 米深处见矿 8 米、品位 16.09%。公司表示 4300 米反循环钻探将支撑年底前首次形成资源量；通杜卢项目今年初以 550 万澳元从塔斯克矿产公司购得。')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104123666',
                '上海有色网', '09-19',
                '伦铜 12 周内第 11 次周线上涨 中国洋山铜溢价创近四年新高',
                '伦铜在近 12 周内第 11 次录得周线上涨，9 月 18 日 LME 铜期货收报 14521.50 美元/吨、涨 0.2%，今年累计涨幅接近 17%。衡量中国进口铜需求的洋山铜溢价同日升至 124 美元/吨，为 2022 年 11 月以来最高，显示需求端明显改善。市场对精炼铜加征关税的预期促使铜货提前流入美国、挤压其他地区供应；美联储本周实施 2023 年以来首次加息并释放进一步收紧信号，但对铜价冲击有限，惠誉旗下 BMI 预计短期基本金属将维持区间震荡。')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104123026-copper-concentrate-tc-index-hits-record-low-smelter-pressures-mount-amid-maintenance-and-supply-constraints',
                'SMM 国际站', '09-18',
                '铜精矿现货加工费指数创历史新低 国内冶炼厂减产压力上升',
                '9 月 18 日，SMM 进口铜精矿现货加工费（TC）指数跌至 -221.89 美元/干吨的历史新低。2026 年进口铜精矿长单加工费基准为零，粗铜加工费同样处于历史低位、粗铜供应偏紧；副产品硫酸价格已回落约两个半月，利润贡献持续收窄。10—11 月国内多家铜冶炼厂计划检修且冷料补充有限，市场消息称部分冶炼厂已释放减产意向并通知客户减少长单交付，阴极铜产量面临下行压力。',
                orig_title='Copper Concentrate TC Index Hits Record Low, Smelter Pressures Mount Amid Maintenance and Supply Constraints')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104123105-goldman-keeps-5400-gold-forecast-intact-despite-fed-hike',
                'SMM 国际站', '09-18',
                '高盛维持 2027 年底金价 5400 美元预测 称加息只放缓不改趋势',
                '高盛将 2027 年底金价预测维持在 5400 美元/盎司不变，认为货币政策收紧会放缓金价涨势但不会使其逆转。9 月 18 日金价升至 4355 美元/盎司上方，受美元走软与国际油价当日下跌约 1% 支撑。美联储本周加息，最新季度经济预测显示 18 位官员中有 16 位预计年内至少再加息 25 个基点，实际利率与美元走势仍是短期压力，中东局势继续为金价提供支撑。',
                orig_title='Goldman keeps $5,400 gold forecast intact despite Fed hike')),
    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260916_10313845.htm',
                '全球矿产资源信息系统', '09-16',
                'BMI 上调今年国际锡价预期至 5.1 万美元/吨',
                '据矿业周刊（Miningweekly）报道，惠誉方案旗下基准矿物情报公司（BMI）将 2026 年锡均价预测由 4.9 万美元/吨上调至 5.1 万美元/吨。9 月 2 日 LME 三个月期锡价约 54633 美元/吨，今年以来均价 51385 美元/吨。BMI 认为人工智能资本支出激增带动半导体用锡大幅增加，预计今年 AI 领域投资约 7850 亿美元；因供应短缺缓解与 AI 投资增速放缓，四季度锡价或小幅回落。全球精炼锡产量预计由 2024 年 41.91 万吨增至 2030 年 47.83 万吨，同期消费量由 41.34 万吨增至 54.43 万吨。')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://www.chinania.org.cn/html/xiehuidongtai/xiehuidongtai/2026/0919/62043.html',
                '中国有色金属工业协会', '09-19',
                '2026 年中国铜加工产业年度大会在铜陵召开 聚焦算力金属',
                '9 月 17 日，2026 年中国铜加工产业年度大会暨中国（铜陵）铜产业高质量发展大会在安徽铜陵召开，主题为「算力金属·链接未来」，聚焦算力金属、高速连接、高效散热等领域铜基新材料技术创新与产业化应用。中国有色金属工业协会党委书记敖宏致辞指出，铜兼具功能材料与结构材料双重属性，既是电力、交通、家电等传统领域基础原材料，也是新能源汽车、光伏储能、新一代信息技术等战略性新兴产业的关键支撑，是当前最重要的算力金属。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/xiehuidongtai/xiehuidongtai/2026/0919/62042.html',
                '中国有色金属工业协会', '09-19',
                '中国有色金属工业协会与韩国矿害矿业公团签署谅解备忘录',
                '9 月 17 日，中国有色金属工业协会与韩国矿害矿业公团在北京签署谅解备忘录，协会常务副会长贾明星与公团社长黄永植代表双方签约。贾明星介绍，中国 2025 年十种有色金属产量突破 8000 万吨，行业利润创历史新高，双方应深化交流合作、携手推动海外资源开发。黄永植介绍，公团是韩国产业通商部所属机构，为矿产资源开发、再生资源产业发展、矿害防治与绿色矿山建设提供支持，希望共同保障中韩关键矿产资源安全。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://www.mining.com/us-doe-looks-to-industry-for-critical-minerals-and-materials-cleanup-at-legacy-sites',
                'MINING.COM', '09-18',
                '美国能源部就遗留核设施关键矿产回收征求业界意见',
                '美国能源部环境管理办公室（EM）发布意向征询（EOI），就五个核清理场址中富余的关键矿产、稀土及其他物料的潜在转让征求美国产业界意见。涉及物料包括铝、铯-137、氯化物、铜、氟、铅、氢化锂、铂、硒、银、钨和钒，均来自历年核武器生产与政府资助的能源研究。五个场址为肯塔基州帕杜卡、俄亥俄州朴茨茅斯、田纳西州橡树岭、内华达国家安全场址与犹他州莫阿布；EM 将于 9 月 30 日举办线上产业日，参与方须自备设备与技术。',
                orig_title='US DOE looks to industry for critical minerals cleanup at legacy sites')),
    (CAT_GJ, ni('https://www.mining.com/nigeria-mining-crackdown-under-fire-after-37-die',
                'MINING.COM', '09-18',
                '尼日利亚矿业整治行动致 37 名被拘留者死亡 引发抗议',
                '尼日利亚矿业整治行动中被捕的 37 人在羁押期间死亡，引发抗议并促使外界审视该国矿业执法。尼日尔州政府 9 月 18 日宣布暂停所有采矿活动，并在明纳市实施全天候宵禁，该市位于首都阿布贾西北约 150 公里。当局 9 月 15 日、16 日在明纳附近矿区逮捕数十人，18 日凌晨发现 37 名被拘留者死亡，死因尚未确定。州长称可能是羁押人数过多导致窒息；尼日利亚内政部已暂停尼日尔州民防指挥部指挥官职务，国际特赦组织呼吁开展独立调查。',
                orig_title='Nigeria mining crackdown under fire after 37 die')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104123742-chilean-copper-output-to-stay-low-disappointing-recovery-hopes-for-2026',
                'SMM 国际站', '09-19',
                '智利铜产量全年维持低迷 2026 年复苏预期落空',
                '智利铜产量全年或持续低迷，市场对下半年复苏可部分弥补上半年损失的预期落空。智利财政部长豪尔赫·基罗斯表示，今年产量降幅将远超官方铜统计机构的预测，预计仅 2027 年出现部分恢复。智利铜业委员会此前已将 2026 年铜产量预测下调至 527 万吨，上半年产量下降 6.6%、7 月同比下降 9.4%。',
                orig_title='Chilean Copper Output to Stay Low, Disappointing Recovery Hopes for 2026')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202609/t20260916_10313846.htm',
                '全球矿产资源信息系统', '09-16',
                '加拿大推出 1 万亿加元招商计划 逾三分之一项目涉及矿业',
                '据矿业网站（Mining.com）报道，加拿大总理马克·卡尼将矿业作为该国争取 1 万亿加元（约 7210 亿美元）国际投资的核心。在多伦多举行的第一届加拿大投资峰会提出的 167 个项目中，超过三分之一涉及矿业，卡尼邀请 100 家世界最大投资者参会，这些投资者旗下资产合计超过 70 万亿美元。蒙特利尔银行资本市场预测未来两年年度投资额增幅将超过 11%，未来五年其研究对象企业在运营成本、可持续资本与增长项目的投资将超过 3500 亿加元。矿业企业中特洛伊罗斯矿业需 14.3 亿美元开发魁北克铜金项目。')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104123723-lg-energy-solution-signs-lithium-supply-agreement-with-smackover-in-arkansas',
                'SMM 国际站', '09-19',
                'LG 新能源与 Smackover Lithium 签署 10 年碳酸锂供应协议',
                'LG 新能源与 Smackover Lithium 签署供货协议，后者将自 2029 年起连续 10 年每年向 LG 新能源供应 8000 吨电池级碳酸锂。碳酸锂是磷酸铁锂（LFP）电池的关键原料，随着 LFP 电池作为低成本替代路线份额上升，相关需求持续增加。该协议是 Smackover Lithium 的第二份承购协议，此前其已于 3 月与托克（Trafigura）签署电池级碳酸锂承购协议。',
                orig_title='LG Energy Solution Signs Lithium Supply Agreement with Smackover in Arkansas')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-19/1225571231.PDF',
                '巨潮资讯网', '09-19',
                '淮北矿业未中选同德化工重整投资人 列为备选',
                '淮北矿业（600985）公告，公司于 2026 年 7 月 14 日召开董事会，审议通过以产业投资人身份与财务投资人组成投资联合体，向山西同德化工股份有限公司预重整辅助机构提交重整投资方案并参与重整投资人遴选。2026 年 9 月 17 日公司收到辅助机构通知书，公司未被选为重整投资人，为备选重整投资人，该事项不会对公司正常生产经营造成不利影响。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-19/1225571792.PDF',
                '巨潮资讯网', '09-19',
                '安彩高科 1.14 亿元出售贵金属铑粉 已完成交割',
                '安彩高科（600207）公告，公司通过公开挂牌方式出售贵金属铑粉（净重 56835.5 克）。2026 年 8 月 12 日，公司在中原产权交易平台第五次公开挂牌，挂牌价 11372.79 万元；9 月 9 日挂牌结束，永兴鹏琨环保有限公司为唯一意向受让方并已缴纳保证金。近日公司与受让方签订《实物资产交易合同》，含税成交金额 11372.79 万元，公司已收到全部价款并完成铑粉移交。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-18/1225571033.PDF',
                '巨潮资讯网', '09-18',
                '亿纬动力与 Fluence 签署 206GWh 电池供货框架协议',
                '亿纬锂能（300014）公告，子公司湖北亿纬动力有限公司与 Fluence Energy Global Production Operation, LLC 就 2027—2031 年向 Fluence 生产交付 206GWh 电池事宜签署供货框架协议：双方就 2027 年承诺交付量 16GWh 达成一致，2028—2031 年预留容量合计 190GWh。协议为框架性约定，具体合作事项以各方后续另行正式签署的采购订单为准，对公司本年度及未来各会计年度财务状况的具体影响存在不确定性。',
                embed='pdf')),
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

# ============ 3.6 数字落地校验（2026-09-14 新增，复用 verify_numbers） ============
# 每条摘要的数字须能在源文（候选池/月库）找到，防 LLM 抄错数字。
# 候选池未落盘或未开 --fetch-detail 时源文基准为空 -> 自动 skip（不阻断生成）。
# 生产守门：置 VERIFY_NUMBERS_STRICT=1 时未落地即抛异常（CI / 上线前卡点）。
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
