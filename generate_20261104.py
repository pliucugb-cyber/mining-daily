# -*- coding: utf-8 -*-
"""
生成 2026-11-04 矿业资讯速览 index.html（周三）
- 11-03 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-06）回补历史条目
- 换入 11-04 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 11-03 收盘 + LME 11-03 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目：11-04 增补 1 宗（河南叶县 3 宗岩盐矿详查探矿权挂牌，首宗 5.5093 平方千米），
  已写入 data/news_2026-11.json，由 news-data.js 直出 #rightsCards，不进主列表
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

REPORT = '2026-11-04'
GRAB = '2026-11-04'
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
                         r'\g<1>2026年11月04日 星期三', html)
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
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475148',
                '中国有色金属报', '11-03',
                '江西九曲山探获钨铁银多金属矿，3 孔累计揭露白钨矿体 77 条',
                '江西省地质调查勘查院基础地质调查所与中国地质科学院联合完成的「铁下找钨：江西省莲花县新发现九曲山钨铁银多金属矿」成果，获评中国地质调查局 2025 年度地质调查十大进展。团队以重力识别隐伏岩体、磁法圈定靶区、音频大地电磁定位成矿层位的「物探+地质」路线，在厚覆盖区圈定 7 组地球物理组合异常。ZK01 设计孔深 650 米、终孔 1,035.57 米，累计见 88 层白钨矿化、边界品位以上矿体 18 条；2025 年 ZK02、ZK03 接续见矿，3 孔合计揭露白钨矿体 77 条，三氧化钨品位 0.07% 以上矿化段累计视厚度 76.29 米。2026 年 ZK05 另见铜矿化线索，ZK501 已于 9 月中旬开钻。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104200390',
                '上海有色网', '11-02',
                '宜春国轩水南矿区锂矿项目环评拟受理，公示期 10 个工作日',
                '宜春市生态环境局公示，拟受理宜春国轩矿业有限责任公司江西省宜丰县水南矿区锂矿项目环境影响评价文件，公示期为 2026 年 11 月 2 日至 11 月 13 日，共 10 个工作日。公众可通过环评科电话 0795-3998291 反馈意见；按环评政府信息公开指南，公示文本不含涉及国家秘密、商业秘密、个人隐私的内容。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104202587',
                '上海有色网', '11-03',
                '世界黄金协会：三季度全球央行净购金 321 吨，上调全年购金预期',
                '世界黄金协会报告显示，2026 年三季度各国央行净购金 321 吨，同比增长 42%，创 2024 年四季度以来最高季度水平；前三季度累计净购金 675 吨，略高于去年同期，协会据此将全年预期上调至至少与 2025 年的 848 吨持平。三季度中国、波兰分别买入 63 吨和 41 吨，俄罗斯净卖出 19 吨；同期全球黄金 ETF 持仓增加 211 吨创历史新高，金条金币需求同比降 19% 至 268 吨，珠宝需求降 17% 至 313 吨，全球矿产金产量同比增 3% 至 1,071 吨。')),

    (CAT_SC, ni('https://news.smm.cn/news/104200551',
                '上海有色网', '11-03',
                '印尼 9 月镍铁出口 975,848 吨，对中国出口占比 96.47%',
                '印尼 9 月镍铁出口量为 975,848 吨，其中对中国出口 941,411 吨、占比 96.47%。同期镍锍出口 34,111 吨，对中国出口 20,658 吨、占比 60.56%；镍湿法冶炼中间产品出口 156,926 吨，全部流向中国；未锻轧的非合金镍出口 11,619 吨，对中国出口 7,969 吨、占比 68.59%。')),

    (CAT_SC, ni('https://news.smm.cn/news/104200235',
                '上海有色网', '11-02',
                '印尼 9 月铝出口量环比下降 37%，1—9 月累计 799,199 吨',
                '印尼统计局数据显示，9 月该国铝出口量环比下降 37%，当月主要出口目的地为克罗地亚、泰国、土耳其和韩国。8 月印尼铝出口量为 157,222 吨；今年 1—9 月，该国原铝和未加工铝合金出口总量为 799,199 吨。')),

    (CAT_SC, ni('https://news.metal.com/newscontent/104202585-smm-analysis-silver-production-drops-503-in-october-2026-pv-sector-sees-1348-decline',
                'SMM 国际站', '11-03',
                'SMM：10 月 1# 白银产量环比降 5.03%，光伏用银降 13.48%',
                'SMM 数据显示，2026 年 10 月 1# 白银产量环比下降 5.03%，全年累计产量约 16,000 吨、同比增长 3.72%。减产主因是国庆假期再生银基本停产，以及部分铜冶炼区检修导致副产银减量。光伏方面，10 月硝酸银产量环比降 13.48%，2026 年累计约 6,000 吨、同比下降 17.59%；截至 10 月 29 日 SMM 社会库存较上月末去库约 68 吨。',
                orig_title='[SMM Analysis] Silver Production Drops 5.03% in October 2026, PV Sector Sees 13.48% Decline')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/104200332',
                '上海有色网', '11-02',
                '天赐材料枝江 30 万吨电解液项目一期环评公示，总投资 67,000 万元',
                '10 月 30 日，天赐材料（宜昌）新能源有限公司年产 30 万吨（一期 15 万吨）电解液项目环境影响报告书（征求意见稿）公示。项目位于湖北省宜昌市枝江市姚家港化工园，总投资 67,000 万元，一期建设规模 15 万吨电解液，二期作为规划预留、不纳入本次评价。公司印尼 2 万吨电解液项目预计 2026 年 12 月进入试生产。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475140',
                '中国有色金属报', '11-03',
                '有色协会：前三季度有色金属行业盈利水平实现跨越式提升',
                '中国有色金属工业协会陈学森表示，在地缘冲突持续、大宗商品价格波动加剧的外部环境下，依托完备的产业体系，叠加人工智能产业快速扩容与能源转型推进，前三季度行业生产、外贸、效益等核心指标均呈积极向好态势，运行基本面稳固。外贸规模大幅攀升，黄金产品成为核心增量，前三季度有色金属产品进出口总额持续增长。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475153',
                '中国有色金属报', '11-03',
                '云南铜业前三季度归母净利 26.0 亿元，同比增 47.86%',
                '云南铜业三季报显示，前三季度实现营业收入 1,638.55 亿元、同比增长 24.78%，归母净利润 26.0 亿元、同比增长 47.86%。公司称铜综合加工成本、铜精矿单位生产成本两项核心指标持续优化；重点地质勘探项目有序推进，资源储备基础不断夯实，一批关键产业升级项目建设加速落地。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475112',
                '中国有色金属报', '11-02',
                '长沙有色院炼锌渣协同处置技术达国际领先，已建成 28.7 万吨/年产线',
                '长沙有色冶金设计研究院自主研发的「炼锌渣绿色协同处置及资源高效利用技术」通过中国有色金属工业协会组织的专家评价，整体达到国际领先水平。我国每年产出湿法炼锌渣超 500 万吨，该技术以铅精矿为贵金属捕集剂，使铜、银、铅等有价金属高效进入粗铅。2022 年 6 月该技术在深圳市中金岭南丹霞冶炼厂落地，建成一条年处理 28.7 万吨废渣废料的生产线并运行至今。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-04/1225655587.PDF',
                '巨潮资讯网', '11-04',
                '厦门钨业收购江西巨通实业 30.1683% 股权事项披露进展',
                '厦门钨业 11 月 4 日发布公告，就收购江西巨通实业有限公司 30.1683% 股权暨关联交易的进展情况进行披露。该交易构成关联交易，公告未在标题层面给出对价与交割安排，具体条款以公告全文为准。',
                embed='pdf')),

    (CAT_MA, ni('https://www.mining.com/acgs-220-million-blue-moon-deal-creates-european-copper-giant',
                'MINING.COM', '11-03',
                'ACG 以 2.2 亿美元收购 Blue Moon 挪威资产，打造欧洲铜业新巨头',
                '伦敦上市的 ACG Metals 宣布以 2.2 亿美元全股票交易收购 Blue Moon Metals 的挪威资产，其中包括北挪威 Nussir 铜矿 94.52% 股权，与公司位于土耳其的 Gediktepe 矿山形成两大核心资产。公司预计合并后年产铜将超过 5 万吨。',
                orig_title="ACG's $220 million Blue Moon deal creates European copper giant")),

    (CAT_MA, ni('https://www.mining.com/mmg-anglo-american-extend-500-million-nickel-deal-deadline',
                'MINING.COM', '11-03',
                '五矿资源与英美资源将 5 亿美元巴西镍交易截止日延至 12 月 31 日',
                '五矿资源（HKEX: 1208）与英美资源（LON: AAL）将 5 亿美元巴西镍矿交易的最终截止日由 10 月 31 日延长至 2026 年 12 月 31 日，以避免在未获监管批准的情况下终止交易。欧盟监管机构正在审查该交易对区域不锈钢行业的潜在影响。',
                orig_title='MMG, Anglo American extend $500 million nickel deal deadline')),

    (CAT_MA, ni('https://www.mining.com/standard-nears-lithium-investment-decision',
                'MINING.COM', '11-03',
                'Standard Lithium 拟年底敲定阿肯色州锂项目投资决定',
                'Standard Lithium（TSXV/NYSE-A: SLI）计划在年底前就其 South West Arkansas 锂项目作出最终投资决定，项目资本开支约 14.5 亿美元，建成后将成为 Smackover 层系首个大型锂生产项目。该项目由公司与挪威油气生产商 Equinor 合资的 Smackover Lithium 推进，采用直接提锂（DLE）工艺。',
                orig_title='Standard nears lithium investment decision')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/jpmorgan-sees-us-copper-output-more-than-doubling',
                'MINING.COM', '11-03',
                '摩根大通：美国铜矿年产量有望翻倍以上，潜在新增产能 130 万吨',
                '摩根大通认为，通过新项目与扩产，美国年矿产铜产量有望增加 130 万吨、实现翻倍以上，扭转数十年下滑趋势，潜在供应增量位居全球第三、仅次于智利和阿根廷。但该行指出，这些产能多数要到 2030 年之后才能投产。',
                orig_title='JPMorgan sees US copper output more than doubling')),

    (CAT_GJ, ni('https://www.mining.com/canada-gold-output-jumps-22-as-global-supply-slips',
                'MINING.COM', '11-03',
                '加拿大三季度黄金产量同比增 22%，新投产矿山贡献主要增量',
                '世界黄金协会数据显示，加拿大三季度黄金产量同比增长 22%，跑赢全球增速，新投产矿山是主要推手。Equinox Gold 位于纽芬兰与拉布拉多的 Valentine 矿山、B2Gold 位于努纳武特的 Goose 矿山投产带动产量上升，同时成本上行推高单盎司生产成本。',
                orig_title='Canada gold output jumps 22% as global supply slips')),

    (CAT_GJ, ni('https://www.mining.com/i-80-golds-growth-faces-nevada-labour-squeeze',
                'MINING.COM', '11-03',
                'I-80 Gold 受内华达用工紧张拖累，全年产量落在指引下半区',
                'I-80 Gold（TSX/NYSE: IAU）预计全年产量落在 40,000 至 50,000 盎司指引区间的下半区，主因内华达州工人流动导致采矿进度放缓，公司股价下跌。公司维持产量指引不变，但 Granite Creek 高品位矿石接续延迟，Archimedes 矿山部分黄金产量将推迟至 2027 年初。',
                orig_title="I-80 Gold's growth faces Nevada labour squeeze")),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104202584-smm-flashdrc-mines-ministry-facilitates-return-of-artisanal-miners-to-mulondo-site-through-negotiated-arrangement',
                'SMM 国际站', '11-03',
                '刚果（金）矿业部协调手工采矿者重返 Mulondo 矿区作业',
                '11 月 2 日，刚果（金）矿业部长 Louis Watum Kabamba 监督采矿合作社 COMIKAN 成员在卢阿拉巴省 Mutshatsha 地区 Mulondo 矿区恢复作业，该矿距科卢韦齐东南约 42 公里。此前新运营方 PAJECLEM 接手 Chemaf 原有矿权后，手工采矿者被迫撤离并闲置一年有余；经协商，PAJECLEM 让出两个采矿区块给 COMIKAN 矿工，以划清作业范围、避免用地纠纷。',
                orig_title='DRC Mines Ministry Facilitates Return of Artisanal Miners to Mulondo Site Through Negotiated Arrangement')),

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
    ('九曲山', CAT_ZK),
    ('水南矿区', CAT_ZC),
    ('世界黄金协会', CAT_SC),
    ('印尼 9 月镍铁', CAT_SC),
    ('印尼 9 月铝', CAT_SC),
    ('白银产量', CAT_SC),
    ('天赐材料', CAT_HY),
    ('云南铜业', CAT_HY),
    ('长沙有色院', CAT_HY),
    ('有色协会', CAT_HY),
    ('厦门钨业', CAT_MA),
    ('Blue Moon', CAT_MA),
    ('五矿资源', CAT_MA),
    ('Standard Lithium', CAT_MA),
    ('摩根大通', CAT_GJ),
    ('加拿大三季度', CAT_GJ),
    ('I-80', CAT_GJ),
    ('Mulondo', CAT_GJ),
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
