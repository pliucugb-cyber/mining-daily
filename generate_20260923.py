# -*- coding: utf-8 -*-
"""
生成 2026-09-23 矿业资讯速览 index.html
- 09-22 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-23）回补历史条目
- 换入 09-21~09-22 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-22 收盘 + LME 09-22 收盘（东财日K末点=09-22，卡片=走势图口径），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层，不进主页列表（ky.mnr 09-22 有新公告，另行注入）
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信
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

REPORT = '2026-09-23'
GRAB = '2026-09-23'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
# 站点名固定「矿业资讯速览」，标题统一写成「矿业资讯速览 · YYYY-MM-DD」。
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月23日 星期三', html)
assert _n_badge == 1, 'date-badge 替换次数异常: %d' % _n_badge
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-09-\d{2} 更新',
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
# 单位同为「元/吨」= 国内盘分组单位 -> 走 unit_class 隐藏重复单位（2026-09-13 契约）
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
    # ---------- 💼 矿权交易 ----------
    (CAT_KQ, ni('https://www.mining.com/sunshine-silver-mining-boosts-mineral-rights-position-in-idaho-by-60',
                'MINING.COM', '09-21',
                '美国银谷矿权整合提速 Sunshine Silver 矿权面积扩大 60%',
                'Sunshine Silver Mining & Refining（NYSE: SSMR）宣布，在爱达荷州北部银谷（Silver Valley）新增约 14,100 英亩矿权，使其在该区的合并矿权面积扩大至约 38,000 英亩、增幅 60%，成为这一美国历史最高产银矿区的最大矿权持有者。公司同步启动为期数年、总进尺 45,000 米的地表勘探钻探，首批锁定 East Sunshine、Rock Creek、Pine Creek 3 个可钻靶区，计划今年四季度开钻。公司 6 月完成 2.7 亿美元美国 IPO，当前市值约 23 亿美元。',
                orig_title='Sunshine Silver Mining boosts mineral rights position in Idaho by 60%')),

    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260922_2938952.html',
                '自然资源部', '09-22',
                '我国战略找矿成果喜人 安徽茶亭铜金矿等达超大型规模',
                '自然资源部党组书记、国家自然资源总督察刘国洪 9 月 22 日在国新办「开局起步‘十五五’」系列主题新闻发布会上介绍，1—8 月全国探矿权出让成交金额同比增长 133.5%，石油可采储量净增近 7000 万吨、天然气 6100 亿立方米，安徽茶亭铜金矿、贵州猪拱塘铅锌矿资源量达超大型规模。「十五五」期间将统筹战略性矿产资源探、产、供、储、销，加快实施新一轮找矿突破战略行动。')),
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474081',
                '中国有色金属报', '09-17',
                '我国面向全球首次发布「智能填图」系统',
                '9 月 11 日，自然资源部在 2026（第二十八届）中国国际矿业大会上面向全球首次正式发布「智能填图（AI-GeoMapping）」系统。该系统由中国地质调查局自主研发，覆盖智能预研、采集、成图、编图全流程，可自动建立地质格架、划分填图单位、识别地质界线并生成野外路线图、剖面图、柱状图等专业图件；内置全球 1∶500 万、全国陆域 1∶100 万至 1∶5 万等多尺度地质图与 150 余个数据处理解释算法。系统已在青海、西藏、新疆等省区近百个 1∶5 万图幅试用，并在摩洛哥、沙特、老挝、秘鲁等国推广，地质体识别精度总体超 90%，编图效率较传统方法提升 50% 以上。')),
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474198',
                '中国有色金属报', '09-22',
                'Auro Metals 厄瓜多尔铜金矿项目单孔连续见矿 905 米',
                '9 月 15 日，Auro Metals Inc. 的 Santa Barbara 铜金矿项目一期钻探再获突破：最新 3 个钻孔全部稳定见矿，核心钻孔 DSB-68 连续见矿 905.22 米，平均金品位 0.60 克/吨、铜品位 0.12%，创项目勘探纪录，且至 1282 米终孔仍见矿。DSB-70 钻获 262.5 米连续矿化段、平均金品位 0.71 克/吨，其中深部 100.45 米矿段金品位突破 1.01 克/吨。一期钻探累计完成 22 个钻孔、总进尺 11047.35 米，二期 2 万米深部钻探即将全面启动。项目位于厄瓜多尔东南部萨莫拉铜金成矿带，持有 52 平方公里勘探权，探明加推断资源量合计 2.35 亿吨，含金 128 吨、铜 22.4 万吨。')),
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260922_10320702.htm',
                '全球矿产资源信息系统', '09-22',
                '西澳州里奇利铜矿初步钻探完成 见矿 14 米铜品位 2.49%',
                '据矿业新闻网报道，博亚资源公司（BOA Resources）在西澳州莫奇森地区里奇利（Ricci Lee）铜矿项目的初步钻探证实，远景区南部铜矿化连续，钻孔在 122 米深处见矿 14 米、铜品位 2.49%，其中包括 4 米厚、品位 4.6% 的矿体。公司已完成 46 个反循环钻孔，编录时还发现银矿化。里奇利位于萨杜纳（Thaduna）矿床西南 2 公里，后者矿石资源量 410 万吨、铜品位 2.5%、即铜金属量 10.3 万吨。整个钻探计划包括 138 个孔、总进尺 13086 米，这也是该项目 10 年来首次钻探。')),
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474209',
                '中国有色金属报', '09-22',
                '中铝国际中勘院新技术实现矿山边坡稳定性精确评价',
                '中铝国际所属中国有色金属工业昆明勘察设计研究院有限公司提出的三维结构面抗剪强度代表性试样选取方法，攻克野外快速判别及多尺度试验装备等核心技术瓶颈，推动我国工程岩体边坡稳定性评价从经验估算转向精确获取。项目团队首创三维结构面抗剪强度代表性试样选取方法，参与发明矿山边坡岩体潜在滑移面野外快速判别方法、基于三维激光扫描的节理规模快速精细取值方法，并研制世界首套单台多尺寸抗剪强度试验装备。相关技术已在金鼎兰坪铅锌矿、大平掌铜矿、江铜德兴铜矿等矿山应用。')),

    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260922_2938953.html',
                '自然资源部', '09-22',
                '「十五五」找矿部署：多找矿、找大矿、找富矿',
                '自然资源部新闻发言人、副部长周星在 9 月 22 日国新办发布会上介绍，「十五五」时期我国重要矿产资源需求仍将保持刚性增长，自然资源部将继续实施新一轮找矿突破战略行动：组织实施国家地质填图计划，推动陆域 1∶5 万区域地质调查覆盖率提升至 51%、重要成矿区带矿产地质调查覆盖率提升至 66%；组织开展「找矿大会战行动」，聚焦石油、铁、铜、铝等紧缺矿产，兼顾稀土等优势矿产，部署一批重点勘查开采项目，力争新发现一批大中型矿产地和油气田。')),
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474080',
                '中国有色金属报', '09-17',
                '《矿业绿色发展天津宣言》发布 提出 10 方面倡议',
                '9 月 10 日，《矿业绿色发展天津宣言》在矿业国际合作部长论坛暨 2026（第二十八届）中国国际矿业大会开幕式上发布。《宣言》围绕「合作共赢 绿色智能」主题，从绿色发展、资源效率、低碳转型、技术创新、数智融合、标准互认、贸易投资、民生福祉、协同创新、共同发展 10 个方面提出倡议和行动，包括推行绿色勘查和绿色矿山建设、促进人工智能与数字孪生等新技术与矿业融合、发展智能矿山、推进绿色矿产国际合作、欢迎各方加入《绿色矿产国际经贸合作倡议》等。')),
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474005',
                '中国有色金属报', '09-17',
                '《矿产资源对外合作可持续发展自律倡议》发布',
                '《矿产资源对外合作可持续发展自律倡议》由中国五矿化工进出口商会、中国矿业联合会、中国钢铁工业协会及近 30 家行业企业共同发起，旨在推动形成中国矿产供应链对外合作领域共同遵循的行业行为规范。倡议依据我国对外投资合作相关法律法规，结合《绿色矿产国际经贸合作倡议》《可持续矿业守则》等框架并参考联合国相关国际文书制定，覆盖境外投资贸易、勘探开发、冶炼加工、金属深加工、再生矿产回收及上下游合作供应商与承包商，推动可持续发展要求融入投资决策、项目建设、生产运营和供应链管理全过程。')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104127060',
                '上海有色网', '09-22',
                '广期所调整国庆假期碳酸锂等期货涨跌停板与保证金标准',
                '9 月 21 日，广州期货交易所发布关于 2026 年国庆节假期调整相关期货合约涨跌停板幅度和交易保证金标准的通知。自 9 月 29 日结算时起，工业硅期货合约涨跌停板幅度调整为 10%、投机交易保证金标准调整为 12%；多晶硅涨跌停板 11%、投机保证金 15%；碳酸锂涨跌停板 15%、投机保证金 17%、套期保值保证金 16%；铂、钯期货涨跌停板及保证金标准均调整为 18%。10 月 8 日恢复交易后，工业硅、多晶硅、碳酸锂恢复至调整前水平，铂、钯调整为 12% 和 14%。')),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474201',
                '中国有色金属报', '09-22',
                '铜精矿 TC 深度负值 硫酸副产成铜企利润翻倍主因',
                '今年上半年铜精矿 TC 跌至负值，截至 2026 年 9 月进口铜精矿现货 TC 已跌至 -200 美元/干吨附近，7 月起铜冶炼环节陷入深度亏损；但 18 家上市铜企半年报全线盈利，北方铜业净利润同比增幅达 186.61%，江西铜业、铜陵有色、西部矿业、恒邦股份等增幅均超 100%。利润推手并非铜冶炼主业——铜企主业毛利率普遍仅 0%~6%，而硫酸毛利率高达 75%~85%，上半年硫酸价格从年初约 900 元/吨涨至近 2000 元/吨。火法炼铜每产 1 吨阴极铜约副产 3.5~4 吨硫酸，只要硫酸价格维持在 1000 元/吨以上，深度负 TC 格局便可延续。')),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474200',
                '中国有色金属报', '09-22',
                '沪铝结构性独立行情延续 供给受限与低库存构筑底部',
                '国内有色板块整体承压背景下铝价下行空间受限：一方面美国 8 月 CPI 同比上涨 3.4%、核心 CPI 环比上涨 0.3%，PPI 同比攀升至 5.4%，加息预期升温对铝价形成宏观压制；另一方面国内电解铝受政策约束供给增量有限，截至 8 月中国电解铝运行产能 4561 万吨、产量 387.4 万吨，下游加工龙头企业开工率回升至 61.3%。库存持续去化，截至 9 月 11 日国内主要地区铝锭库存降至 74.9 万吨、上期所库存降至 34.76 万吨，LME 库存中俄铝占比超九成、可用资源紧缺。')),
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/16bb390b6b0b47de824ff0f865b178d8.html',
                '长江有色网', '09-22',
                '碳酸锂触底反弹 现货涨 750 元/吨 主力合约涨 2.53%',
                '9 月 22 日，长江综合电池级碳酸锂 99.5% 均价 133750 元/吨，较上一交易日上涨 750 元/吨；工业级碳酸锂 99.2% 均价 130750 元/吨，同样上涨 750 元/吨。期货市场同步走强，碳酸锂主力合约当日收涨 2.53%、报 134400 元/吨。市场同时提示，社会库存与新增产能仍对反弹空间构成限制。')),
    (CAT_SC, ni('https://news.smm.cn/news/104108292',
                '上海有色网', '09-22',
                'SMM 日评：金属涨跌互现 沪铜领涨 1.24% 碳酸锂涨超 2%',
                '截至 9 月 22 日日间收盘，内盘基本金属普涨，仅沪铝跌 0.27%、沪锌跌 0.6%；沪铜以 1.24% 涨幅领涨，沪镍涨 0.97%，氧化铝主连涨 0.51%。碳酸锂主连涨 2.53%，多晶硅主连涨 2.39%。外盘基本金属普涨，伦铜涨 0.45%、伦铝涨 0.41%，伦锌与伦镍小幅下跌。贵金属走弱，COMEX 黄金跌 0.69%、白银跌 1.08%，沪金跌 1.06%、沪银跌 1.8%，铂主连跌 1.48%、钯主连跌 1.32%。')),
    (CAT_SC, ni('https://www.mining.com/copper-price-closes-in-on-new-record-as-shanghai-london-warehouses-empty-out',
                'MINING.COM', '09-22',
                '铜价逼近历史纪录 上海与伦敦库存双双告急',
                '铜价周二连续第六个交易日上涨，COMEX 12 月期铜盘中最高涨 1.6% 至 6.8710 美元/磅、收于 6.8370 美元/磅（约 15070 美元/吨），逼近 9 月 9 日创下的 6.8885 美元/磅结算纪录；LME 三个月铜涨 0.7% 至 14766 美元/吨，上海期货交易所主力合约涨 1.2% 至 111320 元/吨。上期所铜库存自 6 月初以来下降 70%，上海电解铜库存上周降至 43900 吨、为 2023 年以来最低；LME 注销仓单再增 6700 吨至 122150 吨、占在库仓单 48%，可交易库存仅剩 133725 吨。COMEX 铜库存 696204 吨、占全球交易所监测铜库存约 69%，新奥尔良港库容基本用满。',
                orig_title='Copper price closes in on new record as Shanghai, London warehouses empty out')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474193',
                '中国有色金属报', '09-22',
                '神火集团年产 5 万吨钠离子电池铝箔项目开工',
                '神火集团年产 5 万吨钠离子电池高性能铝箔项目开工，规划建设约 4 万平方米现代化生产车间并配套智能化仓储物流系统，配置 3 台 1850 毫米和 3 台 2150 毫米铝箔轧机，产品覆盖 1070、1100 等合金牌号、厚度 8~20 微米的钠离子电池正负极专用铝箔。项目建设周期 24 个月、计划今年年内建成投产，建成后预计提供就业岗位 300 余个、年实现利税约 1.2 亿元，可将神火新材商丘基地铝箔加工能力提升至 16.5 万吨；全面达产后集团铝箔总产能将达 19 万吨。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474217',
                '中国有色金属报', '09-22',
                '凉山矿业红泥坡铜矿采选工程主系统通风机试运行成功',
                '9 月 10 日，凉山矿业股份有限公司红泥坡铜矿采选工程项目主系统通风机试运行成功，井下风速、风量、风质等各项指标满足规范要求。该通风系统采用中央进风、两翼回风的布置方式，新鲜风流经进风竖井、充填进风盲斜井、辅助竖井、箕斗竖井与斜坡道进入各分段，污风经东南回风竖井及西回风竖井排出地表。此次试运行成功进一步优化了井下通风线路、改善了作业环境，是项目建设的重要里程碑。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474207',
                '中国有色金属报', '09-22',
                '五矿铍业启动铍铜母合金全流程智能化改造',
                '五矿铍业有限责任公司与北京中冶设备研究设计总院签约铍铜合金生产技术及装备研究项目，正式启动铍铜母合金全流程智能化改造。项目将搭建覆盖原料处理、冶炼、精炼、合金化及成品铸锭的自动化生产体系，推动高危区域机械化替人作业，并攻关 2000℃ 高温机械化精炼技术，把传统两次铸锭工艺优化为一次稳定成材。项目预计 2027 年 4 月建成中试平台、2027 年 12 月全面竣工，建成国内首条铍铜母合金全流程智能示范产线。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://www.mining.com/mali-challenges-force-resolute-mining-to-cut-syama-outlook',
                'MINING.COM', '09-22',
                '马里供应受阻 Resolute 下调 Syama 金矿产量指引约两成半',
                'Resolute Mining（ASX/LON: RSG）将马里 Syama 金矿 2026 年产量指引由 19.5 万~21 万盎司下调至 15 万~16 万盎司，全维持成本（AISC）由 1950~2150 美元/盎司上调至 2300~2400 美元/盎司。公司集团层面产量指引同步下调至 20.5 万~22.5 万盎司。Syama 自二季度以来持续低于计划产量：雨季炸药供应间歇性中断、低乳化炸药可得性迫使改用铵油炸药，露天矿 A21 进度滞后推迟了高品位矿石的接续；7—8 月合计仅产金 15500 盎司，三季度产量约 31000 盎司。公司预计四季度产量回升至 4.5 万~5 万盎司，并正在建设现场乳化炸药厂（11 月投产）。',
                orig_title='Mali setbacks force Resolute Mining to cut Syama outlook')),
    (CAT_GJ, ni('https://www.mining.com/mining-companies-built-mini-armies-in-risky-regions-expert',
                'MINING.COM', '09-22',
                '专家：西非矿企在风险地区自建「小型武装」',
                'Critical Risk Team 合伙人 George McLeod 在《北方矿工》播客中表示，布基纳法索、马里等国政府逐渐失去对领土的控制，矿业公司遂自行组建安保力量维持运营，「实际上把自己的矿山变成了许多小国，靠自建的迷你安保军队而非退化的政府军」。他认为矿企在此类环境中的处境并不算差——矿山只需保证物资运入与精矿运出，对其它条件依赖有限。McLeod 同时称，西方包括澳大利亚、美国、巴西等获得自有精炼产能后，中国对稀土市场的影响力预计最多还剩约 3 年。',
                orig_title='Mining companies built ‘mini armies’ in risky regions: expert')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/kyaqyhb/202609/t20260922_10320745.htm',
                '全球矿产资源信息系统', '09-22',
                '美国拟清理核设施遗留关键矿产 面向业界招商',
                '据 Mining.com 报道，9 月 18 日美国能源部环境管理办公室发布意向征询书，就转让位于全美五个清理场址的过剩关键矿物、稀土元素及其他材料征求业界意见。这些材料源于过去的核武器生产及政府资助的能源研究，涉及铝、铯-137、氯化物、铜、氟、铅、氢化锂、铂、硒、银、钨和钒等。五个场址包括肯塔基州帕迪尤卡、俄亥俄州朴次茅斯、田纳西州橡树岭、内华达国家安全试验场以及犹他州摩押；能源部将于 9 月 30 日举办线上「行业日」活动，意向方须自行提供设备与专业技术完成材料搬迁或提取。')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104124716-drc-establishes-us-drc-special-working-group-to-accelerate-strategic-minerals-partnership',
                'SMM 国际站', '09-21',
                '刚果（金）设立美刚工作组 加速战略矿产伙伴关系',
                '据外媒报道，刚果（金）内阁批准设立刚果（金）—美国工作组，以加速落实双边战略矿产伙伴关系协议、吸引西方投资进入该国铜钴产业。刚果（金）是全球最大钴生产国、第二大铜生产国与出口国，两国去年 12 月签署矿产合作协议。在当前合作框架下，Virtus Minerals 已获得美国支持的矿业投资，并推动 Gecamines 与 Mercuria、嘉能可扩大铜矿合作。该工作组原定今年 2 月启动，因行政障碍推迟，成员与重点项目尚未披露；内阁会议同时批准 2027 年 248 亿美元财政预算，同比增长 12%。',
                orig_title='DRC Establishes US-DRC Special Working Group to Accelerate Strategic Minerals Partnership')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104129006-smm-flash-south-african-platinum-sector-mine-fatalities-reach-18-in-2026',
                'SMM 国际站', '09-22',
                '南非铂族金属行业 2026 年矿难死亡人数升至 18 人',
                '南非矿产与石油资源部长 Gwede Mantashe 在 9 月 17 日举行的矿山安全峰会上表示，截至 2026 年 9 月 14 日，南非铂族金属（PGM）行业已录得 18 名矿工死亡，而 2025 年全年为 11 人。Mantashe 敦促行业及时调查事故并加强工人保护。该数字上升使铂族金属生产商与监管机构的矿山安全问题受到更多关注，但部长讲话未宣布新规、停产或产量调整。',
                orig_title='[SMM Flash] South African Platinum-Sector Mine Fatalities Reach 18 in 2026')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('https://www.mining.com/global-lithium-soars-50-on-a333m-titan-takeover',
                'MINING.COM', '09-22',
                '阿联酋 Titan 以 3.33 亿澳元收购 Global Lithium',
                'Global Lithium Resources（ASX: GL1）同意接受总部位于阿联酋的 Titan Australia Mining 提出的 3.33 亿澳元（约 2.37 亿美元）现金收购，Titan Australia 报价 1.15 澳元/股，较 Global Lithium 9 月 18 日收盘价 0.665 澳元溢价近 73%。消息公布后公司股价盘中最高涨 62.4% 至 1.08 澳元，收于 0.995 澳元。交易使 Titan 获得 Global Lithium 位于西澳的 Manna 锂项目，Titan 并承诺提供 1.2 亿澳元贷款额度支持 Manna 于 2026 年底完成最终投资决策、2028 年 6 月发运首批锂辉石。交易仍需股东及监管批准，计划 12 月召开方案会议、2027 年 1 月中旬实施。',
                orig_title='Global Lithium soars 50% on A$333M Titan takeover')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-22/1225574029.PDF',
                '巨潮资讯网', '09-22',
                '天原股份拟竞拍控股子公司天程锂电 20.2057% 股权',
                '天原股份（002386）公告，公司拟参与竞拍控股子公司天程锂电 20.2057% 股权，以进一步提高持股比例。据四川天健华衡资产评估有限公司以 2026 年 7 月 31 日为基准日出具的评估报告，天程锂电全部股权价值人民币 46480.00 万元，对应 20.2057% 股权的评估值为 9391.61 万元。天程锂电 2026 年 1—7 月经审计营业收入 124900.43 万元、净利润 1786.16 万元。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-22/1225575230.PDF',
                '巨潮资讯网', '09-22',
                '焦作万方发行股份购买资产申请获深交所终止审核',
                '焦作万方（000612）公告，公司于 2026 年 9 月 14 日召开第十届董事会第十五次会议，审议通过终止发行股份购买资产暨关联交易并撤回申请文件的议案；9 月 21 日收到深圳证券交易所《关于终止对焦作万方铝业股份有限公司发行股份购买资产申请审核的决定》（深证上审〔2026〕288 号）。公司称本次终止不会对主营业务、财务状况产生重大不利影响，不存在损害公司及中小股东利益的情形。',
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

# ============ 3.6 数字落地校验（2026-09-14 新增，复用 verify_numbers） ============
# 每条摘要的数字须能在源文（候选池/月库）找到，防 LLM 抄错数字。
# 候选池未落盘或未开 --fetch-detail 时源文基准为空 -> 自动 skip（不阻断生成）。
# 生产守门：置 VERIFY_NUMBERS_STRICT=1 时未落地即抛异常（CI / 上线前卡点）。
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

# ============ 7. div 收支自检（2026-09-11 破损教训） ============
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
