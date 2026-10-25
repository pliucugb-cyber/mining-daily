# -*- coding: utf-8 -*-
"""
生成 2026-10-23 矿业资讯速览 index.html（周五）
- 10-22 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-24）回补历史条目
- 换入 10-23 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-22 收盘 + LME 10-22 收盘（10-23 周五 05:30 未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，本批新增 9 宗，不进主页列表
  （由 tmp/add_rights_1023.py 注入月库））
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

REPORT = '2026-10-23'
GRAB = '2026-10-23'
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
                         r'\g<1>2026年10月23日 星期五', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202610/t20261022_10342361.htm',
                '全球矿产资源信息系统', '10-22',
                '巴西铁山稀土矿钻探见矿 111 米，TREO 品位 8.25%',
                'Power Minerals 在巴西铁山（Morro do Ferro）稀土项目钻探从地表开始见矿 111 米，总稀土氧化物（TREO）品位 8.25%，其中 42 米深处见矿 1.2 米、TREO 品位 40.5%、磁性稀土氧化物（MREO）品位 7.73%。同批进展还包括西澳皮尔巴拉温都矿床见矿 12 米、铜品位 0.9%、锌 1.2%、银 2.2 克/吨，该矿床现有矿石资源量 620 万吨、铜品位 1.12%。')),

    (CAT_ZK, ni('https://www.mining.com/liberty-gold-stretches-black-pines-reach-in-idaho',
                'MINING.COM', '10-22',
                'Liberty Gold 爱达荷 Black Pine 钻探扩边，指向 2028 年建设决策',
                'Liberty Gold 公布美国爱达荷州 Black Pine 项目新一轮钻探结果，见矿段向外延伸了矿体范围。公司正推进该项目，目标是在 2028 年作出建设决策，本轮钻探用于支撑资源量与开采设计的更新。',
                orig_title='Liberty Gold stretches Black Pine’s reach in Idaho')),

    (CAT_ZK, ni('https://www.mining.com/fortuna-targets-deeper-lindero-pit-after-gold-hits',
                'MINING.COM', '10-22',
                'Fortuna 智利 Lindero 金矿深部见厚矿段，拟纳入修订储量',
                'Fortuna Mining 公布智利 Lindero 金矿坑底以下深部钻探结果，多个宽厚矿段见矿。分析机构认为，这些结果强化了把坑底以下矿化纳入修订露天坑设计与储量估算的依据，项目服务年限有望延长。',
                orig_title='Fortuna targets deeper Lindero pit after gold hits')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.mining.com/us-permitting-environmental-review-overhaul-could-speed-mine-approvals-but-hurdles-remain',
                'MINING.COM', '10-22',
                '美参议院两党许可改革法案：NEPA 豁免扩容，诉讼期压缩至 150 天',
                '美国参议院 9 月 30 日提出两党许可改革法案，拟扩大《国家环境政策法》（NEPA）分类豁免的适用范围、允许牵头机构合并适用不同类别豁免，并将特定 NEPA 诉讼时限由最长约 6 年压缩至 150 天。法案还拟把《清洁水法》排污许可（NPDES）最长期限由 5 年延长至 10 年，并修订《濒危物种法》磋商时限；发起人希望在 2027 年 1 月 3 日本届国会届满前通过，也有议员主张等 11 月中期选举后再议。',
                orig_title='US permitting: Environmental review overhaul could speed mine approvals, but hurdles remain')),

    (CAT_ZC, ni('https://news.smm.cn/news/104171620',
                '上海有色网', '10-23',
                '《电动汽车动力蓄电池在役检测试验方法》国家标准发布',
                '国家标准《电动汽车动力蓄电池在役检测试验方法》正式发布。该标准针对在用动力蓄电池规定检测试验方法，为在役电池的状态评估与安全管理提供统一技术依据，锂电产业链企业需关注后续实施安排与配套检测能力建设。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104171618',
                '上海有色网', '10-23',
                'WBMS：2026 年 8 月全球精炼铜供应过剩 15.88 万吨',
                '世界金属统计局（WBMS）公布数据显示，2026 年 8 月全球精炼铜市场供应过剩 15.88 万吨。该口径为月度供需平衡统计，反映当月精炼铜产量超过消费量，是判断铜市过剩压力的重要参照。')),

    (CAT_SC, ni('https://news.smm.cn/news/104169007',
                '上海有色网', '10-23',
                '9 月铝矿砂及其精矿进口量同比上升 16.01%',
                '海关总署数据显示，2026 年 9 月中国铝矿砂及其精矿进口量同比上升 16.01%。铝土矿进口保持增长，与国内氧化铝运行产能高位带来的原料需求相呼应，进口来源结构仍是市场关注重点。')),

    (CAT_SC, ni('https://news.smm.cn/news/104168865',
                '上海有色网', '10-23',
                '9 月铜矿砂及其精矿进口量同比下降 3.74%',
                '海关总署数据显示，2026 年 9 月中国铜矿砂及其精矿进口量同比下降 3.74%，铜精矿进口出现回落。原料端供应弹性有限，冶炼厂原料采购与加工费走势仍是影响精炼铜产量的关键变量。')),

    (CAT_SC, ni('https://news.smm.cn/news/104168910',
                '上海有色网', '10-23',
                '9 月锡矿砂及其精矿进口量同比上升 148.23%',
                '海关总署数据显示，2026 年 9 月中国锡矿砂及其精矿进口量同比上升 148.23%，增幅显著。缅甸等主产区供应恢复带动进口放量，锡精矿供应紧张局面阶段性缓解。')),

    (CAT_SC, ni('https://news.metal.com/newscontent/104168847-chinas-rare-earth-magnet-exports-hit-record-in-september-driven-by-backlog-release-and-regulatory-easingsmm-analysis',
                'SMM 国际站', '10-23',
                '中国 9 月稀土永磁出口 6165 吨创纪录，环比增 23%',
                'SMM 分析显示，中国 9 月稀土永磁材料出口量达 6165 吨、环比增 23%，创历史新高。增长主要来自 7 月至 8 月港口积压订单集中清关，而非新增需求；中美谈判推动通关恢复，欧盟「绿色通道」磋商将四季度出口预估上调至约 5700 吨/月，大型磁材企业恢复快于中小厂。',
                orig_title='China’s Rare Earth Magnet Exports Hit Record in September, Driven by Backlog Release and Regulatory Easing')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/38a4dc50e0464bfabeb6eb994cdeba1d.html',
                '长江有色网', '10-22',
                '碳酸锂主力合约大跌 3.58%，远期新增产能压制盘面',
                '长江有色报道，10 月 22 日碳酸锂主力合约大跌 3.58%，盘面提前交易远期新增产能释放预期。弱预期主导下，市场对锂盐价格反弹的持续性存疑，资金情绪转向谨慎。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/c172e195c492400d8edf9970fe29a1e2.html',
                '长江有色网', '10-22',
                '钼铁阴跌至 33.35 万元/吨，全球钼市「换轨」',
                '长江有色报道，钼铁价格阴跌至 33.35 万元/吨。南美贸易流向分化，全球钼市供需与贸易格局正在「换轨」，国内钼系产品价格跟随外盘承压。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsyj/202610/t20261022_10342362.htm',
                '全球矿产资源信息系统', '10-22',
                '必和必拓本财年一季度铜产量 40.07 万吨，同比下降 19%',
                '必和必拓 2026/27 财年第一季度铜产量 40.07 万吨、同比下降 19%，低于市场预期的 42.36 万吨和上财年同期的 49.4 万吨。减产主因智利埃斯康迪达铜矿事故停产、南澳卡拉帕蒂纳铜矿传送带断裂；同期西澳铁矿石产量 7190 万吨，铁矿石销售价格下跌 9% 至 76.27 美元/吨（湿）。')),

    (CAT_HY, ni('https://news.smm.cn/news/104168898',
                '上海有色网', '10-23',
                '英美资源集团第三季度铜产量同比下降 5%',
                '英美资源集团（Anglo American）公布第三季度生产报告，铜产量同比下降 5%。在铜价高位运行的背景下，产量回落将影响其铜板块年度目标的完成度，市场关注四季度矿山运营恢复情况。')),

    (CAT_HY, ni('https://news.smm.cn/news/104169342',
                '上海有色网', '10-23',
                '墨西哥集团：金属涨价推高利润，下调铜产量指引',
                '墨西哥集团（Grupo México）表示，金属价格上涨推高了公司利润，但同时下调全年铜产量指引。该公司为全球重要铜生产商，旗下拥有秘鲁与墨西哥多座大型铜矿，产量指引下调对今明两年铜精矿供应预期形成扰动。')),

    (CAT_HY, ni('https://news.metal.com/newscontent/104173952-flash-mmg-resets-2026-mine-outlook-as-las-bambas-targets-the-top-end',
                'SMM 国际站', '10-23',
                '五矿资源调整 2026 年指引，拉斯邦巴斯目标指向区间上沿',
                '五矿资源（MMG）调整 2026 年矿山产量指引，旗下秘鲁拉斯邦巴斯（Las Bambas）铜矿目标指向指引区间上沿。公司称该矿运营改善，全年产量有望达到指引上限。',
                orig_title='MMG Resets 2026 Mine Outlook as Las Bambas Targets the Top End')),

    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/1020/62204.html',
                '中国有色金属工业协会', '10-20',
                '紫金矿业保有铜资源量约 1.1 亿吨、金 4610 吨，分列全球第三、第五',
                '紫金矿业 10 月 17 日在福建上杭召开第八次科技大会，公司当前保有铜资源量约 1.1 亿吨、金资源量 4610 吨，分列全球第三、第五位。「十四五」期间自主勘查新增铜资源量 2346 万吨，吨铜勘查成本 71 元，约为行业平均水平的三分之一；自研「震旦」三维激电系统探测深度超 1500 米，已在 40 余个勘查区应用。')),

    (CAT_HY, ni('https://news.smm.cn/news/104174001',
                '上海有色网', '10-23',
                '中钨高新子公司拟投 1.31 亿元实施 PCB 钻针棒提质增效项目',
                '中钨高新公告，子公司拟投资 1.31 亿元实施 PCB 钻针棒提质增效项目。公司前三季度净利润同比大幅增长，硬质合金与精密工具板块的产能与产品结构升级同步推进。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-23/1225615377.PDF',
                '巨潮资讯网', '10-23',
                '海南矿业更新发行股份购买资产报告书（修订稿）',
                '海南矿业披露发行股份及支付现金购买资产并募集配套资金暨关联交易报告书（修订稿），同步更新审核问询函回复、备考审阅报告及修订说明。交易仍在审核推进中，标的资产作价与业绩承诺安排以最终公告为准。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-23/1225617077.PDF',
                '巨潮资讯网', '10-23',
                '赤峰黄金控股股东及实际控制人变更，H 股配售同步完成',
                '赤峰黄金公告，股东协议转让公司股份已完成过户登记，并按特别授权配售新增发行 H 股。上述事项完成后，公司控股股东及实际控制人发生变更，控制权结构进入新阶段。',
                embed='pdf')),

    (CAT_MA, ni('https://news.metal.com/newscontent/104168925-chinese-6billion-battery-investment-in-morocco-reshapes-eu-lithium-demand-amid-tariff-shifts',
                'SMM 国际站', '10-23',
                '中企在摩洛哥投资 60 亿美元建电池厂，重塑欧盟锂需求路径',
                'SMM 国际站报道，中国企业已宣布在摩洛哥投资 60 亿美元建设电池与电动车零部件工厂，当地生产的整车不受欧盟对中国产电动车加征关税影响。摩洛哥 2024 年生产整车 56 万辆，其中电动车仅约 5 万辆；欧盟现行对中国产电动车加征最高 35% 附加税。',
                orig_title='Chinese $6Billion Battery Investment in Morocco Reshapes EU Lithium Demand Amid Tariff Shifts')),

    (CAT_MA, ni('https://www.mining.com/mining-ma-wave-set-to-lift-juniors-investor-predicts',
                'MINING.COM', '10-23',
                '投资人预计矿业并购潮将惠及初级勘探公司',
                '投资人 Michael Gentile 预计，大型矿企为寻求增长将加大对初级勘探公司的并购力度，矿业并购潮有望抬升初级公司估值。他认为大型矿企自有项目储备不足以支撑产量增长，收购成为补足资源的主要路径。',
                orig_title='Mining M&A wave set to lift juniors, investor predicts')),

    (CAT_MA, ni('https://www.mining.com/southern-copper-weighs-680m-cuajone-mine-expansion',
                'MINING.COM', '10-22',
                '南方铜业评估 6.80 亿美元 Cuajone 铜矿扩建',
                '南方铜业（Southern Copper）正评估秘鲁 Cuajone 铜矿的选矿升级扩建，投资规模约 6.80 亿美元（$680 million）。项目拟提升铜与钼产量，规划年产钼 1400 吨目标，最终投资决定尚待董事会批准。',
                orig_title='Southern Copper weighs $680M Cuajone mine expansion')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/ai-boom-could-overwhelm-metals-supply-woodmac',
                'MINING.COM', '10-23',
                '伍德麦肯兹：AI 与电力需求或压垮金属供应',
                '伍德麦肯兹（Wood Mackenzie）称，全球在跟踪的数据中心项目已超 250 吉瓦、为一年前的三倍以上，预计 AI 相关用电量 2025—2030 年增长五倍、2035 年突破 1000 太瓦时。输电线路、变电站与专用发电所需金属量可达数据中心本身的 3—4 倍；铜价已创 14,759 美元/吨纪录，美国以外市场精炼铜缺口约 45 万吨，2026 年智利铜产量预计下降 5.2%。',
                orig_title='AI boom could overwhelm metals supply: WoodMac')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104173948-flash-strike-countdown-begins-at-tecks-highland-valley-copper-putting-molybdenum-target-at-risk',
                'SMM 国际站', '10-23',
                '泰克资源高地谷铜矿罢工倒计时，最早 10 月 24 日启动',
                '泰克资源（Teck Resources）确认收到加拿大不列颠哥伦比亚省高地谷铜矿（Highland Valley Copper）工会的罢工通知，罢工最早可于 10 月 24 日启动，谈判仍在进行、生产暂未中断。该矿 2026 年钼产量指引为 1,500 至 1,800 吨，上半年已产约 700 吨，长时间停产将影响剩余产量安排。',
                orig_title='Strike Countdown Begins at Teck’s Highland Valley Copper, Putting Molybdenum Target at Risk')),

    (CAT_GJ, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/1020/62213.html',
                '中国有色金属工业协会', '10-20',
                '联合国启动关键矿产国家支持机制，六国入选首批名单',
                '联合国在 9 月纽约气候峰会上启动关键能源转型矿产国家支持机制，印度尼西亚、赞比亚、几内亚、津巴布韦、马达加斯加和尼日利亚 6 国入选首批名单。机制不提供直接贷款，而以政策设计、法律框架、环境与社会标准建设为抓手，推动 6 国从原矿出口转向本地加工；刚果（金）被列入后续 15 国扩展名单。')),
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
