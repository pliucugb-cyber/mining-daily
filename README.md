# 矿业日报 — Mining Daily

> 有色金属行业每日动态、行情、AI 辅助分类，部署在 GitHub Pages。
> 🔗 [线上站点](https://pliucugb-cyber.github.io/mining-daily/)

## 功能概览

| 模块 | 说明 |
|------|------|
| **行情区** | LME 六大金属 + 上期所主力 + 上金所 + 碳酸锂，热力图 / K 线 / 涨跌排行 |
| **新闻区** | 自动抓取国内（SMM、有色网、东方财富）+ 境外（LME、Mining.com 等）信源 |
| **AI 分类** | DeepSeek 辅助归类政策/并购/融资/产能等，人工审核后发布 |
| **离线支持** | Service Worker 预缓存核心资源，弱网/无网可浏览历史 |
| **移动端** | 响应式布局 + PWA 安装，支持深色模式 |

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | 原生 HTML / CSS / JavaScript（ESM 无构建），Service Worker |
| 后端（CI/抓取） | Python 3.8+ **纯标准库**（urllib / json / re / gzip / xml.etree / ssl） |
| 部署 | GitHub Pages（静态站）+ GitHub Actions（定时抓取） |
| 边缘服务 | Netlify Edge Functions（QA 问答）、阿里云 FC / 华为云 FG / SCF（新闻查询） |
| 缓存/鉴权 | Cloudflare Workers（前端验证） |

> ✅ **无 pip install** —— 所有生产脚本仅用标准库，CI 启动无需装包。

## 本地运行

### 前置条件
- Python 3.8+
- 现代浏览器（Chrome / Edge / Firefox）
- （可选）LME API Token：东财 futures api 行情 token（`lme_token.txt`）

### 快速开始

```bash
# 1. 抓取行情 + 生成前端数据
python fetch_price_history.py
python fetch_lme.py

# 2. 抓取新闻候选池
python fetch_news.py

# 3. 生成当日页面（自动化流程）
python generate_common.py   # 公共骨架
python generate_daily.py    # 当日生成器

# 4. 本地预览
python -m http.server 8080
# 浏览器打开 http://localhost:8080
```

### 常用脚本

```bash
python fetch_news.py --merge           # 抓取 + 并入月度库
python fetch_news.py --source smm      # 只跑指定信源
python backcheck.py                    # 漏稿回溯
python build_static.py                 # 构建静态站
python deploy_pages.py                 # 部署到 gh-pages
```

## CI / 定时任务

| Workflow | 触发 | 作用 |
|----------|------|------|
| `daily.yml` | 每天北京时间 06:15（UTC 22:15） | 抓取行情 + 新闻候选池，推 `draft/fetch` 分支（阶段一） |
| Pages build | gh-pages 变更 | 自动构建部署静态站 |

**Secrets 配置**：
- `LME_TOKEN` — 东财 futures api 行情 token

**并发控制**：`concurrency` group `mining-daily-fetch`，`cancel-in-progress: false`

## 目录结构

```
mining-daily/
├── app.js                 # 前端主脚本（行情、新闻、排行渲染）
├── sw.js                  # Service Worker
├── index.html             # 主页（生成产物，勿手动编辑）
├── generate_common.py     # 生成器公共骨架
├── generate_YYYYMMDD.py   # 每日生成器（自动化产出）
├── fetch_news.py          # 新闻爬虫（SOURCES 配置化）
├── fetch_lme.py           # LME 行情抓取
├── fetch_price_history.py # 历史 K 线抓取
├── fetch_ma.py            # 上金所 / GFEX 行情
├── export_news_json.py    # 导出月度新闻 JSON
├── preflight_check.py     # 运行前健康检查
├── automation_lock.py     # 并发锁（避免 06:00 / 08:00 打架）
├── deploy_pages.py        # 部署到 gh-pages
├── build_static.py        # 构建静态站
├── query_news.py          # 新闻查询接口
├── logutil.py             # 公共日志模块（MINING_LOG_PLAIN=1 回退裸 print）
├── source_whitelist.py    # 域名白名单
│
├── data/                  # 抓取数据（候选池 / 月度库 / 行情缓存）
│   ├── news_YYYY-MM.json  # 月度新闻库
│   ├── ma_YYYY-MM.json    # 月度行情
│   └── em_kline_cache/    # 东财 K 线缓存
│
├── netlify/               # Netlify 边缘函数（QA）
├── aliyun-fc/             # 阿里云函数（新闻查询）
├── huawei-fg/             # 华为云函数（新闻查询）
├── scf/                   # 腾讯云 SCF
├── worker/                # Cloudflare Workers
├── legacy-redirect/       # 旧跳转站
├── old-link-notice/       # 旧链接迁移提示
│
├── docs/                  # 设计文档 / UX 规格
├── reviews/               # UX 评审记录
├── archive/               # 一次性脚本归档（历史留存）
│   ├── generators/        # 历史 generate_YYYYMMDD.py
│   ├── fixes/             # add_rights / patch / fix_links 等
│   └── analysis/          # classify / update_analysis 等
│
└── .github/workflows/     # CI 配置
```

## 信源清单

`fetch_news.py` 内 `SOURCES` 字典定义所有信源，新增源只需加一条配置。当前启用：

| Key | 名称 | 国内/境外 |
|-----|------|----------|
| smm | SMM 有色资讯 | 国内 |
| cnmn | 中国有色金属网 | 国内 |
| miningweekly | 矿业周刊 | 国内 |
| （其他…） | | |
| lme | LME News | 境外 |
| mining_com | Mining.com | 境外 |

**三重过滤**：白名单域 → 有色相关性命中 → 时政/广告/招聘噪声排除

## 设计原则

1. **零依赖** —— 生产脚本纯标准库，CI 不装包
2. **阶段隔离** —— `draft/fetch` 分支与 `main` / `gh-pages` 完全隔离，抓取不碰线上
3. **配置化** —— 信源清单从脚本动态读取，不在 CI 里硬编码
4. **可观测** —— CI 输出各信源产出统计，零产出源自动标记

## License

MIT
