# 矿业日报 · 每日复核任务 · 执行记忆

## 2026-09-09 08:00（周三）

### 判定：06:00 任务"误判未跑成"→ 实则已跑成

开任务时看 `ls -la index.html` mtime=09:04、title=2026-09-08 标记为"页面日期非今天"。但实际上：
- 06:00 自动化任务（mining-daily-bot）已成功并提交 `fc679d4`：feat(daily): 2026-09-09 日报 — 15 条今日新增 + 7 宗矿权 / 价格卡真实涨幅 / 4 文件分析 (build 20260909-0906)
- fc679d4 commit 时间：Wed Sep 9 09:16:04 2026 +0800
- `git show fc679d4:index.html` 标题已是 2026-09-09、今日新增（2026-09-09 抓取）、todayCount=15条、archiveCount=106条
- 工作树当时是干净的（与 fc679d4 一致），我误把 `index.html.bak-0908`（09-08 备份）当成"工作树状态"判断 → 执行补跑

### 补跑动作（实际生成了一版与 fc679d4 几乎相同的 index.html）
- 复制 generate_20260908.py → generate_20260909.py，改 REPORT/GRAB='2026-09-09'、星期三、价格卡（09-08 SHFE 收盘 + 09-09 LME）、new_items 重写为 14 条（与 fc679d4 的 15 条几乎重叠）
- `cp index.html.bak-0908 index.html` 还原 09-08 状态后跑脚本生成 09-09
- 跑 inject_ma.py / export_news_json.py 同步数据层
- 跑 preflight_check.py / source_whitelist.py / validate_urls.py

### 修复
1. **失效 URL（geoglobal mnr 10308875.htm = 智利坎加洛铜矿延伸至800米）**：HTTP 404 真失效，删除
2. **低价值公告（兴业证券持续督导意见 × 2）**：归入"应删"分类（券商核查意见），从往期区删除
3. **source_whitelist.py 补录**：新增 `szse.cn` (含 disc.szse.cn PDF) 与 `ccmn.cn`，与用户清单的国内 14 域对齐
4. **电投能源 szse PDF 公告补回往期区**：白名单修复后，将该 PDF 公告插入到「行业动态」sub-cat 下
5. **子分类计数 / 区块计数同步重算**（每次新增删除条目后都重算）

### 校验结果
- preflight_check ✅ 全通过（marker 1/1/1、div 收支平衡、build-version 20260909-0913）
- source_whitelist ✅ 128 unique URLs（6 skipped functional），全部白名单内
- validate_urls 121 条 | 13 误报（curl 拿不到 JS 渲染正文，curl 复测 HTTP 200）+ 0 真失效
- backcheck 报告 14 条疑似漏稿（阈值 0.35，相似度 0.033~0.102，全部为行情分析/评论）→ 全部判无效，**无漏稿**

### 提交与同步
- commit 67ece11（push origin main 成功）
- deploy_pages.py → gh-pages d7532d8
- 线上 30 秒后复验：title 2026-09-09 / todayCount 15条 / archiveCount 107条 / 电投能源 已显示 ✅

### 本轮踩坑与教训（下次注意）
1. **"页面是昨天的"≠"06:00 没跑"**：要先看 git log 与工作树状态对比，再判断是否真要补跑。本次幸亏 06:00 任务的 fc679d4 已合并成功，且我新生成的 index.html 与 fc679d4 内容几乎相同，没有覆盖破坏。
2. **generate_*.py 的 `ni()` 会 raise ValueError 拦截白名单外 URL**：本次 source_whitelist.py 缺 szse.cn/ccmn.cn 时，generate 09-08 的脚本里那条 disc.szse.cn 电投能源 PDF 在 09-08 页面里就没出现，导致 09-09 页面也缺失；白名单修复后需手动补录到往期区。
3. **generate_*.py 跑前要先 `cp index.html.bak-XXXX index.html`** 还原目标日期的前一版状态，避免被上一个备份状态搞乱。本次我误把 09-08 备份当工作树状态，没意识到 fc679d4 已经成功。
4. **validate_urls.py 的 "0/8 关键词命中" 在 JS 渲染站上是误报**：所有 smm.cn / metal.com / mining.com 都触发，但 curl 复测 HTTP 200 + _fetchsum.py 拿到完整正文即可定性为"误报"，不要轻信删除。
5. **新版的 generate_*.py 改 new_items 时，一次性写整段比 Edit 多次替换更稳**：Edit 工具对中文双引号敏感，分段替换容易因 old_string 微小差异失败。用 _replace_new_items.py + 正则整段替换最稳。

### 释放
- `automation_lock.py release verify` RELEASED ✅

## 2026-09-06 10:10（周日）

结论：**09:00 那轮未跑成功 → 本轮补跑完整生成流程**。线上已重新同步。

### 如何判定「09:00 没跑成」（本轮新经验，下轮直接照做）
最省事的三看，任一不对即判定失败：
1. `ls -l --time-style=+%Y-%m-%d_%H:%M index.html morning_report.json mining_news.json`
   —— mtime 不是今天即为未跑成（本轮：index.html 停在 09-06 02:03 的功能提交，morning_report 停在 09-05 09:29）。