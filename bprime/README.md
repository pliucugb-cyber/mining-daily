# B' 无人化矿业日报骨架（代码资产化 · 待激活）

> 目标：把"每日抓取 + 生成 + 部署"全链路搬到国内轻量服务器，彻底甩手 WorkBuddy。
> 与 WB 当前模式的根本区别：**生成逻辑是固定代码、模型只填空**，不依赖每日 LLM 临时写脚本。

## 架构

```
fetch_news.py (复用)        -> 候选池 data/news_candidates_<date>.json
   │
bprime.generate            -> DeepSeek 批量写中文摘要 (固定 prompt)
   │
bprime.judge               -> 数字落地校验(verify_numbers) + 有界修复一次 + 分级
   │                          auto / review(残差人工) / dropped(丢弃)
   │
verify_numbers --strict    -> 上线前最终机械守门（防 LLM 抄错数字）
   │
generate_common (复用)     -> 渲染今日区块 (ni / render_cat_groups / card)
   │
deploy_pages.py (复用)     -> 推 gh-pages
```

## 本地"搭通待激活"（零成本，不依赖 key/网络）

```bash
python -m bprime.pipeline --mock            # 读 data/snapshots 快照，离线跑通全链路
python -m bprime.pipeline --mock --strict   # 同上 + 数字守门
```

mock 模式用确定性离线 Provider 生成摘要、校验数字、渲染预览到
`data/bprime_preview_<date>.html`，**不碰真实 index.html、不部署**。用于验证模块串联。

## 激活步骤（买到轻量服务器后）

1. 开轻量应用服务器（2核2G，约 68 元/年首单），装好 git。
2. 把本仓库 scp / git clone 到 `/app`。
3. `cp .env.example .env` 并填 `DEEPSEEK_API_KEY` 与 `LME_TOKEN`。
4. 生成 SSH 部署密钥并加到 GitHub（deploy_pages 推 gh-pages 用）。
   （`setup_server.sh` 已含密钥生成 + crontab 模板，可直接复用。）
5. `docker build -t bprime . && docker run -d --restart=always --env-file .env bprime`
   或裸机：`pip` 无需（纯 stdlib），`crontab /etc/cron.d/bprime` 即每天 06:15 跑。
6. 首跑观察 3 天日志 `/var/log/bprime.log`，确认 egress/生成质量稳定后，退役 GitHub Actions 的 fetch 链路。

## 成本

- 轻量服务器：≈68 元/年首单（续费 ~82–99 元/年）。
- DeepSeek：≈40–80 元/年（deepseek-chat，14 条/日摘要 + judge）。
- 域名/gh-pages/agent-mail：免费。

## 残留风险（诚实边界）

- **语义误读 judge 仍可能漏**（研究与人类互认约 64–90%）：所以 `dropped` 之外，
  `review` 级残差仍需你早间点一眼（分级发布闸），这是最后一道、且比你现档位2 全量复核轻。
- 完整渲染需对齐 `REFERENCE.md §42` 形态契约（价格卡/矿权双视图/简报/四分析文件）。
  骨架已复用 `generate_common` 真实原语，但**完整采编模板**在激活前需补全（见 pipeline 注释 TODO）。
- 境外源在真实云节点需实测 egress（本机已验证 metal/mining 可达；真机再确认一次）。

## 文件

- `bprime/config.py` 环境变量（与云账号解耦）
- `bprime/llm.py` DeepSeek 客户端（真实 + mock）
- `bprime/generate.py` 生成器（固定 prompt）
- `bprime/judge.py` judge/repair + 分级
- `bprime/pipeline.py` 流程编排（cron 入口）
- `verify_numbers.py` 数字落地校验（WB 与 B' 共用）
- `Dockerfile` / `.env.example` 激活封装
- `data/snapshots/candidates_sample.json` 离线回归基线
