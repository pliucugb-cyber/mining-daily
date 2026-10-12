# B' 全链路上云 · 落地步骤清单（轻量应用服务器版）

> 定稿 2026-09-28。目标：日报「抓取→生成→校验→渲染→部署」全部搬到云服务器，PC（WorkBuddy）降为兜底。
> 预期年成本：服务器 68 元 + DeepSeek 45–70 元 ≈ **110–140 元/年**。

## 执行状态（2026-10-12 · 已落地代码，待购服务器联调）

原清单把"激活缺口"写成 3 个小修，**低估了工作量**：每日 `generate_YYYYMMDD.py` 把精选新闻写死、且 `pipeline` 只渲染预览页。实际补的是**通用生成器重建**：

- ✅ `generate_site.py`（新增）：以 `generate_20261012.py` 为蓝本做参数化重构，仅改 3 处——常量块→argparse、`new_items` 写死列表→读 `site_news` JSON、写出路径→`--out`；其余渲染/价格/往期/校验逻辑逐字保留。**已用今日真实数据沙箱验证：产出 19 条、字节 600240、与线上仅 build-version 时间戳不同，零内容损失。**
- ✅ `bprime/generate.py`：新增 `dump_site_news()`，把 LLM 摘要落盘为 `data/site_news_<日期>.json`。
- ✅ `bprime/pipeline.py`：改写为"生成步骤"（取候选→LLM 生成→judge→落盘→`generate_site` 渲染→数字守门）；**部署不在此步**，留待 cron 在 `export_news_json`/`build_static` 之后统一 `deploy_pages`（因 `news-data.js` 须等 index.html 生成后由 `export_news_json` 反解）。
- ✅ `setup_bprime.sh`（新增）：全链路 cron（fetch→LME/价格/公司→bprime 生成→export_news_json→build_static→deploy）+ 部署写密钥 + .env + logrotate。
- 真实全链路顺序：`fetch_news --fetch-detail` → `fetch_lme`/`fetch_price_history`/`fetch_company` → `python -m bprime.pipeline` → `export_news_json.py` → `build_static.py` → `deploy_pages.py`。

> ⚠️ 未提交/未联调项：服务器未购买；`bprime` 生成目前仍用 mock 之外的真实 LLM 仅周自检验证过，`pipeline` 真实跑通需服务器上配好 `.env` 后手动按 setup_bprime.sh 第 7 步验证一次。

---

## 阶段 0：代码激活（我可代办，约 30 分钟）

现状：`bprime/` 骨架已"搭通待激活"，mock 模式验证过串联，但有 3 处激活缺口：

| # | 缺口 | 位置 | 改法 |
|---|------|------|------|
| 1 | 部署是占位注释 | `bprime/pipeline.py:82` `# 激活时：os.system('python deploy_pages.py')` | 改为真调 `deploy_pages.py` 并检查退出码 |
| 2 | cron 只装了 fetch-only | `setup_server.sh` 装的是「抓取→回推 draft/fetch」 | 新写 `setup_bprime.sh`：fetch `--fetch-detail` → `pipeline.py --strict` → deploy |
| 3 | `.env` 加载 | `bprime/config.py` 已支持（绝对路径定位） | 服务器上重建 `.env` 即可 |

## 阶段 1：购买服务器（你动手，10 分钟）

1. 平台：腾讯云或阿里云「轻量应用服务器」，**68 元/年促销档**（2核2G 足够，Python+cron 而已）。
2. 地域：**北京/上海/广州任选** —— 本机已实测（probe_domestic_reach）国内节点全部源可达，含境外 metal/mining。
3. 系统镜像：**Ubuntu 22.04 LTS**。
4. 防火墙规则：只放行 22/80/443，且 22 端口最好限定为你常用出口 IP。

## 阶段 2：服务器初始化（你动手或我给逐条命令，20 分钟）

```bash
# 1. 时区
sudo timedatectl set-timezone Asia/Shanghai

# 2. 拉代码（私有仓库：先生成只读 deploy key 加到 GitHub）
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -C "mining-daily-server"
cat ~/.ssh/id_ed25519.pub   # → GitHub 仓库 Settings → Deploy keys（不勾 write）
git clone git@github.com:<你>/<mining-daily>.git && cd mining-daily

# 3. 密钥文件（.env 已被 .gitignore 忽略，须重建）
cat > .env <<'EOF'
DEEPSEEK_API_KEY=sk-****（你现有的 key）
LME_TOKEN=****（lme_token.txt 内容）
EOF
chmod 600 .env

# 4. 手动验证抓取（能落盘 data/news_candidates_*.json 即通）
python3 fetch_news.py --fetch-detail --quiet

# 5. 手动验证全链路（先不部署，看 data/bprime_preview_*.html）
python3 -m bprime.pipeline --strict
```

## 阶段 3：部署密钥（写 gh-pages，5 分钟）

1. 服务器另生成**专用写密钥**：`ssh-keygen -t ed25519 -f ~/.ssh/mining_daily_deploy`
2. 公钥加到 GitHub **Deploy keys，必须勾选 Allow write access**（deploy_pages.py 要推 gh-pages 分支）。
3. 企业网/云上若 22 端口被 RST，走 443 兜底：`~/.ssh/config` 加
   ```
   Host github.com
     Hostname ssh.github.com
     Port 443
     IdentityFile ~/.ssh/mining_daily_deploy
   ```

## 阶段 4：并行验证 1–2 周（关键，别跳）

- crontab 装云链路（`setup_bprime.sh` 一键），**每天北京 06:00** 跑全链路；
- **WB 06:00 主链路照常跑，不要停**；
- 每天抽 1 分钟对比：云产出的 `bprime_preview_<日期>.html` vs 正式 index.html；
- 观察分级比例：`auto` 应占绝对多数，`review/dropped` 是否都是 PDF 无正文那类已知情况；
- 日志：`data/cron_pipeline.log`，加 logrotate 防膨胀。

## 阶段 5：切换 + 收尾

1. 云链路连续 7–14 天无误报、无漏发 → **停 WB 每日抓取/生成自动化**（保留定义，随时一键恢复）。
2. GitHub Actions `draft/fetch`（06:15）可停可留：留着当免费备份观察哨，不冲突。
3. WB 的新角色：**兜底 + 质量台**——看 `review/dropped` 分级项、跑周自检 qa_tuning（也可迁到云上 cron 周日 20:30）。

## 回滚预案

云链路任何一天没出报：WB 自动化仍在，重新启用即可，日报不断更。这是并行期的最大保险。

---

**下一步**：你买好服务器、拿到公网 IP 后告诉我，我先把阶段 0 的 3 处代码缺口补掉并推 GitHub，然后给你阶段 2 逐条命令的"照抄版"。
