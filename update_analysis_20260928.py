# -*- coding: utf-8 -*-
"""更新四个分析文件：morning_report.json / sentiment.json / signals.json / alerts.json
数据源：mining_news.json + price_history_detail.json + lme_data.json
报告日期 2026-09-28（周一；国内 SHFE/上金所 09-25 起中秋休市，最新收盘 09-24；
LME 当日未收盘，口径对齐最近已收盘日 09-25，卡片=走势图口径）
morning_report 固定五节：行情 / 政策与产业 / 勘查与技术 / 并购与投资 / 矿权市场
"""
import json, datetime, collections, re
import update_analysis_common as ua
from update_analysis_common import (text, score_item, label, trend, fmt_bullet,
    is_low_value_notice, recent_items, to_items, digest_summary,
    POS, NEG, COMM, THEMES, LOW_VALUE_NOTICE, ROUTINE_NOTICE, BRIEF_MAX,
    DOM, LME_MAP, NOTE, SEC_NAMES)

REPORT = '2026-09-28'
ASOF = '09-25'
NOW = datetime.datetime.now().astimezone(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')

news = json.load(open('mining_news.json', encoding='utf-8'))['news']
ph = json.load(open('price_history_detail.json', encoding='utf-8'))['series']
lme = json.load(open('lme_data.json', encoding='utf-8'))['metals']
ua.bind(news, ph)


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

# ---------- 3. alerts.json ----------
alerts = []
for key, name, mkt in DOM:
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
# LME 异动以 lme_data.json（fetch_lme.py 当日收盘）为准，不用价格历史里的滞后序列
for m in lme:
    if m['price'] is None or m.get('chg_pct') is None:
        continue
    pct = m['chg_pct']
    if abs(pct) >= 5:
        sev = 'high'
    elif abs(pct) >= 3:
        sev = 'medium'
    else:
        continue
    alerts.append({
        'commodity': m['zh'].replace('LME ', ''), 'market': 'LME 03', 'move': '%+.2f%%' % pct,
        'severity': sev,
        'detail': '%s（LME 03）最新收报 %s 美元/吨，单日 %+.2f%%（数据日期 %s）。'
                  % (m['zh'], format(m['price'], ',.2f'), pct, ASOF),
        'type': 'price',
    })
alerts.sort(key=lambda a: abs(float(a['move'].rstrip('%'))), reverse=True)

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


# —— 行情：只保留领涨/领跌要点 + 一句点评（完整报价由价格卡承担，不重复枚举）——
_rows = []
for key, name, unit, nd in [('cum', '沪铜', '元/吨', 0), ('alm', '沪铝', '元/吨', 0),
                            ('pbm', '沪铅', '元/吨', 0), ('znm', '沪锌', '元/吨', 0),
                            ('snm', '沪锡', '元/吨', 0), ('nim', '沪镍', '元/吨', 0),
                            ('au9999', '上海金', '元/克', 2), ('agtd', '白银', '元/千克', 0),
                            ('lcm', '碳酸锂', '元/吨', 0)]:
    p = ph[key]['points']
    pct = (p[-1][1] - p[-2][1]) / p[-2][1] * 100
    _rows.append((name, p[-1][1], pct, unit, nd, '国内'))
for m in lme:
    if m['price'] is None:
        continue
    _rows.append((m['zh'], m['price'], m['chg_pct'], '美元/吨', 2, 'LME'))
_rows.sort(key=lambda x: -x[2])
_up = _rows[0]
_down = _rows[-1]
quote_lines = [
    '- 领涨：%s %s%s（%+.2f%%）；领跌：%s %s%s（%+.2f%%）。' % (
        _up[0], format(_up[1], ',.%df' % _up[4]), _up[3], _up[2],
        _down[0], format(_down[1], ',.%df' % _down[4]), _down[3], _down[2]),
]
_price_comment = ('- 周一早盘国内尚未开盘，行情与前一版一致：国内最新为 09-24 日收盘（09-25 起中秋休市），沪锌 +0.92%、沪锡 +0.45% 收涨，沪铝 -0.02%、沪铜 -0.18%、沪铅 -0.40%、上海金 -1.26%、白银 -3.12%、碳酸锂 -3.48% 走弱。LME 六金属（行情末点与价格卡同源，均为 09-25 日收盘）：伦锡 +1.30%、伦铝 +0.80% 上涨，伦铜 -0.10%、伦铅 -0.13%、伦镍 -0.88%、伦锌 -1.80% 下跌。假期期间外盘多数回落，国内节后首个交易日尚未开盘，价格与前一版保持一致。')
# 「政策与产业」= 政策与监管 + 行业动态 两源（2026-09-12 修正）：
_policy_items = recent_items('政策与监管', drop_notice=True) + recent_items('行业动态', drop_notice=True)

# 矿权市场（数据层 rights，单独从月度库读取，不进 index.html 正文）
rights_lib = json.load(open('data/news_2026-09.json', encoding='utf-8'))['news']
rights = [n for n in rights_lib if n.get('category') == '矿权交易']
rights.sort(key=lambda x: x.get('orig_date_full', ''), reverse=True)
rk_new = [r for r in rights if r.get('first_seen', '') == REPORT]
rights_highlights = '；'.join(
    '%s（%s）' % (r['title'].split('探矿权')[0].split('采矿权')[0][:18], r.get('orig_date', ''))
    for r in (rk_new or rights)[:4]) or '无'
rights_text = ('矿权交易专区窗口内累计 %d 宗（挂牌/协议/转让/结果）；' % len(rights) +
               ('今日新增 %d 宗：%s。' % (len(rk_new), rights_highlights) if rk_new
                else '今日无新增矿权公告，最新一批：%s。' % rights_highlights))


# ---------- 简报精炼 ----------
BRIEF_DIGEST = [
    {'cat': '行情', 'k': '',
     't': '国内 09-24 收盘（节后未开盘）：沪锌 +0.92%、沪锡 +0.45% 收涨，碳酸锂 -3.48%、白银 -3.12% 走弱。'},
    {'cat': '行情', 'k': '',
     't': 'LME 末点仍为 09-25 收盘：伦锡 +1.30%、伦铝 +0.80% 上涨，伦锌 -1.80%、伦镍 -0.88% 下跌。'},
    {'cat': '行情', 'k': '28.8',
     't': '8 月有色金属价格环比上涨 3.9%、同比上涨 28.8%，铜锌铝环比分别涨 4.0%、3.9%、3.8%。'},
    {'cat': '政策与产业', 'k': '镨钕',
     't': 'SMM：中美经贸对话提振镨钕市场情绪，但价格最终仍由基本面主导。'},
    {'cat': '政策与产业', 'k': 'TC',
     't': 'TC 深度负值下 18 家上市铜企半年报全线盈利，利润主要来自硫酸等副产品。'},
    {'cat': '政策与产业', 'k': '镁合金电驱壳体',
     't': '明月湖实验室研制高性能镁合金电驱壳体，整体减重 30%，预计 2027 年上半年量产。'},
    {'cat': '政策与产业', 'k': '海绵钛',
     't': '攀钢 1—8 月海绵钛出口同比大幅增长，超额完成阶段性奋斗目标。'},
    {'cat': '勘查与技术', 'k': '于沟',
     't': '江西物化探大队完成新疆于沟钼多金属矿普查野外物探，为钻探验证提供依据。'},
    {'cat': '勘查与技术', 'k': '镁稀土',
     't': '洛阳特种材料研究院成形单重 1100kg 镁稀土合金圆饼，攻克超大规格均质制备难题。'},
    {'cat': '并购与投资', 'k': '湖南裕能',
     't': '湖南裕能西班牙项目投资额提高至约 16.5 亿元，规划年产能 7 万吨正极材料。'},
    {'cat': '并购与投资', 'k': '恩捷',
     't': '恩捷股份收购子公司少数股权并与亿纬锂能设立合资公司事项取得进展。'},
    {'cat': '矿权市场', 'k': '',
     't': '矿权专区新增 4 宗探矿权变更登记，均为内蒙古锌、银、铅多金属矿项目。'},
]

# —— 三项硬校验：超长 / 越界分节 / 混入例行条目，任一命中即拒绝生成（fail loud）——
for _d in BRIEF_DIGEST:
    if _d['cat'] not in SEC_NAMES:
        raise RuntimeError('BRIEF_DIGEST 分节名不在五节内：%s' % _d['cat'])
    if len(_d['t']) > BRIEF_MAX:
        raise RuntimeError('BRIEF_DIGEST 条目超 %d 字（实 %d 字）：%s'
                           % (BRIEF_MAX, len(_d['t']), _d['t']))
    for _w in ROUTINE_NOTICE:
        if _w in _d['t']:
            raise RuntimeError('BRIEF_DIGEST 混入例行条目（命中「%s」）：%s' % (_w, _d['t']))

# —— 关键词 → url / 来源 ——
for _d in BRIEF_DIGEST:
    _d['u'], _d['s'] = '', ''
    if _d['k']:
        for _n in new_items:
            if _d['k'] in (_n.get('title') or ''):
                _d['u'] = _n.get('url', '')
                _d['s'] = (_n.get('source') or '').strip()
                break

# —— 兜底源 ——
SEC_FALLBACK = {
    '政策与产业': _policy_items,
    '勘查与技术': recent_items('找矿成果与勘查技术'),
    '并购与投资': recent_items('并购与投资'),
}

brief_sections = []
for _name in SEC_NAMES:
    _items = [{'t': d['t'], 'u': d['u'], 's': d['s']}
              for d in BRIEF_DIGEST if d['cat'] == _name]
    if not _items and _name in SEC_FALLBACK:
        _items = [{'t': digest_summary(x.get('summary') or x.get('title') or ''),
                   'u': x.get('url', ''), 's': (x.get('source') or '').strip()}
                  for x in SEC_FALLBACK[_name][:3]]
        _items = [i for i in _items if i['t']]
    if not _items and _name == '行情':
        _items = [{'t': quote_lines[0][2:], 'u': '', 's': ''}]
    if not _items and _name == '矿权市场':
        _items = [{'t': rights_text, 'u': '', 's': ''}]
    if _items:
        brief_sections.append({'name': _name, 'count': len(_items), 'items': _items})

report = '\n\n'.join(
    '**%s：**\n%s' % (s['name'], '\n'.join(
        '- %s%s' % (it['t'], ('（%s）' % it['s']) if it['s'] else '') for it in s['items']))
    for s in brief_sections) + '\n'

highlights = [{'cat': s['name'], 't': s['items'][0]['t'], 'u': s['items'][0]['u']}
              for s in brief_sections][:5]

_cat = collections.Counter(n.get('category', '') for n in new_items)

morning = {
    'date': REPORT,
    'report': report,
    'highlights': highlights,
    'brief_sections': brief_sections,
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
print('--- brief sections ---')
for s in brief_sections:
    print('  [%s] %d 条，最长 %d 字' % (s['name'], s['count'], max(len(i['t']) for i in s['items'])))
print('total digest chars:', sum(len(i['t']) for s in brief_sections for i in s['items']))
print('--- report preview ---')
print(report[:1200])
