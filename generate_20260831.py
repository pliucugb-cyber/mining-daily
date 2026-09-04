# -*- coding: utf-8 -*-
"""Generate mining daily index.html for 2026-08-31 (fallback run)."""
import re
from datetime import datetime, timedelta
from pathlib import Path

OLD_INDEX = Path(r'C:\Users\windows\WorkBuddy\2026-08-25-21-20-31\output\mining-daily\index.html')
OUT_INDEX = OLD_INDEX

TODAY = datetime(2026, 8, 31)
CUTOFF = TODAY - timedelta(days=7)  # keep items >= 2026-08-24
YEAR = 2026

# ---------- New candidates from agents (already pre-filtered, URLs verbatim) ----------
NEW_CANDIDATES = [
    # 矿业权市场
    {'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260828_10300653.htm','title':'湖南省株洲市芦淞区长垅矿区金矿普查探矿权网上挂牌出让公告','src':'矿业权市场','date':'08-28','summary':'湖南省株洲市芦淞区长垅矿区金矿普查探矿权以网上挂牌方式公开出让，主矿种为金矿，助力区域金矿勘查开发。'},
    {'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298777.htm','title':'广西灌阳县新圩镇深浦源铅锌矿勘查探矿权网上挂牌出让公告','src':'矿业权市场','date':'08-25','summary':'广西灌阳县新圩镇深浦源铅锌矿勘查探矿权以网上挂牌方式出让，主矿种为铅、锌，区域有色金属勘查再添新项目。'},
    {'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298758.htm','title':'吉林省磐石市石咀铜矿勘查探矿权挂牌出让公告','src':'矿业权市场','date':'08-25','summary':'吉林省磐石市石咀铜矿勘查探矿权挂牌出让，主矿种为铜，推动东北地区铜矿勘查工作。'},
    # 全球矿产资源
    {'url':'https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202608/t20260831_10302802.htm','title':'智阿秘玻四国成立关键矿产联盟','src':'全球矿产资源','date':'08-31','summary':'智利、阿根廷、秘鲁、玻利维亚四国宣布成立关键矿产联盟，加强锂、铜等战略性矿产供应链合作与资源安全协调。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202608/t20260831_10302803.htm','title':'西澳州纳纳迪铜金矿钻探见厚富矿体','src':'全球矿产资源','date':'08-31','summary':'西澳大利亚州纳纳迪铜金矿项目最新钻探见厚富矿体，铜金勘查取得重要进展，为海外铜金资源开发提供新靶区。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202608/t20260831_10302801.htm','title':'智利和阿根廷推进跨边界铜矿开发','src':'全球矿产资源','date':'08-31','summary':'智利与阿根廷两国就跨边界铜矿开发达成共识，推进安第斯山脉铜矿带资源整合与基础设施互联互通。'},
    # 中国有色网
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473461','title':'加拿大矿业公司Auro Metals再获496米厚大矿段 高品位矿段金品位达1.12克/吨','src':'中国有色网','date':'08-31','summary':'加拿大Auro Metals公司勘探取得重大突破，新发现496米厚大矿段，其中高品位矿段金品位达1.12克/吨，海外金矿勘查成果亮眼。'},
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473589','title':'西北有色地矿集团七一一总队深耕地勘主业聚力实现新突破','src':'中国有色网','date':'08-31','summary':'西北有色地矿集团七一一总队持续深耕地质勘查主业，在矿产勘查与资源发现领域实现新突破，聚焦有色金属找矿。'},
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473401','title':'希尔威金属矿业公布吉尔吉斯金矿重大勘探成果','src':'中国有色网','date':'08-26','summary':'希尔威金属矿业公布吉尔吉斯斯坦金矿项目重大勘探成果，海外金矿资源勘查取得关键进展。'},
    # 中国有色金属工业协会
    {'url':'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0831/61862.html','title':'金川镍钴承压奋进攀高逐新','src':'中国有色金属工业协会','date':'08-31','summary':'金川集团镍钴产业在压力中持续奋进，围绕镍、钴等关键矿产提升资源保障与产业竞争力，奋力攀登高质量发展新高度。'},
    {'url':'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0831/61861.html','title':'中国稀土集团2026年安全环保绿色低碳专题研修班开班','src':'中国有色金属工业协会','date':'08-31','summary':'中国稀土集团举办2026年安全环保绿色低碳专题研修班，推动稀土产业绿色低碳转型与可持续发展。'},
    {'url':'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0831/61856.html','title':'【谱写“十五五”有色新篇章】利润总额同比大增98% 中国铝业中期增速再创历史新高','src':'中国有色金属工业协会','date':'08-31','summary':'中国铝业发布中期业绩，利润总额同比大增98%，增速再创历史新高，铝产业高质量发展动能强劲。'},
    # 中国地质学会
    {'url':'https://www.geosociety.org.cn/?v1=v14&v4=v15&v2=6a62d50844e67&v3=v41','title':'全国勘查地球化学找矿与分析技术培训交流会在江苏连云港举办','src':'中国地质学会','date':'08-24','summary':'全国勘查地球化学找矿与分析技术培训交流会在江苏连云港举办，聚焦地球化学找矿方法、分析技术及应用实践。'},
    # 中国稀土行业协会
    {'url':'http://www.ac-rei.org.cn/article/0a0d05a6-7f7c-4ee7-a5d6-06af20c68123','title':'2026年08月24日稀土价格指数','src':'中国稀土行业协会','date':'08-24','summary':'中国稀土行业协会发布2026年8月24日稀土价格指数，反映国内稀土市场行情变动。'},
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

# ---------- Price strip ----------
price_note = f'{TODAY.strftime("%Y-%m-%d")} 晨间更新 · 沪期主力/SMM·上金所 · 涨红跌绿'

price_html = f'''<div class="price-strip" id="priceStrip">
<div class="price-strip-head">
<span class="price-strip-title">📊 金属价格</span>
<span class="price-strip-note">{price_note}</span>
</div>
<div class="price-cards">
<div class="price-card down"><div class="pc-name">沪铜 <span class="pc-tag">SHFE</span></div><div class="pc-value">108,160</div><div class="pc-unit">元/吨</div><div class="pc-chg">▼ -460 (-0.42%)</div></div>
<div class="price-card up"><div class="pc-name">沪铝 <span class="pc-tag">SHFE</span></div><div class="pc-value">23,985</div><div class="pc-unit">元/吨</div><div class="pc-chg">▲ +55 (+0.23%)</div></div>
<div class="price-card up"><div class="pc-name">沪铅 <span class="pc-tag">SHFE</span></div><div class="pc-value">16,335</div><div class="pc-unit">元/吨</div><div class="pc-chg">▲ +95 (+0.58%)</div></div>
<div class="price-card up"><div class="pc-name">沪锌 <span class="pc-tag">SHFE</span></div><div class="pc-value">26,350</div><div class="pc-unit">元/吨</div><div class="pc-chg">▲ +75 (+0.29%)</div></div>
<div class="price-card down"><div class="pc-name">沪锡 <span class="pc-tag">SHFE</span></div><div class="pc-value">416,140</div><div class="pc-unit">元/吨</div><div class="pc-chg">▼ -5,860 (-1.39%)</div></div>
<div class="price-card down"><div class="pc-name">沪镍 <span class="pc-tag">SHFE</span></div><div class="pc-value">126,400</div><div class="pc-unit">元/吨</div><div class="pc-chg">▼ -1,800 (-1.40%)</div></div>
<div class="price-card"><div class="pc-name">上海金 <span class="pc-tag">早盘价</span></div><div class="pc-value">989.36</div><div class="pc-unit">元/克</div><div class="pc-chg">早盘 989.36 / 午盘 995.35</div></div>
<div class="price-card"><div class="pc-name">白银 <span class="pc-tag">Ag(T+D)</span></div><div class="pc-value">17,090</div><div class="pc-unit">元/千克</div><div class="pc-chg">今开 17,090</div></div>
<div class="price-card up"><div class="pc-name">碳酸锂 <span class="pc-tag">电池级</span></div><div class="pc-value">153,235</div><div class="pc-unit">元/吨（SMM折）</div><div class="pc-chg">▲ +550 (+0.36%)</div></div>
<div class="price-card down"><div class="pc-name">电解钴 <span class="pc-tag">SMM</span></div><div class="pc-value">305,428</div><div class="pc-unit">元/吨（SMM折）</div><div class="pc-chg">▼ -2,403 (-0.77%)</div></div>
</div>
</div>'''

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
<!-- ==================== 已归档收藏 ==================== -->
<div class="section" id="archivedFavSection" style="display:none">
<div class="section-title">🗂️ 已归档收藏（原新闻已滚出页面，收藏记录永久保留）<span class="news-count" id="archFavCount">0条</span></div>
<div id="archFavList"></div>
</div>
<div class="footer">
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

# ---------- Assemble final HTML ----------
final_html = (
    header_part + style_block + '\n' + body_start + price_html + '\n' + stats_bar +
    special_section + today_section_start + today_html + '</div>\n\n' +
    archive_section_start + archive_html + '</div>\n\n' +
    install_guide + script_block + '\n</body>\n</html>'
)

OUT_INDEX.write_text(final_html, encoding='utf-8')
print(f'Wrote {OUT_INDEX} ({len(final_html)} chars)')
