# 矿业资讯速览 · 日报系统全面体检与优化清单（2026-09-26）

> 检查时间：2026-09-26 21:06 ｜ 基准 build `20260926-2031`（v11 已上线，main `cd84f71` / gh-pages `4af04eb`）
> 依据：REFERENCE.md §42 全站契约、§42.9 测试基线、§42.19 v11 交接、20260924 优化清单
> 性质：**只读审计**，未改任何线上代码；下列为"值得优化的内容"分级清单。

## 一、结论先行

- **v11 公司模块经代码级复查无回退**：折叠逻辑（`closed = coGroupsClosed[key] && !hasActive` 实现"选中公司强制展开"）、折叠仅加 `hidden` 不移除节点（DOM 计数不变）、app.js 无硬编码 `146`、`test_company_section.js` 实测 **162/0** 全绿、暗色已读态覆盖由第 162 条断言锁死。模块本身**健康**，无需动。
- **最大可优化项是结构性债务，不是功能缺陷**：① 13 份 `generate_2026*.py` + 13 份 `update_analysis_2026*.py` 逐日整份复制（每份 24–31KB）；② 根目录 27 个 `test_*.js` + 9 个 `test_*.py`，大量 dated/一次性脚本；③ 公司模块的"重建安全"目前**只有被动保护**（靠生成脚本不碰 `#companySection`），无自动化闸门。
- **P2 一整批功能优化仍是开放状态**（跨区检索、新闻卡缩略图、滚动进度条、性能审计、数据广度、日历区块），来自 20260924 清单，未落地。
- **未发现 P0 级回归硬伤**（移动检索入口 B1/E1、清空二次确认 D3 等已知 P0 已在 09-24 批次落地）。

## 二、值得优化的内容（按杠杆排序）

### A. 结构性债务（最高杠杆，建议优先）

| # | 现状 | 风险 | 建议 |
|---|---|---|---|
| A1 | 根目录 13 份 `generate_2026*.py` + 13 份 `update_analysis_2026*.py`，每份 24–31KB，骨架高度同构，仅日期 + `BRIEF_DIGEST` 不同；`generate_common.py` 已存在但未承载全部稳定逻辑。生成脚本 `_replace_block` 仅重写 `priceCardsShfe`/`priceCardsLme`（已 grep 确认重建边界） | 改一处生成逻辑要手改当日文件；历史日副本冻结、无法统一修 bug；仓库噪声大、diff 假象多 | 抽"生成引擎"进 `generate_common.py`（或新 `gen_engine.py`），每日仅留**日期 + 当日 `BRIEF_DIGEST` 数据**，删除 12 份旧 `generate_2026*.py` 与 `update_analysis_2026*.py` 历史副本（保留最近 1–2 份作样本）。改动须在重建边界内、跑全量测试 + preflight 后部署 |
| A2 | 根目录 36 个测试（`test_*.js`×27、`test_*.py`×9），其中 `test_p02_visibility.js` / `test_p2_20260910.js` / `test_p3_20260910.js` / `test_ux_20260910.js` / `test_mobile_opt_20260910.js` / `test_qa_navtab_20260910.js` 等为 dated/一次性，已被后续大测试吸收 | §42.9「全量闸门 = 根目录全部 test_*」会让**过期测试拖慢全量跑、甚至与现行代码矛盾假 FAIL**，掩盖真回归 | 盘点哪些已被 `test_smoke_0908.js`/`test_company_section.js`/`test_mobile_ux_batch.js` 覆盖，将过期者移入 `archive/`（勿删，保留溯源）；维护「权威测试清单」与 §42.9 对齐 |
| A3 | 公司模块 v11 的"抗重建"靠 `generate_*.py` 不碰 `#companySection` 内联 `<style>`（§42.19 已 grep 确认），**但没有任何 preflight / 测试在每次重建后断言 v11 指纹存活** | 一旦某天 `generate_*.py` 改成整段重建（见用户待办③），或误改内联 `<style>`，v11 会在**次日 06:00 静默回退**，08:00 复验前用户已看到坏版 | 新增 **preflight 指纹校验**（仿 `check_price_unit_dedup`）：重建后 grep `index.html` 确认 v11 必留指纹——`.co-nav-g-h` 为 `<button>`、`.co-nav-g-body[hidden]` 规则、`co-title` 近黑/`co-summary` 中灰、文案无「按市值/知名度」「有内容」「最新动态」。落 `preflight_check.py` 或 `test_company_section.js` 静态契约段 |

### B. 已立项但 P2 未做的 backlog（来自 20260924 清单 §四）

| # | 方向 | 现状 | 优先级 | 红线/风险 |
|---|---|---|---|---|
| B1 | 跨区检索（新闻+公司+矿权一起搜） | 公司搜索已支持摘要匹配，但首页搜索仅限新闻流 | P2 | 矿权需接 `rightsType`；勿破坏现有搜索口径 |
| B2 | 往期「跳到某天」日期下拉/月份锚点 | 往期按日组折叠，无快速跳日 | P2 | 不与 `.digest-dtag` 日期口径冲突 |
| B3 | 新闻卡缩略图（16:9） | 纯文字卡，扫读效率低 | P2 | 须先确认数据源稳定给图；不得引外链追踪图；图片懒加载 |
| B4 | 长摘要统一句末截断 + 内联「展开全文」 | 公司模块已有，首页新闻卡未统一 | P2 | 勿碰简报 `BRIEF_DIGEST` 契约（§16） |
| B5 | 滚动进度条（1–2px，非发光） | 无 | P2 | 纯 CSS/JS，无发光 |
| B6 | 性能审计（F4） | `app.js` 430KB / `index.html` 676KB / `news-data.js` 346KB / `company_news.json` 185KB，单文件体量偏大 | P2 | 不得破坏 `__mdBootGrace` 健康判定；先量 LCP/CLS 再动 |
| B7 | 数据广度（F6） | 公司 52 家、矿权源增量 | P2 | 走 `fetch_company.py` 链路；⑤ 由并发会话推进，不重复 |
| B8 | 事件·数据日历区块（F7） | 区块已建、`EC_ENABLED=false` 默认隐藏（§42.16） | 已完成（待开放） | 恢复显示只改 `EC_ENABLED=true` 一行；勿与 `#expoMini` 口径打架 |

### C. 用户已自列的待办（直接承接）

| # | 项 | 现状核查 | 建议 |
|---|---|---|---|
| C1 | 两条每日 prompt 内联「146」零偏差重发 | 06:00 `5cdcdfff…` / 08:00 `21dba82b…` 内联值仍为旧 `146`，靠「以 §42.9 为准」兜底（用户 §42.19 已确认） | 若求零偏差：用 `automation_update` 的 view→解码→替换→再编码闭环整体重发（~10KB 转义风险，切勿打断每日链路）；**至少**在 prompt 顶部加一行「测试基线以 REFERENCE §42.9 为准（当前 162）」，降低日后误读 |
| C2 | 线上字节验收（Dr.COM 网关劫持） | 当前以 `git ls-remote` 远端 SHA == 本地推送 SHA 作「部署达成」替代证据 | 网关放行后用 `md_online_retry.py` 轮询确认 `build-version==20260926-2031` + `app.js?v` md5 前 8 + `CACHE_NAME` 同步；建议把该轮询做成一次性自动化，省去手动 |
| C3 | v11 静态 CSS 纳入生成脚本时的防护 | 当前靠「不重建」被动保护（= A3 风险源） | 一旦纳入：补 §42.19 必留指纹 + 同步两条 prompt + 启用 A3 的 preflight 闸门 |

### D. 仓库噪音与清理

| # | 项 | 建议 |
|---|---|---|
| D1 | 根目录遗留：`index.html.bak-0908`(443KB)、`update_analysis_20260912.py.bak-briefrefine`、`audit_2026-09-08.md`、`audit_report.html`、`coverage_audit_2026-09-07.md` | 移入 `archive/` 或删除（`mining-daily-优化清单-20260924.md` 保留，仍有参考价值） |
| D2 | `tmp/` 含 **927 个文件**（含 `co_cache` 24h HTML 缓存等） | 确认已 gitignore；加定期清理/GC，避免无限增长（`fetch_company.py` 的 `tmp/co_cache` 应有 TTL 清理） |
| D3 | 疑似遗留部署平台目录：`bprime/`(7)、`aliyun-fc/`(2)、`huawei-fg/`(2)、`scf/`(4)、`worker/`(5)、`netlify/`(3)、`legacy-redirect/`(2)、`old-link-notice/`(1) | 逐一确认是否仍接入每日 06:00 部署链路；不用的归档，避免误改牵连部署 |

### E. 性能体量（F4 细化）

- **现状**：`index.html` 676KB（含巨大内联 `<style>` + 内容）、`app.js` 430KB（单文件）、`news-data.js` 346KB、`company_news.json` 185KB。
- **建议（均 P2，先量化再动）**：
  1. 确认 Netlify/CF 已开 brotli/gzip（文本资源压缩比通常 3–5×）；
  2. 用真实 Chrome 探针量 **LCP / TBT / CLS**，定位首屏瓶颈（§42.28 已指出本机 headless 被环境管控，`--dump-dom` 零输出，需换真机或 `--headless=new`）；
  3. `app.js` 430KB 单文件既是解析成本也是维护成本，评估是否按区块（价格/公司/AI搜/简报）做**按需初始化**（模块已多为 IIFE，可延迟非首屏模块的执行，不动结构）；
  4. 首屏关键区（今日新闻 + 简报）优先渲染，矿权/公司/会展等 below-fold 可 `requestIdleCallback` 延后。

## 三、建议执行顺序

- **P0（先排雷，低风险）**：A3（加公司模块重建指纹闸门）—— 用最小成本把"被动保护"升级为"主动断言"，直接封堵用户待办③的失效路径。
- **P1（结构性减负）**：A1（生成脚本去重）+ A2（过期测试归档）；D1/D2/D3 仓库清理。
- **P2（功能与体验）**：B 系列按业务价值挑（B3 缩略图 / B6 性能 / B1 跨区检索 优先）；C1/C2 承接既有待办。

## 四、红线提醒（勿踩）

- 动 `generate_*.py` / 重建逻辑 → 必须跑全量相关测试 + preflight + bump `build-version`/`CACHE_NAME` + deploy，且**不得**触碰 `#companySection` 内联 `<style>`（除非同步 A3 闸门）。
- 动公司模块前端 → 须**新增断言**、勿改 §42.9 既有 146 项期望值；改 `@media`/网格断点须补**真实 Chrome** 探针。
- 勿复活已否决项（阅读模式、`#rightsTable`、发光/脉冲图标、简报「必看 N 条」、热门新闻榜、简报要点层、矿种维度 `#coFilters`/`.co-sec`）。
- 红涨绿跌（中国口径）、日期唯一来源 `.date-badge`、头部深蓝 `#1a3a5c` 细条（2026-09-26 撤销白底）均不可回退。

## 五、本次审计附带验证记录

- `node test_company_section.js` → **通过 162 / 失败 0**（与用户声明一致，v11 16 条断言全绿）。
- app.js grep：`.co-feed-name` 旧 `var(--fs-h3)` 已改 `calc(var(--fs-body)+3px)`；`.co-nav-g-h` 已为 `<button>`；无硬编码 `146`。
- `generate_20260926.py` grep：`_replace_block` 仅重写 `priceCardsShfe`/`priceCardsLme`，确认公司模块重建边界与被动保护成立（即 A3 风险真实存在）。

## 六、执行记录（2026-09-26 21:2x，P0/A3 已落地）

- **已交付**：`preflight_check.py` 新增 `check_company_v11(html_text, app_text)`，并在 `main()` 的 `sections` 注册为「公司模块 v11 指纹」。
- **闸门内容（13 子项）**：① index.html 内联 `<style>` 的 6 条 v11 CSS 指纹（标题三级层级 / 正文 -1px / `.co-feed-name` +3px / `.co-nav-g-body[hidden]` / 已读态 `--ink-400` + 暗色 `--ink-300`）；② app.js 折叠逻辑 3 标记（`<button class="co-nav-g-h">` / `toggleCoGroup` / `md_co_groups`）；③ app.js 文案红线 4 禁语（`按市值`/`知名度`/`家有内容`/`（最新动态）`）。
- **扫描边界**：CSS 指纹只扫 `index.html`（重建边界真身）；文案红线只扫 `app.js`（渲染源），**不扫整文件**——因 index.html 内联样式的**历史注释**本就含「按市值·知名度排序」字样，整文件禁语会误红。这与 `test_company_section.js:626`（`!/按市值|知名度/.test(ghTxt)` 只验渲染 DOM）口径一致、互为补充。
- **验证**：`python preflight_check.py` 在现行 build `20260926-2031` 上 **exit 0 / 全部通过**；另做负向测试——删 `.co-nav-g-body[hidden]`、删 `.co-title` 字号、在 app.js 复活 `按市值`/`家有内容` 均被精准判红，证明闸门非假绿。
- **契约落档**：§42.19 ③ 废弃项里"只被引用、从未枚举"的回退指纹㉓㉔㉕ 已写成具体内容并指向 `check_company_v11`；preflight 文档新增检查项 10。
- **未做（保持待办）**：未 bump build-version / CACHE_NAME（本次仅改 preflight 脚本，未动线上页面）；未改两条每日 prompt（待办 C1，可选）；未把 v11 CSS 纳入生成脚本（待办③的"若日后"分支——届时本闸门即生效拦截）。
- **影响评估**：低风险、纯增量；不改 index.html/app.js，故 `test_company_section.js` 162 项与 §42.9 基线不受影响；改动已纳入每日 06:00 重建后的 preflight 闭环（含自动化 `--fail-on-error` 默认 exit 1 守门）。
