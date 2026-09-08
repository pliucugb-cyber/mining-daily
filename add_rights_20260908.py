# -*- coding: utf-8 -*-
"""将 09-08 新增矿权条目插入 data/news_2026-09.json（仅矿权数据层，不入主页列表）。
export_news_json.py 解析 index.html 后按 id 合并，本条目不在 index.html 中，将被原样保留。
矿权交易专区（#rightsSection）由前端从 window.NEWS_DATA 渲染，严禁写回今日区/往期区主列表。"""
import json, hashlib, datetime

PATH = 'data/news_2026-09.json'
REPORT = '2026-09-08'

ITEMS = [
    ('https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260908_10307786.htm',
     '江西省宜丰县鸦溪铜多金属矿详查探矿权转让公示',
     '江西省自然资源厅公示（赣自然探转公示〔2026〕50号）：江西省地质局第一地质大队将「江西省宜丰县鸦溪铜多金属矿详查」探矿权转让给南昌纪华矿业有限公司。权证号T3600002008073010011749，勘查矿种32006铜矿，面积0.384平方千米，有效期2025年8月11日至2030年8月10日。',
     ['铜', '矿权']),
    ('https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260908_10307785.htm',
     '江西省宜春市袁州区何家坪钽铌矿详查探矿权转让公示',
     '江西省自然资源厅公示（赣自然探转公示〔2026〕49号）：江西省地质局第一地质大队将「江西省宜春市袁州区何家坪钽铌矿详查」探矿权转让给纪华矿业（宜春）有限公司。权证号T3600002008075010011750，勘查矿种52300铌钽矿，面积0.192平方千米，有效期2025年9月15日至2030年9月14日。',
     ['钽', '铌', '矿权']),
    ('https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260908_10307784.htm',
     '江西省奉新县坪头岭钽铌矿详查探矿权转让公示',
     '江西省自然资源厅公示（赣自然探转公示〔2026〕48号）：江西省地质局第一地质大队将「江西省奉新县坪头岭钽铌矿详查」探矿权转让给纪华矿业（宜春）有限公司。权证号T3600002010035010039685，勘查矿种52300铌钽矿，面积0.184平方千米，有效期2025年5月6日至2030年5月5日。',
     ['钽', '铌', '矿权']),
    ('https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260908_10307783.htm',
     '江西省永新县铜锣山铜多金属矿详查探矿权转让公示',
     '江西省自然资源厅公示（赣自然探转公示〔2026〕47号）：江西省地质局第一地质大队将「江西省永新县铜锣山铜多金属矿详查」探矿权转让给南昌纪华矿业有限公司。权证号DT3600002009053010028631，勘查矿种32006铜矿，面积1.6720平方千米，有效期2026年7月29日至2031年7月28日。',
     ['铜', '矿权']),
    ('https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260908_10307782.htm',
     '江西省永丰县正坑金银铅矿详查探矿权转让公示',
     '江西省自然资源厅公示（赣自然探转公示〔2026〕46号）：江西省地质矿产开发总公司将「江西省永丰县正坑金银铅矿详查」探矿权转让给吉安金诺矿业有限公司。权证号T3600002009054010030344，勘查矿种42201金矿，面积0.5600平方千米，有效期2021年9月15日至2026年9月14日。',
     ['金', '银', '铅', '矿权']),
    ('https://ky.mnr.gov.cn/zrgs/ckzrgs/202609/t20260908_10307777.htm',
     '关于勉县铺沟铅锌矿转让公示',
     '陕西省自然资源厅公示（陕自然资转公示〔2026〕2号）：勉县铺沟铅锌矿采矿权转让，权证号C6100002009063120025015，开采矿种32007铅矿、32008锌矿，矿区面积0.4474平方千米，位于陕西省汉中市勉县，有效期2026年9月7日至2026年9月18日。',
     ['铅', '锌', '矿权']),
]

d = json.load(open(PATH, encoding='utf-8'))
news = d.get('news', [])
added = 0
for url, title, summary, tags in ITEMS:
    eid = hashlib.md5(url.encode('utf-8')).hexdigest()[:12]
    if any(x.get('id') == eid for x in news):
        continue
    news.append({
        'id': eid,
        'title': title,
        'url': url,
        'source': '矿业权市场',
        'orig_date': '09-07',
        'orig_date_full': '2026-09-07',
        'report_date': REPORT,
        'category': '矿权交易',
        'is_new': True,
        'summary': summary,
        'embed': 'ok',
        'tags': tags,
        'first_seen': REPORT,
        'last_seen': REPORT,
    })
    added += 1

news.sort(key=lambda x: (x.get('orig_date_full', ''), x.get('id', '')), reverse=True)
d['news'] = news
d['count'] = len(news)
d['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
json.dump(d, open(PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('OK 插入矿权条目 %d 条，库内合计 %d 条' % (added, len(news)))
