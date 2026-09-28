# -*- coding: utf-8 -*-
"""
生成 2026-09-29 矿业资讯速览 index.html（周二）
- 09-28 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-31）回补历史条目
- 换入 09-28 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-28 收盘（周二 06:00 未开盘）
  + LME 09-28 收盘（卡片=走势图末点口径），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易），不进主页列表
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

REPORT = '2026-09-29'
GRAB = '2026-09-29'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月29日 星期二', html)
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
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/ddyw/202609/t20260928_869736.html',
                '中国地质调查局', '09-28',
                '央视新闻：多项硬核突破！“梦想”号深海钻探取心达 5000 米级',
                '我国首艘大洋钻探船“梦想”号完成南海大洋钻探试钻任务返回广州：本航次历时 30 天，在南海 4100 米水深海域完成 2 口井的钻探取心任务，成功钻获南海洋盆玄武岩样品。最大完钻深度 4929.17 米、最大进尺 864.77 米，并钻获 4.27 米玄武岩岩心，将我国深海钻探取心作业能力提升至 5000 米级，成为全球第三个利用钻探船钻获深海洋盆硬岩样品的国家。')),

    (CAT_ZK, ni('http://static.cninfo.com.cn/finalpage/2026-09-29/1225586130.PDF',
                '巨潮资讯网', '09-29',
                '大中矿业：四川马尔康加达锂矿勘探报告资源储量通过评审备案',
                '大中矿业（001203）公告，全资子公司安徽省大中新能源投资有限责任公司收到自然资源部复函，《四川省马尔康市加达矿区 119～167 线锂矿勘探报告》矿产资源储量通过评审备案。截至 2025 年 12 月 31 日，加达锂矿首采区外围 4.0178 平方公里新增矿石量 3352.30 万吨、Li₂O 矿物量 42.38 万吨、平均品位 1.26%，折合碳酸锂当量约 104.68 万吨；本次增储后，加达锂矿累计备案碳酸锂当量由 148.42 万吨提升至 253.10 万吨。',
                embed='pdf')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/en/newscontent/104137362-miit-unveils-15th-five-year-plan-boost-safety-performance-in-consumer-nev-and-ess-batteries',
                'SMM 国际站', '09-29',
                '工信部等七部门发布新型电池产业“十五五”规划，聚焦安全与性能提升',
                '工信部等七部门联合发布《新型电池产业发展“十五五”规划》，提出通过工艺优化、材料升级与结构创新提升能量密度、功率密度与循环寿命。规划要求发展高安全消费电子锂电池，提升新能源汽车与电动船舶动力电池的安全性、快充性能、低温适应性与轻量化水平，并开发高安全、大容量、构网型、超长循环寿命的储能电池。',
                orig_title="MIIT Unveils 15th Five-Year Plan: Boost Safety, Performance in Consumer, NEV, and ESS Batteries")),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104136879',
                '上海有色网', '09-28',
                'SMM 日评：金属近全线飘绿，碳酸锂、沪银领跌',
                'SMM 9 月 28 日讯：内盘基本金属集体下跌，沪铝跌 1.2%、沪镍跌 1.12%、沪锌跌 0.92%、沪锡跌 0.83%、沪铜跌 0.7%、沪铅跌 0.58%；碳酸锂主连重挫 5.69%，工业硅主连跌 0.99%，多晶硅主连涨 0.07%。外盘基本金属同步下跌，伦铜跌 1.33%、伦铝跌 1.04%、伦锌跌 1.38%、伦锡跌 1.65%；贵金属方面沪银跌 5.08%、沪金跌 2.86%，COMEX 白银跌 4.44%。')),

    (CAT_SC, ni('https://news.smm.cn/news/104137374',
                '上海有色网', '09-28',
                '金银集体杀跌！高油价与美联储高加息预期持续压制贵金属',
                '油价高位运行叠加美国经济活动走强，强化了市场对美联储维持高利率甚至继续加息的预期，贵金属大幅承压：布伦特原油突破 100 美元/桶、日内涨超 2.5%，现货黄金跌破 4150 美元/盎司，现货白银跌 5.01% 至 61.08 美元/盎司。市场定价显示美联储 10 月再度加息的概率约为 65% 至 70%，美元指数小幅上涨、徘徊在 101 附近。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/123a6c856244449998d14870fbbae208.html',
                '长江有色网', '09-28',
                '长江有色：旺季备库结束，28 日碳酸锂报价下调 7000 元',
                '9 月 28 日，长江综合电池级碳酸锂 99.5% 均价 123750 元/吨、工业级碳酸锂 99.2% 均价 120750 元/吨，均较上一交易日下跌 7000 元。期货市场同步大幅下挫，碳酸锂主力合约破位下行，收报 119040 元/吨，期现联动走弱，市场悲观情绪快速发酵。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/9781cafe7c0c4fcc9dac777c5295328b.html',
                '长江有色网', '09-28',
                '2.4 万关口失守：铝价是变盘信号还是区间下沿压力测试',
                '9 月 28 日，沪铝主力 2611 合约盘中最低触及 23935 元/吨，尾盘收报 23950 元/吨，跌破 2.4 万元这一市场普遍关注的心理与成本关口。海外市场同步走弱，LME 三个月期铝交投于 3225 美元/吨附近。')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202609/t20260928_10324232.htm',
                '全球矿产资源信息系统', '09-28',
                '上周五国际矿产品价格多数下跌，原油跌幅居前',
                '上周五（25 日）国际矿产品价格多数下跌，原油跌幅居前，金银价格小幅回升。WTI 原油收于 92.43 美元/桶、下跌 2.46%，布伦特原油收于 97.43 美元/桶、下跌 2.77%；LME 铜收于 14625.50 美元/吨、下跌 0.14%，铝 3276.00 美元/吨、上涨 0.75%，锌 3892.00 美元/吨、下跌 1.84%，锡 54230.00 美元/吨、上涨 0.71%。纽约商品交易所黄金收于 4285.0 美元/盎司、上涨 0.24%，白银 64.26 美元/盎司、上涨 0.68%。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/104137316',
                '上海有色网', '09-28',
                '锡业股份：锡业分公司 9 月 30 日起停产检修，预计不超过 45 天',
                '锡业股份（000960）公告，为保障锡冶炼设备安全有效运行及后续稳定高效生产，锡业分公司将对锡冶炼设备进行例行停产检修，计划于 2026 年 9 月 30 日开始、预计不超过 45 天。公司年初预算及生产计划已考虑本次停产检修事宜，对全年生产计划无较大影响。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-09-29/1225584915.PDF',
                '巨潮资讯网', '09-29',
                '华锡有色：间接控股股东国有股权无偿划转完成',
                '华锡有色（600301）公告，控股股东华锡集团 28.79% 国有股权无偿划转已完成交割，关键金属集团以间接方式合计控制上市公司 56.47% 股份、成为间接控股股东。本次划转完成后，上市公司实际控制人广西壮族自治区国资委与直接控股股东华锡集团均未发生变化。',
                embed='pdf')),

    (CAT_HY, ni('https://news.smm.cn/news/104136390',
                '上海有色网', '09-28',
                '顺博合金：铸造铝合金产能共计 105 万吨，上半年量价齐升',
                '顺博合金披露，公司在重庆合川、广东清远、湖北襄阳、安徽马鞍山等地布局铸造铝合金板块，目前铸造铝合金产能共计 105 万吨。2026 年上半年公司实现营业收入 84.47 亿元、同比增长 18.54%，归属于上市公司股东的净利润 1.95 亿元、同比增长 6.02%。')),

    (CAT_HY, ni('https://www.ccmn.cn/news/ZX018/202609/6544bb0f91644e35bc21e71278c07cc8.html',
                '长江有色网', '09-28',
                '全球首条水系金属电池大规模产线在江苏常州投产',
                '美国储能企业 EnerVenue 宣布，其全球首条 Aqueous Metal Cell（AMC，水系金属电池）大规模生产线在江苏常州武进正式投产。该项目于今年 4 月破土动工，9 月底实现首块合格电芯下线，标志该款新型储能电池迈入规模化量产阶段；产品循环次数可达 3 万次、无热失控火灾风险。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202609/t20260928_10324231.htm',
                '全球矿产资源信息系统', '09-28',
                '嘉能可将协助美国构建关键矿产储备',
                '据 Mining.com 报道，在获得美国进出口银行（EXIM）5 亿美元资金承诺后，瑞士矿商与贸易商嘉能可、摩科瑞将通过公私合营的金库公司（VaultCo）为美国工业提供关键矿产和贱金属的货源、采购与交付。EXIM 已批准为“金库计划”提供 100 亿美元直接贷款，在美国各设施储备原材料，供制造商在供应链中断时获取材料。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202609/t20260928_10324230.htm',
                '全球矿产资源信息系统', '09-28',
                '巴西卡拉道稀土项目资源量大幅增长',
                '据 BNAmericas 报道，阿塞尔稀土公司（Axel REE）更新其在巴西的卡拉道（Caladao）项目资源量：伍尔里奇离子型稀土矿床完成钻探后资源量增长 107%，矿石资源量达 2.65 亿吨、TREO 品位 0.1101%。整个项目矿石资源量已增至 7.09 亿吨、TREO 品位 0.1443%，增长 24%；镓矿石资源量 5.80 亿吨、增长 31%，公司称该矿是世界最大镓矿床之一。')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104137371-alba-advances-in-acquisition-of-aluminium-dunkerque-aims-for-global-low-carbon-aluminum-expansion',
                'SMM 国际站', '09-29',
                '阿联酋铝业（Alba）收购 Aluminium Dunkerque 交易推进中',
                '阿联酋铝业（Alba）表示，其收购 Aluminium Dunkerque 的交易正在推进，公司正努力取得交割所需的剩余监管批准。公司董事长在 9 月 22 日的董事会会议上称，这笔交易是 Alba 国际扩张、构建全球低碳铝平台的重要一步。该交易于 2026 年 5 月签约，估值约 22 亿美元，标的为欧盟最大的原铝冶炼厂。',
                orig_title="Alba Advances in Acquisition of Aluminium Dunkerque, Aims for Global Low-Carbon Aluminum Expansion")),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104137367-guinea-seeks-us-financing-for-cbgs-alumina-refinery-project',
                'SMM 国际站', '09-29',
                '几内亚为 CBG 氧化铝厂项目寻求美国融资',
                '几内亚正为几内亚铝土矿公司（CBG）规划的氧化铝厂寻求美国融资，以加快国内铝土矿就地加工。几内亚矿业部称，9 月 18 日已与美国国际开发金融公司（DFC）和美国进出口银行就参与该项目融资进行了商谈。CBG 计划 2026 年底前开工建设，但该氧化铝厂的融资需求与美国可能出资的规模尚未披露。',
                orig_title="Guinea Seeks US Financing for CBG's Alumina Refinery Project")),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104137357-nyrstar-launches-strategic-review-of-budel-smelter-operations-continue-normally',
                'SMM 国际站', '09-29',
                'Nyrstar 对荷兰 Budel 锌冶炼厂启动战略评估',
                'Nyrstar 宣布对位于荷兰的 Budel 锌冶炼厂启动战略评估，原因是欧洲能源成本高企、锌精矿竞争激烈以及加工费处于历史低位。公司称 Budel 一直处于亏损状态，荷兰政府决定不将能源密集型产业的电网费用减免纳入 2027 年预算，进一步加大了压力。该厂年精炼锌产能 315000 吨，评估预计 2026 年底完成，期间正常运营。',
                orig_title="Nyrstar Launches Strategic Review of Budel Smelter; Operations Continue Normally")),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104137349-smm-aluminum-flash-newsun-selects-6-nations-for-support-in-critical-mineral-development-amid-global-energy-transition',
                'SMM 国际站', '09-29',
                '联合国选定 6 国支持其关键矿产开发',
                '联合国秘书长古特雷斯宣布，联合国已选定印度尼西亚、赞比亚、几内亚、津巴布韦、马达加斯加和尼日利亚 6 个国家，支持其从能源转型所需的关键矿产中获取更大价值，联合国相关机构将协调帮助这些国家发展相关产业。赞比亚是非洲第二大铜生产国，津巴布韦是非洲电池级锂的重要供应方，印尼是全球最大镍生产国，几内亚则是铝土矿最大生产国。',
                orig_title="[SMM Aluminum Flash News] UN Selects 6 Nations for Support in Critical Mineral Development Amid Global Energy Transition")),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104137343-smm-aluminum-flash-newsodisha-commits-local-bauxite-for-vedantas-lanjigarh-alumina-refinery',
                'SMM 国际站', '09-29',
                '印度奥里萨邦承诺向韦丹塔供应本地铝土矿',
                '印度奥里萨邦政府承诺为韦丹塔（Vedanta）位于 Kalahandi 的 Lanjigarh 氧化铝厂提供本地铝土矿。该承诺是在 9 月 26 日邦首席部长 Mohan Charan Majhi 与韦丹塔董事长 Anil Agarwal 的会面中作出的，双方还讨论了加快推进该公司拟在该邦约 1 万亿卢比（约 104.2 亿美元）的铝业投资。',
                orig_title="[SMM Aluminum Flash News] Odisha commits local bauxite for Vedanta’s Lanjigarh alumina refinery")),

    (CAT_GJ, ni('https://www.mining.com/northern-star-rejects-opportunistic-gold-fields-27b-takeover-bid',
                'MINING.COM', '09-28',
                'Northern Star 拒绝 Gold Fields 270 亿美元收购要约',
                '澳大利亚金矿商 Northern Star 拒绝了 Gold Fields 提出的“机会主义”收购要约，该要约估值约 270 亿美元。要约被拒后，激进投资者 Elliott 推动这家澳洲矿企探索出售的压力进一步加大。',
                orig_title="Northern Star rejects ‘opportunistic’ Gold Fields’ $27B takeover bid")),

    (CAT_GJ, ni('https://www.mining.com/b2gold-strikes-new-goose-gold-zone',
                'MINING.COM', '09-29',
                'B2Gold 在 Goose 矿发现新高品位金矿带',
                'B2Gold 在位于加拿大努纳武特的 Goose 矿发现了一条新的高品位金矿带。该矿今年 4 月曾发生火灾，目前公司正处在恢复生产的过程中。',
                orig_title="B2Gold strikes new Goose gold zone")),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104137359-new-zealands-tiwai-point-smelter-at-full-capacity-boosted-by-strong-aluminum-prices',
                'SMM 国际站', '09-29',
                '新西兰 Tiwai Point 铝冶炼厂满负荷运行',
                '受铝价走强支撑出口收益，新西兰 Tiwai Point 铝冶炼厂正满负荷生产，该国铝出口额已达约 22 亿新西兰元。力拓旗下的新西兰铝冶炼厂（NZAS）年产能超过 335000 吨，约 90% 用于出口，因主要使用可再生能源水电而成为全球碳排放较低的原铝生产商之一。',
                orig_title="New Zealand's Tiwai Point Smelter at Full Capacity, Boosted by Strong Aluminum Prices")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-29/1225585468.PDF',
                '巨潮资讯网', '09-29',
                '紫金矿业：就获得赤峰黄金控制权签署补充协议，交割期限延长',
                '紫金矿业（601899）公告，全资子公司紫金黄金与赤峰黄金控股股东李金阳及其一致行动人签署《股份转让协议》之补充协议，将收购约 2.42 亿股赤峰黄金 A 股的交割先决条件满足期限延长至 2026 年 11 月 30 日；同时与赤峰黄金签署《战略投资协议》之补充协议，将认购约 3.11 亿股 H 股定向增发的最后截止日期一并延长至同日。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-29/1225584676.PDF',
                '巨潮资讯网', '09-29',
                '中稀有色：拟以 3.06 亿元增资全资子公司晟源永磁',
                '中稀有色（600259）公告，董事会审议通过以自有资金向全资子公司广东晟源永磁材料有限责任公司增资 3.06 亿元，用于加快磁材板块战略布局、优化子公司资本结构。晟源公司是“8000t/a 高性能钕铁硼永磁材料项目”的实施主体，增资完成后上市公司仍持有其 100% 股权。',
                embed='pdf')),

    (CAT_MA, ni('https://news.smm.cn/news/104137019',
                '上海有色网', '09-29',
                '金银河拟定增募资不超 15 亿元，加码固态电池及钠电装备',
                '金银河披露定向增发预案，拟募集资金不超过 15 亿元，用于加码固态电池及钠离子电池装备业务，进一步扩充新型电池装备产能布局。')),

    # ── 💼 矿权交易（仅入 rightsSection 数据层，不进主列表） ───
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
