# -*- coding: utf-8 -*-
"""
生成 2026-10-30 矿业资讯速览 index.html（周五）
- 10-29 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-01）回补历史条目
- 换入 10-30 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-29 收盘 + LME 10-29 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目（ky.mnr 10-29 批 4 宗）已追加进月库 → 前端 #rightsCards，不进主列表
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

REPORT = '2026-10-30'
GRAB = '2026-10-30'
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
                         r'\g<1>2026年10月30日 星期五', html)
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
    (CAT_ZK, ni('https://news.metal.com/newscontent/104184233-ironveld-reports-titanium-bearing-intersections-at-south-africas-bushveld-complex',
                'SMM 国际站', '10-29',
                'Ironveld 南非 Bushveld 21 层见厚层钛矿化，15 米厚二氧化钛品位 8.11%',
                'Ironveld 公布南非 Bushveld 杂岩体 21 层既有钻孔岩心的矿物学与地球化学结果：自 55.5 米见矿 15 米、二氧化钛品位 8.11%，自 29.5 米见矿 23 米、品位 7.47%。矿物学工作识别出钛铁矿与含钛磁铁矿、磷灰石共生；公司正评估可分别回收磁铁矿、钛铁矿与含磷精矿的选矿流程，以拓宽项目收入来源。',
                orig_title="Ironveld reports titanium-bearing intersections at South Africa\u2019s Layer 21")),

    (CAT_ZK, ni('https://www.mining.com/mule-canyon-gold-resource-advances-restart-plans',
                'MINING.COM', '10-29',
                'Mule Canyon 金矿公布资源量，重启计划进入下一阶段',
                'Mule Canyon 金矿公布资源量，重启计划由此进入下一阶段：将把推断资源量升级为更高类别、完成项目经济性评估，并落实重启所需的许可。项目审批与投产时间表以公司后续披露为准。',
                orig_title='Mule Canyon gold resource advances restart plans')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104186628',
                '上海有色网', '10-29',
                '商务部公布 2027 年货物出口配额总量，磷矿石、白银继续暂停出口配额管理',
                '商务部公告 2026 年第 53 号公布 2027 年货物出口配额总量，明确磷矿石、白银继续暂停出口配额管理、实行出口许可证管理，符合条件的经营者可凭有效出口合同申领出口许可证。2027 年配额（招标方式分配除外）申请期为 2026 年 11 月 1 日至 11 月 15 日，申请材料提交省级商务主管部门。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104181982',
                '上海有色网', '10-28',
                '上期所就锌期货合约及业务细则修订公开征求意见',
                '上期所 10 月 27 日发布公告，就修订《上海期货交易所锌期货合约》《上海期货交易所锌期货业务细则》向社会公开征求意见，反馈截止 2026 年 11 月 3 日。此次修订依据期货和衍生品法、期货交易管理条例等规定推进，具体条款以公开征求意见稿为准。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104178782',
                '上海有色网', '10-26',
                '欧盟废止对华太阳能玻璃“双反”关税，10 月 22 日起生效',
                '欧盟委员会 10 月 21 日公告，正式废止对原产于中国的太阳能玻璃反倾销税与反补贴税，《欧盟官方公报》公布次日即 10 月 22 日生效。此前反倾销税率为 17.5% 至 75.4%、普遍税率 67.1%，反补贴税率为 3.2% 至 17.1%、普遍 17.1%；废止理由是欧盟境内已无活跃的太阳能玻璃生产企业。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104181913',
                '上海有色网', '10-28',
                '沪铝库存连降十九周至近九个月新低，LME 铝库存较年初降逾五成',
                '上期所数据显示，10 月 23 日当周沪铝库存减少 10.18% 至 212,858 吨，连降十九周并降至近九个月新低；节后铝水比例恢复、铸锭量收缩，叠加旺季需求回暖。LME 铝库存降至 232,100 吨、再创新低，较年初降逾五成，俄产铝在可交割库存中的占比进一步上升。')),

    (CAT_SC, ni('https://news.smm.cn/news/104181737',
                '上海有色网', '10-27',
                '丸红：日本三大港口 9 月底铝库存环比下降 9.5%',
                '丸红株式会社 10 月 27 日表示，截至 9 月底日本横滨、名古屋、大阪三大主要港口铝库存为 223,200 吨，较 8 月底的 246,600 吨下降 9.5%，为连续去化后的低位水平。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/9d310d316c364fe3aadb676b266957fd.html',
                '长江有色网', '10-29',
                '碳酸锂期货大跌 8.4% 至 88,360 元/吨，现货重心同步下移',
                '10 月 29 日长江综合电池级碳酸锂（99.5%）均价 96,000 元/吨、较上一交易日跌 3,000 元，工业级碳酸锂（99.2%）均价 93,000 元/吨、同步下跌 3,000 元。期货端跌幅更大，主力合约收盘大跌 8.4%、报 88,360 元/吨，市场在旺季需求证伪与远期供给释放预期之间持续博弈。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475043',
                '中国有色金属报', '10-29',
                '秘鲁 8 月铜产量同比下降 5%，Antamina 增产 21.4% 居首',
                '秘鲁能矿部初步统计显示，8 月铜产量 230,676 吨、同比下降 5%，1 至 8 月累计 182.98 万吨、同比增 1.2%。分矿山看，Antapaccay 当月产量 8,565 吨、同比降 48.7%；Antamina 产铜 44,959 吨、同比增 21.4%，占全国产量 18.7%；Las Bambas 产铜 32,894 吨、增 8.3%，三家合计贡献 48.4%。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-29/1225635088.PDF',
                '巨潮资讯网', '10-29',
                '西部黄金子公司百源丰奥尔托喀讷什三区锰矿恢复生产',
                '西部黄金（601069）公告，控股子公司百源丰所属奥尔托喀讷什三区锰矿已恢复生产。复产安排及对全年产量的具体影响以公司公告与定期报告披露为准。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-30/1225639499.PDF',
                '巨潮资讯网', '10-30',
                '宝地矿业控股子公司备战矿业签订重大合同',
                '宝地矿业（601121）公告，控股子公司备战矿业签订重大合同，合同标的、金额及履约期限以公告正文披露为准。备战矿业所属项目此前已取得采矿安全设施设计审查意见书并转入基建期。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-30/1225644700.PDF',
                '巨潮资讯网', '10-30',
                '旭光电子子公司氮化铝粉体技改扩产，新增产能 640 吨/年',
                '旭光电子（600353）公告，子公司宁夏北瓷新材料科技实施氮化铝粉体生产工艺提质技改扩产项目，新增氮化铝粉体产能 640 吨/年。项目投资额、建设周期与投产安排以公告正文披露为准。')),

    (CAT_HY, ni('https://news.metal.com/newscontent/104186741-glencores-self-produced-copper-up-3-yoy-in-first-three-quarters-full-year-production-expected-near-lower-end-of-guidance',
                'SMM 国际站', '10-29',
                '嘉能可前三季度自产铜 59.86 万吨同比增 3%，全年指引趋向区间下限',
                '嘉能可三季度产量报告显示，当季自产铜 20.16 万吨、环比增 2%，前三季度累计 59.86 万吨、同比增 3%；剔除 Mount Isa 停产与 Kidd 矿出售影响后，可比口径同比增 12%，增量主要来自非洲铜矿业务与 Antamina。公司预计全年铜产量接近指引区间下限。',
                orig_title="Glencore's self-produced copper up 3% YoY in first three quarters, full-year production expected near lower end of guidance")),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475046',
                '中国有色金属报', '10-29',
                '中铝国际长沙院强岩溶区超细矿泥建库技术达国际领先，已在广西铝土矿山应用',
                '中铝国际下属长沙有色冶金设计研究院自主研发的强岩溶区超细矿泥建库安全堆存成套技术，突破强岩溶区存储超细矿泥技术瓶颈、填补国内岩溶区建库技术空白，达到国际领先水平。该技术针对 -200 目占比 95.6%、含水率约 70% 的超细尾矿与岩溶发育库址，首创地下水分区分级导排、地下气压动态平衡等五项核心技术，已在广西华银铝业、广西信发铝电及中铝广西分公司应用。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-30/1225643919.PDF',
                '巨潮资讯网', '10-30',
                '红星发展公开挂牌转让万山鹏程矿业全部股权及债权',
                '红星发展（600367）公告，公司及所属公司拟公开挂牌转让所持万山鹏程矿业有限责任公司全部股权及截至评估基准日的全部债权，同日披露股权价值与债权资产价值两份评估报告。交易尚需履行挂牌与审批程序，受让方及成交价格待定。')),

    (CAT_MA, ni('https://www.mining.com/rio-tinto-pumps-1-4b-into-lithium-projects-in-argentina',
                'MINING.COM', '10-29',
                '力拓在阿根廷锂项目投入 14 亿美元，新增年产能 2.5 万吨',
                '力拓向阿根廷两座锂项目投入 14 亿美元，两个新项目合计新增年产能 2.5 万吨，以推进其在电池金属领域的增长目标。相关项目为其阿根廷盐湖布局的组成部分，投产节奏与产能爬坡安排以公司披露为准。',
                orig_title='Rio Tinto pumps $1.4 billion into lithium projects in Argentina')),

    (CAT_MA, ni('https://news.metal.com/newscontent/104184232-turaco-signs-us79m-deal-for-remaining-partner-stake-in-cote-divoires-afema-gold-project',
                'SMM 国际站', '10-29',
                'Turaco 以 7,900 万美元收购科特迪瓦 Afema 金矿剩余 20% 权益',
                'Turaco Gold 签署协议收购 Sodim 持有的科特迪瓦 Afema 金矿项目剩余 20% 权益，对价约 7,900 万美元，包含现金、股份、期权及承接的权益金回购安排。公司已支付 300 万美元不可退还费用取得三个月收购选择权；交易完成后仍需遵守科特迪瓦政府 10% 不可分摊权益的规定。',
                orig_title='Turaco signs US$79m deal for remaining partner stake in C\u00f4te d\u2019Ivoire\u2019s Afema gold project')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://news.metal.com/newscontent/104186811-rock-collapse-at-oyu-tolgoi-mine-injures-15-workers-all-stable-after-emergency-response',
                'SMM 国际站', '10-30',
                '蒙古奥尤陶勒盖铜矿井下岩体坍塌致 15 人受伤，暂无人员死亡',
                '奥尤陶勒盖有限责任公司公告，当地时间 10 月 29 日傍晚，井下破碎岩带发生突发地震地质事件并引发局部岩体坍塌，15 名作业人员受伤、暂无死亡报告。矿方随即启动应急响应机制并组织救援，事故原因与对生产的影响仍在评估。',
                orig_title='Rock Collapse at Oyu Tolgoi Mine Injures 15 Workers, All Stable After Emergency Response')),

    (CAT_GJ, ni('https://www.mining.com/copper-nickel-at-risk-due-to-el-ninos-disruptions',
                'MINING.COM', '10-30',
                'BMI：厄尔尼诺或扰动铜、镍生产至 2027 年初',
                'BMI 在最新报告中指出，厄尔尼诺可能通过极端天气扰动铜、镍生产，影响或延续至 2027 年初。该机构认为，天气风险与矿石品位下降、项目投产延迟叠加，将加大今明两年铜镍供应端的不确定性。',
                orig_title='Copper, nickel at risk due to El Ni\u00f1o\u2019s disruptions')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104186742-zambia-appoints-new-minister-of-mines',
                'SMM 国际站', '10-29',
                '赞比亚任命新矿业部长，2031 年铜产量目标 300 万吨',
                '赞比亚总统 Hichilema 于 10 月 28 日任命 Brenda Tambatamba 为矿业与矿产发展部长，其此前任劳动部长，早年曾在 Barrick 旗下 Lumwana 铜矿负责可持续发展事务。赞政府计划到 2031 年将铜产量提升至 300 万吨，而 2025 年实际产量约 89.03 万吨、同比增约 8%，距目标仍需新增约 211 万吨年产能。',
                orig_title='Zambia Appoints New Minister of Mines')),

    (CAT_GJ, ni('https://www.mining.com/eldorado-drops-as-skouries-setbacks-cut-gold-outlook-18',
                'MINING.COM', '10-29',
                'Eldorado 因 Skouries 项目拖累下调 2026 年黄金产量指引 18%',
                'Eldorado Gold 将 2026 年黄金产量指引下调 18%，并上调资本开支，主因希腊 Skouries 铜金项目进度受阻。消息公布后公司股价下跌，市场关注项目投产时点与成本超支幅度。',
                orig_title='Eldorado drops as Skouries setbacks cut gold outlook 18%')),
    (CAT_MA, ni('https://www.mining.com/critical-one-energy-sicc-ink-303-million-antimony-offtake-deal-for-howells-lake-project-in-ontario',
                'MINING.COM', '10-30',
                'Critical One Energy 与 SICC 签署 3.03 亿美元锑承购协议，覆盖安大略 Howells Lake 项目',
                'Critical One Energy 与 SICC 就加拿大安大略省 Howells Lake 锑项目签署价值约 3.03 亿美元（约 21.8 亿元）的锑承购协议（offtake），覆盖该项目锑精矿的包销安排。Howells Lake 是加拿大最大的未开发锑矿，该协议为 Critical One Energy 推进项目后续开发与融资提供了确定性需求支撑。',
                orig_title='Critical One Energy, SICC ink $303 million antimony offtake deal for Howells Lake project in Ontario')),

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
    ('Ironveld', CAT_ZK),
    ('Mule Canyon', CAT_ZK),
    ('货物出口配额', CAT_ZC),
    ('锌期货合约', CAT_ZC),
    ('太阳能玻璃', CAT_ZC),
    ('沪铝库存', CAT_SC),
    ('丸红', CAT_SC),
    ('碳酸锂', CAT_SC),
    ('秘鲁 8 月铜产量', CAT_SC),
    ('百源丰', CAT_HY),
    ('备战矿业', CAT_HY),
    ('氮化铝', CAT_HY),
    ('嘉能可前三季度', CAT_HY),
    ('强岩溶区', CAT_HY),
    ('万山鹏程', CAT_MA),
    ('力拓', CAT_MA),
    ('Turaco', CAT_MA),
    ('奥尤陶勒盖', CAT_GJ),
    ('厄尔尼诺', CAT_GJ),
    ('赞比亚', CAT_GJ),
    ('Eldorado', CAT_GJ),
    ('Howells Lake', CAT_MA),
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
