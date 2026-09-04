# -*- coding: utf-8 -*-
"""
生成 2026-09-04 矿业新闻日报 index.html（原地更新）
- 09-03 的"今日新增"条目滚入"往期内容"（去 NEW 标记、按同类目合并）
- 按 7 天窗口剔除往期条目（保留 08-28 及以后），月度全量在 data/news_*.json
- 换入 09-04 抓取的最新条目（is-new + NEW），更新各计数与 AI 区条数
- 更新国内期货/上金所价格卡（2026-09-04 盘中）；LME 行由 lme-data.js 前端动态渲染
"""
import re, datetime

SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()

REPORT = '2026-09-04'
GRAB = '2026-09-04'
WIN_FROM = '08-28'          # 7 天滚动窗口：保留 >= 08-28（月份同为 2026-09/08 当期）

# ============ 1. 标题 / 日期 / 更新时间 ============
html = html.replace('<title>矿业新闻日报 2026-09-03</title>', '<title>矿业新闻日报 2026-09-04</title>')
html = html.replace('2026年09月03日 星期四', '2026年09月04日 星期五')
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'更新时间：2026-09-04 \d{2}:\d{2}', '更新时间：2026-09-04 ' + now, html)
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)

# ============ 2. 价格条说明 + 国内价格卡 ============
def card(css, name, tag, value, unit, chg):
    return ('<div class="price-card %s" data-slug="%s"><div class="pc-name">%s <span class="pc-tag">%s</span></div>'
            '<div class="pc-value">%s</div><div class="pc-unit">%s</div><div class="pc-chg">%s</div></div>'
            % (css, '', name, tag, value, unit, chg))

cards = []
cards.append(card('up', '沪铜', 'SHFE', '108,780', '元/吨', '&#9650; +240 (+0.22%)'))
cards.append(card('up', '沪铝', 'SHFE', '24,290', '元/吨', '&#9650; +15 (+0.06%)'))
cards.append(card('up', '沪铅', 'SHFE', '16,130', '元/吨', '&#9650; +15 (+0.09%)'))
cards.append(card('up', '沪锌', 'SHFE', '26,745', '元/吨', '&#9650; +115 (+0.43%)'))
cards.append(card('up', '沪锡', 'SHFE', '416,460', '元/吨', '&#9650; +1,160 (+0.28%)'))
cards.append(card('down', '沪镍', 'SHFE', '127,780', '元/吨', '&#9660; -930 (-0.72%)'))
cards.append(card('up', '上海金', 'Au99.99', '964.40', '元/克', '&#9650; +0.72%'))
cards.append(card('up', '白银', 'Ag(T+D)', '16,229', '元/千克', '&#9650; +1.53%'))
cards.append(card('down', '碳酸锂', '主力连续', '141,940', '元/吨', '&#9660; -11,360 (-7.41%)'))
cards.append(card('', '电解钴', 'SMM 09-03', '304,940', '元/吨', '上日 304,940（SMM 未更新）'))
new_cards = '<div class="price-cards" id="priceCardsShfe">' + ''.join(cards) + '</div>\n'
html = re.sub(r'<div class="price-cards" id="priceCardsShfe">.*?(?=<div class="price-cards" id="priceCardsLme")',
              lambda m: new_cards, html, flags=re.DOTALL)

# ============ 3. 解析今日/往期两个区 ============
def _next(html, s, pat):
    m = re.search(pat, html[s:])
    return s + m.start() if m else -1

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
    pos = 0
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

def item_date(it):
    m = re.search(r'</span>\s*·\s*([0-9]{2}-[0-9]{2})', it)
    return m.group(1) if m else '99-99'

def strip_new(it):
    it = it.replace(' is-new', '')
    it = it.replace('<span class="badge-new">NEW</span>', '')
    it = it.replace('<div class="news-head"><span class="dot"></span>', '<div class="news-head"><span class="dot"></span>')
    return it

# 今日区内容（上一期 7 条）转往期
prev_today = [(cat, strip_new(it)) for cat, it in today_items if '<div class="news-item' in it]
# 往期窗口滚动：剔除 08-27 及更早（跨月时同月比较；因窗口都在 2026-08/09 内，直接比 MM-DD）
arch_keep = [x for x in arch_items if '<div class="news-item' in x[1] and item_date(x[1]) >= WIN_FROM]

# ============ 4. 今日新增条目（09-04 抓取） ============
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
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260904_10305955.htm', '矿业权市场', '09-03',
        '新疆皮山县库尔良铜矿勘查探矿权挂牌出让公告',
        '新疆维吾尔自治区自然资源厅委托自治区公共资源交易中心挂牌出让皮山县库尔良铜矿勘查探矿权，区块面积39.42平方千米，起始价118.27万元，出让收益率1.2%，拟出让年限5年，挂牌期2026年10月21日至11月4日。')),
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260904_10305949.htm', '矿业权市场', '09-03',
        '内蒙古巴林右旗巴彦琥硕银矿勘查探矿权挂牌出让公告',
        '赤峰市自然资源局委托赤峰市公共资源交易中心网上挂牌出让巴彦琥硕银矿勘查探矿权（赤公矿交告〔2026〕001号），区块面积6.30平方千米，起始价38万元，出让收益率2.3%，拟出让年限5年，挂牌期2026年10月23日至11月6日。')),
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/xfx/202609/t20260903_10305932.htm', '全球矿产资源', '09-03',
        '澳大利亚延达尔金矿勘探取得新发现',
        '盖特维矿业（Gateway Mining）宣布西澳延达尔（Yandal）金矿项目考扎（Cowza）探区取得重大高品位原生金矿发现，钻孔在104米深处见矿41米、金品位2克/吨；连同赛利亚南、沃德靶区，延达尔构造带延伸长度已超13公里，后续将开展金刚石钻探。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0903/61913.html', '中国有色金属工业协会', '09-03',
        '薪火代代传——驰宏锌锗以“0.3克锗精神”续写科研攻坚答卷',
        '从1958年乌蒙山简陋实验室提取0.3克金属锗起步，驰宏锌锗现年产锗产品含锗65吨、稳居全球原生锗产业第一梯队；自主研发的沉锗工艺为全球独有，并正以一步法直接蒸馏技术填补国内低品位锗料高效处置空白。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0903/61904.html', '中国有色金属工业协会', '09-03',
        '2026矿冶科技集团有限公司科技创新大会在京召开',
        '矿冶集团科技创新大会8月28日在京召开，部署“十五五”时期集团科技创新重点任务，发布集团志《走向辉煌（2016—2026）》与“十五五”品牌战略规划，并同期举办采矿工程、选矿工程、冶金环境、新材料4个分论坛。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0903/61902.html', '中国有色金属工业协会', '09-03',
        '有色企业紧急捐款驰援西藏吉隆灾区',
        '尼泊尔侧泥石流灾害造成西藏日喀则吉隆口岸重大人员伤亡后，有色企业紧急驰援：中国铝业携中国铜业捐赠2000万元，中国黄金集团1500万元，魏桥创业1000万元，紫金矿业1000万元，用于抢险救援与灾后重建。')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260903_10305931.htm', '全球矿产资源', '09-03',
        '政府干预关键矿产“前所未有”',
        '据Mining.com报道，各国政府正从单纯贷款转向股权、保底价与长期承购等商业投资模式直接介入采矿与关键矿产交易；美国2月启动120亿美元“金库计划”，快市统计2025年1月以来矿产相关协议约160个、总额近400亿美元，激励与禁购并举的模式被指“前所未有”。')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202609/t20260903_10305934.htm', '全球矿产资源', '09-03',
        '国际贵金属价格回升',
        '周三国际矿产品价格多数下跌、贵金属普遍上涨：纽约金收于4387.8美元/盎司涨1.36%，银65.32美元/盎司涨1.95%，钯涨2.25%；LME铜14236美元/吨涨0.35%，铝3292.5美元/吨涨0.61%，镍16890美元/吨涨1.35%，铅、锌、锡小幅走低；铀（U3O8）收89.50美元/磅。')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202609/t20260903_10305933.htm', '全球矿产资源', '09-03',
        '格陵兰资源公司获最高1.2亿美元融资意向 推进马尔姆杰格钼镁项目',
        '加拿大初级矿业公司格陵兰资源收到北欧投资银行（NIB）最高1.2亿美元融资意向书，为加拿大EDC牵头2.75亿美元支持的补充；马尔姆杰格钼镁项目已完成最终可行性研究，钼金属储量5.71亿磅，前10年年均产钼精矿3280万磅，约为欧盟年消费量的25%。')),
]

def render_cat_groups(seq, mark_new=False, suffix='条'):
    """按顺序渲染分类分组：相邻同名分类自动合并计数"""
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
        flag = '新增' if mark_new else ''
        out.append('<div class="sub-cat">%s<span class="sub-count">%d%s%s</span></div>\n' % (cat, n, flag, suffix))
        out.extend(items)
    return out

# 往期合并：上一期今日 → 往期顶部；与旧往期按分类合并
merge_seq = []
seen = set()
for cat, it in prev_today + arch_keep:
    if it in seen:
        continue
    seen.add(it)
    merge_seq.append((cat, it))
arch_groups = render_cat_groups(merge_seq, mark_new=False, suffix='条')

today_groups = render_cat_groups(new_items, mark_new=True, suffix='新增')

# ============ 5. 拼装新区 ============
n_today = sum(len(g) for g in [x for x in []] ) or len(new_items)
arch_n   = len(merge_seq)
all_n    = n_today + arch_n

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
