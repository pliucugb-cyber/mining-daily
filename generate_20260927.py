# -*- coding: utf-8 -*-
"""
生成 2026-09-27 矿业资讯速览 index.html（周日）
- 09-26 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-28）回补历史条目
- 换入 09-24~09-27 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-24 收盘 + LME 09-25 收盘（周日休市，东财日K末点=09-24，卡片=走势图口径），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层，不进主页列表（本日 ky.mnr 三宗均为石料/夹缝类小宗，按口径不收）
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

REPORT = '2026-09-27'
GRAB = '2026-09-27'
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
                         r'\g<1>2026年09月27日 星期日', html)
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
    (CAT_ZK, ni('https://www.mining.com/op-ed-understanding-lct-pegmatites-why-context-can-make-or-break-a-lithium-project',
                'MINING.COM', '09-26',
                'MINING.COM 专栏：LCT 伟晶岩的地质语境决定锂项目成败',
                'MINING.COM 刊发地质咨询机构 Mineral Consulting 的专栏文章指出，锂—铯—钽（LCT）伟晶岩天然强分带，常规钻孔化验只给出锂总量的平均值，无法反映锂究竟赋存于易选的粗粒锂辉石，还是难以处理的细粒云母与黏土，后者会拖低精矿品位并抬高杂质。文章以澳大利亚 Mount Marion（出现未建模的细粒锂辉石与高云母带，改变选矿行为、压低精矿品位）、加拿大 Tanco（曾假定锂矿化全部为约 60% 锂辉石加 40% 石英的均匀结构）为例，并指出 Patriot Battery Metals 魁北克 Shaakichiuwaanaan 项目的 20 件岩芯矿物学结果未纳入三维块体模型、仅以基于锂总量的简化公式估算回收率；高砷、高锑块段往往对应锂辉石被晚期交代流体破坏的低回收区。',
                orig_title="Op-Ed: Understanding LCT pegmatites \u2013 why context can make or break a lithium project")),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104134769',
                '上海有色网', '09-27',
                '联合国启动关键矿产“国家支持机制”',
                '联合国 9 月 23 日启动新的“国家支持机制”，帮助资源丰富的发展中国家建立可持续的关键矿产产业、扩大矿产加工与工业发展，并从全球能源转型中获得更大份额的收益。该机制将提供治理、矿产加工、环境与社会保障方面的协调技术与能力建设援助，几内亚、印度尼西亚、马达加斯加、尼日利亚、赞比亚和津巴布韦成为首批获得专门支持的国家，由联合国开发计划署与联合国发展协调办公室牵头，通过联合国驻地办事处运作。',
                )),
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474202',
                '中国有色金属报', '09-22',
                '美国 232 条款对多晶硅及光伏产品加征 15% 关税并设最低限价',
                '8 月 6 日，美国依据《1962 年贸易扩展法》第 232 条款（第 11052 号公告）对进口多晶硅及其衍生产品加征 15% 关税，并叠加最低进口价格机制：多晶硅最低限价 21 美元/公斤、组件最低限价 0.38 美元/瓦，覆盖多晶硅、硅片、电池及组件全产业链，12 月 4 日正式生效。公告同时设“回流美国”激励通道，企业在 2029 年 1 月 20 日前承诺在美建厂可申请部分进口设备免缴关税；文章分析认为，中国多晶硅直接出口美国规模极小，但限制东南亚加工转口路径的间接影响不可忽视。',
                )),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104134764',
                '上海有色网', '09-27',
                'SMM 假期行情回顾：外盘金属普跌 伦锡涨逾 1% 伦锌跌近 2%',
                '上海有色网回顾 9 月 25 日（周五）行情：LME 基本金属普跌，伦铜 -0.1%、伦铝 +0.8%、伦铅 -0.13%、伦锌 -1.8%、伦锡 +1.3%、伦镍 -0.88%；COMEX 黄金当日涨 0.52% 但周线下跌 2.36%，COMEX 白银当日涨 1.11%、周线下跌 3.63%；美股三大指数收涨，美元指数收于 101.03、周线涨 0.81%。同时提示国庆假期安排：9 月 30 日上金所、上期所等因节前无夜盘交易，10 月 1 日至 10 月 7 日沪深及国内期货交易所休市。',
                )),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104134304-geopolitical-risks-fluctuate-and-rate-hike-expectations-heat-up-copper-prices-retreat-after-rapid-rise-smm-macro-weekly-review',
                'SMM 国际站', '09-27',
                'SMM 宏观周评：地缘风险反复叠加加息预期升温，铜价冲高回落',
                'SMM 宏观周评指出，本周铜价先涨后跌：周初美伊高层对话释放缓和信号、沙特恢复延布港出口，油价回落；随后美伊关系再起波折，叠加美国 9 月标普全球制造业 PMI 初值升至 57（近五年高位）强化加息预期，美元与美债收益率走强，铜价自高位回落，周内 LME 铜最高触及 14,799 美元/吨、沪铜主力最高 111,840 元/吨。国内 SMM 铜社会库存周环比减少 1.65 万吨至 7.26 万吨，SHFE/LME 比价回落至 7.6、进口亏损扩大至 1,500 元/吨以上；SMM 预计下周 LME 铜运行区间 14,350—14,800 美元/吨、沪铜 109,800—112,000 元/吨。',
                orig_title="Geopolitical Risks Fluctuate and Rate Hike Expectations Heat Up, Copper Prices Retreat After Rapid Rise [SMM Macro Weekly Review]")),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104129249-why-is-shfe-coppers-three-highs-market-intensifying',
                'SMM 国际站', '09-27',
                'SMM：沪铜高升水、高负价差、高价格的“三高”行情为何加剧',
                'SMM 分析认为，铜价自前期高位回落后下游订单增长明显、升水悄然走高，叠加阴极铜供应扰动加剧，下游在刚需采购与节前备货中被迫接受“三高”行情：上海现货铜升水已突破 1,000 元/吨，SHFE 铜远期合约对 LME 三个月期铜的负价差仍超 1,000 元/吨，节前国内到货预计有限。文章提示节后市场转向交割逻辑，近月 BACK 结构仍有走阔空间，10 月升水甚至可能进一步上行，需警惕高升水、宽价差环境下的波动风险。',
                orig_title="Why Is SHFE Copper\u2019s \u201cThree Highs\u201d Market Intensifying?")),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104129430-smm-analysis-chinas-shifting-tungsten-trade-landscape-a-strategic-view',
                'SMM 国际站', '09-27',
                'SMM：中国钨品贸易格局转变，8 月进口激增、出口承压',
                'SMM 依据海关数据分析，2026 年 8 月中国钨品进口总量 5,590.6 吨、环比增 39.3%，折钨金属量 2,477.6 吨、同比增 97.8%，年内累计进口 25,839.5 吨、同比增 91.7%；同期钨品出口 1,289.7 吨、环比降 5.2%、同比降 28.4%，折金属量 1,054.3 吨、同比降 31.7%。其中 8 月钨精矿进口实物量 5,505.8 吨、环比增 39.6%、同比增 152%，年内累计 25,026.4 吨、同比增 116%；SMM 认为在国内矿石品位逐年下降、环保与合规整改持续收紧的背景下，加大海外初端钨原料进口具有长周期战略意义。',
                orig_title="[SMM Analysis] China\u2019s Shifting Tungsten Trade Landscape: A Strategic View")),
    (CAT_SC, ni('https://www.mining.com/ai-boom-fails-to-lift-gold-demand-wgc-says',
                'MINING.COM', '09-26',
                '世界黄金协会：AI 热潮尚未提振黄金需求',
                '世界黄金协会发布《AI Boom and Gold》报告指出，2025 年黄金在技术领域的需求基本持平于 323 吨，AI 芯片需求爆发被器件小型化与厂商“去金化”努力所抵消；2024 年技术用金曾增 7% 至 326 吨。协会认为电子行业用金正处于“拉锯”状态，但随着共封装光学（CPO）等先进封装普及，黄金在激光器等光学与光子部件中仍难替代，长期可能成为新的需求来源。报告发布当日（周五）金价报 4,270.30 美元/盎司，同比上涨近 14%；电子制造约占黄金工业用途的 80%。',
                orig_title="AI boom fails to lift gold demand, WGC says")),
    (CAT_SC, ni('https://www.mining.com/metals-are-stock-puppets-bloomberg-strategist-says',
                'MINING.COM', '09-26',
                '彭博策略师：金属已成股市“傀儡”，铜或随回调下跌 20%~30%',
                '彭博行业研究高级商品策略师 Mike McGlone 接受 MINING.COM 采访时表示，股市如今就是经济本身，金属整体上已成为股市的“傀儡”，其中铜与股市的联动最强：股市上涨时铜波动更大、表现更弱，而一旦股市出现正常的 10% 回调，铜价可能下跌 20%~30%。他还提醒当前金价“过热”，投资者应保持谨慎，并认为美联储近期加息体现了该国政治与市场之间的制衡与自我纠错机制。',
                orig_title="Metals are stock puppets, Bloomberg strategist says")),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474204',
                '中国有色金属报', '09-22',
                '宏源期货：美联储加息落地后黄金价格仍存上行动能',
                '宏源期货分析文章指出，美联储 9 月加息 25 个基点、点阵图显示年内还有 1 次加息；消息落地前金价一度涨超 4,368 美元/盎司，宣布加息后最低回落至 4,235 美元/盎司。文章认为，美国为中期选举可能与伊朗缓和冲突、油价随之回落，叠加加息利空出尽，贵金属短期有望反弹；中期虽市场预期美联储 2026 年 10 月及 2027 年 1 月、4 月继续加息，但多国央行持续增持黄金储备，金价下跌后仍有上行动能。',
                )),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474290',
                '中国有色金属报', '09-24',
                '焦作经开区打造全国最大钛合金材料生产基地',
                '焦作经济技术开发区围绕“四氯化钛—海绵钛—钛合金—钛制品”链条打造全国最大的钛合金材料生产基地，集聚河南中源钛业、焦作东锆新材料、焦作市维纳科技等重点企业，产品涵盖十余类钛合金品种；今年 1—7 月园区营业收入 224.17 亿元、同比增加 22.78%，税收收入 7.23 亿元。龙头企业龙佰集团的钛白粉、海绵钛产能居全球第一，产品远销 110 多个国家和地区，园区下一步将重点引进超薄钛带、超厚钛板材等深加工项目。',
                )),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474216',
                '中国有色金属报', '09-22',
                '中铝国际长沙院矿山无人自动安全巡检系统实现工业化应用',
                '中铝国际长沙有色冶金设计研究院自主研发的“矿山重大危险源无人自动安全巡检系统”实现工业化应用，集成无人机自动起降平台、工业无人机、数据采集中心、远程监控平台与远程维护中心五大模块。系统搭载激光雷达、红外传感器和高分辨率摄像头，可完成矿区测绘建模与全天候安全监控，并基于深度学习隐患预测算法提前识别山体滑坡、地面塌陷、森林火灾等风险，目前已在多个矿区部署并构建全场景数字孪生模型。',
                )),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474205',
                '中国有色金属报', '09-22',
                '铜冠铜箔上半年净利增 515%，高端 PCB 铜箔产量占比过半',
                '安徽铜冠铜箔集团上半年实现营业收入 40.21 亿元、同比增长 34%，归母净利润 2.15 亿元、同比增长 515%；高频高速基板用铜箔（RTF、HVLP）产量占 PCB 铜箔总产量比重突破 50%，HVLP4 代铜箔实现批量供货，PCB 铜箔营业收入 25.07 亿元、毛利率 11.6%、同比提升 6.04 个百分点。该公司在锂电铜箔加工费断崖式下跌后转向 AI 算力用高端铜箔，HVLP 铜箔可将高频信号传输损耗降低 40% 以上。',
                )),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474211',
                '中国有色金属报', '09-22',
                '陕西有色天策发布 3 款中间相沥青基碳纤维新产品',
                '陕西有色天策新材料科技有限公司在陕西省碳纤维及其复合材料产业链推介对接会（西安）上发布高碳型、超高模、高导热三大系列中间相沥青基碳纤维新产品，均已实现定型量产，关键性能指标对标国际先进水平，面向航空航天、精密装备减重提精度以及高端芯片、新能源电池等高功率电子设备散热场景。该公司为陕西省碳纤维及其复合材料产业链链主企业，将聚焦中间相沥青基碳纤维、高性能沥青系碳材料及高性能树脂及其复合材料三大领域持续发力。',
                )),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.smm.cn/news/104134767',
                '上海有色网', '09-27',
                '智利 Escondida 矿工会拒绝暂停合同谈判，9 月 28—30 日表决',
                '9 月 25 日（周五），全球最大铜矿智利埃斯孔迪达（Escondida）矿的工会驳回了管理层因本周早些时候发生致命事故而提出的暂停合同谈判请求，谈判按原计划继续进行。代表监督人员的工会将于 9 月 28 日至 30 日就公司最新合同提议投票，该工会已敦促成员拒绝提议，此举可能为罢工打开大门。该矿位于智利北部阿塔卡马沙漠，事故后暂停运营并于周四逐步恢复，由必和必拓运营，力拓持股 30%、日本 JECO 持股 12.5%。',
                )),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104134782-eu-draft-waste-shipment-list-excludes-india-malaysia-thailand-from-metal-scrap-imports',
                'SMM 国际站', '09-27',
                '欧盟废料清单草案拟将印度、马来西亚、泰国排除在金属废料进口之外',
                '欧盟委员会 9 月 18 日公布符合《废物运输条例》的非 OECD 国家草案清单，将印度、马来西亚和泰国排除在黑色与有色金属废料准入之外；欧盟自 2027 年 5 月 21 日起禁止向非 OECD 国家出口此类废料，清单内国家可获豁免，意见征询至 10 月 16 日。印度材料回收协会（MRAI）称该草案为贸易壁垒与资源保护主义，并提示欧盟分别占印度上财年铝废料进口（约 203 万吨）的 20%、铜及铜合金废料（47 万吨）的 22%、铅废料（21 万吨）的 20% 和锌废料（11 万吨）的 40%，其黑色与不锈钢废料进口 845 万吨中有 79 万吨来自欧盟。',
                orig_title="[EU Draft Waste Shipment List Excludes India, Malaysia, Thailand from Metal Scrap Imports]")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474203',
                '中国有色金属报', '09-22',
                '洛阳钼业完成 15 亿元科创债发行，票面利率 1.58%',
                '洛阳钼业 2026 年度第一期科技创新债券完成发行，发行总额 15 亿元、期限 3+2 年、票面利率 1.58%，创全国同行业同期限科创债及河南省同期限债券票面利率新低，募集资金计划全部用于偿还公司有息债务，认购倍数达 2.73 倍，主承销商及簿记管理人为中国银行。公司主体信用评级为 AAA；今年上半年实现营业收入 1353.20 亿元、同比增长 42.78%，归母净利润 161.52 亿元、同比大增 86.27%。',
                )),
    (CAT_MA, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474192',
                '中国有色金属报', '09-22',
                '中铝能源“四策并行”清退涉煤低效资产，资产负债率降至 29.7%',
                '作为中铝集团涉煤低效资产出清的专业化处置平台，中铝能源以股权转让、破产清算、股债打包转让、零费用注销“四策并行”模式攻坚“两非”“两资”清退；2023 年以来已完成 6 家涉煤企业的债务清收、股权出清与人员安置，自身资产负债率由 2023 年初的 75% 降至目前的 29.7%。其中陕西境内一家控股煤矿引来 6 家意向方、经 28 轮竞价成交，甘肃境内一家控股涉煤企业转让价较评估值溢价超 6%，贵州两家全资煤企已完成破产清算出表。',
                )),
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
