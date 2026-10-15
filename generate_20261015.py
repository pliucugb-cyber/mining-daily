# -*- coding: utf-8 -*-
"""
生成 2026-10-15 矿业资讯速览 index.html（周四）
- 10-14 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-16）回补历史条目
- 换入 10-15 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-14 收盘 + LME 10-14 收盘（10-15 05:30 国内未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，tmp/add_rights_1015.py 注入），不进主页列表
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

REPORT = '2026-10-15'
GRAB = '2026-10-15'
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
                         r'\g<1>2026年10月15日 星期四', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202610/t20261014_10335386.htm',
                '全球矿产资源信息系统', '10-14',
                '西澳州朱皮特稀土矿首次估算推定资源量',
                '全球矿产资源信息系统援引矿业周刊报道，科里蒂卡（Critica）宣布西澳州朱皮特（Jupiter）稀土矿资源量更新，首次估算推定矿石资源量 1.6 亿吨、TREO 品位 0.17%，其中镨钕镝铽等磁体稀土占 TREO 的 25%；朱皮特矿床推测矿石资源量 17 亿吨、TREO 品位 0.17%，公司正开展概略研究。')),

    (CAT_ZK, ni('https://www.mining.com/hycroft-hits-bonanza-gold-grades-at-nevada-mine',
                'MINING.COM', '10-15',
                'Hycroft 内华达金矿钻遇迄今最高金品位',
                'MINING.COM 报道，Hycroft Mining 在内华达州 Vortex 矿段的钻孔 H26D-6175A 自 416.5 米见矿 19.6 米、金品位 30.49 克/吨、银 1726.72 克/吨，为公司迄今最高金品位；Vortex 与 Brimstone 高品位域探明加控制资源量 1810 万吨、银 154.71 克/吨与金 0.512 克/吨。',
                orig_title='Hycroft hits bonanza gold grades at Nevada mine')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474544',
                '中国有色金属报', '10-13',
                '铜冠建安参与编制的行业标准《道路用固废基胶凝材料》发布',
                '中国有色金属报报道，安徽铜陵有色铜冠建安建材公司参与编制的行业标准《道路用固废基胶凝材料》正式获批发布，并于 2026 年 9 月 1 日实施，填补国内道路工程固废基胶凝材料领域的标准化空白，将拓宽冶金、钢铁、化工固废资源化消纳渠道，降低道路基层水泥用量。')),

    (CAT_ZC, ni('https://www.ccmn.cn/news/ZX018/202610/ef53ff14c5de46e5a208e1e41398caba.html',
                '长江有色网', '10-14',
                '越南拟对 17 种关键矿产限制初级产品出口',
                '长江有色金属网报道，越南工贸部完成《允许出口的国内战略及重要矿产清单及加工级别》总理决定草案编制，10 月 8 日移交司法部审查、尚未正式生效；草案公布后锡价一度拉升，12 日长江现货 1# 锡上涨 6000 元/吨，但 14 日现货锡价大跌 8500 元/吨至 388750 元/吨，显示矿端收紧预期尚未转化为实际供给缺口。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.mining.com/global-copper-surplus-to-more-than-triple-by-2027-icsg',
                'MINING.COM', '10-14',
                'ICSG：全球精炼铜过剩到 2027 年将增两倍以上',
                'MINING.COM 报道，国际铜研究小组（ICSG）预测全球精炼铜过剩量将从 2026 年的 10.4 万吨扩大至 2027 年的 36.8 万吨；2026 年全球精炼铜产量预计仅增 0.4%、2027 年加速至 3.4%，精炼铜消费 2026、2027 年分别增长 1.5% 和 2.5%，中国占全球消费的 59%。',
                orig_title='Global copper surplus to more than triple by 2027: ICSG')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104157698-lme-zinc-inventory-surges-to-144100-mt-driven-by-singapore-and-hong-kong-stocks',
                'SMM 国际站', '10-15',
                'LME 锌库存连续三日大增，升至 14.41 万吨',
                'SMM 国际站快讯称，截至 10 月 13 日 LME 锌锭库存连续三日显著累积至 144100 吨，增量主要来自新加坡（+17150 吨）、中国香港（+400 吨）与巴生港（+75 吨），高雄港去库 350 吨。',
                orig_title='LME Zinc Inventory Surges to 144,100 MT, Driven by Singapore and Hong Kong Stocks')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/ecd4b66ebe654223b31f511c2f3a7731.html',
                '长江有色网', '10-15',
                '伦铝三连跌创年内低点，伦锡大跌 2.3%',
                '长江有色金属网报道，10 月 14 日 LME 基本金属期货全线下跌，伦铝三连跌并创下年内低点，伦锡大跌 2.3%；市场关注美国 9 月 CPI 数据对美联储加息路径的影响。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/5cd912211efd4708877f79f13a88d531.html',
                '长江有色网', '10-14',
                '锑价单日下跌 4000 元/吨至 96000 元/吨',
                '长江有色金属网报道，10 月 14 日长江现货 1# 锑均价报 96000 元/吨，较上一交易日下跌 4000 元/吨；贸易货源释放叠加需求偏弱令现货报价明显下探，市场交投情绪转冷。')),

    (CAT_SC, ni('https://news.smm.cn/news/104157571',
                '上海有色网', '10-15',
                '美国 9 月 CPI 高于预期，金属内外盘全线下跌',
                '上海有色网报道，因美国 9 月 CPI 高于预期，隔夜内盘基本金属全线下跌，沪铜跌 0.81%、沪铝跌 0.96%、沪锡跌 3.39%、沪镍跌 0.64%；外盘 LME 基本金属同步走低，伦铝跌 1.65%、伦锡跌 3%；COMEX 白银跌 6.26%，沪银主连跌 6.29%。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474566',
                '中国有色金属报', '10-13',
                '府谷镁产业从原材料基地向镁基新材料制造高地转型',
                '中国有色金属报报道，陕西府谷县现有镁及镁合金生产企业 34 户，2025 年原镁产量 55.77 万吨、连续 14 年位居全球原镁产量首位，全县镁产业集群总产值突破 400 亿元；当地依托半焦与镁耦合循环模式，向镁合金汽车零部件、安全帽、自行车架等深加工产品延伸。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474543',
                '中国有色金属报', '10-13',
                '西部矿业青海铜业入选 2026 年青海省先进级智能工厂',
                '中国有色金属报报道，青海省工业和信息化厅公布 2026 年度先进级智能工厂认定名单，西部矿业集团旗下青海铜业阴极铜生产一体化协同智能工厂入选；其电解车间核心设备自动化、数字化及联网率达 95%，电解生产工艺优化为「9 天 2 周期」。')),

    (CAT_HY, ni('https://www.mining.com/equinox-gold-output-jumps-34-after-orla-merger',
                'MINING.COM', '10-15',
                'Equinox 与 Orla 合并后三季度黄金产量增 34%',
                'MINING.COM 报道，Equinox Gold 与 Orla Mining 合并后三季度黄金产量 237019 盎司、较上一季度增 34%，黄金销量增 39.6% 至 248484 盎司；前三季度累计产金 611483 盎司，全年指引维持 87 万至 92 万盎司，公司预计合并后年产量可达 110 万盎司。',
                orig_title='Equinox gold output jumps 34% after Orla merger')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-15/1225605544.PDF',
                '巨潮资讯网', '10-15',
                '盛达资源拜仁达坝银多金属矿 90 万吨/年技改通过节能审查',
                '巨潮资讯网披露，盛达资源控股子公司内蒙古银都矿业收到克什克腾旗发改委《拜仁达坝银多金属矿 90 万吨/年采矿技改工程项目节能审查意见》，原则同意该项目节能报告；该矿区保有矿石量 803.4 万吨、银金属量 1433 吨、平均品位 221.96 克/吨。',
                embed='pdf')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-13/1225600568.PDF',
                '巨潮资讯网', '10-13',
                '金钼股份前三季度净利润 29.94 亿元，同比增 30.94%',
                '巨潮资讯网披露业绩快报，金钼股份 2026 年前三季度实现营业总收入 124.46 亿元、同比增 14.34%，利润总额 39.74 亿元、同比增 32.25%，归属于上市公司股东的净利润 29.94 亿元、同比增 30.94%，主要因各类钼产品价格较上年同期上涨。',
                embed='pdf')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/bhp-averts-strike-at-worlds-biggest-copper-mine-2',
                'MINING.COM', '10-14',
                '必和必拓埃斯康迪达铜矿达成初步协议避免罢工',
                'MINING.COM 报道，必和必拓与智利埃斯康迪达铜矿监督人员工会达成初步协议，避免全球最大铜矿停产，若工会成员投票否决则于 10 月 15 日上午开始罢工；GEM 咨询评估显示埃斯康迪达约 7.5% 的产量面临风险，El Teniente 以 9% 居首，智利大型铜矿平均有 5.2% 的产量易受扰动。',
                orig_title="BHP averts strike at world's biggest copper mine")),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104155269-centinela-strike-could-cut-november-copper-output-by-half-unions-say',
                'SMM 国际站', '10-15',
                'Centinela 铜矿罢工或使 11 月产量减半',
                'SMM 国际站援引矿业周刊报道，智利 Antofagasta 旗下 Centinela 铜矿自 10 月 7 日起罢工，工会称若停工持续，11 月铜产量可能减少约 50%；代表该矿过半关键岗位工人的两个工会此前拒绝了政府调解下的进一步谈判。',
                orig_title='Centinela Strike Could Cut November Copper Output by Half, Unions Say')),

    (CAT_GJ, ni('https://www.mining.com/deep-sea-mining-faces-surprise-risk-of-rocks-catching-fire',
                'MINING.COM', '10-14',
                'USGS：深海硫化物矿石暴露空气后可自燃',
                'MINING.COM 报道，美国地质调查局（USGS）研究发现，2022 年采自俄勒冈—加州外海 Escanaba 海槽的 57 件热液岩样中有 2 件在实验室处理时自燃，反应温度超过 100°C；研究将不稳定的纳米晶白铁矿列为可能原因，提示深海采矿需评估矿石稳定性并防范船上火灾风险。',
                orig_title='Deep-sea mining faces surprise risk of rocks catching fire')),

    (CAT_GJ, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474551',
                '中国有色金属报', '10-13',
                'Bikita 矿业津巴布韦道路修缮项目开工',
                '中国有色金属报报道，当地时间 10 月 7 日上午，中矿资源旗下 Bikita 矿业在津巴布韦的索塞拉购物中心至恩丹巴尼道路修缮项目正式开工；道路全长 4 公里、串联沿线 8 个村落、惠及约 400 户居民，连通穆塔雷—马斯温戈干线公路。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/electra-battery-materials-partners-with-wmc-to-finance-ontario-cobalt-refinery',
                'MINING.COM', '10-14',
                'Electra 与 WMC 签署五年合作，为安大略钴精炼厂融资',
                'MINING.COM 报道，Electra Battery Materials 与大宗商品贸易商 WMC Group AG 签署为期五年的营运资金与商业合作条款书，为安大略省 Temiskaming Shores 的北美首座硫酸钴精炼厂采购钴原料，并由 WMC 作为对应电池级硫酸钴产品的买方与独家销售代理；Electra 市值 7380 万加元。',
                orig_title='Electra Battery Materials partners with WMC to finance Ontario cobalt refinery')),

    (CAT_MA, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202610/t20261014_10335387.htm',
                '全球矿产资源信息系统', '10-14',
                '马来西亚最高元首溢价购入南盟矿业 2.25% 股份',
                '全球矿产资源信息系统援引路透社报道，新加坡上市铁矿生产商南盟矿业（SAM）董事经理 Pek Kok Sam 以每股 0.425 新元、较 10 月 12 日收盘价溢价 11.84%，向马来西亚最高元首易卜拉欣转让 2.25% 股份，交易额 610 万新元（476 万美元）；该公司持有马来西亚稀土矿商 MCRE 资源 40% 股权。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-13/1225601284.PDF',
                '巨潮资讯网', '10-13',
                '北方稀土预计前三季度净利润同比增逾 135%',
                '巨潮资讯网披露，北方稀土预计 2026 年前三季度实现归属于母公司所有者的净利润 36.2 亿元至 36.8 亿元，同比增加 134.95% 到 138.84%；扣除非经常性损益后的净利润 36.3 亿元至 36.9 亿元，同比增加 166.64% 到 171.04%。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-14/1225603992.PDF',
                '巨潮资讯网', '10-14',
                '中钨高新预计前三季度净利润同比增逾 219%',
                '巨潮资讯网披露，中钨高新预计 2026 年前三季度归属于上市公司股东的净利润 29 亿元至 31 亿元，重述后同比增长 219% 到 241%；业绩增长主要因报告期内钨精矿均价同比上涨，钨精矿及粉末产品盈利水平提升。',
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
