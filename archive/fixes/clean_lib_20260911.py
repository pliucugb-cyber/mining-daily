# -*- coding: utf-8 -*-
"""月库收尾清理（2026-09-11）

1) 删除 61959（中国有色金属工业协会 镁行业新标准）这条已 404 的重复条目
   —— 同文已由 fix_links 换源为 473839（中国有色金属报），旧条目属于改写前的残留。
2) 顺手校验 id == md5(url)[:12]，纠正不一致；补充缺失的 region 字段。
3) 按 URL 去重兜底 + 更新 count。
"""
import json, io, os, hashlib

os.chdir(r'C:\Users\中铝矿业投并部\mining-daily')
FN = 'data/news_2026-09.json'
STALE_URL = 'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0908/61959.html'

d = json.load(io.open(FN, encoding='utf-8'))
news = d['news']
before = len(news)

# 1) 删旧
removed = [e for e in news if e.get('url') == STALE_URL]
news = [e for e in news if e.get('url') != STALE_URL]

# 2) id 校验 + region 兜底
fixed_id = 0
for e in news:
    u = e.get('url', '')
    want = hashlib.md5(u.encode('utf-8')).hexdigest()[:12]
    if e.get('id') != want:
        e['id'] = want
        fixed_id += 1
    if not e.get('region'):
        e['region'] = '国内'

# 3) URL 去重兜底（保留 first_seen 最早的）
seen, out, dup = {}, [], 0
for e in news:
    u = e.get('url', '')
    if u in seen:
        dup += 1
        continue
    seen[u] = 1
    out.append(e)

d['news'] = out
d['count'] = len(out)
json.dump(d, io.open(FN, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

# 快照 mining_news.json 同步删旧（export 会重建，这里先保证不残留）
m = json.load(io.open('mining_news.json', encoding='utf-8'))
if isinstance(m, dict) and isinstance(m.get('news'), list):
    m['news'] = [e for e in m['news'] if e.get('url') != STALE_URL]
    if 'meta' in m:
        m['meta']['count'] = len(m['news'])
    json.dump(m, io.open('mining_news.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

print('stale_removed=%d fixed_id=%d dup_removed=%d total %d -> %d' % (
    len(removed), fixed_id, dup, before, len(out)))
