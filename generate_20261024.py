# -*- coding: utf-8 -*-
"""
生成 2026-10-24 矿业资讯速览 index.html（周六）
- 10-23 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-25）回补历史条目
- 换入 10-24 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-23 收盘 + LME 10-23 收盘（10-24 周六休市），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，本批新增 5 宗，不进主页列表
  （由 tmp/add_rights_1024.py 注入月库））
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

REPORT = '2026-10-24'
GRAB = '2026-10-24'
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
                         r'\g<1>2026年10月24日 星期六', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202610/t20261023_10343558.htm',
                '全球矿产资源信息系统', '10-23',
                '澳大利亚吉尔摩铜金矿新孔 321 至 750 米见明显矿化',
                '林克公司公布澳大利亚吉尔摩（Gilmore）铜金项目吉景邦南靶区钻孔结果，自 321 米至终孔 750.3 米矿化「非常明显」，岩心样品将在未来 6 至 8 周内化验。该孔为计划 4 个孔之一、孔间距 200 至 300 米、最大孔深 1000 米。吉尔摩项目合计矿石资源量 5.16 亿吨，含金约 370 万盎司、铜 120 万吨；吉景邦与达姆两矿床资源量 1.2 亿吨，铜 20 万吨、金 170 万盎司。')),

    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/ddyw/202610/t20261023_870838.html',
                '中国地质调查局', '10-23',
                '中国地质调查局在河北平泉举办二维地震勘探野外实训',
                '10 月 13 日至 17 日，中国地质调查局在河北平泉举办二维地震勘探野外实训，目标是强化地质调查技术业务综合管理、提升局属单位地震勘探自主实施能力。实训面向野外采集与资料处理环节，属新一轮找矿突破战略行动中物探能力建设的组成部分。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104169018',
                '上海有色网', '10-23',
                '加纳拟 2030 年起禁止未加工矿产出口',
                '加纳总统马哈马 10 月 19 日在阿克拉矿业会议上表示，计划到 2030 年禁止未加工矿产出口，铝土矿、锰、铁、锂等须支持国内加工与工业发展。加纳是非洲最大黄金生产国，同时为全球第三大锰出口国、约占全球开采供应量 10%，并拥有可观铝土矿储量。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104171690',
                '上海有色网', '10-23',
                '美国金库计划拟向关键矿产制造商提供最高 10 亿美元贷款',
                '美国政府支持的金库计划（Project Vault）准备向寻求关键矿产的美国制造商发放最高 10 亿美元贷款，负责实施的 VaultCo 正与 70 多家供应链企业洽谈，首批涉及 10 余家原始设备制造商。该计划今年 2 月启动，获美国进出口银行 100 亿美元贷款及近 20 亿美元私人投资；嘉能可与摩科瑞各出资 5 亿美元，摩科瑞已从刚果（金）发运 1.2 万吨铜。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104172701',
                '上海有色网', '10-23',
                '巴西对原产于中国和印度的石墨电极作出反倾销初裁',
                '巴西发展、工业、贸易和服务部外贸秘书处 10 月 15 日发布第 98 号通告，对原产于中国和印度的石墨电极作出反倾销初裁。该调查系应巴西企业 Graftech 于 2025 年 7 月 31 日提交的申请，于 2026 年 3 月 12 日以第 18 号公告立案启动，涉华石墨电极出口再添贸易壁垒。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104174127',
                '上海有色网', '10-23',
                '宜春枧下窝锂矿采矿项目环评拟批准公示',
                '宜春市生态环境局就枧下窝锂矿采矿项目生态环境影响报告书发布拟批准公示，项目环评进入拟批准阶段。枧下窝为江西宜春地区重要锂云母矿山，环评推进意味着采矿工程审批向前一步，后续仍需关注正式批复与建设投产节奏。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104174081',
                '上海有色网', '10-23',
                'LME 美国仓库铜库存 16.95 万吨，创 12 年半新高',
                '10 月 22 日，LME 美国仓库铜库存升至 169,475 吨，为 2014 年 4 月以来最高，约占交易所全部铜库存的 62%（2019 年 3 月以来最高占比），主要位于新奥尔良与巴尔的摩。当日新奥尔良入库 24,225 吨、巴尔的摩入库 2,450 吨；COMEX 铜库存连续 23 天攀升至 794,450 短吨（720,712 吨）。美国商务部提议 2027 年起对精炼铜进口加征 15% 关税、2028 年升至 30%，尚未宣布是否实施。')),

    (CAT_SC, ni('https://news.smm.cn/news/104174148',
                '上海有色网', '10-23',
                '白银跌至三个月低位，高盛称投机资金正在撤离',
                '周四现货白银一度大跌 5%，跌至三个月低位；现货黄金一度下破 4,050 美元/盎司，为 8 月 4 日以来首次。美国 9 月 CPI 同比上涨 3.7%，美元走强压制贵金属。高盛测算，截至 10 月 13 日当周管理基金净卖出白银约 5.65 亿美元，此前三周累计约 22 亿美元，净多头降至约 17 亿美元、为两年跟踪区间低位。')),

    (CAT_SC, ni('https://news.smm.cn/news/104173679',
                '上海有色网', '10-23',
                '镁锭价格触及年内低点 15,100 元/吨，半年多跌近 14%',
                '镁锭 9990（府谷、神木）10 月 21 日下探至 15,100 元/吨的年内低点，较 4 月 8 日高点 17,500 元/吨明显回落，较 2025 年 12 月 31 日的 15,750 元/吨下跌 4.13%，半年多累计跌幅近 14%。价格逼近 15,000 元/吨关口后行业整体贴近成本线、部分企业亏损，冶炼厂惜售挺价，10 月 22 日出现低位反弹。')),

    (CAT_SC, ni('https://news.smm.cn/news/104168895',
                '上海有色网', '10-23',
                '9 月废铜进口 23.66 万吨，同比增 28.55%',
                '海关总署数据显示，2026 年 9 月中国废铜进口量 236,614.89 吨，环比上升 33.37%、同比上升 28.55%。其中自泰国进口 42,311.18 吨，环比增 40.50%、同比增 40.46%；自日本进口 27,445.10 吨，环比增 1.13%、同比降 18.05%。同期废铜出口量 112 吨。废铜进口放量对冶炼原料形成一定补充。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474858',
                '中国有色金属报', '10-24',
                '高盛上调 2026 年底铜价预测至 14,700 美元/吨',
                '高盛 10 月 19 日上调铜价预测，将 2026 年底目标由 13,735 美元/吨调高至 14,700 美元/吨，2027 年均价预测由 13,800 美元/吨上调至 15,400 美元/吨，理由是矿产供应低于预期且美国以外将出现供应缺口。该行预计 2026 年美国以外铜缺口约 95 万吨、2027 年 22 万吨，均高于此前预期的 64 万吨和 17 万吨；2026 年美国铜库存增幅预期由 90 万吨升至约 100 万吨，并建议做多 2027 年 12 月交割的 LME 铜合约。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/104176811',
                '上海有色网', '10-24',
                '紫金矿业前三季净利 575.26 亿元，同比增 51.93%',
                '紫金矿业三季报显示，前三季度归母净利润 575.26 亿元、同比增 51.93%，扣非净利润 558.42 亿元、同比增 63.63%，营业收入 2,834.53 亿元、同比增 11.51%。第三季度归母净利润 183.56 亿元、同比增 25.97%。前三季度矿山产金 70.13 吨、矿产铜 81.57 万吨、当量碳酸锂 7.9 万吨；公司已于 10 月 22 日完成对赤峰黄金控制权收购。')),

    (CAT_HY, ni('https://www.ccmn.cn/news/ZX018/202610/1d71bb0820bb4f18a31219a785c2aed9.html',
                '长江有色网', '10-23',
                '海德鲁三季度核心利润低于预期，下调资本支出',
                '海德鲁（Norsk Hydro）三季度调整后 EBITDA 同比增长 51.6% 至 90.9 亿挪威克朗（约 9.743 亿美元），低于分析师平均预期的 95.3 亿挪威克朗。公司同时下调资本支出，并预判四季度铝业务盈利走弱，成本压力与铝价震荡是主要压制因素。')),

    (CAT_HY, ni('https://www.ccmn.cn/news/ZX018/202610/5e9d301b7095401cbe8d35c8c59f10d4.html',
                '长江有色网', '10-23',
                '海亮股份 6.75 万吨高端铜箔项目进入主体施工',
                '海亮股份 AI 算力及先进电池技术用铜箔生产线项目落地绍兴诸暨市，目前已进入厂房主体施工阶段，规划产能 6.75 万吨，计划 2030 年全部投产。项目面向高端电子与电池铜箔需求，投产后将扩大公司在高附加值铜箔领域的份额。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474852',
                '中国有色金属报', '10-24',
                '中铝铝箔浩鑫厂连续两月铝箔产量破 1000 吨',
                '中铝铝箔浩鑫厂下半年以来连续两个月铝箔产量突破 1000 吨，电池箔产量实现历史性突破。该厂重塑轧机分工、按成品率倒排产能，技术团队用 13 天完成工艺调试并攻克两合金电池箔试产难题，粗轧合格率提升 70% 以上。')),

    (CAT_HY, ni('https://news.smm.cn/news/104170941',
                '上海有色网', '10-23',
                '宁德时代回应股价大跌：2027 年行业需求依旧可期待',
                '宁德时代 10 月 21 日就股价大跌回应称，行业需求没有那么悲观，产能利用率仍将处于较高水平，2027 年行业需求依旧可以期待。公司前三季度营收 4,421.37 亿元、同比增 56.19%，归母净利润 645.30 亿元、同比增 31.60%；但第三季度单季净利同比仅增 14.54%，经营性现金流同比下降 23.60%，公司称为主动调整供应商付款所致。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.smm.cn/news/104174211',
                '上海有色网', '10-23',
                '力拓投 19 亿美元开发昆士兰 Kangwinan 铝土矿',
                '力拓 10 月 23 日宣布投资 19 亿美元开发澳大利亚昆士兰州 Kangwinan 铝土矿项目，用于接替本十年内到期的 Andoom 矿，并为 Weipa 业务新增 2000 万吨铝土矿年产能。项目首批产出目标定于 2029 年、2032 年满产，Weipa 年产能将由目前约 3800 万吨提升至约 4400 万吨，同时抵消 2029 年关闭北领地 Gove 铝土矿的产量缺口。')),

    (CAT_MA, ni('https://news.smm.cn/news/104171230',
                '上海有色网', '10-23',
                '中色股份子公司签哈萨克斯坦 30 万吨/年铜冶炼厂准备启动协议',
                '中色股份公告，控股子公司中色哈萨克斯坦与哈萨克斯坦矿业冶炼公司签署《哈萨克斯坦 30 万吨/年铜冶炼厂项目准备工作启动协议》。双方此前于 2024 年 6 月 3 日签署项目总协议，本次协议仅覆盖施工合同签订前的准备工作，公司同时提示履约与不可抗力风险。')),

    (CAT_MA, ni('https://www.mining.com/boroo-signs-100m-deal-for-yukon-eagle-gold-mine',
                'MINING.COM', '10-23',
                'Boroo 以最高 1.4 亿加元收购加拿大 Eagle 金矿',
                '新加坡私营企业 Boroo 达成协议收购 Victoria Gold，交易对价最高 1.4 亿加元（约 1 亿美元）：交割时先付 4,000 万加元，另 1 亿加元按许可与商业投产里程碑支付。标的 Eagle 金矿位于育空地区白马市以北约 375 公里，2024 年 6 月堆浸场坍塌致约 180 万吨物料外泄后停产。Boroo 计划 2027 至 2029 年投入约 8 亿加元用于修复、水处理与分阶段复产，对加投入承诺超 15 亿加元，交割目标为 12 月 31 日。',
                orig_title='Boroo signs $100M deal for Yukon Eagle gold mine')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://news.smm.cn/news/104171905',
                '上海有色网', '10-23',
                '林甸资源坎甘昆德稀土矿 12 月产出首批精矿',
                '林甸资源（Lindian Resources）按计划推进 12 月产出首批独居石精矿，目前矿石储备已由 9 月的 2.4 万吨增至 14.9 万吨，并力争 11 月第一周实现场地通电。坎甘昆德设计年产 TREO 品位 55% 的稀土精矿 1.53 万吨，分阶段扩产至年产 12 万吨，第一阶段矿山服务年限预计 45 年。')),

    (CAT_GJ, ni('https://news.smm.cn/news/104171846',
                '上海有色网', '10-23',
                '阿克拉拉彭科稀土项目税后净现值 3.44 亿加元',
                '阿克拉拉资源（Aclara Resources）智利彭科稀土项目最新初步经济评价显示，税后净现值 3.44 亿加元（约 2.43 亿美元），产前投资 2.44 亿加元（约 1.78 亿美元）。评价采用 8% 折现率（2021 年为 5%），露天采坑可采年限延长 3 年至 17 年，内部收益率升至 26.1%；净现值上升主要因矿石量增 55% 至 3,080 万吨。探明加推定资源量 3,580 万吨、TREO 品位 0.2095%、稀土氧化物量 75,025 吨、增 19%。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202610/t20261023_10343556.htm',
                '全球矿产资源信息系统', '10-23',
                '乌干达 8 月出口额增 36%，黄金出口 8.89 亿美元',
                '乌干达财政部报告显示，8 月商品出口额由上年同期的 11 亿美元增至 15 亿美元，同比增长 36%，金和其他商品出口增长是主要推力。当月贵金属出口额达 8.89 亿美元、同比增长 68.9%，乌干达已逐步成为地区黄金加工与贸易中心。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202610/t20261023_10343559.htm',
                '全球矿产资源信息系统', '10-23',
                '萨里托甘石墨项目可研：年产 5 万吨，税前净现值 1.32 亿美元',
                '萨里托甘石墨公司（Sarytogan Graphite）公布哈萨克斯坦萨里托甘石墨项目可研结果，项目具备年产 5 万吨石墨精矿潜力：2 万吨三种规格（最大粒径 15 微米）精矿、1 万吨未分级精矿、2 万吨超纯细粉及球形纯化石墨。仅计上游产品，按均价 805 美元/吨测算税前净现值 1.32 亿美元（1.89 亿澳元）、内部收益率 19.8%、总资本支出 8,050 万美元。')),

    (CAT_GJ, ni('https://www.mining.com/halo-minerals-clears-key-hurdle-at-chile-copper-project',
                'MINING.COM', '10-24',
                'Halo 获智利 Playa Verde 尾矿铜项目关键许可',
                'Halo Minerals（AIM: HALO）取得智利 Playa Verde 铜金尾矿项目关键采矿许可，其子公司 Minera Playa Verde 可自 Chañaral 海滩（含城区段）疏浚含矿物料，智利住建部未提出异议。项目设计年处理约 500 万吨物料、年产可付铜 8,600 吨（阴极铜与精矿），预计年现金流约 5,000 万美元；公司尚未作出最终投资决定。',
                orig_title='Halo Minerals clears key hurdle at Chile copper project')),

    # ── 🌐 国际矿业动态（08:20 并集补稿：云端独有，本机 05:30 漏抓） ──
    (CAT_GJ, ni('https://www.mining.com/bannerman-pulls-trigger-on-353m-uranium-mine',
                'MINING.COM', '10-24',
                'Bannerman 批准纳米比亚 Etango 铀矿建设，融资 3.53 亿美元',
                'Bannerman Resources 批准纳米比亚 Etango 铀矿项目建设，建设资金已落实且不含项目债务，首产目标定为 2028 年。Etango 为露天铀矿项目，建设获批标志着项目进入实质性开发阶段。',
                orig_title='Bannerman pulls trigger on $353M uranium mine')),

    (CAT_GJ, ni('https://www.mining.com/moon-river-lifts-davidson-value-to-879m-tungsten-output-jumps',
                'MINING.COM', '10-24',
                'Moon River 将 Davidson 钨矿估值提至 8.79 亿美元，钨产量跃升',
                'Moon River 更新加拿大不列颠哥伦比亚省 Davidson 钨矿项目经济评估，项目估值升至 8.79 亿美元、钨产量显著提升；但项目仍处初步评估阶段，尚未形成矿产储量。',
                orig_title='Moon River lifts Davidson value to $879M, tungsten output jumps')),
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
