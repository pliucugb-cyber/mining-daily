# -*- coding: utf-8 -*-
"""更新四个分析文件：morning_report.json / sentiment.json / signals.json / alerts.json
数据源：mining_news.json + price_history_detail.json + lme_data.json
报告日期 2026-10-25（周日休市；国内 SHFE/上金所/GFEX 用 10-23 收盘、LME 用 10-23 收盘口径）
morning_report 固定五节：行情 / 政策与产业 / 勘查与技术 / 并购与投资 / 矿权市场
"""
import json, datetime, collections, re
import update_analysis_common as ua
from update_analysis_common import (text, score_item, label, trend, fmt_bullet,
    is_low_value_notice, recent_items, to_items, digest_summary,
    POS, NEG, COMM, THEMES, LOW_VALUE_NOTICE, ROUTINE_NOTICE, BRIEF_MAX,
    DOM, LME_MAP, NOTE, SEC_NAMES)

REPORT = '2026-10-25'
ASOF = '10-23'
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
_dom_pairs = [(r[0], r[2]) for r in _rows if r[5] == '国内']
_lme_pairs = [(r[0], r[2]) for r in _rows if r[5] == 'LME']
_dom_fmt = '、'.join('%s %+.2f%%' % (n, v) for n, v in sorted(_dom_pairs, key=lambda x: -x[1]))
_lme_fmt = '、'.join('%s %+.2f%%' % (n, v) for n, v in sorted(_lme_pairs, key=lambda x: -x[1]))
# —— 行情：只保留领涨/领跌要点 + 一句点评 ——
_price_comment = ('- 国内 %s 收盘：%s。'
                  'LME 六金属 %s 收盘（末点与价格卡同源）：%s。'
                  % (ph['cum']['points'][-1][0], _dom_fmt, ASOF, _lme_fmt))

# 「政策与产业」= 政策与监管 + 行业动态 两源（2026-09-12 修正）：
_policy_items = recent_items('政策与监管', drop_notice=True) + recent_items('行业动态', drop_notice=True)

# 矿权市场（数据层 rights，单独从月度库读取，不进 index.html 正文）
rights = []
for _mf in ('data/news_2026-10.json', 'data/news_2026-09.json'):
    try:
        _rl = json.load(open(_mf, encoding='utf-8'))['news']
    except Exception:
        continue
    rights += [n for n in _rl if n.get('category') == '矿权交易']
rights.sort(key=lambda x: x.get('orig_date_full', ''), reverse=True)
rk_new = [r for r in rights if r.get('first_seen', '') == REPORT]
rights_highlights = '；'.join(
    '%s（%s）' % (r['title'].split('探矿权')[0].split('采矿权')[0][:18], r.get('orig_date', ''))
    for r in (rk_new or rights)[:4]) or '无'
rights_text = ('矿权交易专区窗口内累计 %d 宗（挂牌/协议/转让/结果）；' % len(rights) +
               ('今日新增 %d 宗：%s。' % (len(rk_new), rights_highlights) if rk_new
                else '今日无新增矿权公告，最新一批：%s。' % rights_highlights))


# ---------- 简报精炼 ----------
# —— 行情两行：按当日现算，控制 ≤BRIEF_MAX 字 ——
_defs = sorted(_dom_pairs, key=lambda x: -x[1])
_ldefs = sorted(_lme_pairs, key=lambda x: -x[1])


def _fmt_pair(pairs, top=True):
    picks = pairs[:2] if top else pairs[-2:]
    if not top:
        picks = list(reversed(pairs[-2:]))
    return '、'.join('%s %+.2f%%' % (nm, v) for nm, v in picks)


_dom_date = ph['cum']['points'][-1][0]


def _lead_words(pairs):
    """全跌时说「跌幅最小/最大」、全涨时说「领涨/涨幅最小」，否则「领涨/领跌」。"""
    if not pairs:
        return '领涨', '领跌'
    if pairs[0][1] <= 0:
        return '跌幅最小', '跌幅最大'
    if pairs[-1][1] >= 0:
        return '领涨', '涨幅最小'
    return '领涨', '领跌'


_w_up, _w_dn = _lead_words(_defs)
_lw_up, _lw_dn = _lead_words(_ldefs)


def _dn_frag(pairs):
    """跌方片段：若倒数第二为正、倒数第一为负，只取真正的下跌项，避免「涨幅」被说成「领跌」。"""
    if len(pairs) >= 2 and pairs[-1][1] < 0 <= pairs[-2][1]:
        return '、'.join('%s %+.2f%%' % (nm, v) for nm, v in pairs[-1:])
    return _fmt_pair(pairs, False)


_w_dn = '领跌' if _defs[-1][1] < 0 else '涨幅最小'
_lw_dn = '领跌' if _ldefs[-1][1] < 0 else '涨幅最小'
_DF_DN = _dn_frag(_defs)
_LD_DN = _dn_frag(_ldefs)
_t1 = '国内 %s 收盘：%s %s，%s %s。' % (_dom_date, _fmt_pair(_defs, True), _w_up,
                                       _DF_DN, _w_dn)
if len(_t1) > BRIEF_MAX:
    _t1 = '国内 %s 收盘：%s %s，%s %s。' % (
        _dom_date,
        '、'.join('%s %+.2f%%' % (nm, v) for nm, v in _defs[:1]), _w_up,
        '、'.join('%s %+.2f%%' % (nm, v) for nm, v in _defs[-1:]), _w_dn)
_t2 = 'LME 六金属 %s 收盘：%s %s，%s %s。' % (ASOF, _fmt_pair(_ldefs, True), _lw_up,
                                             _LD_DN, _lw_dn)
if len(_t2) > BRIEF_MAX:
    _t2 = 'LME 六金属 %s 收盘：%s %s，%s %s。' % (
        ASOF,
        '、'.join('%s %+.2f%%' % (nm, v) for nm, v in _ldefs[:1]), _lw_up,
        '、'.join('%s %+.2f%%' % (nm, v) for nm, v in _ldefs[-1:]), _lw_dn)

BRIEF_DIGEST = [
    {'cat': '行情', 'k': '', 't': _t1},
    {'cat': '行情', 'k': '', 't': _t2},
    {'cat': '政策与产业', 'k': '铝型材',
     't': '新西兰认定进口铝型材未达严重损害标准，终止保障措施调查、不设限。'},
    {'cat': '政策与产业', 'k': '超范围采矿',
     't': '中国稀土子公司超采稀土氧化物 7.17 吨案移送审查起诉，已缴罚款 396.16 万元。'},
    {'cat': '政策与产业', 'k': 'PCB 钻针棒',
     't': '中钨高新投 1.31 亿元扩产 PCB 钻针棒，新增年产能 2,000 万支。'},
    {'cat': '政策与产业', 'k': '37 家电池',
     't': '37 家电池新能源企业三季报最高增 19,540.5%，6 家扭亏，材料环节最受益。'},
    {'cat': '勘查与技术', 'k': 'Queensway',
     't': 'New Found 上调 Queensway 金矿税后净现值至 12.3 亿美元，资源量增 38%。'},
    {'cat': '勘查与技术', 'k': 'Kodal',
     't': 'Kodal 以 30 万美元入股加纳锂矿，五年至少投 1,300 万美元勘查。'},
    {'cat': '并购与投资', 'k': '债转股',
     't': '大中矿业以债转股向湖南大中赫锂矿增资 10 亿元，注册资本增至 20 亿元。'},
    {'cat': '并购与投资', 'k': '招金瑞宁',
     't': '招金集团收购招金瑞宁 20% 股权，持股升至 64.45%，控股股东与实控人不变。'},
    {'cat': '并购与投资', 'k': '宏联电子',
     't': '新铝时代收购东莞宏联电子 100% 股权完成过户，过渡期未亏损。'},
    {'cat': '并购与投资', 'k': '盛和资源',
     't': '盛和资源出让 4 家稀土冶炼子公司部分股权，与中稀集团合作、仍主导经营。'},
    {'cat': '矿权市场', 'k': '',
     't': '矿权专区近 14 日窗口累计 55 宗；今日新增 4 宗，含修水下汪坑铜探矿权出让、宜章山门口锡矿转让。'},
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
print('_price_comment:', _price_comment)
