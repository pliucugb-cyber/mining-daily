# -*- coding: utf-8 -*-
"""
生成 2026-11-22 矿业资讯速览 index.html（周日）
- 11-21 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30）回补历史条目
- 换入 11-22 采集的条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-20 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）
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

REPORT = '2026-11-22'
GRAB = '2026-11-22'
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
                         r'\g<1>2026年11月22日 星期日', html)
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
    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/newscontent/WRRKLNAZXKUSQCT3ZRKKTHGKAHXP5SFN4IY2GWI-chinas-ministry-of-natural-resources-issues-new-rules-for-strategic-mineral-exploration-rights-tendering',
                'SMM 国际站', '11-21',
                '自然资源部规范探矿权招标出让，战略矿产勘查区块优先招标',
                '自然资源部近日印发《关于规范探矿权招标出让的通知》，自 2027 年 1 月 1 日起施行，有效期五年。通知要求，对稀缺性强的战略性矿产资源勘查区块、资源储量达中型及以上的战略矿产勘查区块，以及勘查开采技术或生态环境保护有特殊要求的区块，出让探矿权时应优先采用招标方式。招标条件设置须服务全国统一大市场建设，加强公平竞争审查，禁止违法设置地域、行业或所有制形式等限制性条件。',
                orig_title='China\'s Ministry of Natural Resources Issues New Rules for Strategic Mineral Exploration Rights Tendering')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://news.metal.com/newscontent/4UROQ4BQ4ZMF5QGGNAKGPFPQO5OX2B3XJKITJ5A-australasian-metals-commences-diamond-drilling-at-c',
                'SMM 国际站', '11-20',
                'Australasian Metals启动科特迪瓦Atex锂钽项目金刚石钻探，设计3000米',
                'Australasian Metals 在其科特迪瓦 Atex 锂钽项目 Spodumene Hill 矿段启动金刚石钻探，设计总进尺约 3000 米，其中 1500 米部署于 Spodumene Hill，另 1500 米用于解释成矿构造走廊内的区域靶区。公司持有该项目 75% 权益的独家选择权。本轮钻探主要评价含锂伟晶岩的延伸与连续性，项目兼具钽矿潜力，尚需钻探与分析结果确认矿化规模与经济意义。',
                orig_title='Australasian Metals Commences Diamond Drilling at C\u00f4te d\u2019Ivoire\u2019s Atex Project')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475373',
                '中国有色金属报', '11-17',
                '西北有色地矿七一七总队连中两标，内蒙古达茂旗铜镍矿详查开钻',
                '西北有色地矿集团七一七总队公司地质勘查院先后中标内蒙古自治区达茂旗某铜镍矿详查钻探技术服务项目与陕西省某耕地提质增效项目。达茂旗铜镍矿详查设计钻探总进尺 1500 米、单孔孔深 500 米，10 月 30 日已举行开钻仪式，为该公司近年首次进入内蒙古钻探施工市场；陕西项目属渭河中上游山水林田湖草沙一体化保护和修复工程子项目，统筹生态修复与耕地保护。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/XUUXKMDG6DKVZEIKI747HH6GMRFE2F6I2C7AYZQ',
                '上海有色网', '11-20',
                '章源钨业上调11月下半月长单报价，黑钨精矿升至39.5万元/标吨',
                '崇义章源钨业公布 11 月下半月长单采购报价：55% 黑钨精矿 39.5 万元/标吨、55% 白钨精矿 39.4 万元/标吨，均较上轮上调 2 万元/标吨；仲钨酸铵（国标零级）57 万元/吨，较上轮上调 2 万元/吨。钨精矿与 APT 报价同步上调，反映原料端偏紧格局仍在延续。')),

    (CAT_SC, ni('https://news.smm.cn/news/LFI5ZMCVWGQUSDACT264EF7Y623FWWNRS7EIV2Q',
                '上海有色网', '11-18',
                '高盛：2027年底金价看4650美元/盎司，短期谨防大幅回撤',
                '高盛在 2027 年贵金属策略中预计，到 2027 年 12 月黄金价格将达每盎司 4650 美元，2028 年 12 月进一步升至 5600 美元，但提醒长期看涨并不等于短期上涨。该行预计美联储 2026 年 12 月与 2027 年 3 月各加息 25 个基点，将压制西方黄金 ETF 需求、加大投机盘平仓风险；若累计加息四次，2027 年底金价预测下调至约 4585 美元，若 ETF 额外流出 300 吨则降至 4265 美元。央行持续购金被视为金价的主要支撑力量。')),

    (CAT_SC, ni('https://news.smm.cn/news/CRM6NP4LW37ZYIOS4T3LPFWGT47RGT43VITJSGA',
                '上海有色网', '11-18',
                'WPIC：2027年全球铂金重回短缺，缺口约9吨',
                '世界铂金投资协会（WPIC）三季度《铂金季刊》预测，2027 年全球铂金总需求同比增长 12% 至约 239 吨，总供应仅增 1% 至约 231 吨，全年缺口约 9 吨。投资需求由 2026 年净抛售 12 吨转为净增持 16 吨，工业需求连续第三年增长、创 83 吨历史新高。2027 年底地上存量预计降至 56 吨，仅能满足不足三个月需求。')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/xycrgs/ckq/202611/t20261121_10369994.htm',
                '矿业权市场', '11-20',
                '陕西榆林三台界煤矿深部资源采矿权拟协议出让，面积6.2159平方公里',
                '榆林市自然资源和规划局公示，依据矿业权出让交易规则等规定，拟以协议方式出让陕西榆林榆阳区三台界煤矿深部资源采矿权，开采矿种为煤，面积 6.2159 平方千米。协议出让理由为满足矿山安全生产和矿业权设置合理性要求，需利用原有生产系统进一步勘查开采已设采矿权深部资源。公示期至 2026 年 12 月 4 日。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475411',
                '中国有色金属报', '11-19',
                '商洛铁钒钛产业链前9月产值32.48亿元，占规上工业11.3%',
                '陕西商洛市以绿色矿业为方向深化产业链「链长制」，已形成上游采选、中游冶炼加工为主的铁钒钛产业集群。2026 年 1—9 月，全市铁钒钛产业链 17 家规模以上企业实现产值 32.48 亿元，占规上工业总产值的 11.3%。龙头企业陕西大西沟矿业拥有大西沟铁矿采矿权面积 4.2863 平方公里、探明铁矿石储量 3.02 亿吨，正实施 800 万吨/年菱铁绿色循环产业改扩建项目，总投资 16.65 亿元。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/elementusa-geophysx-partner-to-advance-jamaicas-critical-minerals-sector',
                'MINING.COM', '11-20',
                'ElementUSA与Geophysx合作，从牙买加铝土矿赤泥中回收关键矿产',
                '关键矿产回收技术开发商 ElementUSA 与牙买加勘查企业 Geophysx Jamaica 签署谅解备忘录，联合从牙买加铝土矿赤泥中回收关键矿产、铁及其他有价组分，并为这些历史工业场地的环境问题寻找商业化解决方案。牙买加氧化铝工业数十年产出大量赤泥，目前多以堆存方式处置。双方计划结合 ElementUSA 的工艺与工程能力、Geophysx 的本地资源开发经验和社区关系，验证赤泥作为关键矿产商业来源的可行性。',
                orig_title='ElementUSA, Geophysx partner to advance Jamaica\u2019s critical minerals sector')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/FDLTBASG227XJPLR7BXDBFDEMJJRRJVBKRSB77Y-perseus-mining-advances-nyanzaga-commissioning-after-first-ore-enters-plant',
                'SMM 国际站', '11-20',
                'Perseus坦桑尼亚Nyanzaga金矿首批矿石入厂，目标2027年初首次产金',
                'Perseus Mining 位于坦桑尼亚西北部的 Nyanzaga 金矿首批矿石进入选厂，项目由建设转入试运行；尾矿库与营地已建成，半自磨机与球磨机衬板安装完成，采矿物料运输进度超前。矿山按 16 年服务期规划，全周期产金约 350 万盎司，2028—2041 年大部分年份年产金超 20 万盎司。公司目标 2027 年初首次浇金，220 千伏并网调试预计 2026 年 11 月底完成。',
                orig_title='Perseus Mining Advances Nyanzaga Commissioning After First Ore Enters Plant')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/YLEHKTT36DMPDLARLUYJHLBSFNLG2XVZ6QVUHJQ-kenya-selects-us-led-consortium-as-preferred-bidder-for-mrima-hill-project',
                'SMM 国际站', '11-20',
                '肯尼亚Mrima Hill铌稀土项目选定美国牵头联合体为优先投标人',
                '肯尼亚政府经竞争性招标，选定 Frontier Minerals 联合体为夸莱郡 Mrima Hill 铌稀土项目优先投标人，成员包括 Frontier Minerals LLC、Bunker Hill Mining、ReElement Technologies 与 American Resources。该项目被视为肯尼亚最具战略意义的未开发关键矿产矿床之一，政府援引的初步评估显示稀土与铌潜力可观。联合体尚需完成社区沟通并取得勘查许可，项目因涉及森林和当地视为圣地的区域，面临环境与社会敏感性约束。',
                orig_title='Kenya Selects US-Led Consortium as Preferred Bidder for Mrima Hill Project')),
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
    ('探矿权招标', CAT_ZC),
    ('Australasian', CAT_ZK),
    ('七一七', CAT_ZK),
    ('章源钨业', CAT_SC),
    ('高盛', CAT_SC),
    ('铂金', CAT_SC),
    ('三台界', CAT_KQ),
    ('商洛', CAT_HY),
    ('ElementUSA', CAT_GJ),
    ('Perseus', CAT_GJ),
    ('Mrima', CAT_GJ),
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
