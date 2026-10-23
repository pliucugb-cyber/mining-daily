#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
union_candidates.py —— 把「本机 WorkBuddy + 境内云 server/fetch + 境外 runner draft/fetch」
三份候选池按文章 id 去重合并，产出与 data/news_candidates_<日期>.json 同 schema 的
data/news_candidates_union_<日期>.json，作为日报甄选的统一原料（并集出稿）。

设计目标
--------
- 日报「今日新增」由 LLM 智能体从候选池甄选，原本只认本机候选池（05:30 抓的那份）。
  本脚本把三端抓到的不同条目并起来，智能体甄选时不再漏掉「只有云端/只有境外抓到」的条目。
- 去重键 norm(url) 优先级：
    1) ?id= / ?lic= 等 query 里的文章标识（cnmn / kyreg_tk 这类源，id 在 query 中）；
    2) URL 路径里 /(\\d{6,})[-_] 的文章 id（metal.com 等）；
    3) 兜底：去 fragment + 去 query + 去末尾斜杠后的完整 URL。
- 合并策略：同键多条 → 保留 is_new=True 优先；orig_date_full 更新优先；summary 更长优先；
  记录 _branches（哪些分支@日期贡献了这条）、_from（主来源分支）。
- 日期回退：某分支「今日」池不可得 → 依次试 前1天、前2天（与 compare_fetches 同口径），
  并在 _branches 标注实际用了哪天（智能体按 orig_date_full 过滤即可，不会把昨天的混进今天）。

用法
----
  python union_candidates.py                          # 今天
  python union_candidates.py --date 2026-10-23
  python union_candidates.py --date 2026-10-23 --no-draft    # 只并集本机 + 境内云
  python union_candidates.py --date 2026-10-23 --strict-date # 禁用日期回退（今日不可得即跳过该分支）

输出
----
  data/news_candidates_union_<日期>.json  —— {report_date, count, news}
  news 每项在原字段基础上增 _branches（list[branch@date]）、_from（str）两个非破坏性元信息字段。
  这两个字段不影响下游（候选池本就 gitignore、只作甄选原料 + verify_numbers 文本基准）。

依赖：纯标准库；取 GitHub 分支需本机 SSH 能拉取 origin（已配 id_ed25519_mining）。
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser('~').replace(os.sep, '/')  # Windows 反斜杠会被 sh 吃，强制正斜杠
SSH = ('ssh -F %s/.ssh/config '
       '-o UserKnownHostsFile=%s/.ssh/known_hosts '
       '-i %s/.ssh/id_ed25519_mining '
       '-o BatchMode=yes -o StrictHostKeyChecking=accept-new'
       % (HOME, HOME, HOME))


def repo_path(*a):
    return os.path.join(REPO, *a)


def _git_env():
    env = dict(os.environ)
    env['GIT_SSH_COMMAND'] = SSH
    return env


def norm(u):
    """去重键：先抽 query 里的 ?id=/?lic= 文章标识；再抽路径 /(\\d{6,})[-_] 的 id；
    都没有则用「去 fragment+去 query+去末尾斜杠」的完整 URL 兜底。"""
    u0 = (u or '').split('#')[0].rstrip('/')
    m = re.search(r'[?&](?:id|lic)=([A-Za-z0-9_.-]{6,})', u0)
    if m:
        return 'qid:' + m.group(1)
    m = re.search(r'/(\d{6,})[-_]', u0)
    if m:
        return 'id:' + m.group(1)
    return u0.split('?', 1)[0].rstrip('/')


def load_local(date):
    p = repo_path('data', 'news_candidates_%s.json' % date)
    if not os.path.exists(p):
        return None, '本机候选池不存在：%s' % p
    return json.load(open(p, encoding='utf-8')), None


def load_gh(date, branch_ref, strict=False):
    """取 GitHub 分支上某日期的候选池；strict=False 时回退到前 1/2 天。返回 (pool, used_date, err)。"""
    env = _git_env()
    subprocess.run(['git', 'fetch', 'origin', branch_ref],
                   cwd=REPO, capture_output=True, text=True, env=env, timeout=120)
    dates = [date] if strict else [date,
                                   (datetime.date.fromisoformat(date) - datetime.timedelta(days=1)).isoformat(),
                                   (datetime.date.fromisoformat(date) - datetime.timedelta(days=2)).isoformat()]
    for d in dates:
        o = subprocess.run(['git', 'show', 'origin/%s:data/news_candidates_%s.json' % (branch_ref, d)],
                           cwd=REPO, capture_output=True, text=True, env=env)
        if o.returncode == 0 and o.stdout.strip():
            try:
                return json.loads(o.stdout), d, None
            except Exception as e:
                return None, d, 'JSON 解析失败：%s' % e
    return None, None, 'GitHub %s 候选池读取失败（今日及前两日均无）' % branch_ref


def better(a, b):
    """a 是否比 b 更优（应保留 a）。优先级：is_new > orig_date_full 更新 > summary 更长。"""
    a_new = bool(a.get('is_new'))
    b_new = bool(b.get('is_new'))
    if a_new and not b_new:
        return True
    if b_new and not a_new:
        return False
    da = a.get('orig_date_full') or ''
    db = b.get('orig_date_full') or ''
    if da and db and da != db:
        return da > db
    return len(a.get('summary') or '') > len(b.get('summary') or '')


def merge_item(stored, incoming, tag, used):
    """把 incoming 合并进 stored（同键）。branches 累加；若 incoming 更优则替换主条目。"""
    branches = list(stored.get('_branches', []))
    bt = '%s@%s' % (tag, used)
    if bt not in branches:
        branches.append(bt)
    if better(incoming, stored):
        merged = dict(incoming)
        merged['_branches'] = branches
        merged['_from'] = tag
        return merged
    stored['_branches'] = branches
    return stored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.date.today().strftime('%Y-%m-%d'))
    ap.add_argument('--no-server', action='store_true', help='不并入境内云 server/fetch')
    ap.add_argument('--no-draft', action='store_true', help='不并入境外 runner draft/fetch')
    ap.add_argument('--strict-date', action='store_true', help='禁用日期回退（今日不可得即跳过该分支）')
    args = ap.parse_args()

    date = args.date
    pools = []  # (branch_tag, pool, used_date)

    wb, err = load_local(date)
    if wb is None:
        print('⚠️', err, '—— 本机候选池是并集根基，缺失则无法并集。先跑 fetch_news.py。')
        sys.exit(2)
    pools.append(('wb', wb, date))

    if not args.no_server:
        sv, used, err = load_gh(date, 'server/fetch', strict=args.strict_date)
        if sv is None:
            print('ℹ️  境内云 server/fetch 跳过：%s' % err)
        else:
            if used != date:
                print('ℹ️  境内云 server/fetch 今日未就绪，回退到 %s（已标注 _branches）' % used)
            pools.append(('server', sv, used))

    if not args.no_draft:
        dr, used, err = load_gh(date, 'draft/fetch', strict=args.strict_date)
        if dr is None:
            print('ℹ️  境外 runner draft/fetch 跳过：%s' % err)
        else:
            if used != date:
                print('ℹ️  境外 runner draft/fetch 今日未就绪，回退到 %s（已标注 _branches）' % used)
            pools.append(('draft', dr, used))

    merged = {}
    src_count = {}  # fetch_src -> {wb, server, draft}
    union_by_src = defaultdict(int)
    for tag, pool, used in pools:
        for it in pool.get('news', []):
            key = norm(it.get('url', ''))
            if not key:
                continue
            src = it.get('fetch_src', '?')
            sc = src_count.setdefault(src, {'wb': 0, 'server': 0, 'draft': 0})
            sc[tag] = sc.get(tag, 0) + 1
            if key in merged:
                merged[key] = merge_item(merged[key], it, tag, used)
            else:
                e = dict(it)
                e['_branches'] = ['%s@%s' % (tag, used)]
                e['_from'] = tag
                merged[key] = e
                union_by_src[src] += 1  # 真实并集条数（仅新建键时 +1）

    news = list(merged.values())
    out = {'report_date': date, 'count': len(news), 'news': news}

    out_path = repo_path('data', 'news_candidates_union_%s.json' % date)
    with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print()
    print('========== 并集候选池 %s ==========' % date)
    print('本机: %d 条' % len(wb['news']))
    for tag, pool, used in pools[1:]:
        print('  + %s(%s): %d 条%s' % (tag, used, len(pool['news']), '' if used == date else ' [回退]'))
    print('并集去重后: %d 条（较本机净增 %d）' % (len(news), len(news) - len(wb['news'])))
    print()
    print('%-14s %6s %6s %6s %6s' % ('信源', '本机', '境内云', '境外', '并集'))
    print('-' * 44)
    for src in sorted(union_by_src, key=lambda k: -union_by_src[k]):
        c = src_count[src]
        print('%-14s %6d %6d %6d %6d' % (src, c['wb'], c['server'], c['draft'], union_by_src[src]))
    print('-' * 44)
    only_cloud = sum(1 for e in news if 'wb' not in [b.split('@')[0] for b in e['_branches']])
    only_wb = sum(1 for e in news if e['_branches'] == ['wb@%s' % date])
    print('仅云端/境外独有（本机漏抓）: %d 条 | 仅本机独有: %d 条' % (only_cloud, only_wb))
    print()
    print('产出: %s' % out_path)
    print('结论：并集已覆盖三端去重后的全部条目；甄选时优先核对「仅云端/境外独有」的 %d 条。' % only_cloud)


if __name__ == '__main__':
    main()
