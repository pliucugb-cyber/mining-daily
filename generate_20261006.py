# -*- coding: utf-8 -*-
"""
生成 2026-10-06 矿业资讯速览 index.html（周二 · 国庆假期第 6 天）
- 10-05 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-07）回补历史条目
- 换入 10-06 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-30 收盘（现算）
  + LME 卡片=走势图末点口径 10-05 收盘（周二国庆假期国内休市），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易），不进主页列表
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

REPORT = '2026-10-06'
GRAB = '2026-10-06'
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
                         r'\g<1>2026年10月06日 星期二', html)
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
    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104143848-smm-news-patagonia-lithium-completes-72-hour-pump-test-at-cilon',
                'SMM 国际站', '10-05',
                '帕塔戈尼亚锂业阿根廷 Cilon 卤水井完成 72 小时抽水试验',
                'SMM 国际站报道，Patagonia Lithium 在阿根廷 Cilon 特许区 8 号井完成 72 小时抽水试验，流量 2,043 升/小时、累计抽液 146,800 升；250 米深度锂浓度达 232 ppm，共抽出锂约 34 公斤，折合碳酸锂当量约 180 公斤。24 小时恢复试验中水位由 52.4 米回升至静水位 3.64 米。公司已识别 226~324 米深度含水层，正更新资源量估算，随后将出具概略研究。',
                orig_title='[SMM News] Patagonia Lithium completes 72-hour pump test at Cilon')),

    (CAT_ZK, ni('https://www.mining.com/swanson-results-fall-short-despite-6-05-g-t-gold-highlight',
                'MINING.COM', '10-06',
                'LaFleur 魁北克 Swanson 金矿钻探见矿 6.05 克/吨，连续性不及预期',
                'MINING.COM 报道，LaFleur Minerals 公布魁北克 Swanson 金矿项目新钻探结果：Bartec 靶区钻孔 SW-26-124 见矿 8 米、金品位 6.05 克/吨，为该靶区 1987 年以来首个现代钻孔；Jackson 靶区 SW-26-111 见矿 7.70 米、金品位 1.45 克/吨。公司称已在 Jackson 圈定长约 1,200 米的含矿走廊，但整体未展现出较强的连续性，股价周一再跌 2.86%。',
                orig_title='Swanson results fall short despite 6.05-g/t gold highlight')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/en/newscontent/104143815-south-africa-moves-to-ban-cash-scrap-metal-sales-to-curb-infrastructure-theft',
                'SMM 国际站', '10-06',
                '南非拟立法禁止废旧金属现金交易，遏制基础设施盗窃',
                'SMM 国际站报道，南非正推动修订《二手商品法》，拟禁止废旧金属现金交易，以遏制非法贸易与基础设施破坏，相关损失每年约 450 亿兰特（约 25 亿美元）。新规要求经销商留存卖家信息并改用电子支付、逐笔登记，回收商须记录拾荒者姓名与身份证号；无合法永久居留权的外籍人士将被吊销交易牌照，黄金与铬一并纳入管理。',
                orig_title='South Africa Moves to Ban Cash Scrap Metal Sales to Curb Infrastructure Theft')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.mining.com/silver-shortage-could-flip-to-surplus-in-2027-deutsche',
                'MINING.COM', '10-06',
                '德意志银行：白银短缺或于 2027 年转为供应过剩',
                'MINING.COM 报道，德意志银行最新报告认为，白银库存上升叠加工业需求走弱，最快 2027 年出现供应过剩。金属研究主管 Daniel Ghali 预计 2027 年二季度现货银均价约 70 美元/盎司，低于 2026 年上半年水平，并称"白银稀缺性峰值已过"。现货银周一报 60.99 美元/盎司，年内累计下跌约 14%，但同比仍高约 26%。',
                orig_title='Silver shortage could flip to surplus in 2027: Deutsche')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104143819-smm-chromium-flash-global-chrome-ore-departures-fall-274-wow-to-642500-mt-maputo-rebounds',
                'SMM 国际站', '10-06',
                'SMM：全球铬矿发运量周环比降 2.74%，马普托港回升',
                'SMM 国际站数据显示，截至 10 月 2 日当周全球铬矿发运量 64.25 万吨，周环比下降 2.74%。马普托港发运量由 34.02 万吨升至 48.88 万吨、增长 43.68%，占比从约 51.5% 回升至约 76%；理查兹湾港由 22.78 万吨降至 9.57 万吨、下降 57.99%，梅尔辛港下降 31.52% 至 5.80 万吨，贝拉港连续第四周无发运。',
                orig_title='[SMM Chromium Flash] Global Chrome Ore Departures Fall 2.74% WoW to 642,500 mt, Maputo Rebounds')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104143638-smm-nickel-flash-news-unrest-at-pt-askon-in-morowali-raises-concerns',
                'SMM 国际站', '10-06',
                '印尼莫罗瓦利 PT Askon 发生骚乱，镍矿物流一度受阻',
                'SMM 国际站报道，10 月 2 日印尼中苏拉威西省莫罗瓦利县 Matarape 村因采矿扬尘与环境影响引发的抗议升级为骚乱，PT Astima Konstruksi（PT Askon）多台车辆与挖掘机被烧，运矿道路与码头通行受阻，警方随后撤离现场中方人员。截至 10 月 5 日尚无具体镍矿停产或减产的确证消息，后续需关注运输恢复与镍矿供应影响。',
                orig_title='[SMM Nickel Flash News] Unrest at PT Askon in Morowali Raises Concerns')),

    (CAT_HY, ni('https://www.mining.com/westwin-elements-to-build-502m-nickel-refinery-in-mississippi',
                'MINING.COM', '10-06',
                'Westwin 拟投 5.02 亿美元在密西西比建一级镍精炼厂',
                'MINING.COM 报道，Westwin Elements 宣布未来五年投入 5.02 亿美元，在密西西比州纳奇兹 Belwood 工业区建设商业化一级镍精炼厂。一期规划年产一级镍 1.8 万吨，目标 2029 年投产；公司已完成银行级可行性研究并签下长期场地租约，原料与包销协议均已落实。其俄克拉荷马州劳顿的 20 吨/年示范厂此前已多次产出合格一级镍粉。',
                orig_title='Westwin Elements to build $502M nickel refinery in Mississippi')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/barrick-secures-15-year-north-mara-mining-licences-in-tanzania',
                'MINING.COM', '10-06',
                '巴里克坦桑尼亚 North Mara 金矿采矿证获续期 15 年',
                'MINING.COM 报道，坦桑尼亚将巴里克矿业 North Mara 金矿的采矿许可证续期 15 年。该矿为露天与地下联合开采，位于多多马西北约 540 公里，巴里克持股 84%、坦桑尼亚政府持股 16%，去年权益产量 24.9 万盎司。续期消除矿权期限风险后，公司需扭转上半年产量同比下滑 47%（至 6.8 万盎司）的局面，并达成 2026 年 20 万~23 万盎司权益产量指引。',
                orig_title='Barrick secures 15-year North Mara mining licences in Tanzania')),

    (CAT_GJ, ni('https://www.mining.com/greenland-government-approves-tanbreez-mine-plan',
                'MINING.COM', '10-05',
                '格陵兰政府批准 Tanbreez 稀土矿开采与闭坑方案',
                'MINING.COM 报道，Critical Metals（纳斯达克：CRML）位于格陵兰南部的 Tanbreez 稀土项目开采与闭坑方案获格陵兰政府批准，为开工建设扫清关键障碍。该项目属中国以外规模较大的未开发重稀土项目之一，2025 年 3 月初步经济评估给出税后净现值 21 亿美元（15% 折现率）、初始资本开支 2.9 亿美元。消息公布后公司股价周一上涨 4.4% 至 7.34 美元。',
                orig_title='Greenland government approves Tanbreez rare earth mine plan')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104143858-what-could-a-cobre-panam',
                'SMM 国际站', '10-06',
                'SMM 分析：Cobre Panamá 若复产对全球铜供应意味着什么',
                'SMM 国际站分析指出，巴拿马政府委员会 9 月 30 日建议与第一量子就 Cobre Panamá 新运营框架启动正式谈判，令这座全球大型铜矿恢复采矿的前景再度升温。该矿 2023 年产量 33.09 万吨、约占全球产量 1%；目前仅恢复库存矿石加工，采矿仍处停滞。任何复产大概率分阶段推进，时点取决于谈判进展、法律条件与作业重启。',
                orig_title='What Could a Cobre Panamá Restart Mean for Global Copper Supply?')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104143850-smm-news-brazil-regulator-orders-partial-halt-at-sigma-lithium-mine-over-imminent-risk',
                'SMM 国际站', '10-06',
                '巴西监管机构以"紧迫风险"为由要求 Sigma 锂矿部分停产',
                'SMM 国际站报道，10 月 2 日 Sigma Lithium 暂停其巴西唯一在产资产 Grota do Cirilo 的全部采矿与工业活动，等待联邦上诉法院就其环境许可初步禁令作出裁定。巴西国家矿业局此前已下令暂停北坑东帮采矿。停产期间精矿产出中止、锂细料销售继续；公司将 24 万吨的 12 个月产量指引推迟三个月，维持 2027 财年 33 万吨精矿目标。',
                orig_title="Brazil regulator orders partial halt at Sigma Lithium mine over 'imminent risk'")),

    (CAT_GJ, ni('https://www.mining.com/rio-tinto-founders-factory-back-five-mining-startups',
                'MINING.COM', '10-05',
                '力拓与 Founders Factory 投资五家矿业初创企业',
                'MINING.COM 报道，力拓与 Founders Factory 通过矿业科技加速器投资五家初创企业，方向覆盖矿产勘查、地灾监测与金属加工，入选者从 500 多份申请中选出，为该项目第五期（为期四个月）。加速器将协助其对接澳大利亚、美国与加拿大的政府合作方及银行与资本市场；此前参与的企业中约三分之二已在力拓西澳矿山完成技术试验。',
                orig_title='Rio Tinto, Founders Factory back five mining startups')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104143847-smm-news-eramet-plans-5041-million-argentina-lithium-expansion',
                'SMM 国际站', '10-06',
                '埃赫曼筹划阿根廷锂项目扩建，投资规模约 5.041 亿美元',
                'SMM 国际站报道，10 月 2 日埃赫曼（Eramet）考虑对其阿根廷 Centenario-Ratones 锂项目进行 3.5 亿美元棕地扩建，新增碳酸锂当量产能 1.1 万吨/年（原文标题口径合计 5.041 亿美元）。最终投资决定或于 2027 年底作出，详细工程设计正在进行；项目 6 月已达铭牌产能的 90%，公司计划申请纳入阿根廷大型投资激励制度（RIGI）。',
                orig_title='[SMM News] Eramet plans $504.1 million Argentina lithium expansion')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104143844-smm-news-liontown-lifts-fy27-capex-guidance-by-nearly-35-after-approving-lithium-mine-expansion',
                'SMM 国际站', '10-06',
                'Liontown 批准西澳锂矿扩建，上调 2027 财年资本开支指引近 35%',
                'SMM 国际站报道，9 月 30 日 Liontown Resources 批准对西澳 Kathleen Valley 锂矿 3.89 亿澳元（约 2.7168 亿美元）的扩建。公司将 2027 财年资本开支指引由 3.20 亿~3.70 亿澳元上调至 4.35 亿~4.95 亿澳元，中值增幅约 35%，其中含 1.75 亿~1.95 亿澳元扩建资本。扩建预计自 2030 财年起把锂辉石精矿年均产量提升至约 78 万吨，2027 财年产量指引维持 39 万~44 万吨不变。',
                orig_title='[SMM News] Liontown lifts FY27 capex guidance by nearly 35% after approving lithium mine expansion')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104143842-vedanta-plans-23-billion-expansion-in-india-and-saudi-arabia-and-advances-tuticorin-smelter-restart',
                'SMM 国际站', '10-06',
                '韦丹塔拟投 23 亿美元扩产，并推进 Tuticorin 冶炼厂复产',
                'SMM 国际站报道，韦丹塔铜业计划未来三至四年在印度与沙特投入 23 亿美元，目标 2030 年铜年产量超 100 万吨。其中约 20 亿美元投向沙特铜矿、冶炼与铜杆项目，沙特铜冶炼厂投资决定预计本季度作出。公司同时寻求重启 2018 年起停产的印度 Tuticorin 铜冶炼厂，预计三个月内获法院裁决，若获批将投 2.5 亿美元改造、8 至 9 个月内复产，年产能 25 万吨。',
                orig_title='Vedanta Plans $2.3 Billion Expansion in India and Saudi Arabia, and Advances Tuticorin Smelter Restart')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104143846-smm-news-prairie-lithium-garners-c63m-federal-canadian-funding-to-reach-initial-production',
                'SMM 国际站', '10-06',
                'Prairie Lithium 获加拿大联邦 630 万加元融资',
                'SMM 国际站报道，Prairie Lithium 通过加拿大草原经济发展署"扩大规模与生产率计划"获得 630 万加元联邦融资，用于其萨斯喀彻温省项目一期生产，包括商业化直接提锂（DLE）装置的配套系统，该笔资金 2029 年起免息偿还。一期目标从油田卤水年产 150 吨碳酸锂当量（以氯化锂计），全部产量已由 Hydro Lithium 包销，首批卤水预计 2026 年四季度产出。',
                orig_title='[SMM News] Prairie Lithium garners C$6.3m federal Canadian funding to reach initial production')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104143845-smm-flash-gotion-and-volkswagens-powerco-cross-invest-in-european-lfp-capacity-morocco-cathode-plant-included',
                'SMM 国际站', '10-06',
                '国轩高科与大众 PowerCo 交叉投资欧洲磷酸铁锂产能',
                'SMM 国际站报道，9 月 28 日国轩高科将投资 11 亿欧元（约 12.5 亿美元）取得大众 PowerCo 西班牙瓦伦西亚工厂 49% 股权，该厂将成为欧洲磷酸铁锂（LFP）电池生产基地，PowerCo 保留多数股权；同时 PowerCo 将投资 4.7 亿欧元，分别取得国轩高科斯洛伐克 Šurany 电芯工厂与摩洛哥肯尼特拉正极材料工厂各 49% 股权。双方称此举属共建欧洲电池供应链计划的一部分。',
                orig_title="[SMM Flash] Gotion and Volkswagen's PowerCo cross-invest in European LFP capacity; Morocco cathode plant included")),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104143849-smm-news-lithium-argentina-outlines-phased-expansion-plan-for-cauchari-olaroz',
                'SMM 国际站', '10-06',
                'Lithium Argentina 确认 Cauchari-Olaroz 盐湖二期扩建',
                'SMM 国际站报道，Lithium Argentina 确认阿根廷 Cauchari-Olaroz 盐湖项目二期扩建，新增 4.5 万吨/年碳酸锂产能、总产能提升至 8.5 万吨/年；其中首个 1 万吨/年吸附法直接提锂（DLE）模块预计 2028 年投产。按碳酸锂 1.8 万美元/吨、运营成本 5,006 美元/吨测算，税后净现值 31 亿美元、内部收益率 28.5%；二期总投资 10 亿美元，新增供应自 2028 年起释放。',
                orig_title='[SMM News] Lithium Argentina outlines phased expansion plan for Cauchari-Olaroz')),

    (CAT_MA, ni('https://www.mining.com/millennial-potash-targets-2029-production-as-us-backed-gabon-project-advances',
                'MINING.COM', '10-05',
                'Millennial Potash 加蓬 Banio 钾盐项目目标 2029 年投产',
                'MINING.COM 报道，加拿大开发商 Millennial Potash 目标 2029 年在其加蓬西南部 Banio 钾盐项目投产，目前正推进可行性研究，预计今年底完成、2027 年初或作出最终投资决定。公司首席执行官表示，研究正评估溶解采矿法，并可能考虑大于初步经济评估所设 80 万吨/年的规模；美国国际开发金融公司（DFC）已为可研提供 300 万美元并表达建设融资兴趣。',
                orig_title='Millennial Potash targets 2029 production as US-backed Gabon project advances')),

    (CAT_MA, ni('https://www.mining.com/surge-battery-boosts-returns-cuts-costs-for-nevada-lithium-project',
                'MINING.COM', '10-05',
                'Surge Battery 更新内华达锂项目可研，回报提升、成本下降',
                'MINING.COM 报道，Surge Battery Metals 公布内华达 North 锂项目预可行性研究：按 8% 折现率与 2.4 万美元/吨碳酸锂当量价格，税后净现值 98.1 亿美元、内部收益率 24%、税后回收期 4.2 年。一期初始资本开支 27.7 亿美元，二期再投 23.5 亿美元；较 2025 年 6 月初步经济评估，运营成本下降约 10%（由 5,243 美元/吨起算），回收率由 82.8% 提升至 84.9%，年均产量增加约 7%。',
                orig_title='Surge Battery boosts returns, cuts costs for Nevada lithium project')),

    # ── 💼 矿权交易（仅入 rightsSection 数据层，不进主列表） ───
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
