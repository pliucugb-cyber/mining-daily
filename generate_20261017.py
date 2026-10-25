# -*- coding: utf-8 -*-
"""
生成 2026-10-17 矿业资讯速览 index.html（周六）
- 10-16 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-17）回补历史条目
- 换入 10-17 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-16 收盘 + LME 10-16 收盘（10-17 05:30 国内未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，tmp/add_rights_1017.py 注入），不进主页列表
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

REPORT = '2026-10-17'
GRAB = '2026-10-17'
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
                         r'\g<1>2026年10月17日 星期六', html)
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
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474627',
                '中国有色金属报', '10-15',
                '西北有色地矿集团赴津巴布韦开展地质矿业市场考察',
                '中国有色金属报报道，西北有色地矿集团代表团赴津巴布韦开展地质矿业市场考察，实地走访 MDL 金矿、One Step 金矿及环球铂业津巴布韦铂金矿等项目，围绕矿权办理、找矿增储、开发利用、矿业政策与劳动用工深入交流。代表团认为该国金等战略性矿产需求旺盛、成矿地质条件优越、找矿空间广阔，但基础地质调查和矿产勘查投入不足，矿业开发规范化、集约化水平亟待提升，拟将津巴布韦打造成集团海外地质矿业市场的重要支点。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474542',
                '中国有色金属报', '10-13',
                '水口山金信攻克冰铜含铅高难题，综合含铅量降至 7.68%',
                '中国有色金属报报道，衡阳水口山金信铅业公司通过优化回转炉配料与炉况调控攻克冰铜含铅高难题：利用铁屑置换原理精准优化铁屑、纯碱等熔剂配比，把铅元素从冰铜中析出富集至粗铅，同时紧盯原料成分波动动态调整熔炼温度、改善炉渣流动性。今年以来该公司外销 11 批次共 435.22 吨冰铜，综合含铅量稳定压在 7.68%，而技改前一度突破 13%。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474553',
                '中国有色金属报', '10-13',
                '从中国国际矿业大会透视全球矿业调整方向',
                '中国有色金属报分析第 28 届中国国际矿业大会，大会以「合作共赢、绿色智能」为主题在天津举行：加纳、哈萨克斯坦、老挝、苏丹、苏里南矿业部长与联合国贸发会议代表同台致辞，资源安全从储量产量延伸至贸易通道与产业链布局；刚果（金）驻华使馆设 100 余平方米展馆，希望在本地加工后再出口。大会发布的全球矿业发展报告显示，2025 年全球矿业融资额增长 1 倍以上至 214.30 亿美元，矿业交易金额增长 150.40%。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104162383',
                '上海有色网', '10-16',
                '碳酸锂主连 12 连跌创 2025 年 12 月以来新低',
                '上海有色网日评显示，10 月 16 日国内基本金属涨跌互现：沪镍跌 2.02% 领跌，沪铅跌 0.71%、沪锌跌 0.59%，沪锡涨 0.81% 领涨、沪铝涨 0.71%、沪铜涨 0.1%；氧化铝主连涨 1.54%。碳酸锂主连跌 4.2%、盘中最低下探 96240 元/吨，创 2025 年 12 月以来新低并录得 12 连跌；多晶硅主连涨 1.34%、工业硅主连涨 2.29%。贵金属方面，沪金涨 1.36%、沪银涨 2.49%，铂、钯主连分别涨 1.85% 和 1.9%；美元指数下跌 0.18% 报 101.82。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474555',
                '中国有色金属报', '10-13',
                '港交所将研究推出人民币计价黄金期货',
                '中国有色金属报报道，香港特区 2026 年施政报告提出深化全球离岸人民币业务和资本市场，港交所行政总裁陈翊庭表示国际投资者已重新把目光投向亚洲特别是中国市场，港交所会把推出以人民币计价的黄金期货列入考虑范围；她称港交所近期再次推出美元计价黄金期货后投资者反应热烈。此外，伦敦金属交易所在港认可仓库数量已有 10 余个但仍不足，需研究是否考虑寻找大型仓库以满足市场需求。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474629',
                '中国有色金属报', '10-15',
                '美银：短期金价难站稳 4000 美元/盎司',
                '中国有色金属报援引美国银行 10 月 12 日贵金属报告，预计 2026 年第四季度黄金均价为 4000 美元/盎司、2027 年均价有望升至 4813 美元/盎司，并认为未来 3 个月金价难以稳固站在 4000 美元/盎司上方；美银本月早些时候曾预计，能源价格居高不下、通胀担忧持续发酵可能推动金价在第四季度跌至 3750 美元/盎司。美银还指出，全球央行整体购金活动有所减弱，央行黄金持仓价值增长中约 90% 来自价格上涨带来的估值收益。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474631',
                '中国有色金属报', '10-15',
                '工业硅成本端有强支撑，四季度供需边际转弱',
                '中国有色金属报分析，10 月初焦煤期货价格大幅上行带动工业硅期价反弹；10 月国内四大主产区工业硅总产量 4.73 万吨、环比增加 810 吨、同比减少 6850 吨，多晶硅周度产量回落 0.45 万吨至 2.25 万吨，有机硅周度产量 4.25 万吨、环比下滑 6.4%。四季度电价抬升（原油煤炭涨价、电力市场化推进、西南枯水期）构成成本端强支撑，从新疆企业现金成本结构看电力成本占比近 40%、硅煤约占 20%。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474628',
                '中国有色金属报', '10-15',
                '美联储政策易紧难松，白银价格持续承压',
                '中国有色金属报分析，美联储 9 月议息会议全票通过加息 25 个基点、将联邦基金利率目标区间上调至 3.75%~4.00%，点阵图显示 18 位官员中有 16 人预计年内至少再加息 1 次，12 月加息概率回升至 80%~85%。世界白银协会预计 2026 年全球白银缺口将扩大至 4630 万盎司、较 2025 年 4030 万盎司增长 15%，为连续第 6 年供应短缺，其中光伏领域用银需求同比下降约 19%；上期所白银库存已从 9 月 11 日的 1407.5 吨升至 10 月 2 日的 1490.8 吨。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474540',
                '中国有色金属报', '10-13',
                '金川镍钴以闪速「悬浮+侧吹」强化熔炼破解产能瓶颈',
                '中国有色金属报报道，金川镍钴镍冶炼厂对闪速熔炼工艺实施提升改造，形成闪速「悬浮+侧吹」强化熔炼技术并实现镍精矿配上料智能化，「镍闪速熔炼系统产能提升研究与应用」经中国有色金属工业协会成果评价达到国际领先水平；针对低品位、高氧化镁复杂镍原料自主开发「侧吹浸没燃烧熔炼法+侧吹浸没燃烧还原硫化法+电炉贫化」技术，新型合金炉采用底吹连续进料、连续熔炼、连续吹炼工艺，两项成果均达国际先进水平且均为国内首创。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474434',
                '中国有色金属报', '10-09',
                '中国铜业复杂锌基资源绿色冶炼技术达国际领先水平',
                '中国有色金属报报道，由中国铜业所属呼伦贝尔驰宏牵头、联合昆明理工大学等单位历经 6 年攻关的「多杂难处理锌基物料绿色冶炼与资源高效回收技术及应用」项目通过中国有色金属工业协会科技成果评价，专家组认定整体技术达到国际领先水平；项目构建以氧压浸出—矿化沉铁为核心的短流程绿色冶炼新技术体系，建成国内规模最大的标杆工程，实现年产 14 万吨锌、6 万吨铅，并配套生产硫酸、白银、黄金、精铟及海绵镉、铜精矿、钴精矿等副产品。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474488',
                '中国有色金属报', '10-12',
                '金川镍钴：以全产业链协同对冲周期波动',
                '中国有色金属报报道，甘肃省金昌市的金川集团镍钴股份有限公司构建「保供压舱—产业配套—高端突破」三级递进产品体系：第一层级为保供压舱类基础金属，以金驼牌高纯电镍、电积钴为核心，在 2024—2025 年镍价下行周期中依靠品质实现市场升水、价格长期高于期货盘面；第二层级面向新能源动力电池等战略性新兴产业提供配套材料。公司副总经理孙治忠表示，只聚焦单一冶炼、单一产品就会被动承受周期冲击，故坚持「稳底盘、提弹性」双轮驱动。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474496',
                '中国有色金属报', '10-12',
                '包头稀土高新区以「研发贷」破解轻资产科创企业融资难',
                '中国有色金属报报道，包头稀土高新区构建多层次、全周期的科技金融服务体系，创新推行「一线工作法」把政银企对接会搬到生产一线；内蒙古自治区首家稀土光功能材料量产企业内蒙古国创稀品科技有限公司手握 16 项核心专利、4 条纳米级生产线全面投产，在订单增长带来原材料采购压力的情况下顺利拿到 300 万元中长期「研发贷」，破解了轻资产科创企业「有技术、有订单、缺抵押」的信用困局。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474495',
                '中国有色金属报', '10-12',
                '金洲公司新增 2 项微钻技改扩能项目，总投资约 3.79 亿元',
                '中国有色金属报报道，中钨高新所属深圳市金洲精工科技股份有限公司 8 月 20 日宣布新增 2 项重要技改扩能项目：「AI 高速高频印制电路板用高精密微型刀具技改扩能项目」预计总投资 1.9 亿元，「多层印制电路板用精密微型刀具技改扩能项目」预计总投资 1.89 亿元，建设期均为一年、第二年达产。这是该公司近一年来的第六次扩产，预计新增近 8 亿支产能，以满足 AI 算力产业链关键加工环节的供给需求。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/exiro-led-group-takes-control-of-vales-manitoba-nickel-complex',
                'MINING.COM', '10-16',
                'Exiro 牵头财团取得淡水河谷曼尼托巴镍矿 81.1% 股权',
                'MINING.COM 报道，Exiro Minerals、Orion Resource Partners 与加拿大增长基金（CGF）联合取得淡水河谷位于加拿大曼尼托巴省的汤普森（Thompson）镍矿业务 81.1% 股权，淡水河谷基本金属公司通过子公司保留 18.9% 少数股权，新成立的 Exiro Nickel 已接管运营。该综合体现有两座在产地下矿山、一座配套选矿厂，以及横跨 135 公里汤普森镍矿带的勘探机会，三方计划投资最高 2 亿美元；淡水河谷另签署多年期协议购买汤普森选矿厂产出的镍精矿。',
                orig_title='Exiro-led group takes control of Vale’s Manitoba nickel complex')),

    (CAT_GJ, ni('https://www.mining.com/minnova-maps-53m-restart-for-manitoba-gold-mine',
                'MINING.COM', '10-16',
                'Minnova 拟投 7600 万加元重启曼尼托巴 PL 金矿',
                'MINING.COM 报道，Minnova 公布 7600 万加元（约 5340 万美元）计划，拟于 2028 年让曼尼托巴省 Sherridon 附近的 PL 金矿（原名 Puffy Lake，1987 年 12 月至 1989 年 3 月曾运营）恢复生产。初步经济评估显示，投产后年均产金 62200 盎司、矿山寿命 10 年，采用高品位露天矿起步后转地下开采，现有选厂产能计划从 1000 吨/日扩建至 2000 吨/日，投资回收期约 8 个月；2025 年 9 月资源估算为探明及控制 376 万吨、品位 4.98 克/吨、含金 601158 盎司，推断 167 万吨、品位 3.78 克/吨、含金 202810 盎司。',
                orig_title='Minnova maps $53M restart for Manitoba gold mine')),

    (CAT_GJ, ni('https://www.mining.com/canadas-new-foreign-investment-rules-what-critical-minerals-miners-need-to-know',
                'MINING.COM', '10-17',
                '加拿大新规：关键矿产领域少数股权投资将强制预先申报',
                'MINING.COM 报道，加拿大将于 2027 年初实施《加拿大投资法》新规，把特定敏感领域外国投资者的部分非控制性少数股权投资纳入交割前强制申报；相关立法 2024 年已通过，触发条件包括外资在特定业务活动领域取得重大非公开技术信息或重大资产渠道，并附带治理等特殊权利，但「规定业务活动」清单尚未最终确定。律师预计多数被纳入交易会在 45 天国家安全审查期内通过，存疑交易审查期可长达 200 天或更久；加拿大于 2022 年曾要求三家中国企业剥离在加关键矿产公司持股。',
                orig_title="Canada's new foreign investment rules: What critical minerals miners need to know")),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104160533-trump-tariff-threat-builds-us-copper-stocks-above-1-million-tonnes-as-comex-lme-spread-narrows-to-310-usdtonne',
                'SMM 国际站', '10-16',
                '关税威胁推升美国铜库存破 100 万吨，COMEX—LME 价差收窄至 310 美元/吨',
                'SMM 国际站报道，美国加征关税的威胁推动美国铜库存突破 100 万吨，COMEX 仓库集中了全球约 70% 的显性库存；2 月关税研究后货物集中流向美国，推动 COMEX 铜价 9 月 22 日创下 6.83 美元/磅（约 15057 美元/吨）纪录，COMEX 与 LME 价差 7 月一度超过 3000 美元/吨、目前收窄至约 310 美元/吨。麦格理测算美国铜库存总量接近 160 万吨、COMEX 库存增长约 750% 至逾 71.4 万吨；15% 精炼铜进口关税原定 2027 年 1 月 1 日起实施、2028 年升至 30%，至今未决。',
                orig_title='Trump tariff threat builds US copper stocks above 1 million tonnes as COMEX-LME spread narrows to 310 USD/tonne')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104162926-smm-chromium-flash-south-africas-august-chrome-ore-exports-fall-11-as-ferrochrome-shipments-rebound-20',
                'SMM 国际站', '10-16',
                '南非 8 月铬矿出口降 10.75%，高碳铬铁出口增 20%',
                'SMM 国际站报道，2026 年 8 月南非铬矿出口环比下降 10.75% 至 236 万吨，高碳铬铁出口则增长 20.0% 至 117180 吨，贸易结构分化明显。中国仍是铬矿最大目的地，接收 167 万吨、占南非总出货量的 70.8%，但环比下降 6.09%；铬铁出口受北美需求支撑，加拿大接收 26373 吨、美国 26029 吨，两国合计占南非铬铁出口的 44.7%。',
                orig_title='[SMM Chromium Flash] South Africa’s August Chrome Ore Exports Fall 11% as Ferrochrome Shipments Rebound 20%')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-17/1225608736.PDF',
                '巨潮资讯网', '10-17',
                '山东黄金拟出资 4 亿元设立香港财资公司',
                '巨潮资讯网披露，山东黄金全资子公司山东黄金矿业（香港）有限公司拟与控股股东山东黄金集团全资子公司雅诚投资有限公司在香港共同出资设立山东黄金（香港）财资管理有限公司（暂定名），股份认购出资总额 10 亿元人民币、实行分阶段缴付，其中雅诚公司认购 6 亿元、持股 60%，矿业香港认购 4 亿元、持股 40%；初始阶段先缴付 3 亿元，后续拟逐步增资至 10 亿元。该议案经公司 10 月 16 日第七届董事会第二十一次会议以 7 票同意审议通过。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-17/1225608617.PDF',
                '巨潮资讯网', '10-17',
                '西藏藏青基金扩募 16 亿元，总规模增至 53.1 亿元',
                '巨潮资讯网披露，藏格矿业参与设立的西藏藏青新能源产业发展基金合伙企业（有限合伙）拟扩募 160000 万元，总规模从 371000 万元增至 531000 万元，并新增 4 名有限合伙人：宁波梅山保税港区新沙鸿运投资管理有限公司（公司持股 5% 以上股东）、贵州省黔晟国有资产经营有限责任公司、贵州磷化（集团）有限责任公司、湖北万润新能源科技股份有限公司。藏格矿业发展（海南）有限公司基于战略规划及资金安排不认购本次扩募份额，认缴出资 50000 万元不变，认缴比例由 13.48% 降至 9.42%。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-17/1225608669.PDF',
                '巨潮资讯网', '10-17',
                '国城矿业子公司签署碳酸锂购销合同，三年销量不低于 2 万吨',
                '巨潮资讯网披露，国城矿业控股子公司四川国城锂业有限公司与控股股东国城控股集团全资子公司天津国城贸易有限公司签署《碳酸锂购销合同》，约定自 2026 年 11 月至 2029 年 10 月国城锂业向天津国城销售电池级碳酸锂不低于 20000 吨，该交易构成关联交易、尚需提交股东会审议；定价以上海有色网交货月每日公布的电池级碳酸锂平均价月均价或广州期货交易所碳酸锂主力合约结算价月均价为基准，并设置合理阶梯折扣。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-17/1225608114.PDF',
                '巨潮资讯网', '10-17',
                '首华燃气拟获授权通过市场化方式购买铝土矿资源',
                '巨潮资讯网披露，首华燃气科技（上海）股份有限公司于 2026 年 10 月 16 日召开第六届董事会第二十三次会议，审议通过《关于授权通过市场化方式购买铝土矿资源的议案》，拟提请股东会授权董事会及经营管理层办理竞拍相关事宜；购买金额连续 12 个月内低于公司最近一个会计年度经审计总资产的 50%（不含 50%），授权期限自股东会审议通过之日起 12 个月内有效，资金来源为自有或自筹资金，参与竞拍项目为公开出让的矿产资源、预计不涉及关联交易。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-17/1225607853.PDF',
                '巨潮资讯网', '10-17',
                '中国稀土预计前三季度净利润同比增 88.96%~140.99%',
                '巨潮资讯网披露，中国稀土集团资源科技股份有限公司预计 2026 年前三季度归属于上市公司股东的净利润 36314 万元至 46314 万元，比上年同期 19218.33 万元增长 88.96%~140.99%；扣除非经常性损益后的净利润 36572.77 万元至 46572.77 万元、同比增长 98.63%~152.94%，基本每股收益 0.3422~0.4364 元/股。公司称受稀土行业政策、产业供需格局持续调整优化等多重有利因素影响，市场行情整体上行、部分产品价格较去年同期涨幅明显。',
                embed='pdf')),

    (CAT_MA, ni('https://news.smm.cn/news/104157606',
                '上海有色网', '10-16',
                '东方锆业预计前三季度净利润同比增 261.93%~365.34%',
                '上海有色网报道，东方锆业发布的前三季度业绩预告显示，公司预计 2026 年前三季度实现归属于上市公司股东的净利润 1.40 亿元至 1.80 亿元，同比增长 261.93%~365.34%。公司称业绩大幅增长主要因锆材料下游新兴应用领域需求快速增长、国产替代进程加快，主要产品量价齐升带动营业收入较快增长，同时通过工艺改良和设备改造降低原辅材料单耗与能源消耗、压降生产成本，并持续优化产品结构提升产能利用率。')),

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
