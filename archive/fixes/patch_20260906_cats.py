# -*- coding: utf-8 -*-
"""
2026-09-06 今日区分类修正补丁（在 10:00 补跑已完成的基础上做增量修正，不重建整页）
问题：补跑版把「紫金矿业：高位进阶后的"韧性突围"」（中国企业）归入 🌐 国际矿业动态，
      导致国际类仅 1 条且分类错误，四类配比失衡。
修正：
  1) 紫金矿业条目改回 🏭 行业动态
  2) 补入 2 条已逐页核实的真实国际矿业动态（政府干预关键矿产 / 艾佩里昂美军钛合同）
  3) 同步 todayCount / tocTodayCount / tocAllCount / AI 条数 / 更新时间
修正后配比：矿权 5 · 找矿 2 · 行业 3 · 国际 2 = 12 条
"""
import re, datetime

SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()

REPORT = '2026-09-06'
CAT_KQ = '💼 矿权交易'
CAT_ZK = '🔍 找矿成果与勘查技术'
CAT_HY = '🏭 行业动态'
CAT_GJ = '🌐 国际矿业动态'

TAG_TODAY = '<div class="section" id="todaySection">'
TAG_ARCH  = '<div class="section" id="archiveSection">'
i_t = html.find(TAG_TODAY)
i_a = html.find(TAG_ARCH)
assert 0 <= i_t < i_a, 'markers not found'
today_raw = html[i_t:i_a]

# ---------- 解析今日区 ----------
def split_items(block):
    out, cat = [], None
    for mm in re.finditer(r'<div class="sub-cat">([^<]*)<span class="sub-count">([^<]*)</span></div>'
                          r'|<div class="news-item[^>]*>.*?(?=<div class="news-item|<div class="sub-cat|</div>\s*</div>)',
                          block, re.S):
        if mm.group(1) is not None:
            cat = mm.group(1).strip()
        elif cat:
            out.append((cat, mm.group(0)))
    return out

def item_url(it):
    m = re.search(r'data-url="([^"]+)"', it)
    return m.group(1) if m else ''

items = split_items(today_raw)

# ---------- 1) 紫金矿业：国际 -> 行业 ----------
moved = 0
fixed = []
for cat, it in items:
    if '325589' in item_url(it) and cat == CAT_GJ:
        fixed.append((CAT_HY, it))
        moved += 1
    else:
        fixed.append((cat, it))
items = fixed
print('紫金矿业条目重分类：%d 条' % moved)

# ---------- 2) 补入 2 条国际矿业动态（均已逐页核实标题/日期/正文） ----------
def ni(url, src, date, title, summary, embed='ok'):
    return ('<div class="news-item is-new" data-url="%s" data-embed="%s"><div class="news-head"><span class="dot"></span>'
            '<span class="badge-new">NEW</span><a class="news-title" href="%s" target="_blank">%s</a></div>'
            '<div class="news-meta"><span class="src">%s</span> · %s</div><div class="news-summary">%s</div>'
            '<a class="btn-read" href="%s" target="_blank">查看原文 →</a></div>'
            % (url, embed, url, title, src, date, summary, url))

add = [
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260903_10305931.htm', '全球矿产资源', '09-03',
        '政府干预关键矿产“前所未有”',
        '据Mining.com报道，各国政府不再是传统贷款方，而是直接参与采矿和关键矿产交易，以保障战略供应链安全并改变项目融资方式。2月美国总统特朗普宣布启动“金库计划”，出资120亿美元支持关键矿产战略储备。Fastmarkets统计显示，自2025年1月以来与矿产相关的协议约160个、总额近400亿美元。政府更多采用股权、保底价和长期承购协议等商业投资模式，公共资本与私人资本联手形成混合资本。')),
    (CAT_GJ, ni('https://www.worldmr.net/MRightTrade/MRightCorpList/Info/2026-09-02/325521.shtml', '全球矿产资源网', '09-02',
        '艾佩里昂公司获美军钛供应研发合同',
        '据Mining.com报道，艾佩里昂公司（IperionX）宣布美军已向其授予一份小企业创新研究（SBIR）合同，用于探索国防用低成本钛的国内供应。钛因独特的强度重量比和耐腐蚀性被美国、欧盟和加拿大列为关键矿产。这是该公司第二份SBIR合同，使美国政府机构可下达总额不超过9900万美元的特定项目订单，任务订单1和2总额约1980万美元。')),
]

# 去重：已存在的 URL 不重复加入
have = {item_url(it) for _, it in items}
for cat, it in add:
    if item_url(it) not in have:
        items.append((cat, it))
    else:
        print('  跳过已存在：', item_url(it))

# ---------- 3) 重渲染分组 ----------
def render_cat_groups(seq):
    order, groups = [], {}
    for cat, it in seq:
        if cat not in groups:
            groups[cat] = []
            order.append(cat)
        groups[cat].append(it)
    out = []
    for cat in order:
        n = len(groups[cat])
        out.append('<div class="sub-cat">%s<span class="sub-count">%d条新增</span></div>\n' % (cat, n))
        out.extend(groups[cat])
    return out, {c: len(v) for c, v in groups.items()}

body, counts = render_cat_groups(items)
n_today = len(items)
print('今日配比：', {k: v for k, v in counts.items()}, '合计', n_today)

# ---------- 4) 拼装今日区（保留原 section 头部，仅换 count） ----------
first_sub = today_raw.find('<div class="sub-cat">')
assert first_sub > 0
head = today_raw[:first_sub]
head = re.sub(r'id="todayCount">\d+条<', 'id="todayCount">%d条<' % n_today, head)
new_today = head + ''.join(body) + '</div>\n'

html = html[:i_t] + new_today + html[i_a:]

# ---------- 5) 同步各处计数与更新时间 ----------
now = datetime.datetime.now().strftime('%H:%M')
n_arch = int(re.search(r'id="tocArchiveCount">(\d+)<', html).group(1))
html = re.sub(r'id="tocTodayCount">\d+<', 'id="tocTodayCount">%d<' % n_today, html)
html = re.sub(r'id="tocAllCount">\d+<', 'id="tocAllCount">%d<' % (n_today + n_arch), html)
html = re.sub(r'今日 \d+ 条新闻的智能解读', '今日 %d 条新闻的智能解读' % n_today, html)
html = re.sub(r'更新时间：%s \d{2}:\d{2}' % REPORT, '更新时间：%s %s' % (REPORT, now), html)
html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
              'name="build-version" content="%s-%s"' % (REPORT.replace('-', ''), now.replace(':', '')), html)

with open(SRC, 'w', encoding='utf-8') as f:
    f.write(html)

print('OK patch -> today=%d archive=%d all=%d size=%d' % (n_today, n_arch, n_today + n_arch, len(html)))
