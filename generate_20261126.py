# -*- coding: utf-8 -*-
"""
生成 2026-11-26 矿业资讯速览 index.html（周四）
- 11-25 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30）回补历史条目
- 换入 11-25/11-26 采集的条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为最近已收盘交易日，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）
- 矿权条目：今日新增公告走 #rightsCards 既有窗口，不进主列表
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信 / 价格三视图
- 境外条目保留英文原题（data-orig-title + 摘要末尾「原题：…」）
"""

import re, datetime, json, glob, os
import sys
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

REPORT = '2026-11-26'
GRAB = '2026-11-26'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年11月\d{2}日 星期.',
                         r'\g<1>2026年11月26日 星期四', html)
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

# 2026-10-29 一次性清理：chinania.org.cn 源已禁用且死链已从月库/前端库清除，
# 但现有 index.html 往期区仍残留其卡片（arch_keep 继承自旧 html），
# 此处统一剔除，确保重生成的 index.html 不再渲染该死链。
merge_seq = [(c, it) for c, it in merge_seq if 'chinania.org.cn' not in it]

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
    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/newscontent/ERCE5L5UPIUPIW2OTRS5SVLUCZTB7YKTX4555OQ-france-to-establish-strategic-reserves-of-critical-minerals-from-2027-to-reduce-reliance-on-china',
                'SMM 国际站', '11-26',
                '法国将于2027年起建立稀土等关键矿产战略储备',
                '法国总统马克龙宣布，法国计划自 2027 年起建立稀土及其他关键矿产战略储备，并推动工业用户联合采购、签订长期供应协议，以降低对中国供应链的依赖。该计划由一家国有金融机构牵头实施，欧盟提供支持。',
                orig_title='France to Establish Strategic Reserves of Critical Minerals from 2027 to Reduce Reliance on China')),

    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/flfg/202611/t20261125_10374191.htm',
                '全球矿产资源信息系统', '11-25',
                '刚果（金）11月30日起再度暂停钴出口',
                '刚果（金）战略矿产市场监管机构（ARECOMS）宣布，自 11 月 30 日起暂停全部钴出口，以缓解国际市场供应过剩、提振持续下跌的钴价。这是该国第二次全面禁止钴出口——2025 年 2 月的首轮禁令 8 个月后被配额制替代，配额制目前仍在执行。禁令前刚果（金）钴矿出口占全球约四分之三，洛阳钼业、嘉能可与欧亚资源集团持有最大配额；分析认为新禁令可能使印尼镍矿伴生钴受益。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.mining.com/copper-price-sinks-to-2026-low-as-mining-stocks-brace-for-further-losses',
                'MINING.COM', '11-25',
                '铜价跌至2026年新低，铜矿股市值本月蒸发1450亿美元',
                '11 月 25 日 Comex 12 月期铜下跌 2.1% 至 5.25 美元/磅（约 11584 美元/吨），盘中低见 5.222 美元，跌破 3 月 20 日的 5.3425 美元年内前低；LME 三个月期铜跌 1.9% 至 11596 美元/吨。铜价年内累跌约 7%、11 月单月跌近 19%，较 9 月 9 日纪录高位低 24%。MINING.COM 测算，10 家大型铜矿企业 10 月底以来市值合计缩水 1450 亿美元，其中南方铜业减少 360 亿美元；BMO 预计抛售或延续至 10000—11000 美元/吨区间。',
                orig_title='Copper price sinks to 2026 low as mining stocks brace for further losses')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202611/t20261125_10374194.htm',
                '全球矿产资源信息系统', '11-25',
                '国际矿产品价格多数下跌，锡价单日跌超6%',
                '周二（11 月 24 日）国际原油小幅上涨，其他矿产品价格多数下跌。锡期货收于 39410 美元/吨、下跌 6.28%，为当日跌幅最大品种；铜收于 11886.50 美元/吨、下跌 4.68%，铝 2777 美元/吨、下跌 2.89%，锌 3443.50 美元/吨、下跌 3.01%，镍 15240 美元/吨、下跌 1.33%，铅 1839 美元/吨、上涨 0.57%。贵金属同步走弱，纽约金收于 3556.9 美元/盎司、下跌 2.15%，银 40.91 美元/盎司、下跌 5.13%，铂 1257.8 美元/盎司、下跌 5.01%。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.mining.com/sulphur-shortage-threatens-indonesias-nickel-plans',
                'MINING.COM', '11-25',
                '硫磺短缺或拖累印尼逾60万吨镍产能扩张',
                '咨询机构伍德麦肯兹 11 月 25 日表示，硫磺供应紧张可能拖累印尼电池材料领域逾 60 万吨镍产能的扩产项目。霍尔木兹海峡关闭前，印尼约 80% 的硫磺进口来自中东；2026 年上半年硫磺进口量同比下降 29%，均价接近翻三倍。硫磺约占印尼高压酸浸（HPAL）工厂运营成本的一半。国际能源署数据显示，印尼 2025 年镍产量约 260 万吨，占全球约三分之二。',
                orig_title='Sulphur shortage threatens Indonesia\u2019s nickel plans')),

    (CAT_HY, ni('https://www.mining.com/core-lithium-ships-first-spodumene-concentrate-from-finniss',
                'MINING.COM', '11-25',
                'Core Lithium芬尼斯矿复产后首批发运锂精矿',
                '澳大利亚 Core Lithium（ASX: CXO）11 月 25 日从达尔文港发运芬尼斯（Finniss）矿复产后首批锂精矿，约 1 万湿吨、品位 5.1% 氧化锂，买家为一家大型国际锂化学品生产商。该矿 2026 年 5 月复产，9 月重介质选矿厂投产。公司预计生产延续至 2027 年四季度初，累计交付约 13.4 万吨 SC5 当量锂精矿；精矿由嘉能可依据五年承销协议负责销售。',
                orig_title='Core Lithium ships first spodumene concentrate from Finniss')),

    (CAT_HY, ni('https://news.metal.com/newscontent/ADP6PXQICDC3EFF473UVG5BLWQAHFBPWCBTO4IY-bhp-plans-181b-investment-to-double-copper-production-in-south-australia-by-2040',
                'SMM 国际站', '11-23',
                '必和必拓拟投最高181亿美元，南澳铜年产能提至65万吨',
                '必和必拓（BHP）11 月 23 日宣布，计划投资 142 亿—181 亿美元，将南澳铜年产量提升至 65 万吨、较目前接近翻倍，最终投资决定预计 2027 年上半年作出。南澳被公司称为全球第二大铜矿省，达产后产能将接近智利埃斯康迪达铜矿。公司目标是到 2030 年代中期全球铜产量达 200 万吨，南澳项目预计贡献其 2035 年前铜增量的约三分之一。',
                orig_title='BHP Plans $18.1B Investment to Double Copper Production in South Australia by 2040')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://news.metal.com/newscontent/6MCKNYYCUORYK25HBDIO43ZTWX7PSKSREUARZGI-trinity-metals-launches-diamond-drilling-at-rwandas-rutongo-tin-mine-targets-200-tmonth-within-five-years',
                'SMM 国际站', '11-26',
                'Trinity Metals启动卢旺达Rutongo锡矿首个现代金刚石钻探',
                'Trinity Metals 于 11 月 13 日在卢旺达 Rutongo 锡矿的 Karambo 矿井启动首个现代金刚石钻探计划，验证现有采场下部矿化。首期 5 个钻孔、总进尺 1800—2000 米，最深 650—700 米，工期约三个月，首孔已钻进 75 米，成果将用于规划深部开拓与生产衔接。Rutongo 位于基加利以北 26 公里，拥有 6 座地下锡矿、面积 9600 公顷，目前月产锡 40—70 吨；公司估算可采锡 5.4 万吨，目标五年内月产 200 吨，该工作属 1.2 万米地表勘探计划的一部分。',
                orig_title="Trinity Metals launches diamond drilling at Rwanda's Rutongo tin mine, targets 200 t/month within five years")),

    (CAT_ZK, ni('https://www.mining.com/stratum-ai-model-feeds-simberis-mineral-resource-estimate',
                'MINING.COM', '11-25',
                'Stratum AI深度学习模型用于巴新辛贝里金矿资源量估算',
                '多伦多深科技公司 Stratum AI 宣布，其深度学习模型已用于圣芭芭拉（St Barbara）巴布亚新几内亚辛贝里（Simberi）金矿的公开资源量估算，属矿业界首批案例之一。模型用于风化程度与矿石类型分类，使原被认为不适合现有炭浸（CIL）工艺的矿石得到利用：2024 年 5 月据此识别出额外 14.3 万盎司可处理矿石，延长矿山处理年限 17 个月，探明加概略储量提高 40%。该估算按 JORC 准则编制；辛贝里由圣芭芭拉、灵宝黄金与 Kumul 矿业共同持有。',
                orig_title='Stratum AI model feeds Simberi\u2019s mineral resource estimate')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/namib-minerals-pours-first-gold-at-historic-redwing-gold-mine',
                'MINING.COM', '11-23',
                'Namib Minerals津巴布韦Redwing金矿产出首金',
                'Namib Minerals（Nasdaq: NAMM）宣布，其位于津巴布韦东部的百年老矿 Redwing 在停产七年后产出首金，恢复商业生产；该矿 1981—2023 年累计产金约 65 万盎司。公司计划分阶段达产，长期目标是在 Redwing、How 与 Mazowe 三矿实现合计年产 30 万盎司，矿山重启预计投入 3 亿美元。可行性研究预计 2027 年一季度完成，随后开展资源圈定钻探；How 矿 2025 年产金 2.5 万盎司。',
                orig_title='Namib Minerals pours first gold at historic Redwing gold mine')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202611/t20261125_10374192.htm',
                '全球矿产资源信息系统', '11-25',
                '艾芬豪看好巴基斯坦未勘探铜金资源前景',
                '据矿业网（Mining.com）报道，艾芬豪矿业创始人罗伯特·弗里德兰在伊斯兰堡举行的巴基斯坦矿业投资论坛上表示，该国大部分尚未勘探的铜金资源有望推动经济起飞。他认为矿业可创造就业、惠及当地社区，并为长期受冲突影响的地区带来经济机遇。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/valore-seeks-financing-for-135m-brazil-gold-deal',
                'MINING.COM', '11-25',
                'ValOre拟1.35亿美元收购巴西Água Azul金矿，尚需落实融资',
                '加拿大 ValOre Metals（TSXV: VO）11 月 25 日宣布，以 1.35 亿美元（1.93 亿加元）向 Opportunity Holding 基金收购巴西 Água Azul 金矿及配套土地资产，对价约为其停牌前市值的 20 倍。付款安排为交割时 9000 万美元、一年后 2000 万美元、两年后 2500 万美元；公司尚未落实收购资金，目标 2027 年 1 月 15 日前完成交割。该矿位于圣保罗西北约 1900 公里，现有露天矿年处理矿石约 12 万吨；指示资源 2280 万吨、品位 1.27 克/吨、含金 93.2 万盎司，初步经济评价拟将处理能力扩至 285 万吨/年，税后净现值 9.276 亿美元。',
                orig_title='ValOre seeks financing for $135M Brazil gold deal')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-26/1225687443.PDF',
                '巨潮资讯网', '11-26',
                '南山铝业1美元受让印尼合资化工项目20%股权，持股升至71%',
                '南山铝业（600219）11 月 26 日公告，印尼合资公司 PT Bintan Fine Chem Indonesia 的年产 20 万吨烧碱、16.5 万吨环氧氯丙烷项目主体结构基本完成，正进行设备安装与管道施工。原持股 49% 的合作方实控人因对该领域经验不足退出并转让股权，公司境外全资公司 HHKIL 以 1 美元受让合资平台 20% 股权，持股比例由 51% 升至 71%。项目投资总额约 18.68 亿元人民币，本次交易资金来源为自有资金。',
                embed='pdf')),

    # ── 💼 矿权交易（仅入月库 → 前端 #rightsCards，不进主列表）─────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261126_10374206.htm',
                '矿业权市场', '11-26',
                '内蒙古敖汉旗东山梁金矿勘查探矿权出让成交，金陶股份竞得',
                '内蒙古自治区自然资源厅公示，敖汉旗东山梁金矿勘查探矿权于 2026 年 10 月 30 日至 11 月 13 日以网上挂牌方式出让，竞得人为内蒙古金陶股份有限公司（公示文号：赤自然资示字〔2026〕3 号）。矿区位于赤峰市敖汉旗金厂沟梁镇，出让标的为金矿勘查探矿权。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/ckzrgs/202611/t20261126_10374204.htm',
                '矿业权市场', '11-26',
                '汝州中鑫金华矿业向炳言矿业转让盛家村铝土矿采矿权',
                '河南省自然资源厅公示汝州市炳言矿业有限公司盛家村铝土矿采矿权转让事项（公示文号：豫自然资公〔2026〕264100001923 号），转让方为汝州中鑫金华矿业有限公司，受让方为汝州市炳言矿业有限公司。矿山位于汝州市汝南工业区虎头村西南，矿种为铝土矿。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261126_10374205.htm',
                '矿业权市场', '11-26',
                '四川盐源鸡心山铜多金属矿详查探矿权拟转让至兴陇矿业',
                '四川省自然资源厅公示盐源县鸡心山铜多金属矿详查探矿权转让事项（公示文号：川探转公示〔2026〕17 号），受让方为盐源县兴陇矿业有限公司，矿权位于凉山彝族自治州盐源县树河镇。')),
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

# —— 分桶 PIN（按内容口径：勘查成果属 🔍、政策属 📜、企业事故/产能属 🏭，勿被 _reclassify_ma 依「投资」二字拉到 💰）——
_PIN_CAT = [
    ('法国', CAT_ZC),
    ('刚果（金）', CAT_ZC),
    ('铜价跌至2026年新低', CAT_SC),
    ('国际矿产品价格', CAT_SC),
    ('硫磺', CAT_HY),
    ('Core Lithium', CAT_HY),
    ('必和必拓', CAT_HY),
    ('Trinity', CAT_ZK),
    ('Stratum', CAT_ZK),
    ('Namib', CAT_GJ),
    ('艾芬豪', CAT_GJ),
    ('ValOre', CAT_MA),
    ('南山铝业', CAT_MA),
]

def _pin_cat(title, cat):
    for _kw, _c in _PIN_CAT:
        if _kw in (title or ''):
            return _c
    return cat


new_items = [(_pin_cat(item_title(_it), _c), _it) for _c, _it in new_items]

merge_seq = [x for x in merge_seq if item_url(x[1]) not in new_seen_url]
merge_seq = dedup_same_event(merge_seq)

# ============ 3.6 数字落地校验（复用 verify_numbers） ============
# 2026-10-25 A03：严格模式下校验失败/校验器故障必须非零退出、不写正式产物
# （旧实现吞异常后继续 → strict 守门形同虚设）。分类见 generate_site.py 同段注释。
_STRICT_NUM = os.environ.get('VERIFY_NUMBERS_STRICT') == '1'
try:
    from verify_numbers import verify_new_items
    _num_issues = verify_new_items(new_items, REPORT, strict=_STRICT_NUM)
    if _num_issues:
        print('[num-warn] 共 %d 条摘要存在数字未在源文找到，请人工核对' % len(_num_issues))
except AssertionError as _e:
    if _STRICT_NUM:
        print('[verify_numbers] 严格模式：数字落地校验未通过，终止生成（不写 index.html）：%s' % _e)
        sys.exit(1)
    print('[num-warn] %s' % _e)
except Exception as _e:
    if _STRICT_NUM:
        print('[verify_numbers] 严格模式：数字校验器故障，终止生成（不写 index.html）：%s' % _e)
        sys.exit(1)
    print('[verify_numbers] 警告：数字校验未执行（工具故障）：%s' % _e)
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
