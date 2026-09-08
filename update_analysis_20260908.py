# -*- coding: utf-8 -*-
"""
更新四个分析文件：morning_report.json / sentiment.json / signals.json / alerts.json
数据源：mining_news.json（110 条，今日新增 32 条）+ price_history_detail.json（15 品种日 K）
报告日期 2026-09-08（国内 SHFE/上金所最新收盘 09-07；LME 09-08 电子盘）
"""
import json, datetime, collections

REPORT = '2026-09-08'
ASOF = '2026-09-07'
NOW = datetime.datetime.now().astimezone(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')

news = json.load(open('mining_news.json', encoding='utf-8'))['news']
ph = json.load(open('price_history_detail.json', encoding='utf-8'))['series']

COMM = {
    '铜': ['铜'], '铝': ['铝'], '铅': ['铅'], '锌': ['锌'], '镍': ['镍'],
    '锡': ['锡'], '金': ['金'], '银': ['银'], '锂': ['锂', '碳酸锂'],
    '钴': ['钴'], '稀土': ['稀土'], '钪': ['钪'], '锑': ['锑'],
    '钼': ['钼'], '钨': ['钨'], '锗': ['锗'], '磷': ['磷'],
    '铂族': ['铂', '钯'], '铀': ['铀'], '铁矿': ['铁矿', '铁矿石'],
    '钛': ['钛'], '铍': ['铍'], '钽铌': ['钽', '铌'],
}
THEMES = {
    '价格': ['价格', '美元', '元/吨', '上涨', '下跌', '涨幅', '跌幅', '收于', '报价'],
    '矿权': ['探矿权', '采矿权', '出让', '挂牌', '拍卖', '竞买', '起始价', '转让'],
    '找矿': ['找矿', '勘查', '勘探', '资源量', '见矿', '钻探', '钻孔', '新发现', '增储', '靶区'],
    '政策': ['政策', '规划', '监管', '通知', '办法', '大会', '年会', '论坛', '意见', '公示'],
    '国际': ['国际', '全球', '海外', '美元', '智利', '澳洲', '西澳', '非洲', '美国', '巴西',
             '南非', '哥伦比亚', '欧盟', '土耳其', '印尼', '淡水河谷'],
    '技术': ['技术', '工艺', '智能', '数字化', '回收率', '无人驾驶', '双碳', '低碳', '绿色', '数字孪生'],
}
POS = ['突破', '重大', '新增', '升级', '上涨', '增长', '创新高', '达标', '获批', '加速',
       '提速', '提升', '新高', '先进', '领先', '最大', '潜力', '投产', '开幕', '达成', '一等奖']
NEG = ['下跌', '下降', '回落', '下滑', '减产', '停产', '短缺', '风险', '约束', '收紧',
       '亏损', '事故', '灾害', '违规', '处罚', '暂停', '扰动', '瓶颈', '压力', '延期', '搁置']


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

# ---------- 3. alerts.json（单日涨跌超 5% 记 high，超 3% 记 medium） ----------
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
        sev = 'high'
    elif abs(pct) >= 3:
        sev = 'medium'
    else:
        continue
    alerts.append({
        'commodity': name, 'market': mkt, 'move': '%+.2f%%' % pct,
        'severity': sev,
        'detail': '%s（%s）最新收报 %s，单日 %+.2f%%（数据日期 %s）。'
                  % (name, mkt, format(last[1], ',.2f'), pct, last[0]),
        'type': 'price',
    })

if alerts:
    summary = '今日异动 %d 项：' % len(alerts) + '；'.join(
        '%s %s（%s）' % (a['commodity'], a['move'], a['market']) for a in alerts) + '。'
else:
    summary = '15 个品种单日涨跌幅均未超过 3%，无显著异动。'
max_sev = 'high' if any(a['severity'] == 'high' for a in alerts) else (
    'medium' if any(a['severity'] == 'medium' for a in alerts) else 'none')

alerts_obj = {
    'date': REPORT, 'has_history': True, 'history_days': hist_days,
    'alerts': alerts, 'summary': summary, 'max_severity': max_sev,
}
json.dump(alerts_obj, open('alerts.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------- 4. morning_report.json ----------
new_items = [n for n in news if n.get('is_new')]
headlines = [{'d': n.get('orig_date_full', ''), 't': n['title'], 's': n['source']} for n in new_items]

top_news = [{'d': n.get('orig_date_full', ''), 't': n['title'], 's': n['source'], 'u': n['url']}
            for n in new_items[:5]]


def fmt_bullet(n):
    body = (n.get('summary') or n.get('title') or '').strip()
    if not body:
        return ''
    s = n.get('source', '').strip()
    return '- %s%s' % (body, '（%s）' % s if s else '')


def recent_items(category, limit=6):
    arr = [n for n in news if n.get('category') == category and n.get('is_new')]
    arr.sort(key=lambda x: x.get('orig_date_full', ''), reverse=True)
    return arr[:limit]


policy_text = '\n'.join(fmt_bullet(n) for n in recent_items('行业动态')) or '今日暂无新的政策与产业动态。'
tech_text = '\n'.join(fmt_bullet(n) for n in recent_items('找矿成果与勘查技术')) or '今日暂无新的勘查与技术动态。'
ma_text = '\n'.join(fmt_bullet(n) for n in recent_items('并购与投资')) or '今日暂无新增并购/投资类公告（巨潮接口 09-08 返回 504，次日补抓）。'


def _ph_q(key):
    p = ph[key]['points']
    last, prev = p[-1][1], p[-2][1]
    pct = (last - prev) / prev * 100 if prev else 0.0
    return last, pct


def _fmt_pct(x):
    return ('+%.2f%%' if x >= 0 else '%.2f%%') % x


_lme = {name: _ph_q(k) for k, name in [('lcpt', '铜'), ('lalt', '铝'), ('lznt', '锌'),
                                       ('lldt', '铅'), ('lnkt', '镍'), ('ltnt', '锡')]}
_lme_up = ['%s %s（%s）' % (n, format(v[0], ',.1f'), _fmt_pct(v[1])) for n, v in _lme.items() if v[1] > 0.001]
_lme_down = ['%s %s（%s）' % (n, format(v[0], ',.1f'), _fmt_pct(v[1])) for n, v in _lme.items() if v[1] < -0.001]
_lme_flat = ['%s %s（%s）' % (n, format(v[0], ',.1f'), _fmt_pct(v[1])) for n, v in _lme.items() if -0.001 <= v[1] <= 0.001]
lme_text = 'LME 09-08 收盘（美元/吨）——' + '、'.join(_lme_up) + '偏强，' + '、'.join(_lme_down) + '走弱'
if _lme_flat:
    lme_text += '，' + '、'.join(_lme_flat) + '持平'

report = """**行情：**
国内 09-07 收盘全线走强：沪锌 27,095 元/吨（+1.31%）领涨、沪铜 109,410 元/吨（+0.58%）、沪锡 418,870 元/吨（+0.58%）、沪铝 24,420 元/吨（+0.54%）、沪铅 16,210 元/吨（+0.50%）、沪镍 127,820 元/吨（+0.03%）；贵金属回调，上海金 950.78 元/克（-1.57%）、白银 15,990 元/千克（-1.60%）；碳酸锂 142,200 元/吨（+0.18%）止跌企稳；电解钴无当日源，沿用上日 SMM 304,940 元/吨。{lme_text}。伦铜受关税套利挤仓与海外大矿减产推动创历史新高，伦锌续刷逾 4 年新高，锌为当前最强品种；贵金属在美联储鹰派预期升温下高位回吐。

**政策与产业：**
{policy_text}

**勘查与技术：**
{tech_text}

**并购与投资：**
{ma_text}

**矿权市场：**
- 江西省宜丰县鸦溪铜多金属矿详查探矿权转让公示（赣自然探转公示〔2026〕50号）：江西省地质局第一地质大队 → 南昌纪华矿业有限公司，铜矿，0.3840 平方千米。
- 江西省永新县铜锣山铜多金属矿详查探矿权转让公示（〔2026〕47号）：江西省地质局第一地质大队 → 南昌纪华矿业有限公司，铜矿，1.6720 平方千米。
- 江西省宜春市袁州区何家坪钽铌矿详查（〔2026〕49号）、奉新县坪头岭钽铌矿详查（〔2026〕48号）探矿权转让公示：均转让至纪华矿业（宜春）有限公司，铌钽矿，面积分别 0.1920／0.1840 平方千米。
- 江西省永丰县正坑金银铅矿详查探矿权转让公示（〔2026〕46号）：江西省地质矿产开发总公司 → 吉安金诺矿业有限公司，金矿，0.5600 平方千米。
- 陕西省勉县铺沟铅锌矿采矿权转让公示（陕自然资转公示〔2026〕2号）：铅矿、锌矿，矿区面积 0.4474 平方千米，公示期 09-07 至 09-18。
（以上 6 宗均为 09-07 发布、09-08 进入矿业权市场专区，详见「矿权交易」板块。）

**风险提示：**
铜价创历史新高后波动加剧，美国铜关税政策迟迟未落地、COMEX 库存连续 53 天升至 69.36 万公吨创纪录，一旦政策明朗存在挤仓反转与进口断崖风险；锌价逼近四年新高但需求端并未同步改善，警惕高位回调；MHP 钴计价系数由约 90% 回落至 67%，印尼 HPAL 厂商利润承压，或传导至镍钴供给；澳洲 Aurukun 铝土矿审批二次延期至 2027 年 2 月，1500 万吨项目投产节奏存在不确定性；欧盟拟全面禁止向非 OECD 国家出口含铝废料，再生铝原料流向或重构；贵金属在杰克逊霍尔鹰派信号发酵下高位回撤，注意利率预期反复。""".strip().format(policy_text=policy_text, tech_text=tech_text, ma_text=ma_text, lme_text=lme_text)

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
