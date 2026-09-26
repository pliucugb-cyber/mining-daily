# -*- coding: utf-8 -*-
"""更新四个分析文件：morning_report.json / sentiment.json / signals.json / alerts.json
数据源：mining_news.json + price_history_detail.json + lme_data.json
报告日期 2026-09-18（周五盘前；国内 SHFE/上金所最新收盘 09-17；LME 09-16 收盘）
morning_report 固定五节：行情 / 政策与产业 / 勘查与技术 / 并购与投资 / 矿权市场
"""
import json, datetime, collections, re
import update_analysis_common as ua
from update_analysis_common import (text, score_item, label, trend, fmt_bullet,
    is_low_value_notice, recent_items, to_items, digest_summary,
    POS, NEG, COMM, THEMES, LOW_VALUE_NOTICE, ROUTINE_NOTICE, BRIEF_MAX,
    DOM, LME_MAP, NOTE, SEC_NAMES)

REPORT = '2026-09-18'
ASOF = '09-16'
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
_price_comment = ('- 周五盘前国内最新为 9 月 17 日收盘：碳酸锂 +4.26% 领涨，沪铅 +1.64%、沪镍 +1.43%、'
    '沪锡 +0.82%、沪铜 +0.71%、沪铝 +0.17% 收涨，白银 -1.51%、上海金 -0.59%、沪锌 -0.08% 走弱；'
    'LME 六金属多数上涨，伦镍 +1.32%、伦锡 +1.18%、伦铜 +0.96%、伦铝 +0.72%、伦铅 +0.35%，仅伦锌 -0.55%。'
    '驱动上，美元走弱提振以美元计价的基本金属，碳酸锂在矿端扰动与需求预期改善下大幅反弹；'
    '刚果（金）上半年铜出口 172 万吨创历史新高、钴出口因配额制同比降 6.4%，叠加沪铜库存连降 3 周，'
    '铜钴供应格局仍是市场关注焦点；韩国锌业温山冶炼厂焙烧系统发生事故，是否减产待观察，伦锌相对承压。'
    '整体呈「美元走弱、国内普涨、贵金属回调」格局。')
# 「政策与产业」= 政策与监管 + 行业动态 两源（2026-09-12 修正）：
# 此前只喂「行业动态」，节名里的「政策」无对应内容，名不副实。现先政策后产业拼接，
# 两类目内部各自按发布日期倒序；drop_notice 仍生效，剥离治理/信披类公告（见 REFERENCE.md §3）。
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




# ---------- 简报精炼（2026-09-12 三次修订：用户要求「内容本身缩减」）----------
# 演进：① 09-11 用户要「总结全」→ 单条不截断、每节不限条数（§9.2.5 / §10.1）；
#   ② 09-12 上午先做「要点层 + 完整层」两层，用户否决要点层，定为「五节结构化 + 默认收起」。
#   两次都没动**内容长度**：展开后仍是 18 条 / 4184 字、平均每条 232 字 —— 条目直接
#   搬运 news['summary']（与下方新闻卡片同源），等于把新闻列表又抄了一遍。
# ③ 09-12 用户定夺「精炼单条·保留全貌 + 剔除例行条目 + 立即重做当日」：
#   简报条目改为**逐条撰写的精炼句**（BRIEF_DIGEST），不再搬运整段摘要；
#   每条硬上限 BRIEF_MAX 字，超限直接 RuntimeError（逼撰写者压缩，不静默截断）；
#   低信息量例行条目（发运/工商变更/业绩说明会…）不进简报（下方新闻列表仍可查）。
#   某节一条未写时用 digest_summary() 自动截句兜底，保证不空节。
# 详见 REFERENCE.md §16。

# 例行条目关键词：命中即视为低信息量，禁止进简报。与 §3 的低价值公告一脉相承。




# 简报条目：逐条撰写的精炼句（≤BRIEF_MAX 字，只留 主体 + 动作 + 关键数字）。
#   cat = 所属分节；t = 精炼句；k = 用于在当日条目标题里匹配 url 的关键词（空 = 无链接）。
BRIEF_DIGEST = [
    {'cat': '行情', 'k': '',
     't': '碳酸锂 +4.26%、沪铅 +1.64%、沪镍 +1.43% 领涨，沪铜 +0.71%、沪锡 +0.82%；白银 -1.51% 领跌。'},
    {'cat': '行情', 'k': '',
     't': 'LME 六金属多数上涨：伦镍 +1.32%、伦锡 +1.18%、伦铜 +0.96%、伦铝 +0.72%，仅伦锌 -0.55%。'},
    {'cat': '政策与产业', 'k': '矿产资源对外合作可持续发展自律倡议',
     't': '《矿产资源对外合作可持续发展自律倡议》发布，覆盖境外投资、勘查开发与供应链管理全过程。'},
    {'cat': '政策与产业', 'k': '第三批矿区生态修复典型案例',
     't': '自然资源部发布第三批矿区生态修复典型案例 24 个，含废弃矿区、生产矿山、矿业遗迹 3 类。'},
    {'cat': '政策与产业', 'k': '广期所明确多晶硅',
     't': '广期所明确多晶硅 PS2709、碳酸锂 LC2709 合约手续费与单日开仓限额（200 手 / 400 手）。'},
    {'cat': '政策与产业', 'k': '云南铜业碳足迹认证',
     't': '云南铜业碳足迹认证覆盖全部外销终端产品，含阴极铜、阳极铜、硫酸及 4 种铜加工产品。'},
    {'cat': '政策与产业', 'k': '美国启动铟锰镁钛',
     't': '美国面向国内企业招标铟、锰、镁、钛 4 种关键金属投资方案，截至 9 月 17 日，覆盖全产业链。'},
    {'cat': '勘查与技术', 'k': '智能填图',
     't': '我国面向全球首发「智能填图」系统，由中国地质调查局自主研发，覆盖预研到编图全流程。'},
    {'cat': '勘查与技术', 'k': '诺斯曼金矿资源量',
     't': '辛克莱尔黄金澳洲诺斯曼项目金资源量增至 180 万盎司、较 2 月翻倍，仍有 5 台钻机施工。'},
    {'cat': '勘查与技术', 'k': 'Newcore 加纳',
     't': 'Newcore 加纳 Enchi 项目 Boin 矿段见矿 69 米、金品位 2.59 克/吨，含 24 米 6.41 克/吨。'},
    {'cat': '并购与投资', 'k': '藏格矿业联手云图控股',
     't': '藏格矿业联手云图控股以 1.71 亿美元收购刚果（布）Kanga 钾盐项目 92% 股权。'},
    {'cat': '并购与投资', 'k': 'Luca Mining 以 6000 万美元',
     't': 'Luca Mining 以 6000 万美元收购 Agnico 墨西哥 El Barqueño 金银铜项目，获在墨第三个资产。'},
    {'cat': '并购与投资', 'k': '赞比亚 KCM',
     't': '赞比亚 KCM 与中国恩菲签 4.98 亿美元铜尾矿回收厂协议，预计年增铜产量 7 万吨。'},
    {'cat': '矿权市场', 'k': '',
     't': '矿权专区今日新增 3 宗挂牌出让：新疆皮里青煤矿、四川德昌杉树坪脉石英矿、新疆三塘湖五号勘查区。'},
]
# 分节顺序（与 §2 桶序 / generate_YYYYMMDD.py 的 THEME_BUCKET 一致）


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

# —— 关键词 → url / 来源（在当日新增条目标题里找第一条匹配；找不到则留空，优雅降级）——
for _d in BRIEF_DIGEST:
    _d['u'], _d['s'] = '', ''
    if _d['k']:
        for _n in new_items:
            if _d['k'] in (_n.get('title') or ''):
                _d['u'] = _n.get('url', '')
                _d['s'] = (_n.get('source') or '').strip()
                break

# —— 兜底源：某节一条未写时，从该类目当日摘要自动截句（保证不空节）——
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

# report 由 brief_sections 拼出：保证「report 兜底文本」与结构化数据永不失同步。
report = '\n\n'.join(
    '**%s：**\n%s' % (s['name'], '\n'.join(
        '- %s%s' % (it['t'], ('（%s）' % it['s']) if it['s'] else '') for it in s['items']))
    for s in brief_sections) + '\n'

# highlights：单一真源 —— 由 brief_sections 各节首条派生，最多 5 条。
#   前端自 §15 起不再渲染该字段（与「今日要闻」重复），保留产出仅为将来复用/兼容旧前端。
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
print('--- report preview ---')
print(report[:1600])
