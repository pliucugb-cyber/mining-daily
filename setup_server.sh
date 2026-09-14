#!/usr/bin/env bash
#
# setup_server.sh —— 矿业日报「抓取上云」一键部署脚本（方案 B·阶段①）
#
# 目标平台：任意境内 Linux（轻量应用服务器 / ECS / 腾讯云 Lighthouse 等）
# 职责：只把「每日抓取」搬上云；生成 / 部署仍由 WorkBuddy 负责（分工不变）。
#
# 前置：已 git clone 本仓库（当前目录即仓库根，或脚本会自动定位）
# 用法：  bash setup_server.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "==> [1/6] 环境校验"
python3 --version
if ! command -v git >/dev/null; then
  echo "    安装 git ..."
  (command -v apt  >/dev/null && sudo apt-get update -y && sudo apt-get install -y git) || \
  (command -v yum  >/dev/null && sudo yum install -y git) || \
  (command -v dnf  >/dev/null && sudo dnf install -y git) || \
  echo "    ⚠️ 未能自动安装 git，请手动安装后重跑"
fi
if ! command -v cron >/dev/null && ! command -v crond >/dev/null; then
  echo "    安装 cron ..."
  (command -v apt  >/dev/null && sudo apt-get install -y cron  && sudo systemctl enable --now cron)  || \
  (command -v yum  >/dev/null && sudo yum install -y cronie && sudo systemctl enable --now crond) || \
  echo "    ⚠️ 未能自动安装 cron，请手动安装后重跑"
fi

echo "==> [2/6] 时区设为 Asia/Shanghai"
sudo timedatectl set-timezone Asia/Shanghai 2>/dev/null || \
  (echo "Asia/Shanghai" | sudo tee /etc/timezone >/dev/null) || true
echo "    当前时间：$(date)  （应为北京时间）"

echo "==> [3/6] 生成 SSH 部署密钥（回推候选池到 GitHub draft/fetch 分支用）"
KEY=~/.ssh/mining_daily_deploy
if [ ! -f "$KEY" ]; then
  mkdir -p ~/.ssh && chmod 700 ~/.ssh
  ssh-keygen -t ed25519 -N "" -f "$KEY" -C "mining-daily-cloud-fetch"
  echo "    ✅ 已生成 $KEY.pub"
  echo "    ⚠️ 请把下面这段公钥添加到 GitHub 仓库 Deploy keys（勾 Allow write access）："
  echo "       Settings → Deploy keys → Add deploy key"
  echo "----------------------------------------------------------------"
  cat "$KEY.pub"
  echo "----------------------------------------------------------------"
else
  echo "    已存在 $KEY，跳过生成"
fi

echo "==> [4/6] 写入 LME_TOKEN 环境变量模板"
ENVFILE=~/.mining-daily.env
if [ ! -f "$ENVFILE" ]; then
  cat > "$ENVFILE" <<'EOF'
# 矿业日报抓取所需密钥（cron 环境无用户 env，需在此显式提供）
# 取值：本机 lme_token.txt 内容（与 GitHub Secrets.LME_TOKEN 相同）
LME_TOKEN=__请填写__
EOF
  echo "    ✅ 已生成 $ENVFILE，请编辑填入真实 LME_TOKEN"
else
  echo "    已存在 $ENVFILE，跳过"
fi

echo "==> [5/6] 安装 crontab（每天北京时间 06:15 抓取 + 回推 draft/fetch 分支）"
# 系统已设 Asia/Shanghai，故 06:15 即本地 15 6 * * *。
# 流程：注入 env → 抓新闻候选池 → 抓 LME → 回推候选池到 draft/fetch（生成环节仍在 WorkBuddy）
CRON_LINE="15 6 * * *  set -a; . ~/.mining-daily.env; set +a; cd $REPO_DIR && /usr/bin/python3 fetch_news.py --report-date \"\$(date +\\%Y-\\%m-\\%d)\" --quiet && /usr/bin/python3 fetch_lme.py && { git add -f data/news_candidates_*.json 2>/dev/null; git -c user.email=bot@mining-daily -c user.name=mining-daily-cloud commit -m \"chore(fetch): \$(date +\\%Y-\\%m-\\%d) 候选池（云抓取）\" >/dev/null 2>&1; git push origin HEAD:refs/heads/draft/fetch --force; } >> data/cron_fetch.log 2>&1"
# 去重：清掉旧 mining-daily 行再写，避免重复叠加
( crontab -l 2>/dev/null | grep -v "mining-daily" || true ) | { cat; echo "$CRON_LINE"; } | crontab -
echo "    ✅ crontab 已写入（北京 06:15 / UTC 22:15）"
echo "    查看：crontab -l"

echo "==> [6/6] 首次可达性探针（国内节点能抓哪些源）"
/usr/bin/python3 probe_domestic_reach.py || echo "    ⚠️ 探针异常，可稍后手动跑：python3 probe_domestic_reach.py"

echo ""
echo "============================================================"
echo "✅ 阶段① 部署脚本执行完毕"
echo "请完成两件事后方可自动运行："
echo "  1) 编辑 ~/.mining-daily.env，填入真实 LME_TOKEN"
echo "  2) 把部署公钥加到 GitHub Deploy keys（写权限）"
echo "验证：手动跑  python3 fetch_news.py --quiet  看是否落盘候选池"
echo "决策：看 data/probe_domestic_reach.json ——"
echo "  - 若 mining(境外) 不可达 → 仍需保留 GitHub 抓境外源，或给云配代理"
echo "  - 若全部可达        → 国内节点可独立承担，GitHub 可退役"
echo "============================================================"
