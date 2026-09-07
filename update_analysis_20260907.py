# -*- coding: utf-8 -*-
"""
更新四个分析文件：morning_report.json / sentiment.json / signals.json / alerts.json
数据源：mining_news.json（46 条，今日新增 9 条）+ price_history_detail.json（15 品种日 K）+ lme_data.json
报告日期 2026-09-07（周一交易时段进行中，国内最新收盘仍为 09-04，LME 09-07 电子盘由前端 JS 填充）
"""
import json, datetime, collections

REPORT = '2026-09-07'
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
          for th, v in sorted(theme_score.items(), key=lambda kv: -len(kv[1]))]

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
            'detail': '%s%s最新收报 %s，单日 %+.2f%%（数据日期 %s，周一交易时段进行中，国内最新收盘沿用上一交易日 09-04）。'
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
headlines.append({'d': ASOF, 't': '碳酸锂主力再跌 5.30%、贵金属金强银强，基本金属铜锌偏强镍铝走弱', 's': '行情数据'})

top_news = [{'d': n.get('orig_date_full', ''), 't': n['title'], 's': n['source'], 'u': n['url']}
            for n in new_items[:5]]

# 动态生成政策与产业、勘查与技术要点（基于当前白名单内的 mining_news.json）
def fmt_bullet(n):
    body = (n.get('summary') or n.get('title') or '').strip()
    if not body:
        return ''
    s = n.get('source', '').strip()
    return '- %s%s' % (body, '（%s）' % s if s else '')

def recent_items(category, limit=5):
    arr = [n for n in news if n.get('category') == category]
    arr.sort(key=lambda x: x.get('orig_date_full', ''), reverse=True)
    return arr[:limit]

policy_text = '\n'.join(fmt_bullet(n) for n in recent_items('行业动态')) or '今日暂无新的政策与产业动态。'
tech_text = '\n'.join(fmt_bullet(n) for n in recent_items('找矿成果与勘查技术')) or '今日暂无新的勘查与技术动态。'
ma_text = '\n'.join(fmt_bullet(n) for n in recent_items('并购与投资')) or '近 14 日窗口内暂无新增有色金属矿企并购/投资类公告。'

report = """**行情：**
周一交易时段进行中，国内上期所最新官方收盘仍为 09-04（上周五）数据，价格卡沿用并显示；LME 09-07 电子盘窄幅波动——铜 14,400.5 美元/吨（+0.15%）、锌 3,969.5（+0.74%）、铅 1,913.5（+0.37%）偏强，铝 3,295.5（-0.02%）、镍 16,805.0（-0.18%）、锡 54,770.0（-0.15%）走弱。国内基本金属延续"金强锂弱"：上海金 965.96 元/克（+0.79%）、白银 16,250 元/千克（+1.28%）偏强；碳酸锂主力 09-04 收 141,940 元/吨（-5.30%）仍为最弱品种；沪锌 +0.51%、沪铜 +0.34% 偏强，沪镍 -0.86%、沪铝 -0.33% 走弱。详见下方金属价格板块。

**政策与产业：**
{policy_text}

**勘查与技术：**
{tech_text}

**并购与投资：**
{ma_text}

**矿权市场：**
- 甘肃文县范坝交流一带金矿普查探矿权公开出让结果公示（09-07）：竞得人陇南市忠亿矿业开发有限公司，成交价 8365 万元，区块面积 1.4195 平方千米，勘查矿种金矿，拟出让年限 5.0 年，起始价 5.0 万元；公示期 09-07 至 09-18。

**风险提示：** 碳酸锂主力 09-04 单日 -5.30%、两日累计跌逾 12%，短线情绪偏弱，关注锂价下行对上游矿企利润的压制；西藏吉隆"8·26"冰岩崩—泥石流灾害链次生风险仍处高位，源区残留不稳定冰川与岩体需持续监测；周一国内尚无新收盘，价格卡沿用 09-04 数据，盘中波动以 LME 09-07 电子盘为参考。""".strip().format(policy_text=policy_text, tech_text=tech_text, ma_text=ma_text)

import collections as _c
_cat = _c.Counter(n.get('category', '') for n in new_items)

morning = {
    'date': REPORT,
    'report': report,
    'stats': {
        'new_count': len(new_items),
        'total': len(news),
        'by_category': dict(_cat),
    },
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
print('morning  : headlines=%d top_news=%d new_count=%d by_category=%s' %
      (len(headlines), len(top_news), len(new_items), dict(_cat)))
