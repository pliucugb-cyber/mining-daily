# -*- coding: utf-8 -*-
"""B' 质量调优脚本（2026-09-14 新增）

目的：用真实候选池 + 真实 DeepSeek，实测三件事，据此定 judge 阈值、识别系统性问题：
  ① 摘要质量（长度/可读性/重点）
  ② verify_numbers「强基准」（抓正文）下的数字落地初检通过率
  ③ judge/repair 闭环的真实挽救率与丢弃率

用法：
  python qa_tuning.py --days 2026-09-12,2026-09-13,2026-09-14 --per-day 12
输出：
  tmp/tuning_<today>.json        原始逐条结果
  tmp/tuning_report_<today>.md   汇总报告
（tmp/ 已被 .gitignore 忽略，不污染仓库）
"""
import sys
import os
import json
import re
import argparse
import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(ROOT, 'tmp')

from bprime import llm
from bprime.generate import _prompt_for
from bprime.judge import judge_repair
import verify_numbers
import fetch_news

# 营销/会议/例行类：调优样本剔除，聚焦有实质信息的新闻
NOISE = ['年会', '论坛', '峰会', '研讨会', '发布会', '邀请函', '预告', '直播',
         '圆满', '落幕', '招商', '培训', '招募', '报名', '会议通知']


def load_pool(day):
    p = os.path.join(DATA, 'news_candidates_%s.json' % day)
    if not os.path.exists(p):
        return []
    d = json.load(open(p, encoding='utf-8'))
    return d.get('news') or d.get('items') or (d if isinstance(d, list) else [])


def is_noise(t):
    return any(w in (t or '') for w in NOISE)


def fetch_full_text(url, limit=3000):
    """抓正文全文（不优先 meta description）——供强基准数字校验使用。
    实测 SMM 等 SSR 站正文在 HTML 里（clean 后 5k-10k 字），meta 仅 ~190 字；
    只取 meta 会让摘要数字大量"假未落地"（2026-09-14 实测）。"""
    h = fetch_news.http_get(url, timeout=20, retries=1)
    if not h or h.startswith('__ERR__'):
        return ''
    # PDF/二进制源（szse/cninfo 公告 PDF）拿不到文本基准 -> 返回空（归 review，避免误判为「抄错数字」）
    if '%PDF' in h[:2048] or h.count('\x00') > 50:
        return ''
    h = re.sub(r'(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>', ' ', h)
    return fetch_news.clean_text(h)[:limit]


def pick(items, per_day):
    """分层抽样：按来源轮转取（每源内含数字优先），避免样本被单一来源（如境外 SMM）垄断。"""
    from collections import defaultdict
    by_src = defaultdict(list)
    for e in items:
        if is_noise(e.get('title', '')):
            continue
        by_src[e.get('source') or '?'].append(e)
    for k in by_src:
        by_src[k].sort(key=lambda e: (not bool(re.search(r'\d', e.get('title', ''))),))
    srcs = sorted(by_src.keys(), key=lambda k: -len(by_src[k]))
    picked = []
    while len(picked) < per_day:
        progressed = False
        for k in srcs:
            if by_src[k]:
                picked.append(by_src[k].pop(0))
                progressed = True
                if len(picked) >= per_day:
                    break
        if not progressed:
            break
    return picked


def _resolve_days(args):
    """--days 显式优先；不传则用 --last N 自动取「今天往前 N 天」（含今天）——供每周自检 cron 使用。"""
    if args.days:
        return [d.strip() for d in args.days.split(',') if d.strip()]
    n = max(1, int(args.last or 1))
    t = datetime.date.today()
    return [(t - datetime.timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _append_history(path, summary):
    """把本次核心指标追加进趋势账本（跨周累积），返回最近记录列表（旧->新）。"""
    hist = []
    try:
        if path and os.path.exists(path):
            hist = json.load(open(path, encoding='utf-8'))
            if not isinstance(hist, list):
                hist = []
    except Exception as ex:
        print('[tuning] 读趋势账本失败（将重建）: %s' % ex, file=sys.stderr)
        hist = []
    keep = ('date', 'days', 'total', 'foreign', 'with_source', 'no_source',
            'initial_pass', 'initial_fail', 'initial_pass_rate',
            'auto', 'review', 'dropped', 'repaired_to_auto', 'avg_summary_len')
    hist.append({k: summary.get(k) for k in keep})
    hist = hist[-60:]
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        json.dump(hist, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    except Exception as ex:
        print('[tuning] 写趋势账本失败: %s' % ex, file=sys.stderr)
    return hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', default=None, help='逗号分隔日期；不传则按 --last 自动推算')
    ap.add_argument('--last', type=int, default=3, help='自动取最近 N 天（含今天）')
    ap.add_argument('--per-day', type=int, default=12)
    ap.add_argument('--limit', type=int, default=3000, help='抓正文的最大字符数')
    ap.add_argument('--history-file', default=os.path.join(DATA, 'qa_tuning_history.json'),
                    help='质量趋势账本路径；传空串则不写')
    args = ap.parse_args()
    days = _resolve_days(args)
    today = datetime.date.today().isoformat()
    os.makedirs(OUT, exist_ok=True)

    client = llm.LLM()
    rows = []
    day_stats = {}
    seen_urls = set()
    for day in days:
        # 跨天去重：同一条新闻可能在多天候选池重复出现，避免重复样本
        picked = [e for e in pick(load_pool(day), args.per_day * 2)
                  if e.get('url') not in seen_urls][:args.per_day]
        for e in picked:
            seen_urls.add(e.get('url'))
        print('[tuning] %s 选样 %d 条' % (day, len(picked)), flush=True)
        items = []
        info = {}
        for i, e in enumerate(picked, 1):
            url = e.get('url', '')
            content = ''
            if url:
                try:
                    content = fetch_full_text(url, limit=args.limit) or ''
                except Exception as ex:
                    print('   [warn] 抓正文失败 %s: %s' % (url, ex), flush=True)
            src = content or e.get('summary') or ''
            # 注意：候选池 foreign 是字符串 'True'/'False'，须显式转 bool 再喂 prompt
            pmeta = {'title': e.get('title', ''), 'source': e.get('source', ''),
                     'foreign': str(e.get('foreign')) == 'True'}
            try:
                ds = client.chat(_prompt_for(pmeta, src))
            except Exception as ex:
                print('   [warn] 生成失败 %s: %s' % (url, ex), flush=True)
                ds = ''
            meta = {'url': url, 'title': e.get('title', ''), 'source': e.get('source', ''),
                    'foreign': str(e.get('foreign')) == 'True', 'category': e.get('category', '')}
            items.append((meta, ds))
            info[url] = {'day': day, 'wb_summary': e.get('summary', ''), 'content_len': len(content),
                         'content': content}
            print('   %d/%d len(ds)=%d len(content)=%d | %s'
                  % (i, len(picked), len(ds), len(content), url[:60]), flush=True)

        src_map = {u: v['content'] for u, v in info.items() if v['content']}
        # 初检（未修复）miss
        for meta, ds in items:
            s = src_map.get(meta['url'], '')
            info[meta['url']]['initial_miss'] = (
                [m[0] for m in verify_numbers.verify_summary(ds, s)] if s else None)
        graded, stats = judge_repair(items, client, src_map, day)
        # repair 是否真的动过（最终文本 != 初版）
        first_by_url = {m['url']: ds for m, ds in items}
        for meta, summary, grade in graded:
            u = meta['url']
            info[u]['final_differs'] = (summary != first_by_url.get(u))
            rows.append({
                'day': day, 'url': u, 'title': meta['title'], 'source': meta['source'],
                'foreign': meta['foreign'], 'content_len': info[u]['content_len'],
                'wb_summary': info[u]['wb_summary'], 'ds_summary': summary,
                'ds_len': len(summary), 'initial_miss': info[u]['initial_miss'],
                'final_differs': info[u]['final_differs'], 'grade': grade,
            })
        day_stats[day] = stats
        print('[tuning] %s 分级: %s' % (day, stats), flush=True)

    # ---- 汇总 ----
    total = len(rows)
    with_src = [r for r in rows if r['initial_miss'] is not None]
    auto = [r for r in rows if r['grade'] == 'auto']
    review = [r for r in rows if r['grade'] == 'review']
    dropped = [r for r in rows if r['grade'] == 'dropped']
    init_ok = [r for r in with_src if r['initial_miss'] == []]
    init_bad = [r for r in with_src if r['initial_miss']]
    repaired = [r for r in auto if r['final_differs']]
    avg_len = round(sum(r['ds_len'] for r in rows) / total, 1) if total else 0
    foreign_n = sum(1 for r in rows if r['foreign'])

    summary = {
        'date': today, 'days': days, 'total': total, 'foreign': foreign_n,
        'with_source': len(with_src), 'no_source': total - len(with_src),
        'initial_pass': len(init_ok), 'initial_fail': len(init_bad),
        'initial_pass_rate': round(100.0 * len(init_ok) / len(with_src), 1) if with_src else 0,
        'auto': len(auto), 'review': len(review), 'dropped': len(dropped),
        'repaired_to_auto': len(repaired), 'avg_summary_len': avg_len,
        'day_stats': day_stats,
    }

    json_path = os.path.join(OUT, 'tuning_%s.json' % today)
    json.dump({'summary': summary, 'rows': rows}, open(json_path, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)

    # 趋势账本（跨周累积；每周自检据此判断质量是否漂移）
    trend = _append_history(args.history_file, summary) if args.history_file else []
    md = build_report(summary, rows, trend)
    md_path = os.path.join(OUT, 'tuning_report_%s.md' % today)
    open(md_path, 'w', encoding='utf-8').write(md)

    print('\n===== 汇总 =====')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('\n已写:\n  %s\n  %s' % (json_path, md_path))
    return 0


def build_report(s, rows, trend=None):
    L = []
    L.append('# B\' 质量调优报告（%s）' % s['date'])
    L.append('')
    L.append('样本：%s，每天选 %d 条 → 共 **%d 条**（含境外 %d 条）。'
             % ('、'.join(s['days']), s['total'] // max(1, len(s['days'])), s['total'], s['foreign']))
    L.append('')
    L.append('## 一、总体指标')
    L.append('')
    L.append('| 指标 | 值 | 说明 |')
    L.append('|---|---|---|')
    L.append('| 抓正文成功 | %d / %d | 强基准（正文）覆盖 |' % (s['with_source'], s['total']))
    L.append('| 数字落地初检通过率 | **%s%%** | 未修复即通过（%d/%d） |'
             % (s['initial_pass_rate'], s['initial_pass'], s['with_source']))
    L.append('| 分级 auto | %d | 可自动发布 |' % s['auto'])
    L.append('| 分级 review | %d | 无基准，需人工点一眼 |' % s['review'])
    L.append('| 分级 dropped | %d | 修复后仍数字不符，丢弃 |' % s['dropped'])
    L.append('| repair 挽救 | %d | 初检失败→修复→通过 |' % s['repaired_to_auto'])
    L.append('| 平均摘要长度 | %s 字 | — |' % s['avg_summary_len'])
    L.append('')
    L.append('## 二、按日分级')
    L.append('')
    L.append('| 日期 | auto | review | dropped |')
    L.append('|---|---|---|---|')
    for d, st in s['day_stats'].items():
        L.append('| %s | %d | %d | %d |' % (d, st['auto'], st['review'], st['dropped']))
    L.append('')
    L.append('## 三、问题样本明细（初检失败 / 丢弃）')
    L.append('')
    bad = [r for r in rows if (r['initial_miss'] or r['grade'] == 'dropped')]
    if not bad:
        L.append('（无：所有条目数字均落地或修复通过）')
    for r in bad[:60]:
        L.append('### %s' % r['title'][:80])
        L.append('- 来源：%s｜境外：%s｜正文长度：%d｜分级：**%s**'
                 % (r['source'], r['foreign'], r['content_len'], r['grade']))
        L.append('- url：%s' % r['url'])
        L.append('- 未落地数字：%s' % ('、'.join(r['initial_miss']) if r['initial_miss'] else '（无基准）'))
        L.append('- DS 摘要：%s' % (r['ds_summary'] or '（空）')[:220])
        L.append('')
    L.append('## 四、结论与 judge 阈值建议')
    L.append('')
    pr = s['initial_pass_rate']
    if pr >= 95:
        note = '初检通过率 ≥95%，DeepSeek 摘要数字准确性高，judge 阈值可维持当前（有未落地即 repair→仍失败才 dropped）。'
    elif pr >= 85:
        note = ('初检通过率 85-95%，属"偶发抄错数字"区间：repair 层是必要的（已挽救 '
                + str(s['repaired_to_auto']) + ' 条）；建议对 dropped 项保留人工复盘。')
    else:
        note = '初检通过率 <85%，说明摘要数字系统性不稳：应先加强生成 prompt（要求逐字引用原文数字），再考虑放宽/收紧 judge。'
    L.append('- %s' % note)
    L.append('- dropped 率：%s%%（%d/%d）。'
             % (round(100.0 * s['dropped'] / max(1, s['total']), 1), s['dropped'], s['total']))
    L.append('- 建议：**auto 自动发布；dropped 丢弃并留档；无基准条目归 review（早间点一眼）**。')
    L.append('')

    # 五、趋势（跨周累积；每周自检的主价值就在这一节）
    if trend:
        L.append('## 五、质量趋势（最近 %d 次自检，旧 → 新）' % len(trend))
        L.append('')
        L.append('| 日期 | 样本 | 正文基准 | 初检通过率 | auto | review | dropped | 平均长度 |')
        L.append('|---|---|---|---|---|---|---|---|')
        for h in trend[-10:]:
            L.append('| %s | %s | %s | %s%% | %s | %s | %s | %s |'
                     % (h.get('date'), h.get('total'), h.get('with_source'),
                        h.get('initial_pass_rate'), h.get('auto'), h.get('review'),
                        h.get('dropped'), h.get('avg_summary_len')))
        L.append('')
        if len(trend) >= 2:
            prev, cur = trend[-2], trend[-1]
            try:
                d = float(cur.get('initial_pass_rate') or 0) - float(prev.get('initial_pass_rate') or 0)
                if d <= -10:
                    L.append('- ⚠️ 初检通过率较上次下降 %s 个百分点：优先排查生成 prompt / 源站改版 / 校验规则。'
                             % round(d, 1))
                elif d >= 10:
                    L.append('- 初检通过率较上次上升 %s 个百分点。' % round(d, 1))
                else:
                    L.append('- 初检通过率与上次基本持平（%s 个百分点）。' % round(d, 1))
            except Exception:
                pass
            try:
                dq = float(cur.get('dropped') or 0) - float(prev.get('dropped') or 0)
                if dq >= 2:
                    L.append('- ⚠️ dropped 较上次增加 %d 条：可能有真错数，抽查明细。' % int(dq))
            except Exception:
                pass
        L.append('')
    return '\n'.join(L)


if __name__ == '__main__':
    sys.exit(main())
