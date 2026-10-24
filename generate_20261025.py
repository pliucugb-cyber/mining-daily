# -*- coding: utf-8 -*-
"""
生成 2026-10-25 矿业资讯速览 index.html（周日）
- 10-24 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-26）回补历史条目
- 换入 10-25 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-23 收盘 + LME 10-23 收盘（10-24/10-25 周末休市），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，本批新增由 tmp/add_rights_1025.py 注入）
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

REPORT = '2026-10-25'
GRAB = '2026-10-25'
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
                         r'\g<1>2026年10月25日 星期日', html)
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
    (CAT_ZK, ni('https://www.mining.com/new-found-gold-doubles-queensway-valuation-to-1-2b',
                'MINING.COM', '10-23',
                'New Found Gold 上调 Queensway 金矿估值至 12.3 亿美元，资源量增 38%',
                '纽芬兰 Queensway 金矿修订初步经济评价显示，税后净现值升至 17.3 亿加元（约 12.3 亿美元），较上年的 7.43 亿加元翻倍；探明加控制资源量增至 2,730 万吨、品位 2.19 克/吨、含金 192 万盎司，增幅 38%。按 3,600 美元/盎司金价测算，15 年年均产金 11.6 万盎司、2032 年峰值 19 万盎司，全维持成本 1,375 美元/盎司，税后内部收益率 126%，首批处理目标为 2027 年底。',
                orig_title='New Found Gold doubles Queensway valuation to $1.2B')),

    (CAT_ZK, ni('https://www.mining.com/kodal-targets-ghana-lithium-growth-beyond-mali-mine',
                'MINING.COM', '10-23',
                'Kodal 进军加纳锂矿，五年至少投入 1,300 万美元勘查',
                'Kodal Minerals 与 GH Geo-Consult 签署具约束力协议，以 30 万美元取得加纳东部省 Asamankese 锂矿项目 10% 初始权益，并可在 5 年内投入至少 1,300 万美元勘查后增至最高 80%。项目面积 156 平方公里，早期在 Amantra、Nfranta 靶区发现伟晶岩，岩屑样氧化锂品位最高 3.02%；公司计划以 Bougouni 矿山经营现金流而非新增股权融资支持勘查。',
                orig_title='Kodal targets Ghana lithium growth beyond Mali mine')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104172753',
                '上海有色网', '10-22',
                '新西兰终止对进口铝型材保障措施调查，不实施保障措施',
                '新西兰商业、创新和就业部 10 月 13 日公告，认定铝型材进口虽对国内产业造成损害，但未达到《2014 年贸易（保障措施）法》要求的严重损害标准，决定不实施保障措施并终止调查，涉案税号为 7604.21.00 00B 与 7604.29.09 00F。该调查于 2026 年 5 月 28 日发起，WTO 保障措施委员会已于 10 月 16 日通报。')),

    (CAT_ZC, ni('http://static.cninfo.com.cn/finalpage/2026-10-24/1225619667.PDF',
                '巨潮资讯网', '10-24',
                '中国稀土子公司超范围采矿案移送审查起诉，已缴罚款 396.16 万元',
                '中国稀土公告，控股子公司中稀（湖南）稀土开发有限公司收到江华瑶族自治县公安局《案件移送起诉告知书》，其非法采矿案已移送江华县人民检察院审查起诉。该公司因在江华稀土矿区超出采矿许可证范围北侧采出稀土氧化物 7.17 吨，于 2026 年 5 月 29 日被湖南省自然资源厅处罚，已完成整改并足额缴纳罚款 396.16 万元；公司初步判断不会对生产经营产生重大不利影响。',
                embed='pdf')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104176869',
                '上海有色网', '10-24',
                'ICSG：8 月全球精炼铜市场过剩 13.2 万吨，7 月为短缺 4.5 万吨',
                '国际铜业研究组织（ICSG）月度公报显示，2026 年 8 月全球精炼铜市场供应过剩 13.2 万吨，7 月为供应短缺 4.5 万吨；8 月精炼铜产量 247 万吨、消费量 234 万吨。1 至 8 月累计过剩 21.8 万吨，高于上年同期的 15.8 万吨。')),

    (CAT_SC, ni('https://news.smm.cn/news/104176868',
                '上海有色网', '10-24',
                '花旗：LME 周看淡工业金属，铝 2027 年或过剩 100 万至 200 万吨',
                '花旗称今年 LME 周与会者普遍看淡工业金属，理由包括经济增长疲弱、AI 相关风险、能源价格高企、供应增加与美国铜关税预期落空，在能源与关税明朗前对铜维持中性。该行认为铝是看空情绪最浓的品种，2027 年或面临 100 万至 200 万吨过剩；锡 6 至 12 个月基准目标 60,000 美元/吨、看涨情景 70,000 美元/吨，镍在 16,000 美元/吨下方具备上行潜力。')),

    (CAT_SC, ni('https://news.smm.cn/news/104173449',
                '上海有色网', '10-22',
                '渣打上调铜价预测至 2026 年 13,674 美元/吨，下调铝价至 3,249 美元',
                '渣打银行将 2026 年铜均价预测由 13,472 美元/吨上调至 13,674 美元/吨、2027 年至 13,210 美元/吨，理由是美国铜关税不确定与供给瓶颈；同时下调铝价预测至 2026 年 3,249 美元/吨、2027 年 3,001 美元/吨，因中东供应恢复、印尼增产与中国产量强劲。该行上调 2026 年锌价预测至 3,555 美元/吨、小幅下调镍价至 17,055 美元/吨，并指出智利 8 月铜矿产量同比下滑 12.8%、为 2011 年 2 月以来最低月度水平。')),

    (CAT_SC, ni('https://news.smm.cn/news/104174347',
                '上海有色网', '10-23',
                '金价跌破 4,000 美元/盎司关口，抹去整个夏季涨幅',
                '10 月 23 日现货黄金盘中跌破 4,000 美元/盎司，为 7 月以来首次、日内跌 0.6%，已回吐 8 月以来全部涨幅。分析师指出此次下跌与美元指数、美债收益率走势背离：美元指数下跌、收益率下行却未提振贵金属，可能与 AI 及科技股抛售引发的平仓、以及疑似日元干预有关；3,900 至 4,000 美元为关键支撑区间。')),

    (CAT_SC, ni('https://news.smm.cn/news/104174366',
                '上海有色网', '10-23',
                '印尼镍企协同减产预期发酵，沪镍主力两日累涨逾 4%',
                '受青山、格林美、力勤、华友等在印尼布局高压酸浸（HPAL）的企业讨论协同减产的消息驱动，沪镍主力 10 月 21 日收涨 3.05% 至 121,090 元/吨，22 日盘中最高触及 123,430 元/吨、收 121,420 元/吨，两日累计涨逾 4%；伦镍连续四个交易日上行，21 日涨 3.65% 至约 15,925 美元/吨。但减产尚未官宣，LME 镍库存约 28.1 万吨、上期所镍库存 106,648 吨仍处高位，机构提示上方空间看 12.2 万至 12.4 万元/吨、不宜追高。')),

    (CAT_SC, ni('https://news.smm.cn/news/104174227',
                '上海有色网', '10-23',
                '几内亚 8 月铝土矿出口 1,506.9 万吨，氧化铝出口 2.8 万吨',
                '几内亚统计局数据显示，2026 年 8 月该国出口铝土矿 15,069,218.8 吨，同期出口氧化铝 28,059.3 吨。几内亚是中国进口铝土矿的最主要来源国，其月度出口节奏直接影响国内氧化铝原料供应。')),

    (CAT_SC, ni('https://news.metal.com/newscontent/104175277-gold-at-usd-6000-silver-at-usd-90-metals-focus-remains-bullish-for-2027',
                'SMM 国际站', '10-23',
                'Metals Focus：2027 年金价均价看 5,330 美元，银价看 84.4 美元',
                '英国研究机构 Metals Focus 预计 2027 年黄金均价 5,330 美元/盎司、较 2026 年的 4,600 美元升 16%，四季度均价 5,600 美元、峰值有望触及 6,000 美元；白银 2027 年均价 84.4 美元、四季度突破 90 美元。该机构认为近期回调属必要修正而非熊市起点，央行购金与美元资产多元化仍是主线；但 2027 年白银将转为 3,730 万盎司过剩，涨价需依赖 ETF 资金流入。',
                orig_title='Gold at USD 6,000, silver at USD 90: Metals Focus remains bullish for 2027')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-23/1225615882.PDF',
                '巨潮资讯网', '10-23',
                '中钨高新投 1.31 亿元扩产 PCB 钻针棒，新增年产能 2,000 万支',
                '中钨高新董事会 10 月 21 日通过株硬公司 PCB 钻针棒提质增效技改项目，总投资 1.3102 亿元、建设期 10 个月，资金由公司增资 1.2 亿元与株硬自筹解决；建成后新增年产 2,000 万支 PCB 钻针棒产能，税后内部收益率 12.74%。公司称 AI 算力建设带动 PCB 行业扩张，直径 1.15 毫米以上中大规格产品需求增长显著、现有产能不足。',
                embed='pdf')),

    (CAT_HY, ni('https://news.metal.com/newscontent/104176800-37-battery-and-new-energy-companies-report-cards-highest-growth-of-195405-6-turned-losses-into-profits-is-the-material-chain-the-big-winner-again',
                'SMM 国际站', '10-24',
                '37 家电池新能源企业三季报出炉，最高增幅 19,540.5%、6 家扭亏',
                'SMM 统计 37 家电池及新能源企业三季报，业绩最高同比增幅达 19,540.5%，6 家企业实现扭亏为盈，材料环节被视为本轮业绩的最大赢家。上游原料价格回升带动材料端盈利修复，是本轮业绩分化的主要线索。',
                orig_title="37 battery and new energy companies' report cards: highest growth of 19,540.5%, 6 turned losses into profits")),

    (CAT_HY, ni('https://news.metal.com/newscontent/104176774-smm-aluminum-flash-newsamericas-5-series-aluminum-frp-demand-expands-north-american-consumption-to-reach-223mmt',
                'SMM 国际站', '10-24',
                '美洲 5 系铝板带需求扩张，北美消费量将达 223 万吨',
                'SMM 铝快讯显示，美洲 5xxx 系铝板带需求持续扩张，北美消费量预计达到 223 万吨。5 系铝镁合金在汽车、包装与建筑领域的替代应用扩大，是需求增长的主要驱动。',
                orig_title="Americas' 5-Series Aluminum FRP Demand Expands, North American Consumption to Reach 2.23Mmt")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-24/1225621414.PDF',
                '巨潮资讯网', '10-24',
                '大中矿业以债转股方式向湖南大中赫锂矿增资 10 亿元',
                '大中矿业 10 月 23 日董事会通过以债转股方式对全资子公司湖南大中赫锂矿有限责任公司增资 10 亿元，增资后其注册资本由 10 亿元增至 20 亿元，公司仍持有 100% 股权。公司称此举旨在优化子公司资产负债结构、增强资金实力，不构成关联交易或重大资产重组。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-23/1225617307.PDF',
                '巨潮资讯网', '10-23',
                '招金集团收购招金瑞宁 20% 股权，持股升至 64.45%',
                '招金黄金公告，控股股东招金瑞宁的股东招金集团 10 月 21 日与冉盛盛通签署股权转让协议，收购其持有的招金瑞宁 20% 股权，招金集团持股由 44.45% 升至 64.45%；紫金投资所持 11.11% 股权暂不交割，双方就延期退出继续磋商。招金瑞宁持有上市公司 20% 股份，本次变动不改变控股股东与实际控制人（招远市人民政府）。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-23/1225616022.PDF',
                '巨潮资讯网', '10-23',
                '新铝时代收购东莞宏联电子 100% 股权完成过户，过渡期未亏损',
                '新铝时代以发行股份及支付现金方式向陈旺等 19 名交易对方购买东莞市宏联电子有限公司 100% 股权，标的资产已于 2026 年 8 月 28 日过户至公司名下，新增 23,561,616 股于 9 月 23 日上市。审计显示过渡期（2025 年 4 月 1 日至 2026 年 8 月 31 日）标的资产未发生亏损，收益由公司享有，交易对方无需承担补偿责任。',
                embed='pdf')),

    (CAT_MA, ni('https://news.smm.cn/news/104171386',
                '上海有色网', '10-21',
                '盛和资源出让 4 家稀土冶炼分离子公司部分股权，与中稀集团合作',
                '盛和资源就出售 4 家稀土冶炼分离子公司部分股权、与中国稀土集团产业发展有限公司开展股权合作回应称，交易后仍深度参与 4 家公司经营，总经理由盛和提名、管理层与用工保持稳定，且合作仅限这 4 家标的。公司预计交易价格较账面值有溢价、将增加投资收益与所有者权益，交割后不再纳入合并报表；前三季度预计归母净利润 11 亿元至 12.3 亿元、同比增 39.66% 至 56.17%。')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/central-banks-pile-into-gold-as-china-leads-buying-spree',
                'MINING.COM', '10-23',
                '高盛：8 月全球央行购金 79 吨，中国约 25 吨居首',
                '高盛估算 8 月全球央行购金约 79 吨，接近历史月均水平的五倍，7 月为 44 吨，远高于 2022 年前 17 吨的月均水平；中国为最大买家、约 25 吨，而人民银行官方口径为增持约 20 吨。官方数据显示 9 月人民银行增持为近三年最大单月、连续第 23 个月买入，储备多元化与去美元化是主要动因。',
                orig_title='Central banks pile into gold as China leads buying spree')),

    (CAT_GJ, ni('https://www.mining.com/diesel-price-surge-putting-mining-profits-to-test',
                'MINING.COM', '10-23',
                '柴油价格飙升推高成本，矿企利润承压',
                '霍尔木兹海峡运输扰动推高液化天然气与柴油价格，矿业生产与运输成本随之上升。安托法加斯塔将全年铜现金成本指引上调至 2.60 至 2.70 美元/磅，Capstone 二季度 C1 现金成本同比增 15% 至 2.82 美元/磅（Mantos Blancos 单矿增 88% 至 3.93 美元/磅）；金矿商则依靠创纪录金价对冲，巴里克黄金生产成本同比升 17%、利润仍增长。',
                orig_title='Diesel price surge putting mining profits to test')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104176759-smm-precious-metals-express',
                'SMM 国际站', '10-24',
                'Tharisa 自 9 月起获 Etana Energy 可再生电力供应',
                '南非铂铬生产商 Tharisa 已自 2026 年 9 月起正式获得 Etana Energy 的可再生电力供应，为其降低电力成本、推进脱碳目标的关键一步。',
                orig_title='Tharisa has officially received renewable electricity supply from Etana Energy since September 2026')),
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

# —— 分桶 PIN（按内容口径：技改扩产属 🏭、勘查投入属 🔍，勿被 _reclassify_ma 依「投资」二字拉到 💰）——
_PIN_CAT = [
    ('PCB 钻针棒', CAT_HY),
    ('Kodal', CAT_ZK),
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
