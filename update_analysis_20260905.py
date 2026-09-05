# -*- coding: utf-8 -*-
"""
更新四个分析文件：morning_report.json / sentiment.json / signals.json / alerts.json
数据源：mining_news.json（页面 47 条）+ price_history_detail.json（15 品种日 K）+ lme_data.json
报告日期 2026-09-05（周六休市，行情沿用 09-04 收盘）
"""
import json, datetime, collections

REPORT = '2026-09-05'
ASOF   = '2026-09-04'
NOW    = datetime.datetime.now().astimezone(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')

news = json.load(open('mining_news.json', encoding='utf-8'))['news']
ph   = json.load(open('price_history_detail.json', encoding='utf-8'))['series']

# ---------- 品种/主题词典 ----------
COMM = {
    '铜': ['铜'], '铝': ['铝'], '铅': ['铅'], '锌': ['锌'], '镍': ['镍'],
    '锡': ['锡'], '金': ['金'], '银': ['银'], '锂': ['锂', '碳酸锂'],
    '钴': ['钴'], '稀土': ['稀土'], '钪': ['钪'], '锑': ['锑'],
    '钼': ['钼'], '钨': ['钨'], '锗': ['锗'], '磷': ['磷'],
    '铂族': ['铂', '钯'], '铀': ['铀'], '铁矿': ['铁矿', '铁矿石'],
}
THEMES = {
    '价格': ['价格', '美元', '元/吨', '上涨', '下跌', '涨幅', '跌幅', '收于', '报价'],
    '矿权': ['探矿权', '采矿权', '出让', '挂牌', '拍卖', '竞买', '起始价'],
    '找矿': ['找矿', '勘查', '勘探', '资源量', '见矿', '钻探', '钻孔', '新发现', '增储', '靶区'],
    '政策': ['政策', '规划', '监管', '通知', '办法', '大会', '年会', '论坛', '意见'],
    '国际': ['国际', '全球', '海外', '美元', '智利', '澳洲', '西澳', '非洲', '美国', '巴西', '埃塞俄比亚'],
    '技术': ['技术', '工艺', '智能', '数字化', '回收率', '无人驾驶', '双碳', '低碳', '绿色'],
}
# 正向 / 负向情绪词
POS = ['突破', '重大', '新增', '升级', '上涨', '增长', '创新高', '达标', '获批', '加速',
       '提速', '提升', '新高', '先进', '领先', '最大', '潜力', '投产', '开幕', '达成']
NEG = ['下跌', '下降', '回落', '下滑', '减产', '停产', '短缺', '风险', '约束', '收紧',
       '亏损', '事故', '灾害', '违规', '处罚', '暂停', '扰动', '瓶颈', '压力']

def text(n):
    return (n.get('title', '') + ' ' + n.get('summary', ''))

def score_item(n):
    t = text(n)
    s = 50
    for w in POS:
        if w in t:
            s += 6
    for w in NEG:
        if w in t:
            s -= 6
    # 价格类按实际涨跌幅微调
    if '涨' in t and '%' in t:
        s += 4
    if '跌' in t and '%' in t:
        s -= 4
    return max(5, min(95, s))

# ---------- 1. sentiment.json ----------
by_comm = {}
theme_counter = collections.Counter()
theme_score = collections.defaultdict(list)
samples = []

for n in news:
    t = text(n)
    sc = score_item(n)
    hit_c = [c for c, kws in COMM.items() if any(k in t for k in kws)]
    hit_t = [th for th, kws in THEMES.items() if any(k in t for k in kws)]
    for c in hit_c:
        by_comm.setdefault(c, []).append(sc)
    for th in hit_t:
        theme_counter[th] += 1
        theme_score[th].append(sc)
    if n.get('is_new'):
        samples.append({'t': n['title'], 's': n['source'], 'd': n.get('orig_date_full', ''),
                        'score': sc, 'commodities': hit_c[:4], 'themes': hit_t[:4]})

def label(s):
    return '偏多' if s >= 60 else ('偏空' if s < 40 else '中性')

by_commodity = {}
for c, arr in by_comm.items():
    sc = int(round(sum(arr) / len(arr)))
    by_commodity[c] = {'score': sc, 'count': len(arr), 'label': label(sc)}
by_commodity = dict(sorted(by_commodity.items(), key=lambda kv: -kv[1]['score']))

themes = [{'theme': th, 'count': theme_counter[th],
           'score': int(round(sum(v) / len(v)))}
          for th, v in sorted(theme_score.items(), key=lambda kv: -kv[1][0] if False else -len(kv[1]))]

all_scores = [score_item(n) for n in news]
market_index = int(round(sum(all_scores) / len(all_scores)))

sentiment = {
    'date': REPORT,
    'total': len(news),
    'market_index': market_index,
    'market_label': label(market_index),
    'by_commodity': by_commodity,
    'themes': themes,
    'samples': sorted(samples, key=lambda x: -x['score']),
    'source': 'keyword-rule（基于 index.html 收录 %d 条）' % len(news),
}
json.dump(sentiment, open('sentiment.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------- 2. signals.json ----------
def trend(key, days=3):
    p = ph[key]['points']
    if len(p) < days + 1:
        return None, None
    base = p[-1 - days][1]
    last = p[-1][1]
    prev = p[-2][1]
    prev_base = p[-2 - days][1]
    return (last - base) / base * 100, (prev - prev_base) / prev_base * 100

LME_MAP = [('lcpt', 'Cu', '铜'), ('lalt', 'Al', '铝'), ('lznt', 'Zn', '锌'),
           ('lldt', 'Pb', '铅'), ('lnkt', 'Ni', '镍'), ('ltnt', 'Sn', '锡')]
NOTE = {
    '偏强': '三日累计上行，短期偏强',
    '中性': '区间震荡，方向不明',
    '偏弱': '三日累计下行，短期偏弱',
}
metals = []
for key, sym, name in LME_MAP:
    t3, t3p = trend(key)
    if t3 is None:
        continue
    p = ph[key]['points']
    ma5 = round(sum(x[1] for x in p[-5:]) / 5, 2) if len(p) >= 5 else None
    ma10 = round(sum(x[1] for x in p[-10:]) / 10, 2) if len(p) >= 10 else None
    sig = '偏强' if t3 > 0.5 else ('偏弱' if t3 < -0.5 else '中性')
    d = t3 - (t3p or 0)
    delta = '（较前一日 %+.2f%%，%s）' % (d, '加速' if d > 0 else '放缓')
    metals.append({'symbol': sym, 'name': name, 'signal': sig,
                   'position': '3日趋势：%+.2f%%%s' % (t3, delta),
                   'ma5': ma5, 'ma10': ma10, 'ma20': None,
                   'note': NOTE[sig] + ('，MA5=%.1f' % ma5 if ma5 else '')})

hist_days = len(ph['lcpt']['points'])
signals = {
    'date': REPORT,
    'has_history': True,
    'history_days': hist_days,
    'metals': metals,
    'summary': 'LME 六基本金属 3 日趋势：' + '、'.join(
        '%s %s' % (m['name'], m['position'].split('（')[0].replace('3日趋势：', '')) for m in metals
    ) + '；样本 %d 个交易日，MA20 待继续积累。' % hist_days,
}
json.dump(signals, open('signals.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------- 3. alerts.json（单日涨跌超 5% 记 high） ----------
DOM = [('cum', '沪铜', 'SHFE 主连'), ('alm', '沪铝', 'SHFE 主连'), ('pbm', '沪铅', 'SHFE 主连'),
       ('znm', '沪锌', 'SHFE 主连'), ('snm', '沪锡', 'SHFE 主连'), ('nim', '沪镍', 'SHFE 主连'),
       ('au9999', '上海金', '上金所 Au99.99'), ('agtd', '白银', '上金所 Ag(T+D)'),
       ('lcm', '碳酸锂', 'GFEX 主连')]
alerts = []
for key, name, mkt in DOM + [(k, n, 'LME 03') for k, n, s in LME_MAP]:
    p = ph[key]['points']
    last, prev = p[-1], p[-2]
    pct = (last[1] - prev[1]) / prev[1] * 100
    if abs(pct) >= 5:
        alerts.append({
            'commodity': name, 'market': mkt, 'move': '%+.2f%%' % pct,
            'severity': 'high',
            'detail': '%s%s最新收报 %s，单日 %+.2f%%（数据日期 %s，周六休市沿用上一交易日收盘）。'
                      % (name, mkt and '（%s）' % mkt or '', format(last[1], ',.2f'), pct, last[0]),
            'type': 'price',
        })

if alerts:
    summary = '今日异动 %d 项：' % len(alerts) + '；'.join(
        '%s %s（%s）' % (a['commodity'], a['move'], a['market']) for a in alerts) + '。'
else:
    summary = '15 个品种单日涨跌幅均未超过 5%，无显著异动。'
max_sev = 'high' if any(a['severity'] == 'high' for a in alerts) else (
    'medium' if any(a['severity'] == 'medium' for a in alerts) else 'none')

alerts_obj = {
    'date': REPORT, 'has_history': True, 'history_days': hist_days,
    'alerts': alerts, 'summary': summary, 'max_severity': max_sev,
}
json.dump(alerts_obj, open('alerts.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------- 4. morning_report.json ----------
def pct_of(key):
    p = ph[key]['points']
    return (p[-1][1] - p[-2][1]) / p[-2][1] * 100

def price_of(key):
    return ph[key]['points'][-1][1]

new_items = [n for n in news if n.get('is_new')]
headlines = [{'d': n.get('orig_date_full', ''), 't': n['title'], 's': n['source']} for n in new_items]
headlines.append({'d': ASOF, 't': '碳酸锂主力再跌 5.30%、钯价单日大涨 5.84% 领涨贵金属', 's': '行情数据'})

top_news = [{'d': n.get('orig_date_full', ''), 't': n['title'], 's': n['source'], 'u': n['url']}
            for n in new_items[:5]]

report = """**总览：** 今日（09-05，周六休市，行情沿用 09-04 收盘）市场延续“贵金属强、锂弱”的分化格局。国际方面钯价单日大涨 5.84% 至 1440.0 美元/盎司领涨，铂涨 3.93%、银涨 2.52%、金涨 1.96% 至 4473.6 美元/盎司；国内上海金 Au99.99 报 965.96 元/克（+0.79%）、白银 Ag(T+D) 16,250 元/千克（+1.28%）。碳酸锂主力连续第二日重挫，09-04 再跌 5.30% 至 141,940 元/吨（前一日 -7.41%），两日累计跌幅超 12%。基本金属小幅分化：沪锌 +0.51%、沪铜 +0.34% 偏强，沪镍 -0.86%、沪铝 -0.33% 走弱；LME 六金属涨跌互现，锌 +1.10%、铜 +0.11% 小幅收涨，铝 -0.65%、镍 -0.41% 回落。

**今日头条：**
- 安徽茶亭超大型铜多金属矿跑出深部找矿“中国速度”：设计钻探 96,240 米、最大孔深 2000 米，力争一年完成常规需 2~3 年的工作量。
- 国际钯价大幅上涨 5.84% 至 1440.0 美元/盎司，铂、银、金同步上行，贵金属全线走强。
- 2026（第二十八届）中国国际矿业大会将于 9 月 10—12 日在天津举办，新增矿业权交易板块，展览面积 6.5 万平方米创历届新高。
- 四川、河北集中出让 3 宗探矿权：峨边桥儿沟磷铅锌矿（29.28 km²、起始价 352 万元）、会理关河铜镍矿（10.46 km²、84 万元）、宽城蒋杖子村金矿（3.12 km²、9.36 万元）。
- 第十三届中国锑业年会在昆明召开，协会提出严控新增产能、夯实资源保障、推进锑期货上市研究等八点建议。
- 烟台金矿勘查获新突破：烟台海岸带地质调查中心基本查明 3 个完工标准图幅的成矿地质条件，划定多处优质成矿有利区。
- 埃塞俄比亚 SEDEX 型矿床潜力分析：阿法尔洼地蒸发岩 + 阿拉伯—努比亚地盾金属源 + 碳酸盐/碳质页岩还原障三要素齐备。
- 西澳格拉斯帕奇项目钪资源量升级至 9.58 亿吨（钪金属量 4.7 万吨），为世界最大已公开钪资源量。

**风险提示：** 碳酸锂两日累计跌逾 12%，短线情绪偏弱，关注锂价下行对上游矿企利润的压制；Sibanye-Stillwater 美国矿区劳资谈判破裂、罢工风险上升，铂族金属供给存隐忧；电解钴 SMM 周末未更新，价格卡沿用上日数值。""".strip()

morning = {
    'date': REPORT,
    'report': report,
    'sections': {
        'sentiment': sentiment,
        'signals': signals,
        'anomalies': alerts_obj,
        'headlines': headlines,
    },
    'top_news': top_news,
    'source': 'llm',
    'updated': NOW,
}
json.dump(morning, open('morning_report.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

print('sentiment: index=%d(%s) commodities=%d themes=%d samples=%d' %
      (market_index, sentiment['market_label'], len(by_commodity), len(themes), len(samples)))
print('signals  : %d metals, hist=%d days' % (len(metals), hist_days))
print('alerts   : %d, max_severity=%s' % (len(alerts), max_sev))
for a in alerts:
    print('   -', a['commodity'], a['move'], a['market'])
print('morning  : headlines=%d top_news=%d' % (len(headlines), len(top_news)))
