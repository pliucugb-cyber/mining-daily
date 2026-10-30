# -*- coding: utf-8 -*-
"""
生成 2026-10-31 矿业资讯速览 index.html（周六）
- 10-30 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-02）回补历史条目
- 换入 10-31 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-30 收盘 + LME 10-30 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目（ky.mnr 10-30 批 4 宗）已追加进月库 → 前端 #rightsCards，不进主列表
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

REPORT = '2026-10-31'
GRAB = '2026-10-31'
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
                         r'\g<1>2026年10月31日 星期六', html)
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
    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://news.smm.cn/news/104183720',
                '上海有色网', '10-28',
                '科特迪瓦阿斐马金矿钻探见 6 米 18.5 克/吨富矿',
                '图拉科黄金（Turaco Gold）扩大科特迪瓦阿斐马（Afema）项目钻探：66 米深处见矿 6 米、金品位 18.5 克/吨，55 米深处见矿 10 米、品位 6.56 克/吨。项目当前资源量 465 万盎司，本季度将更新；预可行性研究估算投资 4.42 亿美元，投产前七年年均产金 21.5 万盎司，总可持续成本 1500 美元/盎司。')),

    (CAT_ZK, ni('https://news.smm.cn/news/104179578',
                '上海有色网', '10-27',
                '巴西铁山稀土矿地表见 111 米 TREO 8.25%，澳洲温都铜矿同步见富矿',
                '动力矿产（Power Minerals）巴西铁山（Morro Do Ferro）项目自地表见矿 111 米、TREO 品位 8.25%，其中 42 米处见 1.2 米、TREO 40.5%；绿技金属（GreenTech Metals）西澳温都项目彦尼瑞矿床 68 米深处见 12 米，铜 0.9%、锌 1.2%；纳甘比资源维多利亚项目见金 24 克/吨、锑 30.9% 富矿。')),

    (CAT_ZK, ni('https://news.smm.cn/news/104179624',
                '上海有色网', '10-27',
                '加拿大戴维森钼铜钨项目税后净现值升至 12.3 亿加元',
                '月亮河钼业（MRM）更新加拿大不列颠哥伦比亚省戴维森项目初步经济评价：按 8% 折现率税后净现值由 10.3 亿加元升至 12.3 亿加元，税后内部收益率 33%，回报期由 2.3 年缩短至 1.5 年；可年均产钼 1,327 万磅、铜 150 万磅、钨（WO3）151 万磅，较上次估算的 33.4 万磅提升逾 4 倍。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474931',
                '中国有色金属报', '10-26',
                '第三届绿色勘查高质量发展大会在日照召开，聚焦深地与数智勘查',
                '10 月 21 至 22 日，第三届新一轮找矿突破战略行动绿色勘查高质量发展大会在山东日照召开，400 余名代表围绕深地探测、智能勘查、绿色发展与产业升级研讨。会议提出面向「十五五」聚焦增储上产、科技赋能、绿色转型三项任务，推动深地低扰动绿色勘查成套技术应用。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104183697',
                '上海有色网', '10-28',
                '澳大利亚调整关键矿产战略，重心转向冶炼与加工',
                '澳大利亚资源部长玛德琳·金表示，因投资竞争加剧、供应链担忧未消，该国将调整关键矿产战略，把更多重心放在冶炼和加工，尤其是澳方拥有或可建立比较优势的领域，并将扩大对欧洲出口。此前其 12 亿澳元战略储备优先考虑锑、镓和稀土。')),

    (CAT_ZC, ni('https://www.ccmn.cn/news/ZX018/202610/3dc823728661435a850af626467d0500.html',
                '长江有色网', '10-30',
                '上期所暂停阴极铜、铝期货保税交割业务',
                '上海期货交易所 10 月 29 日公告，自即日起暂停阴极铜（CU）、铝（AL）期货保税交割业务，并明确该调整为正常业务调整，不影响 BC 铜及上期所铜铝期货的正常交割流程。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104189567',
                '上海有色网', '10-30',
                '伦敦金库白银库存升至 9.32 亿盎司，金银比回到 76 上方',
                'Metals Focus 报告显示，9 月底伦敦金库白银库存升至 9.32 亿盎司、为近四年最高；剔除 ETP 持仓后可流通库存约 2.67 亿盎司，接近 2025 年 10 月低点的两倍。全球白银 ETP 年内减持约 6,000 万盎司，金银比升至 76 以上、为 2025 年 12 月以来首次。')),

    (CAT_SC, ni('https://www.mining.com/gold-price-slumps-to-one-year-low-silver-price-breaks-50-as-mining-stocks-tank',
                'MINING.COM', '10-30',
                '金价跌至一年低点、银价失守 50 美元，金银矿股重挫',
                '现货黄金一度跌 3.2% 至 3,891.67 美元/盎司，为去年 10 月 28 日以来最低；白银跌 5.8% 至 49.34 美元/盎司，为 2025 年 11 月以来首次跌破 50 美元，月内跌幅约 18%。油价走高强化美联储加息预期、科技股下跌迫使投资者抛售金属，金银生产商股价最多跌 8%。',
                orig_title='Gold price slumps to one-year low, silver price breaks $50 as mining stocks tank')),

    (CAT_SC, ni('https://news.metal.com/newscontent/104189649-domestic-port-inventories-of-imported-bauxite-drop-by-480000-mt-week-on-week',
                'SMM 国际站', '10-30',
                '国内十港进口铝土矿库存周环比减少 48 万吨',
                'SMM 10 月 30 日统计，国内十个港口的进口铝土矿库存合计较前一周减少 48 万吨。该口径为 SMM 周度跟踪的十港合计库存，反映氧化铝厂原料到港与提货节奏。',
                orig_title='Domestic Port Inventories of Imported Bauxite Drop by 480,000 mt Week-on-Week')),

    (CAT_SC, ni('https://news.metal.com/newscontent/104186807-world-bank-forecasts-copper-prices-to-stay-near-re',
                'SMM 国际站', '10-30',
                '世界银行上调 2027 年铜价预测 18% 至 13,000 美元/吨',
                '世界银行 10 月展望报告将 2027 年铜价预测较 4 月上调 18% 至 13,000 美元/吨（约 5.90 美元/磅），仅比其对本年 13,200 美元/吨的均价预测低 1.5%。报告认为新矿投产难以跟上电力与数据中心建设带来的铜需求。',
                orig_title='World Bank Forecasts Copper Prices to Stay Near Record Highs in 2027 Amid Strong Demand')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/104186154',
                '上海有色网', '10-29',
                '中铝国际中标越南平福 240 万吨/年氧化铝项目，合同额 8.33 亿美元',
                '中铝国际（02068.HK）公告，10 月 23 日中标越南平福矿业股份有限公司年产 240 万吨氧化铝项目，合同总价 8.33 亿美元、折合人民币约 55.95 亿元，最终价格以双方签署的 EPC 合同约定为准。')),

    (CAT_HY, ni('https://news.smm.cn/news/104186716',
                '上海有色网', '10-29',
                '中国稀土前三季度净利 4.08 亿元，同比增 112.37%',
                '中国稀土三季报显示，前三季度营业收入 26.57 亿元、同比增 6.52%，归母净利润 4.08 亿元、同比增 112.37%；第三季度营收 10.11 亿元、同比增 63.19%，净利润 1.71 亿元、同比增 461.73%，主因部分稀土产品价格上涨与采销策略调整。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-31/1225646426.PDF',
                '巨潮资讯网', '10-31',
                '兴业银锡子公司事故后采区恢复生产',
                '兴业银锡公告，此前发生安全事故的子公司相关采区已恢复生产，复产范围与进度以公告正文及后续定期报告披露为准。')),

    (CAT_HY, ni('https://news.smm.cn/news/104184267',
                '上海有色网', '10-29',
                '江特电机茜坑锂矿 300 万吨/年采矿工程安全设施设计通过审查',
                '江特电机 10 月 27 日在投资者互动平台表示，茜坑锂矿已于 2024 年 5 月取得采矿许可证，2026 年 10 月其 300 万吨/年采矿工程安全设施设计通过国家矿山安全监察局审查。公司称茜坑锂矿是其最重要的锂矿资源。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475072',
                '中国有色金属报', '10-30',
                '西安新派得高纯铌钽新产线通产，完成数千万元 Pre-A 轮融资',
                '西安新派得科技 10 月 28 日在西安举行高纯铌钽新产线点火仪式，产线正式通产；公司同步公布完成数千万元 Pre-A 轮股权融资，由芯能创投、上海科创集团知识产权基金、江苏金桥基金联合投资，资金用于提纯工艺迭代与专用装备自研。')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://news.smm.cn/news/104183713',
                '上海有色网', '10-28',
                '南方铜业评估秘鲁夸霍内铜矿 6.8 亿美元扩产',
                '南方铜业正评估秘鲁南部夸霍内（Cuajone）铜矿 6.8 亿美元扩产项目，日磨矿能力将由 9 万吨提升至 12 万吨，预计年产铜 5.5 万吨、钼 1,400 吨，并研究进一步提至日处理 15 万吨。公司尚未作出最终投资决定，时间表未定。')),

    (CAT_GJ, ni('https://www.mining.com/glencore-cobalt-output-sinks-52-under-drc-quotas',
                'MINING.COM', '10-29',
                '嘉能可前三季度自产钴 1.37 万吨，同比降 52%',
                '嘉能可三季度产量报告显示，前三季度自产钴 1.37 万吨，较上年同期 2.85 万吨下降 52%，当季产量 3,500 吨、环比降 20%。公司称因刚果（金）出口配额，更多将混合矿中的钴保留在溶液中而非加工为可销售氢氧化物，被保留部分不计入报告产量。',
                orig_title='Glencore cobalt output sinks 52% under DRC quotas')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104186738-teck-q3-copper-production-up-11-yoy-maintains-full',
                'SMM 国际站', '10-29',
                '泰克资源三季度产铜 11.57 万吨同比增 11%，维持全年指引',
                '泰克资源三季度产铜 11.57 万吨、同比增 11%，其中 Quebrada Blanca 产铜 4.72 万吨、环比降约 15.4%，主因暴雪、强风、停电及高品位矿受限。公司维持 2026 年铜产量指引 45.5 万至 53 万吨；Highland Valley Copper 自 10 月 24 日起罢工、目前减产运行。',
                orig_title='Teck Q3 Copper Production Up 11% YoY, Maintains Full-Year 2026 Production Guidance')),

    (CAT_GJ, ni('https://www.mining.com/us-copper-stockpiles-conceal-growing-global-supply-crunch',
                'MINING.COM', '10-29',
                'COMEX 铜库存 71.8 万吨占全球交易所库存 69%，掩盖真实紧缺',
                'GEM Mining Consulting 研究显示，10 月 COMEX 铜库存 71.8 万吨，占 LME、COMEX 与上期所可见库存的 69%（2015 至 2024 年均值仅 16%）；全球交易所库存 104 万吨、同比增 83%，但 LME 与上期所合计 31.9 万吨、低于长期均值 11%。ICSG 预计 2026 年过剩 10.4 万吨，高盛则估算美国以外缺口约 95 万吨。',
                orig_title='US copper stockpiles conceal growing global supply crunch')),

    (CAT_GJ, ni('https://www.mining.com/critical-minerals-getting-harder-to-mine-as-deposits-age-ey',
                'MINING.COM', '10-30',
                'EY：矿山老龄化与品位下降推高运营复杂性，居 2027 年行业风险首位',
                'EY《采矿与金属业十大商业风险与机遇》基于全球 400 位高管调查，将运营复杂性列为 2027 年行业头号风险，其后为资本可得性、供应链中断、成本上升与地缘政治，29% 受访者提及储量品位波动。2023 至 2025 年各国对关键矿产的公共融资承诺增长逾三倍、约 650 亿美元。',
                orig_title='Critical minerals getting harder to mine as deposits age: EY')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-30/1225639527.PDF',
                '巨潮资讯网', '10-30',
                '贵研铂业拟以非公开协议方式转让贵研工业催化剂 100% 股权',
                '贵研铂业公告，云南省贵金属新材料控股集团拟将所持贵研工业催化剂（云南）有限公司 100% 股权以非公开协议方式转让。交易对方、对价与生效条件以公告正文披露为准。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-29/1225635834.PDF',
                '巨潮资讯网', '10-29',
                '兴业银锡披露对外投资收购威领股份进展',
                '兴业银锡公告对外投资收购威领股份的进展，具体交易进度、股权比例与对价以公告正文及后续披露为准。')),

    (CAT_MA, ni('https://news.metal.com/newscontent/104189635-ghana-bauxite-co-secures-250m-financing-for-awaso-',
                'SMM 国际站', '10-30',
                '加纳铝土矿公司获 2.5 亿美元融资，扩建 Awaso 矿并建氧化铝厂',
                '加纳铝土矿公司（Ghana Bauxite）委托 Ecobank Ghana 安排最高 2.5 亿美元融资，用于 Awaso 铝土矿扩建的资本开支与营运资金；其铝土矿出口量已由 2022 年约 77.3 万吨增至 2025 年 207 万吨，并计划建设初期年产能 50 万吨、远期 150 万吨的氧化铝厂。',
                orig_title='Ghana Bauxite Co. Secures $250M Financing for Awaso Mine Expansion and Alumina Refinery Development')),

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
    ('阿斐马', CAT_ZK),
    ('巴西铁山', CAT_ZK),
    ('戴维森', CAT_ZK),
    ('绿色勘查', CAT_ZK),
    ('澳大利亚调整', CAT_ZC),
    ('上期所暂停', CAT_ZC),
    ('金银比', CAT_SC),
    ('金价跌至一年低点', CAT_SC),
    ('铝土矿库存', CAT_SC),
    ('世界银行', CAT_SC),
    ('中铝国际中标', CAT_HY),
    ('中国稀土前三季度', CAT_HY),
    ('兴业银锡子公司', CAT_HY),
    ('茜坑', CAT_HY),
    ('新派得', CAT_HY),
    ('南方铜业', CAT_GJ),
    ('嘉能可前三季度自产钴', CAT_GJ),
    ('泰克资源', CAT_GJ),
    ('COMEX 铜库存', CAT_GJ),
    ('EY：', CAT_GJ),
    ('贵研', CAT_MA),
    ('威领股份', CAT_MA),
    ('加纳铝土矿', CAT_MA),
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
