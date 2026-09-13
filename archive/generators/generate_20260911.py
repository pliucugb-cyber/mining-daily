# -*- coding: utf-8 -*-
"""
生成 2026-09-11 矿业新闻日报 index.html
- 09-10 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-13）回补历史条目
- 换入 09-11 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所 09-10 收盘 + LME 09-10 收盘，全部由 price_history_detail.json /
  lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（data/news_2026-09.json），不进主页列表
- 保留：会展预告 IIFE / 搜索 / CSV / PDF / 防横跳
- 境外条目保留英文原题（data-orig-title + 摘要末尾「原题：…」）
"""
import re, datetime, json, glob
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
)
from functools import partial


SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()
_ORIG_SIZE = len(html)

REPORT = '2026-09-11'
GRAB = '2026-09-11'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / 更新时间 / build-version ============
html = re.sub(r'<title>\d{4}-\d{2}-\d{2}</title>', '<title>%s</title>' % REPORT, html)
html = html.replace('2026年09月10日 星期四', '2026年09月11日 星期五')
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'更新时间：2026-09-\d{2} \d{2}:\d{2}', '更新时间：%s %s' % (REPORT, now), html)
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-09-\d{2} 更新', 'id="priceStripNote">%s 更新' % REPORT, html)
html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
              'name="build-version" content="%s-%s"' % (REPORT.replace('-', ''), now.replace(':', '')), html)

# ============ 2. 价格卡刷新（全部现算，禁止手抄） ============
_ph = json.load(open('price_history_detail.json', encoding='utf-8'))['series']

# slug -> (中文名, 标签, 单位, 小数位)
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
    shfe_cards.append(card(slug, name, tag, val, unit, chgtxt, 'up' if chg >= 0 else 'down'))
shfe_html = ''.join(shfe_cards)
# 电解钴：无当日源，保留上日 SMM 值并标注
shfe_html += ('<div class="price-card "><div class="pc-name">电解钴 <span class="pc-tag">SMM %s</span></div>'
              '<div class="pc-value">304,940</div><div class="pc-unit">元/吨</div>'
              '<div class="pc-chg">上日 304,940（SMM 未更新）</div></div>' % DATA_ASOF)

# LME 6 卡：直接读 lme_data.json（2026-09-10 收盘，零手抄）
_lme = json.load(open('lme_data.json', encoding='utf-8'))['metals']
_lme_map = {m['slug']: m for m in _lme}
LME_DEFS = [
    ('lcpt', 'LME 铜'), ('lalt', 'LME 铝'), ('lznt', 'LME 锌'),
    ('lldt', 'LME 铅'), ('lnkt', 'LME 镍'), ('ltnt', 'LME 锡'),
]
lme_list = []
for slug, name in LME_DEFS:
    m = _lme_map[slug]
    arrow = UP if m['chg'] >= 0 else DOWN
    if m['price'] is None:
        lme_list.append((slug, name, 'LME', '--', '美元/吨', '暂无数据', 'flat'))
        continue
    val = format(m['price'], ',.2f')
    sign = '+' if m['chg'] >= 0 else ''
    chg = '%s %s (%s%.2f%%)' % (arrow, sign + format(m['chg'], ',.2f'), sign, m['chg_pct'])
    lme_list.append((slug, name, 'LME', val, '美元/吨', chg, 'up' if m['chg'] >= 0 else 'down'))
lme_html = ''.join(card(*c) for c in lme_list)

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

# 2026-09-11 增：跨源同事件去重（同题多源转发 / SMM 中英文双语站重复）。
# 只按 URL 去重会漏掉「自然资源部+地调局+有色报」三家同题这类情况，
# 往期区曾因此残留 6 组重复。放在最后、保留先出现者。
merge_seq = dedup_same_event(merge_seq)

# ============ 4. 今日新增条目（09-11 抓取，均逐源核实） ============

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
    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260910_2938082.html', '自然资源部', '09-10',
                '绿色勘查六大生态区差异化模式成形 以钻代槽、直升机吊运钻机规模化应用',
                '新一轮找矿突破战略行动中，自然资源系统针对平原农耕、深山峡谷、草原、森林、黄土高原、荒漠戈壁六大典型生态区探索差异化绿色勘查模式：山东齐河—禹城富铁矿勘查以广域电磁、二维地震构建三维探测网，钻探时长压缩超20%；四川旺苍作坊坪矿区以直升机整机吊运钻机，不修一寸施工便道；黑龙江"以钻代槽"单孔占地仅16平方米、为同等槽探的1/83，全省推广应用以来累计减少林地占用37.66万平方米；黄土高原区地表扰动面积三年降幅超54%；荒漠戈壁区以可控震源替代爆破，扰动面积减少64%。')),
    (CAT_ZK, ni('https://www.mining.com/osisko-hits-4-7-copper-beneath-gaspe-workings', 'MINING.COM', '09-10',
                'Osisko 加斯佩铜矿钻探见矿 257 米，其中 28.5 米铜品位 4.74%',
                '钻孔 30-1228 自 33 米深处见约 257 米、铜品位 0.85%、银 5.13 克/吨的矿化，其中约 200 米深处有一厚 28.5 米、铜品位 4.74%、银 27.4 克/吨的高品位段，矿化延伸至历史 C 矿带以下 50 米、垂直深度 275 米。该矿位于加拿大魁北克东部加斯佩半岛，规划日处理能力最高 16 万吨，属加拿大最大级别矿山之一。',
                orig_title='Osisko hits 4.7% copper beneath Gaspé workings')),
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473893', '中国有色金属报', '09-10',
                '中铝集团连续十年获中国专利奖 3 项发明专利摘优秀奖',
                '国家知识产权局发布第二十六届中国专利奖授奖决定，中铝集团所属企业申报的 3 项发明专利获中国专利优秀奖，集团至此连续 10 年获奖。其中昆明勘察设计研究院"一种上游式尾矿堆积坝勘测与稳定性评价方法及系统"面向尾矿库安全与环境岩土工程，沈阳铝镁设计研究院"一种均化铝电解槽铝液中电流分布的方法"面向铝电解槽阴极结构与电流均化。')),

    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260910_2938103.html', '自然资源部', '09-10',
                '2026中国国际矿业大会在天津开幕 何立峰出席并致辞',
                '中共中央政治局委员、国务院副总理何立峰 9 月 10 日在天津出席矿业国际合作部长论坛暨 2026 中国国际矿业大会开幕式并致辞，指出矿业国际合作是实现各国资源优势互补、促进经济社会发展的重要载体，也是维护全球产供链安全稳定的现实需要；中国始终充分尊重各国矿产资源主权，愿同各国深化全方位务实合作。开幕式前，何立峰到矿山机械装备博览会展馆巡馆。')),
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260910_2938085.html', '自然资源部', '09-10',
                '自然资源部部长刘国洪：以"合作共赢 绿色智能"推动全球矿业发展',
                '自然资源部党组书记刘国洪在大会寄语中表示，本届大会以"合作共赢 绿色智能"为主题，真正的资源安全应建立在多元供应和互信合作之上；中国将持续放宽外资准入、优化营商环境，深化勘查开采、技术装备、标准规则和人才培养合作。矿业绿色转型已写入新修订的矿产资源法，中国将全面推进绿色勘查、健全绿色矿业标准、实施矿区生态修复，并加速人工智能、大数据、云计算、5G 与矿业融合，推进智能矿山建设。')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104108291', '上海有色网', '09-10',
                'SMM 日评：美元四连跌 沪锡领涨 1.87% 伦锌、氧化铝、多晶硅跌超 1%',
                '9 月 10 日国内日盘基本金属普涨：沪锡以 1.87% 领涨，沪铜涨 0.97%，沪镍等涨幅有限，仅沪铝跌 0.29%、沪锌跌 0.04%；氧化铝主连跌 1.18%、多晶硅主连跌 1.98%、工业硅主连跌 1.3%。外盘截至 15:05 基本金属普涨，仅伦铝、伦锌下跌，伦锌跌 1.19%。黑色系普跌，仅不锈钢微涨 0.11%。')),
    (CAT_SC, ni('https://news.smm.cn/news/104108749', '上海有色网', '09-10',
                '沪铜收涨 0.97% 报 112,200 元 非美地区低库存支撑铜价',
                '沪铜早间高开、日内涨幅震荡扩大，主力合约收涨 0.97% 报 112,200 元。矿端偏紧持续困扰铜市，在美国铜关税政策落地前非美地区低库存局面难改，铜价下方支撑较强、期价重心不断上移。同期中东地缘冲突升级、美伊展开六个月来最大规模海上互袭，国际油价破百，叠加部分美联储官员表态偏鹰、就业数据坚挺，市场对美联储 9 月小幅加息的押注约六成。')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104108744-white-house-undecided-on-copper-tariffs-lme-copper-drops-over-2-amid-market-uncertainty', 'SMM 国际站', '09-10',
                '白宫铜关税立场未决 伦铜单日重挫 4.25% 至 14,182.50 美元/吨',
                '消息人士称白宫尚未决定是否对精炼铜（阴极铜）征收关税，官员正在权衡"铜价上涨或推高制造成本"与"鼓励国内采矿"的得失，铜关税计划陷入停滞。消息公布后沪铜已收盘，伦铜盘中跌超 2%，当日收报 14,182.50 美元/吨、跌 629.50 美元（-4.25%），COMEX 12 月期铜盘中最大跌幅达 5.4%；此前一年交易商因关税预期大举囤铜，曾推动铜价连续四个交易日创历史新高。',
                orig_title='White House Undecided on Copper Tariffs, LME Copper Drops Over 2% Amid Market Uncertainty')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104108783-lme-zinc-plunges-25-from-four-year-high-driven-by-chinese-export-expectations-and-copper-pullback', 'SMM 国际站', '09-10',
                'LME 锌自四年高位重挫 收跌 5.14% 至 3,855 美元/吨',
                'LME 锌在前一日触及 4,065 美元/吨的四年多高位后急转直下，北京时间 19:00 报 3,960 美元/吨、跌约 2.5%，当日最终收报 3,855.00 美元/吨、跌 209.00 美元（-5.14%）。下跌主因是中国出口交仓 LME 的预期升温，叠加伦铜因关税预期变化大幅回落，拖累基本金属整体风险偏好，后续需关注 LME 期限结构与锌仓单交仓节奏。',
                orig_title="LME Zinc Plunges 2.5% from Four-Year High, Driven by Chinese Export Expectations and Copper Pullback")),
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/f9eb8ddf3c894703b12b0ca5fafbd5e4.html', '长江有色网', '09-10',
                '长江现货 1# 锡均价涨 9,250 元至 426,750 元/吨 沪锡盘中触及 427,970 元',
                '9 月 10 日长江现货 1# 锡报价 425,750~427,750 元/吨、均价 426,750 元/吨，较前一日上涨 9,250 元/吨；沪锡主力合约日内最高 427,970 元、最低 418,550 元，涨幅超 1%，量能同步放大、交投活跃度提升。分析将涨势归因于中东地缘局势升温推升大宗商品风险溢价，以及 AI 服务器（单台耗锡量约为传统机型 3 倍）、先进封装、EUV 光刻机等对精密焊料的刚性需求。')),
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202609/8d57feba9a684ef0b81f241ffb83cb87.html', '长江有色网', '09-10',
                '长江现货 1# 锑均价报 104,000 元/吨 单日上涨 1,000 元',
                '长江有色金属网数据显示，9 月 10 日长江现货 1# 锑市场均价报 104,000 元/吨，较上一交易日上涨 1,000 元/吨，现货价格重心小幅上移，战略小金属板块情绪有所回暖。')),
    (CAT_SC, ni('https://www.mining.com/mining-stocks-rally-comes-to-abrupt-halt-as-copper-silver-prices-plummet-and-gold-slides', 'MINING.COM', '09-10',
                '金属价格跳水 全球矿业股涨势戛然而止',
                '美国生产者价格报告与布伦特原油站上 105 美元/桶，将美联储下周加息概率推升至约 70%，叠加白宫铜关税计划停滞，金属与矿业板块全线回调：COMEX 12 月期铜盘中最大跌 5.4% 至 6.5160 美元/磅（约 14,380 美元/吨），12 月期金一度跌 2.1%，白银最大跌 6.1%，铂、钯均跌超 6%。对冲基金此前大举做多铜，关税溢价一经动摇便缺乏缓冲。',
                orig_title='Mining stocks rally comes to abrupt halt as copper, silver prices plummet and gold slides')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://www.chinania.org.cn/html/xiehuidongtai/xiehuidongtai/2026/0909/61963.html', '中国有色金属工业协会', '09-09',
                '2026 年（第二十四届）中国国际铜业论坛在哈尔滨召开',
                '9 月 9 日，2026 年（第二十四届）中国国际铜业论坛在黑龙江哈尔滨召开，主题为“链韧新开局 ‘铜’铸新时代——共筑全球铜产业安全与高质量发展共同体”。与会嘉宾围绕铜供应链安全与产业链韧性、铜需求新场景驱动与铜价值重构等议题展开研讨。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473894', '中国有色金属报', '09-10',
                '五矿二十三冶首个超千米深竖井项目取得阶段性成果',
                '截至 9 月 6 日，五矿二十三冶承建的鲁中矿业铁矿资源采选工程东风井累计下掘 144 米、成井 136.4 米，掘砌总进尺突破百米，标志其首个超千米深竖井项目取得阶段性成果。项目位于山东济南莱芜张家洼街道，建设内容包括 1 条超千米深竖井、2 条盲竖井及多中段平巷等，建成后将提升鲁中矿业铁矿开采效率与产能规模。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473895', '中国有色金属报', '09-10',
                '西部矿业集团在"数据要素×"大赛青海分赛获多项奖',
                '2026 年"数据要素×"大赛青海总决赛上，西部矿业集团"业财一体化数据融合的数据治理及资金精益管理"获金融服务赛道二等奖，西矿信息"多源矿山数据赋能矿产资源全生命周期智慧管控平台"获工业制造赛道二等奖；此外"全域 DCS 数据要素集成的生产工艺实时预警创新实践""数字孪生的工业高危场景数据集建设与实训管控"获三等奖，稀贵金属公司"工业互联网平台及智慧应用"获优秀奖。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473898', '中国有色金属报', '09-10',
                '中国稀土集团举行 2026 年工程硕博士入企实践开学典礼',
                '9 月 4 日，中国稀土集团 2026 年工程硕博士入企实践开学典礼在集团总部举行。集团方面表示，面对复杂多变的国际形势，稀土正加速向"战略新材料"跃迁，集团比以往任何时候更渴求拔尖创新人才，入企实践学生需完成从书本到生产、论文到工程、个人到团队的转变。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473848', '中国有色金属报', '09-08',
                '中铁资源乌兰矿充填站累计充填量突破 130 万立方米',
                '截至 9 月 1 日，中铁资源新鑫公司乌兰矿充填站累计完成充填方量突破 130 万立方米，同步消纳尾砂超过 150 万吨。该充填站自 2022 年 5 月试运行以来，底流浓度已从初期无法满足工艺要求稳定控制在 68%±2%，破解了充填作业不连续的难题，实现系统长周期高效运转。')),
    (CAT_HY, ni('https://www.cgs.gov.cn/ywdt/ddyw/202609/t20260910_868192.html', '中国地质调查局', '09-10',
                '中国地质调查局举办 2026 年新入职职工培训班',
                '9 月 2 日至 7 日，自然资源部中国地质调查局举办 2026 年新入职职工培训班，设置"学习习近平新时代中国特色社会主义思想，强化政治意识""学习局史局情，强化角色转变""学习纪法规矩，强化廉洁自律"三个单元，内容涵盖地质调查业务部署与科技创新、新职工野外一线能力提升、全面从严治党要求等。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://www.mining.com/rio-tinto-wins-aboriginal-consent-for-winu-copper-mine', 'MINING.COM', '09-10',
                '力拓取得西澳 Winu 铜金矿原住民同意 目标 2030 年首次产铜',
                '力拓与 Nyangumarta Warrarn 原住民公司达成协议，为其西澳 Winu 铜金矿项目建立长期合作框架，明确在推进规划的同时避免影响环境与原住民文化遗产。力拓与住友金属矿山共同持有该项目 70% 权益，目标 2030 年首次产出铜，尚待最终监管批准与最终投资决定。该项目位于西澳大沙沙漠、布鲁姆以南约 300 公里。',
                orig_title='Rio Tinto wins Aboriginal consent for Winu copper mine')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104108596-aic-mines-starts-dry-commissioning-of-eloise-plant-expansion-copper-output-targeted-at-25000', 'SMM 国际站', '09-10',
                'AIC Mines 的 Eloise 选厂扩建进入干式调试 2029 财年铜产量目标 2.5~2.7 万吨',
                'AIC Mines 位于澳大利亚昆士兰州西北部的 Eloise 铜金选厂一期扩建已通电并开始干式调试，处理能力将由约 72.5 万吨/年提升至 110 万吨/年，项目预算与进度均在计划内、预计四季度投产。公司三年产量目标为 2027 财年 1.75~1.85 万吨、2028 财年 2~2.2 万吨、2029 财年 2.5~2.7 万吨铜，并已承诺二期将处理能力提升至 150 万吨/年。',
                orig_title='AIC Mines Starts Dry Commissioning of Eloise Plant Expansion, Copper Output Targeted at 25,000–27,000 t in FY2029')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104108381-zambia-urges-vedanta-to-accelerate-power-investment-to-support-kcm-copper-expansion', 'SMM 国际站', '09-10',
                '赞比亚敦促 Vedanta 加快电力投资 支撑 KCM 铜矿扩产',
                '赞比亚总统希奇莱马会见 Vedanta 战略与增长负责人时，敦促其加快发电投资以支撑孔科拉铜矿（KCM）扩产；Vedanta 介绍了 KCM 扩产进展及将铜年产量提升至 50 万吨的长期目标。赞方表示新增发电投资既能服务矿山运营，也有助其国家能源目标。双方均未披露新增发电产能、投资金额与实施时间表。',
                orig_title='Zambia Urges Vedanta to Accelerate Power Investment to Support KCM Copper Expansion')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-11/1225557124.PDF', '巨潮资讯网', '09-11',
                '常铝股份：控股股东签署股份转让协议之补充协议 控制权拟发生变更',
                '常铝股份公告，控股股东就此前签署的股份转让协议签署补充协议，公司控制权拟发生变更事项取得进展。该交易将导致公司控制权转移，具体转让股份数量、价格与生效条件以公告全文为准。')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-11/1225557705.PDF', '巨潮资讯网', '09-11',
                '华盛锂电：参与投资设立产业基金二期暨关联交易进展',
                '华盛锂电披露参与投资设立产业基金二期的进展事项，该交易构成关联交易。公司继续以产业基金方式推进对外投资布局，具体出资金额与投资方向以公告全文为准。')),

    # ---------- 09-11 下午增量：政策与监管 ----------
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260911_2938137.html', '自然资源部', '09-11',
                '《矿业绿色发展天津宣言》发布 就矿业绿色低碳转型提出十方面倡议',
                '2026 中国国际矿业大会期间，自然资源部会同各国矿业主管部门、国际组织、矿业企业与行业协会代表共同发布《矿业绿色发展天津宣言》，围绕矿业绿色低碳转型提出十方面倡议，明确推动绿色勘查、绿色矿山建设、矿区生态修复、清洁能源替代与资源高效利用，倡导将绿色发展理念贯穿矿产资源勘查开发全过程，并呼吁加强国际绿色矿业标准互认与能力建设合作。')),
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260911_2938139.html', '自然资源部', '09-11',
                '《中国矿产资源报告 2026》摘编：十四五新发现战略性矿产大中型矿产地 398 处',
                '报告显示，"十四五"期间我国新发现战略性矿产大中型矿产地 398 处，累计投入找矿资金超 5000 亿元、较"十三五"增长 29.3%，14 种矿产储量居世界第一；2025 年全国地质勘查投资 1178.55 亿元、同比增长 1.6%。山西省孝义市申家庄探明我国最大单体铝土矿床，甘肃金昌白家嘴子矿区新增镍 56.75 万吨及伴生钴 3.29 万吨。2025 年十种有色金属产量 8175.0 万吨、同比增长 3.9%。')),
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260911_2938140.html', '自然资源部', '09-11',
                '《全球矿业发展报告 2026》摘编：全球矿业步入叠加变革期',
                '报告指出，2025 年全球固体矿产勘查投入 124.01 亿美元、同比微降 0.6%；全球矿业并购交易额 735.2 亿美元、同比增长 150.4%，融资额 214.3 亿美元、同比增长 108.7%，其中钴、金、银融资分别增长 33.0%、62.8% 和 144.8%。中国已建成绿色矿山超过 5500 座，绿色低碳与关键矿产供应链安全正成为全球矿业竞争的新维度。')),

    # ---------- 09-11 下午增量：市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104110888', '上海有色网', '09-11',
                'SMM 日评：内盘金属普遍下挫 沪锌锡铂钯跌超 3% 沪银跌逾 5%',
                '9 月 11 日国内日盘基本金属普遍下挫，沪锌跌 3.06%、沪锡跌 3.07%、沪铜跌 2.45%，铂、钯跌幅均超 3%，沪银跌 5.11%，碳酸锂跌 4.99%；美元指数报 99.06，美国 8 月 PPI 年率 5.4% 超预期，叠加欧洲央行加息，市场对美联储加息的押注升温，贵金属与基本金属同步承压。')),
    (CAT_SC, ni('https://news.smm.cn/news/104108889', '上海有色网', '09-11',
                '沪银主力重挫逾 6% 铂钯大跌 贵金属板块全线走低',
                '受美国 8 月 PPI 超预期及欧洲央行加息 25 个基点影响，国内贵金属期股齐跳水，沪银主力合约重挫逾 6%、报 15,412 元/千克（SMM1# 白银均价下跌 5.58%），铂、钯大幅下跌，贵金属板块整体走低；上半年国内金饰消费量同比下降 30% 至 136 吨，高银价对实物消费的抑制进一步显现。')),
    (CAT_SC, ni('https://www.mining.com/platinum-palladium-price-forecasts-cut-by-bmi-as-car-sales-shrink-and-south-african-supply-recovers', 'MINING.COM', '09-11',
                'BMI 下调铂钯价格预测：汽车销售萎缩 南非供应回升',
                '惠誉解决方案旗下 BMI 下调铂、钯价格预测，主因全球汽车销售萎缩削弱催化剂需求、南非铂族金属供应回升。同期 Sibanye-Stillwater 推进亏损矿井重组，其美国蒙大拿州钯矿发生罢工；世界铂金投资协会（WPIC）预计到今年年底全球地上铂库存仅相当于约 3.4 个月的需求。',
                orig_title='Platinum, palladium price forecasts cut by BMI as car sales shrink and South African supply recovers')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104111178-longbai-group-raises-titanium-dioxide-prices-by-rmb-700ton-in-china-usd-100ton-globally-from-sept-11', 'SMM 国际站', '09-11',
                '龙佰集团自 9 月 11 日起上调钛白粉价格 国内每吨 700 元、国际每吨 100 美元',
                '龙佰集团发布调价函，决定自 2026 年 9 月 11 日起在现行合同基础上上调全部"雪莲"牌钛白粉产品价格，国内市场每吨上调 700 元人民币，国际市场每吨上调 100 美元。龙头企业此轮主动提价既释放市场回暖信号，也有助于提振行业信心，后续需跟踪实际订单落地及其他厂商跟涨情况。',
                orig_title='Longbai Group Raises Titanium Dioxide Prices by RMB 700/ton in China, USD 100/ton Globally from Sept 11')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104111096-smm-analysis-us-ppi-beat-expectations-fueling-rate-hike-bets-nickel-prices-under-heavy-pressure-this-week', 'SMM 国际站', '09-11',
                'SMM 分析：美国 PPI 超预期推升加息押注 镍价本周明显承压',
                '美国 8 月生产者价格指数（PPI）超市场预期，进一步推升市场对美联储加息的押注，美元走强压制有色金属估值；SMM 分析认为镍价本周明显承压运行，后续需关注宏观情绪变化以及不锈钢、新能源等下游需求的边际改善情况。',
                orig_title='[SMM Analysis] US PPI Beat Expectations, Fueling Rate Hike Bets, Nickel Prices Under Heavy Pressure This Week')),

    # ---------- 09-11 下午增量：行业动态 ----------
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0911/61972.html', '中国有色金属工业协会', '09-11',
                '2026 年（第二届）有色金属行业"双碳"大会在杭州召开',
                '9 月 4 日，2026 年（第二届）有色金属行业"双碳"大会在浙江杭州召开，中国有色金属工业协会常务副会长贾明星出席并讲话、提出三点意见，张建阳致辞，中国工程院院士聂祚仁作主旨报告，近 300 余名代表参会。大会同期举办铝行业节能降碳专题研讨会，围绕铝冶炼能碳评价指南、欧盟碳边境调节机制（CBAM）等议题展开交流。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0911/61975.html', '中国有色金属工业协会', '09-11',
                '高端铜箔产业跑出"加速度" 高频高速基板用铜箔产量占比突破 50%',
                '安徽铜冠铜箔 2026 年半年报显示营收与利润双增长，其高频高速基板用铜箔（RTF/HVLP）产量占 PCB 铜箔总产量的比重突破 50%，HVLP4 代铜箔实现批量供货，RTF 产品产销规模位居内资企业前列，反映国内高端电子铜箔国产替代进程持续加快。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0911/61971.html', '中国有色金属工业协会', '09-11',
                '西北有色地矿集团 712 总队实现"时间过半、任务过半"',
                '截至 6 月底，西北有色地矿集团 712 总队公司经营收入完成年度目标的 50.22%、利润总额完成 52.12%，实体项目 93 项，新签合同总额完成年度计划的 80%；在新疆、内蒙古实现项目"零的突破"，塞拉利昂海外项目落地；技术端推广三维地质建模、千米深孔钻探与重载无人机吊运。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0911/61970.html', '中国有色金属工业协会', '09-11',
                '西北有色地矿集团研究院"科学家+工程师"团队项目获批秦创原专项立项',
                '西北有色地矿集团研究院公司联合西安交通大学申报的"基于多模态大模型的猕猴桃病害智能监测与防控"科学家+工程师团队"项目，获批 2026 年度陕西省秦创原"科学家+工程师"队伍建设专项立项，标志该集团在人工智能与地质交叉领域取得新的科研平台突破。')),

    # ---------- 09-11 下午增量：境外勘查 ----------
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104111131-amigo-resources-reports-pgm-values-of-up-to-707-ppm-in-tanzania-processing-testwork', 'SMM 国际站', '09-11',
                'Amigo Resources 坦桑尼亚项目选冶试验报出最高 7.07 ppm 铂族金属',
                'Amigo Resources 公布坦桑尼亚项目选冶试验结果，铂族金属（PGM）品位最高达 7.07 ppm，显示该项目矿石在铂族金属回收方面具有一定潜力，后续选冶流程优化与资源量估算进展值得关注。',
                orig_title='Amigo Resources Reports PGM Values of Up to 7.07 ppm in Tanzania Processing Testwork')),
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
# 2026-09-11 增：往期区内部跨源同事件再兜一次（回补的月库条目可能与已有条目同事件）
merge_seq = dedup_same_event(merge_seq)
# 今日新增与往期区互斥：同事件以「今日新增」为准，往期区让位
_new_titles = [item_title(it) for _c, it in new_items]
if _new_titles:
    merge_seq = [x for x in merge_seq
                 if not any(same_event(item_title(x[1]), _t) for _t in _new_titles)]
# 自检：今日新增内部若出现同事件重复，说明 new_items 人工挑稿有误，显式告警（不静默丢弃）
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

_buf = html.encode('utf-8')
assert len(_buf) > _ORIG_SIZE * 0.9, 'refuse to write suspiciously small index.html: %d bytes (orig %d)' % (len(_buf), _ORIG_SIZE)
with open(SRC + '.tmp', 'w', encoding='utf-8') as f:
    f.write(html)
import os
os.replace(SRC + '.tmp', SRC)

print('OK index.html -> today=%d archive=%d all=%d size=%d' % (n_today, arch_n, all_n, len(html)))
