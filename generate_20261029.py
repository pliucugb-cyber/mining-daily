# -*- coding: utf-8 -*-
"""
生成 2026-10-29 矿业资讯速览 index.html（周四）
- 10-28 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-30）回补历史条目
- 换入 10-29 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-28 收盘 + LME 10-28 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目（ky.mnr 10-27 批 9 宗）直接追加进月库 → 前端 #rightsCards，不进主列表
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

REPORT = '2026-10-29'
GRAB = '2026-10-29'
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
                         r'\g<1>2026年10月29日 星期四', html)
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
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474962',
                '中国有色金属报', '10-27',
                '铜陵有色冬瓜山铜矿深部找矿新增铜金属量 36.87 万吨',
                '铜陵有色矿产资源中心完成的冬瓜山铜矿深部详查报告已评审备案：采矿权深部以下新增铜金属量 14.64 万吨，矿权内核实新增 22.23 万吨，合并新增 36.87 万吨。"十四五"期间深部勘查施工钻孔 300 余个、总进尺 10 万米；2023 年 6 月结束的南东段详查完成钻探 35,305.80 米、104 个孔，新增矿石量 1,455.3 万吨、铜金属量 11.4 万吨。该矿服务年限一度不足 15 年，现转向深部与边部找接替资源。')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202610/t20261028_10347765.htm',
                '全球矿产资源信息系统', '10-28',
                '科特迪瓦阿斐马金矿钻探见富矿，6 米见矿金品位 18.5 克/吨',
                '图拉科黄金公司（Turaco Gold）扩大科特迪瓦阿斐马项目钻探并见到高品位矿体：66 米深处见矿 6 米、金品位 18.5 克/吨；55 米深处见矿 10 米、金品位 6.56 克/吨。项目现有资源量 465 万盎司，加通贝祥认为可超 500 万盎司。预可行性研究需投资 4.42 亿美元，投产后前 7 年年产金 21.5 万盎司，总可持续生产成本 1,500 美元/盎司；资源量本季度更新。')),

    (CAT_ZK, ni('https://www.mining.com/firefly-finds-copper-gold-system-near-idle-mill',
                'MINING.COM', '10-28',
                'FireFly 在纽芬兰闲置选厂旁发现铜金矿化，22.5 米见矿铜品位 1.87%',
                'FireFly Metals 在纽芬兰 Green Bay 项目 Mount Joy 靶区钻孔 FFR26-071 自 109 米见矿 22.5 米、铜品位 1.87%、金 0.64 克/吨，矿点距 Ming 矿 35 公里、距 Nugget Pond 选厂 2.6 公里。后续孔 FFR26-076 在 240 至 280 米见约 40 米半块状硫化物，化验约 4 周后出。公司 2027 财年为区域勘探编列预算，Ming 资源更新与可行性研究定于 2027 年一季度，目标 2029 年投产。',
                orig_title='FireFly finds copper-gold system near idle mill')),

    (CAT_ZK, ni('https://www.mining.com/xxix-metal-launches-largest-drilling-campaign-in-its-history',
                'MINING.COM', '10-29',
                'XXIX Metal 启动 65,000 米钻探，覆盖魁北克与安大略三个铜项目',
                'XXIX Metal 启动公司史上最大钻探计划，总进尺 65,000 米，在魁北克 Opemiska、Cooke 与安大略 Thierry 三个铜项目同步推进：Opemiska 约 20,000 米用于资源升级以支撑预可行性研究，Cooke 目标建立首个资源量，Thierry 已施工逾 6,200 米、9 个孔并计划延续至 2027 年 3 月。公司 2025 年 6 月资源量为 1.412 亿吨，含铜 15 亿磅、金 105 万盎司。',
                orig_title='XXIX Metal launches largest drilling campaign in its history')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202610/t20261028_10347764.htm',
                '全球矿产资源信息系统', '10-28',
                '澳大利亚调整关键矿产战略，重心转向冶炼与加工',
                '澳大利亚资源部长玛德琳·金表示，鉴于投资竞争加剧、供应链担忧未解，该国将调整关键矿产战略，把更多重心放在冶炼和加工，特别是澳方拥有或可建立比较优势的领域，并扩大对欧洲出口。澳方今年 1 月已设立 12 亿澳元（8.42 亿美元）战略储备，优先考虑锑、镓和稀土；欧盟将钨、稀土和镓列为首批储备矿种。')),

    (CAT_ZC, ni('https://news.metal.com/newscontent/104184134-shanghai-futures-exchange-approves-cmst-for-group-delivery-business-adjusts-storage-locations',
                'SMM 国际站', '10-28',
                '上期所批准中储发展为集团交割中心，并调整部分存放地点',
                '上期所依据交割仓库管理办法审核后作出决定，批准中储发展股份有限公司作为铜、铝、铅、氧化铝、螺纹钢、线材等品种的集团交割中心，同时对相关交割库存放地点作出调整。具体库容、升贴水与生效时间以交易所公告为准。',
                orig_title='SHFE approves CMST for group delivery business, adjusts storage locations')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202610/t20261028_10347763.htm',
                '全球矿产资源信息系统', '10-28',
                '伍德麦肯兹：战略金属仍供不应求，铜未来十年每年需新增 85 万吨矿产供应',
                '伍德麦肯兹警告，许可迟缓、地缘政治不确定与项目复杂度上升使矿山项目落地低于预期，铜、铝、镍、锂新建矿山尤为突出。该机构估计未来 10 年铜矿需每年新增约 85 万吨供应；铜价近期创 15,000 美元/吨历史新高，美国囤积超 170 天需求的铜库存，其他国家短缺 46 万吨。AI 数据中心用电约 250 吉瓦，输电、变电站等配套金属需求可达其所支撑设施的 3 至 4 倍。')),

    (CAT_SC, ni('https://www.mining.com/world-bank-lifts-copper-price-outlook-by-18',
                'MINING.COM', '10-29',
                '世界银行上调 2027 年铜价预测 18% 至 13,000 美元/吨',
                '世界银行 10 月展望将 2027 年铜价预测较 4 月上调 18% 至 13,000 美元/吨（约 5.90 美元/磅），仅比今年均价 13,200 美元低 1.5%；锡价预测上调 22% 至 45,000 美元/吨，锌上调 13% 至 3,100 美元/吨。该行金属与矿产价格指数今年预计涨 25%、2027 年回落 3.3%，仍较 2021 年峰值高 16%。',
                orig_title='World Bank lifts copper price outlook by 18%')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX018/202610/43f23fee61dc47eeaa8671ce65155f9a.html',
                '长江有色网', '10-28',
                '芝商所计划 2027 年一季度推出全球首只钨 APT 期货，采用现金结算',
                '芝商所公布计划，将于 2027 年一季度在 COMEX 挂牌全球首只钨 APT（仲钨酸铵）期货，采用纯现金结算，锚定 Fastmarkets 发布的鹿特丹、巴尔的摩 CIF 到岸价，不设实物交割通道、不生成仓单，也不涉及钨品仓储与实物流转。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474928',
                '中国有色金属报', '10-26',
                '基本面支撑沪铝探底回升，但中期上行空间仍受限',
                '沪铝主力合约探底回升：国内电解铝社会库存降至 56.6 万吨、上期所库存 23.69 万吨，均回到近 5 年同期水平；现货升水由节前 20 至 40 元/吨扩大至 295 元/吨（截至 10 月 20 日）。但 9 月国内电解铝产量 391 万吨、同比增 3.1%，1 至 9 月累计 3,503 万吨、同比增 3.8%，叠加海外供应恢复与新增产能释放，铝价中期反弹高度受限。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/0e72af9322ac4b1d8f1f9cd950da1cc3.html',
                '长江有色网', '10-28',
                '碳酸锂期货冲高回落大跌 4.64%，旺季证伪与供给预期双重定价',
                '碳酸锂期货反弹遇阻，主力合约冲高后回落、单日大跌 4.64%，市场在旺季需求证伪与远期供给释放预期之间重新定价，现货价格重心同步下移，下游以刚需采购为主。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474976',
                '中国有色金属报', '10-27',
                '洛阳钼业前三季度净利 240.2 亿元同比增 68.21%，单季产铜 20.87 万吨',
                '洛阳钼业前三季度营业收入 2,072.9 亿元、同比增 42.48%，归母净利润 240.2 亿元、同比增 68.21%；第三季度单季营收 719.71 亿元创历史新高，产铜 20.87 万吨、连续两个季度站稳 20 万吨。前三季度累计产铜 59.67 万吨、同比增 9.81%，产金 16.09 万盎司，钼钨板块营收首次突破 100 亿元。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474914',
                '中国有色金属报', '10-26',
                '中金岭南广西矿业前三季度产量、营收、利润同比齐增，盘龙铅锌扩产推进',
                '广西中金岭南矿业 1 至 9 月产量、营收、利润均同比增长，完成前三季度生产任务；盘龙铅锌矿 6,000 吨/天采选扩产改造取得阶段性进展，地面至 -270 米大斜井贯通、西回风井进入试运行，新选矿厂浮选车间完成第 3 次负荷带水试车，破碎与磨浮系统先后带料运转。')),

    (CAT_HY, ni('https://news.smm.cn/news/104181902',
                '上海有色网', '10-28',
                '宁德时代预计全固态电池 2027 年有望实现小批量生产',
                '10 月 28 日锂电快讯显示，宁德时代预计全固态电池 2027 年有望实现小批量生产，固态电池产业化节奏成为锂电材料需求的重要变量。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/glencore-cngr-back-380m-brazil-nickel-mine-with-40m',
                'MINING.COM', '10-29',
                '嘉能可与中伟各出资 2,000 万美元，支持 Centaurus 巴西 Jaguar 镍矿',
                '嘉能可与中伟（CNGR）向 Centaurus Metals 合计投资 4,000 万美元，并分别签署五年期协议、每年各采购至少 2 万吨镍精矿，覆盖巴西 3.8 亿美元 Jaguar 项目投产前五年的全部镍精矿产量，合同金属价值按当前价格约 9 亿美元。投资分两期支付，首期各 1,250 万美元，第二期各 750 万美元以股东批准与最终投资决定为条件。',
                orig_title='Glencore, CNGR back $380M Brazil nickel mine with $40M')),

    (CAT_MA, ni('https://news.metal.com/newscontent/104184234-australia-conditionally-approves-us414m-loan-for-global-advanced-metals-tantalum-production',
                'SMM 国际站', '10-28',
                '澳大利亚有条件批准向 Global Advanced Metals 提供贷款，支持钽生产',
                '澳大利亚政府有条件批准向 Global Advanced Metals 提供贷款，用于支持其钽生产项目、扩大关键矿产供应，贷款金额与附加条件以澳方公告为准。',
                orig_title='Australia conditionally approves US$41.4m loan for Global Advanced Metals tantalum production')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://news.metal.com/newscontent/104184136-antamina-copper-mine-halts-operations-after-worker-fatality-launches-investigation',
                'SMM 国际站', '10-28',
                '秘鲁安塔米纳铜矿因工人死亡事故暂停运营并启动调查',
                '由嘉能可与必和必拓控股的秘鲁安塔米纳铜矿（Antamina）表示，安卡什大区 Yanacancha 矿区一名工人死亡，公司已实施预防性安全停产并启动调查，复产时间待定。',
                orig_title='Antamina copper mine halts operations after worker fatality, launches investigation')),

    (CAT_GJ, ni('https://www.mining.com/nova-minerals-gets-final-approvals-for-alaska-antimony-project',
                'MINING.COM', '10-28',
                'Nova Minerals 获阿拉斯加最终许可，推进美国本土锑供应链',
                'Nova Minerals 获阿拉斯加自然资源部对 Estelle 项目 Styx 与 Stibium 矿段运营方案及复垦方案的最终批准，三个月内取得全部许可，可开展一期建设。一期由美国国防部 4,340 万美元资金支持，用于军用级三硫化锑产能；公司在 Port MacKenzie 的锑精炼厂用地许可覆盖 42.81 英亩。',
                orig_title='Nova Minerals gets final approvals for Alaska antimony project')),

    (CAT_GJ, ni('https://www.mining.com/labour-shortage-hurts-west-lake-gold-output',
                'MINING.COM', '10-28',
                '劳动力短缺拖累 West Red Lake 旗下 Madsen 金矿，年产指引下调约四分之一',
                'West Red Lake Gold Mines 将 Madsen 金矿今年产量指引由 3.5 万至 4.5 万盎司下调至 2.7 万至 3.2 万盎司，主因劳动力短缺与老采区残留矿柱回采难度加大。三季度产量环比降 8.4% 至 7,859 盎司，公司股价当日跌 12%。',
                orig_title='Labour shortage hurts West Lake Gold output')),
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
    ('冬瓜山', CAT_ZK),
    ('阿斐马', CAT_ZK),
    ('FireFly', CAT_ZK),
    ('XXIX', CAT_ZK),
    ('澳大利亚调整关键矿产', CAT_ZC),
    ('中储发展', CAT_ZC),
    ('伍德麦肯兹', CAT_SC),
    ('世界银行', CAT_SC),
    ('钨 APT', CAT_SC),
    ('沪铝', CAT_SC),
    ('碳酸锂', CAT_SC),
    ('洛阳钼业', CAT_HY),
    ('中金岭南', CAT_HY),
    ('宁德时代', CAT_HY),
    ('Jaguar', CAT_MA),
    ('Global Advanced', CAT_MA),
    ('安塔米纳', CAT_GJ),
    ('Nova Minerals', CAT_GJ),
    ('West Red Lake', CAT_GJ),
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
