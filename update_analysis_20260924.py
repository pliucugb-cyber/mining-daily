# -*- coding: utf-8 -*-
"""更新四个分析文件：morning_report.json / sentiment.json / signals.json / alerts.json
数据源：mining_news.json + price_history_detail.json + lme_data.json
报告日期 2026-09-24（周四盘前，国内未开盘；国内 SHFE/上金所最新收盘 09-23；LME 09-22 收盘，东财日K末点=09-22）
morning_report 固定五节：行情 / 政策与产业 / 勘查与技术 / 并购与投资 / 矿权市场
"""
import json, datetime, collections, re

REPORT = '2026-09-24'
ASOF = '09-22'
NOW = datetime.datetime.now().astimezone(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')

news = json.load(open('mining_news.json', encoding='utf-8'))['news']
ph = json.load(open('price_history_detail.json', encoding='utf-8'))['series']
lme = json.load(open('lme_data.json', encoding='utf-8'))['metals']

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
        '亏损', '事故', '灾害', '违规', '处罚', '暂停', '扰动', '瓶颈', '压力', '延期', '搁置', '跳水', '重挫']


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

# ---------- 3. alerts.json ----------
DOM = [('cum', '沪铜', 'SHFE 主连'), ('alm', '沪铝', 'SHFE 主连'), ('pbm', '沪铅', 'SHFE 主连'),
       ('znm', '沪锌', 'SHFE 主连'), ('snm', '沪锡', 'SHFE 主连'), ('nim', '沪镍', 'SHFE 主连'),
       ('au9999', '上海金', '上金所 Au99.99'), ('agtd', '白银', '上金所 Ag(T+D)'),
       ('lcm', '碳酸锂', 'GFEX 主连')]
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


def fmt_bullet(n, max_len=0):
    """简报单条（2026-09-11 用户要求「总结全」）：默认使用完整摘要，不再按 80 字截断。

    历史上 max_len=80 会把 36 条里的 35 条切在句子中间（如「HVLP4 代铜箔实…」），
    读者看到的是半句话。改为整条呈现：max_len=0 不截断；若显式传 max_len>0，
    只按句末标点（。！？）截到该长度内，绝不在句中硬切。
    """
    body = (n.get('summary') or n.get('title') or '').strip()
    if not body:
        return ''
    # 简报是中文摘要，行尾「（原题：英文标题）」对读者是噪音；英文原题在新闻卡片上已保留。
    _i = body.find('（原题：')
    if _i > 0:
        body = body[:_i].rstrip()
    if max_len and len(body) > max_len:
        cut = body[:max_len]
        pos = max(cut.rfind('。'), cut.rfind('！'), cut.rfind('？'))
        if pos >= 40:
            body = cut[:pos + 1]
    s = n.get('source', '').strip()
    return '- %s%s' % (body, '（%s）' % s if s else '')


LOW_VALUE_NOTICE = [
    '公告参加', '参加中信', '业绩说明会', '业绩发布会', '中期业绩联合发布会', '投资者关系',
    '互动易', '接待调研', '机构调研', '持续督导', '核查意见', '法律意见书',
    '股东大会', '董事会决议', '监事会', '独立董事', '换届', '薪酬',
    '股票交易异常波动', '停牌', '复牌', '权益变动', '减持', '增持',
    '问询函', '关注函', '监管函', '更正公告', '补充公告', '关于召开', '拟变更',
]


def is_low_value_notice(n):
    t = text(n)
    return any(w in t for w in LOW_VALUE_NOTICE)


def recent_items(category, limit=0, drop_notice=False):
    """取该类目当日新增条目（2026-09-12 起默认全量）。

    limit=0（默认）= 不截断条数。历史上 limit=4 会让「行业动态」9 条只出 4 条、
    「找矿」6 条只出 4 条，读者看到的简报是残缺的。前端 setupBriefClamp() 已有
    420px 折叠 +「展开全部（N 条）」兜底，放全不会把价格区顶到屏幕外，故不再限条数。
    需要限量时显式传 limit>0。
    category 可传单个类目名，也可传列表（多类目并按传入顺序拼接）。
    """
    cats = list(category) if isinstance(category, (list, tuple)) else [category]
    arr = [n for n in news if n.get('category') in cats and n.get('is_new')]
    if drop_notice:
        arr = [n for n in arr if not is_low_value_notice(n)]
    arr.sort(key=lambda x: x.get('orig_date_full', ''), reverse=True)
    return arr[:limit] if limit else arr


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
_price_comment = ('- 星期四 盘前国内尚未开盘，最新为 09-23 日收盘：白银 +1.35%、沪镍 +0.58% 领涨；碳酸锂 -4.09%、沪铜 -0.89% 走弱。LME 六金属（行情末点与价格卡同源，均为 09-22 日收盘）：LME 镍 +1.10%、LME 铜 +0.81% 领涨，LME 锌 -0.36%、LME 铅 -0.16% 下跌。驱动上，国内基本金属普跌、仅沪镍逆势上涨 0.97%，沪铅跌 0.61%、沪锌跌 0.64%、氧化铝主连跌 1.21%，碳酸锂主连在库存去化背景下仍跌 3.2%；外盘基本金属全线飘绿，伦锌跌 1.24% 领跌、伦铜跌 0.85%。钨市延续弱势，黑钨精矿（≥65%）均价跌破 40 万元/标吨至 398500 元/标吨，较 8 月 26 日累计下跌 4.78%。贵金属分化，COMEX 黄金跌 0.14%、白银涨 0.27%。')
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


def to_items(arr):
    """news 条目 → 结构化 bullet [{t,u,s}]；正文为空则丢弃。

    t = 完整摘要（不截断，剥掉行尾「（原题：…）」英文题），u = 原文链接（= 页面卡片 data-url）。
    """
    out = []
    for n in arr:
        body = (n.get('summary') or n.get('title') or '').strip()
        _i = body.find('（原题：')
        if _i > 0:
            body = body[:_i].rstrip()
        if body:
            out.append({'t': body, 'u': n.get('url', ''), 's': (n.get('source') or '').strip()})
    return out


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
BRIEF_MAX = 80

# 例行条目关键词：命中即视为低信息量，禁止进简报。与 §3 的低价值公告一脉相承。
ROUTINE_NOTICE = [
    '装车发运', '出厂检验', '启运', '工商登记变更', '工商变更', '完成工商',
    '业绩说明会', '投资者关系', '机构调研', '持续督导', '核查意见', '法律意见书',
    '股东大会', '董事会决议', '监事会', '异常波动', '问询函', '关注函',
    '更正公告', '补充公告', '权益变动', '减持', '增持',
]


def digest_summary(body, max_len=BRIEF_MAX):
    """长摘要 → ≤max_len 的关键句：整句优先，单句超长退到逗号/分号，绝不在句中硬切。"""
    body = (body or '').strip()
    _i = body.find('（原题：')
    if _i > 0:
        body = body[:_i].rstrip()
    if len(body) <= max_len:
        return body
    out = ''
    for seg in re.split(r'(?<=[。！？])', body):
        if len(out) + len(seg) > max_len:
            break
        out += seg
    if out:
        return out
    cut = body[:max_len]
    pos = max(cut.rfind('，'), cut.rfind('；'), cut.rfind('、'))
    return cut[:pos + 1] if pos >= 20 else cut


# 简报条目：逐条撰写的精炼句（≤BRIEF_MAX 字，只留 主体 + 动作 + 关键数字）。
#   cat = 所属分节；t = 精炼句；k = 用于在当日条目标题里匹配 url 的关键词（空 = 无链接）。
BRIEF_DIGEST = [
    {'cat': '行情', 'k': '',
     't': 'LME 镍 +1.10%、铜 +0.81%、锡 +0.58% 上涨，锌 -0.36%、铅 -0.16%、铝 -0.12% 微跌（09-22 收盘）。'},
    {'cat': '行情', 'k': '',
     't': '国内 09-24 收盘：白银 +1.35%、沪镍 +0.58%、上海金 +0.40% 领涨，碳酸锂 -4.09%、沪铜 -0.89%、沪铅 -0.58% 走弱。'},
    {'cat': '政策与产业', 'k': '四种关键金属',
     't': '美国国防部招标铟、锰、镁、钛四种关键金属，覆盖采矿、选冶到回收全产业链。'},
    {'cat': '政策与产业', 'k': '挪威施压',
     't': '欧盟坚持反对北极新油气钻探，称不购买其油气，新北极政策 10 月 20 日公布。'},
    {'cat': '政策与产业', 'k': '移出国家级绿色矿山',
     't': '自然资源部将彭泽县丰岭矿区建筑石料用灰岩矿移出国家级绿色矿山名录。'},
    {'cat': '政策与产业', 'k': '澳大利亚黄金产量',
     't': '2025/26 财年澳大利亚黄金产量 303 吨，较上一财年增长 4 吨。'},
    {'cat': '政策与产业', 'k': 'METLEN',
     't': 'METLEN 投资 2500 万欧元升级希腊再生铝产线，可处理更复杂废料流。'},
    {'cat': '勘查与技术', 'k': '斯特金福尔斯',
     't': '沃尔塔金属斯特金福尔斯稀土矿见矿 214.5 米、TREO 品位 0.80%，含 7.37% 高品位段。'},
    {'cat': '勘查与技术', 'k': 'Meridian',
     't': 'Meridian 完成巴西 Cabaçal 铜金项目 DFS：矿山寿命 13.9 年、初始资本开支 3.22 亿美元。'},
    {'cat': '勘查与技术', 'k': '驰宏锌锗',
     't': '驰宏锌锗保有铅锌资源量超 3200 万吨，未来 3~5 年力争增长。'},
    {'cat': '并购与投资', 'k': 'Capstone',
     't': 'Capstone 以最高 3.85 亿美元向 Luca Mining 出售墨西哥 Cozamin 铜矿。'},
    {'cat': '并购与投资', 'k': 'Lohum',
     't': '印度 Lohum 拟收购印尼、菲律宾镍矿，目标镍年产能由 1000 吨提至 10000 吨。'},
    {'cat': '并购与投资', 'k': '鲁北化工',
     't': '鲁北化工拟约 2.09 亿元增资源海科技，保障 20 万吨联产法钛白粉项目投产。'},
    {'cat': '并购与投资', 'k': 'Highlander',
     't': 'Highlander 为秘鲁 Corani 银矿项目安排 3.3 亿美元债务融资。'},
    {'cat': '矿权市场', 'k': 'Blue Moon',
     't': '矿业权市场窗口内新增 14 宗：新疆和静南铜多金属矿探矿权转让、内蒙二道河锌矿深部勘查协议出让等。'},
]
# 分节顺序（与 §2 桶序 / generate_YYYYMMDD.py 的 THEME_BUCKET 一致）

SEC_NAMES = ['行情', '政策与产业', '勘查与技术', '并购与投资', '矿权市场']

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
