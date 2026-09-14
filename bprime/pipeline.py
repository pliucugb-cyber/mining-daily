# -*- coding: utf-8 -*-
"""B' 全流程编排（cron 入口）。

串联：取候选 -> 生成 -> judge/repair -> 数字守门 -> 渲染 -> 部署。

mock 模式：读快照、不碰真实 index.html、不部署，仅验证模块串联与校验生效
           （本地"搭通待激活"用，零成本、不依赖网络/key）。
激活模式：填 DEEPSEEK_API_KEY + 真实候选池（fetch_news 产出），走完整链路推 gh-pages。
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bprime import config, llm, generate, judge
from verify_numbers import load_source_map, verify_new_items


def _load_candidates(report, mock, data_dir='data'):
    if mock:
        snap = os.path.join(data_dir, 'snapshots', 'candidates_sample.json')
        if os.path.exists(snap):
            return json.load(open(snap, encoding='utf-8'))
        return []
    cand = os.path.join(data_dir, 'news_candidates_%s.json' % report)
    if os.path.exists(cand):
        d = json.load(open(cand, encoding='utf-8'))
        return d.get('items') or d.get('news') or (d if isinstance(d, list) else [])
    return []


def run(report=None, mock=False, strict=None):
    report = report or config.report_today()
    strict = config.STRICT if strict is None else strict
    print('=== B\' pipeline report=%s mock=%s strict=%s ===' % (report, mock, strict))
    llm_client = llm.LLM(mock=mock)
    candidates = _load_candidates(report, mock)
    if not candidates:
        print('[pipeline] 无候选，结束')
        return None

    items = generate.generate_summaries(candidates, llm_client, report)

    # 补基准：候选自身 content/summary 优先（mock 快照带 content，校验更强）
    src_map = load_source_map(report)
    for meta, _ in items:
        u = meta.get('url')
        if u and u not in src_map:
            c = next((x for x in candidates if x.get('url') == u), None)
            if c:
                src_map[u] = c.get('content') or c.get('summary') or ''

    graded, stats = judge.judge_repair(items, llm_client, src_map, report)

    # 渲染预览（复用 generate_common 真实渲染原语；mock 不碰 index.html）
    import generate_common
    seq = []
    for meta, summary, grade in graded:
        if grade == 'dropped':
            continue
        it = generate_common.ni(meta.get('url', ''), meta.get('source', ''),
                                meta.get('date', report), meta.get('title', ''), summary,
                                embed='ok', orig_title=meta.get('orig_title', ''))
        seq.append((meta.get('category', '行业动态'), it))
    html = generate_common.render_cat_groups(seq, mark_new=True)
    preview = os.path.join('data', 'bprime_preview_%s.html' % report)
    open(preview, 'w', encoding='utf-8').write('<html><body>%s</body></html>' % html)
    print('[render] 预览 %s（%d 条，dropped 已排除）' % (preview, len(seq)))

    # 数字落地最终守门（复用 verify_new_items；strict 时未落地抛异常）
    try:
        verify_new_items(seq, report, strict=strict, src_map_override=src_map)
    except AssertionError as e:
        print('[pipeline] ⚠️ 数字守门未通过：%s' % e)
        if strict:
            print('[pipeline] strict 模式：中止（不部署）')
            return graded, stats

    # 部署
    if mock:
        print('[deploy] MOCK 模式：跳过 deploy_pages.py（激活后真推 gh-pages）')
    else:
        print('[deploy] 调用 deploy_pages.py ...')  # 激活时：os.system('python deploy_pages.py')

    print('[pipeline] 完成。分级 auto=%d review=%d dropped=%d'
          % (stats['auto'], stats['review'], stats['dropped']))
    return graded, stats


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='B\' 无人化日报 pipeline')
    ap.add_argument('--report')
    ap.add_argument('--mock', action='store_true', help='离线模式：读快照、不部署')
    ap.add_argument('--strict', action='store_true', help='数字未落地即中止')
    a = ap.parse_args()
    run(report=a.report, mock=a.mock, strict=a.strict)
