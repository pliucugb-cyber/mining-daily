# -*- coding: utf-8 -*-
"""
生成 2026-09-05 矿业新闻日报 index.html（原地更新）
- 09-04 的"今日新增"条目滚入"往期内容"（去 NEW 标记、按同类目合并）
- 按 14 天窗口剔除往期条目（保留 >= 08-23，即 今日-13 天），月度全量在 data/news_*.json
- 换入 09-05 抓取的最新条目（is-new + NEW），更新各计数与 AI 区条数
- 更新国内期货/上金所价格卡（周六休市，沿用 09-04 收盘）；LME 行由 lme-data.js 前端动态渲染
- 保留：data-slug / digestStrip / qaFab / pchartMask / themeToggle / 正文热榜与 AI 解析区块
"""
import re, datetime

SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()

REPORT = '2026-09-05'
GRAB = '2026-09-05'
ARCHIVE_DAYS = 14          # 往期展示窗口（天）。复制本脚本出新版时只改 REPORT/GRAB/新条目，窗口自动按 REPORT 往前推 (ARCHIVE_DAYS-1) 天，勿再手写日期
REPORT_DT = datetime.date.fromisoformat(REPORT)
CUTOFF_DT = REPORT_DT - datetime.timedelta(days=ARCHIVE_DAYS - 1)   # 往期最早日期（含）；按 (年,月,日) 元组比较，正确跨年
DATA_ASOF = '09-04'         # 周六休市，国内外均无当日收盘，沿用上一交易日

# ============ 1. 标题 / 日期 / 更新时间 ============
html = html.replace('<title>矿业新闻日报 2026-09-04</title>', '<title>矿业新闻日报 %s</title>' % REPORT)
html = html.replace('2026年09月04日 星期五', '2026年09月05日 星期六')
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'更新时间：2026-09-\d{2} \d{2}:\d{2}', '更新时间：%s %s' % (REPORT, now), html)
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote">2026-09-\d{2} 更新', 'id="priceStripNote">%s 更新' % REPORT, html)

# ============ 2. 国内价格卡（09-04 收盘，周六休市） ============
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
    """条目是否在往期窗口内（含 CUTOFF_DT）。无日期的条目保留。按 (年,月,日) 元组比较，跨年不误删。"""
    m = re.search(r'</span>\s*·\s*([0-9]{2})-([0-9]{2})', it)
    if not m:
        return True
    im, id_ = int(m.group(1)), int(m.group(2))
    # 跨年处理：条目月份大于报告月份 → 视为上一年（仅对 <1 年窗口有效，14 天窗口足够）
    iy = REPORT_DT.year if im <= REPORT_DT.month else REPORT_DT.year - 1
    return (iy, im, id_) >= (CUTOFF_DT.year, CUTOFF_DT.month, CUTOFF_DT.day)

def strip_new(it):
    it = it.replace(' is-new', '')
    it = it.replace('<span class="badge-new">NEW</span>', '')
    return it

prev_today = [(cat, strip_new(it)) for cat, it in today_items if '<div class="news-item' in it]
arch_keep = [x for x in arch_items if '<div class="news-item' in x[1] and item_after_cutoff(x[1])]

# ============ 4. 今日新增条目（09-05 抓取，源文 09-03~09-04 发布，均逐页核实） ============
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
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260905_10306828.htm', '矿业权市场', '09-04',
        '四川省峨边县桥儿沟磷铅锌矿勘查探矿权挂牌出让公告',
        '四川省自然资源厅委托省政务服务和公共资源交易服务中心网上挂牌出让峨边县桥儿沟磷铅锌矿勘查探矿权，勘查矿种磷矿，区块面积29.28平方千米，起始价352万元，出让收益率磷矿2.1%、铅锌2.3%，拟出让年限5年，挂牌期2026年10月27日至11月10日，竞买保证金2000万元。')),
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260905_10306829.htm', '矿业权市场', '09-04',
        '河北省宽城满族自治县蒋杖子村金矿勘查探矿权拍卖出让公告',
        '承德市自然资源和规划局委托承德银源拍卖有限公司拍卖出让宽城满族自治县蒋杖子村金矿勘查探矿权（承矿拍〔2026〕02号），区块面积3.12平方千米，起始价9.36万元，出让收益率2.3%，拟出让年限5年，竞买保证金100万元，拍卖定于2026年10月27日在承德市公共资源交易中心举行。')),
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260905_10306831.htm', '矿业权市场', '09-04',
        '四川省会理市关河铜镍矿勘查探矿权挂牌出让公告',
        '四川省自然资源厅委托省政务服务和资源交易服务中心挂牌出让会理市关河铜镍矿勘查探矿权（川公共矿挂〔2026〕013号），勘查矿种铜矿，区块面积10.46平方千米，起始价84万元，出让收益率1.2%，拟出让年限5年，挂牌期2026年10月27日至11月10日，保证金1500万元；出让范围与国家级水土流失重点预防区重叠6.80平方千米。')),
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/ddyw/202609/t20260904_867977.html', '中国地质调查局', '09-04',
        '跑出深部找矿“中国速度”——安徽茶亭超大型铜多金属矿勘探与勘查增储纪实',
        '安徽宣州茶亭铜多金属矿为伴生银、硫的斑岩型铜金矿床，核心勘查区上长村矿段面积1.24平方千米。项目针对火山岩厚覆盖、第四系厚沉积及膏盐层难题，打破“伸展火山盆地难成大型斑岩铜金矿”理论束缚，由唐菊兴院士团队领衔，采用央地企协同、产学研用融合模式，设计钻探总量96240米、最大孔深2000米，力争一年完成常规需2至3年的工作量。')),
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kydt/kykj/202609/t20260904_10306813.htm', '全球矿产资源', '09-04',
        '埃塞俄比亚SEDEX型矿床潜力分析',
        '据Mining.com报道，分析认为埃塞俄比亚具备形成喷流沉积（SEDEX）矿床的条件：阿法尔洼地蒸发岩环境可生成高密度盐卤水作为搬运流体；阿拉伯—努比亚地盾火山沉积岩与东非大裂谷提供丰富金属源；元古代基底之上沉积的碳酸盐与碳质页岩构成还原障。恩卡法拉已有典型喷流沉积铁锰钡矿床记录，显示该区仍具SEDEX找矿潜力。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473759', '中国有色网', '09-04',
        '2026年（第二届）有色金属行业“双碳”大会在杭州召开',
        '9月4日，中国有色金属工业协会主办的第二届有色行业“双碳”大会在杭州召开。常务副会长贾明星指出行业正处从规模扩张向绿色低碳转型的关键期，提出夯实碳管理基础、以刚性约束倒逼结构调整、以碳排放双控为引领等意见；聂祚仁院士作主旨报告。近300名代表参会，同期召开铝行业节能降碳专题研讨会。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473758', '中国有色网', '09-04',
        '2026年（第十三届）中国锑业年会在云南昆明召开',
        '9月3日，以“安全、高效、可持续发展”为主题的第十三届中国锑业年会在昆明召开，300余人参会。有色协会副会长陈学森提出严守政策底线、强化行业自律严控新增产能、夯实资源保障、拓展下游应用、推进锑期货上市研究等八点建议；专家围绕出口管制合规、全球锑资源勘查开发、光伏产业形势等议题交流。')),
    (CAT_HY, ni('https://www.cgs.gov.cn/ywdt/ddyw/202609/t20260904_867980.html', '中国地质调查局', '09-04',
        '2026中国国际矿业大会将于9月10日开幕',
        '9月4日从组委会获悉，以“合作共赢，绿色智能”为主题的2026（第二十八届）中国国际矿业大会将于9月10日至12日在天津梅江会展中心举办，在往届论坛、展览两大板块基础上新增矿业权交易板块。大会设28场论坛，展览面积6.5万平方米创历届新高，已吸引全球25个国家的658家企业参展。')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202609/t20260904_10306817.htm', '全球矿产资源', '09-04',
        '国际钯价大幅上涨',
        '周四国际矿产品价格多数上涨，贵金属涨幅居前：纽约金收于4473.6美元/盎司涨1.96%，银66.96美元/盎司涨2.52%，铂1834.0美元/盎司涨3.93%，钯1440.0美元/盎司涨5.84%领涨；LME铜14356美元/吨涨0.84%、锡54750美元/吨涨1.32%；WTI原油91.66美元/桶涨1.15%，62%铁矿粉99.35美元/吨涨1.85%，铀（U3O8）89.50美元/磅持平。')),
    (CAT_ZK, ni('https://www.worldmr.net/GeologyNews/NewsList/Info/2026-09-04/325603.shtml', '全球矿产资源网', '09-04',
        '烟台金矿勘查获新突破',
        '据中国矿业报报道，中国地质调查局烟台海岸带地质调查中心承担的重要金多金属矿集区资源调查评价项目实现找矿新突破。截至目前，项目已基本查明3个完工标准图幅的区域成矿地质条件、矿产分布规律与资源禀赋特征，划定多处优质成矿有利区，为后续勘查部署与资源扩容提供了重要地质依据。')),
    (CAT_GJ, ni('https://www.worldmr.net/MRightTrade/MRightCorpList/Info/2026-09-04/325588.shtml', '全球矿产资源网', '09-04',
        '西澳格拉斯帕奇项目进展',
        '里德利山矿业公司（Mount Ridley Mines）西澳格拉斯帕奇（Grass Patch）项目推测资源量升级至9.58亿吨，钪品位0.0050%，折合钪金属量4.7万吨，公司称其为世界最大已公开钪资源量，赋存于含重稀土—镓的风化层中；自研Selectro工艺钪回收率可达80%、重稀土83%、镓56%。')),
]

def render_cat_groups(seq, mark_new=False):
    """按顺序渲染分类分组：相邻同名分类自动合并计数
    今日区显示形如「3条新增」，往期区显示形如「18条」"""
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

merge_seq = []
seen = set()
for cat, it in prev_today + arch_keep:
    if it in seen:
        continue
    seen.add(it)
    merge_seq.append((cat, it))
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
    '<div class="section-title"><span class="icon">📰</span> 往期内容（近14天自动展开，更早需点开）'
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
