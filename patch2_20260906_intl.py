# -*- coding: utf-8 -*-
"""
2026-09-06 国际条目二次修正
经 export_news_json.py 比对发现：「政府干预关键矿产"前所未有"」的 first_seen(n)=2026-09-04，
属 09-04 已收录旧条目，不能算今日新增（重复收录）。
替换为已逐页核实、且 news-data.js 中确认全新（未收录）的：
  BMI：未来5年铁矿石产量增速加快（全球矿产资源 / 09-01）
条数保持 12 不变（矿权 5 · 找矿 2 · 行业 3 · 国际 2）
"""
import re, datetime

SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()

OLD_URL = 'https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260903_10305931.htm'
NEW_URL = 'https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260901_10303964.htm'

def ni(url, src, date, title, summary, embed='ok'):
    return ('<div class="news-item is-new" data-url="%s" data-embed="%s"><div class="news-head"><span class="dot"></span>'
            '<span class="badge-new">NEW</span><a class="news-title" href="%s" target="_blank">%s</a></div>'
            '<div class="news-meta"><span class="src">%s</span> · %s</div><div class="news-summary">%s</div>'
            '<a class="btn-read" href="%s" target="_blank">查看原文 →</a></div>'
            % (url, embed, url, title, src, date, summary, url))

new_item = ni(NEW_URL, '全球矿产资源', '09-01',
    'BMI：未来5年铁矿石产量增速加快',
    '据矿业周刊（Miningweekly）报道，惠誉方案（Fitch Solutions）旗下基准矿物情报公司（BMI）在最新铁矿石采矿业展望报告中预计，2026—2030年全球铁矿石生产增速将加快，平均增速2.2%，高于前5年的1.2%，到2030年产量有望达30.4亿吨。西芒杜铁矿达产后，几内亚将成为全球铁矿石产量增长的主要推动力；BMI同时预计政治和社会不稳以及资源民族主义将导致部分项目开发推迟。中期看，价格下跌将使铁矿石生产停滞，2032—2034年转为下降。')

# 定位并替换旧条目整块
pat = re.compile(r'<div class="news-item is-new" data-url="%s".*?</div>\s*(?=<div class="news-item|<div class="sub-cat|</div>)'
                 % re.escape(OLD_URL), re.S)
m = pat.search(html)
assert m, '未找到待替换条目'
html = html[:m.start()] + new_item + html[m.end():]

# 更新时间戳
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'更新时间：2026-09-06 \d{2}:\d{2}', '更新时间：2026-09-06 %s' % now, html)
html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
              'name="build-version" content="20260906-%s"' % now.replace(':', ''), html)

with open(SRC, 'w', encoding='utf-8') as f:
    f.write(html)

i_t = html.find('<div class="section" id="todaySection">')
i_a = html.find('<div class="section" id="archiveSection">')
print('OK 替换完成 -> today items =', html[i_t:i_a].count('<div class="news-item'),
      '| 旧条目残留:', OLD_URL in html, '| 新条目:', NEW_URL in html)
