# -*- coding: utf-8 -*-
"""将 09-07 新增矿权条目插入 data/news_2026-09.json（仅矿权数据层，不入主页列表）。
export_news_json.py 解析 index.html 后按 id 合并，本条目不在 index.html 中，将被原样保留。"""
import json, hashlib, os

PATH = 'data/news_2026-09.json'
URL = 'https://ky.mnr.gov.cn/jggs/jjgs/202609/t20260907_10307760.htm'
eid = hashlib.md5(URL.encode('utf-8')).hexdigest()[:12]

entry = {
    'id': eid,
    'title': '甘肃省文县范坝交流一带金矿普查探矿权公开出让结果公示',
    'url': URL,
    'source': '矿业权市场',
    'orig_date': '09-07',
    'orig_date_full': '2026-09-07',
    'report_date': '2026-09-07',
    'category': '矿权交易',
    'is_new': True,
    'summary': '甘肃省自然资源厅公示文县范坝交流一带金矿普查探矿权公开出让结果：竞得人陇南市忠亿矿业开发有限公司，成交价8365万元，区块面积1.4195平方千米，勘查矿种金矿（42201），拟出让年限5.0年，起始价5.0万元；公示期2026-09-07至09-18。',
    'embed': 'ok',
    'tags': ['金', '矿权'],
    'first_seen': '2026-09-07',
    'last_seen': '2026-09-07',
}

d = json.load(open(PATH, encoding='utf-8'))
news = d.get('news', [])
if any(x.get('id') == eid for x in news):
    print('SKIP 已存在 id=%s' % eid)
else:
    news.append(entry)
    news.sort(key=lambda x: (x.get('orig_date_full', ''), x.get('id', '')), reverse=True)
    d['news'] = news
    d['count'] = len(news)
    d['updated_at'] = __import__('datetime').datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
    json.dump(d, open(PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('OK 插入矿权条目 id=%s total=%d' % (eid, len(news)))
