# -*- coding: utf-8 -*-
"""
生成 2026-10-03 矿业资讯速览 index.html（周六 · 国庆假期第 3 天）
- 09-30 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-02）回补历史条目
- 换入 10-03 抓取的最新条目（is-new + NEW），更新计数
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

REPORT = '2026-10-03'
GRAB = '2026-10-03'
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
                         r'\g<1>2026年10月03日 星期六', html)
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
    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202610/t20261002_2939532.html',
                '自然资源部', '10-02',
                '广西地矿局水工环勘查托举平陆运河通航',
                '平陆运河 9 月 16 日正式通航。广西壮族自治区地质矿产勘查开发局组织局属多家单位，为运河开展水工环地质、工程勘察、资源评估、生态监测与海洋地质工作；2021 年启动 1:5 万平陆运河水文地质工程地质环境地质调查，铺开 7,500 平方千米调查作业，为线路比选与枢纽选址提供实测数据支撑。')),

    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104143522-tuskers-malawi-sampling-points-to-ilmenite-dominance',
                'SMM 国际站', '10-02',
                'Tusker 马拉维 Mzimba 采样显示钛铁矿主导',
                'SMM 国际站报道，Tusker Minerals 9 月 30 日称马拉维北部 Mzimba 项目 149 件区域土壤样中 112 件磁性钛超过计算金红石当量，指示钛铁矿主导体系并局部含金红石；33 件浅坑样未显示高品位金红石向深部延续，公司暂缓一期异常的金红石专项钻探、重新评估地质模型，近期重心仍在喀麦隆。',
                orig_title="Tusker's Malawi sampling points to ilmenite dominance")),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/en/newscontent/104143505-ghana-draft-bill-proposes-state-special-share-and-shorter-mining-leases',
                'SMM 国际站', '10-02',
                '加纳矿业法案草案拟设国家特别股、缩短采矿租约',
                'SMM 国际站援引路透审阅的草案：加纳拟允许矿业部长要求企业向国家无偿发行特别股，并对重大交易拥有同意权；保留现行 10% 无偿干股，采矿租约期限限定为 15 年或预计矿山寿命（取较短者），未来还可要求本地加工并限制未加工精矿出口。草案尚未进入立法程序，现有矿权持有者续期可获同类许可优先考虑。',
                orig_title='Ghana draft bill proposes state special share and shorter mining leases')),

    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202610/t20261002_2939533.html',
                '自然资源部', '10-02',
                '自然资源部对重庆贵州启动地质灾害防御 IV 级响应',
                '据气象部门预报，未来三天重庆、贵州部分地区有大到暴雨、局地大暴雨，经自然资源部地质灾害技术指导中心研判，重庆北部、贵州东部地质灾害风险较高。自然资源部于 9 月 30 日 18 时对重庆、贵州启动地质灾害防御 IV 级响应，要求强化巡查排查、监测预警、会商研判与灾情险情处置，中国地质调查局等加强专家调度。')),

    (CAT_ZC, ni('https://www.mining.com/controlling-supply-chain-key-to-us-future-doe',
                'MINING.COM', '10-02',
                '美国能源部：掌控关键矿产供应链关乎美国未来',
                '美国能源部负责关键矿产与能源创新的助理部长 Audrey Robertson 表示，美国必须重新掌控关键矿产供应链，以保障能源、经济与国家安全；能源部现阶段聚焦采矿、加工、技术与劳动力培训投资，目标是重启过去三十年外流的本土能力，并把已外迁的重工业拉回美国。',
                orig_title='Controlling supply chain key to US future: DOE')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104143076-smm-analysis-discounts-officially-emerge-rkab-quota-increases-and-delayed-rainy-season-push-indonesian-laterite-nickel-ore-prices-below-hpm',
                'SMM 国际站', '09-30',
                'SMM 分析：印尼红土镍矿价格跌破 HPM',
                'SMM 分析指出，2026 年印尼 RKAB 初始核准镍矿产量 2.6 亿至 2.7 亿吨、明显低于 2025 年配额水平；随修订版 RKAB 陆续获批、雨季推迟，红土镍矿升水本周期首次转负。8 月 28 日至 9 月 28 日，印尼 1.6% 品位镍矿到厂价由 65.8 美元/湿吨降至 63.4 美元/湿吨，该品位升水由 1.52 美元/湿吨压缩至 0.02 美元/湿吨；1.2% 品位 HPM 自 9 月 15 日起由 44.97 美元/湿吨下调至 24.89 美元/湿吨。',
                orig_title='[SMM Analysis] Discounts Officially Emerge: RKAB Quota Increases and Delayed Rainy Season Push Indonesian Laterite Nickel Ore Prices Below HPM')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104142283-gold-silver-platinum-and-palladium-rebound-precious-metals-sector-rallies-silver-and-platinum-spot-markets-show-strong-holiday-atmosphere-smm-flash',
                'SMM 国际站', '09-30',
                '贵金属集体反弹，金银铂钯同步走高',
                'SMM 报道，受美联储官员表态偏鸽、美元指数走弱、地缘不确定性以及各国央行购金需求支撑，黄金、白银、铂、钯集体反弹。纽约联储主席威廉姆斯称若经济大致符合预期，年内或还有一次加息合适，但强调无需急于行动；市场对 10 月加息预期由约 70% 快速回落至约 50%。',
                orig_title='Gold, silver, platinum, and palladium rebound, precious metals sector rallies, silver and platinum spot markets show strong holiday atmosphere [SMM Flash]')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104143285-european-apt-offers-drop-to-2700-3100mtu-amid-weak-demand-and-lower-scrap-prices',
                'SMM 国际站', '10-01',
                '欧洲 APT 报价下移至 2,700-3,100 美元/吨度',
                'SMM 报道，欧洲仲钨酸铵（APT）报价本周下移至 2,700 至 3,100 美元/吨度，部分报 2,700 至 2,750 美元/吨度，实际成交清淡、无新现货成交；冶炼厂长单价格维持 3,000 美元/吨度以上、现有产量多已预售，废料与钨矿价格同步走低，买家看空观望，市场陷入僵持。',
                orig_title='European APT Offers Drop to $2,700-3,100/mtu Amid Weak Demand and Lower Scrap Prices')),

    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/jqzs/2026/0929/62104.html',
                '中国有色金属工业协会', '09-29',
                '协会：8 月锂行业运行情况',
                '中国有色金属工业协会发布 8 月锂行业运行情况：电池级碳酸锂价格由月初 14.05 万元/吨涨至月末 15.55 万元/吨、涨幅 10.7%，工业级由 13.75 万元/吨涨至 15.25 万元/吨，氢氧化锂由 13.05 万元/吨涨至 14.55 万元/吨、涨幅 11.5%；碳酸锂主力合约收盘价由 13.89 万元/吨涨至 16.10 万元/吨。截至 8 月底广期所碳酸锂仓单库存 45,624 吨，环比增加 20,582 吨。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-01/1225591141.PDF',
                '巨潮资讯网', '10-01',
                '西部黄金：子公司新疆美盛选矿厂临时停产约 45 天',
                '西部黄金公告，全资子公司新疆美盛矿业尾矿库二、三期合建工程即将与一期坝体衔接，需同步调整尾矿库监测设施并建设排水系统，选矿厂配合停产，临时停产预计 45 天左右。新疆美盛主要产品为金精矿等黄金产品，2026 年 1—6 月营业收入 70,022.50 万元、占公司营业收入 6.34%，净利润 1,658.06 万元、占 3.03%；恢复生产时间尚不确定。',
                embed='pdf')),

    (CAT_HY, ni('https://www.chinania.org.cn/html/xiehuidongtai/xiehuidongtai/2026/0929/62096.html',
                '中国有色金属工业协会', '09-29',
                '首届氧化铝智能制造大会召开，发布数智化行动方案',
                '首届氧化铝智能制造技术与产业升级大会 9 月 22 日在广西防城港召开，会上发布《中国氧化铝数智化发展行动方案（2026—2030 年）》。协会介绍，2025 年我国氧化铝、电解铝、铝材产量分别为 9,294 万吨、4,423 万吨、4,880 万吨，全球占比均超 60%；氧化铝产能超 1.2 亿吨、海外布局近千万吨，氧化铝中镓提取全球占比达 95%，行业仍面临资源对外依存度高、投资过热、数智化水平不高等挑战。')),

    (CAT_HY, ni('https://www.chinania.org.cn/html/xiehuidongtai/xiehuidongtai/2026/1001/62115.html',
                '中国有色金属工业协会', '10-01',
                '先进有色金属（稀有）材料产业链共链行动大会在成都召开',
                '2026 年先进有色金属（稀有）材料现代产业链共链行动大会 9 月 29 日在成都召开，由国务院国资委、工业和信息化部、中国有色金属工业协会和中国铝业集团指导。协会党委书记敖宏指出，2023 年以来国家对镓、锗、锑、铟等实施两用物项出口管制，全行业合规意识明显增强，下一步要筑牢资源安全根基、强化创新协同、共建产业生态。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104143526-kghm-and-south32-launch-us725m-sierra-gorda-expansion-lifting-copper-capacity-26',
                'SMM 国际站', '10-02',
                'KGHM 与 South32 启动 Sierra Gorda 铜矿 7.25 亿美元扩建',
                'SMM 国际站报道，KGHM 与 South32 在智利阿塔卡马大区 Sierra Gorda 铜钼矿启动第四条磨矿线建设，投资 7.25 亿美元，工期三年、2027 年 1 月开工、2029 年底完工、2030 年下半年满产。矿石处理能力由 13.1 万吨/日提升 26% 至 16.5 万吨/日，年产铜由 2025 年的 16.5 万吨增至 19.5 万吨，项目由经营现金流与债务融资，单位运营成本预计下降约 10%。',
                orig_title='KGHM and South32 launch US$725m Sierra Gorda expansion, lifting copper capacity 26%')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104143454-emerita-extends-final-review-of-iberian-belt-west-pfs-release-expected-in-coming-weeks',
                'SMM 国际站', '10-02',
                'Emerita 推迟西班牙 Iberian Belt West 预可研发布',
                'SMM 国际站报道，Emerita Resources 更新西班牙 Iberian Belt West 多金属项目预可行性研究（PFS）进展，称研究已深度推进但仍处最终技术审查，审查范围扩大至额外技术与质量保证环节，发布时间由原定窗口推迟至未来数周。该项目含铜、锌、铅、金、银矿化，公司未披露新的产量、资本开支或经济性数据。',
                orig_title='Emerita Extends Final Review of Iberian Belt West PFS, Release Expected in Coming Weeks')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104143498-pgms-independent-tests-advance-platinum-and-palladium-battery-technology',
                'SMM 国际站', '10-02',
                '铂钯基电极通过独立测试，PGM 打开电池新用途',
                'SMM 国际站报道，Platinum Group Metals 10 月 1 日称 Battery Innovation Center 的独立测试验证其 Lion Battery 子公司铂、钯基电极在锂硫原型电池中的表现，相比未加催化剂电芯容量与倍率性能更优、富钯配方综合最佳。Lion 由 Platinum Group 与 Valterra Platinum 分别持股 52%、48%，双方已批准下一阶段经费；该结果仍属原型里程碑，尚未确立商业化性能。',
                orig_title='PGMs: Independent tests advance platinum and palladium battery technology')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104143524-aterian-reports-higher-rwanda-3t-ore-sales-trading-margins-remain-estimates',
                'SMM 国际站', '10-02',
                'Aterian 卢旺达 3T 矿石销售放量，贸易利润仍为估计值',
                'SMM 国际站报道，Aterian Resources 中报显示，截至 2026 年 6 月 30 日止六个月钽及其他矿石销售收入 134.1 万英镑，上年同期为 2 万英镑；毛利 52.2 万英镑，税前亏损 56.8 万英镑。其卢旺达贸易业务投入约 218 万美元营运资金，管理层估计相关采购潜在销售额 278 万美元，但提示该估值不构成额外确认收入。',
                orig_title='Aterian reports higher Rwanda 3T ore sales; trading margins remain estimates')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/world-bank-unlocks-1-4b-for-chiles-copper-giant',
                'MINING.COM', '10-02',
                '世行以 Codelco 为范例，解锁约 14 亿美元担保支持',
                'MINING.COM 报道，世界银行集团以智利国家铜业公司（Codelco）为范例，说明担保工具可帮助资源国吸引长期资本并降低矿山环境足迹。做法是通过多边投资担保机构（MIGA）为商业贷款人提供担保；其中一笔近 8.6 亿美元的 15 年期担保覆盖桑坦德银行与汇丰银行提供的 6 亿美元贷款，用于支持五份可再生能源购电协议。世行本周发布报告《Made Possible by Minerals》。',
                orig_title="World Bank unlocks $1.4B for Chile's copper giant")),

    (CAT_MA, ni('https://www.mining.com/minings-future-is-up-for-sale',
                'MINING.COM', '10-01',
                '金属流融资成独立资产类别，Wheaton 43 亿美元押注 Antamina',
                'MINING.COM 报道，金属流（streaming）融资已从面向资金紧张矿商的细分工具，演变为数十亿美元级交易并形成二级市场的独立资产类别。Wheaton Precious Metals 今年同意支付 43 亿美元（61 亿加元），购买必和必拓在秘鲁 Antamina 矿产量份额的白银流；多笔较小交易已吸引私募股权与专业公司买卖存量流与权益金。对矿商而言，流融资可在少发股、不过度加杠杆的前提下提供大额资金。',
                orig_title="Mining's future is up for sale")),

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
