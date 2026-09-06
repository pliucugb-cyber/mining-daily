# -*- coding: utf-8 -*-
"""
生成 2026-09-06 矿业新闻日报 index.html（原地更新）
- 09-05 的"今日新增"条目滚入"往期内容"（去 NEW 标记、按同类目合并）
- 按 7 天窗口剔除往期条目（保留 >= 08-31，即 今日-6 天），月度全量在 data/news_*.json
- 换入 09-06 抓取的最新条目（is-new + NEW），更新各计数与 AI 区条数
- 周日休市，国内外均无当日收盘，价格卡沿用 09-04（上一交易日）收盘
- 保留：data-slug / digestStrip / qaFab / pchartMask / themeToggle / 正文热榜与 AI 解析区块

【补跑说明】本脚本由 10:00 复核任务补跑：09:00 那轮未跑成功（标题与 morning_report 仍停留在 09-05）。
"""
import re, datetime

SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()

REPORT = '2026-09-06'
GRAB = '2026-09-06'
ARCHIVE_DAYS = 7          # 往期展示窗口（天）
REPORT_DT = datetime.date.fromisoformat(REPORT)
CUTOFF_DT = REPORT_DT - datetime.timedelta(days=ARCHIVE_DAYS - 1)   # 往期最早日期（含）
DATA_ASOF = '09-04'       # 周日休市，国内外均无当日收盘，沿用上一交易日

# ============ 1. 标题 / 日期 / 更新时间 ============
html = html.replace('<title>矿业新闻日报 2026-09-05</title>', '<title>矿业新闻日报 %s</title>' % REPORT)
html = html.replace('2026年09月05日 星期六', '2026年09月06日 星期日')
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'更新时间：2026-09-\d{2} \d{2}:\d{2}', '更新时间：%s %s' % (REPORT, now), html)
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote">2026-09-\d{2} 更新', 'id="priceStripNote">%s 更新' % REPORT, html)
html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
              'name="build-version" content="%s-%s"' % (REPORT.replace('-', ''), now.replace(':', '')), html)

# ============ 2. 国内价格卡（09-04 收盘，周日休市） ============
def card(slug, css, name, tag, value, unit, chg):
    return ('<div data-slug="%s" class="price-card %s"><div class="pc-name">%s <span class="pc-tag">%s</span></div>'
            '<div class="pc-value">%s</div><div class="pc-unit">%s</div><div class="pc-chg">%s</div></div>'
            % (slug, css, name, tag, value, unit, chg))

cards = [
    card('cum',    'up',   '沪铜',   'SHFE',      '108,780', '元/吨',   '&#9650; +370 (+0.34%)'),
    card('alm',    'down', '沪铝',   'SHFE',      '24,290',  '元/吨',   '&#9660; -80 (-0.33%)'),
    card('pbm',    'up',   '沪铅',   'SHFE',      '16,130',  '元/吨',   '&#9650; +10 (+0.06%)'),
    card('znm',    'up',   '沪锌',   'SHFE',      '26,745',  '元/吨',   '&#9650; +135 (+0.51%)'),
    card('snm',    'up',   '沪锡',   'SHFE',      '416,460', '元/吨',   '&#9650; +370 (+0.09%)'),
    card('nim',    'down', '沪镍',   'SHFE',      '127,780', '元/吨',   '&#9660; -1,110 (-0.86%)'),
    card('au9999', 'up',   '上海金', 'Au99.99',   '965.96',  '元/克',   '&#9650; +0.79%'),
    card('agtd',   'up',   '白银',   'Ag(T+D)',   '16,250',  '元/千克', '&#9650; +1.28%'),
    card('lcm',    'down', '碳酸锂', '主力连续',  '141,940', '元/吨',   '&#9660; -7,940 (-5.30%)'),
]
# 电解钴：SMM 周末无更新，沿用上日数值并标注
cards.append('<div class="price-card "><div class="pc-name">电解钴 <span class="pc-tag">SMM %s</span></div>'
             '<div class="pc-value">304,940</div><div class="pc-unit">元/吨</div>'
             '<div class="pc-chg">上日 304,940（SMM 未更新）</div></div>' % DATA_ASOF)

new_cards = '<div class="price-cards" id="priceCardsShfe">' + ''.join(cards) + '</div>\n'
html = re.sub(r'<div class="price-cards" id="priceCardsShfe">.*?(?=<div class="price-cards" id="priceCardsLme")',
              lambda m: new_cards, html, flags=re.DOTALL)

# ============ 3. 解析今日/往期两个区 ============
TAG_TODAY = '<div class="section" id="todaySection">'
TAG_ARCH  = '<div class="section" id="archiveSection">'
TAG_INST  = '<div class="section" id="installGuideSection">'
i_t = html.find(TAG_TODAY)
i_a = html.find(TAG_ARCH)
i_i = html.find(TAG_INST)
assert 0 <= i_t < i_a < i_i, 'markers not found'

today_raw = html[i_t:i_a]
arch_raw  = html[i_a:i_i]

def split_items(block):
    """按 (cat, subcount) 与 news-item 顺序切分，返回 items[(cat, htmlitem)] 序列"""
    out = []
    cat = None
    for mm in re.finditer(r'<div class="sub-cat">([^<]*)<span class="sub-count">([^<]*)</span></div>'
                          r'|<div class="news-item[^>]*>.*?(?=<div class="news-item|<div class="sub-cat|<div class="fold-toggle|</div>\s*</div>)',
                          block, re.S):
        if mm.group(1) is not None:
            cat = mm.group(1).strip()
        else:
            if cat:
                out.append((cat, mm.group(0)))
    return out

today_items = split_items(today_raw)
arch_items  = split_items(arch_raw)

def item_after_cutoff(it):
    """条目是否在 7 日往期窗口内（含 CUTOFF_DT）。无日期的条目保留。"""
    m = re.search(r'</span>\s*·\s*([0-9]{2})-([0-9]{2})', it)
    if not m:
        return True
    im, id_ = int(m.group(1)), int(m.group(2))
    iy = REPORT_DT.year if im <= REPORT_DT.month else REPORT_DT.year - 1
    return (iy, im, id_) >= (CUTOFF_DT.year, CUTOFF_DT.month, CUTOFF_DT.day)

def item_url(it):
    m = re.search(r'data-url="([^"]+)"', it)
    return m.group(1) if m else it

def strip_new(it):
    it = it.replace(' is-new', '')
    it = it.replace('<span class="badge-new">NEW</span>', '')
    return it

prev_today = [(cat, strip_new(it)) for cat, it in today_items if '<div class="news-item' in it]
arch_keep = [x for x in arch_items if '<div class="news-item' in x[1] and item_after_cutoff(x[1])]

merge_seq = []
seen_url = set()
for cat, it in prev_today + arch_keep:
    url = item_url(it)
    if url in seen_url:
        continue
    seen_url.add(url)
    merge_seq.append((cat, it))

# ============ 4. 今日新增条目（09-06 抓取，均逐页核实标题/日期/正文） ============
def ni(url, src, date, title, summary, embed='ok'):
    return ('<div class="news-item is-new" data-url="%s" data-embed="%s"><div class="news-head"><span class="dot"></span>'
            '<span class="badge-new">NEW</span><a class="news-title" href="%s" target="_blank">%s</a></div>'
            '<div class="news-meta"><span class="src">%s</span> · %s</div><div class="news-summary">%s</div>'
            '<a class="btn-read" href="%s" target="_blank">查看原文 →</a></div>'
            % (url, embed, url, title, src, date, summary, url))

CAT_KQ = '💼 矿权交易'
CAT_ZK = '🔍 找矿成果与勘查技术'
CAT_HY = '🏭 行业动态'
CAT_GJ = '🌐 国际矿业动态'

new_items = [
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260905_10306830.htm', '矿业权市场', '09-04',
        '四川省丹巴县天宝洞金矿勘查探矿权挂牌出让公告',
        '受四川省自然资源厅委托，四川省政府政务服务和公共资源交易服务中心网上挂牌出让丹巴县天宝洞金矿勘查探矿权（川公共矿挂〔2026〕011号），区块面积15.93平方千米，起始价128万元，起始出让收益率2.3%，拟出让年限5年，竞买保证金1500万元。')),
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260905_10306827.htm', '矿业权市场', '09-04',
        '四川省乐山市金口河区鲤鱼堡铅锌矿勘查探矿权挂牌出让公告',
        '四川省政府政务服务和公共资源交易服务中心挂牌出让乐山市金口河区鲤鱼堡铅锌矿勘查探矿权（川公共矿挂〔2026〕010号），区块面积10.80平方千米，起始价87万元，出让收益率2.3%，拟出让年限5年，竞买保证金1500万元；公告明确本区块不接受外商和外资参与竞买。')),
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260905_10306826.htm', '矿业权市场', '09-04',
        '河北省滦平县安纯沟门乡大西沟金矿勘查探矿权拍卖出让公告',
        '承德市公共资源交易中心委托承德银源拍卖有限公司拍卖出让滦平县安纯沟门乡大西沟金矿勘查探矿权（承矿拍〔2026〕03号），区块面积4.37平方千米，起始价26.22万元，出让收益率2.3%，拟出让年限5年，竞买保证金100万元，保证金缴纳截止2026年10月26日16时。')),
    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260905_10306820.htm', '矿业权市场', '09-04',
        '内蒙古自治区扎赉特旗黑大山金铜多金属矿勘查探矿权转让公示',
        '兴安盟自然资源局公示扎赉特旗黑大山金铜多金属矿勘查探矿权转让（内自然资探转示〔2026〕026号），转让人为喀喇沁旗天成美石有限责任公司，受让人为嘉石矿业（兴安盟扎赉特旗）有限公司，勘查面积34.417平方千米，发证机关为内蒙古自治区自然资源厅，探矿权有效期自2026年7月30日起。')),
    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260904_10305942.htm', '矿业权市场', '09-03',
        '吉林省临江市小栗子银多金属矿详查探矿权转让公示',
        '白山市自然资源局公示临江市小栗子银多金属矿详查探矿权转让（白山自然资探转〔2026〕1号），转让人为吉林星泰集团有限公司，勘查面积1.237平方千米，探矿权有效期自2026年7月9日起，依据《矿产资源法实施条例》《矿业权出让交易规则》办理。')),
    (CAT_ZK, ni('https://www.worldmr.net/Industry/IndustryList/Info/2026-09-04/325571.shtml', '全球矿产资源网', '09-04',
        '低品位难选铁矿有望成“富矿”',
        '据中国矿业报，全球规模最大的难选铁矿流态化磁化焙烧工程在辽宁鞍山通过竣工验收，年处理556万吨并连续稳定运行、全面达产。中科院过程工程研究所朱庆山团队攻关20余年，从含铁仅11%的铁尾矿中稳定产出品位65%的铁精矿，铁矿物相转化率达98%，综合能耗较同类技术低35%；项目入选国家发改委首批绿色低碳先进技术示范清单，有望带动国内近300亿吨难选铁矿和近100亿吨含铁尾矿开发，并已与老挝签订褐铁矿焙烧提质项目。')),
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/ddyw/202609/t20260904_867978.html', '中国地质调查局', '09-04',
        '中国地质调查局实施吉隆泥石流次生地质灾害监测',
        '受西藏吉隆口岸“8·26”冰岩崩—泥石流灾害链持续影响，源区残留不稳定冰川与岩体，存在冰岩崩、泥石流、滑坡—堰塞湖等次生风险。由中国工程院院士殷跃平牵头、中国地质调查局18名技术专家组成团队，在错坚河口至拉比村核心风险带布设边坡雷达、雷视一体监测仪、微震监测仪，并在色琼村同步部署监测河道水位与断面变化，实现24小时全自动观测与智能预警。')),
    (CAT_HY, ni('https://www.worldmr.net/Industry/IndustryList/Info/2026-09-04/325572.shtml', '全球矿产资源网', '09-04',
        '从粗放开采到绿色高效',
        '我国矿山生产加速由经验驱动转向数据驱动：浙江交投矿业搭建“一个中心、一套模型、四大平台、N个子系统”智能架构，依托三维实景模型模拟推演开采方案，调度效率提升10%；湖州新开元碎石构建矿山三维动态地质孪生模型，创新“四量四率”量化管理，生产管控效率提升四成；嵩县山金运用Vulcan三维软件建资源数据库并实现关键固定设备无人值守，西部矿业锡铁山铅锌矿建成智慧矿山管控平台。')),
    (CAT_HY, ni('https://www.worldmr.net/MRightTrade/MRightCorpList/Info/2026-09-04/325598.shtml', '全球矿产资源网', '09-04',
        '贵州推动非常规天然气增储上产',
        '贵州省人民政府办公厅印发《贵州省非常规天然气增储上产三年攻坚行动方案（2026—2028年）》，聚焦页岩气、煤层气（煤矿瓦斯）系统推进勘探、开发、储运、利用全链条建设，部署六大方面15条举措：统筹资源储备扩容与产能释放、优化矿产资源管理整治矿业权低效利用、深化地质勘探夯实深部油气开发基础、推进煤气共采由井下被动抽采转向地面主动预抽、推进全省天然气管道“一张网”、强化科技攻关与成果转化。')),
    (CAT_GJ, ni('https://www.worldmr.net/MRightTrade/MRightCorpList/Info/2026-09-04/325589.shtml', '全球矿产资源网', '09-04',
        '紫金矿业：高位进阶后的“韧性突围”',
        '紫金矿业2025年年度股东会披露新一届管理层“三年规划和十年远景目标”：到2028年铜、金矿产品产量进入全球前3位，到2035年全面建成“绿色高技术超一流国际矿业集团”。董事长邹来昌表示增长策略新增“上产”维度，把握金属价格高企机遇加快释放产能、以规模效应摊薄固定成本；一季度主营金属产量高位抬升，利润突破200亿元创历史新高、同比近乎翻番。')),
]

def render_cat_groups(seq, mark_new=False):
    suffix = '条新增' if mark_new else '条'
    order, groups = [], {}
    for cat, it in seq:
        if cat not in groups:
            groups[cat] = []
            order.append(cat)
        groups[cat].append(it)
    out = []
    for cat in order:
        items = groups[cat]
        n = len(items)
        out.append('<div class="sub-cat">%s<span class="sub-count">%d%s</span></div>\n' % (cat, n, suffix))
        out.extend(items)
    return out

unique_new = []
new_seen_url = set()
for cat, it in new_items:
    url = item_url(it)
    if url in new_seen_url:
        continue
    new_seen_url.add(url)
    unique_new.append((cat, it))
new_items = unique_new

merge_seq = [x for x in merge_seq if item_url(x[1]) not in new_seen_url]

arch_groups = render_cat_groups(merge_seq, mark_new=False)
today_groups = render_cat_groups(new_items, mark_new=True)

# ============ 5. 拼装新区 ============
n_today = len(new_items)
arch_n  = len(merge_seq)
all_n   = n_today + arch_n

new_today_block = ('<!-- ==================== 今日新增（%s 抓取） ==================== -->\n' % GRAB +
    '<div class="section" id="todaySection">\n'
    '<div class="section-title today"><span class="icon">🔥</span> 今日新增（%s 抓取）<span class="news-count" id="todayCount">%d条</span></div>\n'
    % (GRAB, n_today) + ''.join(today_groups) + '</div>\n')

new_arch_block = ('<!-- ==================== 往期内容 ==================== -->\n'
    '<div class="section" id="archiveSection">\n'
    '<div class="section-title"><span class="icon">📰</span> 往期内容（滚动保留最近7天）'
    '<span class="news-count" id="archiveCount">%d条</span></div>\n'
    '<div class="fold-toggle" id="foldToggle" style="display:none" onclick="toggleOldFold()">▸ 展开更早内容</div>\n'
    % arch_n + ''.join(arch_groups) + '</div>\n')

html = html[:i_t] + new_today_block + new_arch_block + html[i_i:]

# ============ 6. 更新计数与 AI 提示 ============
html = re.sub(r'id="tocAllCount">\d+<', 'id="tocAllCount">%d<' % all_n, html)
html = re.sub(r'id="tocTodayCount">\d+<', 'id="tocTodayCount">%d<' % n_today, html)
html = re.sub(r'id="tocArchiveCount">\d+<', 'id="tocArchiveCount">%d<' % arch_n, html)
html = re.sub(r'今日 \d+ 条新闻的智能解读', '今日 %d 条新闻的智能解读' % n_today, html)

with open(SRC, 'w', encoding='utf-8') as f:
    f.write(html)

print('OK index.html -> today=%d archive=%d all=%d size=%d' % (n_today, arch_n, all_n, len(html)))
