# -*- coding: utf-8 -*-
"""Generate mining daily index.html for 2026-08-30 (fallback run)."""
import re
from datetime import datetime, timedelta
from pathlib import Path

OLD_INDEX = Path(r'C:\Users\windows\WorkBuddy\2026-08-25-21-20-31\output\mining-daily\index.html')
OUT_INDEX = OLD_INDEX

TODAY = datetime(2026, 8, 30)
CUTOFF = TODAY - timedelta(days=7)  # keep items >= 2026-08-23
YEAR = 2026

# ---------- New candidates from agents (already pre-filtered, URLs verbatim) ----------
NEW_CANDIDATES = [
    {'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260827_10299659.htm','title':'吉林省舒兰市长发屯地区铜及多金属矿勘查探矿权挂牌出让公告','src':'矿业权市场','date':'08-27','summary':'吉林省舒兰市长发屯地区铜及多金属矿勘查探矿权挂牌出让，起始价446万元，区域有色金属勘查持续推进。'},
    {'url':'https://www.shumx.com/kyzixun_detail/id/11194.html','title':'福建省自然资源厅矿业权出让合同管理两份文件公开征求意见','src':'上海联合矿权交易所','date':'08-24','summary':'福建省自然资源厅就矿业权出让合同管理相关文件公开征求意见，规范矿业权出让合同管理。'},
    {'url':'https://www.shumx.com/kyzixun_detail/id/11195.html','title':'自然资源部持续推进绿色矿山建设','src':'上海联合矿权交易所','date':'08-24','summary':'自然资源部介绍绿色矿山建设工作进展，推动矿业绿色低碳转型发展。'},
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473538','title':'2026年有色金属行业经济运行报告会暨有色企业统计信息发布会在济南召开','src':'中国有色网','date':'08-27','summary':'8月26日，中国有色金属工业协会主办的2026年有色金属行业经济运行报告会在济南召开，研判行业形势与高质量发展路径。'},
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473443','title':'数智赋能护航矿业高质量发展新征程 2026智能矿山高质量发展大会暨数智赋能本质安全论坛召开','src':'中国有色网','date':'08-25','summary':'8月20日，2026智能矿山高质量发展大会在辽宁丹东召开，聚焦数智赋能与矿山本质安全，铜铝锂等金属需求持续增长。'},
    {'url':'https://www.cngold.org.cn/news/show-9515.html','title':'深化产融协同 共促黄金市场高质量发展——中国黄金协会赴上海黄金交易所拜访交流','src':'中国黄金协会','date':'08-24','summary':'8月21日，中国黄金协会赴上海黄金交易所拜访交流，双方将在产业调研、风险防控、政策研究等领域协同发力。'},
    {'url':'http://www.ac-rei.org.cn/article/0a0d05a6-7f7c-4ee7-a5d6-06af20c68123','title':'2026年08月24日稀土价格指数','src':'中国稀土行业协会','date':'08-24','summary':'中国稀土行业协会发布2026年8月24日稀土价格指数为261.3，反映国内稀土市场行情变动。'},
    {'url':'https://www.geosociety.org.cn/?v1=v14&v4=v15&v2=6a8bdad842942&v3=v41&v6=1','title':'第六届“非传统稳定同位素地球化学”暑期学校在中国地质科学院京区基地举办','src':'中国地质学会','date':'08-24','summary':'第六届非传统稳定同位素地球化学暑期学校举办，系统讲解理论、分析技术及其在矿床学等领域应用。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202608/t20260827_10300644.htm','title':'国际铀价突破90美元/磅关口','src':'全球矿产资源','date':'08-27','summary':'周三国际矿产品价格多数上涨，铀价收于90.60美元/磅突破90美元关口；LME铜价持平，镍价下跌，黄金收于4593.7美元/盎司。'},
]

# ---------- Read old index ----------
html = OLD_INDEX.read_text(encoding='utf-8')
style_block = re.search(r'<style>.*?</style>', html, re.S).group(0)
script_block = re.search(r'<script>.*?</script>', html, re.S).group(0)

# ---------- Parse existing items ----------
item_pat = re.compile(
    r'<div class="news-item([^"]*)" data-url="([^"]+)"(?:\s+data-embed="([^"]+)")?[^>]*>'
    r'.*?<a class="news-title" href="([^"]+)" target="_blank">([^<]+)</a>'
    r'.*?<span class="src">([^<]+)</span>\s*·\s*([^<]+)'
    r'.*?<div class="news-summary">([^<]+)</div>',
    re.S
)
old_items = []
for m in item_pat.finditer(html):
    cls, data_url, embed, href, title, src, date, summary = m.groups()
    old_items.append({
        'url': data_url,
        'href': href,
        'title': title.strip(),
        'src': src.strip(),
        'date': date.strip(),
        'summary': summary.strip(),
        'is_new': 'is-new' in cls,
        'embed': embed or 'ok',
    })

print(f'Parsed {len(old_items)} old items')

# Correct a known broken URL from a previous generation attempt
corrections = {
    'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260827_10299659.html':
        'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260827_10299659.htm',
}
for it in old_items:
    if it['url'] in corrections:
        it['url'] = corrections[it['url']]
        it['href'] = it['url']

# ---------- Date helpers ----------
def parse_date(d):
    try:
        mm, dd = d.split('-')
        return datetime(YEAR, int(mm), int(dd))
    except Exception:
        return None

def keep_date(d):
    dt = parse_date(d)
    return dt is not None and dt >= CUTOFF

# ---------- Deduplication ----------
# Candidate URLs that belong to today's new items (they are NOT part of the 08-29 baseline)
candidate_urls = {d['url'] for d in NEW_CANDIDATES}

def norm_title(t):
    return re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9]', '', t)

# Baseline old URLs = current file URLs minus today's candidate URLs
base_old_urls = {it['url'] for it in old_items} - candidate_urls
base_old_titles_norm = {norm_title(it['title']) for it in old_items if it['url'] not in candidate_urls}

new_items = []
for d in NEW_CANDIDATES:
    if d['url'] in base_old_urls:
        print('Skip duplicate URL:', d['url'])
        continue
    nt = norm_title(d['title'])
    if nt and nt in base_old_titles_norm:
        print('Skip duplicate title:', d['title'])
        continue
    new_items.append(d)

print(f'New items after dedup: {len(new_items)}')

# Build archive from old baseline items within 7 days; exclude items that are actually today's candidates
archive_items = [it for it in old_items if it['url'] in base_old_urls and keep_date(it['date'])]
print(f'Archive items kept (>= {CUTOFF.strftime("%m-%d")}): {len(archive_items)}')

# ---------- Classification ----------
def classify(d):
    src = d.get('src','')
    title = d.get('title','')
    url = d.get('url','')
    text = title + d.get('summary','')
    if '矿业权市场' in src or '北京矿权' in src or '上海联合' in src:
        if any(k in title for k in ['探矿权','采矿权','矿业权','出让','转让','挂牌','拍卖','协议出让','成交公示']):
            return 'rights'
    if any(k in title for k in ['探矿权','采矿权','矿业权','挂牌出让','拍卖出让','协议出让','转让公示','成交公示']):
        return 'rights'
    if '全球矿产资源' in src or 'geoglobal' in url:
        return 'global'
    if any(k in title for k in ['国际','全球','海外','境外','铀价','铜产量','锌价','稀土矿','并购','收购','供应链','关键矿产']):
        return 'global'
    if '中国地质调查局' in src or 'cgs.gov.cn' in url:
        return 'explore'
    if any(k in title for k in ['找矿','勘查','勘探','矿床','新发现','资源量','储量','深部','物探','化探','钻探','超短半径','TBM']):
        return 'explore'
    if '中国地质学会' in src or 'geosociety' in url:
        return 'edu'
    if any(k in title for k in ['培训','研修','暑期学校','学术','研讨会','同位素']):
        return 'edu'
    if any(k in title for k in ['产量','利润','景气指数','分红','价格','运行报告','统计信息','产融协同','价格指数','战略合作']):
        return 'industry'
    if any(k in title for k in ['征求意见','通知','公告','政策','法规','办法','条例','规划']):
        return 'policy'
    return 'industry'

for it in new_items:
    it['cat'] = classify(it)
for it in archive_items:
    it['cat'] = classify(it)

# ---------- Build news item HTML ----------
def make_item(d, is_new):
    badge = '<span class="badge-new">NEW</span>' if is_new else ''
    url = d['url']
    embed = d.get('embed','ok')
    return (
        f'<div class="news-item{" is-new" if is_new else ""}" data-url="{url}" data-embed="{embed}">'
        f'<div class="news-head"><span class="dot"></span>{badge}<a class="news-title" href="{url}" target="_blank">{d["title"]}</a></div>'
        f'<div class="news-meta"><span class="src">{d["src"]}</span> · {d["date"]}</div>'
        f'<div class="news-summary">{d["summary"]}</div>'
        f'<a class="btn-read" href="{url}" target="_blank">查看原文 →</a>'
        f'</div>'
    )

cat_order = ['policy','explore','rights','industry','global','edu']
cat_titles = {
    'policy': '📜 政策法规',
    'explore': '🔍 找矿成果与勘查技术',
    'rights': '💼 矿权交易',
    'industry': '🏭 行业动态',
    'global': '🌐 国际矿业动态',
    'edu': '🎓 培训与学术',
}

def build_section(items, is_new):
    by_cat = {c: [it for it in items if it.get('cat')==c] for c in cat_order}
    out = ''
    for c in cat_order:
        lst = by_cat[c]
        if not lst:
            continue
        suffix = '新增' if is_new else ''
        out += f'<div class="sub-cat">{cat_titles[c]}<span class="sub-count">{len(lst)}条{suffix}</span></div>\n'
        for it in lst:
            out += make_item(it, is_new) + '\n'
    return out

today_html = build_section(new_items, True)
archive_html = build_section(archive_items, False)
new_total = len(new_items)
archive_total = len(archive_items)

# ---------- Price strip (update date only; values same as 08-29 due to weekend) ----------
price_note = f'{TODAY.strftime("%Y-%m-%d")} 晨间更新 · 沪期主力/SMM·上金所 · 涨红跌绿'

# Use the exact price strip HTML from old file but change note date
price_html = '''<div class="price-strip" id="priceStrip">
<div class="price-strip-head">
<span class="price-strip-title">📊 金属价格</span>
<span class="price-strip-note">{}</span>
</div>
<div class="price-cards">
<div class="price-card"><div class="pc-name">沪铜 <span class="pc-tag">SHFE</span></div><div class="pc-value">108,570</div><div class="pc-unit">元/吨</div><div class="pc-chg">-50 (-0.05%)</div></div>
<div class="price-card"><div class="pc-name">沪铝 <span class="pc-tag">SHFE</span></div><div class="pc-value">23,925</div><div class="pc-unit">元/吨</div><div class="pc-chg">-5 (-0.02%)</div></div>
<div class="price-card"><div class="pc-name">沪铅 <span class="pc-tag">SHFE</span></div><div class="pc-value">16,230</div><div class="pc-unit">元/吨</div><div class="pc-chg">-10 (-0.06%)</div></div>
<div class="price-card up"><div class="pc-name">沪锌 <span class="pc-tag">SHFE</span></div><div class="pc-value">26,375</div><div class="pc-unit">元/吨</div><div class="pc-chg">▲ +100 (+0.38%)</div></div>
<div class="price-card down"><div class="pc-name">沪锡 <span class="pc-tag">SHFE</span></div><div class="pc-value">417,760</div><div class="pc-unit">元/吨</div><div class="pc-chg">▼ -4,240 (-1.00%)</div></div>
<div class="price-card down"><div class="pc-name">沪镍 <span class="pc-tag">SHFE</span></div><div class="pc-value">126,750</div><div class="pc-unit">元/吨</div><div class="pc-chg">▼ -1,450 (-1.13%)</div></div>
<div class="price-card"><div class="pc-name">上海金 <span class="pc-tag">早盘价</span></div><div class="pc-value">989.36</div><div class="pc-unit">元/克</div><div class="pc-chg">早盘 989.36 / 午盘 995.35</div></div>
<div class="price-card"><div class="pc-name">白银 <span class="pc-tag">Ag(T+D)</span></div><div class="pc-value">—</div><div class="pc-unit">元/千克</div><div class="pc-chg">待更新</div></div>
<div class="price-card up"><div class="pc-name">碳酸锂 <span class="pc-tag">电池级</span></div><div class="pc-value">153,000</div><div class="pc-unit">元/吨（SMM折）</div><div class="pc-chg">▲ +555 (+0.36%)</div></div>
<div class="price-card down"><div class="pc-name">电解钴 <span class="pc-tag">SMM</span></div><div class="pc-value">305,000</div><div class="pc-unit">元/吨（SMM折）</div><div class="pc-chg">▼ -2,375 (-0.77%)</div></div>
</div>
</div>'''.format(price_note)

# Lithium/cobalt SMM折: keep old approximations. If needed compute:
# USD/CNY=6.737; battery Li 22710.41 USD/t => 153,000 CNY/t; Cobalt 45272.38*6.737=305,000.

# ---------- Static sections ----------
header_part = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#1a3a5c">
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="icon-192.png">
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="icon-512.png">
<link rel="icon" type="image/png" sizes="192x192" href="icon-192-maskable.png" purpose="maskable">
<link rel="icon" type="image/png" sizes="512x512" href="icon-512-maskable.png" purpose="maskable">
<title>矿业新闻日报 {TODAY.strftime("%Y-%m-%d")}</title>
'''

weekday_cn = ['星期一','星期二','星期三','星期四','星期五','星期六','星期日'][TODAY.weekday()]
body_start = f'''</head>
<body>
<nav class="toc-sidebar" id="tocSidebar">
<div class="toc-title">📑 目录导航</div>
<div class="toc-main-item toc-all active" onclick="showAll();window.scrollTo({{top:0,behavior:'smooth'}})">📋 全部内容 <span class="toc-count" id="tocAllCount">{new_total+archive_total}</span></div>
<div class="toc-main-item" data-target="specialSection" onclick="scrollToSection('specialSection',this)" style="color:#b45009">⛏️ 找矿专项 <span class="toc-count" id="tocSpecialCount" style="background:#fdf3d7;color:#b45009">0</span></div>
<div class="toc-main-item" data-target="todaySection" onclick="scrollToSection('todaySection',this)">🔥 今日新增 <span class="toc-count" id="tocTodayCount">{new_total}</span></div>
<div class="toc-main-item" data-target="archiveSection" onclick="scrollToSection('archiveSection',this)">📰 往期内容 <span class="toc-count" id="tocArchiveCount">{archive_total}</span></div>
<div class="toc-main-item" onclick="toggleFavFilter();window.scrollTo({{top:0,behavior:'smooth'}})" style="color:#f39c12">★ 我的收藏 <span class="toc-count" id="tocFavCount" style="background:#fef5e7;color:#f39c12">0</span></div>
<div class="toc-main-item" onclick="toggleHistoryFilter();window.scrollTo({{top:0,behavior:'smooth'}})" style="color:#8e44ad">📋 浏览记录 <span class="toc-count" id="tocHistoryCount" style="background:#f5eef8;color:#8e44ad">0</span></div>
<div class="toc-main-item" data-target="installGuideSection" onclick="scrollToSection('installGuideSection',this)" style="color:#0e7490">📲 安装到桌面 <span class="toc-count" id="tocInstallGuideCount" style="background:#e0f2fe;color:#0e7490">📘</span></div>
<div class="toc-back-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">↑ 返回顶部</div>
</nav>
<div class="container">

<div class="header">
<h1>⛏️ 矿业新闻日报 <span class="date-badge">{TODAY.strftime("%Y年%m月%d日")} {weekday_cn}</span></h1>
<div class="sub">每日 9:00 起自动更新（约 9:30 前出今日版本） · 11个信息源 · 聚焦有色金属 · 部门内部参考 · 点击标题查看原文</div>
<div class="install-tip show" id="installTip"><span id="installTipText">📲 手机：浏览器菜单选「<b>添加到桌面 / 添加书签</b>」（微信内先点右上角「···」→ 浏览器中打开）<br>💻 电脑：点 Edge/Chrome 地址栏右侧「<b>安装</b>」图标 → 变成独立窗口软件 ｜ <a href="javascript:void(0)" onclick="scrollToSection('installGuideSection',null)" style="color:#7dd3fc;text-decoration:underline">查看详细说明 ↓</a></span><button class="tip-close" onclick="dismissInstallTip()" title="我知道了">✕</button></div>
</div>
'''

stats_bar = '''<div class="stats-bar">
<div class="stat-item"><span class="stat-num new" id="newCount">0</span> 今日新增</div>
<div class="stat-item"><span class="stat-num unread" id="unreadCount">0</span> 条未读</div>
<button class="btn btn-filter" id="filterBtn" onclick="toggleFilter()">只看新增</button>
<button class="btn btn-special" id="specialBtn" onclick="toggleSpecialFilter()" title="只看与新一轮找矿突破战略行动相关的新闻" style="margin-left:8px">⛏️ 专项 <span id="specialCountNum">0</span></button>
<button class="btn btn-restore" onclick="clearAllRead()" title="一键清除所有已读记录，全部恢复为未读状态" style="margin-left:8px">↻ 全部恢复未读</button>
<button class="btn btn-fav" id="favBtn" onclick="toggleFavFilter()" style="margin-left:8px">★ 收藏 <span id="favCount">0</span></button>
<button class="btn btn-history" id="historyBtn" onclick="toggleHistoryFilter()">📋 历史 <span id="historyCount">0</span></button>
<button class="btn btn-allread" onclick="markAllRead()">✓ 全部标为已读</button>
</div>
'''

special_section = '''<!-- ==================== 新一轮找矿突破战略行动·专项 ==================== -->
<div class="section" id="specialSection">
<div class="section-title special"><span class="icon">⛏️</span> 新一轮找矿突破战略行动 · 专项<span class="news-count" id="specialCount"></span></div>
<div class="sp-cat">📌 政策与部署<span class="sub-count" id="spCount-policy">0条</span></div>
<div class="sp-list" id="spList-policy"></div>
<div class="sp-cat">🏔️ 找矿成果与新发现<span class="sub-count" id="spCount-result">0条</span></div>
<div class="sp-list" id="spList-result"></div>
<div class="sp-cat">🔬 勘查技术与装备<span class="sub-count" id="spCount-tech">0条</span></div>
<div class="sp-list" id="spList-tech"></div>
<div class="sp-cat">🌏 战略矿产与资源安全<span class="sub-count" id="spCount-security">0条</span></div>
<div class="sp-list" id="spList-security"></div>
</div>
'''

today_section_start = f'''<!-- ==================== 今日新增 ==================== -->
<div class="section" id="todaySection">
<div class="section-title today"><span class="icon">🔥</span> 今日新增（{TODAY.strftime("%Y-%m-%d")} 抓取）<span class="news-count" id="todayCount"></span></div>
'''

archive_section_start = f'''<!-- ==================== 往期内容 ==================== -->
<div class="section" id="archiveSection">
<div class="section-title"><span class="icon">📰</span> 往期内容（滚动保留最近7天）<span class="news-count" id="archiveCount">{archive_total}条</span></div>
<div class="fold-toggle" id="foldToggle" style="display:none" onclick="toggleOldFold()">▸ 展开更早内容</div>

'''

install_guide = '''<!-- ==================== 详细安装指引 ==================== -->
<div class="section" id="installGuideSection">
<div class="section-title guide"><span class="icon">📲</span> 安装到桌面 · 详细说明 <span class="news-count" style="background:#cffafe;color:#0e7490">建议收藏本页</span></div>
<div class="guide-intro">本页面是网页，<b>不需要"装软件"</b>。推荐做法：把链接<br><b>① 收藏到浏览器书签</b>（任意浏览器都行——每天打开一次即可）<br>② 或通过浏览器菜单"<b>添加到主屏幕 / 添加到桌面</b>"，桌面会出现一个图标、点图标直达、像App一样。本页面在介绍两种方式的详细操作、适用浏览器和常见坑。</div>

<div class="guide-cols">
<!-- ============== 手机端 ============== -->
<div class="guide-col mobile">
<div class="guide-col-head">📱 手机端 · 把日报添加到桌面</div>
<div class="guide-col-body">
<div class="guide-step gs-mobile"><strong>① 安卓 Chrome（最常见）</strong>右上角「⋮」（三点）→「<b>添加到主屏幕</b>」→ 可改名称（默认"矿业新闻日报"）→「<b>添加</b>」。桌面出图标，点图标直达、全屏显示。</div>
<div class="guide-step gs-mobile"><strong>①' 安卓 Edge / QQ 浏览器 / 360 极速</strong>这几种支持 <b>PWA</b>：菜单选「<b>安装应用 / 添加到主屏幕</b>」→「<b>添加</b>」。比普通"添加到主屏幕"更强——可全屏、有启动动画、离线也能开。</div>
<div class="guide-step gs-mobile"><strong>①'' 安卓三星 / 华为 / 小米 自带浏览器</strong>右上角菜单 → 找「<b>添加到主屏幕</b>」「添加书签到桌面」之类选项，名称略有差异。</div>
<div class="guide-step gs-mobile"><strong>② iPhone Safari / iPad</strong>底部工具栏「<b>分享 □↑</b>」图标 → 滚到下方找「<b>添加到主屏幕</b>」→「<b>添加</b>」。iPhone 没有 PWA 全屏，但桌面图标直达已经很方便。</div>
<div class="guide-step gs-warn"><strong>⚠️ 微信里看不到这些按钮！</strong>必须先点微信右上角「<b>···</b>」 →「<b>在浏览器中打开</b>」（若没这个选项，选「<b>复制链接</b>」→ 打开手机自带的浏览器 → 把链接粘贴进去）。</div>
<div class="guide-step"><small>💡 "添加到桌面"的桌面图标其实是<b>网页书签</b>，不是真正安装App。优点是几乎所有浏览器都支持、不占内存、即加即用；缺点是不像 PWA 那样能离线运行。</small></div>
</div>
</div>

<!-- ============== 电脑端 ============== -->
<div class="guide-col pc">
<div class="guide-col-head">💻 电脑端 · 装成独立窗口软件</div>
<div class="guide-col-body">
<div class="guide-step gs-pc"><strong>方式一：地址栏「安装」图标（推荐，最像 App）</strong>用 <b>Microsoft Edge</b> 或 <b>Google Chrome</b> 打开日报链接 → 看地址栏最右侧有没有一个<b>小方块+下载箭头</b>图标（有的浏览器显示 ⊞ 或 ⬇）→ 鼠标悬停显示「<b>安装 矿业新闻日报</b>」→ 点一下 → 弹窗确认「<b>安装</b>」。会自动：① 桌面生成图标 ②「开始菜单」里出现「矿业新闻日报」 ③ 以后双击图标就打开日报，<b>无地址栏、无标签页、全屏独立窗口</b>。</div>
<div class="guide-step gs-pc"><strong>方式二：菜单「安装」</strong>如果地址栏右侧没图标，可点浏览器右上角「···」菜单 → 找「<b>安装 矿业新闻日报</b>」或「<b>将此网站作为应用安装</b>」选项。</div>
<div class="guide-step gs-pc"><strong>方式三：Ctrl+D 收藏（兜底，所有浏览器都行）</strong>任意浏览器按 <b>Ctrl+D</b>（Mac 是 ⌘+D）→ 可改名称 → 选保存到「<b>书签栏</b>」（或收藏夹）→「完成」。每天打开浏览器点书签直达，无需安装。</div>
<div class="guide-step gs-pc"><small>✅ 支持安装 PWA 的浏览器：<b>Microsoft Edge</b>（Windows 自带，强烈推荐）、<b>Google Chrome</b>、<b>QQ 浏览器（极速模式）</b>、<b>360 极速浏览器</b>、<b>Brave</b>。<br>❌ 不支持 PWA 安装、只能用 Ctrl+D 收藏：Firefox（火狐）、Safari（Mac）、IE、360 安全浏览器。<br>💡 推荐用电脑自带的 <b>Microsoft Edge</b> 即可，零下载，Win10/11 系统自带。</small></div>
</div>
</div>
</div>

<!-- 安装 PWA 的链接 -->
<a class="guide-link" href="https://04bad6570ebc40da9fa12c25c30b6ad3.app.workbuddy.link" target="_blank">📋 复制链接到浏览器：https://04bad6570ebc40da9fa12c25c30b6ad3.app.workbuddy.link</a>

<div class="guide-tip">💡 <b>安装后怎么卸载？</b>手机：长按桌面图标选「删除」；电脑：Edge / Chrome「设置」→「应用」→「已安装的应用」→ 找"矿业新闻日报"→「卸载」。链接收藏在书签：书签栏 → 浏览器「收藏夹管理器」删。本页面随时能在浏览器输入链接打开，不会因为卸载而丢失。</div>
</div>
'''

archived_fav = '''<!-- ==================== 已归档收藏 ==================== -->
<div class="section" id="archivedFavSection" style="display:none">
<div class="section-title">🗂️ 已归档收藏（原新闻已滚出页面，收藏记录永久保留）<span class="news-count" id="archFavCount">0条</span></div>
<div id="archFavList"></div>
</div>
'''

footer = f'''<div class="footer">
<p>数据来源：自然资源部 · 中国地质调查局 · 矿业权市场 · 中国有色网 · 北京国际矿业权交易所 · 上海联合矿权交易所 · 全球矿产资源信息系统 · 中国地质学会 · 中国黄金协会 · 中国稀土行业协会 · 中国有色金属工业协会</p>
<p>聚焦有色金属：铜镍铅锌铝金银稀土钨钼锡锑锂钴 | 排除：煤炭、石油、天然气、钢铁：铁矿</p>
<p>更新时间：{TODAY.strftime("%Y-%m-%d")} 10:30 | 每日9:00起自动更新（约9:30前完成） | 11个信息源 | 本页新增：已读状态存储于访问者本机浏览器</p>
<p>📱 手机：在浏览器菜单选「<b>添加到主屏幕</b>」｜ 💻 电脑：用 Edge 或 Chrome 点击地址栏右侧「安装」图标 → 独立窗口运行 ｜ <a href="javascript:void(0)" onclick="scrollToSection('installGuideSection',null)" style="color:#1a3a5c;text-decoration:underline">详细说明 ↓</a></p>
<div style="border-top:1px solid #d5dde5;margin:14px 0 10px;padding-top:12px;text-align:left">
<p style="font-size:12px;color:#5b6b7a;line-height:1.8"><b style="color:#3a4a5a">版权与免责声明</b><br>
本页面信息均来源于互联网公开渠道，包括但不限于中国政府机构、行业协会、权威媒体的官方网站及公开新闻报道。所有著作权及其他权利归原机构 / 原媒体所有。<br>
本站仅作<b>信息聚合展示</b>，不存储完整原文，不作任何商业用途；通过「查看原文」链接引导读者返回原网站阅读，以尊重原网站访问流量与运营收益。<br>
如原权利人认为本站所展示的内容存在侵权，请通过邮箱 <a href="mailto:1642988981@qq.com" style="color:#1a3a5c;text-decoration:underline">1642988981@qq.com</a> 联系我们，并提供：① 权利人身份证明；② 涉嫌侵权内容的页面链接；③ 要求删除的具体说明。我们将在收到通知后 <b>3 个工作日内</b>核实并处理。<br>
本站不对所聚合信息的及时性、准确性、完整性作担保；如因信息源变更导致链接失效，概与本站无关。</p>
</div>
</div>
</div>
'''

# ---------- Assemble ----------
new_html = (
    header_part
    + style_block + '\n'
    + body_start
    + price_html + '\n'
    + stats_bar
    + special_section
    + today_section_start
    + today_html
    + '</div>\n\n'
    + archive_section_start
    + archive_html
    + '</div>\n\n'
    + install_guide
    + archived_fav
    + footer
    + script_block + '\n'
    + '</body>\n</html>\n'
)

OUT_INDEX.write_text(new_html, encoding='utf-8')
print(f'Wrote {OUT_INDEX} ({len(new_html)} chars)')
print(f'Today new: {new_total}, Archive: {archive_total}')
