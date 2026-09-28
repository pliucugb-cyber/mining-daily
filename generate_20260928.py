# -*- coding: utf-8 -*-
"""
生成 2026-09-28 矿业资讯速览 index.html（周一）
- 09-27 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-30）回补历史条目
- 换入 09-28 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-24 收盘（09-25 起中秋休市、周一 08:00 未开盘）
  + LME 09-25 收盘（当日未收盘，口径对齐最近已收盘日），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易），不进主页列表
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

REPORT = '2026-09-28'
GRAB = '2026-09-28'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月28日 星期一', html)
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
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474272',
                '中国有色金属报', '09-28',
                '江西物化探大队挺进阿尔金山，新疆于沟钼多金属矿普查完成野外物探',
                '江西省地质局物化探大队承接的新疆若羌县于沟钼多金属矿普查项目，位于新疆若羌与青海茫崖交界的阿尔金山脉之间，平均海拔 4500 多米，高寒缺氧、裸岩广布、大风沙尘频发；6 月 29 日项目组正式进场。此次物探工作包括磁法、重力、激电中梯、激电测深及测井等，目的是大致查明矿体规模、形态、产状、厚度等特征，为下一步钻探验证提供数据支撑。项目组通过奥维地图精细规划电极点位、行进路线与发电机布设位置，以充足准备保障野外施工高效开展。',
                )),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/en/newscontent/104133460-smm-analysis-china-us-talks-fuel-bullish-sentiment-in-pr-nd-market-but-fundamentals-prevail',
                'SMM 国际站', '09-28',
                'SMM 分析：中美经贸对话提振镨钕市场情绪，但基本面仍主导',
                'SMM 分析指出，在中美经贸议程中，稀土与关键矿产是全球供应链最受关注的主题之一，相关经贸对话一度提振镨钕（Pr-Nd）市场情绪。不过分析认为，价格最终仍由基本面主导，情绪面的提振难以脱离供需现实。',
                orig_title="[SMM Analysis] China-US Talks Fuel Bullish Sentiment in Pr-Nd Market, But Fundamentals Prevail")),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474280',
                '中国有色金属报', '09-28',
                '8 月有色金属价格环比上涨 3.9%、同比上涨 28.8%',
                '商务部商务大数据显示，8 月全国生产资料市场价格环比上涨 1.1%。从主要品种看，有色金属价格环比上涨 3.9%、同比上涨 28.8%，其中铜、锌、铝价格环比分别上涨 4.0%、3.9% 和 3.8%。同期钢材价格环比下降 1.0%、同比下降 4.1%，成品油、煤炭价格环比分别上涨 6.1% 和 1.9%。',
                )),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474214',
                '中国有色金属报', '09-28',
                '供需博弈下镁价筑底，双节备货需求待释放',
                '9 月第 3 周国内镁市场先扬后稳：截至 9 月 18 日，陕西府谷 99.9% 镁锭主流出厂含税现金报价 1.59 万元/吨，市场主流成交集中在 1.585 万元/吨，较上上周温和上调约 100 元/吨。9 月前 3 周镁价在 1.58 万～1.62 万元/吨区间窄幅震荡，多数镁厂处于成本倒挂状态、控制出货节奏，低价货源稀缺。机构判断短期镁市以筑底企稳为主，中秋、国庆双节临近带来的阶段性备货需求有望形成支撑。',
                )),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473462',
                '中国有色金属报', '09-28',
                '供应压力增加，铜价将震荡走强',
                '近期铜价在美国铜关税忧虑情绪推动下先扬后抑：沪铜主力合约价格突破以 105000 元/吨为中枢的震荡区间，价格重心抬升至 108000 元/吨附近；8 月中下旬海外现货供应紧张、LME 现货升水快速拉升，一度刺激铜价最高上涨至 109780 元/吨，随后因基本面缺乏可持续的实质性利好而回吐涨幅。宏观方面，美国 7 月 ISM 制造业指数升至 55.6，但 7 月非农就业人数减少 2.3 万人、CPI 同比上涨 3.4%，市场对美联储加息路径的预期持续调整。文章判断供应压力增加背景下铜价将震荡走强。',
                )),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104134765-gold-silver-and-oil-fell-on-the-weekly-chart-overseas-metals-broadly-declined-lme-tin-rose-over-1-lme-zinc-fell-nearly-2-us-stocks-rose-holiday-market-review',
                'SMM 国际站', '09-28',
                '假期行情回顾：金银油周线收跌，外盘金属普跌、伦锡涨逾 1%',
                'SMM 假期行情回顾显示，假期期间海外金属普遍下跌，其中伦锡涨超 1%、伦锌跌近 2%；黄金、白银与原油周线收跌，美股上涨。该回顾汇总了中秋假期期间境外主要市场表现，为节后开盘提供参考。',
                orig_title="Gold, silver, and oil fell on the weekly chart, overseas metals broadly declined, LME tin rose over 1%, LME zinc fell nearly 2%, US stocks rose [Holiday Market Review]")),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104134818-bauxite-departures-from-guinea-australia-drop',
                'SMM 国际站', '09-28',
                '几内亚、澳大利亚铝土矿发运量环比大幅下降',
                '据 9 月 25 日数据，中国港口铝土矿周度到港量合计 397.61 万吨，环比减少 105.7 万吨；几内亚主要港口铝土矿周度发运量 244.36 万吨，环比减少 188.74 万吨；澳大利亚主要港口周度发运量 88.61 万吨，环比减少 39.36 万吨。',
                orig_title="Bauxite Departures from Guinea, Australia Drop")),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104134820-bauxite-inventory-at-ten-domestic-ports-falls-by-70000-mt-wo',
                'SMM 国际站', '09-28',
                '国内十港铝土矿库存周环比下降 7 万吨',
                'SMM 数据显示，国内十个港口的铝土矿库存周环比下降 7 万吨。该库存跟踪用于观察氧化铝原料端的到港与消耗节奏。',
                orig_title="Bauxite Inventory at Ten Domestic Ports Falls by 70,000 mt Wo")),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474019',
                '中国有色金属报', '09-28',
                '明月湖实验室研制出高性能镁合金电驱壳体，整体减重 30%',
                '明月湖实验室联合重庆卓通汽车工业有限公司成功研制出高性能镁合金电驱壳体，该产品实现整体减重 30%，预计 2027 年上半年实现量产。研发团队从材料、结构、工艺三方面攻坚：材料层面通过稀土元素掺杂与多元微合金化使综合性能较传统方案提升约 20%；结构层面依托拓扑优化实现壳体减重 30%、同等电量下百公里电耗可降低 4%～6%；工艺层面创新采用半固态压铸技术提升致密度与尺寸精度。产品盐雾试验时长超 1080 小时。',
                )),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474018',
                '中国有色金属报', '09-28',
                '洛阳特种材料研究院攻克超大规格镁稀土合金构件制备难题',
                '上海交通大学洛阳特种材料研究院团队在超大规格吨级镁稀土合金构件研制领域取得技术突破，成形单重 1100kg 的高性能镁稀土合金圆饼，锻件表面无裂纹、综合力学性能优异。研究团队针对大体积熔体纯净化传输难、主合金元素含量精确控制难、大规格铸锭半连铸易开裂且缺陷多、构件组织性能一致性差等“卡脖子”问题，建立了大体积熔体清洁传输、主合金元素精确调控、大规格铸锭半连铸均质制备等全链条技术方案。',
                )),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474288',
                '中国有色金属报', '09-28',
                '攀钢海绵钛出口量同比大幅增长',
                '1—8 月，攀钢集团有限公司海绵钛出口量同比大幅增长，超额完成阶段性奋斗目标。面对国际市场形势复杂多变、海运价格大幅波动等不利因素，攀钢紧抓海外市场机遇，在持续巩固原有客户渠道的基础上积极开拓新客户，进一步提升海绵钛出口量，丰富并巩固了在欧洲、东南亚等区域市场的客户渠道体系。',
                )),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0922/62063.html',
                '中国有色金属工业协会', '09-22',
                'TC 深度负值之下，18 家上市铜企半年报全线盈利',
                '铜精矿加工费 TC 近两年一路走跌：2019 年 6 月还在 75 美元/干吨的正常水平，2025 年 2 月跌至 -50 美元/干吨，2026 年 7 月进一步跌破 -100 美元/干吨；截至 2026 年 9 月，进口铜精矿现货 TC 已跌至约 -200 美元/干吨，持续刷新历史低点。然而 18 家上市铜企 2026 年上半年全部实现盈利、多家净利润翻倍：北方铜业增幅达 186.61%，江西铜业、铜陵有色、西部矿业、恒邦股份等增幅均超 100%；紫金矿业归母净利润 391.70 亿元、同比增 68.17%，洛阳钼业 161.52 亿元、增 86.27%。文章指出，冶炼主业亏损背景下利润的真正推手是硫酸等副产品收益，自有矿山占比高的企业则受益于矿端。',
                )),
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104134812-kangpu-chemical-pilot-plant-produces-lithium-carbonate',
                'SMM 国际站', '09-28',
                '康普化学新能源金属中试线产出碳酸锂并实现对外销售',
                '康普化学披露，公司 2024 年建成投产的百吨级新能源金属绿色综合利用装置，采用自主研发的湿法冶金新工艺路线，实现新能源金属的高效提取与绿色回收。装置已验证多批次不同原料，2026 年上半年产出数吨碳酸锂并实现对外销售，为资源循环业务积累运营数据。',
                orig_title="[Kangpu Chemical: Pilot Plant Produces Lithium Carbonate]")),
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104134811-derui-lithium-battery-shexi-plant-phase-1-plans-8-production-lines',
                'SMM 国际站', '09-28',
                '德瑞锂电涉溪厂一期规划 8 条产线，圆柱电池月产能超 500 万只',
                '德瑞锂电披露，涉溪厂一期规划建设 8 条产线，其中圆柱与软包锂一次电池产线各 4 条；2026 年 3 月试生产后产能逐步爬坡，截至 6 月底圆柱锂一次电池月产能已超过 500 万只，缓解了此前部分产品的产能瓶颈。软包产线已完成小批量试产、正处于产品测试验证阶段，新产能释放将随市场开发与订单情况逐步推进。',
                orig_title="[Derui Lithium Battery: Shexi Plant Phase 1 Plans 8 Production Lines]")),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/ngos-warn-donlin-mine-spill-could-devastate-region',
                'MINING.COM', '09-28',
                '多家非政府组织警告 Donlin 金矿尾矿事故可能重创区域生态',
                '一项新的联邦审查发现，Donlin 金矿若发生重大尾矿库事故，可能造成人员死亡、污染水体，并在数代人之内抑制鱼类资源。多家非政府组织据此警告该项目存在严重环境风险。',
                orig_title="NGOs warn Donlin mine spill could devastate region")),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134803-smm-analysis-zimbabwes-lithium-mine-welcomes-a-new-investor-indias-lohum-enters-the-fray',
                'SMM 国际站', '09-28',
                '津巴布韦锂矿迎来新投资方：印度 LOHUM 入局',
                'SMM 分析指出，印度 LOHUM 公司进入津巴布韦锂矿领域，成为当地锂矿项目的新投资方。文章将其视为津巴布韦锂资源开发格局中正在出现的一个新变量。',
                orig_title="[SMM Analysis] Zimbabwe's Lithium Mine Welcomes a New Investor: India's LOHUM Enters the Fray")),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134794-smm-flash-news-indonesia-names-pt-cni-corporate-suspect-in-rp40165-billion-nickel-governance-case',
                'SMM 国际站', '09-28',
                '印尼将 PT CNI 列为 4016.5 亿印尼盾镍治理案企业嫌疑人',
                'SMM 快讯显示，印尼主管部门将 PT CNI 列为一起涉 4016.5 亿印尼盾镍治理案件的企业嫌疑人。该案围绕镍矿治理与合规问题展开，具体指控与后续处理以印尼主管部门公布为准。',
                orig_title="[SMM Flash News] Indonesia Names PT CNI Corporate Suspect in Rp401.65 Billion Nickel Governance Case")),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104131537-smm-analysis-a-snapshot-of-zambias-gold-market-from-mine-output-to-formal-trade',
                'SMM 国际站', '09-28',
                'SMM 分析：赞比亚黄金市场从矿产到正规贸易的概览',
                'SMM 分析认为，赞比亚黄金市场的规模与复杂程度超出官方产量数据所反映的水平。研究考察了 Kansanshi 铜金矿所扮演的角色、对手工采矿者的正规收购、央行购金、拟议中的增值税调整以及黄金 ETF 计划，并解释了赞比亚与阿联酋 2023 年海关记录之间的巨大差距——该差距需要逐笔核对货运数据，不能直接视为走私或税收流失的证据。',
                orig_title="[SMM Analysis] A Snapshot of Zambia's Gold Market: From Mine Output to Formal Trade")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-28/1225581228.PDF',
                '巨潮资讯网', '09-28',
                '恩捷股份：收购下属子公司少数股权暨与亿纬锂能设立合资公司取得进展',
                '恩捷股份（002812）公告，公司收购下属子公司少数股权并与亿纬锂能设立合资公司的事项取得进展，相关安排按前期披露方案推进。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-28/1225580907.PDF',
                '巨潮资讯网', '09-28',
                '*ST威领：西藏山南锑金资源要约收购公司股份（第三次提示）',
                '*ST威领（002667）发布第三次提示性公告，西藏山南锑金资源有限公司要约收购公司股份事项仍在推进。公司提示投资者关注要约收购的进展与相关风险。',
                embed='pdf')),
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104134816-hunan-yuneng-spain-project-investment-raised-to-rmb165b',
                'SMM 国际站', '09-28',
                '湖南裕能西班牙项目投资额提高至约 16.5 亿元，规划年产能 7 万吨',
                '湖南裕能公告称，董事会审议通过决议，同意将西班牙项目建设规模提升至年产 7 万吨锂电池正极材料，项目总投资调整为约人民币 16.5 亿元等值，并授权管理层处理项目投资规模调整的相关具体事项。',
                orig_title="[Hunan Yuneng: Spain Project Investment Raised to RMB1.65B]")),
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
