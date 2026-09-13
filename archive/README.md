# archive/ — 一次性脚本归档

本目录存放历史上用于临时修复、单日生成或一次性分析的脚本。
这些脚本**不再被 CI 或生产流程调用**，仅作历史留存。

## 目录结构

| 子目录 | 内容 |
|--------|------|
| `generators/` | 每日生成器（`generate_YYYYMMDD.py`）+ 已废弃的 `gen_today.py` / `generate_daily.py` |
| `fixes/` | 一次性修复脚本（`add_rights_*`, `fix_links*`, `patch*`, `rebuild_*` 等） |
| `analysis/` | 一次性分析/分类脚本 + `update_analysis_*` 系列 |

## 当前正确做法

- 每日生成：用当日 `generate_YYYYMMDD.py`，公共骨架见 `generate_common.py`
- 抓取行情：`fetch_lme.py` / `fetch_price_history.py` / `fetch_ma.py`
- 抓取新闻：`fetch_news.py`
- 部署：`deploy_pages.py`

---
归档时间：2026-09-13
