#!/usr/bin/env python3
# compare_fetches.py — 对比「本机 WorkBuddy 候选池」与「GitHub Actions 候选池」
#
# 背景：阶段一试运行期间，WorkBuddy(06:00) 与 GitHub Actions(06:15) 各抓一次。
#   本脚本逐源对比两份候选池，识别 GitHub 在哪些信源上漏抓
#   （尤其国内政府源，GitHub 服务器在境外，访问可能受限）。
#
# 用法：
#   python3 compare_fetches.py                  # 对比今天
#   python3 compare_fetches.py --date 2026-09-13
#   python3 compare_fetches.py --date 2026-09-13 --quiet   # 只输出告警
#
# 数据来源：
#   本机 WB 候选池： <repo>/data/news_candidates_YYYY-MM-DD.json （WorkBuddy 本地生成，gitignore）
#   GitHub 候选池：  origin/draft/fetch:data/news_candidates_YYYY-MM-DD.json （Actions 推送）
#
# 依赖：纯标准库。需本地已配置 SSH 能拉取 origin/draft/fetch。
import argparse, json, os, subprocess, sys, datetime

REPO = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser('~').replace(os.sep, '/')  # Windows 反斜杠会被 sh 吃，强制正斜杠
SSH = ('ssh -F %s/.ssh/config '
       '-o UserKnownHostsFile=%s/.ssh/known_hosts '
       '-i %s/.ssh/id_ed25519_mining '
       '-o BatchMode=yes -o StrictHostKeyChecking=accept-new'
       % (HOME, HOME, HOME))

# 视为「关键源」：若 GitHub 持续漏抓这些，基本确诊是节点可达性问题
IMPORTANT = ['mnr_news', 'mnr_policy', 'chinania', 'mining', 'miningrights']


def repo_path(*a):
    return os.path.join(REPO, *a)


def load_wb(date):
    p = repo_path('data', f'news_candidates_{date}.json')
    if not os.path.exists(p):
        return None, f'本机 WorkBuddy 候选池不存在：{p}（WorkBuddy 今天可能还没跑 / 路径不同）'
    return json.load(open(p, encoding='utf-8')), None


def load_gh(date):
    env = dict(os.environ)
    env['GIT_SSH_COMMAND'] = SSH
    subprocess.run(['git', 'fetch', 'origin', 'draft/fetch'],
                   cwd=REPO, capture_output=True, text=True, env=env, timeout=120)
    o = subprocess.run(['git', 'show', f'origin/draft/fetch:data/news_candidates_{date}.json'],
                       cwd=REPO, capture_output=True, text=True, env=env)
    if o.returncode != 0:
        return None, 'GitHub draft/fetch 候选池读取失败（今天 Actions 可能还没跑或失败了）'
    return json.loads(o.stdout), None


def agg(pool):
    out = {}
    for i in pool.get('news', []):
        k = i.get('fetch_src', '?')
        out[k] = out.get(k, 0) + 1
    return out


def sources_meta():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('fn', repo_path('fetch_news.py'))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return {c['key']: c for c in m.SOURCES}
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.date.today().strftime('%Y-%m-%d'))
    ap.add_argument('--quiet', action='store_true', help='只输出告警/结论')
    args = ap.parse_args()

    wb, err1 = load_wb(args.date)
    gh, err2 = load_gh(args.date)
    if wb is None:
        print('⚠️', err1); sys.exit(2)
    if gh is None:
        print('⚠️', err2); sys.exit(2)

    wb_s, gh_s = agg(wb), agg(gh)
    meta = sources_meta()

    if not args.quiet:
        print(f'对比日期 {args.date}')
        print(f'WorkBuddy 本机: {len(wb["news"])} 条 | GitHub draft/fetch: {len(gh["news"])} 条')
        print()
        print('%-14s %-22s %6s %6s %+6s' % ('信源', '名称', 'WB', 'GH', '差'))
        print('-' * 58)

    allk = sorted(set(wb_s) | set(gh_s), key=lambda k: -(gh_s.get(k, 0) + wb_s.get(k, 0)))
    gh_leak, wb_leak = [], []
    for k in allk:
        w, g = wb_s.get(k, 0), gh_s.get(k, 0)
        if w > 0 and g == 0:
            gh_leak.append(k)
        elif g > 0 and w == 0:
            wb_leak.append(k)
        if not args.quiet:
            name = (meta.get(k) or {}).get('name', '')[:20]
            flag = ' GitHub漏' if k in gh_leak else (' WB漏' if k in wb_leak else '')
            print('%-14s %-22s %6d %6d %+6d%s' % (k, name, w, g, g - w, flag))

    if not args.quiet:
        print('-' * 58)
        print(f'有产出源: WB={sum(1 for k in wb_s if wb_s[k] > 0)}  '
              f'GH={sum(1 for k in gh_s if gh_s[k] > 0)}')
        print()

    # 关键源告警
    important_leak = [k for k in IMPORTANT if k in gh_leak]
    if important_leak:
        print('🚨 GitHub 在以下关键源上完全漏抓：', ', '.join(important_leak))
        print('   → 疑似 GitHub 境外节点访问受限，需连续观察 3~5 天确诊后补抓。')
    else:
        print('✅ 关键源 GitHub 未漏抓。')
    if wb_leak:
        print('ℹ️  WorkBuddy 本机漏抓、GitHub 抓到的源：', ', '.join(wb_leak))
    print()
    verdict = 'GitHub 暂不能独立替代 WorkBuddy（有关键源漏抓）' if important_leak else \
              ('GitHub 与 WorkBuddy 互补（WB 有少量漏抓）' if wb_leak else 'GitHub 覆盖良好')
    print('结论：', verdict)


if __name__ == '__main__':
    main()
