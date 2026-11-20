# -*- coding: utf-8 -*-
"""
生成 2026-11-20 矿业资讯速览 index.html（周五）
- 11-19 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-17）回补历史条目
- 换入 11-20 采集的 11-18 至 11-20 条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-19 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；
  电解钴保留上日 SMM 值并标注
- 矿权条目：今日新增公告走 #rightsCards 既有窗口，不进主列表
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

REPORT = '2026-11-20'
GRAB = '2026-11-20'
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
                         r'\g<1>2026年11月20日 星期五', html)
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
    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202611/t20261120_10369937.htm',
                '全球矿产资源信息系统', '11-20',
                '智利铜产量或创 23 年新低，2026 年降至 503.4 万吨',
                '据 Mining.com 报道，普拉斯矿业（Plusmining）预计 2026 年智利铜产量下降 6.6% 至 503.4 万吨、较上年减少 35.4 万吨，为 2003 年以来最低（当年 490.4 万吨），较 2018 年峰值少近 80 万吨。品位下降、运营中断与恶劣天气是主因，8 月产量同比降 12.7% 至 36.6 万吨；2025 年硫酸进口达创纪录的 397 万吨、约占其消费量近一半。机构预计 2027 年回升 25 万吨、2032 年或超 600 万吨，截至 10 月环评受理的矿业项目拟投资超 250 亿美元。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475427',
                '中国有色金属报', '11-19',
                '沪铝月差走扩至 1,200 元/吨以上，Back 结构持续强化',
                '11 月 13 日夜盘 AL2612 与 AL2704 合约价差走扩至 1200 元/吨以上，较 10 月 14 日的极值区域进一步加深。支撑近月的现实是：截至 11 月 13 日 LME 注册仓单仅 19.98 万吨、为有统计以来最低，国内铝锭社会库存自 5 月上旬持续去化；远月则受中东复产（本轮减产峰值 286 万~300 万吨/年，至 11 月上旬仍有约 180 万吨未恢复，阿联酋重启比例 50%）与印尼、越南新产能投放压制，机构预判 2027 年全球铝产量增量约 370 万吨。历史 12 次价差超 500 元/吨的峰值中，7 次在 20 个交易日内收敛至 85 元/吨以下。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX018/202611/61c8259ce32a4f70a6ebea23b7b51410.html',
                '长江有色网', '11-20',
                '套利窗口打开，美国精炼铜开始发运中国',
                '物流公司近几日收到大量贸易商询盘，计划将精炼铜由美国运往中国，目前已完成多批船货订舱，部分铜由 CMA CGM Cassiopeia 轮承运、本周自洛杉矶港起航。这一变化标志着持续两年的铜货流向（中国→美国）迎来反转，此前美铜因关税预期升水吸引大量铜流入。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475404',
                '中国有色金属报', '11-18',
                '上期所将再生铅纳入铅期货交割，替代品贴水 150 元/吨',
                '上期所今年 3 月修订铅期货合约及业务细则，正式将再生铅纳入交割体系：PB2702 合约交割完成后，铅含量符合 99.990%、99.986% 两个牌号的再生铅锭可注册标准仓单，PB2703 成为首个参与交割的合约，替代交割品贴水 150 元/吨。"十四五"期间我国再生铜、铝、铅、锌累计产量 8987 万吨、较"十三五"增 30%，其中再生铅 1435 万吨、增 34%；当前再生铅约占国内铅产能的 50%。')),

    (CAT_ZC, ni('https://www.ccmn.cn/news/ZX006/202611/30884d471ab944f8845090fee86de508.html',
                '长江有色网', '11-20',
                '津巴布韦改按等效硫酸锂价值计征锂精矿出口税',
                '津巴布韦财政部长 Mthuli Ncube 公布锂资源出口税收新政：锂精矿出口税的计税基数不再采用精矿自身售价，改按其所可产出的硫酸锂价值核算。基准品位 6% 的锂精矿统一按 5 吨精矿折算 1 吨硫酸锂的比例计税，税额基于折算后硫酸锂的公平市场总价值计算；硫酸锂本身出口免税。')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://news.smm.cn/news/T6NZTR5BIIAN6NMAKYJMJOUT4M7JIDLBW7NFFGA',
                '上海有色网', '11-18',
                '天齐锂业措拉锂矿储量核实通过评审备案，新增探明资源量',
                '天齐锂业控股子公司盛合锂业收到四川省矿产资源储量评审中心评审意见书，《四川省雅江县措拉矿区锂矿资源储量核实报告》通过评审备案。截至 2025 年 12 月 31 日，措拉锂辉石矿资源量矿石量 2508.7 万吨、含 Li2O 308189 吨、平均品位 1.23%；储量矿石量 1351.9 万吨、含 Li2O 175292 吨、平均品位 1.30%；另伴生铌钽矿石量 1919.9 万吨。公司称本次探矿增储有利于延长矿山服务年限。')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/xfx/202611/t20261119_10368616.htm',
                '全球矿产资源信息系统', '11-19',
                '巴西佩莱南稀土项目钻探见富矿，最高 TREO 品位 16.6%',
                '巴西稀土公司（BRE）佩莱南项目钻探见 TREO 品位 13.2% 的矿体，其中 4 米厚段 TREO 品位 16.6%；另见 14.3 米、TREO 品位 11.2%，TREO 加权品位 5%。公司认为这条沿走向长至少 2.5 公里的矿带为高品位带，南北两侧及东侧均圈定新靶区；镨钕氧化物最高品位 2.55%、镝氧化物 0.12%，钪在地表见矿化、品位 0.0383%。项目勘探目标为接近或超过阿尔托山规模（浅部独居石砂矿推测资源量 2520 万吨、TREO 品位 1%）。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.ccmn.cn/news/ZX018/202611/9c77acd2c67c48bba62c373bf38e287f.html',
                '长江有色网', '11-20',
                '天齐锂业重庆铜梁金属锂项目竣工，总产能升至 1,600 吨/年',
                '天齐锂业年产 1000 吨高能锂电材料电池级金属锂项目在重庆铜梁竣工，投产后公司金属锂总产能提升至 1600 吨/年。固态电池大规模商业化仍需时日，但产业链上游材料环节已提前布局，头部锂企正围绕金属锂负极材料扩产卡位。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475421',
                '中国有色金属报', '11-19',
                '中矿资源卡通巴铜矿吸纳约 4,000 名本地员工，光伏一期 50 兆瓦并网',
                '中矿资源副总裁王治伟在卢萨卡拜会赞比亚工业、电力、矿业与矿产发展、出口贸易四位部长，围绕卡通巴铜矿建设进度、电力保障、产业配套与税收政策会谈。项目已吸纳约 4000 名本地员工，建成 50 兆瓦光伏并接入国家电网、富余电力可上网；Konona 承建的 330/33 千伏变电站计划 2026 年底投运。公司已与 5 家上下游制造企业签署合作意向，待经济特区激励政策落地后入驻。赞方目标为年产 300 万吨铜。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-11-19/1225677210.PDF',
                '巨潮资讯网', '11-19',
                '江特电机茜坑锂矿证载规模 300 万吨/年，矿区面积 1.3826 平方公里',
                '江特电机披露茜坑锂矿项目情况：采矿证证载生产规模 300 万吨/年、矿区面积 1.3826 平方公里、有效期 30 年，开采方式为露天/地下联合开采。该矿属蚀变花岗岩型锂云母矿床，Li2O 平均品位按 0.44% 计矿石资源储量 7293 万吨，按 0.39% 计达 1.2667 亿吨；300 万吨/年采矿工程安全设施设计已通过审查。',
                embed='pdf')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-19/1225677440.PDF',
                '巨潮资讯网', '11-19',
                '中国五矿增资广西关键金属集团 51% 股权，华锡有色触发全面要约收购',
                '华锡有色公告要约收购进展：中国五矿拟以现金或现金加非现金资产组合方式增资广西关键金属集团、取得其 51% 股权并实现实际控制，交易完成后中国五矿间接持有华锡有色的权益将超过已发行股份的 30%，从而触发全面要约收购义务。目前增资尚需广西关键金属集团股东会审议、国家市场监督管理总局经营者集中审查及国资监管部门批准，存在因未完成而终止的风险，公司每 30 日公告一次进展。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-20/1225680136.PDF',
                '巨潮资讯网', '11-20',
                '赣锋锂业拟回购 2 亿至 4 亿元 A 股，价格上限 57.47 元/股',
                '赣锋锂业披露 A 股回购方案：回购资金总额不低于 2 亿元、不超过 4 亿元，回购价格上限 57.47 元/股，按上限测算预计回购股份约 348 万股至 696 万股，回购股份将用于员工持股计划或股权激励等用途。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-18/1225676673.PDF',
                '巨潮资讯网', '11-18',
                '中铝国际以 EPC 总承包中标越南平福年产 240 万吨氧化铝项目',
                '中铝国际披露中标进展：公司以 EPC 总承包模式承揽越南平福年产 240 万吨氧化铝项目，工程内容为氧化铝厂建设。公司提示合同履行期限较长，实际执行情况存在不确定性。',
                embed='pdf')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261120_10368636.htm',
                '矿业权市场', '11-20',
                '河南嵩县何家村金矿勘探探矿权转让公示，面积 1.7821 平方公里',
                '河南省自然资源厅公示（豫自然资公示〔2026〕1789 号）：河南省嵩县何家村金矿勘探探矿权由河南省有色金属地质勘查总院转让给河南省地质研究院，勘查面积 1.7821 平方公里，勘查许可证号 T4100002010074010041505，有效期自 2022 年 5 月 28 日至 2027 年 5 月 28 日，公示期至 2026 年 12 月 2 日。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261120_10368637.htm',
                '矿业权市场', '11-20',
                '河南嵩县龙潭沟金矿详查探矿权转让公示',
                '河南省自然资源厅公示（豫自然资公示〔2026〕1800 号）：河南省嵩县龙潭沟金矿详查探矿权由洛阳双海矿业有限公司转让给嵩县山鑫矿业有限公司，探矿权有效期自 2025 年 1 月 17 日至 2030 年 1 月 17 日，公示期自 2026 年 11 月 19 日至 12 月 2 日。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202611/t20261119_10367431.htm',
                '矿业权市场', '11-19',
                '新疆拜城县宇海锆铪矿勘查探矿权招标出让，保证金 5 亿元',
                '新疆维吾尔自治区自然资源厅委托自治区公共资源交易中心，对拜城县宇海锆铪矿勘查探矿权组织招标出让。只接受投标申请人现场书面申请，凭保证金交纳凭证及申请资料领取招标文件；保证金金额为人民币 5 亿元，须由投标单位账户转账且账户名称与投标单位一致，未中标者保证金在成交结果公示结束后 5 个工作日内原路径退回。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261119_10367425.htm',
                '矿业权市场', '11-19',
                '甘肃肃北南金山南金矿详查探矿权成交 8,705 万元',
                '甘肃省自然资源厅公示（甘交易矿公示〔2026〕50 号）：2026 年甘肃省肃北县南金山南金矿普查等 11 宗探矿权公开挂牌出让，其中南金山南金矿详查探矿权由肃北县荣华矿业有限公司竞得，成交价 8705.0 万元，勘查面积 4.0205 平方公里，成交时间 2026 年 11 月 13 日。同批白银市陶家湾锰矿普查、枣树湾金矿普查探矿权同日公示成交结果，公示期至 12 月 2 日。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/spartan-puts-683-million-price-tag-on-victorio-moly-tungsten-mine-in-new-mexico/',
                'MINING.COM', '11-19',
                'Spartan 为美国新墨西哥州 Victorio 钨钼矿定价 6.83 亿美元',
                'Spartan Metals（TSXV: W）公布初步经济评估：在新墨西哥州 Victorio 建设地下钨钼矿及钨精矿加工厂需投资 6.83 亿美元，矿山服务 24 年，税后净现值 21.4 亿美元（8% 折现）、内部收益率 31%，全生命周期另需 20.3 亿美元维持性支出。测算按钨氧化物 1,350 美元/10 公斤、钼 20 美元/磅；年均回收钨氧化物约 4,100 吨、钼精矿 865 万磅。美国自 2015 年后未商业开采钨，中国占全球仲钨酸铵精炼产能约 85%。',
                orig_title='Spartan puts $683 million price tag on Victorio moly, tungsten mine in New Mexico')),

    (CAT_GJ, ni('https://www.mining.com/chile-threatens-codelco-mine-permit-over-dust-violations/',
                'MINING.COM', '11-19',
                '智利环境监管机构指控 Codelco 铜矿粉尘违规，或面临停产与吊证',
                '智利环境监管局（SMA）就 Ministro Hales 铜矿两项严重粉尘违规提出指控，单项最高罚款约 430 万美元、合计约 870 万美元，并可能导致停产或吊销环境许可。指控称主破碎机未按许可运行布袋除尘系统、2023 年 11 月至 2024 年 2 月除尘效率低于规定的 75%，废石场在 2023—2024 年未对非作业区喷洒抑尘剂。同日 SMA 批准 Codelco 提交的 Talabre 尾矿整改方案：8 项措施、24 个月、约 6680 万美元。',
                orig_title='Chile threatens Codelco mine permit over dust violations')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202611/t20261119_10368615.htm',
                '全球矿产资源信息系统', '11-19',
                '智利与越南升级为战略伙伴关系，为关键矿产长期供应铺路',
                '11 月 16 日，智利总统卡斯特与越共中央总书记、国家主席苏林在河内会晤后宣布将双边关系提升为战略伙伴关系，涉及政治、经济、技术、国防等领域，为智利铜、锂对越长期供应打开通道。2025 年两国贸易额 21.1 亿美元、同比增 39%，但结构失衡：智利自越进口超 17 亿美元、增 46%，对越出口仅 3.08 亿美元，其中铜（含粗铜及精炼铜）仅 740 万美元、降 34%；越南铜消费 90% 依赖进口。智利方面称到 2034 年本国矿业项目投资将超 1000 亿美元。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202611/t20261119_10368617.htm',
                '全球矿产资源信息系统', '11-19',
                '希尔威推进厄瓜多尔埃尔多莫铜矿建设，投资 2.84 亿美元',
                '据 BNAmericas 报道，加拿大希尔威公司（Silvercorp）在厄瓜多尔中部玻利瓦尔省的埃尔多莫多金属矿建设提速：选矿厂预制钢结构与球磨机零件已运抵，变电站开工，连接电网的外部线路同步建设。项目预计投资 2.84 亿美元，2025 年开工，计划 2027 年 6 月完工、下半年投产，2028 年实现稳产。')),
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

# —— 分桶 PIN（按内容口径：勘查成果属 🔍、政策属 📜、企业事故/产能属 🏭，勿被 _reclassify_ma 依「投资」二字拉到 💰）——
_PIN_CAT = [
    ('智利铜产量', CAT_SC),
    ('沪铝月差', CAT_SC),
    ('美铜', CAT_SC),
    ('再生铅', CAT_ZC),
    ('津巴布韦', CAT_ZC),
    ('措拉', CAT_ZK),
    ('佩莱南', CAT_ZK),
    ('天齐锂业重庆', CAT_HY),
    ('卡通巴', CAT_HY),
    ('茜坑', CAT_HY),
    ('华锡', CAT_MA),
    ('赣锋', CAT_MA),
    ('中铝国际', CAT_MA),
    ('何家村', CAT_KQ),
    ('龙潭沟', CAT_KQ),
    ('宇海', CAT_KQ),
    ('南金山南', CAT_KQ),
    ('Spartan', CAT_GJ),
    ('Codelco', CAT_GJ),
    ('智利与越南', CAT_GJ),
    ('希尔威', CAT_GJ),
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
