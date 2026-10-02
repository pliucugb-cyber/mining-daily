# -*- coding: utf-8 -*-
"""
生成 2026-10-02 矿业资讯速览 index.html（周五 · 国庆假期）
- 09-30 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-02）回补历史条目
- 换入 10-01 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-30 收盘（现算）
  + LME 卡片=走势图末点口径 09-28 收盘（当日电子盘未收盘/东财日K滞后），
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

REPORT = '2026-10-02'
GRAB = '2026-10-02'
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
                         r'\g<1>2026年10月02日 星期五', html)
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
    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260930_10327477.htm',
                '全球矿产资源信息系统', '09-30',
                '印度拟将钢铁年产能提升至 6 亿吨',
                '印度钢铁部长宣布新钢铁政策规划：到 2047 年将年产能由目前 2.2 亿吨提升至 6 亿吨，并制定排放削减与铁矿石、焦煤等原材料保障措施。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104143341',
                '上海有色网', '10-01',
                '期铜触及两周低点，美元走强拖累市场情绪',
                'SMM 援引 10 月 1 日 LME 收盘：伦铜跌 166.5 美元或 1.16% 报 14,243.5 美元/吨，盘中触及 14,213.5 美元创 9 月 17 日以来最低；期铝跌至 12 周低点。美元升至 2025 年 4 月以来最高，全球债市抛售推升收益率，拖累金属价格。')),

    (CAT_SC, ni('https://news.smm.cn/news/104143342',
                '上海有色网', '10-02',
                '美国银行上调长期铜价预测至 2031 年 13,577 美元/吨',
                'SMM 援引文华财经：美银将 2031 年铜价预测上调 20% 至 13,577 美元/吨，因美国以外地区供应趋紧、亚洲市场持续紧张；同时警告油价高企或短期压制基本金属，预计金价 2026 年四季度或跌向 3,750 美元/盎司。')),

    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://www.mining.com/greenland-mines-makes-gallium-vanadium-discovery-at-skaergaard',
                'MINING.COM', '10-01',
                'Greenland Mines 在 Skaergaard 发现镓、钒矿化',
                'MINING.COM 报道，Greenland Mines 完成格陵兰东南部 Skaergaard 项目 2026 年度野外工作，正评估含钒钛磁铁矿、铁与镓的潜在价值流，已取得推进冶金流程开发所需的实物样品与地学数据。',
                orig_title='Greenland Mines makes gallium, vanadium discovery at Skaergaard')),

    (CAT_ZK, ni('https://www.mining.com/grid-metals-atomic-clock-cesium-resource-in-manitoba-ranks-second-globally',
                'MINING.COM', '10-01',
                'Grid Metals 加拿大曼尼托巴铯资源规模居全球第二',
                'MINING.COM 报道，Grid Metals 公布加拿大曼尼托巴 Falcon West 项目 Lucy South 矿床首个资源量：51,500 吨、氧化铯品位 2.58%、氧化锂 1.47%，含金属量 1,322 吨氧化铯与 756 吨氧化锂，为西方公司正在开发的全球第二大铯资源。',
                orig_title="Grid Metals' atomic clock cesium resource in Manitoba ranks second globally")),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/104143322',
                '上海有色网', '10-01',
                '巴拿马委员会建议与第一量子谈判重启 Cobre Panama 铜矿',
                'SMM 援引文华财经：巴拿马政府一委员会建议与第一量子开启正式谈判，设定重启已关闭的 Cobre Panama 铜矿条件，新协议将终止悬而未决的国际仲裁索赔，并在不增加国家负担前提下为矿山有序关闭提供资金。该矿曾占全球铜产量约 1%。')),

    (CAT_HY, ni('https://news.smm.cn/news/104143310',
                '上海有色网', '10-01',
                '智利 8 月铜产量同比下降 12.8% 至 369,500 吨',
                'SMM 援引智利国家统计局（INE）：受风暴天气与矿石品位下降影响，智利 8 月铜产量 369,500 吨、同比下降 12.8%，低于 2025 年 8 月的 423,643 吨；7 月风暴对开采与加工的后续影响仍在持续。当月制造业产量同比下降 2.6%。')),

    (CAT_HY, ni('https://news.smm.cn/news/104143325',
                '上海有色网', '10-01',
                '日本三菱材料预计下半财年铜产量同比下降 18%',
                'SMM 援引文华财经：日本三菱材料计划 2026 财年下半年（10 月至次年 3 月）生产精炼铜 142,284 吨，同比下降 18%，主因直岛与小名浜冶炼厂检修；下半财年铅产量计划 13,500 吨，低于上半年 13,644 吨。')),

    (CAT_HY, ni('https://news.smm.cn/news/104143323',
                '上海有色网', '10-01',
                '日本泛太平洋铜业上半财年铜产量低于目标',
                'SMM 援引文华财经：日本最大铜供应商泛太平洋铜业（PPC）称 2026 财年上半年委托生产精炼铜约 284,200 吨，低于 4 月计划的 312,700 吨，因委托设施出现问题；公司罕见地未披露下半财年生产计划，称仍在评估 TC/RC 谈判等因素。')),

    (CAT_HY, ni('https://news.metal.com/en/newscontent/104143324-escondida-supervisors-reject-bhp-contract-offer-paving-way-for-potential-strike',
                'SMM 国际站', '10-01',
                '必和必拓 Escondida 矿主管拒绝合同报价，罢工风险上升',
                'SMM 国际站报道，必和必拓智利 Escondida 铜矿 1,020 名主管工会中 95% 投票成员否决公司最终集体谈判报价，为全球最大铜矿潜在罢工铺路；按智利劳动法，双方须先进入为期 5 天的政府主导强制调解，经双方同意可再延长 5 天。',
                orig_title='Escondida Supervisors Reject BHP Contract Offer, Paving Way for Potential Strike')),

    (CAT_HY, ni('https://news.metal.com/en/newscontent/104143331-fatal-accident-reported-at-codelcos-radomiro-tomic-mine',
                'SMM 国际站', '10-01',
                '智利 Codelco Radomiro Tomic 铜矿发生致死事故',
                'SMM 国际站援引智利矿业监管机构：Codelco 旗下 Radomiro Tomic 铜矿 10 月 1 日发生事故，一名工人在卡拉马附近输送带相关区域身亡。Codelco 已暂停破碎与物料处理区作业，事故原因调查中，暂未公布生产影响。',
                orig_title="Fatal Accident Reported at Codelco's Radomiro Tomic Mine")),

    (CAT_HY, ni('https://news.metal.com/en/newscontent/104143314-generation-mining-begins-construction-at-marathon-copper-palladium-project-in-ontario',
                'SMM 国际站', '10-01',
                'Generation Mining 启动加拿大 Marathon 铜钯项目建设',
                'SMM 国际站报道，Generation Mining 在其全资拥有的加拿大安大略省西北部 Marathon 铜钯项目开工，已缴纳建设期财务保证金。早期工程涵盖进场道路升级、厂址与初坑清理、水管理设施、营地扩建、土方工程与环保监测，将持续至 2026 年四季度并跨入 2027 年。',
                orig_title='Generation Mining Begins Construction at Marathon Copper-Palladium Project in Ontario')),

    (CAT_HY, ni('https://news.metal.com/en/newscontent/104139628-smm-analysis-low-carbon-of-primary-copper-begin-trading-separatelywill-recycled-coppers-green-value-be-reassessed',
                'SMM 国际站', '10-01',
                'SMM 分析：原生铜低碳属性开始独立交易',
                'SMM 分析指出，铜的低碳属性正开始从实物金属贸易中分离。9 月 22 日必和必拓与亚马逊宣布试点，为 Escondida 矿产出的铜精矿与阴极铜创建环境属性证书（EAC），亚马逊可购买并注销以核算其数据中心用铜的供应链减排。',
                orig_title="[SMM Analysis] Low-Carbon of Primary Copper Begin Trading Separately—Will Recycled Copper's Green Value Be Reassessed")),

    (CAT_HY, ni('https://news.metal.com/en/newscontent/104143353-kghm-completes-record-g',
                'SMM 国际站', '10-01',
                'KGHM 提前完成 Głogów II 铜冶炼厂史上最大检修',
                'SMM 国际站报道，波兰 KGHM 于 10 月 1 日宣布提前完成 Głogów 铜冶炼厂史上规模最大的检修与现代化改造，覆盖 Głogów II 全部主工艺线（含闪速炉）；改造后该厂大修间隔由 4 年延长至 5 年，提升可靠性并降低冶炼成本。2026 年电解铜产量目标约 58.9 万吨。',
                orig_title='KGHM Completes Record Głogów II Copper Smelter Overhaul Ahead of Schedule')),

    (CAT_HY, ni('https://news.smm.cn/news/104143327',
                '上海有色网', '10-01',
                '日本古河计划下半年铜产量削减 3%',
                'SMM 援引文华财经：日本冶炼商古河（Furukawa）计划 2026 财年下半年（10 月至次年 3 月）生产精炼铜 21,497 吨，较上年同期下降 3%，因全球铜精矿供应偏紧、冶炼加工利润承压。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/brazil-court-order-shuts-sigma-lithium-mine',
                'MINING.COM', '10-01',
                '巴西法院裁定关停 Sigma Lithium 锂矿',
                'MINING.COM 报道，Sigma Lithium 已暂停巴西 Grota do Cirilo 锂矿全部采矿与选矿作业。此前两日公司曾否认法院已吊销其环保许可，10 月 1 日收到米纳斯吉拉斯州环保监管机构 FEAM 的电子通知后停产。该矿为全球规模最大、品位最高的硬岩锂矿床之一。',
                orig_title='Brazil court order shuts Sigma Lithium mine')),

    (CAT_GJ, ni('https://www.mining.com/bc-first-nation-terminates-agreements-with-spanish-mountain-gold-shares-plunge',
                'MINING.COM', '10-01',
                '加拿大原住民部落终止与 Spanish Mountain Gold 协议',
                'MINING.COM 报道，加拿大不列颠哥伦比亚省 Xatśūll 第一民族宣布终止与 Spanish Mountain Gold 就拟建金矿达成的协议（原于 2012 年与 2021 年签订），公司股价随之大跌。原住民部落称协议旨在推进关系协议谈判，现予以终止。',
                orig_title='BC First Nation terminates agreements with Spanish Mountain Gold, shares plunge')),

    (CAT_GJ, ni('https://www.mining.com/beaver-creek-golds-bond-break-puts-juniors-in-play',
                'MINING.COM', '10-01',
                'Beaver Creek 论坛：金价与美债脱钩，初级矿商受关注',
                'MINING.COM 报道，在科罗拉多州 Beaver Creek 贵金属峰会上，与会者指出自 2022 年初以来金价翻倍以上、同期美债收益率上行，这种「脱钩」或意味着黄金重获货币属性。9 月 24 日 COMEX 近月黄金期货收于 4,263 美元/盎司，较 1 月 29 日纪录结算价 5,318.40 美元低 20%。',
                orig_title="Beaver Creek: Gold's bond break puts juniors in play")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-01/1225590305.PDF',
                '巨潮资讯网', '10-01',
                '宝地矿业：控股股东拟与新疆有色集团整体合并（进展）',
                '宝地矿业公告，控股股东新疆地矿投资（集团）有限责任公司拟与新疆有色金属工业（集团）有限责任公司实施整体合并，本次为进展公告；同日公司披露收购报告书（修订稿）摘要。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-01/1225589823.PDF',
                '巨潮资讯网', '10-01',
                '厦门钨业：子公司金龙稀土北交所上市申请获受理',
                '厦门钨业公告，控股子公司福建省金龙稀土股份有限公司公开发行股票并在北京证券交易所上市的申请已获受理；公司提示本次发行尚需北交所审核及中国证监会注册，存在不确定性。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-01/1225589939.PDF',
                '巨潮资讯网', '10-01',
                '新疆天业拟收购多家矿业公司股权（评估报告披露）',
                '新疆天业公告披露拟收购股权涉及的晶羿矿业、天业集团矿业、天博辰业矿业等多家公司股东全部权益价值资产评估报告，同步披露阿勒担达坂石灰岩矿、科克萨特石灰岩矿及乌勇布拉克盐矿采矿权评估报告，标的均为石灰岩、盐矿等非金属矿产。',
                embed='pdf')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104143319-marimaca-secures-grid-connection-authorization-for-marimaca-oxide-deposit',
                'SMM 国际站', '10-01',
                'Marimaca 获智利氧化矿项目电网接入授权',
                'SMM 国际站报道，Marimaca Copper 就智利 Marimaca 氧化矿项目取得电网接入授权，为项目开发所需电力供应扫清关键许可障碍。',
                orig_title='Marimaca Secures Grid Connection Authorization for Marimaca Oxide Deposit')),

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
