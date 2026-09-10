# -*- coding: utf-8 -*-
"""2026-09-11 链接修复（validate_urls 复核后发现的 3 处真实 404）

1. 中国有色金属工业协会 61959（镁行业新标准）已 404 → 换成同文的中国有色金属报镜像
   https://www.cnmn.com.cn/ShowNews1.aspx?id=473839 （实测 200，标题一致）
2. 全球矿产资源信息系统 t20260908_10308875（智利坎加洛铜矿）整篇已下线，各子栏目路径均 404 → 删除条目
3. 自然资源部 t20260904_2937623（矿区生态修复典型案例公示）已下线 → 删除条目

先改月库（否则 generate 的回补会把删掉的条目重新捞回来），再改 index.html，最后重跑生成链。
"""
import json, io, os, re, datetime

os.chdir(r'C:\Users\中铝矿业投并部\mining-daily')

OLD_MG = 'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0908/61959.htm'
NEW_MG = 'https://www.cnmn.com.cn/ShowNews1.aspx?id=473839'
DROP = [
    'https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260908_10308875.htm',
    'https://www.mnr.gov.cn/dt/ywbb/202609/t20260904_2937623.html',
]

# ---------- 1. 月库 ----------
fn = 'data/news_2026-09.json'
d = json.load(open(fn, encoding='utf-8'))
n_replace = n_drop = 0
out = []
for e in d['news']:
    if e.get('url') == OLD_MG:
        e['url'] = NEW_MG
        e['source'] = '中国有色金属报'
        n_replace += 1
    if e.get('url') in DROP:
        n_drop += 1
        continue
    out.append(e)
d['news'] = out
d['count'] = len(out)
json.dump(d, open(fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

# ---------- 2. index.html ----------
h = io.open('index.html', encoding='utf-8').read()
before = len(h)
# 2.1 换 URL + 换来源名（两个属性都要改，否则 src 与站点不符）
h = h.replace('href="%s" target="_blank"' % OLD_MG, 'href="%s" target="_blank"' % NEW_MG)
h = h.replace('data-url="%s"' % OLD_MG, 'data-url="%s"' % NEW_MG)
# 来源名：只在紧跟该 URL 的 meta 里替换
h = re.sub(re.escape(NEW_MG) + r'(?:(?!</div>\s*</div>).)*?<span class="src">中国有色金属工业协会</span>',
           NEW_MG + r'<span class="src">中国有色金属报</span>', h, flags=re.S)
# 2.2 删除已下线条目
removed = 0
for u in DROP:
    pat = re.compile(r'<div class="news-item[^"]*" data-url="%s"[^>]*>.*?</div>\s*</div>\s*' % re.escape(u), re.S)
    h, k = pat.subn('', h)
    removed += k
assert removed == len(DROP), '删除条目数不符：%d' % removed

buf = h.encode('utf-8')
assert len(buf) > before * 0.9, 'index.html 疑似被截断'
with io.open('index.html.tmp', 'w', encoding='utf-8') as f:
    f.write(h)
os.replace('index.html.tmp', 'index.html')

print('library: replaced=%d dropped=%d total=%d' % (n_replace, n_drop, len(out)))
print('index.html: removed_blocks=%d size %d -> %d' % (removed, before, len(h)))
