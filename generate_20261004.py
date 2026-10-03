# -*- coding: utf-8 -*-
"""
生成 2026-10-04 矿业资讯速览 index.html（周日 · 国庆假期第 4 天）
- 09-30 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-02）回补历史条目
- 换入 10-03 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-30 收盘（现算）
  + LME 卡片=走势图末点口径 10-02 收盘（周日电子盘未收盘），
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

REPORT = '2026-10-04'
GRAB = '2026-10-04'
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
                         r'\g<1>2026年10月04日 星期日', html)
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
    (CAT_ZK, ni('https://www.ccmn.cn/news/ZX018/202609/e7e813b4124e4b63be39f4b79e4acc59.html',
                '长江有色金属网', '09-29',
                '大中矿业加达锂矿新增备案碳酸锂当量 104.68 万吨',
                '长江有色金属网报道，大中矿业 9 月 28 日公告，旗下四川马尔康加达锂矿首采区外围（119~167 线）新增备案氧化锂矿物量 42.38 万吨、平均品位 1.26%，折合碳酸锂当量约 104.68 万吨；叠加首采区此前已备案的 60.09 万吨氧化锂，加达锂矿累计氧化锂资源量突破百万吨，正式达到超大型锂矿床规模，探矿权范围内尚有约 15 平方公里待开展系统勘探。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.cgs.gov.cn/ywdt/dwdt/202609/t20260911_868329.html',
                '中国地质调查局', '09-11',
                '绿色矿山建设规范系列国家标准 10 月 1 日起实施',
                '中国地质调查局消息，国家市场监督管理总局（国家标准化管理委员会）批准发布 10 项《绿色矿山建设规范》系列国家标准，中国地质科学院郑州矿产综合利用研究所牵头编制 9 项、参与编制 1 项，将于 2026 年 10 月 1 日起正式实施。标准覆盖煤炭、陆上油气田、黑色金属、有色金属、化工、非金属、黄金、砂石、水泥用灰岩、地热矿泉水等主要矿产矿山，围绕资源开采、资源综合利用、绿色低碳、生态修复、科技创新与规范管理、矿区环境六个方面提出差异化要求，适用于新建、改扩建和在产矿山的全生命周期。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104143238-smm-flash-newsindonesias-hma-nickel-further-decreased-in-first-period-of-october',
                'SMM 国际站', '10-01',
                '印尼 10 月上半月镍矿基准价（HMA）环比下调 2.25%',
                'SMM 国际站报道，印尼能源与矿产资源部（ESDM）发布 2026 年 10 月上半月镍矿基准价（HMA）：镍价 16,322.67 美元/吨，较 9 月下半月的 16,698.00 美元/吨下调 375.33 美元、降幅 2.25%；同期钴 HMA 为 41,047.33 美元/吨，铁矿石 HMA 为 1.45 美元/吨，铬矿 HMA 为 6.37 美元/吨。',
                orig_title="[SMM Flash News] Indonesia's HMA Nickel Further Decreased in First Period of October")),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474353',
                '中国有色金属报', '09-29',
                '8 月锂行业运行情况：碳酸锂价格月内上涨约 10.7%',
                '中国有色金属报发布 8 月锂行业运行情况：电池级碳酸锂价格由月初 14.05 万元/吨涨至月末 15.55 万元/吨、涨幅 10.7%，工业级由 13.75 万元/吨涨至 15.25 万元/吨、涨幅 10.9%，氢氧化锂由 13.05 万元/吨涨至 14.55 万元/吨、涨幅 11.5%；主力合约收盘价由 13.89 万元/吨涨至 16.10 万元/吨。上涨主因部分企业集中停产检修、津巴布韦锂矿到港量不及预期，叠加下游电池排产超预期、储能与动力电池同步拉动需求。')),

    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0929/62105.html',
                '中国有色金属工业协会', '09-29',
                '8 月锆铪市场回顾：锆英砂进口环比降逾三成',
                '中国有色金属工业协会发布 8 月锆铪市场回顾：7 月我国锆英砂进口量 18.7 万吨，同比下降 3.61%、环比下降 31.11%，1—7 月累计 133 万吨、同比下降 2.95%；7 月氧氯化锆出口量 4,783 吨，同比下降 19.26%、环比下降 5.39%，1—7 月累计 34,914.6 吨、同比增长 1.09%；7 月其他未锻轧锆及粉末进口量 1,448 千克，同比增长 74.88%。')),

    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0929/62108.html',
                '中国有色金属工业协会', '09-29',
                '美联储“鹰派”加息落地，金价不跌反涨',
                '中国有色金属报分析文章指出，9 月美联储 FOMC 会议全票通过加息 25 个基点并释放“鹰派”信号，但加息落地后市场未遵循传统利空逻辑，美债收益率回落、金价快速探底企稳，呈“利空出尽”特征。文章认为，黄金定价逻辑正由实际利率锚定的周期敏感型资产，向美债债务风险锚定的信用对冲工具转型，最悲观的“鹰派”情景已逐步被计价、空头动能持续衰减。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/104143343',
                '上海有色网', '10-02',
                '智利 Codelco 旗下 Radomiro Tomic 铜矿因事故暂停部分作业',
                '上海有色网援引文华财经消息，智利矿业监管机构 Sernageomin 表示，智利国家铜业公司（Codelco）旗下 Radomiro Tomic 铜矿发生事故；Codelco 证实一名机械师死亡，并已暂停发生事故的破碎和物料处理区作业。初步信息显示事故发生在上午 8:50 左右，当时该工人正在该区域进行维护工作。近几周，必和必拓位于智利北部的埃斯康迪达矿在发生一名工人死亡事故后也曾暂停作业。')),

    (CAT_HY, ni('https://www.mining.com/freeports-grasberg-copper-mill-reaches-67-after-mudslide',
                'MINING.COM', '10-03',
                'Freeport 旗下 Grasberg 铜选厂泥石流后恢复至 67%',
                'MINING.COM 报道，自由港麦克莫兰（Freeport-McMoRan）旗下印尼 Grasberg 铜矿选厂在泥石流事故后已恢复至 67% 处理能力，公司预计明年底接近满产。BMO 资本市场预计公司三季度调整后盈利 30.9 亿美元、高于分析师普遍预期的 30 亿美元；国际业务走强部分抵消了美国本土作业受局部洪水、停电和强风影响导致的开工率下降，BMO 认为上述扰动属暂时性。',
                orig_title="Freeport's Grasberg copper mill reaches 67% after mudslide")),

    (CAT_HY, ni('https://www.mining.com/web/glencore-says-trading-profits-will-top-5-billion-this-year/',
                'MINING.COM', '10-02',
                '嘉能可预计今年大宗商品交易利润超 50 亿美元',
                'MINING.COM 援引彭博社报道，嘉能可（Glencore）预计今年大宗商品交易利润将超过 50 亿美元，为其 2022 年创纪录以来的最佳水平，主要受原油、成品油、天然气和运费市场明显重塑驱动；伊朗战争引发的能源价格剧烈波动与霍尔木兹海峡物流中断推高运费，铜和煤炭价格上涨亦构成额外利好。公司预计 2027 年起营销部门年利润约 28 亿至 42 亿美元，上半年核心盈利 101 亿美元、同比增 86%。',
                orig_title='Glencore says trading profits will top $5 billion this year')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474388',
                '中国有色金属报', '09-30',
                '宝信软件中标金钼集团智能化工厂建设 EPC 项目',
                '中国有色金属报报道，宝信软件成功签约金堆城钼业集团（金钼集团）智能化工厂建设 EPC 项目，将为金钼集团全新钼基特种材料产线搭建全流程数字化智能体系，覆盖 IT 基础设施、集中管控、智慧安防、智能物流、工艺 AI 优化、生产运营、绿色环保、数字孪生八大板块。金钼集团是国内钼行业龙头，拥有钼矿采选、冶炼、新材料深加工完整产业链。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/pension-funds-use-gold-as-bond-hedge-weakens',
                'MINING.COM', '10-03',
                '债券对冲弱化，养老金基金转向直接持有黄金',
                'MINING.COM 报道，因担忧矿业股票的商品价格波动，部分养老金基金转而直接持有黄金以获取黄金板块敞口，而不必承担持有个别矿业公司的风险。案例分析显示，不同基金的黄金配置目标并不统一，取决于资金状况、治理结构、风险预算与投资理念；其共同特征是持续性——疫情期间建立的头寸五六年后仍在持有。',
                orig_title='Pension funds use gold as bond hedge weakens')),

    (CAT_GJ, ni('https://www.mining.com/web/colombia-reports-expansion-of-mostly-illegal-alluvial-gold-mining/',
                'MINING.COM', '10-02',
                '哥伦比亚非法冲积金矿开采面积再扩 5,100 公顷',
                'MINING.COM 援引路透社报道，联合国毒品和犯罪问题办公室（UNODC）与哥伦比亚政府的报告显示，该国冲积型金矿开采面积较 2024 年增加 5,100 公顷，为连续第三年增长；75% 的冲积金产量属非法，21% 持有技术或环境许可，4% 正在合法化。去年 32 个省中近半出现冲积金开采，61% 的增量位于非裔哥伦比亚人土地，非法采金是继贩毒之后非法武装团体的第二大资金来源。',
                orig_title='Colombia reports expansion of mostly illegal alluvial gold mining')),

    (CAT_GJ, ni('https://www.mining.com/web/half-a-million-miners-stand-between-bolivia-and-a-critical-minerals-rush/',
                'MINING.COM', '10-02',
                '玻利维亚推进矿业改革，50 万合作社矿工成关键变量',
                'MINING.COM 报道，玻利维亚约 50 万合作社矿工及其代表组织是该国关键矿产开发的重要政治力量。随着总统 Paz 推动改革，行业组织呼吁政府加强矿权保护、加快审批并提供法律确定性以吸引大型投资；私营矿业协会人士指出，金属价格高企往往助长非正规开采。已有企业重新关注玻利维亚，San Cristobal Mining 正评估一项可使白银产量在未来数年翻倍以上的扩张。',
                orig_title='Half a million miners stand between Bolivia and a critical minerals rush')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104143357-vedanta-plans-23-billion-copper-expansion-as-restart-of-400000-tonne-tuticorin-smelter-returns-to-agenda',
                'SMM 国际站', '10-02',
                'Vedanta 拟投资约 23 亿美元扩铜，Tuticorin 冶炼厂重启重回议程',
                'SMM 国际站报道，Vedanta 计划未来三至四年投资约 23 亿美元，到 2030 年将铜产量提升至 100 万吨以上，目标在印度和沙特各约 50 万吨。其中约 20 亿美元用于沙特一体化业务（涵盖采矿、冶炼与铜杆生产），沙特铜杆厂接近投产，新冶炼厂谈判已深入、投资决定预计本季度内作出。公司还重新推进自 2018 年起停产的 40 万吨/年 Tuticorin 铜冶炼厂重启，预计法院将在约三个月内就其“绿色铜”提案作出裁决。',
                orig_title='Vedanta Plans $2.3 Billion Copper Expansion as Restart of 400,000-Tonne Tuticorin Smelter Returns to Agenda')),

    (CAT_MA, ni('https://www.mining.com/web/china-demands-copper-supply-commitments-for-anglo-teck-merger-approval-sources-say/',
                'MINING.COM', '10-02',
                '中国要求 Anglo-Teck 合并作出铜供应承诺',
                'MINING.COM 援引路透社报道，英美资源（Anglo American）与泰克资源（Teck Resources）合并案除中国外已获所有监管辖区批准，中国国家市场监督管理总局（SAMR）在结构性审查中要求两公司作出铜供应承诺。合并后两公司约控制全球 5% 铜供应，低于 10% 至 15% 的竞争门槛，现阶段补救措施未涉及资产出售。两公司预计 2027 年 3 月前完成交易；分析师认为，若 Anglo Teck 未精炼铜被限制进入公开市场，可能加速部分西方冶炼厂关闭并推动定价转向指数挂钩现货价。',
                orig_title='China demands copper supply commitments for Anglo-Teck merger approval, sources say')),

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
