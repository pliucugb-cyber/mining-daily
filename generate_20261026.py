# -*- coding: utf-8 -*-
"""
生成 2026-10-26 矿业资讯速览 index.html（周一）
- 10-25 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-27）回补历史条目
- 换入 10-26 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-23 收盘 + LME 10-23 收盘（10-24/10-25 周末休市、10-26 未开盘），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（本批 ky.mnr 无新增合规公告，仅 1 宗石材类按口径剔除）
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

REPORT = '2026-10-26'
GRAB = '2026-10-26'
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
                         r'\g<1>2026年10月26日 星期一', html)
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
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/ddyw/202610/t20261023_870838.html',
                '中国地质调查局', '10-23',
                '中国地质调查局举办二维地震勘探野外实训，15 家单位近 40 名骨干参训',
                '10 月 13 日至 17 日，中国地质调查局在河北平泉举办二维地震勘探野外实训，依托华北地台页岩油地质调查项目，设置 2 场专题授课与 3 条野外路线，聚焦双复杂山地二维地震采集技术难点。局属 15 家单位近 40 名技术骨干参与现场测量、钻井、井炮激发、资料采集全流程工序，覆盖部署地质目标、激发采集与资料处理解释。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/newscontent/104176906-european-commission-launches-sunset-review-of-anti-dumping-duties-on-chines',
                'SMM 国际站', '10-25',
                '欧盟对华铝板带箔反倾销措施启动日落复审，现行税率 14.3% 至 24.6%',
                '欧盟委员会 10 月 9 日正式对原产于中国的铝板带箔反倾销措施发起期终（日落）复审，现行税率 14.3% 至 24.6%，涉案产品厚度 0.03 毫米至 6 毫米以上，涵盖卷材、定尺板与圆片，涉及十余个 CN 编码；复审期间措施继续有效，中国企业须在公告后 7 日内提交抽样信息。此前 1 月 26 日公告称措施将于 10 月 12 日到期，欧洲铝业协会于 6 月提出复审申请。',
                orig_title='European Commission Launches Sunset Review of Anti-Dumping Duties on Chinese Aluminium Products')),

    (CAT_ZC, ni('https://news.metal.com/newscontent/104176908-eu-carbon-border-mechanism-to-reshape-aluminium-trade-shift-focus-to-low-ca',
                'SMM 国际站', '10-25',
                '欧盟碳边境调节机制进入正式实施期，铝板带箔出口须建 MRV 体系',
                '2026 年欧盟碳边境调节机制（CBAM）进入正式实施阶段，铝板带箔被明确纳入 CBAM 产品清单。出口企业须建立合规的监测、报告与核查（MRV）体系，向原料供应商获取前体材料隐含排放数据，并委托经 EN ISO/IEC 17029 认可的核查机构出具英文报告；市场观点认为反倾销税叠加碳关税，正把中国铝板带箔对欧出口的竞争逻辑由成本竞争转向合规、低碳与技术竞争。',
                orig_title='EU Carbon Border Mechanism to Reshape Aluminium Trade, Shift Focus to Low-Carbon Compliance')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104176870',
                '上海有色网', '10-24',
                'CME：铜市加速区域化，纽约与上海铜价分化、LME 基准地位受挑战',
                'CME 集团全球金属业务负责人 Jin Hennig 在 LME 周期间表示，铜市正日益区域化、碎片化，"一价通吃"已不再有效，纽约与上海铜价分别反映当地供需与政策差异。9 月 22 日 Comex 铜价一度升至每磅 6.83 美元（约每吨 15,057 美元）历史高位，较 2025 年初上涨 50%；Comex 注册仓库逾 70 万吨铜除非 LME 价格显著高于 Comex 或欧洲溢价走高，否则难以流出。')),

    (CAT_SC, ni('https://news.smm.cn/news/104174337',
                '上海有色网', '10-23',
                '供应过剩压制欧洲镍溢价，贸易商预计年底前再跌 50 至 100 美元/吨',
                'S&P Global Energy CERA 将 2026 年 LME 三个月期镍均价预测由 17,548 美元/吨下调至 17,311 美元/吨，预计 2026 年原生镍供应 373.3 万吨、需求 365.4 万吨，过剩 7.9 万吨，2027 与 2028 年分别收窄至 3 万吨、2.6 万吨，2029 年转为短缺。10 月 12 日 LME 镍库存 282,504 吨；欧洲贸易商称年底前鹿特丹现货溢价或再跌 50 至 100 美元/吨。')),

    (CAT_SC, ni('https://news.smm.cn/news/104171722',
                '上海有色网', '10-23',
                '9 月中国进口碳酸锂 2.88 万吨同比增 47%，锂辉石进口 97.01 万吨',
                '海关数据显示，2026 年 9 月中国进口碳酸锂 28,826 吨，环比减少 5%、同比增加 47%，其中自智利进口 18,521 吨占 64%、自阿根廷 7,607 吨占 26%；1 至 9 月累计进口 26.5 万吨、同比增 53%。当月锂辉石进口 97.01 万实物吨、折碳酸锂当量约 8.13 万吨，环比增 7.0%，澳大利亚占 46.0%；9 月底碳酸锂现货降至 12.28 万元/吨，较月初跌 23.3%。')),

    (CAT_SC, ni('https://news.metal.com/newscontent/104176830-30000-mt-alumina-traded-at-361mt-fob-india-for-nov-shipment',
                'SMM 国际站', '10-23',
                '3 万吨氧化铝以 361 美元/吨 FOB 印度成交，船期 11 月',
                '2026 年 10 月 23 日，3 万吨氧化铝以 361 美元/吨 FOB 印度成交，船期为 11 月。该笔成交为当周亚洲氧化铝现货市场具代表性的出口报价，可用于观察印度货源对国内氧化铝内外价差的影响。',
                orig_title='30,000 mt Alumina Traded at $361/mt FOB India for Nov Shipment')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.metal.com/newscontent/104176902-chongqings-250-ktyr-aluminum-project-advances-phase-i-80-complete-targeting',
                'SMM 国际站', '10-25',
                '重庆万州 25 万吨铝板带箔项目一期进度超 80%，目标 11 月底投产',
                '重庆万州 25 万吨铝板带箔项目一期总体进度超 80%，土建逾 90%、设备安装约 50%；铸轧车间 15 台熔炼炉已装 6 台、12 台铸轧机已装 6 台，目标 11 月底启动，两台冷轧机机械安装 50%、12 月初联动调试、12 月全线试生产。项目由重庆高峰新材料建设，属博赛集团 52 亿元铝一体化利用工程三个子项目之一，占地 230 亩，一期 15 万吨、二期 10 万吨，一期年产值约 35 亿元，两期达产后约 55 亿元。',
                orig_title="Chongqing's 250 kt/yr Aluminum Project Advances: Phase I 80% Complete, Targeting End-November Startup")),

    (CAT_HY, ni('https://news.metal.com/newscontent/104176893-sichuan-jiuda-aluminium-breaks-ground-on-rmb-400m-high-tech-battery-materia',
                'SMM 国际站', '10-25',
                '四川九达铝业 4 亿元电池材料项目开工，新增 5 条电池箔产线',
                '四川九达铝业 5 万吨高端电池材料项目在广元经济技术开发区袁家坝铝产业园开工，总投资 4 亿元、占地 25,073.89 平方米。项目将新增 5 条各 1 万吨/年高精度电池箔产线，以及 6,000 吨/年铝铜复合带材、2,400 吨/年铝铜复合箔，配套分切、精切与退火设施；全面达产后预计年产值 13 亿元、税收 9,030 万元，计划 2026 年 10 月投产。',
                orig_title='Sichuan Jiuda Aluminium Breaks Ground on RMB 400M High-Tech Battery Materials Project in Guangyuan')),

    (CAT_HY, ni('https://news.metal.com/newscontent/104176926-tianqi-lithium-q3-net-profit-',
                'SMM 国际站', '10-25',
                '天齐锂业三季度净利 13.6 亿元同比增 1,324%，营收增 135%',
                '天齐锂业三季度营业收入 60.37 亿元、同比增长 135.40%，净利润 13.60 亿元、同比增长 1,323.97%；前三季度营业收入 182.79 亿元、同比增长 147.11%，净利润 56.02 亿元、同比增长 3,013.86%。公司称利润增长主要因新能源行业发展与下游需求增长带动主要锂产品均价同比明显上升，同时来自联营公司 SQM 的投资收益同比增加。',
                orig_title='Tianqi Lithium: Q3 Net Profit +1324% YoY, -42% QoQ')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474846',
                '中国有色金属报', '10-23',
                '圭亚那奥罗拉金矿地采一期 8,615 米 RK 斜坡道提前 2 个月贯通',
                '圭亚那奥罗拉金矿地采一期 RK 超长斜坡道工程近日实现精准贯通，较计划工期提前 2 个月。该斜坡道总长 8,615 米，是地采一期现阶段最长巷道，属矿山深部基建关键性工程，由宏大爆破项目部施工；贯通后将提升井下物流运输效率与通风系统运行效能。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474758',
                '中国有色金属报', '10-20',
                '前三季度我国原镁产量 87.02 万吨同比增 19.73%，陕西占比近七成',
                '中国有色金属工业协会镁业分会统计显示，9 月国内原镁产量约 8.61 万吨，环比降 6.11%、同比降 3.8%；1 至 9 月累计产量 87.02 万吨、同比增 19.73%。区域分化加剧：陕西累计 60.46 万吨、同比增 32.65%，山西 12.08 万吨、同比降 16.57%，内蒙古 2.45 万吨、同比降 17.79%，新疆 4.32 万吨、同比增 10.2%。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/newmont-prices-red-chris-expansion-at-up-to-4-8b/',
                'MINING.COM', '10-23',
                '纽蒙特 Red Chris 铜金矿转地下扩建，投资上限 48 亿美元',
                '纽蒙特（Newmont）将为加拿大不列颠哥伦比亚省 Red Chris 铜金矿转地下开采投入最高 64 亿加元（约 48 亿美元），目标 2033 年实现商业生产。项目 2035 至 2040 年年均产金 27.5 万至 32.5 万盎司、铜 6.5 万至 8.5 万吨；公司持股 70%，与帝国金属共同运营，工程完成度至少 60%，可研接近收尾，2027 年有望开工，资金来自内部现金流。',
                orig_title='Newmont prices Red Chris expansion at up to $4.8B')),

    (CAT_MA, ni('https://www.mining.com/web/first-quantum-readies-argentina-tax-break-plans-for-5-3-billion-taca-taca-copper-project/',
                'MINING.COM', '10-23',
                '第一量子拟为阿根廷 Taca Taca 铜矿申请 RIGI 税收优惠，投资至多 52.5 亿美元',
                '阿根廷外长 Quirno 表示，第一量子矿业计划年内为 Taca Taca 铜矿申请大型投资激励制度（RIGI），初始投资 42 亿美元、最高可达 52.5 亿美元，将创造最多 4,000 个建设岗位与 2,000 个运营岗位。项目位于萨尔塔省、距智利边境 55 公里，公司称年产铜约 20.9 万吨、矿山寿命 35 年，并具扩产空间。',
                orig_title='First Quantum readies Argentina tax-break plans for $5.3 billion Taca Taca copper project')),

    (CAT_MA, ni('https://www.mining.com/web/grupo-mexico-to-press-ahead-with-major-us-copper-projects-after-output-dip/',
                'MINING.COM', '10-23',
                '墨西哥集团三年投 40 至 60 亿美元扩建美国铜矿与冶炼厂',
                '墨西哥集团（Grupo Mexico）表示，未来三年将在美国子公司 Asarco 的主要项目投入 40 亿至 60 亿美元，扩建亚利桑那州 Ray 与 Silver Bell 两矿，并争取重启 Hayden 冶炼厂与精炼厂。Hayden 若重启可年处理 140 万吨铜精矿、对应约 35 万吨含铜量，经精炼后或达 50 万吨；公司三季度铜产量同比下降约 2%，股价当日跌逾 4%。',
                orig_title='Grupo Mexico to press ahead with major US copper projects after output dip')),

    (CAT_MA, ni('https://www.mining.com/web/mmg-to-guarantee-european-ferronickel-supply-to-address-eu-concerns-about-anglo-american-deal/',
                'MINING.COM', '10-23',
                '五矿资源承诺保障欧洲镍铁供应，以化解欧盟对 5 亿美元收购案关切',
                '港股上市的五矿资源（MMG）提出以英国法下具法律约束力的担保，维持对欧洲不锈钢企业的镍铁供应量，以化解欧盟对其 5 亿美元收购英美资源巴西镍业务的竞争关切。欧盟委员会此前担忧 MMG 可能把镍铁供应转向中国、损害欧洲不锈钢企业；英美资源称该救济方案应促成交易获批，并曾威胁若交易被否将关闭该巴西矿山。',
                orig_title='MMG to guarantee European ferronickel supply to address EU concerns about Anglo American deal')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/chinas-argentina-mining-footprint-smaller-than-it-looks',
                'MINING.COM', '10-25',
                'Plusmining：中资仅占阿根廷 RIGI 矿业投资 9.2%，远低于 70% 说法',
                '智利咨询机构 Plusmining 分析显示，截至 10 月 1 日阿根廷 RIGI 制度下已批准 23 个项目、总额 498 亿美元，其中矿业 12 项、212 亿美元；按中资直接与间接持股加权，中资对应投资约 19.5 亿美元、占矿业投资 9.2%。广泛引用的 70% 指的是含中资股东项目的公告锂产能口径；紫金控制 Tres Quebradas、赣锋持 Cauchari-Olaroz 扩建 46.7%、山东黄金持 Veladero 第八九期 50%。',
                orig_title="China's Argentina mining footprint smaller than it looks")),

    (CAT_GJ, ni('https://news.smm.cn/news/104176871',
                '上海有色网', '10-23',
                'Halo Minerals 智利铜项目获准疏浚，尾矿回收项目推进落地',
                'Halo Minerals 表示，智利当地主管部门已批准 Playa Verde 的疏浚作业，使其尾矿回收铜项目向建设推进迈出关键一步。该项目以既有尾矿为原料回收铜，疏浚许可是其取得环境与作业许可链条中的核心环节，公司下一步将推进现场施工与产能建设。')),
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
    ('二维地震', CAT_ZK),
    ('天齐锂业', CAT_HY),
    ('原镁', CAT_HY),
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
