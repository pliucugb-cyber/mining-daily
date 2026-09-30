# -*- coding: utf-8 -*-
"""
生成 2026-09-30 矿业资讯速览 index.html（周三）
- 09-29 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-01）回补历史条目
- 换入 09-30 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-29 收盘（现算）
  + LME 09-28 收盘（卡片=走势图末点口径，当日电子盘未收盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
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

REPORT = '2026-09-30'
GRAB = '2026-09-30'
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
                         r'\g<1>2026年09月30日 星期三', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260929_10325839.htm',
                '全球矿产资源信息系统', '09-29',
                '弗鲁塔北金矿深部及周边钻探进展',
                '全球矿产资源信息系统报道，厄瓜多尔弗鲁塔北（Fruta del Norte）金矿深部及周边钻探取得新进展，进一步确认矿体沿走向与倾向的连续性。')),

    (CAT_ZK, ni('https://www.mining.com/atlas-malacacheta-emerges-as-south-americas-largest-graphite-project',
                'MINING.COM', '09-30',
                'Atlas 的 Malacacheta 项目成为南美最大石墨项目',
                'MINING.COM 报道，Atlas 旗下 Malacacheta 石墨项目经资源评估后成为南美规模最大的石墨项目，公司正推进项目开发研究。',
                orig_title="Atlas' Malacacheta emerges as South America's largest graphite project")),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/kfjs/202609/t20260930_10327479.htm',
                '全球矿产资源信息系统', '09-30',
                '澳大利亚林赛山钨锡矿概略研究完成',
                '全球矿产资源信息系统报道，澳大利亚林赛山钨锡矿概略研究（概览研究）已完成。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474361',
                '中国有色金属报', '09-30',
                '株硬主导制定的我国硬质合金行业首项国际标准发布',
                '由中国有色金属工业协会理事单位株洲硬质合金集团主导制定的我国硬质合金行业首项国际标准正式发布，实现该领域国际标准零的突破。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/e63c2d0ace3f47208656540a6225fc18.html',
                '长江有色网', '09-30',
                '9 月钴价大幅跳水，单月下跌 42000 元/吨后月末反弹',
                '长江有色网报道，9 月国内钴价大幅跳水，单月累计下跌 42000 元/吨，月末触底反弹 4000 元/吨，钴盐与钴酸锂价格同步走弱。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/a30fc3be27524128933321627a6599ce.html',
                '长江有色网', '09-30',
                '长江有色：矿紧托底、库松压顶，铜价节前高位收口',
                '长江有色网分析称，矿端偏紧托底、库存回升施压，铜价在长假前高位收口，市场关注节后需求验证与现实检验。')),

    (CAT_SC, ni('https://news.smm.cn/news/104140299',
                '上海有色网', '09-30',
                'SMM：伦铝库存较年初下降逾五成',
                '上海有色网数据显示，LME 铝库存较年初下降逾五成，海外铝锭显性库存持续去化，对伦铝价格形成支撑。')),

    (CAT_SC, ni('https://www.mining.com/copper-holds-above-14400-as-chile-strike-risk-grows',
                'MINING.COM', '09-29',
                '智利罢工风险升温，铜价维持高位',
                'MINING.COM 报道，安托法加斯塔旗下 Centinela 铜矿劳资谈判破裂、罢工风险上升，加剧供应担忧，铜价维持高位，本月有望录得连续第三个月上涨。',
                orig_title="Copper price holds above $14,400 as Chile strike risk grows")),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474359',
                '中国有色金属报', '09-30',
                '中矿资源 Bikita 矿业钽铌回收二厂项目开工',
                '中矿资源津巴布韦 Bikita 矿业钽铌回收二厂项目开工建设，进一步延伸资源综合利用产业链、提升伴生金属回收能力。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474352',
                '中国有色金属报', '09-30',
                '中铝贵州分公司成功研发 8021 电池铝箔用扁锭',
                '中铝贵州分公司成功研发 8021 电池铝箔用扁锭，为电池铝箔坯料实现自主供应提供支撑。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474388',
                '中国有色金属报', '09-30',
                '宝信软件中标金钼集团智能化工厂建设 EPC 项目',
                '宝信软件中标金钼集团智能化工厂建设 EPC 项目，将承担该钼业企业智能工厂的设计与建设。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-09-29/1225586131.PDF',
                '巨潮资讯网', '09-29',
                '大中矿业：子公司发生安全事故',
                '大中矿业（001203）公告，其子公司发生安全事故，公司已启动应急处置并开展相关善后工作。',
                embed='pdf')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/trumps-venezuela-gold-push-hits-refiner-snag-nyt',
                'MINING.COM', '09-30',
                '美国推动委内瑞拉黄金出口受阻',
                'MINING.COM 援引《纽约时报》报道，美国推动委内瑞拉黄金出口的计划在精炼环节遇阻，部分进入供应链的黄金被指与矿企向委内瑞拉南部金矿区黑帮支付“保护费”有关。',
                orig_title="Trump's Venezuela gold push hits refiner snag: NYT")),

    (CAT_GJ, ni('https://www.mining.com/latin-america-mining-risks-carry-54b-price-tag',
                'MINING.COM', '09-29',
                '拉美矿业风险敞口高企',
                'MINING.COM 报道，审批延迟、社区冲突与安全威胁使拉美矿业面临高额风险敞口，正改变矿企在该地区的资本投放方式。',
                orig_title="Latin America mining risks carry $54B price tag")),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134711-sulphuric-acid-shortage-a-key-constraint-on-zambias-copper-growth',
                'SMM 国际站', '09-30',
                '硫酸短缺成为赞比亚铜产业增长关键制约',
                'SMM 国际站报道，硫酸供应短缺正成为赞比亚铜矿生产与冶炼增长的关键制约，Jubilee Metals 报告酸价成本上升已影响其运营。',
                orig_title="Sulphuric Acid Shortage: A Key Constraint on Zambia’s Copper Growth")),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134804-zimbabwe-lithium-landscape-widens-indias-lohum-joins-chinese-players',
                'SMM 国际站', '09-30',
                '印度 LOHUM 获得津巴布韦 10 个含锂辉石矿块权益',
                'SMM 国际站报道，印度关键矿产企业 LOHUM 获得津巴布韦 10 个含锂辉石矿块权益，成为该国锂矿领域新参与者，与中资企业形成竞争。',
                orig_title="Zimbabwe Lithium Landscape Widens: India’s LOHUM Joins Chinese Players")),

    (CAT_GJ, ni('https://www.ccmn.cn/news/ZX006/202609/08e54cdc1d0c4267a095f5d622da4a8a.html',
                '长江有色网', '09-30',
                '刚果（金）矿业新规落地，2027 年起启动年度审计',
                '长江有色网报道，刚果（金）矿业新规落地，自 2027 年起启动年度审计，多家头部矿企已收到整改要求。')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104140008-smm-nickel-flashindonesia-tightens-mining-contractor-rules-under-new-esdm-regulation',
                'SMM 国际站', '09-30',
                '印尼能矿部新规收紧矿业承包商管理',
                'SMM 国际站报道，印度尼西亚能矿部（ESDM）发布新规，收紧矿业承包商管理规定，或对镍矿等资源开采运营产生影响。',
                orig_title="[SMM Nickel Flash] Indonesia Tightens Mining Contractor Rules Under New ESDM Regulation")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://disc.szse.cn/download/disc/disk03/finalpage/2026-09-28/13f43cf6-bc76-4e6d-a0cb-b41f5bcc1b1c.PDF',
                '深圳证券交易所', '09-28',
                '恩捷股份：收购子公司少数股权并与亿纬锂能设立合资公司事项进展',
                '恩捷股份（002812）披露关于收购下属子公司少数股权暨与亿纬锂能设立合资公司事项的进展公告。',
                embed='pdf')),

    (CAT_MA, ni('https://www.mining.com/strategic-minerals-gets-9-2m-department-of-war-funding-for-uk-tungsten-project',
                'MINING.COM', '09-29',
                'Strategic Minerals 获美国国防部资助，推进英国钨矿项目',
                'MINING.COM 报道，Strategic Minerals 获得美国国防部资助，用于推进英国 Redmoor 钨矿项目，该矿为欧洲品位最高的未开发钨资源。',
                orig_title="Strategic Minerals gets $9.2M Department of War funding for UK tungsten project")),

    (CAT_MA, ni('https://www.mining.com/copper-intelligence-cotec-partner-for-drc-copper-tailing-processing',
                'MINING.COM', '09-30',
                'Copper Intelligence 与 CoTec 合作开发刚果（金）铜尾矿',
                'MINING.COM 报道，Copper Intelligence 与 CoTec 达成合作，共同开发刚果（金）铜矿带自上世纪以来积累的铜尾矿处理机会。',
                orig_title="Copper Intelligence, CoTec partner for DRC tailings processing")),

    (CAT_MA, ni('https://www.mining.com/lake-resources-gets-environmental-green-light-for-kachi-lithium-project-in-argentina',
                'MINING.COM', '09-30',
                'Lake Resources 阿根廷 Kachi 锂项目获环境许可',
                'MINING.COM 报道，Lake Resources 位于阿根廷的 Kachi 锂项目获得环境许可，将转入前端工程设计（FEED）阶段。',
                orig_title="Lake Resources gets environmental green light for Kachi lithium project in Argentina")),

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
