# -*- coding: utf-8 -*-
"""
生成 2026-11-07 矿业资讯速览 index.html（周六）
- 11-06 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-09）回补历史条目
- 换入 11-07 采集的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 11-06 收盘 + LME 11-06 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目：11-07 增补 9 宗（内蒙巴林右旗银矿 + 巴林左旗铅矿挂牌、
  新疆托里安山岩成交、扎赉特旗黑大山转让、云南沧源富公转让、
  湖南临武鸡脚山作价出资、四川达州炉坪煤矿转让、敖汉 2 宗深部协议出让），
  已写入 data/news_2026-11.json，由 news-data.js 直出 #rightsCards，不进主列表
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

REPORT = '2026-11-07'
GRAB = '2026-11-07'
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
                         r'\g<1>2026年11月07日 星期六', html)
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
    (CAT_ZK, ni('https://www.mining.com/new-gold-discovery-boosts-perpetuas-stibnite-project',
                'MINING.COM', '11-05',
                'Perpetua 在 Stibnite 项目发现新金矿，见矿 109.7 米、金 3.2 克/吨',
                'Perpetua Resources 在美国爱达荷州 Stibnite 金矿项目 2026 年勘查钻探中发现 Fiddle 新矿体，发现孔 SB633 见矿 109.7 米、金品位 3.2 克/吨、锑 1.1%，位于已获批 Yellow Pine 采坑以南约 750 米。项目累计完成逾 16,000 米岩心钻探，建成后年产金约 450,000 盎司，锑储量 1.48 亿磅。',
                orig_title='New gold discovery boosts Perpetua\u2019s Stibnite project')),

    (CAT_ZK, ni('https://news.metal.com/newscontent/104207955-eloro-reports-high-grade-silver-tin-drilling-at-bolivias-iska-iska-advances-40000-m-expansion',
                'SMM 国际站', '11-06',
                'Eloro 玻利维亚 Iska Iska 银锡矿见 87.1 米厚银矿体',
                'Eloro Resources 公布玻利维亚波托西 Iska Iska 银锡多金属项目首批扩边钻探成果：DSB-96 孔自 40.4 米见矿 87.1 米、银品位 73.26 克/吨、锡 0.18%，其中近地表 17.9 米银品位 190.5 克/吨、锡 0.45%。公司正推进 40,000 米钻探计划，初步经济评价（PEA）计划于 2027 年二季度完成。',
                orig_title='Eloro reports high-grade silver-tin drilling at Bolivia\u2019s Iska Iska, advances 40,000 m expansion')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104210278',
                '上海有色网', '11-06',
                '印尼要求矿物与棕榈油直接出口，绕开邻国中转',
                '印尼粮食统筹部长祖基菲里 11 月 4 日在巴淡岛表示，印尼希望棕榈油、矿物等自然资源直接运往最终买家，不再经邻国转售加价；他称毛棕榈油在国内每公斤 27,000 印尼盾、卖给邻国仅 15,000 印尼盾，每公斤损失 12,000 印尼盾。能源与矿产资源部长巴赫利尔此前警告，中转国可能将这些大宗商品申报为本国出口，从中获取税收与统计收益。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104207632',
                '上海有色网', '11-05',
                '哥伦比亚废除 530 万公顷采矿限制区，或释放 47 亿美元投资',
                '哥伦比亚矿业部 10 月 22 日废除 15 个特殊采矿分区、覆盖 530 万公顷（约占国土 5%），农业部门同时撤销四个地区的粮食生产保护区。矿业协会主席估计，更有利的投资环境可释放 47 亿美元矿山建设投资、每年吸引 3.5 亿美元勘探支出，并支持行业年增长最高 10%。取消限制并不自动授权采矿，企业仍须满足环境、许可与其他用地要求。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104205434',
                '上海有色网', '11-05',
                '印度批准 2.97 亿美元锂镍加工资本补贴计划',
                '印度内阁批准“促进关键矿产加工资本支出支持计划”，总额 281.4 亿卢比（约 2.97 亿美元），实施期为 2026-27 至 2030-31 财年，对符合条件的投资提供 30% 资本补贴。计划支持建设两座锂加工厂（每座最低产能 3 万吨）与两座镍加工厂（每座最低产能 5 万吨），旨在降低对外部供应链的依赖。')),

    (CAT_ZC, ni('https://www.mining.com/budget-extends-tax-relief-but-leaves-explorers-wanting',
                'MINING.COM', '11-06',
                '加拿大预算将矿产勘查税收抵免延长五年，勘查界仍嫌不足',
                '加拿大联邦 2026 年预算将矿产勘查税收抵免延长五年，但勘查业界认为延长期限与覆盖范围仍不足，难以支撑早期草根勘探融资。预算于 11 月 5 日由总理卡尼与财长商鹏飞在渥太华发布。',
                orig_title='Canada\u2019s budget extends tax relief but leaves mineral explorers wanting')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104210296',
                '上海有色网', '11-06',
                '高盛下调金价预测：2026 年底 4,150 美元、2027 年底 4,800 美元',
                '高盛 11 月 5 日报告将 2026 年底金价目标由 4,650 美元/盎司下调至 4,150 美元，2027 年底由 5,400 美元下调至 4,800 美元，理由是其基准情景假设美联储 2026 年 12 月加息，压制投资者的货币贬值对冲需求。高盛维持央行购金长期看多判断，预计 2026 至 2027 年央行月均购金 60 吨，远高于 2022 年前每月 17 吨的均值。')),

    (CAT_SC, ni('https://news.smm.cn/news/104207743',
                '上海有色网', '11-06',
                '七成 LME 铜库存存放于美国仓库，占比创 2019 年 3 月以来最高',
                'LME 数据显示，新奥尔良、巴尔的摩与莫比尔三地库存合计 223,300 吨，占 LME 铜总库存 318,675 吨的 70.1%，为 2019 年 3 月以来最高；其中新奥尔良 172,500 吨，创 2014 年 4 月以来新高。市场预计美国自 2027 年起对精炼铜征收 15% 关税，推动金属持续流入；LME 亚洲仓库占比降至 23.2%，为 2024 年 4 月以来最低。')),

    (CAT_SC, ni('https://news.smm.cn/news/104205282',
                '上海有色网', '11-05',
                '美国 9 月铜进口环比降 3.1%，仍近去年同期两倍',
                '美国 9 月进口精炼铜及铜合金 194,284 吨，低于 8 月的 200,519 吨和 7 月创纪录的 225,094 吨，环比降 3.1%，但仍是 2025 年 9 月 102,279 吨的近两倍。今年前九个月累计进口 152 万吨、同比增长 17%，市场等待美国是否自 2027 年起对精炼铜征收 15% 关税的明确信号。')),

    (CAT_SC, ni('https://news.smm.cn/news/104207757',
                '上海有色网', '11-06',
                '章源钨业上调 11 月上半月长单报价，黑钨精矿升至 37.5 万元/标吨',
                '崇义章源钨业 11 月 5 日发布 11 月上半月长单采购报价：55% 黑钨精矿 37.5 万元/标吨、55% 白钨精矿 37.4 万元/标吨，均较上轮上调 3.1 万元/标吨；仲钨酸铵（国标零级）55 万元/吨，较上轮上调 5 万元/吨。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475152',
                '中国有色金属报', '11-03',
                '芝商所拟 2027 年一季度挂牌全球首只钨 APT 期货',
                '芝商所（CME）10 月宣布计划于 2027 年一季度在 COMEX 板块挂牌全球首只钨 APT（仲钨酸铵）期货，采用现金结算、锚定 Fastmarkets 鹿特丹与巴尔的摩 CIF 价格，不设实物交割。中国占全球钨精矿产量约 78%、APT 冶炼产能 80% 以上，美国自 2015 年后已无商业钨矿开采产能；2024 至 2026 年鹿特丹 APT 现货价最大涨幅超过 200%。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475221',
                '中国有色金属报', '11-05',
                '巨龙铜业知不拉矿区 45 辆无人驾驶矿卡规模化运行',
                '西藏巨龙铜业知不拉矿区目前约 45 辆无人驾驶矿卡承担装载、运输与翻卸作业，低电量时自动返回充电；矿卡采用“雷达+图像识别”双重技术，驾驶员转为室内调度员，作业地点由海拔 5,000 多米的采场移至 3,800 多米的调度室。公司 2024 年启动无人驾驶矿卡项目，并同步拓宽平整运输道路、加宽装卸作业面、设置矿区红绿灯与通行规则。')),

    (CAT_HY, ni('https://news.smm.cn/news/104207638',
                '上海有色网', '11-05',
                '松下新竹湖口厂爆炸起火，全球高端 CCL 供给约 4% 面临中断',
                '中国台湾松下多层材料（PIDMTW）新竹湖口厂 11 月 4 日凌晨发生爆炸火灾，燃烧面积逾 1 万平方米、约占厂区三分之一，5 名员工受伤、2 名台籍员工失联。业界评估受损产能约占全球高端 CCL 供给的 4%——松下 MEGTRON 系列约占全球高端 CCL 市场 20%，湖口厂又约占该系列全球产能两成；台光电、台燿等厂商有望承接转单。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.smm.cn/news/104207630',
                '上海有色网', '11-05',
                '艾芬豪再下调卡莫阿-卡库拉 2027 年产量指引至 30-35 万吨',
                '艾芬豪矿业今年第二次下调刚果（金）卡莫阿-卡库拉铜矿 2027 年产量指引至 30-35 万吨（此前 38-42 万吨），并将 2027 年 C1 现金成本指引由每磅 2.10-2.50 美元上调至 2.50-3.00 美元。卡库拉东侧正式复产推迟至 2028 年 3 月末；三季度可销售铜产量 76,401 吨，公司预计 2026 年全年产量约 29 万吨。')),

    (CAT_GJ, ni('https://news.smm.cn/news/104207629',
                '上海有色网', '11-05',
                '自由港批准 45 亿美元巴格达铜钼矿扩建，年铜产能提高逾一倍',
                '自由港麦克莫兰董事会批准 45 亿美元的巴格达（Bagdad）铜钼矿区扩建与现代化计划，将使开采与选矿产能提高逾一倍，长期年铜产量提升至 4 亿磅以上（年增量约 2.25 亿磅）、钼产量提升至每年 2,000 万磅以上（年增量约 1,200 万磅）。扩建后该矿将成为美国第二大铜矿；约 20% 投资在 2027 年投入、30% 至 35% 在 2028 年投入。')),

    (CAT_GJ, ni('https://news.smm.cn/news/104207915',
                '上海有色网', '11-06',
                '世纪铝业三季度净利 3.026 亿美元，电力成本拖累业绩',
                '世纪铝业 2026 年三季度归属净利润 3.026 亿美元、环比增 5,330 万美元，调整后净利润 2.716 亿美元、调整后 EBITDA 3.316 亿美元。业绩受冰岛格伦达坦吉 2 号线复产带动出货量提升与售价走高支撑，但被极端高温推高电价、电力结算成本走弱以及 1,510 万美元设备故障税后损失部分抵消。')),

    (CAT_GJ, ni('https://www.mining.com/lundin-cuts-copper-outlook-again-as-wild-chile-weather-bites',
                'MINING.COM', '11-05',
                'Lundin 两月内二度下调铜指引，Caserones 受智利冬季风暴拖累',
                'Lundin Mining 将智利 Caserones 矿 2026 年产量指引由 120,000 至 130,000 吨下调至 105,000 至 115,000 吨，公司全年铜产量指引随之降至 285,000 至 310,000 吨，为两个月内第二次下调。三季度冬季风暴致该矿停产约 30 天，融雪持续限制运输与矿石入厂；公司称减少的产量属递延而非损失，预计 2027 年恢复。',
                orig_title='Lundin cuts copper outlook again as wild Chile weather bites')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104210267-adanis-kutch-copper-raises-utilisation-target-to-80',
                'SMM 国际站', '11-06',
                'Adani Kutch Copper 上调产能利用率目标至 80-85%',
                'Adani 旗下 Kutch Copper 计划在本财年（至 3 月）末将 500,000 吨/年铜冶炼产能利用率提升至 80-85%，高于 7 月提出的 75% 目标。长协覆盖约 50-60% 的铜精矿需求、另有约 20% 通过现货采购；9 月季度利用率为 64%，产铜 80,200 吨、销售 80,600 吨。',
                orig_title='Adani\u2019s Kutch Copper Raises Utilisation Target to 80\u201385% as Feedstock Deals Support Ramp-Up')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.smm.cn/news/104203329',
                '上海有色网', '11-04',
                '戈登矿业完成收购美国新墨西哥州钨尾矿项目',
                '戈登矿业集团完成对美国新墨西哥州塞拉县钨尾矿（TT）项目并购，项目面积 847 英亩、含 41 个矿权。交易对价包括 12.5 万加元（8.9 万美元）现金及向斯特拉塔矿山技术公司出让 150 万股普通股，后者保留 2.0% 冶炼厂净收益权利金，公司可以 100 万美元回购其中 1.0%。公司称将以人工智能辅助定位结合 USGS 地球物理与填图数据确定首个钻探目标。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-07/1225661574.PDF',
                '巨潮资讯', '11-07',
                '中国铝业拟签订几内亚氧化铝项目 EPC 总承包合同',
                '中国铝业公告，拟与中铝国际签署几内亚氧化铝项目 EPC 总承包合同，该交易构成关联交易；中铝国际同日就同一合同发布关连交易公告。合同金额、工期与建设规模以公告正文为准。')),
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
    ('Perpetua', CAT_ZK),
    ('Eloro', CAT_ZK),
    ('印尼', CAT_ZC),
    ('哥伦比亚', CAT_ZC),
    ('印度', CAT_ZC),
    ('加拿大', CAT_ZC),
    ('高盛', CAT_SC),
    ('LME 铜库存', CAT_SC),
    ('铜进口', CAT_SC),
    ('章源', CAT_SC),
    ('芝商所', CAT_SC),
    ('巨龙', CAT_HY),
    ('松下', CAT_HY),
    ('艾芬豪', CAT_GJ),
    ('自由港', CAT_GJ),
    ('世纪铝业', CAT_GJ),
    ('Lundin', CAT_GJ),
    ('Adani', CAT_GJ),
    ('戈登', CAT_MA),
    ('中国铝业', CAT_MA),
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
