# -*- coding: utf-8 -*-
"""
生成 2026-11-03 矿业资讯速览 index.html（周二）
- 11-02 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-05）回补历史条目
- 换入 11-03 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 11-02 收盘 + LME 11-02 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目：11-03 增补 1 宗转让公示（江西奉新坪头岭钽铌矿），由 news-data.js 直出 #rightsCards，不进主列表
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

REPORT = '2026-11-03'
GRAB = '2026-11-03'
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
                         r'\g<1>2026年11月03日 星期二', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202611/t20261102_10351660.htm',
                '全球矿产资源信息系统', '11-02',
                '廿九金属启动 6.5 万米钻探，奥佩米斯卡铜矿拟升级资源量',
                '据 Mining.com 报道，廿九金属公司启动 6.5 万米钻探计划，覆盖魁北克奥佩米斯卡铜矿三个并行项目及安大略蒂埃里项目；7 月以来两台钻机已在蒂埃里施工，12 月至次年 1 月初将在奥佩米斯卡和库克再增 4 台钻机。奥佩米斯卡计划钻探约 2 万米，以升级 2025 年 6 月资源量（矿石量 1.412 亿吨、铜 15 亿磅、金 105 万盎司），为预可行性研究扩大基础。')),

    (CAT_ZK, ni('https://news.metal.com/newscontent/104200189-amaroq-unveils-string-of-pearls-strategy-for-greenland-zinc-lead-silver-project-reports-high-grade-samples',
                'SMM 国际站', '11-02',
                'Amaroq 公布格陵兰「珍珠链」策略，见高品位锌铅银样品',
                'Amaroq 于 11 月 2 日公布格陵兰西部 Maarmorilik 地区「珍珠链」开发策略，该区含曾开采的 Black Angel 锌铅银矿；10 月已向格陵兰政府提交项目环评与社会影响评价工作大纲。新取样中 Garde 见 3.1 米厚 17.49% 锌、8.08% 铅、36 克/吨银，Wedge 见 4.1 米厚 10.05% 锌，岩屑样最高锌品位 62.2%。',
                orig_title="Amaroq Unveils 'String of Pearls' Strategy for Greenland Zinc-Lead-Silver Project, Reports High-Grade Samples")),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104200238',
                '上海有色网', '11-02',
                '上期所同意中远海运物流取消天津锌期货交割库存放点',
                '11 月 2 日上期所公告，同意中远海运物流有限公司取消位于天津市滨海高新区的锌期货存放点，核定库容锌 2 万吨；自公告之日起该存放点不再开展锌期货交割业务，交易所要求各有关单位确保交割业务正常有序进行。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104184280',
                '上海有色网', '10-29',
                '联合国启动关键矿产支持机制，六国首批入选',
                '2026 年 9 月联合国在纽约气候峰会上宣布启动关键能源转型矿产国家支持机制，印度尼西亚、赞比亚、几内亚、津巴布韦、马达加斯加和尼日利亚六国为首批支持对象。该机制不提供直接贷款，而以政策设计、法律框架、环境与社会标准建设为抓手，推动六国从原矿出口转向本地加工与制造。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475110',
                '中国有色金属报', '11-02',
                '铜冠铜箔前三季度扣非净利增 582%，高端铜箔订单骤增',
                '铜冠铜箔三季报显示，前三季度营业收入 65.33 亿元、同比增 37.99%，归母净利润 3.39 亿元、同比增 439.75%，扣非净利润 3.28 亿元、同比增 582.38%；第三季度营收、归母净利、扣非净利环比分别增 15.27%、13.95%、14.25%。公司将有限产能优先配置到 HVLP 铜箔表面处理等关键工序。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475106',
                '中国有色金属报', '11-02',
                '中铝郑州研究院铝灰渣全量化利用技术获日内瓦发明展金奖',
                '中铝郑州研究院「铝灰渣多场景全量化循环利用关键技术开发及应用」在第 51 届日内瓦国际发明展上从全球 40 个国家和地区、千余项成果中获金奖；该技术实现铝灰渣全量化无害处置与资源化利用，消除危废倾倒填埋带来的土壤与水体污染风险，已落地工业产线。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.mining.com/citi-slashes-lithium-price-forecast-by-40-on-lower-demand',
                'MINING.COM', '11-03',
                '花旗下调锂价预测 40%，碳酸锂目标价降至 1.2 万美元/吨',
                '花旗将未来两年锂价预测最多下调 40%，碳酸锂与氢氧化锂目标价分别由 2 万美元/吨、1.7 万美元/吨降至 1.2 万美元/吨，锂辉石由 2,000 美元降至 1,200 美元；理由为电池需求增速放缓、贸易不确定性上升，并预计 2027 年供应改善。',
                orig_title='Citi slashes lithium price forecast by 40% on lower demand')),

    (CAT_SC, ni('https://news.smm.cn/news/104189748',
                '上海有色网', '10-31',
                '现货黄金跌破 3,900 美元创一年新低，白银失守 50 美元',
                '上周五现货黄金跌破 3,900 美元/盎司、日内跌超 3%，创一年新低；现货白银跌破 50 美元/盎司、日内跌超 5%，为 2025 年 11 月以来首次；铂金跌 4%、钯金跌 3.1%，均创阶段新低。当月金价累计跌幅近 6%，白银月内跌幅超 17%，均为连续第二个月下跌。')),

    (CAT_SC, ni('https://news.smm.cn/news/104189473',
                '上海有色网', '10-30',
                '菲律宾 9 月出口镍矿 893.48 万吨，对中国出口 638.37 万吨',
                '菲律宾统计局数据显示，2026 年 9 月菲律宾出口镍矿 893.4782 万吨，其中对中国出口 638.3652 万吨、对印尼出口 255.1130 万吨；中国仍是其镍矿最大流向地，占比逾七成。')),

    (CAT_SC, ni('https://news.smm.cn/news/104189535',
                '上海有色网', '10-30',
                '印尼 9 月精炼锡出口 3,970.25 吨，同比减 18.04%',
                '印尼贸易部 10 月 30 日公布，9 月精炼锡出口量 3,970.25 吨，较上年同期的 4,844.21 吨减少 18.04%，较 8 月的 4,804.30 吨下降 17.36%，出口延续同比、环比双降。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_GJ, ni('https://news.metal.com/newscontent/104200185-fire-erupts-at-korea-zincs-onsan-smelter-no-casualties-reported-amid-investigation',
                'SMM 国际站', '11-02',
                '韩国锌业温山冶炼厂 2 号厂火灾，无人员伤亡',
                '据外媒报道，11 月 2 日上午韩国锌业温山冶炼厂 2 号厂发生火灾，厂区附近浓烟升起；蔚山消防部门出动约 30 辆消防车、70 名人员，下午 1 时 55 分解除一级应急响应，无人员伤亡报告。该厂此前已处于停产状态，事故原因仍在调查。',
                orig_title="Fire Erupts at Korea Zinc's Onsan Smelter, No Casualties Reported Amid Investigation")),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/712-billion-wiped-off-worlds-biggest-mining-companies-since-the-start-of-the-iran-war',
                'MINING.COM', '11-03',
                '全球最大矿企市值自伊朗战争以来蒸发 7,120 亿美元',
                'MINING.COM TOP 50 显示，全球市值前 50 矿企自 2 月高点已下跌 26%，市值蒸发 7,120 亿美元；10 月单月缩水 2,260 亿美元、跌幅 10%，9 月缩水 2,640 亿美元，两个月蒸发近 5,000 亿美元，为今年首次低于 2025 年末水平。',
                orig_title='$712 billion wiped off world’s biggest mining companies since start of Iran war')),

    (CAT_GJ, ni('https://news.smm.cn/news/104186830',
                '上海有色网', '10-30',
                '力拓蒙古奥尤陶勒盖铜矿岩崩，地下运营暂停',
                '10 月 29 日 18 时左右，力拓旗下蒙古国南部奥尤陶勒盖铜矿发生岩崩，造成 15 名工人受伤、暂无死亡报告；运营方称井下岩石破碎带突发震动性地质事件引发局部岩崩，已暂停地下运营，停产时长及产量影响尚不明确。力拓 ADR 一度跌超 4%。')),

    (CAT_GJ, ni('https://www.mining.com/gold-fields-clears-major-hurdle-for-quebecs-windfall-gold-mine',
                'MINING.COM', '11-02',
                'Gold Fields 魁北克 Windfall 金矿获环评批准',
                'Gold Fields 宣布其魁北克高品位 Windfall 金矿项目获魁北克环境部颁发的环境许可证书，确认项目已按《环境质量法》完成环境与社会影响评价，可在满足监管条件后开工建设，为 2027 年最终投资决策扫清主要监管障碍。',
                orig_title='Gold Fields clears major hurdle for Quebec’s Windfall gold mine')),

    (CAT_GJ, ni('https://www.mining.com/endeavour-halts-burkina-gold-underground-as-ramp-sinks',
                'MINING.COM', '11-02',
                'Endeavour 布基纳法索 Mana 金矿地下开采暂停',
                'Endeavour Mining 称，10 月 28 日通往 Wona 采坑的坡道部分下沉，影响 Dangouna 与 Aviera 两个井下入口，公司已暂停布基纳法索 Mana 金矿地下开采并撤离人员，无人受伤；该矿原本预计无法完成年度产量目标。',
                orig_title='Endeavour halts Burkina gold underground as ramp sinks')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202611/t20261102_10351659.htm',
                '全球矿产资源信息系统', '11-02',
                '力拓评估在阿根廷新建锂厂，需新增约 10 亿美元投资',
                '力拓高管透露，公司正评估在阿根廷建设一座新锂工厂，项目需新增约 10 亿美元投资；计划明年将菲尼克斯二期项目——拟建于卡塔马卡省翁布雷穆埃尔托盐滩——提交阿根廷大型投资激励机制办公室审批，同时考虑推进本国铜矿项目。')),

    (CAT_MA, ni('https://www.mining.com/hudbay-leads-49-8m-investment-in-pecoy-copper',
                'MINING.COM', '11-02',
                'Hudbay 领投 Pecoy Copper 4,980 万加元融资',
                '加拿大勘探公司 Pecoy Copper 与 Hudbay 及另一名投资者达成协议，募资 4,980 万加元（约 3,570 万美元），用于秘鲁南部铜金项目钻探与技术研究；其中 Hudbay 出资 3,010 万加元、另一投资者出资 1,970 万加元，交割后各持股略低于 10%。',
                orig_title='Hudbay leads $49.8M investment in Pecoy Copper')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-03/1225653796.PDF',
                '巨潮资讯网', '11-03',
                '海南矿业发行股份购买资产方案提交上会',
                '海南矿业披露发行股份及支付现金购买资产并募集配套资金暨关联交易报告书上会稿及修订说明，并回复审核问询函与审核中心意见落实函。交易标的、对价与配套募资规模以公告正文披露为准。')),

    (CAT_MA, ni('https://news.smm.cn/news/104200265',
                '上海有色网', '11-02',
                '翔鹭钨业前三季度净利 4.93 亿元，同比增 851.48%',
                '翔鹭钨业三季报显示，前三季度营业收入 38.67 亿元、同比增 139.30%，归母净利润 4.93 亿元、同比增 851.48%，主因钨价上涨带动销售收入增加；11 月 2 日收盘股价涨 1.3%，报 22.54 元/股。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-03/1225653544.PDF',
                '巨潮资讯网', '11-03',
                '盛达资源与富宁方鑫黄金矿业签署框架合作协议',
                '盛达资源公告与富宁县方鑫黄金矿业有限责任公司及相关方签署《框架合作协议》，就黄金矿业领域合作达成初步安排；合作标的、交易结构、对价与实施条件以公告正文披露为准。')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://news.metal.com/newscontent/104200266-five-groups-bid-for-kenyas-mrima-hill-niobium-project',
                'SMM 国际站', '11-02',
                '五家联合体竞标肯尼亚 Mrima Hill 铌稀土项目',
                '肯尼亚矿业部长 Joho 10 月 30 日对路透表示，已有五家联合体提交开发 Mrima Hill 铌稀土矿床的投标，预计两到三周内确定优先竞标人；投标仅体现投资意向，项目授标、融资与新增矿供应仍取决于技术研究、审批与可行价格。',
                orig_title='Five groups bid for Kenya’s Mrima Hill niobium project')),

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
    ('廿九金属', CAT_ZK),
    ('Amaroq', CAT_ZK),
    ('上期所', CAT_ZC),
    ('联合国', CAT_ZC),
    ('花旗', CAT_SC),
    ('现货黄金', CAT_SC),
    ('菲律宾', CAT_SC),
    ('印尼 9 月精炼锡', CAT_SC),
    ('铜冠铜箔', CAT_HY),
    ('中铝郑州研究院', CAT_HY),
    ('韩国锌业', CAT_GJ),
    ('全球最大矿企', CAT_GJ),
    ('奥尤陶勒盖', CAT_GJ),
    ('Gold Fields', CAT_GJ),
    ('Endeavour', CAT_GJ),
    ('力拓评估', CAT_MA),
    ('Hudbay', CAT_MA),
    ('海南矿业', CAT_MA),
    ('翔鹭钨业', CAT_MA),
    ('盛达资源', CAT_MA),
    ('Mrima Hill', CAT_KQ),
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
