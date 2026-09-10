# -*- coding: utf-8 -*-
"""注入 2026-09-11 矿权交易公告到 data/news_2026-09.json

- 6 宗：1 挂牌出让（广西铝土矿）/ 4 出让结果（甘肃）/ 1 转让公示（山西绛县）
- 仅入 rightsSection 数据层（category=矿权交易），不进主页列表
- summary 必须包含前端可解析字段：面积X平方千米 / 起始价X万元 / 成交价X万元 /
  竞得人 / 转让人为 / 受让人为 / 公示期 X年X月X日 至 X年X月X日
"""
import json, datetime, hashlib

TODAY = '2026-09-11'
FN = 'data/news_2026-09.json'

ITEMS = [
    {
        'title': '广西龙州县金龙镇金龙矿区外围铝土矿勘查探矿权网上挂牌出让公告',
        'url': 'https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260910_10309854.htm',
        'source': '矿业权市场',
        'orig_date': '09-09',
        'orig_date_full': '2026-09-09',
        'category': '矿权交易',
        'summary': '广西壮族自治区公共资源交易中心受自治区自然资源厅委托，对龙州县金龙镇金龙矿区外围铝土矿勘查探矿权实施网上挂牌出让，勘查矿种铝土矿，面积20.9424平方千米，起始价419.0万元，竞买保证金1000万元，报名截止时间 2026年11月06日，挂牌设在广西壮族自治区公共资源交易平台系统。',
        'method': '挂牌出让', 'mineral': '铝土矿', 'area_km2': '20.9424',
        'region': '广西崇左市龙州县', 'embed': 'ok',
    },
    {
        'title': '甘肃省金塔县大湾铁多金属矿普查探矿权挂牌出让结果公示',
        'url': 'https://ky.mnr.gov.cn/jggs/jjgs/202609/t20260910_10309852.htm',
        'source': '矿业权市场',
        'orig_date': '09-09',
        'orig_date_full': '2026-09-09',
        'category': '矿权交易',
        'summary': '甘肃省自然资源厅公示金塔县大湾铁多金属矿普查探矿权挂牌出让结果，勘查矿种铁矿，面积3.0432平方千米，竞得人 甘肃标城矿业发展有限公司，起始价16.0万元，成交价616.0万元，公示期 2026年09月10日 至 2026年09月23日。',
        'method': '出让结果', 'mineral': '铁矿', 'area_km2': '3.0432',
        'region': '甘肃酒泉市金塔县', 'embed': 'ok',
    },
    {
        'title': '甘肃省瓜州县金沟子转脖子金矿普查探矿权挂牌出让结果公示',
        'url': 'https://ky.mnr.gov.cn/jggs/jjgs/202609/t20260910_10309850.htm',
        'source': '矿业权市场',
        'orig_date': '09-09',
        'orig_date_full': '2026-09-09',
        'category': '矿权交易',
        'summary': '甘肃省自然资源厅公示瓜州县金沟子转脖子金矿普查探矿权挂牌出让结果，勘查矿种金矿，面积10.3712平方千米，竞得人 河南省第一地质大队有限公司，起始价32.0万元，成交价1272.0万元，公示期 2026年09月10日 至 2026年09月23日。',
        'method': '出让结果', 'mineral': '金矿', 'area_km2': '10.3712',
        'region': '甘肃酒泉市瓜州县', 'embed': 'ok',
    },
    {
        'title': '甘肃省合作市南畔外围铜矿普查探矿权挂牌出让结果公示',
        'url': 'https://ky.mnr.gov.cn/jggs/jjgs/202609/t20260910_10309849.htm',
        'source': '矿业权市场',
        'orig_date': '09-09',
        'orig_date_full': '2026-09-09',
        'category': '矿权交易',
        'summary': '甘肃省自然资源厅公示合作市南畔外围铜矿普查探矿权挂牌出让结果，勘查矿种铜矿，面积6.1259平方千米，竞得人 甘肃陇岳矿业有限公司，起始价19.0万元，成交价4619.0万元，公示期 2026年09月10日 至 2026年09月23日。',
        'method': '出让结果', 'mineral': '铜矿', 'area_km2': '6.1259',
        'region': '甘肃甘南州合作市', 'embed': 'ok',
    },
    {
        'title': '甘肃省景泰县猪嘴哑吧外围铜矿普查探矿权挂牌出让结果公示',
        'url': 'https://ky.mnr.gov.cn/jggs/jjgs/202609/t20260910_10309848.htm',
        'source': '矿业权市场',
        'orig_date': '09-09',
        'orig_date_full': '2026-09-09',
        'category': '矿权交易',
        'summary': '甘肃省自然资源厅公示景泰县猪嘴哑吧外围铜矿普查探矿权挂牌出让结果，勘查矿种铜矿，面积7.4297平方千米，竞得人 中疆矿业（天津）有限公司，起始价23.0万元，成交价643.0万元，公示期 2026年09月10日 至 2026年09月23日。',
        'method': '出让结果', 'mineral': '铜矿', 'area_km2': '7.4297',
        'region': '甘肃白银市景泰县', 'embed': 'ok',
    },
    {
        'title': '绛县腾光采石厂（普通合伙）采矿权转让公示',
        'url': 'https://ky.mnr.gov.cn/zrgs/ckzrgs/202609/t20260910_10309844.htm',
        'source': '矿业权市场',
        'orig_date': '09-09',
        'orig_date_full': '2026-09-09',
        'category': '矿权交易',
        'summary': '运城市规划和自然资源局公示绛县腾光采石厂采矿权转让事项，转让人为绛县腾光采石厂（普通合伙），受让人为山西喜善新能源开发有限公司，采矿矿种建筑石料用灰岩，面积0.1308平方千米，开采标高1000米至901米，转让方式出售，公示期 2026年09月09日 至 2026年09月21日。',
        'method': '转让公示', 'mineral': '石灰岩', 'area_km2': '0.1308',
        'region': '山西运城市绛县', 'embed': 'ok',
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

have = {it.get('url', '') for it in lib}
added = 0
for it in ITEMS:
    if it['url'] in have:
        continue
    it['id'] = hashlib.md5(it['url'].encode('utf-8')).hexdigest()[:12]
    it['report_date'] = TODAY
    it['is_new'] = False
    it['tags'] = []
    it['first_seen'] = TODAY
    it['last_seen'] = TODAY
    lib.insert(0, it)
    added += 1

if isinstance(d, list):
    json.dump(lib, open(FN, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
else:
    d['news'] = lib
    d['updated'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json.dump(d, open(FN, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

print('rights added:', added, 'total library:', len(lib))
