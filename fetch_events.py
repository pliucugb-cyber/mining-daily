# -*- coding: utf-8 -*-
"""fetch_events.py —— 「事件跟踪」数据源生成器与建议器（2026-10-25）

为什么需要它
    「事件跟踪」把散落进每日归档、14 天后即下线的「同一件事的连续进展」聚合成可长期追踪的
    事件时间线。数据源是 data/events.json（manual 人工 + review 待审核），本脚本负责：
      ① 由 data/events.json 生成 event-data.js（window.EVENT_DATA，前端渲染用）；
      ② 可选 --suggest：扫描新闻库，把候选「时间线节点 / 全新事件」产出到 review 区，
         交由人工审核采纳，绝不静默写 manual、绝不静默上线。

三条硬规矩（与会议日程 fetch_conferences.py 同源）
      ① 人工条目优先。data/events.json 的 manual 区脚本永不覆盖、也永不删除。
      ② 生成物逗号分隔红线。render_js 条目之间必须有逗号，否则生成的 JS 语法非法
         → 前端 window.EVENT_DATA 未定义 → 卡片整块静默空白。
      ③ 关联新闻只存 URL 不嵌内容。时间线 news:[url] 仅存新闻 URL（news-data.js 是
         slim schema，没有 id 字段，URL 才是前端唯一可现查的稳定主键），渲染时现查
         window.NEWS_DATA；解析不到 → 测试报错（见 test_event_track.js）。

数据流
    data/events.json        唯一数据源（manual 人工 + review 待审核候选）
    event-data.js           生成产物（window.EVENT_DATA），勿直接改

用法
    python fetch_events.py                 # 等同 --export-only（事件当前无自动抓取源）
    python fetch_events.py --export-only   # 仅由 events.json 重新生成 event-data.js
    python fetch_events.py --suggest       # 扫描新闻库 → 向 review 区产出候选（不碰 manual）
    python fetch_events.py --suggest --dry-run  # 只算不写（测试/预览用）
"""
import datetime
import io
import json
import os
import sys
import glob

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, 'data', 'events.json')
OUT_JS = os.path.join(ROOT, 'event-data.js')

HEADER = (
    "/* event-data.js —— 【自动生成，勿直接改】\n"
    " * 数据源：data/events.json（manual 人工 + review 待审核）\n"
    " * 生成器：fetch_events.py（python fetch_events.py --export-only 可重新生成）\n"
    " * 维护：人工事件请改 data/events.json 的 manual 区，脚本永不覆盖该区。\n"
    " * 字段：id 事件标识 · title 标题 · summary 摘要 · category 类别 · status 状态\n"
    " *       priority 优先级 · started 起始日 · timeline 时间线（含 news 关联新闻 URL）\n"
    " * 关联新闻 URL 由 window.NEWS_DATA 现查；news 字段仅存稳定 URL，不嵌内容。\n * （不用 id 的原因：news-data.js 为 slim schema，无 id 字段。）\n"
    " */\n"
)

# 状态排序：active 在前（进行中/观察中），非 active 在后（已达成/已终止）
STATUS_RANK = {'进行中': 0, '观察中': 1, '已达成': 2, '已终止': 3}
PRIORITY_RANK = {'high': 0, 'normal': 1}


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with io.open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, obj):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))


def sort_events(items):
    def key(it):
        st = it.get('status', '')
        pr = it.get('priority', 'normal')
        sd = it.get('started', '') or '0000-00-00'
        return (STATUS_RANK.get(st, 9), PRIORITY_RANK.get(pr, 1), sd)
    return sorted(items, key=key)


def render_js(data):
    """生成 event-data.js（window.EVENT_DATA）。仅渲染 manual 区（review 不展示）。"""
    items = sort_events(data.get('manual', []))
    lines = []
    for it in items:
        parts = []
        for k in ('id', 'title', 'summary', 'category', 'status', 'priority', 'started'):
            v = it.get(k, '')
            if v == '' or v is None:
                continue
            parts.append("%s:'%s'" % (k, str(v).replace('\\', '\\\\').replace("'", "\\'")))
        tl = it.get('timeline')
        if tl:
            # ⚠️ 嵌套 timeline 用 json.dumps 序列化（合法 JS），不要破坏逗号红线
            parts.append('timeline:' + json.dumps(tl, ensure_ascii=False))
        lines.append('    { ' + ', '.join(parts) + ' }')
    updated = data.get('updated', '')
    body = ",\n".join(lines)          # ⚠️ 条目之间必须有逗号，否则生成的 JS 语法非法
    return (HEADER
            + "window.EVENT_DATA = {\n"
            "  updated: '%s',\n"
            "  source: '人工维护（data/events.json 的 manual 区）',\n"
            "  items: [\n%s\n  ]\n"
            "};\n" % (updated, body))


def export_only(data, dry=False):
    js = render_js(data)
    if dry:
        print('[dry] event-data.js 预览（%d 条事件）:\n' % len(data.get('manual', [])))
        print(js[:600])
        return
    with io.open(OUT_JS, 'w', encoding='utf-8', newline='\n') as f:
        f.write(js)
    print('[export] event-data.js 已生成（%d 条事件）' % len(data.get('manual', [])))


# ────────────────────────────── 自动建议（Phase 4：人工确认闸门） ──────────────────────────────
# 强信号关键词：命中且不匹配任何已有事件 → 产出全新候选事件
NEW_EVENT_SIGNALS = ['收购', '拟收购', '受让', '转让', '探矿权', '采矿权', '关税',
                     '重大资产重组', '股权合作', '增资', '并购', '合并']
NEW_EVENT_CATS = {'并购与投资', '矿权交易', '政策与法规'}


def load_news_pool():
    """合并全库新闻（与 news-data.js 同源），返回 (news_list, by_id)。"""
    pool = []
    by_id = {}
    for fn in sorted(glob.glob(os.path.join(ROOT, 'data', 'news_2026-*.json'))):
        try:
            d = json.load(open(fn, encoding='utf-8'))
        except Exception:
            continue
        for e in d.get('news', []):
            pool.append(e)
            if e.get('id'):
                by_id[e['id']] = e
    return pool, by_id


def _norm_list(lst):
    return [str(x).lower() for x in (lst or [])]


# ────────────────────────────── 自动建议（人工确认闸门） ──────────────────────────────
# 强信号关键词：命中且不匹配任何已有事件 → 产出全新候选事件
NEW_EVENT_SIGNALS = ['收购', '拟收购', '受让', '转让', '探矿权', '采矿权', '关税',
                     '重大资产重组', '股权合作', '增资', '并购', '合并']
NEW_EVENT_CATS = {'并购与投资', '矿权交易', '政策与法规'}

# 泛词表：矿业资讯里高频、不足以标识「同一件事」的词。
# ⚠️ 2026-10-25 踩坑（站审同款病因）：只凭「探矿权」就把辽宁闹沟里金铜矿转让公示
#   挂到江西安远铂矿事件上；只凭「伦铜」「COMEX」把一堆价格快讯挂到铜关税事件上；
#   新铝时代事件的关键词含泛词「收购」，一口气误挂 34 条并购新闻。
#   → 泛词只参与排序打分，**永不作为命中资格**；资格一律看「强命中数」。
GENERIC_TOKENS = {
    '探矿权', '采矿权', '矿业权', '勘查', '开采', '转让', '出让', '挂牌', '成交', '受让',
    '协议', '收购', '拟收购', '增资', '并购', '合并', '重组', '股权', '股份', '投资',
    '项目', '子公司', '关税', '条款', '伦铜', '沪铜', 'comex', 'lme', '铜价', '铝价',
    '金价', '价格', '期货', '现货', '铜', '铝', '镍', '锡', '锌', '铅', '金', '银',
    '稀土', '锂', '煤', '煤矿', '铁矿', '矿山', '矿业', '公司', '集团', '公告', '公示',
    '通知', '亿元', '万吨', '资源量', '储量', '花旗', '高盛', '渣打', '摩根', '惠誉',
    '瑞银', '德银', '美银', '预测', '展望', '目标价', '评级', '看多', '看空', '白宫',
}
QUALIFY_STRONG = 2               # 强命中数达到该值才成为候选（泛词不计）
NODE_SUGGEST_WINDOW_DAYS = 60    # 只建议事件最新节点之后 60 天内的新闻
NODE_SUGGEST_CAP = 8             # 每个事件最多建议几条，避免刷屏
NEW_EVENT_CAP = 25               # 全新候选上限
NEW_EVENT_RECENT_DAYS = 30       # 全新候选只取最近 30 天（更早的应已人工处理过）


def _norm_list(lst):
    return [str(x).lower() for x in (lst or [])]


def _parse_date(ds):
    try:
        return datetime.date.fromisoformat(str(ds or '')[:10])
    except Exception:
        return None


def _plus_days(ds, n):
    d = _parse_date(ds)
    if not d:
        return ''
    return (d + datetime.timedelta(days=n)).isoformat()


def _strong_hits(tokens, title):
    """返回 (强命中数, 总命中数)。强命中 = 非泛词命中，是候选资格的唯一依据。"""
    tl = (title or '').lower()
    strong = 0
    total = 0
    for t in set(tokens):
        t = str(t).lower().strip()
        if not t or t not in tl:
            continue
        total += 1
        if t not in GENERIC_TOKENS:
            strong += 1
    return strong, total


def load_news_pool():
    """合并全库新闻（与 news-data.js 同源），返回 (news_list, by_id)。"""
    pool = []
    by_id = {}
    for fn in sorted(glob.glob(os.path.join(ROOT, 'data', 'news_2026-*.json'))):
        try:
            d = json.load(open(fn, encoding='utf-8'))
        except Exception:
            continue
        for e in d.get('news', []):
            pool.append(e)
            if e.get('id'):
                by_id[e['id']] = e
    return pool, by_id


def suggest(data, dry=False):
    """扫描新闻库，产出 review 候选。绝不修改 manual。

    dry=True 时不落盘、不重新生成 event-data.js（供 test_event_track.js 验证精度规则用）。

    精度规则（2026-10-25 加）：候选资格只看「强命中数」（实体/关键词中非泛词的命中），
    泛词（探矿权/伦铜/收购/花旗…）只参与排序、永不给资格。窗口：事件最新节点后 60 天内。
    review 区每次全量重算（同一输入 → 同一输出）；人工采纳即移入 manual，
    下次不会再被建议（已在时间线里，按 URL 去重）。
    """
    manual = data.get('manual', [])
    pool, by_id = load_news_pool()

    node_sugg = []     # 给已有事件补时间线节点
    seen_node = set()  # (event_id, news_id)

    # ── ① 给已有事件补时间线节点（强命中资格） ──
    for ev in manual:
        eid = ev.get('id')
        tokens = _norm_list(ev.get('entities')) + _norm_list(ev.get('keywords'))
        if not tokens:
            continue
        estart = ev.get('started', '') or ''
        latest = ''
        for n in ev.get('timeline', []):
            if (n.get('date') or '') > latest:
                latest = n.get('date') or ''
        window_end = _plus_days(latest or estart, NODE_SUGGEST_WINDOW_DAYS)
        cands = []
        for e in pool:
            t = e.get('title', '') or ''
            strong, _total = _strong_hits(tokens, t)
            if strong < QUALIFY_STRONG:
                continue
            nid = e.get('id')
            u = e.get('url', '') or ''
            if not nid or not u:
                continue
            ed = e.get('orig_date_full', '') or e.get('d', '')
            if estart and ed and ed < estart:
                continue
            if window_end and ed and ed > window_end:
                continue
            # 时间线里已挂此新闻（按 URL）则跳过
            if any(u in (n.get('news') or []) for n in ev.get('timeline', [])):
                continue
            key = (eid, nid)
            if key in seen_node:
                continue
            cands.append((strong, ed, e))
        # 强命中多的在前，其次日期新的在前
        cands.sort(key=lambda x: x[1] or '', reverse=True)
        cands.sort(key=lambda x: x[0], reverse=True)
        for strong, ed, e in cands[:NODE_SUGGEST_CAP]:
            nid = e.get('id')
            seen_node.add((eid, nid))
            node_sugg.append({
                'type': 'node_suggestion',
                'event_id': eid,
                'event_title': ev.get('title', ''),
                'score': strong,
                'node': {
                    'date': ed,
                    'title': e.get('title', ''),
                    'detail': (e.get('summary', '') or '')[:120],
                    'news': [e.get('url', '')],
                    'source': e.get('source', ''),
                    'milestone': False,
                },
            })

    # ── ② 全新候选事件：命中强信号、不被任何已有事件覆盖、且是近期新闻 ──
    new_event = []
    seen_new = set()
    recent_cutoff = _plus_days(datetime.date.today().isoformat(), -NEW_EVENT_RECENT_DAYS)
    for e in pool:
        t = e.get('title', '') or ''
        tl = t.lower()
        if not any(sg in tl for sg in NEW_EVENT_SIGNALS):
            continue
        cat = e.get('category', '')
        if cat not in NEW_EVENT_CATS:
            continue
        ed = e.get('orig_date_full', '') or e.get('d', '')
        if recent_cutoff and ed and ed < recent_cutoff:
            continue
        covered = False
        for ev in manual:
            tokens = _norm_list(ev.get('entities')) + _norm_list(ev.get('keywords'))
            if _strong_hits(tokens, t)[0] >= 1:
                covered = True
                break
        if covered:
            continue
        nid = e.get('id')
        norm = t.strip().lower()
        if norm in seen_new:
            continue
        seen_new.add(norm)
        new_event.append({
            'type': 'new_event',
            'event': {
                'id': 'rv_' + (nid or t[:8]),
                'title': t,
                'summary': (e.get('summary', '') or '')[:160],
                'category': cat,
                'status': '观察中',
                'priority': 'normal',
                'entities': [],
                'keywords': [],
                'started': ed,
                'timeline': [{
                    'date': ed,
                    'title': t,
                    'detail': (e.get('summary', '') or '')[:120],
                    'news': [e.get('url', '')] if e.get('url') else [],
                    'source': e.get('source', ''),
                    'milestone': True,
                }],
            },
        })
    # 新的在前，再截断
    new_event.sort(key=lambda r: r['event'].get('started', '') or '', reverse=True)
    new_event = new_event[:NEW_EVENT_CAP]

    review = node_sugg + new_event
    data['review'] = review
    if not dry:
        save_json(DATA_FILE, data)
        export_only(data)
    print('\n[review] 产出候选 %d 条 → node_suggestion=%d, new_event=%d'
          % (len(review), len(node_sugg), len(new_event)))
    for r in node_sugg[:12]:
        print('  + 节点(%d) → %s : %s' % (r['score'], r['event_title'][:24], r['node']['title'][:40]))
    for r in new_event[:8]:
        print('  + 新事件 → %s' % r['event']['title'][:50])
    if len(new_event) > 8:
        print('  …另有 %d 条新事件候选' % (len(new_event) - 8))
    return 0


def main():
    args = sys.argv[1:]
    export_only_flag = '--export-only' in args
    suggest_flag = '--suggest' in args
    dry = '--dry-run' in args

    data = load_json(DATA_FILE, {'updated': '', 'manual': [], 'review': []})

    if suggest_flag:
        return suggest(data, dry=dry)

    # 默认（无参数）等同 --export-only
    export_only(data, dry=dry)
    return 0


if __name__ == '__main__':
    sys.exit(main())
