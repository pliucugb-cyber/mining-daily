# -*- coding: utf-8 -*-
"""B' 生成编排（cron 内的"生成"步骤，不负责部署）。

串联：取候选 -> 生成(LLM) -> judge/repair -> 落盘 site_news -> 渲染整站(generate_site.py) -> 数字守门。
部署由外部 cron 在 export_news_json / build_static 之后统一调 deploy_pages.py，
因为 news-data.js 必须等 index.html 生成后才能由 export_news_json 反解写出。

mock 模式：读快照、不调真实 LLM、不写 index.html、不部署，仅验证模块串联与校验生效
           （本地"搭通待激活"用，零成本、不依赖网络/key）。
激活模式：填 DEEPSEEK_API_KEY + 真实候选池（fetch_news 产出），走完整链路写到 index.html。
"""
import sys
import os
import json
import subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bprime import config, llm, generate, judge
from verify_numbers import load_source_map, verify_new_items

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def _run(cmd, env=None):
    """跑子进程，日志直出（cron 场景便于排查），非零退出即抛错。"""
    print('[run] %s' % ' '.join(cmd))
    p = subprocess.run(cmd, cwd=ROOT, env=env)
    if p.returncode != 0:
        raise RuntimeError('命令失败(rc=%d): %s' % (p.returncode, ' '.join(cmd)))


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

    # 落盘 site_news（仅非 dropped；dropped 不进站点）
    site_items = [(m, s) for (m, s, g) in graded if g != 'dropped']
    news_json = generate.dump_site_news(site_items, report)
    print('[pipeline] 进入站点渲染 %d 条（dropped=%d）'
          % (len(site_items), stats['dropped']))

    if mock:
        print('[pipeline] MOCK：跳过 generate_site + 校验（激活后真跑）')
        print('[pipeline] 完成。分级 auto=%d review=%d dropped=%d'
              % (stats['auto'], stats['review'], stats['dropped']))
        return graded, stats

    # 真实渲染整站（generate_site.py 读 index.html 模板并覆盖写回）
    env = os.environ.copy()
    if strict:
        env['VERIFY_NUMBERS_STRICT'] = '1'
    _run([sys.executable, os.path.join(ROOT, 'generate_site.py'),
          '--date', report, '--news-json', news_json], env=env)

    # 数字落地最终守门（strict 时未落地抛异常，由调用方决定是否阻断部署）
    try:
        verify_new_items(site_items, report, strict=strict, src_map_override=src_map)
    except AssertionError as e:
        print('[pipeline] ⚠️ 数字守门未通过：%s' % e)
        if strict:
            print('[pipeline] strict 模式：中止（不部署）。请人工核对后重跑或放宽 strict')
            return graded, stats

    print('[pipeline] 完成。分级 auto=%d review=%d dropped=%d'
          % (stats['auto'], stats['review'], stats['dropped']))
    return graded, stats


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='B\' 生成编排（不含部署）')
    ap.add_argument('--report')
    ap.add_argument('--mock', action='store_true', help='离线模式：读快照、不写 index.html')
    ap.add_argument('--strict', action='store_true', help='数字未落地即中止')
    a = ap.parse_args()
    run(report=a.report, mock=a.mock, strict=a.strict)
