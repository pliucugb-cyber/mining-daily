#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy_pages.py —— 把矿业日报的静态站点同步到 GitHub Pages（gh-pages 分支）

背景
----
WorkBuddy 的「发布为应用」链接绑定的是**本机目录绝对路径**，换一台电脑（路径变了）
就会生成新链接，同事手里的地址失效。GitHub Pages 的地址只跟「账号 + 仓库名」有关，
与在哪台电脑发布无关，因此作为对外长期地址。

本脚本把站点必需的静态文件复制到一个独立工作副本（tmp/ghpages，其 .git 指向 gh-pages
分支），提交并推送。GitHub 侧把 Pages 的 Source 设为 gh-pages 分支后，push 即自动生效。

用法
----
    python deploy_pages.py            # 有变更才提交推送；无变更直接退出
    python deploy_pages.py --force    # 无变更也强制推一次（用于首次建站/排障）

说明
----
- 只包含前端真正用到的文件（页面、数据 js、图标、manifest、sw），
  不含 Python 脚本、data/ 抓取缓存、__pycache__ 等。
- 遵循「未编造、可溯源」：只搬运已有文件，不生成任何内容。
"""
import os
import sys
import time
import shutil
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))


def log(msg):
    """立即输出（flush=True）——自动化场景下输出常被管道缓冲，卡住时看不到进度。"""
    print(msg, flush=True)
WORK = os.path.join(ROOT, 'tmp', 'ghpages')
REMOTE = 'git@github.com:pliucugb-cyber/mining-daily.git'
BRANCH = 'gh-pages'

# 站点必需文件（缺一不可；缺失会直接报错终止，避免推一个坏站点上去）
REQUIRED = [
    'index.html',
    'news-data.js',
    'lme-data.js',
    'price-history.js',
    'sw.js',
    'manifest.json',
    'icon-192.png',
    'icon-512.png',
    'icon-192-maskable.png',
    'icon-512-maskable.png',
]

# 可选附带（供后续前端化 / 排查用，缺失不报错）
OPTIONAL = [
    'mining_news.json',
    'price_history_detail.json',
    'price_history.json',
    'lme_data.json',
    'morning_report.json',
    'alerts.json',
    'knowledge.json',
]


def run(cmd, cwd=None, check=True):
    """执行命令，返回 (returncode, stdout+stderr)"""
    # 定时任务里跑 git 时严禁任何交互式等待：否则一个 rebase/编辑器提示就能把整轮流程挂死
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GIT_EDITOR'] = 'true'
    env['GIT_SEQUENCE_EDITOR'] = 'true'
    env['GIT_MERGE_AUTOEDIT'] = 'no'
    p = subprocess.run(cmd, cwd=cwd, shell=True, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode('utf-8', errors='replace')
    if check and p.returncode != 0:
        raise RuntimeError('命令失败: %s\n%s' % (cmd, out))
    return p.returncode, out


def main():
    force = '--force' in sys.argv

    # 1) 校验必需文件齐全
    missing = [f for f in REQUIRED if not os.path.isfile(os.path.join(ROOT, f))]
    if missing:
        log('[deploy_pages] 缺少必需文件，已终止：%s' % ', '.join(missing))
        return 2

    # 2) 准备工作副本
    os.makedirs(WORK, exist_ok=True)
    if not os.path.isdir(os.path.join(WORK, '.git')):
        log('[deploy_pages] 首次初始化工作副本 %s' % WORK)
        run('git init', cwd=WORK)
        run('git checkout -b %s' % BRANCH, cwd=WORK)
        run('git config user.email "mining-daily@local"', cwd=WORK)
        run('git config user.name "mining-daily"', cwd=WORK)
        # remote 可能已存在（重复运行），先尝试新增，失败则覆盖 URL
        code, _ = run('git remote add origin %s' % REMOTE, cwd=WORK, check=False)
        if code != 0:
            run('git remote set-url origin %s' % REMOTE, cwd=WORK)
    else:
        # 确保停在正确分支
        run('git checkout %s' % BRANCH, cwd=WORK, check=False)

    # 3) 清理工作副本中"本轮不再需要"的文件（保留 .git）
    #    刻意不做"先清空再全量复制"：那样每轮都会删除十几个文件，
    #    既触发批量删除确认、也让 git 每次都认为全部文件变动。
    #    只删除确实已不在清单里的文件，日常运行删除数为 0。
    keep = set(REQUIRED + OPTIONAL + ['.nojekyll'])
    for name in os.listdir(WORK):
        if name == '.git' or name in keep:
            continue
        p = os.path.join(WORK, name)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            os.remove(p)
        log('[deploy_pages] 移出清单：%s' % name)

    # 4) 复制站点文件
    copied = []
    for f in REQUIRED + OPTIONAL:
        src = os.path.join(ROOT, f)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(WORK, f)
        shutil.copy2(src, dst)
        copied.append(f)
    log('[deploy_pages] 已复制 %d 个文件：%s' % (len(copied), ', '.join(copied)))

    # 4.5) .nojekyll —— 跳过 GitHub Pages 的 Jekyll 构建
    #   Pages 默认对站点跑 Jekyll：会忽略下划线开头的文件/目录，还可能把 {{ }} 当 Liquid 模板处理。
    #   本项目是已经构建好的纯静态文件，跳过构建更稳妥、发布也更快。
    #   注意：这个文件只放在 gh-pages 分支里，不放项目根 —— 项目根的 server.py 按安全约定
    #   会拦截以 . 开头的静态路径，放那边反而访问不到。
    nojekyll = os.path.join(WORK, '.nojekyll')
    if not os.path.exists(nojekyll):
        with open(nojekyll, 'w') as f:
            f.write('')

    # 5) 提交（工作区有变更才提交）
    run('git add -A', cwd=WORK)
    code, status = run('git status --porcelain', cwd=WORK)
    if status.strip():
        import datetime
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        run('git commit -m "站点更新 %s"' % stamp, cwd=WORK)
        log('[deploy_pages] 已生成本地提交。')
    else:
        log('[deploy_pages] 工作区与上一次提交一致。')

    # 6) 推送
    # 注意：这里**不能**因为"工作区无变更"就跳过推送。
    # 若上一轮推送失败（断网、SSH 未就绪），本地会留下一个未推送的提交；
    # 下一轮工作区恰好无变更时若直接 return，这个提交将永远推不上去，线上内容被卡住。
    # git push 本身是幂等的（无新提交时返回 Everything up-to-date），故每轮都推一次最稳妥。
    log('[deploy_pages] 推送到 %s 分支…' % BRANCH)
    code, out = run('git push -u origin %s' % BRANCH, cwd=WORK, check=False)
    if code != 0:
        log('[deploy_pages] 第 1 次推送失败，3 秒后按「本地文件为准」合并远程再推：\n%s' % out)
        time.sleep(3)
        # 关键：这里绝不能用 git pull --rebase。
        # 非交互环境下 rebase 一旦需要人工介入就会停在中间态，之后每一轮定时任务都会失败。
        # 本站内容是「从 main 复制过来」的全量快照，历史合并一律以本地文件为准（-X ours）。
        run('git fetch origin %s' % BRANCH, cwd=WORK, check=False)
        run('git merge -X ours --no-edit FETCH_HEAD', cwd=WORK, check=False)
        code, out = run('git push -u origin %s' % BRANCH, cwd=WORK, check=False)
        if code != 0:
            log('[deploy_pages] 推送仍失败：\n%s' % out)
            log('[deploy_pages] 排查：检查 ~/.ssh/config 是否正确、公钥是否已加到 GitHub、网络是否可达。')
            return 1

    log('[deploy_pages] 推送成功。')
    code, out = run('git log -1 --format="%h %s"', cwd=WORK)
    log('[deploy_pages] 线上版本：%s' % out.strip())
    log('[deploy_pages] 站点地址：https://pliucugb-cyber.github.io/mining-daily/')
    return 0


if __name__ == '__main__':
    sys.exit(main())
