# -*- coding: utf-8 -*-
"""
生成 2026-10-07 矿业资讯速览 index.html（周三 · 国庆假期第 7 天 · 假期最后一日）
- 10-06 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-08）回补历史条目
- 换入 10-07 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-30 收盘（现算）
  + LME 卡片=走势图末点口径 10-06 收盘（周三国庆假期国内休市），
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

REPORT = '2026-10-07'
GRAB = '2026-10-07'
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
                         r'\g<1>2026年10月07日 星期三', html)
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
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104144028-one-bullion-completes-second-vumba-drill-hole-in-botswana',
                'SMM 国际站', '10-06',
                'One Bullion 博茨瓦纳 Vumba 金矿完成第二个金刚石钻孔',
                'SMM 国际站报道，One Bullion 已完成博茨瓦纳东北部 Vumba 金矿约 3,000 米金刚石钻探计划的第二个孔：VUDD018 在 Central–Makoba 靶区钻至 350.85 米，第三个孔 VUDD019 已开钻。现场编录见多次硅化—碳酸盐化蚀变、石英—碳酸盐脉及毒砂（含少量黄铁矿）。公司称该斜孔提供了 Central–Makoba 体系的第二个构造视角，将用于三维地质建模；但 VUDD018 尚无化验结果，蚀变与硫化物并不等于金品位或矿化宽度，须待实验室结果与 QA/QC 复核后方可评价。',
                orig_title='[SMM Gold flash] One Bullion completes second Vumba drill hole in Botswana')),

    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104144081-goldmining-intersects-400-m-of-gold-copper-mineralization-at-yarumalito-in-colombia',
                'SMM 国际站', '10-06',
                'GoldMining 哥伦比亚 Yarumalito 项目 YAR-45 自地表见矿 399.9 米',
                'SMM 国际站报道，GoldMining 公布其全资拥有的哥伦比亚安蒂奥基亚省 Yarumalito 金铜项目 2026 年金刚石钻探首批化验结果。钻孔 YAR-45 自地表至孔底 399.9 米连续见矿，品位金 0.34 克/吨、铜 0.09%、银 1.21 克/吨，折合金当量 0.45 克/吨；其中包含 74.7 米（金当量 0.61 克/吨）、47.0 米（0.70 克/吨）与 36.0 米（0.65 克/吨）三个较高品位段。公司认为结果支持 P-1 侵入体相为主要含矿体的连续性判断，YAR-46/47/48 三个孔化验结果待出。',
                orig_title='GoldMining Intersects 400 m of Gold-Copper Mineralization at Yarumalito in Colombia')),

    (CAT_ZK, ni('https://www.mining.com/canterra-grows-newfoundland-copper-resource-55-as-grades-fall',
                'MINING.COM', '10-06',
                'Canterra 纽芬兰 Lundberg 铜锌矿探明资源量增 55% 至 2,610 万吨',
                'MINING.COM 报道，Canterra Minerals（TSXV: CTM）更新其全资拥有的纽芬兰 Buchans 项目 Lundberg 铜锌矿资源量：探明（Indicated）资源量增 55% 至约 2,608 万吨，品位铜 0.36%、锌 1.31%、铅 0.56%、银 5.02 克/吨、金 0.06 克/吨（2019 年为 1,679 万吨、铜 0.42%），含铜约 9.48 万吨、锌 34.16 万吨、铅 14.62 万吨，铜当量增 34% 至约 22.62 万吨。本次估算纳入 2024 年收购以来完成的 4,779 米钻探，约 97% 资源量属探明级；另有约 6,000 米钻探结果待出。',
                orig_title='Canterra grows Newfoundland copper resource 55% as grades fall')),

    (CAT_MA, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/kfjs/202609/t20260914_10313021.htm',
                '全球矿产资源信息系统', '09-14',
                '摩洛哥布马丁铅锌银金项目经济性提升，税后净现值 35 亿美元',
                '全球矿产资源信息系统援引 Mining.com 报道，因上调金银价格假设，阿雅金银公司（Aya Gold & Silver）摩洛哥布马丁（Boumadine）铅锌银金项目税后净现值增长一倍至 35 亿美元，初步投资仅增 4% 至 4.63 亿美元，矿山可采年限由 11 年扩至 14 年。按金 3,500 美元/盎司、银 50 美元/盎司测算，内部收益率 93%、回报期 0.7 年。项目位于拉巴特东南约 340 公里、已持采矿证，计划 2027 年下半年开展可行性研究；公司正实施 40 万米钻探。',
                )),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202609/t20260921_10319570.htm',
                '全球矿产资源信息系统', '09-21',
                '尼日利亚矿警执法致 37 名被拘留者死亡，尼日尔州暂停采矿',
                '全球矿产资源信息系统援引 Mining.com 报道，尼日利亚安全与民防部队在明纳附近矿区逮捕数十人后，9 月 17 日清晨发现 37 名被拘留者死亡，引发抗议并招致对该国矿业执法行动的审查。尼日尔州 18 日宣布暂停所有采矿活动并实施全天候宵禁，州政府已成立调查组、下令尸检；内政部长暂停该州民防部队指挥官职务，等待联邦调查。该州 2024 年登记的 880 家矿业公司及合作社中仅 261 家通过资质备案；矿警 2024 年 3 月至今年 8 月取缔 108 处非法采矿点、逮捕 743 人。',
                )),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104144024-bullion-falls-09-as-weekly-decline-reaches-34',
                'SMM 国际站', '10-06',
                '现货黄金周线跌约 3.4%，铂钯同步走弱',
                'SMM 国际站援引路透社数据（原文注明为 10 月 2 日市场快照，非实时报价）：10 月 2 日 18:33 GMT 现货黄金跌 0.9% 至 4,140.06 美元/盎司，全周跌约 3.4%；美国黄金期货收跌 1% 至 4,162.30 美元/盎司。尽管美国 9 月非农就业增幅弱于预期，金价仍回吐了此前逾 1% 的涨幅——高企的国债收益率与美元周线走强共同压制了无息资产。铂金跌 2% 至 1,692.90 美元/盎司，钯金跌 0.5% 至 1,165.75 美元/盎司，主要贵金属周线齐跌。',
                orig_title='Bullion falls 0.9% as weekly decline reaches 3.4%')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104143760-smm-nickel-flash-news-indonesia-update-october-5-2026',
                'SMM 国际站', '10-05',
                'SMM：印尼镍矿 CIF 报价持平，10 月上半月 HMA 下调 2.25%',
                'SMM 国际站数据显示，印尼镍矿 CIF 均价整体持稳：1.2% 品位 25.5 美元/湿吨、1.3% 品位 27.5 美元/湿吨、1.4% 品位 48.7 美元/湿吨、1.5% 品位 54.2 美元/湿吨、1.6% 品位 59.0 美元/湿吨，均与上期持平。上游方面，随着新增 RKAB 配额陆续进入市场、卖方降价压力上升，镍矿价格已较 9 月下旬走弱，部分矿石报价跌破 HPM 基准；10 月上半月镍 HMA 下调至 16,322.67 美元/吨，较 9 月下半月的 16,698 美元/吨下降 375.33 美元（2.25%）。',
                orig_title='[SMM Nickel Flash News] Indonesia Update — October 5, 2026')),

    (CAT_SC, ni('https://news.smm.cn/news/104144078',
                '上海有色网', '10-06',
                '期货日报：铜价年内屡创新高，四季度最大变数是美国 232 铜关税',
                '上海有色网转载期货日报分析文章：2026 年前三季度铜价中枢持续上移，9 月 10 日 LME 三个月期铜盘中触及 14,875 美元/吨创历史新高，沪铜主力当日站上 112,330 元/吨。基本面看，2026 年全球铜矿供给增速预计仅 0.58%，低于精炼铜需求 1.90% 的增速，全球过剩量由 2025 年 46.9 万吨降至 25 万吨，铜精矿加工费持续恶化。进入四季度，矿端紧缺、冶炼减产与库存迁移仍提供支撑，但美国「232 铜关税」最终走向及美国铜库存能否回流，将成为影响铜价的重要变量。',
                )),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://geoglobal.mnr.gov.cn/zx/kysc/gxxs/202609/t20260919_10318181.htm',
                '全球矿产资源信息系统', '09-19',
                '伍德麦肯兹：六大铁矿石生产商十年耗竭储量 111 亿吨',
                '全球矿产资源信息系统援引矿业周刊（Miningweekly）与彭博社报道，伍德麦肯兹称由于寻找储量替代的成本和复杂性上升，全球最大铁矿石生产商储量耗竭速度快于补充。报告显示，包括必和必拓、力拓在内的全球六大铁矿石生产商 2016—2025 年可采储量耗竭 111 亿吨，同期仅三家企业储量替代达到平衡，部分公司新增储量成本是其他公司的 5 倍。铁矿石品位持续下降，部分矿企品位自 2016 年以来下降 1.6 个百分点；行业现金利润率 2021 年见顶后稳定在每吨 50~60 美元，利润空间随成本上升与价格下跌而收窄。',
                )),

    (CAT_HY, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsyj/202609/t20260909_10309842.htm',
                '全球矿产资源信息系统', '09-09',
                '巴西稀土公司一期冶金试验厂投产，产出首批稀土精矿',
                '全球矿产资源信息系统援引矿业周刊报道，澳交所上市企业巴西稀土公司（BRE）在巴西卡马萨里的一期冶金试验厂已成功投产并产出首批稀土精矿，将用于阿尔托山（Monte Alto）稀土矿山及拟建卡马萨里冶炼中心矿床可行性研究所需的冶金试验。公司称已获得计划 2027 年二季度投产的二期湿法冶炼厂的联合投资与技术支持，二期将生产镨钕氧化物、重稀土精矿和铀黄饼，目标将净单位成本降至每公斤镨钕当量 21 美元以下；巴西 SENAI 已承诺提供 170 万澳元资金（约占该厂投资与运营支出 59%）。',
                )),

    (CAT_HY, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsyj/202609/t20260911_10312022.htm',
                '全球矿产资源信息系统', '09-11',
                '智利铜业公司 7 月铜产量同比降 5%，埃斯康迪达降 22.1%',
                '全球矿产资源信息系统援引 Mining.com 与路透社报道，智利铜业委员会统计显示，智利国家铜业公司（Codelco）7 月铜产量 11.28 万吨，同比下降 5%，延续主要矿山运营困难带来的萎缩趋势。必和必拓控股的埃斯康迪达（Escondida）铜矿产量 8.94 万吨、下降 22.1%；英美集团与嘉能可合资的科亚瓦西（Collahuasi）铜矿产量 3.84 万吨、增长 12.3%。7 月智利全国铜产量下降 9.4%，统计机构归因于北部恶劣天气与主要矿山运维；Codelco 曾预计 2026 年智利铜产量下降约 2.5%，明年回升。',
                )),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104144079-smm-analysis-rubaya-ownership-conflict-and-the-global-tantalum-trade',
                'SMM 国际站', '10-06',
                'SMM 分析：刚果（金）鲁巴亚钽铌矿区权属、冲突与全球钽贸易',
                'SMM 国际站发布分析文章指出，刚果（金）东部马西西地区的鲁巴亚（Rubaya）矿区供应全球大部分钶钽铁矿（coltan），是钽这一电子等高端工业用金属的重要来源。文章梳理了该矿区的权属演变、正规化努力与 M23 武装接管过程，并分析了其贸易路线、税费与矿工面临的风险。分析强调，开采者、矿权持有者与收取矿石流通费用者长期并非同一群体，这一分离既解释了鲁巴亚的重要性，也解释了当地冲突反复发生的原因；鲁巴亚对全球钽供应具有实质影响，但其确切贡献仍待进一步研究。',
                orig_title='[SMM Analysis] Rubaya: Ownership, Conflict and the Global Tantalum Trade')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104144021-afaq-outlines-us146-million-egyptian-investment-plan',
                'SMM 国际站', '10-06',
                '埃及 Afaq 拟投 1.46 亿美元开发西加贝尔埃尔巴金矿',
                'SMM 国际站援引路透社报道，埃及私营矿企 Afaq Mining 董事长在 9 月 28—29 日埃及矿业论坛期间表示，公司在东南部沙漠西加贝尔埃尔巴（West Gabal Elba）特许区已探明一处含金约 30.5 万盎司的矿床，计划未来四至五年投入约 1.46 亿美元用于进一步勘探与初期生产设施建设。该披露为埃及现代黄金生产在 Sukari 之外增添了一个潜在来源，也支撑政府将全国年产金量由约 50 万盎司提升至 2030 年 80 万盎司的目标。路透社未将该数字认定为可采储量，商业生产仍取决于后续技术工作、许可与融资。',
                orig_title='Afaq outlines US$146 million Egyptian investment plan')),

    (CAT_GJ, ni('https://www.mining.com/discovery-silver-project-clears-key-mexico-hurdle',
                'MINING.COM', '10-06',
                'Discovery Mining 墨西哥 Cordero 银矿获环境与土地用途许可',
                'MINING.COM 报道，Discovery Mining（TSX: DSV）称已获得墨西哥政府两项关键许可——环境部（SEMARNAT）批准了 Cordero 银矿项目的环境影响评价与土地用途变更许可，使该加拿大矿企得以推进项目建设。Cordero 位于奇瓦瓦州，为银铅锌金多金属项目，公司称许可获批是项目进入开发阶段的重要节点。该矿与铅锌银金共生，属墨西哥近年推进的主要银矿开发项目之一。',
                orig_title='Discovery silver project clears key Mexico hurdle')),

    (CAT_GJ, ni('https://www.mining.com/beaver-creek-video-gold-gains-new-role-vs-bonds',
                'MINING.COM', '10-06',
                '观点：黄金正取代债券成为货币替代，或为结构性转变',
                'MINING.COM 报道，Sprott 管理合伙人 John Hathaway 与 Incrementum 合伙人 Ronald-Peter Stöferle 在科罗拉多州 Beaver Creek 贵金属峰会上表示，黄金作为政府债券与美元货币替代品的角色日益凸显，可能标志着结构性转变而非又一轮周期性牛市。两人指出，央行持续购金、去美元化趋势与黄金在储备中的比重上升是主要支撑。与以往不同的是，黄金与债券传统的反向关系正在发生变化。',
                orig_title='Beaver Creek video: Gold gains new role vs bonds')),

    (CAT_GJ, ni('https://www.mining.com/beaver-creek-minings-next-generation-takes-the-wheel',
                'MINING.COM', '10-06',
                'Beaver Creek：矿业进入代际交接，新一代高管走上台前',
                'MINING.COM 报道，在 Beaver Creek 贵金属峰会的一个论坛上，主持人 Paul Harris 与 Heliostar Metals、First Majestic Silver、Elemental Royalty 等公司高管讨论了矿业正在经历的代际交接：随着资深创始人逐步退居二线，一批更年轻的经营者需要在不断变化的商品周期中证明自己能建立可持续的公司。与会者认为，判断标准正从「找到矿」转向「建成并运营矿山、跨越周期交付现金流」，资本纪律与项目执行力成为新一代管理层的核心考题。',
                orig_title="Beaver Creek: Mining's next generation takes the wheel")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/greenland-mines-authorizes-20m-share-buyback',
                'MINING.COM', '10-06',
                'Greenland Mines 授权 2,000 万美元股份回购',
                'MINING.COM 报道，Greenland Mines（纳斯达克：GRML；法兰克福：HK6）宣布授权一项 2,000 万美元（约 2,846 万加元）的股份回购计划。该决定是在公司近期完成逾 5,900 万美元新融资之后作出。授权允许公司通过公开市场交易不时回购至多 2,000 万美元的已发行普通股。公司旗下主要资产为格陵兰东南部 Skaergaard 金—铂族—钒钛磁铁矿项目，矿种涵盖金、铜、钴、铂族及稀土等。',
                orig_title='Greenland Mines authorizes $20M share buyback')),

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
