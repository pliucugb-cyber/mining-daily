#!/usr/bin/env bash
#
# setup_bprime.sh —— 矿业日报「B' 全链路上云」一键部署脚本
#
# 目标平台：任意境内 Linux（轻量应用服务器 / ECS / Lighthouse）
# 职责：把「抓取 → LLM 生成 → 校验 → 渲染整站 → 导出 news-data → 构建热榜 → 部署」
#       全流程搬到云服务器定时跑，彻底摆脱本机 WorkBuddy 常驻。
#
# 与 setup_server.sh 的区别：后者只做"抓取"（生成仍在 WB）；
#                       本脚本做"全链路"（含 DeepSeek 生成 + generate_site 渲染 + 部署）。
#
# 前置：已 git clone 本仓库到某目录（当前目录即仓库根，或脚本自动定位）
# 用法：  bash setup_bprime.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "==> [1/7] 环境校验"
python3 --version
if ! command -v git >/dev/null; then
  (command -v apt  >/dev/null && sudo apt-get update -y && sudo apt-get install -y git) || \
  (command -v yum  >/dev/null && sudo yum install -y git) || \
  (command -v dnf  >/dev/null && sudo dnf install -y git) || \
  echo "    ⚠️ 未能自动安装 git，请手动安装后重跑"
fi
if ! command -v cron >/dev/null && ! command -v crond >/dev/null; then
  (command -v apt  >/dev/null && sudo apt-get install -y cron  && sudo systemctl enable --now cron)  || \
  (command -v yum  >/dev/null && sudo yum install -y cronie && sudo systemctl enable --now crond) || \
  echo "    ⚠️ 未能自动安装 cron，请手动安装后重跑"
fi

echo "==> [2/7] 设时区 Asia/Shanghai"
sudo timedatectl set-timezone Asia/Shanghai 2>/dev/null || \
  (echo "Asia/Shanghai" | sudo tee /etc/timezone >/dev/null) || true
echo "    当前时间：$(date) （应为北京时间）"

echo "==> [3/7] 生成 gh-pages 部署密钥（写权限，推 Pages 用）"
KEY=~/.ssh/mining_daily_deploy
if [ ! -f "$KEY" ]; then
  mkdir -p ~/.ssh && chmod 700 ~/.ssh
  ssh-keygen -t ed25519 -N "" -f "$KEY" -C "mining-daily-bprime-deploy"
  echo "    ✅ 已生成 $KEY.pub"
  echo "    ⚠️ 请把下面这段公钥添加到 GitHub 仓库 Deploy keys（务必勾 Allow write access）："
  echo "       Settings → Deploy keys → Add deploy key"
  echo "----------------------------------------------------------------"
  cat "$KEY.pub"
  echo "----------------------------------------------------------------"
else
  echo "    已存在 $KEY，跳过生成"
fi
echo "    （若 22 端口被网络重置，改用 443：在 ~/.ssh/config 加 Host github.com Hostname ssh.github.com Port 443 IdentityFile $KEY）"

echo "==> [4/7] 写入 .env 模板（cron 环境无用户 env，需显式提供）"
ENVFILE=~/.mining-daily.env
if [ ! -f "$ENVFILE" ]; then
  cat > "$ENVFILE" <<'EOF'
# 矿业日报 B' 全链路所需密钥（cron 环境由本文件注入）
# DEEPSEEK_API_KEY：DeepSeek 官方 key（生成中文摘要用），年费约 45-70 元
DEEPSEEK_API_KEY=__请填写__
# LME_TOKEN：伦敦金属交易所数据令牌（fetch_lme 用），与 GitHub Secrets.LME_TOKEN 相同
LME_TOKEN=__请填写__
EOF
  echo "    ✅ 已生成 $ENVFILE，请编辑填入真实 DEEPSEEK_API_KEY / LME_TOKEN"
else
  echo "    已存在 $ENVFILE，跳过"
fi

echo "==> [5/7] 安装 crontab（每天北京时间 06:15 跑全链路）"
# 系统已设 Asia/Shanghai，故 06:15 即本地 15 6 * * *。
# 流程：注入 env → 抓新闻(含正文) → 抓 LME/价格/公司 → bprime 生成(LLM+校验+渲染 index.html)
#       → export_news_json(写 news-data.js) → build_static(热榜/AI) → 部署 gh-pages
CRON_LINE="15 6 * * *  set -a; . ~/.mining-daily.env; set +a; cd $REPO_DIR && python3 fetch_news.py --fetch-detail --report-date \"\$(date +\\%Y-\\%m-\\%d)\" --quiet && python3 fetch_lme.py && python3 fetch_price_history.py && python3 fetch_company.py && python3 -m bprime.pipeline --date \"\$(date +\\%Y-\\%m-\\%d)\" && python3 export_news_json.py && python3 build_static.py && python3 deploy_pages.py >> data/cron_bprime.log 2>&1"
# 去重：清掉旧 mining-daily 行再写，避免重复叠加
( crontab -l 2>/dev/null | grep -v "mining-daily" || true ) | { cat; echo "$CRON_LINE"; } | crontab -
echo "    ✅ crontab 已写入（北京 06:15 / UTC 22:15）"
echo "    查看：crontab -l   日志：tail -f data/cron_bprime.log"

echo "==> [6/7] 加日志轮转（防 cron 日志无限膨胀）"
if command -v logrotate >/dev/null; then
  sudo tee /etc/logrotate.d/mining-daily >/dev/null <<EOF
$REPO_DIR/data/cron_bprime.log {
    size 5M
    rotate 4
    missingok
    notifempty
    compress
    copytruncate
}
EOF
  echo "    ✅ 已配置 logrotate（>5M 切 4 份）"
else
  echo "    ⚠️ 未找到 logrotate，请手动定期清理 data/cron_bprime.log"
fi

echo "==> [7/7] 首次手动跑通（不依赖 cron，先验证整链）"
echo "    建议手动依次执行，确认无报错后再交给定时任务："
echo "      set -a; . ~/.mining-daily.env; set +a"
echo "      python3 fetch_news.py --fetch-detail --report-date \$(date +%Y-%m-%d) --quiet"
echo "      python3 fetch_lme.py && python3 fetch_price_history.py && python3 fetch_company.py"
echo "      python3 -m bprime.pipeline --date \$(date +%Y-%m-%d)"
echo "      python3 export_news_json.py && python3 build_static.py && python3 deploy_pages.py"

echo ""
echo "============================================================"
echo "✅ B' 全链路部署脚本执行完毕"
echo "请完成三件事后方可自动运行："
echo "  1) 编辑 ~/.mining-daily.env，填入真实 DEEPSEEK_API_KEY / LME_TOKEN"
echo "  2) 把部署公钥加到 GitHub Deploy keys（写权限）"
echo "  3) 按第 7 步手动跑通一次，确认 data/cron_bprime.log 无报错"
echo "决策与回滚：本机 WB 每日自动化先保留不删；云链路稳定 7-14 天后再停 WB，"
echo "          届时云出任何问题，WB 一键恢复，日报不断更。"
echo "============================================================"
