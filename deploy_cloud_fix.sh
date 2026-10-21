#!/bin/bash
# deploy_cloud_fix.sh —— 云服务器一次性修复（2026-10-21）
#
# 用途
# ----
# 修「云端代码冻结在 10-16」导致 metal/geoglobal 连续 0 条的问题。
# 根因：服务器 cron 跑的脚本缺 `git fetch origin main && git reset --hard origin/main`。
#
# 本脚本做四件事（幂等，可重复执行）：
#   1. 备份（cron + 旧脚本）
#   2. 拉最新 main 到 /opt/md-src（**这一步就修好了 metal 308**）
#   3. 安装新版 shadow_run.sh（含 git 同步）+ shadow_diff.py v5
#   4. 把 crontab 改为调用 shadow_run.sh（以后每天自动同步代码）
#
# 用法（在服务器上，root 身份）
# ----
#   cd /opt/md-src && git fetch origin main && git reset --hard origin/main
#   git show origin/main:deploy_cloud_fix.sh > /tmp/deploy_cloud_fix.sh
#   bash /tmp/deploy_cloud_fix.sh
#
# 回滚
# ----
#   脚本会打印备份路径，按提示 crontab <备份文件> 即可。
set -u

REPO=/opt/md-src
TS=$(date +%Y%m%d-%H%M%S)
BAK_DIR=/root/cloud_fix_backup_$TS

echo "=============================================="
echo " 云端修复部署  $TS"
echo "=============================================="

# ---------- 0. 权限检查 ----------
if [ "$(id -u)" != "0" ]; then
  echo "[ERR] 需要 root 权限。请先执行：sudo -i"
  exit 1
fi
echo "[OK] root 身份"

cd "$REPO" || { echo "[ERR] 找不到 $REPO"; exit 1; }

# ---------- 1. 备份 ----------
mkdir -p "$BAK_DIR"
crontab -l > "$BAK_DIR/crontab.txt" 2>/dev/null || true
[ -f "$REPO/shadow_run.sh" ] && cp "$REPO/shadow_run.sh" "$BAK_DIR/shadow_run.sh"
[ -f "$REPO/shadow_diff.py" ] && cp "$REPO/shadow_diff.py" "$BAK_DIR/shadow_diff.py"
[ -f "$REPO/fix_cron.py" ] && cp "$REPO/fix_cron.py" "$BAK_DIR/fix_cron.py"
echo "[OK] 备份到 $BAK_DIR"
echo "     回滚：crontab $BAK_DIR/crontab.txt && cp $BAK_DIR/shadow_run.sh $REPO/"

# ---------- 2. 拉最新代码（关键修复本体）----------
echo ""
echo "--- 拉取最新 main ---"
if git fetch -q origin main && git reset --hard -q origin/main; then
  echo "[OK] 代码已同步：$(git log -1 --format='%h %ci %s')"
else
  echo "[ERR] git fetch/reset 失败，请检查服务器到 GitHub 的网络与 deploy key 权限"
  exit 1
fi

# 验证 metal 修复是否在位
echo ""
echo "--- 验证 metal 源配置 ---"
if grep -A3 '"metal"' fetch_news.py | grep -q 'list_url.*https://news.metal.com/"'; then
  echo "[OK] metal 已是根路径（308 修复在位）"
else
  echo "[WARN] metal 配置未见根路径，请人工核对："
  grep -A5 '"metal"' fetch_news.py | head -8
fi
echo "     Python 版本：$(python3 --version 2>&1)"

# ---------- 3. 安装脚本 ----------
echo ""
echo "--- 安装脚本 ---"
for f in shadow_run.sh shadow_diff.py fix_cron.py; do
  if git show "origin/main:$f" > "/tmp/_dl_$f" 2>/dev/null && [ -s "/tmp/_dl_$f" ]; then
    install -m 755 "/tmp/_dl_$f" "$REPO/$f"
    echo "[OK] 已安装 $f ($(wc -l < "$REPO/$f") 行)"
  else
    echo "[WARN] 取不到 $f，跳过（可能该文件不在 main 上）"
  fi
done

# 语法自检
bash -n "$REPO/shadow_run.sh" 2>/dev/null && echo "[OK] shadow_run.sh 语法通过" || echo "[ERR] shadow_run.sh 语法错误！"
python3 -m py_compile "$REPO/shadow_diff.py" 2>/dev/null && echo "[OK] shadow_diff.py 编译通过" || echo "[ERR] shadow_diff.py 编译失败！"
python3 -m py_compile "$REPO/fix_cron.py" 2>/dev/null && echo "[OK] fix_cron.py 编译通过" || echo "[ERR] fix_cron.py 编译失败！"

# ---------- 4. 改 crontab ----------
echo ""
echo "--- 更新 crontab ---"
python3 "$REPO/fix_cron.py" --apply
CRON_RC=$?

echo ""
echo "=============================================="
if [ $CRON_RC -eq 0 ]; then
  echo " 部署完成 ✅"
else
  echo " 部署部分完成 ⚠️（crontab 未改成功，请看上方提示）"
fi
echo "=============================================="
echo ""
echo "接下来手动跑一轮，立刻验证 metal 是否恢复："
echo ""
echo "    cd $REPO"
echo "    D=\$(date +%Y-%m-%d)"
echo "    set -a; . ~/.mining-daily.env; set +a"
echo "    python3 fetch_news.py --fetch-detail --report-date \"\$D\""
echo ""
echo "然后查 metal："
echo ""
echo "    python3 -c \"import json;d=json.load(open('data/fetch_health_'\$D'.json'));"
echo "    [print(s['key'],s['count'],s.get('fetch_status','')) for s in d['sources']"
echo "    if s['key'] in ('metal','geoglobal','cjys','mining')]\""
echo ""
echo "判据：metal count > 0 且 fetch_status 含 ok → 修好了。"
echo "备份位置：$BAK_DIR"
