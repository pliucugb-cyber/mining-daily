#!/usr/bin/env bash
# snapshot.sh — 矿业日报部署前资产快照（9/4 事故后强制约定）
# 作用：把 index.html / server.py / news-data.js / lme-data.js / data/*.json / sw.js
#       复制到 tmp/snapshots/<时间戳>/ 并写 .sha256，事故时可秒级回滚
# 用法：bash snapshot.sh            # 部署前跑一次
#       bash snapshot.sh --keep=20  # 只保留最近 N 份
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TS="$(date +%Y%m%d_%H%M%S)"
SNAP="$DEPLOY_DIR/tmp/snapshots/$TS"
KEEP=10

# 解析参数
for arg in "$@"; do
  case "$arg" in
    --keep=*) KEEP="${arg#*=}" ;;
    *) echo "WARN: unknown arg '$arg'" ;;
  esac
done

mkdir -p "$SNAP"

# 关键资产清单（与 server.py 真正读/前端真正用的文件对齐）
FILES=(
  "index.html"
  "news-data.js"
  "lme-data.js"
  "server.py"
  "sw.js"
  "data/news_2026-09.json"
  "data/news_2026-08.json"
  "lme_data.json"
)

echo "=== snapshot @ $TS ==="
TOTAL=0
COPIED=0
for f in "${FILES[@]}"; do
  if [ -f "$DEPLOY_DIR/$f" ]; then
    cp "$DEPLOY_DIR/$f" "$SNAP/$(basename "$f")"
    sz=$(wc -c < "$DEPLOY_DIR/$f")
    TOTAL=$((TOTAL + sz))
    COPIED=$((COPIED + 1))
    printf "  [OK]  %-30s %8d bytes\n" "$f" "$sz"
  else
    printf "  [MISS] %-30s\n" "$f"
  fi
done

# sha256 校验
cd "$SNAP"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum * 2>/dev/null > .sha256
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 * 2>/dev/null > .sha256
elif command -v certutil >/dev/null 2>&1; then
  # Windows 原生 fallback
  : > .sha256
  for f in *; do
    [ "$f" = ".sha256" ] && continue
    h=$(certutil -hashfile "$f" SHA256 2>/dev/null | awk '/^[0-9a-f]/{print $1; exit}')
    [ -n "$h" ] && echo "$h  $f" >> .sha256
  done
fi

echo ""
echo "=== snapshot saved: tmp/snapshots/$TS ==="
echo "===  copied $COPIED files, $TOTAL bytes ==="
echo ""
echo "=== sha256 ==="
cat .sha256
echo ""

# 清理旧快照（保留最近 N 份）
cd "$DEPLOY_DIR/tmp/snapshots"
ls -dt */ 2>/dev/null | tail -n +$((KEEP + 1)) | while read d; do
  echo "prune old: $d"
  rm -rf "$d"
done
echo "=== keep last $KEEP snapshots ==="
ls -dt */ 2>/dev/null | head
