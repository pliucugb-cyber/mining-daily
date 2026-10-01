# -*- coding: utf-8 -*-
"""
生成 2026-10-01 矿业资讯速览 index.html（周四 · 国庆）
- 09-30 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-02）回补历史条目
- 换入 10-01 抓取的最新条目（is-new + NEW），更新计数
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

REPORT = '2026-10-01'
GRAB = '2026-10-01'
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
                         r'\g<1>2026年10月01日 星期四', html)
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
    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260930_10327477.htm',
                '全球矿产资源信息系统', '09-30',
                '印度拟将钢铁年产能提升至 6 亿吨',
                '印度钢铁部长宣布新钢铁政策规划：到 2047 年将年产能由目前 2.2 亿吨提升至 6 亿吨，并制定排放削减与铁矿石、焦煤等原材料保障措施。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104142308',
                '上海有色网', '09-30',
                '节前最后交易日金属期货涨跌互现，氧化铝领涨',
                'SMM 日评：9 月 30 日国内基本金属普跌，仅沪铜涨 0.35%、沪锡涨 0.15%，沪镍跌 0.83% 领跌；氧化铝主连涨 2.45%。9 月制造业 PMI 回升至 50.1%。')),

    (CAT_SC, ni('https://news.smm.cn/news/104142160',
                '上海有色网', '09-30',
                '金银铂钯反弹，贵金属板块拉升',
                'SMM 快讯：美联储官员表态鸽鹰参半，10 月加息预期概率由约 70% 回落至 50% 左右，美元走弱叠加避险与央行购金需求，金银铂钯同步反弹，沪金主连涨 1%。')),

    (CAT_SC, ni('https://news.smm.cn/news/104142996',
                '上海有色网', '09-30',
                '韩国央行时隔 13 年重启买金，12 月拟购 1 吨国产黄金',
                '韩国央行计划今年 12 月买入约 1 吨国产黄金，为其 2013 年以来首次增持实物黄金储备；交易将于 12 月 14 日生效的新规下通过独立协商大宗账户完成。')),

    (CAT_SC, ni('https://news.smm.cn/news/104142340',
                '上海有色网', '09-30',
                '金钼股份：预计钼价将继续维持高位运行',
                '金钼股份在投资者关系活动中表示，上半年钼精矿均价 4560 元/吨度、同比上涨 28%，近期涨至 5400 元/吨度，预计钼价将继续维持高位；上半年销售钼 1.87 万吨。')),

    (CAT_SC, ni('https://news.smm.cn/news/104142261',
                '上海有色网', '09-30',
                '天赐材料：未来 2—3 年储能电池需求增速有望高于动力电池',
                '天赐材料表示电解液及六氟磷酸锂产能利用率已基本满产，订单需求饱满；从下游反馈看，数据中心需求提升有望带动储能电池增速继续高于动力电池。')),

    (CAT_SC, ni('https://news.smm.cn/news/104142921',
                '上海有色网', '09-30',
                '东方钽业：高附加值钽铌产品国内需求逐步上升',
                '东方钽业表示高温合金、半导体钽靶材及高纯铌材等国内需求正逐步上升；上半年营业收入 10.40 亿元、同比增长 30.50%，11.89 亿元募投项目进入设备安装调试阶段。')),

    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104143124-smm-flash-newsmasivo-intersects-3250-metres-of-lead-zinc-bearing-polymetallic-mineralization-at-cerro-colorado',
                'SMM 国际站', '10-01',
                'Masivo 墨西哥 Cerro Colorado 首孔见 32.50 米铅锌多金属矿',
                'SMM 国际站报道，Masivo Silver 在墨西哥索诺拉州 Cerro Colorado 首孔 CC-26-001 见矿 32.50 米，平均品位锌 0.271%、铅 0.141%、银 7.0 克/吨。',
                orig_title='【SMM Flash News】Masivo Intersects 32.50 Metres of Lead-Zinc-Bearing Polymetallic Mineralization at Cerro Colorado')),

    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104143120-smm-flash-newstomagold-reports-6940-metres-grading-194-zinc-at-berrigan-deep',
                'SMM 国际站', '10-01',
                'TomaGold 加拿大 Berrigan 深部见 69.40 米锌矿化',
                'SMM 国际站报道，TomaGold 公布加拿大魁北克 Berrigan 项目二阶段最后三孔结果，TOM-25-012EXT 见矿 69.40 米、品位 1.94% 锌，含 4.20 米 16.49% 锌。',
                orig_title='【SMM Flash News】TomaGold Reports 69.40 Metres Grading 1.94% Zinc at Berrigan Deep')),

    (CAT_ZK, ni('https://www.mining.com/hercules-extends-idaho-copper-discovery',
                'MINING.COM', '09-30',
                'Hercules 扩展美国爱达荷铜矿发现',
                'MINING.COM 报道，Hercules Metals 爱达荷 Southern Flats 铜矿发现向西延伸 200 米，钻孔 HER-26-01 自 862.6 米起见矿 286.5 米、铜品位 0.43%。',
                orig_title='Hercules extends Idaho copper discovery')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104143138-smm-nickel-flashindonesia-npi-loses-access-to-european-market-amid-carbon-footprint-rules',
                'SMM 国际站', '10-01',
                '印尼镍铁因碳足迹规则失去欧洲市场准入',
                'SMM 国际站援引 Eramet 称，印尼镍铁（NPI）因依赖燃煤自备电、碳排放偏高，在欧盟碳边境调节机制（CBAM）进入实质阶段后已失去欧洲市场准入。',
                orig_title='【SMM Nickel Flash】Indonesia NPI Loses Access to European Market Amid Carbon Footprint Rules')),

    (CAT_HY, ni('https://news.metal.com/en/newscontent/104139874-smm-launches-aluminium-cbam-calculator-what-cost-estimates-mean-for-eu-bound-offerssmm-analysis',
                'SMM 国际站', '10-01',
                'SMM 推出铝 CBAM 计算器',
                'SMM 推出铝碳边境调节机制（CBAM）计算器，覆盖 58 个 CN 编码与 68 个原产地/默认值类别，整合产品、原产地、排放数据与证书价格，支持对欧出口报价核算。',
                orig_title='SMM Launches Aluminium CBAM Calculator: What Cost Estimates Mean for EU-Bound Offers')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/panama-commission-urges-orderly-closure-of-first-quantums-cobre-mine',
                'MINING.COM', '09-30',
                '巴拿马委员会建议有序关闭第一量子 Cobre 铜矿',
                'MINING.COM 报道，巴拿马三部委委员会建议总统下令有序关闭第一量子 Cobre Panama 铜矿，与市场此前对复产的预期相反；该矿停产后该国减少近 3.6 万个岗位、税费与权利金减少近 14 亿美元。',
                orig_title='Panama commission urges orderly closure of First Quantum’s Cobre mine')),

    (CAT_GJ, ni('https://www.mining.com/gold-fields-halts-windfall-work-as-quebec-permit-lapses',
                'MINING.COM', '09-30',
                'Gold Fields 因魁北克许可到期暂停 Windfall 项目施工',
                'MINING.COM 报道，Gold Fields 旗下投资 19 亿美元的加拿大魁北克 Windfall 金矿因勘查工作许可 8 月底到期，已暂停井下开拓，等待省级环境审批；项目目标 2029 年产金 30 万盎司。',
                orig_title='Gold Fields halts Windfall work as Quebec permit lapses')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104139507-smm-analysis-the-us-copper-tariff-trade-is-fading-but-it-isnt-over-yet',
                'SMM 国际站', '10-01',
                '美国铜关税交易降温但风险未消',
                'SMM 分析称，9 月 29 日午前美国未公布精炼铜关税，COMEX-LME 价差收窄使套利窗口关闭；但 COMEX 库存已由 32 万短吨升至近 77 万短吨，中国社会库存降至 7.83 万吨。',
                orig_title='[SMM Analysis] The U.S. Copper Tariff Trade Is Fading — but It Isn’t Over Yet')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104143105-india-has-yet-to-decide-on-scrapping-pre-shipment-inspections-for-metal-scrap-imports',
                'SMM 国际站', '10-01',
                '印度尚未决定取消废金属进口装运前检验',
                'SMM 国际站报道，印度对外贸易总局 9 月 30 日称尚未决定取消进口废金属的装运前检验要求，正在评估行业协会提案；印度每年进口约 1300 万吨可回收废金属。',
                orig_title='India Has Yet to Decide on Scrapping Pre-Shipment Inspections for Metal Scrap Imports')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104143102-kazakhstan-and-aurubis-explore-copper-scrap-and-secondary-resource-processing-projects',
                'SMM 国际站', '10-01',
                '哈萨克斯坦与 Aurubis 探讨铜废料与二次资源加工合作',
                'SMM 国际站报道，哈萨克斯坦与 Aurubis 探讨铜回收与二次资源加工合作，哈国有 Tau-Ken Samruk 与 Aurubis 正考虑加工铜废料与技术成因矿物，目前仍处讨论阶段。',
                orig_title='Kazakhstan and Aurubis Explore Copper Scrap and Secondary Resource Processing Projects')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104140015-south-africa-poised-to-become-key-player-in-global-rare-earth-supply-chain-by-2034smm-analysis',
                'SMM 国际站', '09-29',
                '南非有望 2034 年前成为全球稀土供应链关键角色',
                'SMM 分析称，南非凭借高品位独居石、磷石膏尾矿回收、磁性稀土与电池级锰的协同，有望在 2034 年前成为全球稀土供应链关键节点，Steenkampskraal 等三个项目驱动市场预期。',
                orig_title='South Africa Poised to Become Key Player in Global Rare Earth Supply Chain by 2034')),

    (CAT_GJ, ni('https://www.mining.com/mining-forum-friedland-wants-to-kill-the-sag-mill',
                'MINING.COM', '09-29',
                'Friedland 提出以脉冲电能替代 SAG 磨机',
                'MINING.COM 报道，Ivanhoe Mines 创始人 Friedland 称其私营公司 I-Pulse 的脉冲电能碎矿技术可较传统磨矿节能至多 80%、提高金属回收率约 5%，目标是取代 SAG 磨机与球磨机。',
                orig_title='Mining Forum: Friedland wants to kill the SAG mill')),

    (CAT_GJ, ni('https://www.mining.com/us-doe-awards-29-5m-for-17-national-lab-mining-tech-projects',
                'MINING.COM', '09-30',
                '美国能源部拨款 2950 万美元支持 17 个矿业技术项目',
                'MINING.COM 报道，美国能源部通过关键矿产与能源创新办公室向 12 个国家实验室的 17 个矿业技术项目拨款 2950 万美元，覆盖地下采出、自主勘探、二次资源与先进选矿。',
                orig_title='US DOE awards $29.5M for 17 National Lab mining tech projects')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.smm.cn/news/104142616',
                '上海有色网', '09-30',
                '龙佰集团拟约 7.66 亿元并购澳大利亚矿砂项目',
                '龙佰集团与澳交所上市公司 Image Resources 签署条款清单，拟以约 1.6 亿澳元（约 7.66 亿元人民币）取得西澳 Durack、Yandanooka 矿砂项目约 80% 权益，保障钛精矿原料供应。')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104143106-liontown-makes-final-investment-decision-on-kathleen-valley-lithium-mine-expansion',
                'SMM 国际站', '10-01',
                'Liontown 批准 3.89 亿澳元扩建 Kathleen Valley 锂矿',
                'SMM 国际站报道，澳大利亚 Liontown Resources 就 Kathleen Valley 锂矿扩建作出最终投资决定，批准 3.89 亿澳元资本开支，年处理能力将由约 280 万吨提升至 420 万吨。',
                orig_title='Liontown Makes Final Investment Decision on Kathleen Valley Lithium Mine Expansion')),

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
