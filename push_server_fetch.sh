#!/usr/bin/env bash
# push_server_fetch.sh v3 — 把当天候选池推到 GitHub server/fetch 分支
# 临时 index + commit-tree，不碰当前分支(HEAD)/工作树/真实索引，不影响 shadow-reports 推送。
# v2 修复：
#   1) 弃用手搓 mktree 条目（粘贴易坏、空行即炸）→ 改用 GIT_INDEX_FILE 标准管线；
#   2) 硬护栏：commit 为空禁止 push（空 refspec 会误删远端分支！本次事故根因）。
# v3 修复（non-fast-forward 根因）：
#   /opt/md-src 仓库的 fetch refspec 只覆盖 main/shadow-reports，
#   `git fetch origin server/fetch` 永远不会创建 refs/remotes/origin/server/fetch，
#   旧版读不到基线 → 造出无父提交 → 对远端必然 non-FF 被拒。
#   改为：显式 fetch（失败即退出，不再静默吞错），基线用 FETCH_HEAD（每次 fetch 都刷新）。
set -eu
REPO=/opt/md-src
cd "$REPO"

D="${1:-}"
if [ -z "$D" ]; then
  f=$(ls -t data/news_candidates_*.json 2>/dev/null | head -1)
  [ -n "$f" ] && D=$(echo "$f" | sed -E 's#.*news_candidates_([0-9-]+)\.json#\1#')
fi
[ -z "$D" ] && D=$(date +%Y-%m-%d)
nc="data/news_candidates_${D}.json"
[ -f "$nc" ] || { echo "[server/fetch] $nc 不存在，跳过"; exit 0; }

if ! git fetch -q origin server/fetch 2>/dev/null; then
  echo "[server/fetch] fetch origin server/fetch 失败（网络/权限），本轮跳过"
  exit 0
fi

base=""
if git rev-parse -q --verify FETCH_HEAD >/dev/null 2>&1; then
  base=FETCH_HEAD
fi

blob=$(git hash-object -w "$nc")
[ -n "$blob" ] || { echo "[server/fetch] hash-object 失败"; exit 1; }

idx=$(mktemp)
trap 'rm -f "$idx"' EXIT
GIT_INDEX_FILE="$idx" git read-tree --empty
if [ -n "$base" ]; then
  GIT_INDEX_FILE="$idx" git read-tree "$base"
fi
GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo "100644,$blob,data/news_candidates_${D}.json"
tree=$(GIT_INDEX_FILE="$idx" git write-tree)
[ -n "$tree" ] || { echo "[server/fetch] write-tree 失败"; exit 1; }

if [ -n "$base" ]; then
  commit=$(git -c user.email=server@miningdaily.local -c user.name=mining-daily-server \
           commit-tree "$tree" -p "$base" -m "server fetch $D")
else
  commit=$(git -c user.email=server@miningdaily.local -c user.name=mining-daily-server \
           commit-tree "$tree" -m "server fetch $D")
fi
[ -n "$commit" ] || { echo "[server/fetch] commit-tree 失败，禁止推送（防误删分支）"; exit 1; }

if git push origin "$commit:refs/heads/server/fetch"; then
  echo "[server/fetch] 已推送 $D (${commit:0:8})"
else
  echo "[server/fetch] 推送失败：检查 Deploy key 写权限 / 网络"
  exit 1
fi
