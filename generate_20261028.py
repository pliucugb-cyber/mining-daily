# -*- coding: utf-8 -*-
"""
生成 2026-10-28 矿业资讯速览 index.html（周三）
- 10-27 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-29）回补历史条目
- 换入 10-28 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-27 收盘 + LME 10-27 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目（ky.mnr 10-27 批）仅入月库 → 前端 #rightsCards，不进主列表
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

REPORT = '2026-10-28'
GRAB = '2026-10-28'
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
                         r'\g<1>2026年10月28日 星期三', html)
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
    (CAT_ZK, ni('https://news.metal.com/newscontent/104181868-fitzroy-identifies-nine-copper-targets-at-buen-retiro-chile-as-5000-metre-drilling-begins',
                'SMM 国际站', '10-22',
                'Fitzroy 在智利 Buen Retiro 圈定 9 个铜靶区，5,000 米钻探已启动',
                'Fitzroy Minerals 10 月 22 日称，与 Fleet Space Technologies 合作的机器学习与三维地震研究，在智利 Buen Retiro 项目圈定 9 个此前未钻探的铜靶区，埋深约 400 米以内。模型基于 140 个钻孔约 24,400 个铜分析数据、4 套地球物理数据集，按 25 米方块估算铜品位高于 0.5% 的可能分布。5,000 米金刚石与反循环钻探正在进行；首个资源量与初步经济评价计划 2026 年四季度完成，2028 年目标投产。',
                orig_title='Fitzroy Identifies Nine Copper Targets at Buen Retiro, Chile, as 5,000-Metre Drilling Begins')),

    (CAT_ZK, ni('https://news.smm.cn/news/104179608',
                '上海有色网', '10-27',
                '澳大利亚吉尔摩铜金项目钻探见明显矿化，321 米至终孔 750.3 米连续见矿',
                '林克矿产（LinQ Minerals）宣布，新南威尔士州吉尔摩项目钻孔在 321 米深处至终孔 750.3 米见到非常明显矿化，地质团队判断可能存在大型高硫浅成热液—斑岩系统。公司称该孔或已钻遇系统核部，吉景邦与达姆矿床仅为其一部分；项目矿石资源量 5.16 亿吨，含金约 370 万盎司、铜 120 万吨。岩心样品将在 6 至 8 周内化验，该孔为吉景邦南靶区 4 个计划钻孔之一。')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/kfjs/202610/t20261027_10346441.htm',
                '全球矿产资源信息系统', '10-27',
                '西澳朱皮特稀土矿公布 5.56 亿澳元开发计划，税后净现值 20 亿美元',
                '科里蒂卡（Critica）公布西澳磁山附近朱皮特稀土矿开发计划：投资 5.56 亿澳元，概略研究仅覆盖矿床 6%，动用矿石资源量 1.07 亿吨，可采 14 年、年采矿石 800 万吨，产 TREO 品位 0.83% 的混合稀土精矿；基本场景税后净现值 20 亿美元、内部收益率 48.4%、投资回报期 2 年。矿床总资源量 17 亿吨、TREO 品位 0.17%，镨钕镝铽与钇占比 23%，公司目标 2029 年中作出最终投资决定。')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202610/t20261027_10346439.htm',
                '全球矿产资源信息系统', '10-27',
                '巴西地质调查局完成大西洋中脊 29 天调查，加快深海矿产潜力评价',
                '巴西地质调查局（SGB）本月初完成大西洋中脊调查任务，9 月 9 日至 10 月 8 日共 29 天，对三片具热液活动与成矿潜力区域开展物探、海底地形勘测，并采集水样与海底沉积物样品。初步数据显示水中悬浮颗粒异常，指示可能存在热液活动。任务属科迪勒拉项目（Procordilheira）与南赤道大西洋国际水域矿产资源调查计划（PROAREA）的一部分。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104179554',
                '上海有色网', '10-27',
                '上期所新增镍期货交割库存放点，四家仓库核定库容合计增 1 万吨',
                '上期所 10 月 26 日发布〔2026〕231 号公告：上港云仓上海宝山安达路存放点镍交割库容由 1 万吨增至 1.5 万吨；常州金坛儒林镇园区西路存放点新设为镍交割仓库存放点、核定库容 5,000 吨且不设地区升贴水；中国外运华东逸仙路存放点由 1 万吨增至 1.5 万吨；宁波保税区高新货柜存放点由 5,000 吨增至 8,000 吨。')),

    (CAT_ZC, ni('https://news.metal.com/newscontent/104181881-smm-analysis-thailands-proposed-scrap-import-ban-may-redirect-shipments-to-india-and-other-asian-markets',
                'SMM 国际站', '10-28',
                '泰国拟禁止废金属进口，SMM 预计货源或转向印度等亚洲市场',
                'SMM 分析称，泰国拟议的废料进口禁令若落地，相关货源可能转向印度等亚洲市场，推高当地废料供应量，并对混合金属废料与 Zorba 价格形成压力。东南亚废铜、废铝贸易流向或随之调整。',
                orig_title="[SMM Analysis] Thailand's Proposed Scrap Import Ban May Redirect Shipments to India and Other Asian Markets")),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474977',
                '中国有色金属报', '10-27',
                '彭博新能源财经：全球铜短缺 2028 年起显现，2050 年缺口达需求 44%',
                '彭博新能源财经报告称，全球铜市场将从 2028 年起进入大规模长期短缺，2035 年供给缺口达需求量的 8%，2050 年扩大至 44%。LME 铜价 9 月创 14,875 美元/吨历史新高，较 2024 年初累计上涨 76%。Teck 首席执行官 Price 预计 2035 年缺口约 30%，并指出发现、审批并建成一座新矿可能需 15 年，而建一座数据中心只需 6 个月。')),

    (CAT_SC, ni('https://news.smm.cn/news/104177029',
                '上海有色网', '10-26',
                '沪镍自年内低点反弹后回落，机构称弱现实底色未改',
                '沪镍 2612 合约 10 月 16 日跌至 114,610 元/吨的年内低点，减产预期发酵后 10 月 22 日最高触及 123,690 元/吨，10 月 23 日回落收于 120,580 元/吨。印尼将今年镍矿生产配额修订为约 2.9 亿吨、较初设提高约 3,000 万吨；10 月下半月 1.6% 品位镍矿实际成交价跌至 57.62 美元/湿吨。9 月我国精炼镍产量 2.87 万吨、同比降 22.1%；截至 10 月 16 日社会库存 120,574 吨、同比增 128.5%。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/a293e7f45fd7436b9abf09f5ae8f0778.html',
                '长江有色网', '10-27',
                '钨粉均价升至 76.5 万元/吨，光伏钨丝与高端制造需求支撑现货偏紧',
                '10 月 27 日长江综合钨粉均价 765,000 元/吨，较上一交易日上涨 10,000 元，市场看涨情绪升温，钨产业链报价同步走强。光伏钨丝与高端制造需求形成支撑，现货货源偏紧。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/e9d3bac498db4d84af35e99db837c9a7.html',
                '长江有色网', '10-27',
                '电池级氢氧化锂均价回升至 8.95 万元/吨，市场询盘转活跃',
                '10 月 27 日长江综合市场电池级氢氧化锂报价区间 86,500 至 92,500 元/吨，均价 89,500 元/吨，较前一交易日上涨 1,000 元；工业级报价 75,500 至 82,000 元/吨，均价 78,750 元/吨，同步上涨 1,000 元。市场询盘活跃度明显提升，贸易商惜售情绪抬头。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474959',
                '中国有色金属报', '10-27',
                '金鼎锌业 1 万吨/天硫化矿选厂投料试车，为国内铅锌单系列最大',
                '云南金鼎锌业新建 1 万吨/天硫化矿选厂投料试车成功，选厂占地 237.13 亩，2025 年 5 月 9 日开工、2026 年 5 月全流程稳定运行；截至 2026 年 9 月累计处理矿石 117.24 万吨、产出铅锌金属 4.11 万吨。项目碎磨系统靠近采场上部、浮选及后续工序位于下部，依托自然高差实现矿浆自流，每年节约运输成本约 3,000 万元，加工成本每吨降低约 30 元。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474972',
                '中国有色金属报', '10-27',
                '新疆华瓯矿业萤石选矿车间联动试车成功，攻克易泥化高钙萤石难题',
                '10 月 20 日，新疆华瓯矿业选矿车间联动试车一次性成功。该车间 2025 年 9 月投料试生产后受工艺成熟度与矿石条件制约未能连续稳定生产，一年来依托集团揭榜挂帅平台联合科研院所攻关易泥化高钙萤石矿选矿技术，2026 年 8 月 6 日通过竣工验收，目前设备运行平稳、各工序衔接正常。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474912',
                '中国有色金属报', '10-26',
                '中铝数为电解铝熔融电解质在线检测系统完成工业试验，单次检测不超 15 分钟',
                '中铝数为自主研发的电解铝熔融电解质成分在线检测系统，在中铝青海分公司 600kA 电解槽完成工业试验与数据验证，实现高温强磁工况下在线成分检测。传统线下送检单样品全流程耗时 4 小时以上，新系统单次检测不超过 15 分钟、每 10 分钟输出 1 次数据，检测效率提升 95% 以上；2026 年 9 月完成工况适配优化与长期稳定性测试。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-28/1225628609.PDF',
                '巨潮资讯网', '10-28',
                '铜冠铜箔拟对部分生产线实施技术改造',
                '铜冠铜箔 10 月 28 日公告，拟对部分生产线实施技术改造项目，以提升产线装备水平与产品结构。投资金额、改造范围与建设周期以公告原文为准。',
                embed='pdf')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://news.metal.com/newscontent/104181805-smm-news-chile-plans-five-new-lithium-project-tenders-in-2027-to-more-than-double-output',
                'SMM 国际站', '10-21',
                '智利计划 2027 年再招标 5 个锂项目，目标产量翻番以上',
                '智利矿业部 10 月 21 日表示，计划明年再对 5 个锂项目发放招标；目前另有 5 个待批项目，获批后将全面开发。该国以 2027 年为节点争取锂产量较当前水平翻番以上，招标面向国内外企业开放。',
                orig_title='[SMM News] Chile plans five new lithium project tenders in 2027 to more than double output')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.metal.com/newscontent/104181810-atlantic-lithium-transfers-ewoyaa-project-stake-and-offtake-rights-to-huayou-gains-ministry-approval',
                'SMM 国际站', '10-28',
                '华友钴业受让加纳 Ewoyaa 锂矿权益与包销权，获加纳矿业部批准',
                'Atlantic Lithium 宣布，已完成将 Elevra Lithium 在加纳 Ewoyaa 锂项目及加纳更广矿权组合中的权益与权利义务转让给浙江华友钴业，并获加纳矿业部批准。交易完成后华友取得项目权益及包销权，具体股权比例与对价以公司公告为准。',
                orig_title='Atlantic Lithium Transfers Ewoyaa Project Stake and Offtake Rights to Huayou, Gains Ministry Approval')),

    (CAT_MA, ni('https://www.mining.com/capstone-to-invest-3b-in-chile-to-double-copper-production',
                'MINING.COM', '10-27',
                'Capstone 计划在智利投资 30 亿美元，2031 年铜产量翻番',
                '据智利矿业部，Capstone Copper 将在阿塔卡马大区投资 30 亿美元，到 2031 年使其在智利铜产量翻番。其中 23 亿美元投向在建的 Santo Domingo 项目，约 2.2 亿美元用于 Mantoverde 两个扩建项目，另有 1.65 亿美元矿山开发、1.5 亿美元维持性资本与 0.7 亿美元勘探支出。Santo Domingo 建设期用工超 8,000 人，投产后约 1,500 个岗位。',
                orig_title='Capstone to invest $3B in Chile to double copper production')),

    (CAT_MA, ni('https://www.mining.com/perpetua-resources-gets-40m-us-army-funding-to-advance-tungsten-production-in-idaho',
                'MINING.COM', '10-28',
                'Perpetua 获美国陆军 4,000 万美元资助，推进爱达荷钨精矿生产',
                'Perpetua Resources 通过美国陆军国防军械技术联盟（DOTC）获得 36 个月、4,000 万美元资助，用于评估在其爱达荷州 Stibnite 矿区生产钨精矿的技术与经济可行性。资金按成本分摊模式支持钻探圈定钨资源、采集冶金试验样品，以及勘探斜坡道的许可与工程设计。美国自 2015 年起无商业化钨矿开采，完全依赖进口。',
                orig_title='Perpetua Resources gets $40M US Army funding to advance tungsten production in Idaho')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/codelco-copper-mine-blockade-adds-to-supply-concerns',
                'MINING.COM', '10-27',
                'Codelco 智利 Ministro Hales 铜矿遭封堵，停产约 6 小时',
                '智利国家铜业（Codelco）Ministro Hales 铜矿工人因奖金未兑现封堵矿区入口约 6 小时，生产与车辆运输一度停滞。事件源于 2025 年 12 月一起运输卡车起火事故，13 台卡车停运数日并影响奖金发放。咨询机构 GEM 测算，罢工、极端天气、事故与地质问题平均使智利大型铜矿 5.2% 的产量面临风险，El Teniente 风险分 9% 居首。',
                orig_title='Codelco copper mine blockade adds to supply concerns')),

    (CAT_GJ, ni('https://www.mining.com/china-gold-restarts-csh-mine-after-five-month-shutdown',
                'MINING.COM', '10-28',
                '中国黄金国际长山壕金矿恢复露天开采，全年产量指引不变',
                '中国黄金国际（TSX: CGG）内蒙古长山壕金矿因边坡失稳自 2026 年 5 月 22 日停产近 5 个月后，已于 10 月初恢复露天开采，2026 年产量指引维持 70,732 至 83,592 盎司不变。治理工程包括道路系统恢复、清除松散岩土、加固滑坡体、建立排水系统与持续边坡监测，9 月底完成并与应急管理部门完成备案。该矿 2025 年产金 96,816 盎司。',
                orig_title='China Gold restarts CSH mine after five-month shutdown')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104181864-korea-zinc-accelerates-germanium-expansion-kemco-targets-q4-crude-germanium-production',
                'SMM 国际站', '10-28',
                '韩国锌业加速锗扩产，KEMCO 计划四季度量产粗锗',
                '韩国锌业称，其子公司 KEMCO 已于 2026 年 8 月在蔚山温山开始粗锗产品试生产，计划 2026 年四季度转入量产。锗为半导体与红外光学关键材料，海外冶炼企业正加快从锌冶炼副产品中回收锗的布局。',
                orig_title='Korea Zinc Accelerates Germanium Expansion; KEMCO Targets Q4 Crude Germanium Production')),

    (CAT_GJ, ni('https://news.smm.cn/news/104179538',
                '上海有色网', '10-27',
                '诺镍明年起对 Nadezhda 闪速熔炼装置大修 9 个月，或影响 2027—2028 年产量',
                '诺里尔斯克镍业 10 月 26 日表示，明年将开始对 Nadezhda 工厂镍生产链中的关键闪速熔炼装置进行为期 9 个月的大修，预计影响 2027 年、可能延续至 2028 年的主要金属产量。三季度镍产量 6.1 万吨、环比增 41%，前三季度 146,131 吨、同比增 4%；三季度钯 73.6 万盎司、环比增 25%。公司维持 2026 年指引：镍 19.3 至 20.3 万吨、钯 241.5 至 246.5 万盎司、铜 33.6 至 35.6 万吨。')),
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
    ('金鼎', CAT_HY),
    ('华瓯', CAT_HY),
    ('中铝数为', CAT_HY),
    ('铜冠铜箔', CAT_HY),
    ('朱皮特', CAT_ZK),
    ('吉尔摩', CAT_ZK),
    ('Fitzroy', CAT_ZK),
    ('巴西地质', CAT_ZK),
    ('钨粉', CAT_SC),
    ('氢氧化锂', CAT_SC),
    ('铜短缺', CAT_SC),
    ('沪镍', CAT_SC),
    ('诺镍', CAT_GJ),
    ('韩国锌业', CAT_GJ),
    ('长山壕', CAT_GJ),
    ('Ministro', CAT_GJ),
    ('智利计划', CAT_KQ),
    ('Ewoyaa', CAT_MA),
    ('Capstone', CAT_MA),
    ('Perpetua', CAT_MA),
    ('泰国', CAT_ZC),
    ('上期所', CAT_ZC),
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
