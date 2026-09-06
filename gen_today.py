#!/usr/bin/env python3
"""Generate new index.html for mining daily - update date, prices, news content.
Works by in-place modification of the old HTML file.
"""
import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# ========== STEP 1: Update title date ==========
html = html.replace(
    '<title>矿业新闻日报 2026-09-03</title>',
    '<title>矿业新闻日报 2026-09-04</title>'
)

# ========== STEP 2: Update header date badge ==========
html = html.replace(
    '2026年09月03日 星期四',
    '2026年09月04日 星期五'
)

# ========== STEP 3: Update TOC counts ==========
html = html.replace('id="tocAllCount">63<', 'id="tocAllCount">55<')
html = html.replace('id="tocTodayCount">11<', 'id="tocTodayCount">7<')
html = html.replace('id="tocArchiveCount">52<', 'id="tocArchiveCount">48<')
html = html.replace(
    'id="tocSpecialCount" style="background:#fdf3d7;color:#b45009">2<',
    'id="tocSpecialCount" style="background:#fdf3d7;color:#b45009">0<'
)

# ========== STEP 4: Update price strip date ==========
html = html.replace('2026-09-02 更新', '2026-09-03 更新')

# ========== STEP 5: Update price cards ==========
# 2026-09-06 晚定版：价格区为上下两行（国内外分开，用户确认勿改回矩阵/单容器混排）——
#   首行 <div class="price-cards" id="priceCardsShfe">：国内 10 卡，顺序 铜铝铅锌镍锡 + 上海金/白银/碳酸锂/电解钴；
#   次行 <div class="price-cards price-cards-lme" id="priceCardsLme">：LME 6 卡，顺序与首行一致 铜铝铅锌镍锡。
#   slug：国内 cum/alm/pbm/znm/nim/snm + au9999/agtd/lcm（电解钴无slug）；LME lcpt/lalt/lldt/lznt/lnkt/ltnt。
#   LME 卡单位「美元/吨」，数值由前端 renderLmePrices() 按 data-slug 填充，静态值写 -- 和「检测中…」。
#   注意：严禁把 LME 卡混回首行（同列同品种矩阵已废弃），也不要恢复 pm-col/pm-solo 结构。
# 每行容器在 index.html 里各占一行（以行尾 </div>\n 结束），非贪婪匹配不会越过 priceStrip 边界
old_price_pattern = (r'<div class="price-cards[^"]*" id="priceCardsShfe">.*?</div>\n'
                     r'<div class="price-cards[^"]*" id="priceCardsLme">.*?</div>\n')
def _card(slug,cls,name,tag,val,unit,chg):
    d=f' data-slug="{slug}"' if slug else ''
    return (f'<div{d} class="price-card {cls}"><div class="pc-name">{name} <span class="pc-tag">{tag}</span></div>'
            f'<div class="pc-value">{val}</div><div class="pc-unit">{unit}</div><div class="pc-chg">{chg}</div></div>')
def _lme(slug,name):
    return _card(slug,' ',f'LME {name}','LME','--','美元/吨','检测中…')
new_price_html = (
    '<div class="price-cards" id="priceCardsShfe">'
    +_card('cum','up','沪铜','SHFE','108,570','元/吨','&#9650; +460 (+0.43%)')
    +_card('alm','up','沪铝','SHFE','24,350','元/吨','&#9650; +290 (+1.21%)')
    +_card('pbm','up','沪铅','SHFE','16,105','元/吨','&#9650; +10 (+0.06%)')
    +_card('znm','up','沪锌','SHFE','26,665','元/吨','&#9650; +20 (+0.08%)')
    +_card('nim','up','沪镍','SHFE','128,890','元/吨','&#9650; +2,280 (+1.80%)')
    +_card('snm','down','沪锡','SHFE','414,770','元/吨','&#9660; -1,050 (-0.25%)')
    +_card('au9999','up','上海金','早盘价','931.36','元/克','今开 939.99')
    +_card('agtd','up','白银','Ag(T+D)','15,659','元/千克','今开 15,659')
    +_card('lcm','down','碳酸锂','主力连续','156,450','元/吨','&#9660; -523 (-0.33%)')
    +_card(None,'down','电解钴','SMM','304,940','元/吨','&#9660; -45 (-0.02%)')
    +'</div>\n'
    '<div class="price-cards price-cards-lme" id="priceCardsLme">'
    +_lme('lcpt','铜')+_lme('lalt','铝')+_lme('lldt','铅')+_lme('lznt','锌')+_lme('lnkt','镍')+_lme('ltnt','锡')
    +'</div>\n'
)
html = re.sub(old_price_pattern, lambda m: new_price_html, html, flags=re.DOTALL)
# 替换后校验：两容器各一个、LME 6 slug、div 收支为 0
assert html.count('id="priceCardsShfe"')==1 and html.count('id="priceCardsLme"')==1
assert html.count("price-cards-lme")==1
for _sl in ['lcpt','lalt','lldt','lznt','lnkt','ltnt']:
    assert f'data-slug="{_sl}"' in html, _sl
assert len(re.findall(r'<div\b',html))==html.count('</div>'), 'div balance broken'
print("Step 5: Price cards updated (two-row layout)")

# ========== STEP 6: Extract old today & archive, then replace ==========
# Find markers - these are UNIQUE in the file
marker_today = '<!-- ==================== 今日新增 ==================== -->'
marker_archive = '<!-- ==================== 往期内容 ==================== -->'
marker_install = '<!-- ==================== 详细安装指引 ==================== -->'

pos_today = html.find(marker_today)
pos_archive = html.find(marker_archive)
pos_install = html.find(marker_install)

print(f"Step 6: Markers found - today:{pos_today} archive:{pos_archive} install:{pos_install}")

if pos_today < 0 or pos_archive < 0 or pos_install < 0:
    print("ERROR: Could not find all markers!")
    exit(1)

# Extract old sections
old_today_section = html[pos_today:pos_archive]  # from today marker to archive marker
old_archive_section = html[pos_archive:pos_install]  # from archive marker to install marker

# --- Process old today items -> become archive items ---
# Remove is-new class and NEW badges from old today items
old_today_items = old_today_section.replace(' is-new', '').replace('<span class="badge-new">NEW</span>', '')
old_today_items = old_today_items.replace('条新增', '条')

# Extract just the content (sub-cats and news-items), skip the section wrapper
# Find the end of the section-title line
lines = old_today_items.split('\n')
content_lines = []
skip_header = True
brace_depth = 0
for line in lines:
    if skip_header:
        # Skip comments and section div and title
        if '<div class="news-item' in line or '<div class="sub-cat' in line:
            skip_header = False
            content_lines.append(line)
        continue
    else:
        content_lines.append(line)

# Remove the last </div> (section closing tag)
content_text = '\n'.join(content_lines).rstrip()
if content_text.endswith('</div>'):
    content_text = content_text[:-6].rstrip()

old_today_content = content_text

# --- Process old archive items ---
# Remove 08-26 dated items (>7 days from 09-03)
# Find news-items with t20260826 in their data-url
old_archive_cleaned = re.sub(
    r'<div class="news-item"[^>]*data-url="[^"]*t20260826[^"]*"[^>]*>.*?</div>',
    '',
    old_archive_section,
    flags=re.DOTALL
)

# Also remove sub-cats that have 0 items after removal (check if a sub-cat is followed by another sub-cat or end with no items between)
# For simplicity, just extract archive content items
arch_lines = old_archive_cleaned.split('\n')
arch_content_lines = []
skip_arch_header = True
for line in arch_lines:
    stripped = line.strip()
    if skip_arch_header:
        if '<div class="news-item' in line or '<div class="sub-cat' in line:
            skip_arch_header = False
            arch_content_lines.append(line)
        continue
    else:
        # Skip empty lines and closing divs that are section-level
        if stripped == '</div>' and not arch_content_lines[-1].strip().startswith('<div class="news-item'):
            # This might be the section closing tag, skip it
            continue
        arch_content_lines.append(line)

# Clean up archive content
arch_content_text = '\n'.join(arch_content_lines).rstrip()
# Remove trailing section close
if arch_content_text.endswith('</div>'):
    arch_content_text = arch_content_text[:-6].rstrip()

old_archive_content = arch_content_text

# Count old today items for archive count
import re as re2
today_item_urls = re2.findall(r'data-url="([^"]*)"', old_today_content)
archive_item_urls = re2.findall(r'data-url="([^"]*)"', old_archive_content)
# Deduplicate - remove items already in today (shouldn't happen but safety)
existing_urls = set(today_item_urls)
deduped_archive = []
for line in old_archive_content.split('\n'):
    url_match = re2.search(r'data-url="([^"]*)"', line)
    if url_match and url_match.group(1) in existing_urls:
        continue
    deduped_archive.append(line)
old_archive_content = '\n'.join(deduped_archive)

total_today = len(today_item_urls)
total_archive = len(re2.findall(r'data-url="([^"]*)"', old_archive_content))
total_all = total_today + total_archive
print(f"Step 6: Today={total_today}, Archive={total_archive}, All={total_all}")

# --- Build new today section ---
new_today = """<!-- ==================== 今日新增 ==================== -->
<div class="section" id="todaySection">
<div class="section-title today"><span class="icon">🔥</span> 今日新增（2026-09-03 抓取）<span class="news-count" id="todayCount">7条</span></div>
<div class="sub-cat">💼 矿权交易<span class="sub-count">2条新增</span></div>
<div class="news-item is-new" data-url="https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260903_10305021.htm" data-embed="ok"><div class="news-head"><span class="dot"></span><span class="badge-new">NEW</span><a class="news-title" href="https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260903_10305021.htm" target="_blank">湖北省通山县泉塘王矿区金矿勘查网上挂牌出让公告</a></div><div class="news-meta"><span class="src">矿业权市场</span> · 09-03</div><div class="news-summary">湖北省自然资源厅打包出让通山县泉塘王矿区金矿南段和北段勘查探矿权，矿种为金矿，南段3.9平方千米、北段5.9平方千米，起始价59.04万元，出让收益率2.3%。</div><a class="btn-read" href="https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260903_10305021.htm" target="_blank">查看原文 →</a></div>
<div class="news-item is-new" data-url="https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260903_10305004.htm" data-embed="ok"><div class="news-head"><span class="dot"></span><span class="badge-new">NEW</span><a class="news-title" href="https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260903_10305004.htm" target="_blank">云南省广南县董平金矿勘探探矿权转让公示</a></div><div class="news-meta"><span class="src">矿业权市场</span> · 09-02</div><div class="news-summary">文山州自然资源局公示广南县董平金矿勘探探矿权转让，转让人为云南金龙矿业，受让人为广南广钰矿业，勘查面积9.44平方千米，转让方式为出售。</div><a class="btn-read" href="https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260903_10305004.htm" target="_blank">查看原文 →</a></div>
<div class="sub-cat">🏭 行业动态<span class="sub-count">5条新增</span></div>
<div class="news-item is-new" data-url="https://www.cngold.org.cn/news/show-9524.html" data-embed="ok"><div class="news-head"><span class="dot"></span><span class="badge-new">NEW</span><a class="news-title" href="https://www.cngold.org.cn/news/show-9524.html" target="_blank">周洲出席中吉商务与投资论坛 中国黄金集团深耕中亚矿业合作</a></div><div class="news-meta"><span class="src">中国黄金协会</span> · 09-02</div><div class="news-summary">中国黄金集团董事长周洲出席中吉商务与投资论坛，强调吉尔吉斯斯坦是集团推进全球资源布局的重要地区，持续推进库鲁-捷盖列克铜金矿、布丘克金矿等项目建设和运营。</div><a class="btn-read" href="https://www.cngold.org.cn/news/show-9524.html" target="_blank">查看原文 →</a></div>
<div class="news-item is-new" data-url="https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61889.html" data-embed="ok"><div class="news-head"><span class="dot"></span><span class="badge-new">NEW</span><a class="news-title" href="https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61889.html" target="_blank">云铝股份交出历史最好半年成绩单 营收增长20.3%利润增长175%</a></div><div class="news-meta"><span class="src">中国有色金属工业协会</span> · 09-01</div><div class="news-summary">云铝股份上半年营收349.81亿元同比增长20.3%，利润总额104.54亿元同比增长175%，电解铝板块半年利润创历史最好，氧化铝、炭素产量超额完成，合金产品出口实现突破。</div><a class="btn-read" href="https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61889.html" target="_blank">查看原文 →</a></div>
<div class="news-item is-new" data-url="https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61895.html" data-embed="ok"><div class="news-head"><span class="dot"></span><span class="badge-new">NEW</span><a class="news-title" href="https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61895.html" target="_blank">洛阳铜加工产出首根镁合金铸锭 镁板全流程工艺贯通</a></div><div class="news-meta"><span class="src">中国有色金属工业协会</span> · 09-01</div><div class="news-summary">中铝洛阳铜加工变形镁合金板材生产线一期镁熔铸试生产成功，产出首根合格镁合金铸锭，标志镁板全流程生产工艺全线贯通，具备规模化生产能力。</div><a class="btn-read" href="https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61895.html" target="_blank">查看原文 →</a></div>
<div class="news-item is-new" data-url="https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61894.html" data-embed="block"><div class="news-head"><span class="dot"></span><span class="badge-new">NEW</span><a class="news-title" href="https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61894.html" target="_blank">株冶集团奋力推进"三化两型"建设 铅锌冶炼绿色智能升级</a></div><div class="news-meta"><span class="src">中国有色金属工业协会</span> · 09-01</div><div class="news-summary">株冶集团推进绿色化、智能化、融合化建设，30万吨锌冶炼基地单位能耗降22%，建成铜铅锌联合冶炼与多源固废协同利用示范工程，铟回收率超行业均值10个百分点。</div><a class="btn-read" href="https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61894.html" target="_blank">查看原文 →</a></div>
<div class="news-item is-new" data-url="https://www.cgs.gov.cn/ywdt/dwdt/202609/t20260902_867821.html" data-embed="block"><div class="news-head"><span class="dot"></span><span class="badge-new">NEW</span><a class="news-title" href="https://www.cgs.gov.cn/ywdt/dwdt/202609/t20260902_867821.html" target="_blank">西安矿产中心科技成果获陕西省科学技术进步奖三等奖</a></div><div class="news-meta"><span class="src">中国地质调查局</span> · 09-02</div><div class="news-summary">中国地质调查局西安矿产资源调查中心成果获陕西省科技进步奖三等奖，聚焦秦岭矿集区矿渣型泥石流灾害防治与生态修复，成果在汉中、安康等矿集区落地应用。</div><a class="btn-read" href="https://www.cgs.gov.cn/ywdt/dwdt/202609/t20260902_867821.html" target="_blank">查看原文 →</a></div>
</div>
"""

# --- Build new archive section ---
new_archive_count = total_archive
new_archive = (
    '<!-- ==================== 往期内容 ==================== -->\n'
    '<div class="section" id="archiveSection">\n'
    '<div class="section-title"><span class="icon">📰</span> 往期内容（滚动保留最近7天）'
    f'<span class="news-count" id="archiveCount">{new_archive_count}条</span></div>\n'
    '<div class="fold-toggle" id="foldToggle" style="display:none" onclick="toggleOldFold()">▸ 展开更早内容</div>\n'
    + old_today_content + '\n'
    + old_archive_content + '\n'
    '</div>\n'
)

# Replace old today+archive with new today+archive
html = html[:pos_today] + new_today + '\n' + new_archive + html[pos_install:]

print(f"Step 6: Sections replaced. New size: {len(html)} chars")

# ========== STEP 7: Update footer date ==========
html = html.replace('更新时间：2026-09-01 12:00', '更新时间：2026-09-03 09:10')
html = html.replace('更新时间：2026-09-02', '更新时间：2026-09-03 09:10')

# ========== STEP 8: Clear special section spList-security ==========
html = html.replace('id="spCount-security">2条', 'id="spCount-security">0条')
# Clear old strategic items from spList-security
sp_pattern = r'(<div class="sp-list" id="spList-security">)\s*<div class="news-item.*?</div>\s*</div>'
sp_match = re.search(sp_pattern, html, flags=re.DOTALL)
if sp_match:
    html = html[:sp_match.start()] + sp_match.group(1) + '\n' + html[sp_match.end():]
    print("Step 8: spList-security cleared")
else:
    print("Step 8: spList-security pattern not found (may already be empty)")

# ========== Write output ==========
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\nDone! index.html written. Size: {len(html)} chars")
print(f"Today items: {total_today}, Archive items: {total_archive}, Total: {total_all}")
