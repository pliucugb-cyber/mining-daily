# -*- coding: utf-8 -*-
"""
生成 2026-11-16 矿业资讯速览 index.html（周一 · 补跑）
- 11-14 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-16）回补历史条目
- 换入 11-16 采集的周末/周五未收录条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-13 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；
  电解钴保留上日 SMM 值并标注
- 矿权条目：今日新增公告走 #rightsCards 既有窗口，不进主列表
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

REPORT = '2026-11-16'
GRAB = '2026-11-16'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年11月\d{2}日 星期.',
                         r'\g<1>2026年11月16日 星期一', html)
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
    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/SVSCLYJYGQBWDTVKKZJIDQNKJ5YEQI5Q2XA7QII',
                '上海有色网', '11-13',
                '欧盟拟推迟对英国产电动汽车征收 10% 关税，2027 年生效节点或再延',
                '据英国《金融时报》报道，欧盟委员会正就推迟对英国制造电动汽车征收 10% 进口关税征询行业意见。脱欧后原产地规则要求英欧零部件含量不低于 55%、电池电芯与模组不低于 65%、电池包不低于 70%，2023 年已推迟三年实施；若不再延期，相关关税将于 2027 年 1 月生效，届时约 70% 的英产纯电与插混车型受影响。英国汽车制造商和贸易商协会曾估算，若无法达成长期方案，车企可能需支付合计 14 亿英镑（约 18.6 亿美元）关税。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/WNHQAQNHNU27JKFJBPS6DVBBNIPH7I3SVSKUHQA',
                '上海有色网', '11-14',
                'LME 锡现货升水飙至 715 美元/吨，创三年多新高',
                '11 月 13 日 LME 现货锡对三个月期锡升水升至每吨 715 美元，前一日为 264 美元、一周前仅 46 美元，为 2023 年 7 月以来最强水平。6 月中旬以来 LME 锡库存累计下降 59% 至 3,740 吨，接近一年低位；三个月期锡报约 46,800 美元/吨。国际锡业协会分析师称中国投机抛盘放大了回调，LME 数据显示一名市场参与者持有 80% 至 89% 的仓单。')),

    (CAT_SC, ni('https://www.mining.com/copper-shortage-or-surplus-banks-split-on-2027-outlook/',
                'MINING.COM', '11-13',
                '德银看多铜价至 10 美元/磅，高盛警示 2027 年预测面临下行',
                '德意志银行金属研究主管表示，全球可见铜库存或已降至 2006 年以来最低，预计到 2026 年底仅 30% 库存可自由购买，2027 年中期铜价可能升至每磅 10 美元，并把当前定性为「流动性危机」而非需求故事；高盛则称其 2027 年 15,400 美元/吨的预测面临下行风险，若持仓不变均价约 14,600 美元/吨。国际铜研究小组预计 2027 年全球精炼铜过剩将增至三倍以上。',
                orig_title='Copper shortage or surplus? Banks split on 2027 outlook')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://www.mining.com/rare-earths-americas-doubles-mineralized-zone-at-homer-project-in-brazil/',
                'MINING.COM', '11-12',
                '巴西 Homer-A 稀土矿化带扩大逾 60%，最长延伸约 4.3 公里',
                'Rare Earths Americas 公布巴西戈亚斯州 Homer-A 靶区 8 个新钻孔化验结果，矿化面积由 9 月披露的 2.15 平方千米扩大至约 3.5 平方千米、增幅逾 60%，最长延伸由 2.1 公里增至约 4.3 公里且仍未封闭。主异常内已收到化验的 20 个钻孔中 19 个见矿，东南缘单样镝铽氧化物占稀土氧化物加钪总量最高达 8.7%，公司计划 2027 年完成首份矿产资源量估算。',
                orig_title='Rare Earths Americas doubles mineralized zone at Homer project in Brazil')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261114_10363271.htm',
                '矿业权市场', '11-13',
                '广西龙州金龙矿区外围铝土矿探矿权成交，新翔生态铝业竞得',
                '广西龙州县金龙镇金龙矿区外围铝土矿勘查探矿权网上挂牌成交结果公示，竞得人为广西龙州新翔生态铝业有限公司，成交时间 2026 年 11 月 10 日，勘查面积 20.9424 平方千米，公示文号桂资交探出公示〔2026〕19 号。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202611/t20261114_10363279.htm',
                '矿业权市场', '11-13',
                '广东新丰上磜金多金属矿普查探矿权挂牌，起始价 72 万元',
                '广东省自然资源厅委托广州公共资源交易中心，于 2026 年 11 月 13 日至 12 月 25 日挂牌出让新丰县上磜金多金属矿普查探矿权，勘查面积 23.73 平方千米、勘查工作程度为普查、拟出让年限 5 年，起始价 72 万元、出让收益率 2.3%，公告文号 K〔2026〕022 号。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261114_10363270.htm',
                '矿业权市场', '11-13',
                '河北承德米仓沟门金矿详查探矿权转让公示',
                '河北省自然资源厅公示承德县三家乡米仓沟门金矿详查探矿权转让，转让人为秦皇岛荣源地质勘查有限公司，受让人为承德县铭金元矿业有限公司，勘查面积 3.1892 平方千米，勘查许可证有效期至 2030 年 5 月 20 日，公示文号冀探矿交易示字〔2026〕7 号。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.mining.com/capstone-cuts-copper-outlook-as-restart-slips/',
                'MINING.COM', '11-13',
                'Capstone 下调铜产量指引下限至 19.5 万吨，Pinto Valley 复产推迟',
                'Capstone Copper 因亚利桑那 Pinto Valley 主破碎机需由原厂制造额外部件、全面复产推迟至 12 月中旬，将年度铜产量下限下调 5,000 吨至 195,000 吨（原区间 20 万至 23 万吨）。第三季度产铜 45,218 吨、同比下降 18%，其中 Pinto Valley 产铜 6,358 吨、上年同期为 9,949 吨；智利卡车司机全国罢工亦对发运构成风险。',
                orig_title='Capstone cuts copper outlook as restart slips')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-11-14/1225670320.PDF',
                '巨潮资讯网', '11-14',
                '常铝股份控制权变更获济南市国资委批复，转让价 5.79 元/股',
                '常铝股份公告收到济南市国资委批复，同意齐鲁财金投资集团将所持 231,110,118 股（占总股本 22.38%）协议转让给山东济新产业发展有限公司，转让价 5.79 元/股、总价约 13.38 亿元；交易完成后控股股东变更为济新产发，实际控制人由济南市国资委变更为济南新旧动能转换起步区管委会。事项尚需深交所合规性确认并办理过户登记。',
                embed='pdf')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/freeport-strikes-110m-deal-for-bc-copper-stake/',
                'MINING.COM', '11-13',
                'Freeport 以 7,720 万美元收购 TDG 旗下 Aurora West 项目 51% 权益',
                'Freeport-McMoRan 同意支付 7,720 万美元（1.10 亿加元）收购 TDG Gold 在不列颠哥伦比亚省 Aurora West 铜金项目两家持股公司中各 51% 的权益，并可通过投入 8,000 万美元勘探、再向 TDG 支付 4,000 万美元将持股提升至 75% 及两家公司 100%。交易将把相邻矿权并入 Freeport 与 Amarc 的 Toodoggone 地区合作范围，TDG 保留 25% 权益与 2% 净冶炼权益金。',
                orig_title='Freeport strikes $77M deal for BC copper stake')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/anglo-americans-australia-exit-marks-end-of-an-era/',
                'MINING.COM', '11-13',
                '英美资源 39 亿美元出售澳洲炼焦煤资产，布里斯班招牌拆除',
                '英美资源（Anglo American）开始拆除布里斯班办公楼的标识，为把澳洲炼焦煤业务交割给 Dhilmar Limited 做准备。公司 5 月同意以最高 39 亿美元（含 23 亿美元预付款）出售该资产组合，交易预计 2027 年一季度完成交割；澳洲业务 27 年间累计用工逾 10 万人，首席执行官的交接将在交割或 12 月 31 日孰早生效。出售是其与泰克资源合并组建 Anglo Teck 的重组一环。',
                orig_title="Anglo American's Australia exit marks end of an era")),

    # ── 💰 并购与投资（11-16 补采：中国稀土重组预案）────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-14/1225671885.PDF',
                '巨潮资讯网', '11-14',
                '中国稀土 39.41 元/股发行股份收购中稀凉山 51% 股权，重组预案出炉',
                '中国稀土（000831）披露发行股份购买资产并募集配套资金暨关联交易预案：向控股股东中国稀土集团发行股份购买中稀（凉山）稀土有限公司 51% 股权，发行价 39.41 元/股，并向不超过 35 名特定对象募集配套资金。标的公司主营稀土矿采选与冶炼分离，产品为稀土精矿、碳酸稀土及稀土氧化物系列。公司股票自 11 月 2 日开市起停牌，将于预案披露后复牌；交易旨在解决同业竞争、履行集团公开承诺。',
                embed='pdf')),

    # ── 💼 矿权交易（11-16 补采：西藏矿业预挂牌）────────────────────
    (CAT_KQ, ni('http://static.cninfo.com.cn/finalpage/2026-11-14/1225671318.PDF',
                '巨潮资讯网', '11-14',
                '西藏矿业预挂牌转让白银扎布耶锂业 100% 股权',
                '西藏矿业（000762）拟通过上海联合产权交易所公开挂牌转让控股子公司白银扎布耶锂业 100% 股权，其中公司持股 63.125%、控股子公司西藏日喀则扎布耶锂业持股 36.875%，标的注册资本 32,000 万元。目前仅为正式挂牌前的预披露、征寻意向受让方，审计评估尚未完成，预计不构成重大资产重组；交易完成后白银扎布耶不再纳入公司合并报表范围。',
                embed='pdf')),

    # ── 🏭 行业动态（11-16 补采：西部黄金停产进展）──────────────────
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-11-14/1225671007.PDF',
                '巨潮资讯网', '11-14',
                '西部黄金新疆美盛继续停产，尾矿库二三期工程受强降雪影响',
                '西部黄金（601069）公告全资子公司新疆美盛因矿区持续强降雪、道路与电力供应受限，尾矿库二、三期合建工程无法继续施工，决定继续停产，待具备安全生产条件后复产，复产时间尚不确定。新疆美盛主要产品为金精矿，2025 年营业收入 168,777.27 万元、占公司 12.44%，净利润 17,616.55 万元、占 38.07%；2026 年 1—9 月营业收入 121,870.56 万元、占 8.41%。',
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

# —— 分桶 PIN（按内容口径：勘查成果属 🔍、政策属 📜、企业事故/产能属 🏭，勿被 _reclassify_ma 依「投资」二字拉到 💰）——
_PIN_CAT = [
    ('欧盟拟推迟', CAT_ZC),
    ('锡现货升水', CAT_SC),
    ('德银', CAT_SC),
    ('Homer', CAT_ZK),
    ('金龙矿区', CAT_KQ),
    ('上磜', CAT_KQ),
    ('米仓沟门', CAT_KQ),
    ('Capstone', CAT_HY),
    ('常铝股份', CAT_HY),
    ('Freeport', CAT_MA),
    ('英美资源', CAT_GJ),
    ('中国稀土 39.41', CAT_MA),
    ('白银扎布耶', CAT_KQ),
    ('新疆美盛', CAT_HY),
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
