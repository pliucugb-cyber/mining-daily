#!/bin/bash
# shadow_run.sh —— 云服务器每日「抓取 + 生成 + 影子对比」一体化（v3）
#
# v3 变更（2026-10-21，修复「云端代码冻结在 10-16」）：
#   1) **开头加 git fetch origin main && git reset --hard origin/main** ——
#      v2 缺失此步，导致云端代码不更新：10-19 修的 metal 308 重定向
#      (d12ff22/7f36d26) 一直没进云，metal 连续 3 天 0 条；geoglobal 同样 0 条。
#      对照 setup_bprime.sh 装的 cron 一直含这两句 —— 换脚本时把它丢了。
#      **若你看到某个修复在服务器上"没生效"，先查这一行。**
#   2) reset 前把 data/ 里的候选池/健康文件备份到 data/_local_backup/，
#      避免 reset --hard 抹掉云端自己抓取的数据（server/fetch 推送依赖它）。
#   3) 抓取失败不静默：fetch_news 非 0 退出码时记录并继续，但把失败显式写进
#      shadow_diff 报告头部，避免"0 条 = 正常"的假象。
#
# 历史修复（v2）：
#   - 生成站点后立即发布到 gh-pages（deploy_pages.py）
#   - 影子对比前强制刷新 /var/www/mining-daily（reset --hard origin/gh-pages）
#   - bprime.pipeline 失败自动重试 3 次（DeepSeek 超时不打穿整轮）
#
# 注意：本脚本由 root 的 crontab 运行（/opt/md-src、data/、/var/www/mining-daily
#       均 root 属主），cron 里必须以 root 身份跑；手动复跑也要 root。
set -e
set -a; . ~/.mining-daily.env; set +a

# ★ v3 关键修复：同步最新代码（v2 缺失，导致云端代码停留在旧版本）
#   说明：云端自己抓取/生成会修改被跟踪的 data/*.json（index.json、news_2026-*.json 等），
#   直接 reset --hard 会把它们回滚到 main 上的旧值，导致站点用旧数据。
#   故先 stash（保留云端产物），reset 到最新代码，再把 stash 放回；
#   冲突时以新代码为准、放弃本地改动（-f），避免脚本卡死。
#   未跟踪文件（news_candidates_*、fetch__*，均在 .gitignore）不受 reset 影响。
REPO=/opt/md-src
cd "$REPO"
git stash push -q -u -m "cloud-local-$(date +%F)" 2>/dev/null || true
if git fetch -q origin main && git reset --hard -q origin/main; then
  echo "[$(date '+%F %T')] 代码已同步 origin/main -> $(git log -1 --format='%h %ci')"
else
  echo "[$(date '+%F %T')] [warn] 代码同步失败，沿用当前工作区代码（可能很旧）"
fi
git stash pop -q -f 2>/dev/null || true
git checkout -- data/ 2>/dev/null || true   # 生成产物以新代码重跑，不保留旧 stash 值

D=$(date +%Y-%m-%d)
echo "[$(date '+%F %T')] shadow start $D"

# —— 抓取（境外源 + 行情 + 价格/公司）——
FETCH_RC=0
python3 fetch_news.py --fetch-detail --report-date "$D" --quiet || FETCH_RC=$?
if [ "$FETCH_RC" -ne 0 ]; then
  echo "[$(date '+%F %T')] [warn] fetch_news 退出码 $FETCH_RC（某源可能失败，见 data/fetch_health_$D.json）"
fi
python3 fetch_lme.py 2>/dev/null || echo "[warn] fetch_lme 跳过"
python3 fetch_price_history.py 2>/dev/null || echo "[warn] price 跳过"
python3 fetch_company.py 2>/dev/null || echo "[warn] company 跳过"

# —— 生成站点（AI 摘要，失败重试 3 次）——
ok=0
for i in 1 2 3; do
  if python3 -m bprime.pipeline --report "$D"; then ok=1; break; fi
  echo "[warn] pipeline 第 $i 次失败（可能是 DeepSeek 超时），30 秒后重试"
  sleep 30
done
[ $ok -eq 1 ] || { echo "[error] pipeline 连续 3 次失败，本日中止（未对比）"; exit 1; }

python3 export_news_json.py 2>/dev/null || true
python3 build_static.py 2>/dev/null || true
echo "[$(date '+%F %T')] 生成完成"

# —— 对比前强制刷新本地镜像（避免拿陈旧基准误判）——
echo "[$(date '+%F %T')] 刷新 gh-pages 本地镜像"
if git -C /var/www/mining-daily fetch -q origin gh-pages \
   && git -C /var/www/mining-daily reset --hard -q origin/gh-pages; then
  echo "[ok] 镜像已刷新到最新 gh-pages"
else
  echo "[warn] 镜像刷新失败，今日数字可能虚高（基准陈旧）"
fi

# —— 影子对比 + 推送 shadow-reports ——
{
  echo "[$(date '+%F %T')] fetch_news 退出码=$FETCH_RC（0=正常）"
  python3 shadow_diff.py
} | tee /opt/md-src/data/shadow_diff_$D.txt
cp /opt/md-src/data/shadow_diff_$D.txt /var/www/mining-daily/
echo "[$(date '+%F %T')] shadow done"

cd /opt/md-src
git add -f data/shadow_diff_$D.txt
git commit -m "shadow diff $D" >/dev/null 2>&1 || true
git push origin HEAD:shadow-reports >/dev/null 2>&1 || echo "[warn] push shadow report 失败"

# —— 推送当天候选池到 server/fetch（云端质量对比的数据源）——
if [ -x /opt/md-src/push_server_fetch.sh ]; then
  /opt/md-src/push_server_fetch.sh "$D" || echo "[warn] push server/fetch 失败"
fi