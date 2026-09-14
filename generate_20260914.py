# -*- coding: utf-8 -*-
"""
生成 2026-09-14 矿业新闻日报 index.html
- 09-13 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-16）回补历史条目
- 换入 09-14 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所 09-11 收盘（周一盘前）+ LME 09-11 收盘，全部由 price_history_detail.json /
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
    unit_class, UNIT_SHFE_GROUP, UNIT_LME_GROUP,
)
from functools import partial


SITE_NAME = '矿业新闻日报'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()
_ORIG_SIZE = len(html)

REPORT = '2026-09-14'
GRAB = '2026-09-14'
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
                         r'\g<1>2026年09月14日 星期一', html)
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

# ============ 4. 今日新增条目（09-14 抓取，均逐源核实） ============
new_items = [
    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104111528-alchemy-resources-starts-drilling-copper-gold-targets-at-yellow-mountain',
                'SMM 国际站', '09-11',
                'Alchemy 在新南威尔士 Yellow Mountain 启动铜金靶区反循环钻探',
                '​澳大利亚 Alchemy Resources 9 月 11 日公告，已在其新南威尔士州 Yellow Mountain 与 Overflow 项目启动反循环（RC）钻探，本轮勘查计划最多施工 15 个钻孔。Yellow Mountain 为 Alchemy 持股 80% 的项目，钻探将验证已知铜金及多金属矿化的延伸，并测试两个此前未钻探的物探靶区；以往钻探曾见到 113 米、铜当量品位 1.17% 的交段（含铜 0.33%、金 0.37 克/吨、银 24.3 克/吨、铅 0.86%、锌 1.23%）。本轮钻探旨在判断已知矿化系统是否延入新识别靶区，同时安排 Overflow 项目钻探。',
                orig_title='Alchemy Resources Starts Drilling Copper-Gold Targets at Yellow Mountain')),

    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202609/t20260911_2938173.html',
                '自然资源部', '09-11',
                '《关于规范矿业权管理有关事项的通知（征求意见稿）》公开征求意见 收到意见 279 条',
                '​自然资源部 9 月 11 日公告，为贯彻落实《矿产资源法》《矿产资源法实施条例》、规范矿业权管理、推动矿产资源合理开发利用和增储上产，该部起草的《关于规范矿业权管理有关事项的通知（征求意见稿）》已于 2026 年 8 月 24 日至 9 月 7 日向社会公开征求意见。意见征集期间共收到社会各界意见和建议 279 条，该部表示将认真研究并最大程度予以吸收采纳。')),
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260912_2938228.html',
                '自然资源部', '09-12',
                '两份矿业权威报告发布 我国 14 种矿产储量居世界第一',
                '​2026 中国国际矿业大会期间，《中国矿产资源报告 2026》与《全球矿业发展报告 2026》两份矿业权威报告发布。报告显示，我国矿产资源家底更为厚实，14 种矿产储量居世界第一。「十四五」以来新一轮找矿突破战略行动累计新发现矿产地大幅增加，铜、锂、稀土、金等重要矿产新增资源量显著提升，国内资源保障能力持续增强。（详见同日《中国矿产资源报告》摘编。）')),
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260911_2938171.html',
                '自然资源部', '09-11',
                '绿色勘查绿色矿山系列国家标准发布',
                '​2026 中国国际矿业大会期间，绿色勘查、绿色矿山系列国家标准集中发布，覆盖主要矿产类型与勘查—开发全流程关键环节，为绿色勘查技术方法、绿色矿山建设与评价提供统一依据。标准的发布标志着我国绿色矿业标准体系进一步完善，将推动矿产勘查开发全生命周期向绿色低碳转型。')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104103881-smm-analysis-lme-stocks-climb-while-backwardation-widens-whats-behind-zincs-apparent-paradox',
                'SMM 国际站', '09-08',
                'SMM：LME 锌库存回升与现货升水走阔并存 悖论背后是仓单集中',
                '​SMM 分析指出，8 月中旬以来 LME 官方锌库存（注册仓单加注销仓单）自 8 月 17 日的 86,500 吨低点回升至 9 月 4 日的 113,100 吨、累计增加 26,600 吨；但同期 LME 现货对三个月合约（0-3）的现货升水并未缓解，反而从 8 月 17 日的 82.88 美元/吨扩大到 9 月 4 日约 168.62 美元/吨。库存与升水同向走强，指向可用仓单集中度过高、可交割资源结构性偏紧，而非单纯的总量短缺。',
                orig_title="[SMM Analysis] LME Stocks Climb While Backwardation Widens — What's Behind Zinc's Apparent Paradox?")),
    (CAT_SC, ni('https://news.smm.cn/news/104086512',
                '上海有色网', '09-12',
                '期铜周线 6 月以来首次下跌 伦锡沪镍跌幅居前 氧化铝涨超 2%',
                '9 月 11 日 LME 三个月期铜收报 14,240 美元/吨附近，周线下跌、为 6 月以来首次，终结此前连续 10 周上涨；此前周四铜价触及 14,875 美元/吨纪录高位后单日回落 3.6%。基本金属普遍下跌，伦锡、沪镍跌幅居前；氧化铝逆势涨超 2%。市场聚焦美国关税政策走向与美联储偏鹰预期，贵金属同日夜盘跳水。')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104099346-august-copper-scrap-market-recap-widening-price-spread-muted-market-activity-and-invoice-constraints',
                'SMM 国际站', '09-06',
                '精废铜价差创历史极值 8 月末突破 5,000 元/吨',
                '​SMM 8 月再生铜市场回顾显示，2026 年 8 月精铜与废铜价差从月初的 3,455 元/吨扩大到月末的 5,000 元/吨以上，8 月 17 日一度冲高至 5,533 元/吨，达到历史极值区间；铜杆与再生铜杆价差亦在 1,150—2,260 元/吨高位波动。价差走阔压制再生铜杆开工与采购意愿，市场整体成交清淡，并叠加发票合规约束。',
                orig_title='August Copper Scrap Market Recap: Widening Price Spread, Muted Market Activity, and Invoice Constraints')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104111567-rio-tinto-secures-indigenous-consent-for-winu-copper-gold-project-in-western-australia',
                'SMM 国际站', '09-11',
                '力拓西澳 Winu 铜金项目获原住民同意 扫清开发障碍',
                '力拓（Rio Tinto）表示已就其西澳 Winu 铜金项目取得原住民同意，项目得以继续推进。公司与 Nyangumarta Warrarn 原住民机构（NWAC）建立长期伙伴关系，覆盖在 Nyangumarta 土地上开发该矿；协议建立在 2023 年签署的项目规划协议基础上，明确随规划推进双方的合作方式，包括避免对环境和原住民文化遗产造成影响的措施。',
                orig_title='Rio Tinto Secures Indigenous Consent for Winu Copper-Gold Project in Western Australia')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473843',
                '中国有色金属报', '09-08',
                '贵阳院攻克三水铝石矿利用关键技术 支撑海外矿源变绿色产能',
                '针对进口三水铝石矿大规模利用带来的工艺挑战，贵阳铝镁设计研究院有限公司自主攻关形成成套关键技术，已在多个大型氧化铝项目实现产业化应用。该技术为把海外矿源转化为稳定、绿色、高效的国内氧化铝产能提供支撑，助力铝产业链安全与低碳转型。',

                )),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473846',
                '中国有色金属报', '09-08',
                '箭猪坡矿区锑多金属矿储量核实报告通过自然资源部评审备案',
                '华锡有色公告，托管企业河池五吉箭猪坡矿业有限公司提出的矿产资源储量评审备案申请已通过自然资源部评审备案。据评审意见书，截至 2024 年 12 月 31 日，核实区（+500 米至 -300 米标高）保有矿石资源量 797.2 万吨，增幅 268.02%。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104111575-smm-flash-news-eu-may-formally-object-to-mmgs-500-million-acquisition-of-anglo-americans-brazilian-nickel-assets',
                'SMM 国际站', '09-12',
                '欧盟或正式反对五矿 5 亿美元收购英美资源巴西镍资产',
                'SMM 快讯称，欧盟可能正式对五矿资源（MMG）以 5 亿美元收购英美资源（Anglo American）巴西镍资产提出反对意见。该交易正面临欧盟并购审查程序，若正式反对成立，将成为中资企业海外关键矿产收购面临的又一监管阻力。',
                orig_title="[SMM Flash News] EU May Formally Object to MMG's $500 Million Acquisition of Anglo American's Brazilian Nickel Assets")),
    (CAT_GJ, ni('https://www.mining.com/investment-in-canadas-mining-sector-to-grow-with-global-demand-bmo',
                'MINING.COM', '09-13',
                'BMO：全球需求推动加拿大矿业投资增长',
                'BMO 全球市场最新研究指出，随着行业持续增长，加拿大矿业部门对投资者展现出可观潜力。报告认为在全球关键矿产需求上升背景下，加拿大矿业投资有望继续增长。（详情见 BMO 研究原文。）',
                orig_title="Investment in Canada's mining sector to grow with global demand, BMO")),
    (CAT_GJ, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473831',
                '中国有色金属报', '09-08',
                '智利与阿根廷推进跨边界铜矿开发 拟释放 207 亿美元投资',
                '为推动新一代铜矿项目开发，阿根廷和智利两国官员进行新一轮谈判，以重新履行 1997 年签署的《矿业融合互补条约》。会谈期间两国批准了维库尼亚、尼索安迪诺和费洛南矿业项目，这些矿床位于阿根廷圣胡安省与智利阿塔卡马大区交界处。智利矿业部长丹尼尔·马斯称，该制度框架有助于释放 207 亿美元的矿业项目投资，并将全球年铜产量增加 54 万吨。')),
    (CAT_GJ, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473780',
                '中国有色金属报', '09-07',
                '亚行推出「关键矿产到制造端」融资机制 重塑亚太供应链格局',
                '亚洲开发银行在乌兹别克斯坦举行的第 59 届年会上推出「关键矿产到制造端」融资伙伴关系机制，旨在推动亚太经济体从单纯矿产开采向本土加工、制造、回收等高附加值环节延伸，进而嵌入清洁能源、电池、电动汽车和数字技术等产业供应链，使资源国不仅出口原材料，更有望抓住相关产业、技术与就业价值。')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104111527-freeport-ceo-signals-likely-go-ahead-for-45-billion-bagdad-copper-expansion',
                'SMM 国际站', '09-11',
                '自由港 CEO 释放推进 45 亿美元 Bagdad 铜矿扩建信号',
                '自由港麦克莫兰（Freeport-McMoRan）CEO Kathleen Quirk 表示，公司预计将推进亚利桑那州 Bagdad 铜矿的拟议扩建，在正式投资决定前强化了对该项目的承诺。她 9 月 10 日在 Jefferies 全球工业会议上称，项目仍需董事会批准，但她预计公司将推进；扩建建设期约三年，预计不存在重大审批障碍。公司最新项目测算将 Bagdad 扩建资本开支上调至约 45 亿美元，较此前 35 亿美元估算高出约 30%，反映成本上升、范围调整与新增工程设计。',
                orig_title='Freeport CEO Signals Likely Go-Ahead for $4.5 Billion Bagdad Copper Expansion')),
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
# 每条摘要的数字须能在源文（候选池/月库）找到，防 LLM 抄错数字（如 113米看成别的）。
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
