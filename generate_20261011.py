# -*- coding: utf-8 -*-
"""
生成 2026-10-11 矿业资讯速览 index.html（周日）
- 10-10 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-12）回补历史条目
- 换入 10-11 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-09 收盘 + LME 10-09 收盘（周末休市），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
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

REPORT = '2026-10-11'
GRAB = '2026-10-11'
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
                         r'\g<1>2026年10月11日 星期日', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202610/t20261010_10332109.htm',
                '全球矿产资源信息系统', '10-10',
                '阿拉斯加帕尔莫铜锌矿扩边孔见矿 21 米，锌品位 4.79%',
                '全球矿产资源信息系统援引 Mining.com 报道，维斯拉铜业（Vizsla Copper）在美国阿拉斯加东南部帕尔莫（Palmer）铜锌项目的 AG 矿床扩边孔 CMR26-215 于 180.3 米深处见矿 21 米，锌品位 4.79%、铜 0.14%、银 116.9 克/吨、金 0.27 克/吨，其中 182 米处 7 米段锌品位 5.46%、银 207.5 克/吨。另一孔 CMR26-211 在 145.1 米深处见矿 37.2 米，锌 3.62%、铜 0.16%。帕尔莫为火山块状硫化物矿床，面积约 330 平方公里。')),

    (CAT_ZK, ni('https://news.smm.cn/news/104150495',
                '上海有色网', '10-10',
                '西部矿业茶亭铜多金属矿资源储量通过评审备案',
                '上海有色网报道，西部矿业 10 月 9 日公告，控股子公司西藏玉龙铜业之全资子公司安徽西矿玉龙茶亭矿业收到安徽省自然资源厅复函（皖矿储备字〔2026〕18 号），《安徽省宣州区茶亭矿区上长村矿段铜多金属矿勘探报告》矿产资源储量评审备案通过，为后续办理采矿权奠定基础。该矿床为大型斑岩型铜金矿床，累计查明工业品级铜矿石量（推断）12,180.30 万吨、金属量 65.67 万吨、平均品位 0.54%；低品位矿铜矿石量 44,956.12 万吨、金属量 109.09 万吨、品位 0.24%，共伴生金 248.07 吨。')),

    (CAT_ZK, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/1009/62122.html',
                '中国有色金属工业协会', '10-09',
                '永平铜矿六十年接续找矿：从浅表铁矿到铜硫钨多金属基地',
                '中国有色金属工业协会网刊文回顾江西省地质局第八大队在永平铜矿的六十年接续找矿历程：以“就矿找矿”地质理论为指引，运用“顺藤摸瓜、主次转化、平行侧列”三大勘查方法。1961 年在浅表铁矿巷道中揭露厚度超 20 米的原生铜硫矿体，1963—1966 年会战期间首批验证孔单孔揭露 40 米厚工业铜矿体，主攻矿种由铁矿转为铜硫；此后又探明厚层铜钨共生矿体，推动这座老矿山持续增储。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104149635',
                '上海有色网', '10-10',
                '商务部：反对以“产能过剩”为名行贸易保护主义之实',
                '上海有色网转载商务部消息，针对美东时间 10 月 7 日美贸易代表办公室称美国召集 14 个经济体签署应对所谓“结构性产能和生产过剩”问题的部长级联合声明，商务部新闻发言人表示，中方一贯认为看待产能问题要秉持全面、客观、公正态度，不能出于对自身产业竞争力和市场地位的担忧将经贸问题政治化；反对个别国家以所谓“产能过剩”为名行贸易保护主义之实，若有关经济体以此为借口采取损害中方利益的措施，中方将作出必要回应。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104150502',
                '上海有色网', '10-10',
                '发改委主任郑栅洁主持民营企业座谈会，强调提高能源资源安全保障水平',
                '上海有色网转载国家发展改革委消息，10 月 10 日国家发展改革委主任郑栅洁主持召开民营企业座谈会，与石油化工、天然气供应、农业机械、人工智能应用等领域企业负责人交流。郑栅洁表示四季度将加大逆周期调节力度，推动“十五五”规划、“六张网”建设实施方案等明确的重大工程项目尽早开工，推动科技创新与产业创新深度融合、进一步提升产业链供应链韧性、提高能源资源安全保障水平，并常态化向民间资本推介项目。')),

    (CAT_ZC, ni('https://www.ccmn.cn/news/ZX018/202610/e3f1c969321740649c09e8e54bae84e7.html',
                '长江有色网', '10-10',
                '津巴布韦重申 2027 年锂精矿出口禁令不延期',
                '长江有色金属网报道，津巴布韦政府再次明确自 2027 年 1 月起实施的锂精矿出口禁令不会延期，驳回了当地锂生产商协会提出的延至 2027 年 6 月的申请。该国信息部长尼克·曼瓜纳表示，企业已有充足时间为本地加工期限做准备，没有理由进一步推迟。此举意味着全球锂原料跨境供应将进一步收紧。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/1009/62126.html',
                '中国有色金属工业协会', '10-09',
                '机构：全球镍系定价或现“双基准”格局',
                '中国有色金属工业协会网刊文分析印尼矿产与战略大宗商品交易所（ICOMEX）的影响：该交易所由印尼金融服务管理局监管，牌照 2027 年 1 月 1 日发放、1 月 4 日开启首单交易，首批挂牌品种为锡和镍铁。文章认为，印尼占全球镍供应 60% 以上，而 LME 对二级镍覆盖不足、存在“基准真空带”，ICOMEX 最有希望率先形成“LME 一级镍、ICOMEX 二级镍”的双基准格局；锡短期更可能形成双轨报价但体量有限。')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104145280-smm-analysis-indonesias-sulphur-and-sulphuric-acid-import-and-export-data-for-august',
                'SMM 国际站', '10-11',
                '印尼 8 月硫磺进口 27.53 万吨，环比降 62.1%',
                'SMM 国际站报道，2026 年 8 月印尼硫磺进口量 27.53 万吨，环比下降 62.1%、同比下降 27.7%；主要进口来源为加拿大 7.61 万吨、科威特 5.09 万吨、卡塔尔 3.67 万吨、阿联酋 3.16 万吨、印度 2.64 万吨、美国 2.46 万吨。',
                orig_title="[SMM Analysis] Indonesia's Sulphur and Sulphuric Acid Import and Export Data for August")),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104150506-lithium-battery-china-exported-369-billion-lithium-ion-batteries-in-jan-aug-up-229-yoy',
                'SMM 国际站', '10-11',
                '中国 1—8 月出口锂离子电池 36.9 亿只，同比增 22.9%',
                'SMM 国际站援引工信部与海关统计，2026 年 1—8 月中国出口锂离子电池 36.9 亿只，同比增长 22.9%；同期电子信息制造业增加值同比增长 15.7%，营业收入增长 20.1% 至 12.8 万亿元，利润总额增长 110% 至 8,475 亿元。报道称电池出口高增反映海外动力与储能电池需求持续旺盛。',
                orig_title='[Lithium battery: China exported 3.69 billion lithium-ion batteries in Jan-Aug, up 22.9% YoY]')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104148689-gold-morgan-stanley-says-upside-potential-far-outweighs-downside-',
                'SMM 国际站', '10-11',
                '摩根士丹利：4,000 美元构成金价支撑，明年目标 5,000 美元',
                'SMM 国际站援引 GOLDINVEST 报道，摩根士丹利金属与矿业策略主管 Amy Gower 认为，尽管高油价与美债长端收益率创 20 年新高短期压制金价，但 4,000 美元/盎司上方构成强力支撑，需求基础稳固，维持 2027 年下半年金价重回 5,000 美元/盎司的目标。支撑来自三方面：中国实物黄金进口有望创 2017 年以来新高、央行持续购金（如波兰）、黄金 ETF 持仓逆势扩张；白银与黄金的相关性明显强于其与工业金属的相关性。',
                orig_title='Gold: Morgan Stanley Says Upside Potential Far Outweighs Downside – $4,000 as Support')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104150498-copper-cathode-rod-producers-to-boost-operating-rates-by-2711-post-holiday-amid-low-inventories',
                'SMM 国际站', '10-11',
                'SMM：低库存下节后铜杆企业开工率预计提升 27.11%',
                'SMM 国际站报道，受库存低位支撑，中国铜杆（阴极铜杆）生产企业节后开工率预计提升 27.11%。',
                orig_title='Copper Cathode Rod Producers to Boost Operating Rates by 27.11% Post-Holiday Amid Low Inventories')),

    (CAT_HY, ni('https://news.metal.com/en/newscontent/104150492-smm-china-copper-anode-operating-rate-rebounds-to-4714-in-september',
                'SMM 国际站', '10-11',
                'SMM：中国 9 月铜阳极板开工率回升至 47.14%，厂内库存降至 5.95 天',
                'SMM 国际站报道，2026 年 9 月中国铜阳极板开工率回升至 47.14%；因铜阳极板供应持续偏紧，SMM 统计冶炼厂铜阳极板库存天数降至 5.95 天，环比减少 0.18 天，为 2026 年 1 月以来连续第九个月下降。SMM 另预计 10 月铜阳极板整体开工率环比回落。',
                orig_title='SMM China Copper Anode Operating Rate Rebounds to 47.14% in September')),

    (CAT_HY, ni('https://news.metal.com/en/newscontent/104150447-copper-platesheet-and-strip-industry-sees-114-mom-rise-in-operating-rate-up-850-yoy-in-september-2026',
                'SMM 国际站', '10-11',
                'SMM：9 月铜板带行业开工率环比升 1.14 个百分点，节后订单强劲',
                'SMM 国际站报道，2026 年 9 月中国铜板带行业综合开工率环比上升 1.14 个百分点、同比上升 8.50%，维持高位。国庆节后铜板带及带材市场新订单表现良好，多数企业订单储备充足并初现旺季特征，SMM 预计 10 月行业综合开工率将继续保持高位。',
                orig_title='Copper Plate/Sheet and Strip Industry Sees 1.14% MoM Rise in Operating Rate, Up 8.50% YoY in September 2026')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kysc/gxxs/202610/t20261010_10332107.htm',
                '全球矿产资源信息系统', '10-10',
                '罢工与事故叠加，智利铜产量预计降至 2003 年以来最低',
                '全球矿产资源信息系统援引 BNAmericas 报道，安托法加斯塔矿产公司森蒂尼拉铜矿罢工、必和必拓埃斯康迪达铜矿工人停工威胁，正加剧智利铜供应压力。埃斯康迪达工人预计 10 月 14 日开始罢工，森蒂尼拉已有 22% 的工人停工。叠加恶劣天气与事故，安托法加斯塔将 2026 年产量指引下调 5% 至 62.5 万~65.5 万吨，1—7 月智利铜产量同比下降 9.3%。预计 2026 年智利铜产量降至约 510 万吨，为 23 年来最低。')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104150513-cobre-panama-copper-mine-stable-after-major-earthquake-strikes-panama',
                'SMM 国际站', '10-11',
                '巴拿马 7 级以上地震后 Cobre Panama 铜矿设施保持稳定',
                'SMM 国际站报道，Cobre Panama 在社交媒体表示，巴拿马当地时间 10 月 9 日中午发生 7 级以上地震、随后数小时内发生数十次余震，但矿山生产设施与基础设施保持稳定。该矿是中美洲最大露天铜矿，位于巴拿马加勒比海一侧，由加拿大第一量子矿业子公司运营，投资超过 100 亿美元，年产铜精矿约 30 万~35 万吨。',
                orig_title='Cobre Panama Copper Mine Stable After Major Earthquake Strikes Panama')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202610/t20261010_10332108.htm',
                '全球矿产资源信息系统', '10-10',
                '巴拉圭拟出台新矿业法，瞄准铀、钛及锂稀土',
                '全球矿产资源信息系统援引 BNAmericas 报道，巴拉圭能矿部副部长贝哈拉诺在第二届矿业论坛上表示，巴拉圭可能开始开发本国自然资源，主要是铀和钛，未来还可能包括锂或稀土；总统培尼亚正推动建立强有力的监管体系，政府正评估提交基于全球最佳实践的《矿业法》，为矿业投资提供法律确定性。报道称，随着全球寻求供应链多元化，巴拉圭希望复制智利、秘鲁、阿根廷和巴西等南美资源国的投资热度。')),

    (CAT_GJ, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/1009/62127.html',
                '中国有色金属工业协会', '10-09',
                '机构：关键矿产国际合作从贸易主导向供应链主导转变',
                '中国有色金属工业协会网刊文分析 2026 年全球关键矿产合作新动向：7 月韩国与巴西宣布扩大关键矿产全周期合作，8 月澳大利亚与越南同意加强关键矿产供应链合作。文章认为两组合作折射出四层变革——合作模式从贸易主导转向供应链主导、资源国价值诉求集体抬升、制造国主动多元化布局、制度框架与合作机制深度绑定；关键矿产正从商品属性转变为战略纽带。')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104148615-smm-tungsten-analysis-one-market-two-prices-how-to-break-the-structural-deadlock-in-the-tungsten-market',
                'SMM 国际站', '10-11',
                'SMM：钨市场“有价无市”，核心矛盾转向冶炼环节',
                'SMM 国际站分析指出，海外钨矿正加速放量，但国际钨市场的核心矛盾已悄然转移——矿石挖得出来，冶炼环节却跟不上；更值得关注的是下跌的并非原料，而是废钨与钨制品，市场呈现“有价无市”的结构性僵持。',
                orig_title='[SMM Tungsten Analysis] One Market, Two Prices: How to Break the Structural Deadlock in the Tungsten Market?')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-10/1225599560.PDF',
                '巨潮资讯网', '10-10',
                '赣锋锂电 1 亿元参与的产业基金完成私募备案',
                '巨潮资讯网披露，赣锋锂业（002460）公告控股子公司江西赣锋锂电科技股份有限公司认缴出资 10,000 万元与其他合作方共同投资共青城赣锋天泰创业投资合伙企业（有限合伙），赣锋锂电持有基金 45.8716% 份额；近日该基金已在中国证券投资基金业协会完成私募投资基金备案。')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104150512-colombia-signs-168m-contracts-for-copper-gold-and-phosphate-exploration-and-exploitation',
                'SMM 国际站', '10-11',
                '哥伦比亚签署 9 宗铜金磷矿勘查开发合同，预计投资 1,680 万美元',
                'SMM 国际站报道，哥伦比亚国家矿业局（ANM）称已签署 9 宗战略矿产勘查开发特殊合同，涉及铜、金和磷矿，预计投资近 54 亿比索（约合 1,680 万美元）。这些合同在 2026 年矿业招标轮框架下签署，对应塞萨尔、拉瓜希拉、安蒂奥基亚、托利马和乌伊拉省的战略矿业区，其中 8 宗来自铜、金及多金属招标轮，1 宗来自磷矿招标轮。',
                orig_title='Colombia Signs $16.8M Contracts for Copper, Gold, and Phosphate Exploration and Exploitation')),

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
