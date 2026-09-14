# -*- coding: utf-8 -*-
"""
生成 2026-09-15 矿业资讯速览 index.html
- 09-14 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-17）回补历史条目
- 换入 09-15 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所 09-14 收盘 + LME 09-14 收盘，全部由 price_history_detail.json /
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


SITE_NAME = '矿业资讯速览'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()
_ORIG_SIZE = len(html)

REPORT = '2026-09-15'
GRAB = '2026-09-15'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
# 站点名固定「矿业资讯速览」，标题统一写成「矿业资讯速览 · YYYY-MM-DD」。
# 用宽松匹配吃掉落点前的任意旧标题，可覆盖三种历史写法：
#   纯日期（2026-09-07~09-12，站名丢失）／「站名 日期」（09-04~09-06）／「站名 · 日期」。
# 2026-09-12 修复：此前 09-07 起写成纯日期，浏览器标签页只剩一个光秃秃的日期，看不出是什么站。
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月15日 星期二', html)
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

# ============ 4. 今日新增条目（09-14~09-15 抓取，均逐源核实真实发布日期） ============
# 本日 cnmn 列表日期仍失真，逐条抓详情页核实：473660 实为 09-01、473462 实为 08-25、
# 473926 实为 09-11、473839（镁行业标准）实为 09-08 —— 均非当日稿，不予收录。
new_items = [
    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0914/61981.html',
                '中国有色金属工业协会', '09-14',
                '矿业国际合作部长论坛举行 发布《矿业绿色发展天津宣言》',
                '9 月 10 日，矿业国际合作部长论坛暨 2026 中国国际矿业大会开幕式在天津举行，来自全球 60 个国家和国际组织的代表参会，论坛发布《矿业绿色发展天津宣言》。宣言围绕践行绿色发展理念、提高资源利用效率、应对气候变化、绿色低碳技术应用、构筑稳定可持续产业链等 10 个方面提出倡议。会议透露，我国已建成绿色矿山 5000 多家；本届大会 9 月 10 日至 12 日举行，吸引 650 多家国内外企业参会参展。')),
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260914_2938258.html',
                '自然资源部', '09-14',
                '2026 中国国际矿业大会闭幕 达成多项地质矿产合作共识',
                '9 月 12 日，2026（第二十八届）中国国际矿业大会在天津闭幕，为期 3 天的大会共有来自全球 60 个国家和国际组织的代表以及 3.1 万名参会者。大会期间自然资源部领导与多国矿业部长举行多场双边会见，围绕基础地质调查、地质编图、地球化学等领域务实合作深入交换意见，并就深化地质矿产调查合作、加强绿色智能矿业技术研发应用、共享绿色矿山建设标准与实践经验等达成多项共识。')),

    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://news.smm.cn/news/104113820',
                '上海有色网', '09-14',
                '艾芬豪加快刚果（金）马库库铜矿 资源量增长 30% 至约 1200 万吨',
                '艾芬豪矿业正加快实施其刚果（金）马库库（Makoko）铜矿工作计划，目前铜金属资源量约 1200 万吨，较 2025 年估算值增长 30%。其中推定矿石资源量 4200 万吨、铜品位 2.66%，推测矿石资源量 6.12 亿吨、品位 1.8%。公司 2026 年已完成约 6 万米钻探（尚未纳入本次估算），计划 2027 年一季度启动马库库概略研究，并考虑浅坑与地下联合采矿方案以缩短投产时间。',
                )),
    (CAT_ZK, ni('https://news.smm.cn/news/104113821',
                '上海有色网', '09-14',
                '摩洛哥布马丁多金属矿经济性提升 税后净现值增至 35 亿美元',
                '阿雅金银公司（Aya Gold & Silver）更新摩洛哥布马丁（Boumadine）项目初步经济评价：因上调金银价格假设，税后净现值增长一倍至 35 亿美元，内部收益率 93%、回报期 0.7 年，初步投资 4.63 亿美元（高于 2025 年估算的 4.46 亿美元），矿山可采年限由 11 年扩大至 14 年。矿山计划品位下调至金 1.77 克/吨、银 63.5 克/吨、锌 1.37%、铅 0.58%；公司正实施 40 万米钻探计划，拟 2027 年下半年开展可行性研究。',
                )),
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104113784-nicico-puts-irans-copper-ore-resources-at-245bn-tonnes-exploration-drilling-nears-200000-metres',
                'SMM 国际站', '09-14',
                '伊朗 NICICO：铜矿石资源量增至 245 亿吨 勘查钻探近 20 万米',
                '伊朗国家铜业公司（NICICO）称，该国铜矿石地质资源量由年初的 222 亿吨增至 245 亿吨、增长 10.6%，可采（设计）储量由 168 亿吨增至 182 亿吨。本年度前五个月完成勘查钻探 198,462 米，约为全年 50 万米目标的 40%；Miduk 矿可采储量增长 123% 至 17.7 亿吨。',
                orig_title="NICICO Puts Iran's Copper Ore Resources at 24.5bn Tonnes; Exploration Drilling Nears 200,000 Metres")),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104113561',
                '上海有色网', '09-14',
                'SMM 日评：金属近全线下跌 沪锡跌 3.81% 领跌 沪铅跌逾 2%',
                '9 月 14 日国内基本金属集体下跌：沪锡以 3.81% 的跌幅领跌，沪铅跌 2.07%、沪锌跌 1.94%、沪镍跌 1.55%，其余金属跌幅均在 1% 以内；氧化铝主连跌 1.76%，碳酸锂主连跌 1.21%。外盘同步走弱，伦铅跌 1.11%、伦锡跌 1.21%；贵金属方面 COMEX 黄金跌 1.02%、COMEX 白银跌 1.52%。',
                )),
    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0914/61987.html',
                '中国有色金属工业协会', '09-14',
                '中东供应风险溢价重定价 机构看多铝价重回高位',
                '美以伊冲突再度升级、霍尔木兹海峡通航受阻，中东铝供应风险溢价重新成为市场定价核心变量。中东地区电解铝建成产能约 700 万吨、占全球总产能近一成，氧化铝自给率仅约 34%，已确认减产产能高达 271 万吨、约占全球供给的 3%~4%；阿联酋环球铝业塔维拉厂区一度全线停产，目前恢复约 25% 产能。分析认为当前铜铝比值已升至 4.5 的高位（长期均衡约 3.5），铝代铜替代逻辑增强，铝价中枢有望在比价修复中进一步抬升。',
                )),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473967',
                '中国有色金属报', '09-14',
                '8 月中国铅锌产业景气指数回升至 56.8 先行指数大幅上升',
                '中国铅锌产业月度景气指数监测结果显示，8 月中国铅锌产业月度景气指数为 56.8，较 7 月回升 0.8 个点，结束此前连续 2 个月回落态势，仍处「正常」区间运行；先行指数为 77.6，较 7 月大幅上升 9.8 个点。分项看 LME 铅锌价格指数为 74.6、较 7 月上升 9.4 个点，铅酸蓄电池指数回升 17.2 个点。',
                )),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0914/61980.html',
                '中国有色金属工业协会', '09-14',
                '锡业股份上半年营收 316 亿元 扣非净利 19.46 亿元',
                '锡业股份上半年实现营业收入 316 亿元、同比增长 49.68%，扣非归母净利润 19.46 亿元、同比增长 49.30%；上半年有色金属总产量 19.34 万吨，完成进度计划 109.9%。资源端公司完成赤峰大井子锡业项目股权收购、大井子锡业顺利复工复产，北方资源基地建设取得关键突破，精矿金属总量完成进度计划 101.6%。',
                )),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0914/61989.html',
                '中国有色金属工业协会', '09-14',
                '陕西有色天策百吨级中间相沥青基碳纤维产线投产',
                '陕西有色金属集团权属企业陕西有色天策新材料科技有限公司百吨级中间相沥青基碳纤维产线正式投产，补齐国内高端沥青基碳纤维产业化关键短板。沥青基碳纤维以石油渣油或煤焦油为原料，具备超高模量、高导热和近零热膨胀系数等特性，广泛用于航天航空、核工业、高端电子散热等战略领域，此前长期受出口管制；目前全球仅 3 家企业掌握规模化生产能力。',
                )),
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-09-15/1225563600.PDF',
                '巨潮资讯网', '09-15',
                '赤天化子公司安佳矿业花秋二矿扩建项目获批复',
                '赤天化（600227）公告，其全资子公司安佳矿业花秋二矿扩建项目已获得主管部门批复，项目扩建获准推进，具体批复内容与产能规模详见公司公告原文（巨潮资讯网 PDF）。',
                embed='pdf')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://news.smm.cn/news/104113791',
                '上海有色网', '09-14',
                '几内亚与嘉能可洽谈氧化铝及能源投资 铝土矿包销协议已落地',
                '几内亚矿业部长 Bouna Sylla 表示，继上周签署铝土矿销售协议后，几内亚正与嘉能可（Glencore）探讨氧化铝冶炼、能源及其他战略性项目投资机会。几内亚国企 Nimba Mining 与嘉能可上周签署价值超 3 亿美元的铝土矿预付款包销协议，这家瑞士大宗商品巨头将在未来五年内每年销售 1,000 万至 1,200 万吨铝土矿。几内亚已于 2023 年超越澳大利亚成为全球最大铝土矿生产国。',
                )),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104113859-smm-news-chile-proposes-market-reform-to-boost-junior-mining-exploration',
                'SMM 国际站', '09-14',
                '智利拟推资本市场改革 支持初级矿业勘查并吸引外资',
                '智利政府提出资本市场改革方案，为初级勘查与创新企业设立专门投资框架，简化市场准入并降低早期锂及矿产勘查企业的运营成本。方案包含股票转让资本利得税豁免、绿地勘探费用核销等激励措施，符合条件的企业可不必进入国家证券登记册，改由指定保荐机构承担合规与信息披露职责。智利经济与矿业部长 Daniel Mas 表示，把勘查纳入资本市场有助于分散风险、吸引追求回报的投资资金。',
                orig_title='[SMM News] Chile proposes market reform to boost junior mining exploration')),
    (CAT_GJ, ni('https://news.smm.cn/news/104113819',
                '上海有色网', '09-14',
                '美能源部 7300 万美元资助建设四个矿业技术试验基地',
                '美国能源部关键矿产和能源创新办公室（CMEI）通过「未来矿产」计划选定四个项目，提供总计 7300 万美元资金，用于建立美国国内创新性矿业技术试验基地。入选方包括总部位于林奇堡的创新无线技术公司（IWT，在西弗吉尼亚州与科罗拉多州设点）、亚利桑那大学和密苏里大学理事会。项目将结合实际工况验证新一代数字化、互联及自动化采矿方案，并开展先进碎磨技术研究。',
                )),
    (CAT_GJ, ni('https://news.smm.cn/news/104113818',
                '上海有色网', '09-14',
                '刚果（金）推行地质资料分级访问 强化战略数据管控',
                '刚果（金）正加快地质填图、航空测量与历史资料数字化，建设关键矿产国家地质资料中心，并计划对数据实行分级服务：基础地质资料免费访问，更敏感的数据集收费。该国地质调查局（SGNC）局长透露，今年 1 月与西班牙 Xcalibur 公司签订 1.8 亿美元合同后，全国性地质填图正在推进，Xcalibur 项目正对 70 多万平方公里区域开展航空物探与数字化，执行至 2026 年底；SGNC 估计该国仅 20% 的面积做过系统勘探。',
                )),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('https://www.mining.com/us-government-secures-10-stake-in-trilogy-metals',
                'MINING.COM', '09-14',
                '美国政府以 3560 万美元入股 Trilogy Metals 获 10% 股权',
                '美国政府完成对 Trilogy Metals 的 3560 万美元投资，取得该公司 10% 股权，资金用于推进其位于阿拉斯加的北极（Arctic）铜锌项目及 Ambler 矿区通路建设。此举是美国政府降低关键矿产对华依赖的最新动作。',
                orig_title='US government secures 10% stake in Trilogy Metals')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-15/1225564431.PDF',
                '巨潮资讯网', '09-15',
                '焦作万方终止发行股份购买资产并撤回申请文件',
                '焦作万方（000612）公告，公司终止此前筹划的发行股份购买资产暨关联交易事项，并向监管机构撤回相关申请文件。同日公司披露将召开终止本次交易事项的投资者说明会，独立财务顾问亦出具核查意见（详见巨潮资讯网公告 PDF）。',
                embed='pdf')),

    # ---------- 💼 矿权交易 ----------
    (CAT_KQ, ni('http://static.cninfo.com.cn/finalpage/2026-09-15/1225563925.PDF',
                '巨潮资讯网', '09-15',
                '盛达资源子公司光大矿业完成采矿权延续登记',
                '盛达资源（000603）公告，其子公司光大矿业已完成采矿权延续登记。采矿权延续完成后，相关矿业权可依法继续持有，具体登记信息详见公司公告原文（巨潮资讯网 PDF）。',
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
