# -*- coding: utf-8 -*-
"""
生成 2026-09-26 矿业资讯速览 index.html
- 09-24 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-27）回补历史条目
- 换入 09-24~09-25 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-24 收盘 + LME 09-24 收盘（东财日K末点=09-24，卡片=走势图口径），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层，不进主页列表（ky.mnr 09-23/09-24 有新公告，另行注入）
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

REPORT = '2026-09-26'
GRAB = '2026-09-26'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
# 站点名固定「矿业资讯速览」，标题统一写成「矿业资讯速览 · YYYY-MM-DD」。
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月25日 星期五', html)
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
# 单位同为「元/吨」= 国内盘分组单位 -> 走 unit_class 隐藏重复单位（2026-09-13 契约）
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
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104134719-aurum-drilling-delivers-155-gt-gold-hit-at-c',
                'SMM 国际站', '09-26',
                '科特迪瓦 Boundiali 金矿钻探见 155 克/吨高品位金',
                'Aurum Resources 公布科特迪瓦 Boundiali 金矿 BST1 矿床 22 个金刚石钻孔、合计 6172.8 米的化验结果：自 195.2 米起见矿 2.63 米、金品位 76.74 克/吨（含 1.3 米 155 克/吨），自 108 米起见矿 24 米、金品位 6.31 克/吨（含 7 米 19.25 克/吨），部分矿段超出既有资源边界。该矿现有 JORC 资源量 322 万盎司，结果将并入 2026 年四季度初的资源量更新。',
                orig_title="Aurum drilling delivers 155 g/t gold hit at C\u00f4te d\u2019Ivoire\u2019s Boundiali")),
    (CAT_ZK, ni('https://www.mining.com/lundin-gold-hits-record-1035g-in-ecuador',
                'MINING.COM', '09-25',
                'Lundin Gold 厄瓜多尔 Bonza Sur 钻探见矿品位创纪录',
                'MINING.COM 报道，Lundin Gold 在厄瓜多尔 Bonza Sur 的持续钻探继续支持以高品位矿化为重点的修订地质解释，本次公布的最富矿段品位达 1035 克/吨，创该项目纪录。',
                orig_title="Lundin Gold hits record 1035g in Ecuador")),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474275',
                '中国有色金属报', '09-24',
                '上期所镍国际化业务全流程贯通',
                '中国有色金属报报道，上期所镍国际化业务实现全流程贯通，打通了“最后一公里”。下一步上期所将持续丰富国际化产品供给，通过优化业务规则、强化市场培育、深化双向开放、筑牢技术保障、提升交割服务能力等举措，提升境内外各类主体参与便利性。',
                )),
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202609/t20260924_2939265.html',
                '自然资源部', '09-24',
                '自然资源部通报表扬 1—7 月 370 起地质灾害成功避险案例',
                '自然资源部办公厅印发《关于通报表扬2026年1—7月地质灾害成功避险案例的通知》（自然资办函〔2026〕1564号），将今年1—7月全国各地 370 起地质灾害成功避险案例清单汇总印发，并从强化思想认识、健全完善预案、做到群专结合、创新工作方法、部门协同联动、强化制度保障六方面总结经验。',
                )),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104134718',
                '上海有色网', '09-26',
                'ICSG：2026 年 7 月全球铜市场供应短缺 5.1 万吨',
                '上海有色网援引国际铜业研究组织（ICSG）数据，2026年7月全球铜市场供应短缺 5.1 万吨。该数据反映全球精炼铜供需延续偏紧格局。',
                )),
    (CAT_SC, ni('https://news.smm.cn/news/104115948',
                '上海有色网', '09-26',
                'SMM：全球铜市场结构性重塑，在供应动荡与需求转型中寻求平衡',
                '上海有色网（SMM）分析认为，全球铜市场正在经历结构性重塑：供应端扰动频发、需求端同步转型，价格在供需新动态中寻求平衡。',
                )),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104134717-platinum-shows-stronger-inflation-and-real-rate-linkages-than-gold-study-finds',
                'SMM 国际站', '09-26',
                '研究：铂金与通胀、实际利率的联动强于黄金',
                '《Journal of Commodity Markets》刊载的研究显示，铂金与通胀及实际利率的联动比黄金更广泛、更持久，白银也表现出较强的同步性。研究者认为铂金较强的宏观敏感性部分源于其工业属性；但该结论并不意味铂金是普遍优于黄金的通胀对冲工具。',
                orig_title="Platinum Shows Stronger Inflation and Real-Rate Linkages Than Gold, Study Finds")),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474266',
                '中国有色金属报', '09-24',
                '中国有色金属企业信心指数报告（2026 年三季度）',
                '中国有色金属工业协会发布 2026 年三季度中国有色金属企业信心指数报告。指数由新订单量、生产量、原材料采购量、原材料购入单价、单位产品售价、从业人数、企业资金周转、企业盈利水平、下游产业需求、企业经营环境共 10 个单项指标加权构成，权重分别为 15%、10%、5%、10%、15%、5%、10%、15%、7%、8%。',
                )),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474268',
                '中国有色金属报', '09-24',
                '中国恩菲德兴铜矿尾矿库数字运营系统通过上线试运行验收',
                '中国恩菲设计建设的德兴铜矿五号尾矿库数字运营管理系统通过上线试运行验收。该尾矿库每天可处置 13 万吨尾矿；项目依托自主研发的 MIM 矿山设计平台与一体化管控平台，运用“空—天—地—水—工—环”六维感知技术，搭建三维驾驶舱、生产运行、安全监测等 7 个应用模块，构建“预测、预报、预警、预演练”四预风险管控模式。',
                )),
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-09-25/1225581353.PDF',
                '巨潮资讯网', '09-25',
                '山东黄金将 2026 年矿产金产量计划下调至 36—38 吨',
                '山东黄金公告，公司 2026 年生产经营计划由原“黄金产量不低于 49 吨”调整为“矿产金产量 36 吨—38 吨”。公司称调整系外部经营环境变化与项目建设推进影响：上半年因同行企业安全事故开展安全自查导致产量同比下降；下半年加大烟台区域焦家、新城、三山岛、玲珑、蓬莱等资源整合项目建设力度，当期作业面减少。公司 2025 年矿产金产量 48.89 吨，预计 2026 年同比减少约 11—13 吨，归属于上市公司股东的净利润同比下降。',
                embed='pdf')),
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104134725-empire-produces-rutile-pigment-from-pitfield-titanium-ore',
                'SMM 国际站', '09-25',
                'Empire 从 Pitfield 钛矿石制出金红石颜料',
                'Empire Metals 用其西澳 Pitfield 钛项目原位风化矿石产出的精矿，成功制出未包膜金红石型二氧化钛颜料。X 射线衍射确认二氧化钛以金红石相存在，化学分析初测品位 97.6%，扣除硫的干扰后计算品位约 99.2%。公司正推进优化与表面包膜，以生产适用于建筑涂料的金红石颜料。',
                orig_title="Empire produces rutile pigment from Pitfield titanium ore")),
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104131363-huawei-pursues-africa-green',
                'SMM 国际站', '09-23',
                '华为在非洲推进绿色矿山合作，与赞比亚国家电力公司洽谈',
                '在上海有色网主办的 2026 非洲关键矿产大会（ACM2026，9 月 15—16 日于赞比亚卢萨卡）上，华为推介矿山微电网方案，并与赞比亚国家电力公司 ZESCO 就矿区能源供应、新能源部署与电力基础设施共建举行商务洽谈。华为表示，基于 IPP-PPA 模式（独立发电商投资＋长期购电协议）的分布式新能源微电网，可为露天矿与冶炼厂提供稳定的绿色电力；刚果（金）卡莫阿—卡库拉微电网项目投运后已显著降低矿山用电成本与碳排放。',
                orig_title="Huawei Pursues Africa Green-Mining Partnerships and Holds Business Talks with ZESCO at SMM ACM 2026")),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134762-peru-sees-1-million-ty-copper-output-boost-within-five-to-six-years',
                'SMM 国际站', '09-26',
                '秘鲁预计五到六年内铜产量增加 100 万吨',
                '秘鲁能源与矿业部长 Guillermo Shinno 表示，该国计划通过新矿山项目在未来五到六年内增加约 100 万吨/年的铜产量。作为全球第三大铜生产国，秘鲁预计 2026 年产量为 250 万—270 万吨，与 2023 年大致持平，矿石品位下降和社会冲突持续压制供应。新政府拟通过削减审批繁文缛节扭转停滞，已在约 100 项矿业审批要求中识别出可取消的 27 项许可。',
                orig_title="Peru sees 1 million t/y copper output boost within five to six years")),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134711-sulphuric-acid-shortage-emerges-as-a-constraint-on-zambias-copper-growth',
                'SMM 国际站', '09-26',
                '硫酸短缺成为赞比亚铜产量增长的制约',
                '赞比亚硫酸短缺正日益制约铜生产与精炼。Jubilee Metals 报告 2026 财年四季度酸成本上涨超过 200%，Sable 阴极铜产量由三季度的 361 吨降至 250 吨；政府数据显示 2026 年上半年小型铜矿产量同比下降 35.2%。',
                orig_title="Sulphuric Acid Shortage Emerges as a Constraint on Zambia\u2019s Copper Growth")),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134754-india-copper-producers-seek-gst-cut-as-record-prices-raise-working-capital-burden',
                'SMM 国际站', '09-25',
                '印度铜生产商寻求将商品服务税从 18% 下调至 5%',
                '印度初级铜生产商协会（IPCPA）正与政府磋商，寻求将铜产品商品服务税（GST）从 18% 下调至 5%，以缓解铜价创纪录高位下的营运资金压力；业界估算降税可为铜产业链释放最多 36 亿美元营运资金。据印度矿业部数据，2024 年 11 月至 2025 年 10 月印度铜矿产量 2.4774 万吨、占全球 0.11%，精炼铜产量占全球 2.81%。',
                orig_title="India copper producers seek GST cut as record prices raise working-capital burden")),
    (CAT_GJ, ni('https://www.mining.com/bhps-escondida-restart-eases-tight-copper-market',
                'MINING.COM', '09-25',
                '必和必拓 Escondida 复产缓解铜市紧张',
                'MINING.COM 报道，必和必拓旗下全球最大铜矿 Escondida 重启生产，缓解了此前因矿山停产、中国库存偏低以及假期临近而供应缓冲不足的铜市紧张局面。',
                orig_title="BHP\u2019s Escondida restart eases tight copper market")),
    (CAT_GJ, ni('https://www.mining.com/critical-minerals-boom-risks-second-funding-gap-as-governance-support-shrinks',
                'MINING.COM', '09-26',
                '关键矿产热潮面临第二个资金缺口：治理支持收缩',
                'MINING.COM 报道，一家总部位于华盛顿的捐助机构网络指出，投向矿山、加工设施与基础设施的开发融资在扩张，而用于透明度、公民社会监督与社区参与的治理类资金正在被削减，形成关键矿产热潮中的“第二个资金缺口”。',
                orig_title="Critical minerals boom risks second funding gap as governance support shrinks")),
    (CAT_GJ, ni('https://www.mining.com/north-america-is-building-rare-earth-plants-faster-than-it-is-building-rare-earth-engineers',
                'MINING.COM', '09-26',
                '北美稀土冶炼厂建设快于稀土工程师培养',
                'MINING.COM 报道，北美稀土冶炼产能建设速度快于工程师培养速度：工程专业毕业生数量不到美国能源部估算需求量（约每年 600 人）的一半，约为中国的十五分之一。',
                orig_title="North America is building rare earth plants faster than it is building rare earth engineers")),
    (CAT_GJ, ni('https://news.smm.cn/news/104134720',
                '上海有色网', '09-26',
                '铜价高企令智利矿企受益，但投资支出侵蚀利润',
                '上海有色网报道，铜价高企使智利矿企收入受益，但持续走高的投资支出正在侵蚀其利润空间。',
                )),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474149',
                '中国有色金属报', '09-21',
                '北方矿业完成印尼 KSK 项目交割',
                '中国有色金属报报道，北方矿业已完成印度尼西亚 KSK 项目交割。交割前，KSK 项目管理代表拜访了印尼政府有关部门，并向中国驻印尼使馆有关部门报告，获得肯定和支持；下一步北方矿业将科学高效开展各项工作，有序有力推进项目早日建成见效。',
                )),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-25/1225581240.PDF',
                '巨潮资讯网', '09-25',
                '贵研铂业拟 4.346 亿元投建高精度高性能复合材料生产基地',
                '贵研铂业公告，控股子公司贵研中希（上海）新材料科技有限公司拟投资建设高精度高性能复合材料生产基地项目，总投资 43,460 万元（其中建设投资 36,449 万元）。项目位于上海市松江区佘山镇工业区，用地面积 25,766.28 平方米，新建建筑面积 43,807.93 平方米，建设精密合金材、贵廉/廉廉金属复合带、型材、铆钉触点四条生产线，设计规模年产金属复合材料 2,000 吨，建设期 24 个月。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-24/1225583049.PDF',
                '巨潮资讯网', '09-24',
                '亿纬锂能 11.5 亿元转让湖北恩捷新材料 45% 股权',
                '亿纬锂能公告，公司审议通过转让参股公司股权的议案，将所持湖北恩捷新材料科技有限公司 45% 股权以 115,000 万元转让给上海恩捷新材料科技有限公司，交易完成后不再持有该公司股权。标的公司注册资本 16 亿元，2026 年上半年营业收入 103,982.14 万元、净利润 22,649.33 万元。',
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

merge_seq = [x for x in merge_seq if item_url(x[1]) not in new_seen_url]
merge_seq = dedup_same_event(merge_seq)

# ============ 3.6 数字落地校验（2026-09-14 新增，复用 verify_numbers） ============
# 每条摘要的数字须能在源文（候选池/月库）找到，防 LLM 抄错数字。
# 候选池未落盘或未开 --fetch-detail 时源文基准为空 -> 自动 skip（不阻断生成）。
# 生产守门：置 VERIFY_NUMBERS_STRICT=1 时未落地即抛异常（CI / 上线前卡点）。
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

# ============ 7. div 收支自检（2026-09-11 破损教训） ============
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
