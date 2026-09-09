# -*- coding: utf-8 -*-
"""注入 2026-09-09 矿权交易公告到 data/news_2026-09.json

- 7 宗：1 挂牌出让 / 1 转让公示 / 1 出让结果 / 4 协议出让
- 仅注入主列表（add_rights_20260908.py 同款 schema）
- 字段：title/url/source/orig_date/orig_date_full/category/summary/embed/deadline/method/mineral/area
"""
import json, datetime, re, sys

TODAY = '2026-09-09'
FN = 'data/news_2026-09.json'

ITEMS = [
    {
        'title': '新疆托里县成吉思汗山安山岩矿二区普查探矿权公开挂牌出让',
        'url': 'https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260909_10308882.htm',
        'source': '矿业权市场',
        'orig_date': '09-08',
        'orig_date_full': '2026-09-08',
        'category': '矿权交易',
        'summary': '塔城地区自然资源局公告，新疆托里县成吉思汗山安山岩矿二区普查探矿权公开挂牌出让，勘查矿种为安山岩，面积0.1049平方千米。',
        'method': '挂牌出让',
        'mineral': '安山岩',
        'area_km2': '0.1049',
        'region': '新疆托里县',
        'embed': 'ok',
    },
    {
        'title': '辽宁省岫岩县席大岭金多金属矿普查探矿权转让公示',
        'url': 'https://ky.mnr.gov.cn/jggs/jjgs/202609/t20260904_10305944.htm',
        'source': '矿业权市场',
        'orig_date': '09-04',
        'orig_date_full': '2026-09-04',
        'category': '矿权交易',
        'summary': '辽宁省自然资源厅公示席大岭金多金属矿普查探矿权转让信息，转让方为岫岩满族自治县晶瑞矿业有限公司，受让方为安徽省南洋金融信息服务有限公司，矿种为金多金属。',
        'method': '转让公示',
        'mineral': '金多金属',
        'area_km2': '',
        'region': '辽宁岫岩县',
        'embed': 'ok',
    },
    {
        'title': '山东省乳山市金青顶外围金矿普查探矿权挂牌出让结果公示',
        'url': 'https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260905_10306832.htm',
        'source': '矿业权市场',
        'orig_date': '09-03',
        'orig_date_full': '2026-09-03',
        'category': '矿权交易',
        'summary': '山东省公共资源交易中心8月17日—28日挂牌出让乳山市金青顶外围金矿普查探矿权，竞得人为山东金洲矿业集团有限公司，矿种为金矿，面积10.830平方千米。',
        'method': '出让结果',
        'mineral': '金矿',
        'area_km2': '10.830',
        'region': '山东乳山市',
        'embed': 'ok',
    },
    {
        'title': '四川省马尔康市沙普金矿勘查探矿权挂牌出让公告',
        'url': 'https://ky.mnr.gov.cn/xycrgs/tkq/202609/t20260905_10306855.htm',
        'source': '矿业权市场',
        'orig_date': '09-04',
        'orig_date_full': '2026-09-04',
        'category': '矿权交易',
        'summary': '四川省政府政务服务和公共资源交易服务中心受省自然资源厅委托，对马尔康市沙普金矿勘查探矿权进行网上挂牌出让，矿种为金矿，面积40.9006平方千米，位于阿坝州马尔康市。',
        'method': '挂牌出让',
        'mineral': '金矿',
        'area_km2': '40.9006',
        'region': '四川阿坝州马尔康市',
        'embed': 'ok',
    },
    {
        'title': '关于协议出让阿巴嘎旗哈达特陶勒盖银铅锌矿平面垂直投影深部探矿权的公示',
        'url': 'https://ky.mnr.gov.cn/xycrgs/tkq/202609/t20260905_10306857.htm',
        'source': '矿业权市场',
        'orig_date': '09-04',
        'orig_date_full': '2026-09-04',
        'category': '矿权交易',
        'summary': '锡林郭勒盟自然资源局公示阿巴嘎旗哈达特陶勒盖银铅锌矿平面垂直投影上部、深部探矿权协议出让事项，受让方为内蒙古鑫益矿业有限公司，主矿种铅矿，面积5.5428平方千米。',
        'method': '协议出让',
        'mineral': '银铅锌',
        'area_km2': '5.5428',
        'region': '内蒙古锡林郭勒盟阿巴嘎旗',
        'embed': 'ok',
    },
    {
        'title': '关于宁城宏丰实业有限公司陈家杖子金矿采矿权垂直投影范围深部探矿权的协议出让公示',
        'url': 'https://ky.mnr.gov.cn/xycrgs/tkq/202609/t20260905_10306856.htm',
        'source': '矿业权市场',
        'orig_date': '09-04',
        'orig_date_full': '2026-09-04',
        'category': '矿权交易',
        'summary': '赤峰市自然资源局公示宁城宏丰实业有限公司陈家杖子金矿采矿权垂直投影范围深部探矿权协议出让事项，矿种为金矿，面积1.2686平方千米，位于宁城县黑里河镇。',
        'method': '协议出让',
        'mineral': '金矿',
        'area_km2': '1.2686',
        'region': '内蒙古赤峰市宁城县',
        'embed': 'ok',
    },
    {
        'title': '关于乌拉特前旗多金矿业有限公司德尔斯台沟-敖布拉格-点力斯太-乌不浪沟铁矿深部及夹缝区域勘查探矿权的协议出让公示',
        'url': 'https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260909_10308879.htm',
        'source': '矿业权市场',
        'orig_date': '09-09',
        'orig_date_full': '2026-09-09',
        'category': '矿权交易',
        'summary': '巴彦淖尔市自然资源局公示乌拉特前旗多金矿业有限公司德尔斯台沟-敖布拉格-点力斯太-乌不浪沟铁矿深部及夹缝区域勘查探矿权协议出让事项，矿种为铁矿，面积11.7923平方千米。',
        'method': '协议出让',
        'mineral': '铁矿',
        'area_km2': '11.7923',
        'region': '内蒙古巴彦淖尔市乌拉特前旗',
        'embed': 'ok',
    },
]

try:
    d = json.load(open(FN, encoding='utf-8'))
    if isinstance(d, dict) and 'news' in d:
        lib = d['news']
    elif isinstance(d, list):
        lib = d
    else:
        lib = []
except Exception:
    lib = []

# 注入前用 URL 去重
have = {it.get('url', '') for it in lib}
added = 0
for it in ITEMS:
    if it['url'] in have:
        continue
    lib.insert(0, it)
    added += 1

if isinstance(d, list):
    json.dump(lib, open(FN, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
else:
    d['news'] = lib
    d['updated'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json.dump(d, open(FN, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

print('rights added:', added, 'total library:', len(lib))
