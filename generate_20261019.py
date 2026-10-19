# -*- coding: utf-8 -*-
"""
生成 2026-10-19 矿业资讯速览 index.html（周一）
- 10-18 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-20）回补历史条目
- 换入 10-18 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-16 收盘 + LME 10-16 收盘（10-19 周一 05:30 未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，tmp/add_rights_1018.py 注入），不进主页列表
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

REPORT = '2026-10-19'
GRAB = '2026-10-19'
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
                         r'\g<1>2026年10月19日 星期一', html)
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
    (CAT_ZK, ni('https://news.smm.cn/news/104162986',
                '上海有色网', '10-19',
                '2026 年全球有色金属勘查预算同比增三成，创十年最大增幅',
                '自然资源部援引标普全球市场财智调查数据，2026 年全球有色金属矿产（不含油气、煤）勘查投资较 2025 年增长三成，为经历三年萎缩后 10 年来最大增幅。金、铜仍是主要勘查矿种，弥补了锂矿勘查投资下降的缺口；绿地勘查占比回升，拉丁美洲、加拿大、澳大利亚仍是预算最集中的地区。2026 年预算为该项调查开展以来第三高，仅次于 2012 年的 205 亿美元和 2011 年的 172 亿美元。')),

    (CAT_ZK, ni('https://news.smm.cn/news/104162997',
                '上海有色网', '10-19',
                'BDO：澳交所前 50 家矿企握半数现金，勘查投入仅占全澳二季度 27%',
                '咨询机构 BDO 对 750 家澳大利亚勘探公司的资金使用分析显示，截至 6 月底矿企 130.4 亿澳元存款中有一半由前 50 家企业持有，而二季度这 50 家勘查投资 2.39 亿澳元，仅占全澳 10.5 亿澳元勘查投资的 27%，勘查投资占其存款不足 10% 的企业比例达 68%。勘查投资/现金比由一季度的 12% 降至二季度的 9%；西非资源公司期末现金 8.76 亿澳元，当季勘查投入仅 14 万澳元、占可用资金 0.02%。BDO 认为资金正转向并购、项目开发与整合，而非增加钻探。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/jqzs/2026/1015/62168.html',
                '中国有色金属工业协会', '10-15',
                '9 月中国有色金属产业景气指数 42.7，环比降 3.8 个百分点',
                '中国有色金属工业协会监测显示，2026 年 9 月有色金属产业景气指数 42.7，较上月下降 3.8 个百分点，仍处「正常」区间中部；先行指数 88.3、降 1.4 个百分点，一致指数 77.0、降 3.8 个百分点。12 项构成指标中仅商品房销售面积指数处于「偏冷」区间。协会指出，9 月行业主要产品产量保持增长、固定资产投资持续下滑、进出口分化，规模以上企业效益延续大幅增长。')),

    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/1015/62176.html',
                '中国有色金属工业协会', '10-15',
                '工业硅总库存逼近 90 万吨，成本刚性压缩价格下行空间',
                '10 月初国内四大主产区工业硅总产量 4.73 万吨，环比增 810 吨、同比减 6850 吨，增量主要来自新疆；同期多晶硅周产量回落 0.45 万吨至 2.25 万吨，有机硅周产量 4.25 万吨、环比降 6.4%。截至 10 月 8 日社会库存 43.2 万吨、厂库 20.5 万吨、下游原料库存 25.58 万吨，总库存 89.28 万吨。分析认为四季度供需边际转弱，但电价与碳质还原剂涨价推高成本，价格下行空间被压缩。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474500',
                '中国有色金属报', '10-12',
                '机构：四季度铝价有支撑但上行空间受限，三大库存同步去化',
                '分析称，国外供应扰动未完全消退、国内外铝库存持续去化叠加「金九银十」旺季，铝价下方支撑较强；但国内需求修复温和、库存降幅收窄，市场对明年供应恢复的预期升温，上行驱动减弱。最新 LME 铝库存降至 24.03 万吨、上期所库存 28.87 万吨、国内社会库存 64.2 万吨；9 月国内铝加工企业综合开工率 61.2%，环比升 1.4 个百分点；8 月铝材及铝制品出口 55.21 万吨，同比增 15.31%。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474501',
                '中国有色金属报', '10-12',
                '科法斯：2035 年前铜、镍价格可能翻倍，三种金属缺口约占需求一成',
                '科法斯（Coface）10 月 7 日发布的工业金属报告称，受建筑、能源转型与电气化需求推动，铜、镍价格未来 10 年可能翻倍；到 2035 年铝、铜、镍的供应缺口平均约占需求的 10%。报告预计铜供应年均仅增 1%、镍增 1.5%、铝增 0.4%，而需求年均增速约 1.8%。测算显示精炼铜缺口到 2035 年可能由 150 万吨扩大至 650 万吨（约需求的 11%），净零情景下缺口可达 17%；铝缺口为 500 万至 1500 万吨。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474499',
                '中国有色金属报', '10-12',
                '机构：本轮金价下跌更像牛市中的深度回调，央行已连续 23 个月增持',
                '10 月 7 日现货黄金下跌 1.3% 收报 4109.78 美元/盎司，盘中最低触及 4066.30 美元/盎司，为 8 月 5 日以来最低水平。分析认为，美国 10 年期国债实际收益率升至 2.85%、美联储年内仍有加息可能、美国经济数据偏强，共同压制金价；但 9 月末我国黄金储备 7747 万盎司、环比增 74 万盎司，已连续 23 个月增持，本轮下跌更可能是牛市途中的深度回调。')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104162867-30000-tonnes-alumina-traded-at-382mt-fob-india-shipment-in-november-2026',
                'SMM 国际站', '10-16',
                '海外氧化铝现货：3 万吨印度货 382 美元/吨 FOB 成交，11 月装运',
                'SMM 报道，2026 年 10 月 16 日 3 万吨氧化铝以 382 美元/吨 FOB 印度成交，船期为 11 月。该笔为 10 月中旬公开的又一笔氧化铝现货招标成交，反映海外氧化铝现货流动性仍在延续。',
                orig_title='30,000 Tonnes Alumina Traded at $382/mt FOB India, Shipment in November 2026')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.metal.com/en/newscontent/104162707-chinas-copper-cathode-rod-production-rebounds-2959-wow-as-industries-return-to-normal-post-holiday',
                'SMM 国际站', '10-16',
                '节后铜杆企业开工率环比回升 29.59 个百分点，低位库存触发集中补库',
                'SMM 调研显示，本周国内主要铜杆企业开工率环比回升 29.59 个百分点。节后生产逐步恢复正常，成品库存此前处于低位，企业集中补库带动开工率快速反弹；线缆、漆包线等终端行业生产节奏同步恢复，开工率均有不同程度回升。',
                orig_title="China's Copper Cathode Rod Production Rebounds 29.59% WoW as Industries Return to Normal Post-Holiday")),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474573',
                '中国有色金属报', '10-13',
                '中铁资源新鑫公司完成粉矿仓技改，9 月选矿处理量达计划 127.05%',
                '中铁资源新鑫公司选矿厂粉矿仓投用逾 10 年，仓壁挂料、矿料板结导致频繁堵料断料，公司采用「两仓错峰运行、不停机清仓」方案完成技改，一仓保供、一仓清理，保障磨机连续运转。技改修复闲置水平钻并自主铺设 120 米清水管路，以机械破碎板结矿料配合高压水疏导。9 月选矿处理量完成月度计划的 127.05%。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474491',
                '中国有色金属报', '10-12',
                '贵州华仁以激光清理替代人工打磨阳极导杆，年综合效益超 200 万元',
                '贵州华仁新材料引入阳极导杆激光智能清理系统替代人工角磨机打磨，系统集成激光清洗、智能定位、安全防护、智能控制与收尘模块，可与现有悬链生产线联动运行。经实际测算，单根导杆清理节约成本约 5 元，按日均清理 500 根计年省维修成本近 80 万元；接触压降降低后年节电约 250 万千瓦时、节约电费超 150 万元，综合年效益超 200 万元，折合年节约标准煤约 350 吨。')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/1013/62157.html',
                '中国有色金属工业协会', '10-13',
                '从中国国际矿业大会看全球矿业调整：融资与并购激增，勘查支出连降四年',
                '第 28 届中国国际矿业大会发布的全球矿业发展报告显示，2025 年全球矿业融资额增长 1 倍以上至 214.30 亿美元，并购额增长 150.40% 至 735.20 亿美元，同期全球矿产勘查支出连续第 4 年下降。大会发布《矿业绿色发展天津宣言》，并推出 10 项绿色矿山建设国家标准与首部固体矿产绿色勘查国家标准，自 10 月 1 日起施行。资源国普遍提出本地加工诉求，供应链布局向非洲、中亚、南太平洋等区域延伸。')),

    (CAT_GJ, ni('https://www.mining.com/minings-future-hinges-on-global-cooperation-report',
                'MINING.COM', '10-18',
                '报告：2050 年前矿业走向取决于未来几年的合作选择，三种情景差异显著',
                'Systemiq 与 ERM 受戈登与贝蒂·摩尔基金会资助、联合国际矿业与金属理事会（ICMM）发布的报告，设定了 2050 年前矿业三种情景。最有利的「飞轮」情景下，2050 年铜需求提高 18%，同时耗水减少 35%、矿山数量减少 18%、森林砍伐减少 25%；对立的「分裂」情景则需多 30% 的铜、耗水增 70%、矿山增 25%、砍伐增 40%。报告基于 20 余位专家访谈与 16 位行业领袖问卷调查。',
                orig_title="Mining's future hinges on global cooperation: report")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-17/1225608720.PDF',
                '巨潮资讯网', '10-17',
                '山东黄金拟回购 3 亿至 4 亿元股份用于注销，价格上限 48.57 元/股',
                '山东黄金 10 月 16 日董事会审议通过回购方案，拟以集中竞价方式回购 3 亿元（含）至 4 亿元（含），价格不超过 48.57 元/股，资金来源为自有及自筹资金。回购股份将全部用于注销并减少注册资本，期限为股东会审议通过后 12 个月内；方案尚需股东会以特别决议审议通过。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-19/1225610022.PDF',
                '巨潮资讯网', '10-19',
                '上海誉升同风以 27.54 元/股部分要约收购艾艾精工 10.01% 股份',
                '艾艾精工公告，上海誉升同风金属材料科技有限公司拟以现金方式部分要约收购公司 1308.04 万股，占总股本 10.01%，要约价格 27.54 元/股，要约期为 2026 年 10 月 21 日至 11 月 20 日，预受要约申报编号 770010。要约收购报告书已于 10 月 19 日刊登。',
                embed='pdf')),
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
