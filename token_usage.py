# -*- coding: utf-8 -*-
"""
token_usage.py — 统计「本次自动化会话」消耗的 token，用于收尾汇报。

数据源：~/.workbuddy/projects/<cwd>/<sessionId>.jsonl
每行是一次 LLM 调用的事件记录，含 usage 字段：
    input_tokens / output_tokens / total_tokens / cache_read_input_tokens

用法（在自动化 shell 里）：
    python token_usage.py [--session <sid>] [--json]
    --session 省略时读环境变量 CODEBUDDY_SESSION_ID
    --json     仅打印 JSON，便于其他脚本解析

输出（默认）：
    本次消耗 token | 输入(含缓存) X | 缓存命中 Y | 输出 Z | 调用 N 次 | 合计 T

注意：
- 各次调用的 input_tokens 是「当次累计上下文」，求和 = 本次会话真实计费输入总量。
- cache_read 是命中提示缓存的部分（极便宜），单列出来便于判断缓存命中率。
- 找不到用量时打印「本次消耗 token | 未知（记录缺失）」，不报错退出。
"""
import argparse
import glob
import json
import os
import sys


def _proj_root():
    return os.path.expanduser('~/.workbuddy/projects')


def _iter_events(session_id):
    """遍历所有项目 jsonl，产出匹配 session_id 且含 usage 的事件（按事件 id 去重）。"""
    seen = set()
    base = _proj_root()
    if not os.path.isdir(base):
        return
    for path in glob.glob(os.path.join(base, '*', '*.jsonl')):
        try:
            fh = open(path, encoding='utf-8', errors='replace')
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line.startswith('{'):
                    continue
                if session_id and session_id not in line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if session_id and o.get('sessionId') != session_id:
                    continue
                eid = o.get('id')
                if eid in seen:
                    continue
                seen.add(eid)
                u = o.get('usage')
                if not isinstance(u, dict):
                    u = (o.get('message') or {}).get('usage')
                if isinstance(u, dict):
                    yield u


def summarize(session_id):
    s = {
        'input': 0, 'output': 0, 'total': 0, 'cache': 0, 'calls': 0,
    }
    for u in _iter_events(session_id):
        s['input'] += int(u.get('input_tokens', 0) or 0)
        s['output'] += int(u.get('output_tokens', 0) or 0)
        s['total'] += int(u.get('total_tokens', 0) or 0)
        s['cache'] += int(u.get('cache_read_input_tokens', 0) or 0)
        s['calls'] += 1
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--session', default=os.environ.get('CODEBUDDY_SESSION_ID', ''))
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    sid = args.session
    s = summarize(sid)

    if args.json:
        print(json.dumps({'session': sid, **s}, ensure_ascii=False))
        return

    if s['calls'] == 0:
        print('本次消耗 token | 未知（记录缺失）')
        return

    print('本次消耗 token | 输入(含缓存) {input:,} | 缓存命中 {cache:,} '
          '| 输出 {output:,} | 调用 {calls} 次 | 合计 {total:,}'.format(**s))


if __name__ == '__main__':
    main()
