# -*- coding: utf-8 -*-
"""
生成 2026-10-20 矿业资讯速览 index.html（周二）
- 10-19 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-21）回补历史条目
- 换入 10-20 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-19 收盘 + LME 10-19 收盘（10-20 周二 05:30 未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，今日无新增公告，窗口沿用 37 宗），不进主页列表
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

REPORT = '2026-10-20'
GRAB = '2026-10-20'
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
                         r'\g<1>2026年10月20日 星期二', html)
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
    (CAT_ZK, ni('https://www.mining.com/volta-doubles-springer-rare-earths-eyes-2027-study',
                'MINING.COM', '10-19',
                'Volta：安大略 Springer 稀土指示资源增 116% 至 122.4 Mt，居北美第五',
                '沃尔塔金属（Volta Metals）更新安大略省 Springer 稀土-镓矿床资源量，指示资源增 116% 至 122.4 Mt、TREO 品位 0.59%，推断资源 197.5 Mt、品位 0.53%；高品位核 27.6 Mt、品位 1%，并首次估算镓资源 4427 吨。按标普全球市场财智数据，该项目按指示资源量居北美稀土项目第五，公司计划 2027 年上半年完成初步经济评价。',
                orig_title='Volta doubles Springer rare earths resource, eyes 2027 study')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202610/t20261019_10338728.htm',
                '全球矿产资源信息系统', '10-19',
                '纳米比亚奥塔维铜矿钻获 7 米 4.89% 高品位铜，另两项目见矿',
                '米达斯矿产公司在纳米比亚奥塔维项目德布林矿床钻获多层高品位铜矿段：439 米深处见矿 7 米、铜品位 4.89%、银 5.6 克/吨，471 米处见矿 6 米、铜品位 3.47%、银 5.6 克/吨，487 米处见矿 10 米、铜品位 1.92%，并发现金、钼，计划 2027 年更新资源量。同批进展还包括澳大利亚 Peak Hill 金矿斑岩目标延伸至 1651 米以下、西澳 Mt Mulgine 钨矿 2 米处见矿 292 米、钨品位 0.11%。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474691',
                '中国有色金属报', '10-19',
                '中铝郑州研究院铝电解降碳技术突破，吨铝全氟化碳当量排放降 77%',
                '中铝郑州研究院牵头完成的「基于降低全氟化碳排放的铝电解节能降碳技术」取得突破，使我国铝电解全氟化碳等效二氧化碳排放强度由 1.12 吨/吨铝降至 0.26 吨/吨铝以下，降幅超 77%。该技术已在 20 余家电解铝企业推广应用、覆盖产能超 600 万吨，吨铝直流电耗平均降低 47 千瓦时以上，2022 年以来累计节电 11.33 亿千瓦时、减排二氧化碳 1871 万吨。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474682',
                '中国有色金属报', '10-19',
                '新西兰铝挤压材保障措施调查无措施结案，系该国近 30 年首起',
                '新西兰商业、创新与就业部 10 月 13 日发布终裁公告，宣布铝挤压材保障措施调查无措施结案。该调查于 2026 年 5 月 28 日启动，是新西兰近 30 年来首起保障措施调查；中国有色金属工业协会在商务部贸易救济局指导下组织重点涉案企业开展行业无损害抗辩，围绕进口增长、损害与因果关系、公共利益逐项拆解，并争取到中新双边听证。')),

    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474688',
                '中国有色金属报', '10-19',
                '《节水型企业 电解铜箔行业》行业标准获批，2027 年 4 月起实施',
                '工业和信息化部 2026 年第 23 号公告批准包括《5G消息业务质量要求与评估方法》在内的 369 项行业标准，由江铜铜箔牵头编制的《节水型企业 电解铜箔行业》正式获批，将于 2027 年 4 月 1 日起实施。该标准明确电解铜箔行业节水型企业评价指标体系与规范要求，填补了国内电解铜箔行业节水评价标准空白。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104166420',
                '上海有色网', '10-20',
                '央行将设非银机构大额赎回流动性支持工具，隔夜回购利率将成主要政策利率',
                '人民银行行长潘功胜在 2026 金融街论坛年会演讲中提出多项举措：会同金融监管总局、中国证监会设立应对非银机构大额赎回的流动性支持工具，扩大常备借贷便利（SLF）适用机构范围至境内外资法人银行，推动银行间与交易所债券市场互联互通。利率方面将用市场化利率指标替代存贷款基准利率，并研究择机把公开市场主要操作品种期限切换为隔夜。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474701',
                '中国有色金属报', '10-19',
                'INSG 转调：2026 年全球镍市料过剩 1.9 万吨，明年过剩扩大',
                '国际镍业研究组织（INSG）10 月 13 日发布报告，将 2026 年全球镍市由此前预测的短缺 3.2 万吨修正为过剩 1.9 万吨：需求约 385 万吨、同比增长 7.6%，产量 387 万吨；该机构 4 月时预测需求 375 万吨、产量 372 万吨。INSG 同时预计明年供应过剩将进一步扩大。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474702',
                '中国有色金属报', '10-19',
                '麦格隆：白银未来数年或限于 50~84 美元/盎司区间',
                '彭博行业研究高级大宗商品策略师麦格隆认为，白银在年初突破 120 美元/盎司、创历史新高后仍面临严峻技术面压力，未来数年价格可能被限制在 50 美元至 84 美元/盎司之间。他表示这轮涨势留下的估值与波动性问题可能需要多年才能消化，市场需要在更低价格水平上重新调整需求。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/7ef5afaafc2a4156934a7ec3c6ff7d35.html',
                '长江有色网', '10-19',
                '沪铜收 10.98 万元/吨，11 万关口进入三角博弈',
                '10 月 19 日沪铜主力 2611 合约收报 109770 元/吨，亚盘时段伦铜 3M 在 14363.5 美元/吨附近震荡。现货端长江 1# 铜报 110820 元/吨、升水 830 至 870 元/吨，盘面小幅反弹但成交乏力，下游畏高情绪主导、补库仅维持长协刚需。冶炼减产托底与需求、宏观双重压制并存。')),

    (CAT_SC, ni('https://www.mining.com/digital-gold-could-triple-by-2031-wgc-estimates',
                'MINING.COM', '10-20',
                '世界黄金协会：数字黄金规模 2031 年或增至 1600~1700 亿美元',
                '世界黄金协会与波士顿咨询联合报告预计，数字黄金市场规模将从当前 450 亿至 550 亿美元增至 2031 年的 1600 亿至 1700 亿美元，为金市带来约 950 亿美元增量资金。调查显示近九成散户在条件合适时愿意考虑数字黄金，但约八成投资者最看重发行方可信度，目前该品类占实物投资金市场不足 1%。',
                orig_title='Digital gold could triple by 2031, WGC estimates')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474690',
                '中国有色金属报', '10-19',
                '新疆有色大红柳滩冶炼项目一期二阶段开工，锂资源就地深加工',
                '9 月 27 日，新疆有色集团大红柳滩冶炼项目一期二阶段开工仪式在洛浦县昆冈产业园区举行。项目由新疆昆仑蓝钻矿业开发有限责任公司实施，将实现本地锂资源就地深加工转化、完善南疆新能源全产业链条，被集团视为冲刺千亿元产值目标的重要支撑。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474711',
                '中国有色金属报', '10-19',
                '安宁股份 6 万吨能源级钛全产业链项目产出首炉海绵钛',
                '四川安宁铁钛股份有限公司投资建设的年产 6 万吨能源级钛（合金）材料全产业链项目产出第一炉海绵钛，单炉产量约 13 吨，产品质量达到设计要求，项目已进入试生产阶段。公司以钒钛磁铁矿资源为核心，通过横向拓展资源、纵向延伸产业链推进钛金属矿材一体化。')),

    (CAT_HY, ni('https://news.metal.com/newscontent/104166459-north-china-smelter-in-furnace-drying-aims-100-mt-daily-output-in-7-8-days-amid-unstable-raw-material-supply',
                'SMM 国际站', '10-20',
                '华北大型再生铅冶炼厂烘炉，7~8 天后出铅、日产约 100 吨',
                'SMM 报道，华北一家大型冶炼厂已进入烘炉阶段，预计 7 至 8 天后正式出铅，初期日产量约 100 吨。当前废电瓶原料到货不稳，后续产量仍有待观察。',
                orig_title='North China Smelter in Furnace Drying, Aims 100 mt Daily Output in 7-8 Days Amid Unstable Raw Material Supply')),

    (CAT_HY, ni('https://www.mining.com/volvo-to-launch-a-mining-division-to-meet-global-equipment-demand',
                'MINING.COM', '10-20',
                '沃尔沃设矿业事业部，2027 年起供应矿用卡车与自动驾驶方案',
                '沃尔沃集团宣布成立矿业事业部 Volvo Mining，自 2027 年 1 月 1 日起在沃尔沃建筑设备（Volvo CE）下运营，向矿业公司与承包商供应卡车、工程机械及自动驾驶解决方案。该部门先聚焦瑞典、挪威、芬兰市场，后续分阶段扩张，由现任沃尔沃卡车国际高级副总裁 Per-Erik Lindstrom 负责。',
                orig_title='Volvo to launch mining division to meet global equipment demand')),

    (CAT_HY, ni('https://www.mining.com/americas-golds-record-silver-output-misses-forecasts',
                'MINING.COM', '10-19',
                'Americas Gold 三季度白银产量创纪录 80.05 万盎司，仍低于预期',
                'Americas Gold and Silver 三季度白银产量 800458 盎司、同比增长 4.6%，创单季纪录，但低于分析师预期的 95 万盎司；当季销量 86.085 万盎司亦创纪录。公司重申 2026 年白银产量 320 万至 360 万盎司、全维持成本 30 至 35 美元/盎司的指引，前三季度产量 230 万盎司；Galena 与墨西哥 Cosalá 分别产银 38.46 万与 41.59 万盎司。',
                orig_title="Americas Gold's record silver output misses forecasts")),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://news.smm.cn/news/104165130',
                '上海有色网', '10-20',
                'Centinela 两大工会通过新合同，持续一周多的罢工结束',
                '安托法加斯塔旗下智利 Centinela 铜矿两大工会工人表决通过与公司达成的新集体合同，10 月 7 日开始的罢工宣告结束，参与投票工人中 94.49% 赞成。Centinela 矿区工会与 Minera Esperanza 工会合计 700 余名工人，诉求为全员享受同等福利；公司称罢工期间产量维持正常水平，该矿 2025 年铜产量 240400 吨。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202610/t20261019_10338725.htm',
                '全球矿产资源信息系统', '10-19',
                '南非 8 月矿业产出同比降 12.7%，铂族金属拖累 6.1 个百分点',
                '南非统计局数据显示，8 月采矿业产出同比下降 12.7%，其中铂族金属降 22.5%、拖累 6.1 个百分点，煤炭降 11.7%、铁矿石降 16.2%。经季节调整环比降 5.4%，6 至 8 月同比降 5.2%；按现价计算 8 月矿产品销售额同比降 15.1%，金降 48.6%。')),

    (CAT_GJ, ni('https://www.mining.com/sudan-gold-rush-leaves-toxic-legacy-as-war-drives-mining',
                'MINING.COM', '10-19',
                '苏丹战时淘金潮留下汞氰污染，200 万至 500 万人依赖手工采金',
                '苏丹战事导致农业与贸易萎缩，200 万至 500 万人转向基本无监管的手工采金；据苏丹矿产资源公司，手工采矿约占该国黄金产量的 80%，2025 年官方出口黄金 14.7 吨、价值 15.36 亿美元，占出口收入逾 58%。调查在尼罗河州与北方州发现含汞、氰化物的尾渣，部分土壤汞读数远超世卫组织与美国环保署安全标准；10 月 10 日苏丹与埃及边境一处手工金矿遭空袭，致至少 114 人死亡。',
                orig_title='Sudan gold rush leaves toxic legacy as war drives mining')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/copper-hungry-us-buyers-circle-ivanhoe-electric-mine',
                'MINING.COM', '10-19',
                'Ivanhoe Electric 就 14 亿美元 Santa Cruz 铜矿洽谈承购，或含建设融资',
                'Ivanhoe Electric 正就亚利桑那州 14 亿美元的 Santa Cruz 铜矿项目铜承购进行深入谈判，潜在买方包括大宗商品贸易商与寻求本土铜供应的战略伙伴，协议可能附带开发融资。美国进出口银行已出具初步项目函，涉及最多 11 亿美元潜在债务融资，公司另与约十余家商业银行洽谈项目融资，目标 2029 年首次产出。',
                orig_title='Copper-hungry US buyers circle Ivanhoe Electric mine')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-20/1225611067.PDF',
                '巨潮资讯网', '10-20',
                '湖南裕能拟投不超 20 亿元建六期磷酸铁锂项目，建设期 12 个月',
                '湖南裕能 10 月 19 日董事会审议通过投资建设六期磷酸铁锂项目，计划投资不超过人民币 20 亿元，资金来源为企业自筹，建设期 12 个月。项目选址湘潭市雨湖区鹤岭镇，总建筑面积约 8 万平方米，将建设厂房并购置磷酸铁锂成套生产线设备，本事项无需提交股东会审议。',
                embed='pdf')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://www.mining.com/military-metals-wins-four-year-slovak-licence-lifeline',
                'MINING.COM', '10-20',
                'Military Metals 斯洛伐克 Trojárová 锑金矿许可延长四年至 2030 年',
                '斯洛伐克环境部推翻 5 月的吊销决定，Military Metals 的 Trojárová 锑金矿勘探许可延长四年、至 2030 年 10 月 18 日，公司股价当日涨 28% 至 25.5 加分。该项目位于布拉迪斯拉发东北约 20 公里的 Pezinok 附近，推断资源 650 万吨、锑品位 1.02%、金 1.06 克/吨，含锑约 6.7 万吨、金 22.2 万盎司。',
                orig_title='Military Metals wins four-year Slovak licence lifeline')),
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
