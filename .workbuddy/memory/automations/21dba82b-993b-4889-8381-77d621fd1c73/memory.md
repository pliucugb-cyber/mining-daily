# 矿业日报 · 每日复核任务 · 执行记忆

## 2026-09-06 10:10（周日）

结论：**09:00 那轮未跑成功 → 本轮补跑完整生成流程**。线上已重新同步。

### 如何判定「09:00 没跑成」（本轮新经验，下轮直接照做）
最省事的三看，任一不对即判定失败：
1. `ls -l --time-style=+%Y-%m-%d_%H:%M index.html morning_report.json mining_news.json`
   —— mtime 不是今天即为未跑成（本轮：index.html 停在 09-06 02:03 的功能提交，morning_report 停在 09-05 09:29）。
2. `<title>` 里的日期是否 = 今天。
3. 用 PowerShell 看有没有 python/node 生成进程在跑（`Get-Process python*,node*` 看 CommandLine），
   **排除「任务还在跑、我不该插手」的情况**再动手补跑。本轮确认无进程后才补跑。
⚠️ 注意干扰项：lme-data.js / price-history.js / price_history_detail.json 的 mtime 是今天 09:56，
   一度像是「跑了一半」。实际是行情脚本单独跑过，**不能用行情文件 mtime 判断生成是否成功**。

### 本轮修复/生成内容
- 补跑：标题/badge/更新时间/build-version/priceStripNote 统一 09-06；脚本 generate_20260906.py
- 今日新增 10 条（矿权 5 / 找矿技术 2 / 行业 2 / 国际 1），**每条都 curl 原文页核对标题·发布时间·正文数字**
- 往期按 **7 日窗口**（08-31 起）滚动；今日 10 + 往期 39 = 49，各处计数与 mining_news.json meta 一致
- 周日休市，价格卡沿用 09-04 收盘（与 09-05 完全相同，属正常，不要误判为没刷新）
- 四个分析文件用 update_analysis_20260906.py 重算；alerts 仍为碳酸锂 -5.30%（与价格卡一致，非异常）
- commit 2cf2c29 → push main 成功；deploy_pages.py 推 gh-pages（8d0adba）成功
- 线上核对：等待 75s 后 curl，与本地 index.html **字节级一致**

## 2026-09-05 10:10（首次记录）
结论：**09:00 那轮生成成功，本轮复核零修复**，仅刷新 validate_report.md 时间戳。
- 链接校验 47/47（0 失效 / 0 警告）
- 计数一致：今日 11 + 往期 36 = 47；7 日窗口最早 08-31
- 日期标记全为 2026-09-05；行情 15 品种最后 K 线 09-04
- LME 六卡、热榜经运行时渲染验证出值
- commit 35e373d 已 push

## 复用要点（下轮直接照做）

1. **「今日区」不等于当天日期**：09:00 抓取时源站当天稿未发布，今日区实际是前一自然日批次。
   判定是否正常 = 对比上一版：上一版今日区的日期应整批转入本版往期区。若出现重复才是问题。
2. **.news-item 计数**：用 Python `re.findall(r'class="news-item', seg)`，按 `id="todaySection"` →
   `id="archiveSection"` → `id="installGuideSection"` 切段。git bash 的 `grep -o | wc -l` 计数不可靠，勿用。
   全文计数会比真实条目多 1（JS 模板里的选择器字符串），属正常。
3. **交易日判断**：周六/周日运行时，最后 K 线为周五属正常，不要误判为「数据过期」而重跑 fetch。
4. **运行时渲染验证（无浏览器时）**：用技能 `html-runtime-render-check`。
   ⚠️ **路径坑**：脚本路径必须写成 `C:/Users/...` 全路径；写成 `~/.workbuddy/...` 会被 bash 展开成
   `/c/Users/...`，node 再解析成 `C:\c\Users\...` → MODULE_NOT_FOUND。
   ```bash
   NODE=C:/Users/中铝矿业投并部/.workbuddy/binaries/node/versions/22.22.2-2/node.exe
   S="C:/Users/中铝矿业投并部/.workbuddy/skills/html-runtime-render-check/scripts/verify_render.js"
   # 价格卡
   $NODE "$S" --html index.html --data lme-data.js --data price-history.js \
     --need renderLmePrices --init 'renderLmePrices()' \
     --probe '__cards.slice(0,6).map(function(c){return c._value.textContent+"  "+c._chg.textContent;})'
   # 热榜
   $NODE "$S" --html index.html --data news-data.js --need HOT_SRC_W --need HOT_KW --need NORMAL_KW \
     --need computeHotNewsLocal --need qaReportDate --init 'QA_ROWS = window.NEWS_DATA.news' \
     --probe 'computeHotNewsLocal(10)'
   ```
   依赖函数名变更需同步改参数：`renderLmePrices`、`computeHotNewsLocal`。
5. **线上比对**：curl 到本地路径再比对，别写 `/tmp`。curl 存 LF、本地 CRLF，需 `.replace(b'\r\n', b'\n')` 后再比。
6. **push / deploy 需显式指定密钥**：`GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes"` 前置。
   deploy_pages.py 也要带这个环境变量。
7. GitHub Pages 链接固定：https://pliucugb-cyber.github.io/mining-daily/ （勿改用 workbuddy_sites_deploy）。
8. **采集新闻的可复用手法**（本轮验证有效，严禁让模型凭记忆写标题）：
   curl 列表页 → Python 正则抽 `href + 标题 + 日期` → 再 curl 每条原文页 → 从原文页取
   `<title>`、`发布时间：YYYY-MM-DD`、`起始价/面积/收益率/保证金` 等数字写摘要。
   注意 `ky.mnr.gov.cn` 列表页的日期列与原文页 `发布时间` 会差 1 天，**以原文页为准**。
   注意 `worldmr.net` 是 GBK，需 `gb18030` 解码，否则全乱码。
   注意全球矿产资源网会重发旧稿（如"程利伟到访中国五矿"日期标 09-04 但正文是 4 月 8 日），**必读正文再决定**。
