# 矿业新闻日报自动化 — 执行记录

## 2026-09-05（周六）✅ 全流程成功
- 行情：fetch_lme.py 6/6、fetch_price_history.py 15/15 均成功。周六休市，最新数据为 09-04（周五）收盘，价格卡沿用并标注。
- 新闻：实采 11 条（矿权 3 / 找矿 3 / 行业 3 / 国际 2），全部逐页核实。
- 链接校验：47/47 通过，0 失效 0 告警。
- git：commit 22f291f 已 push main；deploy_pages.py 已推 gh-pages（84521c3）。
- 线上验证：首轮 curl 仍为旧版（Pages 延迟），等待 70 秒后复验通过（标题 2026-09-05、沪铜 108,780、is-new 11 条）。

### 本次踩坑与经验（重要）
1. **周末/休市日无当日行情**：K 线最新日期仍是上一交易日，价格卡直接沿用上日收盘，不要误判为抓取失败。
2. **generate_*.py 的 sub-count 渲染 bug**：`render_cat_groups` 中 flag 与 suffix 会重复拼接成「3新增新增」。正确输出应为「3条新增」（今日区）/「18条」（往期区）。新脚本已修正为单参数 suffix。
3. **shmet.com 为 JS 渲染的 SPA**：curl 只能拿到空壳 `<title>资讯详情-上海金属网</title>`，validate_urls.py 会误报「疑似错挂」。不要选用该站链接，已改用 worldmr.net（静态可核验）。
4. **export_news_json.py 会把条目写进月度归档**：若生成后又替换了某条新闻，需手动从 data/news_YYYY-MM.json 删除残留，否则归档数与页面数不一致。
5. **今日区分类顺序**：条目按 CAT 常量在 new_items 列表中的出现顺序分组，同名分类会自动合并计数，注意把同类条目写在一起。

### 收尾补充（第二轮）
- 补充提交 `11bd8dd`：.gitignore 增加 `worker/.wrangler/`（Cloudflare Workers 本地构建缓存，此前一直以未跟踪状态干扰 git status）。
- 质检确认：今日要闻区（digestStrip）由 JS 从 news-data.js 取 `n===报告日期` 的条目，本次 11 条均已正确带 n=2026-09-05，前端可正常提取前 4 条。
- signals.json 因历史已积累 15 个交易日，本次首次可输出 ma5/ma10（昨日为 null），信号质量提升。
- 线上最终复验：HTTP 200，标题/日期徽章/is-new 11 条均正确。

### 可复用脚本
- generate_20260905.py（页面重建，含 7 日窗口 WIN_FROM=08-30、价格卡、计数同步）
- update_analysis_20260905.py（四个分析文件：morning_report / sentiment / signals / alerts）

---

## 2026-09-06（周日）✅ 成功（经两轮：10:00 补跑 + 10:30 分类修正）
- 行情：fetch_lme.py 6/6、fetch_price_history.py 15/15 成功；周日休市，最新为 09-04 收盘，价格卡沿用并标注。
- 新闻：最终 12 条（矿权 5 / 找矿 2 / 行业 3 / 国际 2），全部逐页 curl 核实。
- 链接校验：51/51 通过，0 失效 0 告警。
- git：main 推至 050d2fa；deploy_pages.py 推 gh-pages（617b2f5）。线上复验通过（标题/日期/is-new 12 条/沪铜 108,780）。
- 注意：本日出现两个自动化实例并发（09:00 轮未跑成 + 10:00 复核补跑），最终以补跑结果为准。

### 本次踩坑与经验（重要）
1. **并发实例互相覆盖**：09:00 与 10:00 两轮同时跑，index.html 被反复改写。动手前先看
   index.html / mining_news.json 的 mtime 是否在最近 1 分钟内变动，确认无对手进程再改。
2. **判"新条目"必须查 news-data.js 的 `n`（first_seen）**：只看页面会误把 09-04 已收录的
   旧条目当今日新增（本次「政府干预关键矿产」即为此坑，已剔除并换新）。
3. **中国企业报道不要归入"国际矿业动态"**：紫金矿业被误分类，已归位行业动态。
4. **优先增量补丁而非整页重建**：重建会把今日区滚入往期、并在 data/news_YYYY-MM.json
   留下被替换条目的残留。
5. **别用 `ls` 字节数 vs `len(html)` 字符数判断内容丢失**（中文 UTF-8 三字节，差异可达 15%+），
   改用 `git diff --stat` 确认改动范围。
6. 周日各官方源（cgs / chinania / cnmn / geoglobal）基本无当日更新，最新内容多停在 09-04，
   只能从矿权市场 09-05 发布的公告里找真正的新条目。

### 可复用脚本
- generate_20260906.py / update_analysis_20260906.py（补跑轮生成）
- patch_20260906_cats.py（今日区分类重分配 + 追加条目 + 计数同步，增量）
- patch2_20260906_intl.py（替换指定 URL 的今日条目，增量）

---

## 2026-09-08（周二）✅ 全流程成功
- 行情：LME 6/6（09-08 电子盘）；国内 15/15（09-07 收盘，价格卡全量刷新）。
- 新闻：**32 条**（找矿 3 / 行业 16 / 国际 13），含境外 4 条（MINING.COM ×2、SMM 国际站 ×2）；候选池 199 条，采纳 32 条（约 16%）。
- 矿权 6 宗（江西 5 探矿权转让 + 陕西勉县铺沟铅锌矿采矿权转让）仅入 rightsSection 数据层。
- 链接校验 110 条：3「失效」+1「告警」均为境外英文页中文意译标题的误判，实际均 200 可达。
- git main → 4cce925；gh-pages → d60143d。线上复验通过（build 20260908-0926、沪铜 109,410、LME 铜 14,521.00）。

### 关键经验（务必沿用）
1. **价格卡重建必须按 `<div>` 深度匹配整块替换**，不能用 `[\s\S]*?</div></div>` 非贪婪正则——会在第一张卡末尾截断，
   造成旧卡残留 + div 收支失衡（preflight 报「多余的 </div>」）。generate_20260908.py 内已有 `_replace_block()`。
2. **fetch_news.py geoglobal 源 URL bug 已修**：子栏目目录（kydt/zhyw 等）必须整段捕获，否则 URL 全 404。
3. **cnmn.com.cn 列表日期不可信**：必须取详情页确认真实发布日期，否则误把 3~7 天前的稿当今日新增。
4. **境外条目中文意译标题**会让 validate_urls.py 报「失效」（标题关键词命中英文页为 0）——属预期误判，需人工 curl 复核，不要据此删稿。
5. 巨潮 fetch_ma.py 偶发 504，按规范跳过即可，不影响主流程。

### 可复用脚本
- generate_20260908.py / update_analysis_20260908.py / add_rights_20260908.py

---

## 2026-09-09（周三）✅ 全流程成功（含并发冲突修复）
- 行情：LME 5/6（锡未更新沿用 9-8 收盘 54,862）；国内 9/9 SHFE/上金所/GFEX（09-08 收盘），价格历史 15 品种 OK。
- 新闻：**15 条**（找矿 2 / 行业 5 / 国际 8），境外 6 条（MINING.COM ×2、SMM 国际站 ×4）保留英文原题与 data-orig-title。
- 矿权 7 宗：新疆托里安山岩（挂牌）、辽宁岫岩金多金属（转让）、山东乳山金矿（出让结果）、四川马尔康金矿（挂牌）、内蒙阿巴嘎旗银铅锌（协议）、宁城金矿（协议）、乌拉特前旗铁矿（协议），只入 rightsSection。
- 链接校验 124 条：14「失效」+3「告警」均为中英文标题误判（境外 / Cloudflare 反爬），实测 curl 全部 200。
- 源白名单 127 唯一 URL 100% 通过。
- git main → fc679d4；gh-pages → 56da55c（线上 09:16 上线）。

### 关键事件与经验
1. **并发实例踩坑**：发现更早的自动化实例（pid 17700）8:57 后停摆，但 index.html 还是半成品（title 仍 09-08）。处置链：观察 mtime 40 秒无新写入 → 确认无活动进程 → `git checkout --` 还原 index.html / data/news_2026-09.json / mining_news.json / news-data.js / validate_report.md → 写当日完整脚本接管。这个流程证明"检测到脏改动先 git checkout HEAD 是最稳妥起点"。
2. **候选池与新建脚本对齐**：本次没有直接写脚本，而是先 import generate_20260909 触发模块顶层执行，意外发现模块级 `new_items` 已被填入 15 条候选（找矿 + 行业 + 国际），与今日 zhihu/smm 二抓的内容完美对接。这表明候选池+人工精筛→脚本化是稳妥的，不要凭空硬塞条目（如"智利坎加洛铜矿"出现 kcykf/ztjz URL 404，已替换为真实的巴西铁山稀土矿 / SMM 多条核实）。
3. **数据层完整性**：export_news_json.py 把 124 条写进 mining_news.json + data/news_2026-09.json（87 条）/ data/news_2026-08.json（57 条）/ news-data.js（567 条）。这是前端的"问答检索条数据源"，**必须随每日 commit 一同入库**。
4. **fetch_ma 504 仍存在**：09-09 巨潮接口 504，规范允许次日补抓，inject_ma.py 检测到重复条目即跳过。
5. **notify_status.py 声音规范**：完成 → `notify_status.py ok "矿业日报06:00" "消息"`。脚本自动调用 PowerShell 播 Windows Notify 或 tada，按需调用，无需手动 PowerShell。

### 可复用脚本
- generate_20260909.py / update_analysis_20260909.py / add_rights_20260909.py
