# REFERENCE.md — 矿业日报自动化 查阅类规则外置

> 用途：三套自动化 prompt 已瘦身为「只保留红线 + 指向本文件」。agent 在涉及**白名单核验 / 7 桶分类 / 低价值公告剔除 / 境外信源硬门槛**时，用 Grep 查本文件对应节，不靠记忆。
> 红线（互斥锁协议、LME 口径、矿权单视图、前端自愈引信）**不在此文件**，仍在各自动化 prompt 内，须逐字遵守。
> 本文件只供 agent 查阅，不参与日报构建，勿 git add 到业务提交（属参考文档，可提交但非必需）。

---

## §1 信源白名单（23 域，严禁引入白名单外域）

白名单由 `source_whitelist.py` 强制校验；自动化只需运行 `PY source_whitelist.py --check-file index.html --fail-on-error`，**勿手工维护域列表**。下列供分类/排障时核对。

**国内（14）**
- ky.mnr.gov.cn（矿业权市场，只进 rightsSection）
- mnr.gov.cn / geoglobal.mnr.gov.cn（自然资源部及全球矿产系统）
- cgs.gov.cn（中国地质调查局）
- chinania.org.cn（中国有色金属工业协会）
- cnmn.com.cn（中国有色金属报）
- cngold.org.cn
- chinamining.org.cn
- zgkyb.com（中国矿业报）
- cninfo.com.cn（巨潮，上市公司公告）
- smm.cn（上海有色网）
- antaike.com
- ccmn.cn（长江有色；**mall./ad. 子域已拉黑，勿收**）
- szse.cn（深交所公告，巨潮备份链路）

**境外（9）**
- metal.com（含 news.metal.com，SMM 国际站）
- icsg.org / ilzsg.org / insg.org（铜/铅锌/镍 研究组）
- world-aluminium.org
- lme.com（伦敦金属交易所）
- mining.com（排除 /sponsored-content/、/joint-venture/、servedbyadbutler）
- kitco.com
- gold.org

**已禁（被墙/反爬/付费墙/不可达，勿收）**
reuters、bloomberg、usgs、mining-journal、fastmarkets、cochilco

---

## §2 新闻 7 桶分类（按内容，严禁按信源硬编码）

桶序（与 generate_YYYYMMDD.py 的 THEME_BUCKET 一致）：
💼矿权交易｜🔍找矿成果与勘查技术｜📜政策与监管｜📊市场与价格｜🏭行业动态｜🌐国际矿业动态｜💰并购与投资

**判定原则：按内容不按信源。** 易错边界：
- 海关总署进出口数据 → 📊市场与价格（不是 📜政策与监管）
- 法规宣贯/培训班类 → 📜政策与监管（不是「会议」）
- 国有无对价股权划转 → 🏭行业动态（不是 💰并购与投资）
- 无实质事件的宣传稿 → 🏭行业动态
- 找矿类突破/成果 → 🔍找矿成果与勘查技术（重要条目由前端打⭐战略徽章，不单独建「找矿」分类）
- 并购重组/资产收购转让/对外投资/重大合同中标 → 💰并购与投资
- 投产扩产/停产检修/产量业绩 → 归 💰或 🏭，按事件性质
- 覆盖要求：7 桶都要覆盖，不偏科；🏭占比 >45% 视为偏科需复查

**红线**：category/region 只由 fetch_news.py + classify_llm.py 写；export_news_json.py 已禁止展示层反向覆盖月库。

---

## §3 低价值公告剔除（采编阶段不收，勿进主列表/简报）

**不收（公司治理/信披类，无行业事件价值）**
业绩说明会、投资者关系活动、机构调研、持续督导意见/总结/现场核查、券商核查意见、法律意见书、三会决议、独董换届/声明、异常波动、停复牌、权益变动、减持/增持计划、问询函/关注函/监管函回复、更正/补充公告、召开会议通知、募集说明书/保荐书/评级报告等常规融资流程文件。

**可收（有实质行业事件）**
并购重组、资产收购转让、对外投资、重大合同中标、投产/扩产/停产检修、产量业绩（归 💰并购与投资 或 🏭行业动态）。

> 简报「政策与产业」节须 `drop_notice=True` 走 LOW_VALUE_NOTICE，自动剥离上述治理类。

---

## §4 境外信源硬门槛（收录前必过）

1. **可达性**：收录前 `curl -sL -m15 -A "Mozilla/5.0" <url>`，HTTP 非 000 且正文非空且能取 `<title>` 才收；curl 报 size=0 以 http_code 为准，必要时 python 复测。
2. **已禁域**（见 §1）：reuters/bloomberg/usgs/mining-journal/fastmarkets/cochilco 一律不收。
3. **处理规范**：中文意译术语 + 2–3 句摘要 + 保留英文原题；美元/吨附 ≈元/吨，1oz≈31.1035g；排除 mining.com 的 /sponsored-content/、/joint-venture/、servedbyadbutler；涉华内容只陈述事实；同事件境内外只留 1 条；统一北京时间。
4. **广告清除**：纯广告招商不收，有实质内容可收。

---

## §5 会话协作与上下文卫生（2026-09-11 结算新增）

> 本节是**协作方式**约定，不是日报业务规则；与 §1–§4 同属"查阅而不靠记忆"的外置知识。平台级偏好另存于 `C:\Users\中铝矿业投并部\.workbuddy\MEMORY.md`。

### 5.1 上下文模型（先记住这一句）
**对话上下文是易失的，文件才是持久的。**

- 每次新对话 = 一个全新的 `C:\Users\中铝矿业投并部\WorkBuddy\<日期时间>\` 目录，**上下文从零开始、不继承**（目前已有 29 个这类时间戳目录）。
- 真正持久的只有：①本目录 `mining-daily` 下的文件；②用户级 `~/.workbuddy/MEMORY.md`。
- **术语已变（5.5.6）**：左侧边栏那个入口叫「**项目**」，不再是"空间"；它是云端的**多人协同容器**（详见 §5.5），**不是**本地工作目录。
- 实测差异：**新建任务 = 新建一个时间戳工作目录**（`WorkBuddy\<yyyy-mm-dd-HH-MM-SS>`，1 会话/目录、目录之间不共享上下文）；**新建项目不改工作目录**。
- 正确结构 = **固定一个工作目录（如 `mining-daily`）+ 在其中反复新建任务**；项目只在"要拉人一起干"时才建。
- **单人使用场景（用户 2026-09-11 确认：这个项目就他一个人做，不协作）→ 不建项目，只走「新建任务」**。建任务时在「**任务启动于：**」处手动选 `C:\Users\中铝矿业投并部\mining-daily`（另有「选择工作空间／选择目录」入口；默认路径可在设置「默认工作空间存储路径」改）。⚠️ **同一目录 ≠ 继承对话上下文**：即便 cwd 相同，新会话上下文仍从零开始，开场仍须照 §5.3 贴交接小结。

### 5.2 新建任务的触发条件（目标换了就切，不是卡了才切）

| # | 观察到的信号 | 动作 |
|---|---|---|
| ① | **目标切换**（如从"改版式"变"修数据源"） | 立刻切，哪怕对话很短 |
| ② | 产物已交付并稳定（日报已生成并同步线上） | 收工结算，开新 task |
| ③ | 工具调用累计约 **60 轮** / 来回 30+ 轮 / 跨 **2 天以上** | 强制结算 |
| ④ | 体感变慢（几秒 → 十几秒、反复"思考中"） | 立刻结算 |
| ⑤ | **红线信号**：开始用废弃脚本、复活已删组件（如 `#rightsTable`、显示切换按钮）、违反 category/region 写入约定 | **立刻停、立刻切** |
| ⑥ | 你在重复解释早已说过的约定 | 约定该沉淀进文件 → 沉淀 + 切 |

> **⑤ 对本项目最实用**：一旦出现，说明上下文里新旧混杂、自动压缩已把红线丢掉，别再往下聊。

### 5.3 结算 / 交接模板

- **结算口令**（task 结束时对 agent 发）：见速查卡 `C:\Users\中铝矿业投并部\Desktop\任务交接速查卡.md`。
- **新 task 开场**：贴交接小结 + "按 `C:\Users\中铝矿业投并部\mining-daily\REFERENCE.md` 执行。本次目标：<一句话>。"
- **人工对话也套用自动化已有的节流规则**：约 **12 轮**做一次摘要压缩、长日志用 `runq.py` 落盘只回传 ≤1800 字、禁止整读 >50KB 文件、需要权威清单就 **Grep 本文件**而非凭记忆。

### 5.4 平台机制事实（已实测，勿再反复怀疑）

- 自动压缩（compact）在 token 约 **90%** 时触发，**同对话内、不丢历史**；`~/.workbuddy/settings.json` **无**可调阈值项。
- 磁盘会话 `.jsonl` 每轮全量写，可涨到 **200MB+**，**压缩清不掉**，属平台层限制 —— 这是"长任务拆成多个 task"最稳的根本原因。
- **无"消息级收藏"**；替代方案：**置顶任务**（任务行 ⋯ / 右键 → 置顶）、保存到工作空间、归档、搜索筛选。

### 5.5 「项目」到底是什么（2026-09-11 实测，WorkBuddy 5.5.6）

**一句话：项目 = 云端多人协同容器，与本地工作目录无关。**

| 维度 | 项目（左侧边栏「项目」→「+ 新建项目」） | 任务（「新建任务」） |
|---|---|---|
| 本质 | 云端协作容器（代码 i18n 命名空间 `collab.*`） | 一次会话 = 一个**新时间戳工作目录** |
| 能做什么 | 邀请/审批成员、绑定连接器、上传 Skill 到项目、项目内任务转交（handoff）、改名/归档/删除 | 干活；产物落在该目录 |
| 配额 | 体验版 **5** 个（`PROJECT_QUOTA_LIMITS`：体验 5／标准 10／高级 15／旗舰 20／企业 100；超限报 ecode 17260） | 无上限，但目录无限堆积 |
| 会改工作目录吗 | **否** | 每次都换新目录 |

实测证据（2026-09-11 23:40）：
- `~/.workbuddy/workbuddy.db` 的 `sessions` 表：**45 个会话 `project_id` 全为空**；按 `cwd` 分组，16 个会话共用 `C:\Users\中铝矿业投并部\mining-daily`，其余 29 个目录各只 1 个会话。
- 本地 `WorkBuddy\` 下 30 个目录（29 个时间戳 + `Claw`），即历次"新建任务"的产物。
- 项目页"我的项目"两张卡：「矿业新闻日报」（建于 23:35）、「项目新手指引」（1 天前）。

结论：**别用"新建项目"来攒上下文**（它攒不了）；只有当"要拉同事一起用日报/石鉴"时，项目才是对的工具。

---

## §6 废弃项（勿再使用）

| 废弃项 | 说明 | 替代 |
|---|---|---|
| `C:\Windows\Temp` 作为临时目录 | 非管理员账户 ACL 拒绝访问（沙箱内外均 `PermissionError 13`）；且命令里出现该路径字面量会被记进 audit-log 制造 EPERM 噪音 | 一律用 `%TEMP%`（`C:\Users\中铝矿业投并部\AppData\Local\Temp`） |
| "跨任务保留项目记忆"的说法 | 实测**不成立**：新对话上下文从零开始 | 靠文件持久（本文件 + `~/.workbuddy/MEMORY.md`） |
| "新建项目没必要"的说法 | 部分错误：项目**可重命名/归档**，且能建多个 | 见 §5.5：项目=协作容器，**要拉人一起干时才建**；日常收工靠"固定目录 + 新建任务" |
| 每 4 小时"长对话提速提醒"自动化 `adf619e6` | 只能响一下，治不了结构性问题 | 按 §5.2 触发条件切 task（**待用户确认后删除/暂停**） |
| 已删前端组件 `#rightsTable`、显示切换按钮 | 勿复活（口径以各自动化 prompt 红线为准） | 现行前端单视图 |
| 简报「单条≤80字（句号截断）」与 `update_analysis_*.py::trunc80` | 2026-09-11 用户否决：36 条里 35 条被切在句中（如「HVLP4 代铜箔实…」） | 同日改用完整摘要；**2026-09-12 三次修订再改为「逐条撰写的精炼句」（≤80 字，不是截断）见 §16** |
| 简报单条＝`news.summary` 原样搬运（`fmt_bullet(max_len=0)` / `to_items()`） | 2026-09-12 三次修订：18 条 / 4184 字、平均每条 232 字，与下方新闻列表同源 | §16 `BRIEF_DIGEST` 精炼句（≤80 字/条） |
| 简报每节＝该类目全部 `is_new`（`recent_items(limit=0)`） | 同上：条数与长度双失控 | §16 精选（条数 < 当日新增）+ 单条 ≤80 字；`limit=0` 仅留作兜底 |
| 简报前端显示「今日收录 N 条」 | 与侧栏「今日新增」口径不同（实测 36 vs 32），并列显得数据打架 | `briefSub` 固定「按分类摘要」 |
| 「今日要闻」区的 `#digestDate`（渲染「2026.09.11 星期五」） | 2026-09-12 用户判定**属重复日期**：与头部红底 `.date-badge`「2026年09月11日 星期五」是同一天 | 已删除（元素 + `.digest-date` CSS + `app.js` 填充代码）；非当日发布的条目仍由 `.digest-dtag` 单独标注 |
| 「政策与产业」节只喂 `行业动态` | 2026-09-12 修正：节名里的「政策」无对应内容，名不副实 | 两源合并：`政策与监管` + `行业动态`（先政策后产业，各类目内按发布日期倒序） |
| 简报每节 `recent_items(limit=4)` 硬上限 | 2026-09-12 用户要求「连条数也全」：行业动态 9 条只出 4 条、找矿 6 条只出 4 条 | `limit=0`（默认全量）；前端 `setupBriefClamp()` 420px 折叠 +「展开全部（N 条）」兜底 |
| 阅读模式整套：`body.reading-mode` / `#readingToggle` / `#readingExitBar` / `.reading-toggle` / `.reading-exit` / `toggleReadingMode()` / `restoreReadingMode()` | 2026-09-11 用户判定价值不大，已彻底删除 | 无（勿复活；`test_ux_20260910.js` ② 段已锁死） |
| 简报条里的「（原题：英文标题）」 | 中文摘要夹英文是噪音 | 生成器自动剥离（英文原题仍在新闻卡片保留） |

---

## §7 未完成事项与下一步（截至 2026-09-11 23:50）

1. **[待确认] 删除或暂停提醒自动化 `adf619e6-1639-46e5-a9cc-75b8a0a7d9ae`**（每 4 小时一次），用户已表示"没那么合理"。
2. **[需用户手动·管理员] 清理 `C:\Windows\Temp\md_*.js`**：agent 无权限列/删；需管理员 PowerShell 先 `dir C:\Windows\Temp\md_*.js` 确认，再 `del C:\Windows\Temp\md_*.js`。注意：只清文件，**不减少 `~/.workbuddy/audit-log` 已写盘的历史噪音**。
3. **[已澄清 2026-09-11 23:45 · §5.5] 29 个时间戳目录**：它们是"新建任务"的**必然产物**（每任务一个新目录），**不是**可整理的"空间"；**不要**靠"新建项目"去收敛它们（项目不改工作目录）。日常做法：工作固定落在 `mining-daily` 目录，其余时间戳目录按需清理即可。
4. **[待决策 2026-09-11 23:55] 已建的「矿业新闻日报」项目**：用户明确"就自己一个人做、不协作" → 项目的全部增量价值（成员/共享 Skill/任务转交）用不上，且占用体验版 5 个配额之一。**建议归档**（项目卡 ⋯ → 归档），日常一律走"新建任务 + 手动选 `mining-daily`"。
5. **[可选] 把"结算口令"做成单词快捷指令**，省得每次翻速查卡。
6. **[已完成·本项目外]**：`~/.workbuddy/artifact-index/f2f418e9-1531-4aff-9c33-b6b1f99dd5d5.json` 中 3 条指向 `C:\Windows\Temp` 的死引用已删除（58→55），备份在 `%TEMP%\artifact-index-f2f418e9.bak.json`。
7. **[已解决 2026-09-12 · §10.1] 简报每节仍上限 4 条**：用户定「连条数也全」→ `recent_items` 默认 `limit=0`（全量，不再限量）；单条也早已不截断（§6 / §9.2.5）。
8. **[已解决 2026-09-12 · §10.2] 「政策与产业」节由 `行业动态` 喂数**：用户选「两源合并、节名不变」→ 数据源 = `政策与监管` + `行业动态`（先政策后产业，各类目内按发布日期倒序），`drop_notice=True` 仍生效。
9. **[已解决 2026-09-12 · §10.3] `digestDate` 属重复日期**：用户确认属重复 → 已删除（元素 + `.digest-date` CSS + `app.js` 填充代码），非当日条目仍由 `.digest-dtag` 标注。
10. **[已完成 2026-09-12 00:25 · commit `19f6480`] 本文件已提交并推送**：含上一会话 §5–§7 与本次 §6/§7 追加 + §8/§9，均已入版本库。当时为免带走另一会话正在改的 `morning_report.json` / `update_analysis_20260911.py`，故单独一个 commit（只含 REFERENCE.md，+142 行）。

11. **[已解决 2026-09-12 · §16] 简报「展开后仍然太长」**：用户反馈「3500 多字太多，只要关键信息」→ 定夺「精炼单条·保留全貌 + 剔除例行条目 + 立即重做当日」→ 条目改逐条精炼句（≤80 字），实测 **16 条 / 1057 字**（原 18 条 / 4184 字，-75%）。

---

## §8 本次对话达成的结论（2026-09-11 21:15–00:10）

> 本轮四次改动均已上线并核对线上字节。build 演进：`20260911-1512` → `20260911-2258` → `20260911-2323` → `20260911-2347`。

### 8.1 加载横幅误报（Task C / D，build 1512 / 2258）

- **现象**：健康页面每次刷新先闪一下红条（C），修完又变成琥珀「部分区块未加载（热榜）」（D），几秒后自动消失；且横幅自身诊断行写着 `区块 热榜:OK … 错误0条`，自相矛盾。
- **根因（两轮同源）**：把**正常加载窗口里的瞬时态**当成了故障。
  - ① `mdDegraded()` 见 `!__mdAppEvaluated` 就判「app.js 未执行」，而 1.2s 自愈轮恰好跑在 app.js 的正常加载窗口内（defer + 内容指纹脚本）。
  - ② `fetchHotNews()` 是**异步**的：先 `fetch('api/hot-news')`，静态站 404 后走 `.catch` 回落本地计算才渲染 DOM；1.2s/3s 自愈轮看到 `mdOk('hotListBody')` 仍为 false。
- **结论**：任何依赖网络/异步渲染的健康态都必须给**宽限期**——`__mdBootGrace`(10s) 门控整页降级判定、`__mdRegionGrace`(10s) 门控区块判定；两者均 < 12s 看门狗，真实故障仍会报出。

### 8.2 桌面顶部优化（Task E，build 2323）

- **阅读模式整个删除**（用户："意义不是很大"）：CSS 块（`.reading-toggle` / `body.reading-mode …` / `.reading-exit` 及其媒体查询）、44px 触控项、`#readingToggle`、`#readingExitBar`、`toggleReadingMode/restoreReadingMode`、Esc 监听、`mdSafeStep('restoreReadingMode')`。`test_ux_20260910.js` 原 ② 段 12 条「存在」断言**改写为 7 条「已移除」断言**，把删除固化成回归锁。
- **头部纵向收窄**：`.header` padding `var(--s5) var(--s5)`（上下 24px）→ `var(--s4) var(--s5)`（上下 16px）；`.header-actions` 定位 14px→12px 同步内收。
- **日期去重**：保留头部 `.date-badge`（红底、最显眼、即当天日期），删掉简报 `#briefDate` 的「数据日期 …」span 及 `app.js` 的填充代码。

### 8.3 今日简报口径（Task F，build 2347）

- **截断真相**：`update_analysis_*.py::trunc80/fmt_bullet` 硬截 **80 字**，cut 内找不到「。」就直接补「…」→ 36 条里 **35 条**被切在句中（摘要中位 172 字、最长 312 字）。规格出处是 **06:00 自动化 prompt §11.8**「单条≤80字（句号截断）」—— 只改代码、不改 prompt，次日必复现。
- **计数真相（非 bug）**：`morning_report.stats.new_count=36`（生成时纳入当日的**全部** `is_new`）≠ 页面「今日新增」**32**。差额 4 ＝ **3 条会展条目**被前端移入 `meetingSection`（2026中国国际矿业大会／中国国际铜业论坛／有色行业"双碳"大会）＋ **1 条旧闻**（09-08，>2 天）被 `demoteStaleNew()` 降级「补录」。子分类 6+2+12+6+3+3=32 与 `newCount`/`tocTodayCount` 一致；今日区共 34 条 = 32 新增 + 1 补录 + 1 矿权结果摘要。**两者本就不同口径，不该相等。**
- **处置**：单条改完整摘要（不截断、剥「（原题：…）」）；简报**不再显示条数**（`briefSub` 固定「按分类摘要」），条数统一由侧栏/统计条呈现。

---

## §9 新确立的约定 / 红线（2026-09-11）

### 9.1 前端行为

1. **横幅宽限**：`__mdBootGrace`(10s) 门控 `mdDegraded()` 的「app.js 未执行」判定；`__mdRegionGrace`(10s) 门控 `mdStuckRegions()` 整体。今后新增任何"异步/网络依赖"的健康态，必须同步给宽限。
2. **阅读模式已废**（见 §6）：见 `body.reading-mode` / `#readingToggle` / `#readingExitBar` 即为回退，`test_ux_20260910.js` ② 段会立刻失败。
3. **简报 `briefSub` 固定显示「按分类摘要」**（不出条数）——2026-09-12 二次修订后如此（见 §15；当天早些时候曾短暂改为「必看 N 条」，**已否决，勿恢复**）。**仍禁止**拼侧栏口径的 `今日收录 N 条`（口径不同，见 §8.3）。简报内**各节条数**由前端从 `brief_sections` 渲染（节标题徽标），属简报自身口径，可以出。
4. 头部日期以 `.date-badge` 为唯一来源：简报不再另写「数据日期」（`briefDate` 已删），今日要闻的 `digestDate` 也已于 2026-09-12 删除（§10.3）；非当日条目用 `.digest-dtag` 单独标注。见 `body.reading-mode`/`#readingToggle`/`#briefDate`/`#digestDate` 即为回退。

### 9.2 数据 / 生成

5. **简报单条＝完整摘要，不截断**：`fmt_bullet` 默认 `max_len=0`；仅显式传 `max_len>0` 时按句末标点（。！？）截断，**绝不在句中硬切**；自动剥掉行尾「（原题：…）」。**⚠️ 2026-09-12 三次修订后本条对简报已不适用**：简报条目改由 `BRIEF_DIGEST` 逐条撰写（≤80 字），不再搬运 `news.summary`，见 §16；`fmt_bullet` 仅存于 report 兜底路径。
6. `stats.new_count`（收录口径）与页面「今日新增」（实时新鲜口径）**不必相等**，且通常 收录 ≥ 新增（差额＝移入会议专区的会展条目 ＋ 降级「补录」的旧闻）。**不要**为了让两者数值相等去改数据。
7. 只改 `morning_report.report` 的稳妥做法：备份 4 个分析 JSON → 跑修好的生成器 → 只取新 `report` 覆盖回原文件（保住 `updated`/`stats`/`sections`）→ 其余 3 个 JSON 从备份还原（避免 `NOW` 时间戳漂移）；最后 diff 确认**仅 bullet 文本**变化。
- **⚠️ 本条已被 §16 取代（2026-09-12 三次修订）**：简报**不再**取该类目全部 `is_new`，改为「精选 + 逐条精炼（≤80 字）」——因为用户看到的上线效果是「展开后 4184 字、平均 232 字/条」，证明「长度问题全交给前端折叠」不够。`recent_items(limit=0)` 降级为**兜底路径**（某节未撰写时取前 3 条自动截句）；前端 420px 折叠（§15）继续作为展示层第二道保险。原文「简报每节＝该类目全部 is_new / 不在数据层砍内容」**已作废**。
- **「政策与产业」= `政策与监管` + `行业动态` 两源**（2026-09-12 新增，§10.2）：先政策后产业，各类目内按 `orig_date_full` 倒序，`drop_notice=True` 仍生效（见 §3）。**不要**退回单类目喂数——只喂「行业动态」则节名里的「政策」没有内容，只喂「政策与监管」则产业面内容从简报消失。
- **简报须产出 `brief_sections`（必须）**（2026-09-12 新增；**三次修订后的契约见 §16**）：五节结构化、**空节不收录**、每节 `count==items.length`；**`t` = 精炼句（≤80 字、逐条撰写，非 `news.summary` 搬运）**；缺失时前端静默回退旧 markdown 渲染（页面不报错，但节条数徽标与条目跳转都没了，属**静默回退**）。`highlights` 生成端仍产出但**前端已不渲染**（用户否决要点层：与「今日要闻」重复），**不作为复核项**。`report` 保留作兜底。

### 9.3 流程 / 工程

8. 改 `index.html` 必 bump `build-version`；**手改主树 `sw.js` 的 `CACHE_NAME` 再跑 preflight**（`deploy_pages.py` 虽也会同步，但它在推 gh-pages 时才改，会卡在 preflight 闸门）。
9. **行尾差异**：`index.html` / `app.js` 是 **LF**，而 `test_ux_20260910.js` 是 **CRLF**。批量替换脚本先 `repr()` 看行尾——按 `\n` 拼的多行串在 CRLF 文件上会匹配 0 次，须改按「行索引区间替换 + 保留 `\r`」。
10. **提交只 add 本次实际改动的文件**：他人/其他会话未提交的无关改动（如 `REFERENCE.md`）不要顺手带进 commit。
11. **改生成侧功能必须同步 06:00 与 08:00 两条自动化 prompt**，否则次日复现。历轮已同步：§11.8 取消 80 字截断、§11.8b 禁止把「今日收录 N 条」加回 `briefSub`、§11.10 加"无关改动别带进 commit"、§11.8c 每节全量 + 政策与产业两源、**§16 简报改精炼句（≤80 字）+ 剔除例行条目（2026-09-12 三次修订）**。
12. **线上验收必须实抓字节**（`urllib` 带 `Cache-Control: no-cache`），不能只看脚本日志；GitHub Pages 有 30–70s 延迟，首读旧属正常，要重试（本轮还遇到过代理 502）。
- **jsdom 不实现 `fetch`**（2026-09-12 实测）：直接用 `JSDOM.fromURL` 验简报会拿到「morning_report.json 不可用，简报区保持隐藏」，简报永远渲染不出来。验证简报要在 `beforeParse(w)` 里把 Node 的 `fetch` 桥进 window（`w.fetch=(u,o)=>fetch(new URL(String(u),url).href,o)`），并用本地 `http.server` 起静态服务（file:// 下也不行）。实测这样能拿到 `briefMain li` 的真实条数。
- **判定「测试失败是不是我改出来的」**：把 HEAD 导到临时目录（`git archive HEAD | tarfile`）跑同一测试对比退出码，比凭记忆争论快且准（2026-09-12 用此法确认 `test_price_enhance.js` / `test_ready_state_tdz.js` 为既有失败）。

---

## §10 本次对话结论（2026-09-12 00:16–00:4x，build `20260912-0024`）

> 本轮把 §7 的 7 / 8 / 9 / 10 四条待办一次做完，均由用户当面拍板。build `20260912-0024`，main `61c3f0f`（业务）+ `968023e`（本文档）已推送，gh-pages `0a54cd4`，线上实抓字节已核对通过。

### 10.1 简报每节改为全量（不再限 4 条）

- 改动：`update_analysis_YYYYMMDD.py::recent_items` 默认 `limit=0`（全量），原 `limit=4` 会让「行业动态」9 条只出 4 条、「找矿」6 条只出 4 条。
- 依据：前端 `setupBriefClamp()` 已有 420px 折叠 +「展开全部（N 条）」，放全不会把价格区顶到屏幕外 → 长度问题在展示层解决，不在数据层砍内容。
- 实测（jsdom + 本地 http + fetch 桥接）：`briefMain li = 24` = 行情 2 + 政策与产业 12 + 勘查与技术 6 + 并购与投资 3 + 矿权 1。

### 10.2 「政策与产业」改为两源合并

- 改动：`recent_items('政策与监管', drop_notice=True) + recent_items('行业动态', drop_notice=True)`，**先政策后产业**，各类目内按 `orig_date_full` 倒序。
- 09-11 实测分布：政策与监管 3 + 行业动态 9 = 12 条（此前只有行业动态 4 条）。`drop_notice` 保持 True（§3）。

### 10.3 删除 `digestDate`（判定为重复日期）

- 删除三处：`index.html` 的 `<span class="digest-date" id="digestDate">`、两条 `.digest-date` CSS（亮/暗）、`app.js::renderDigest()` 的填充代码（含已无用的 `week` / `dt`）。
- 头 `.date-badge`（红底）保留为唯一日期来源；要闻条非当日发布时仍由 `.digest-dtag` 标注，信息不丢。
- 实测：jsdom 下 `#digestDate` = null、`.digest-date` 节点 = 0、`digestList li = 4` 正常。

### 10.4 工程观察

- **并发会话**：本轮进行中，另一会话于 00:25 / 00:28 提交并推送了 `19f6480` / `680c24c`（只动 `REFERENCE.md`），远端与本地一度同时前进。结论：**同一 `mining-daily` 目录别开两个会话同时改**，至少不要同时提交；提交前先 `git log --oneline -3 origin/main` 看远端是否被别人推过。
- **既有失败（非本轮引入）**：`test_price_enhance.js`（① 组 3 条，今日异动全为下跌、只有锌一条进条）、`test_ready_state_tdz.js`（「app.js 末行是求值完成信标」——实际信标在第 5 行倒数位置，末行是 `mdSyncBanner` 调用）。两者在 HEAD 上同样 exit=1。要不要修属新决策，本轮未动。

---

## §11 移动端 UI 优化（2026-09-12 01:0x，build `20260912-0102`）

> 用户三点诉求：①顶部分类栏排版 ②底栏「问」图标要体现搜索＋AI（要看参考案例后定夺）③其余待优化项。
> 本轮只做 ①②（③ 已实测定位、待拍板）。main `0405dd0`、gh-pages `55d4a44`，线上字节已核对通过。

### 11.1 顶部分类栏改四等分铺满（①）

- 根因：`.mctab` 原为 `flex:0 0 auto`（宽度＝文字宽），4 个 tab 只占屏幕左侧约 1/3，右侧大片留白、视觉重心偏左。
- 改动（`index.html` 移动端块）：`.mctab` → `flex:1 1 0` 四等分铺满；字号 14px → `var(--fs-h2)` 16px（回到字号体系，非野值）；`.mctab.active::after` 下划线改居中定宽 24px（避免整格通栏看起来像分隔线）。
- 实测（真实 Chrome headless 探针，390/360/320）：`fill=100%`，每格 87.8 / 80.3 / 70.3，`h=41`，无横向溢出。

### 11.2 底栏「问」→「AI 搜」双语义图标（②，用户定夺「方案 A」）

- `app.js::mdMobileTabBar()` 的 `SVG_QA`：空心对话气泡（`M4 5h16v11H9l-5 4V5z`）→ **放大镜**（`circle cx=9.5 cy=12 r=5.5` ＋手柄 `M13.4 15.9 18.3 20.8`）＋**四角星芒**（`M17.6 3.2 18.66 6.14 21.6 7.2 18.66 8.26 17.6 11.2 16.54 8.26 13.6 7.2 16.54 6.14Z`）。
- 星芒 `stroke-width="1.7"`（主图形 2）：22px 实际渲染下细一号才不糊成一团。
- 文字标签 `问` → `AI 搜`；`MD_BRAND_NAMES.qa` 同步为 `AI 搜`；补 `aria-label="AI 搜：新闻检索与问答"`。
- **改标签必须同步改断言**：`test_qa_navtab_20260910.js:54` 原断言 `qaBtn.textContent.trim() === '问'`，不改必红（本轮已随之更新）。
- **约束（不可回退）**：`test_mobile_ux_batch.js:77-78` 要求 `.mtab[data-go="qa"]{color:var(--brand)}` 存在、且禁止 `qaOrbPulse` 渐变发光球 → 新图标必须**单色描边**（`currentColor`），不得用渐变/发光/脉冲。
- 该图标最初采用顺序：用户否掉「空心气泡＋问」（无搜索/AI 语义）；历史上还否掉过「渐变发光球」。

### 11.3 实测定位、尚未处理的三项（③，待用户拍板）

1. **移动端顶部搜索按钮是死代码 → 首页检索条无入口**：`index.html:1484` 顶层 `.md-search-btn{display:none}`（本意"桌面隐藏"）在**源码顺序**上晚于 `:1458`（`@media(max-width:768px)` 内的 `display:inline-flex`），同特异性 → 前者永远赢。实测三档视口均 `searchBtn display=none w=0`。而 `mdOpenSearch()` 只挂在 `#mdSearchBtn`（`app.js:2557`）→ **移动端首页的抽屉式检索条 `#newsFilterBar` 没有任何入口能打开**。修法二选一：①把 `:1484` 改写成 `@media(min-width:769px){…}` 恢复图标；②删死代码，检索能力统一收进 `#qaFloat`（面板内已有「检索」＋「AI」双按钮）。**这正说明「AI 搜」tab 是移动端唯一检索入口，图标必须同时承载两种语义。**
2. **≤360px 品牌行日期被截断**：`.md-date` 需要 127px，实测可用仅 99.5px(360) / 59.5px(320) → 320px 上「2026年09月11日 星期五」只能看到「2026年09」。建议窄屏换短格式（如「09-11 周五」）。
3. **「问」常驻品牌色，稀释"当前位置"指示**：`body` 级 `.mtab[data-go="qa"]{color:var(--brand)}` 与 `.mtab.active` 同色，首页激活时两个 tab 同时是品牌色。若改需同步改 `test_mobile_ux_batch.js:77` 的断言。

### 11.4 本轮新增的工具经验

- **不开浏览器量移动端几何**：`%TEMP%\md_probe_mobile.py` —— 本地 `http.server` 托管项目根，探针用 iframe 按给定 CSS 宽度加载 `index.html`，等 `#mdTop`/`#mobileTabBar` 注入后逐档量 `getBoundingClientRect`/`getComputedStyle`，结果写入 `<pre id="out">`，再用 `chrome --headless=new --dump-dom` 读回。用法：`python md_probe_mobile.py "390,360,320"`。**比截图更精确**（且当前模型不能读图，截图路线走不通）。
- **断言要排除注释**：验收"旧图标已消失"时，`OLD_PATH not in js` 会被自己写的注释（"替代了原气泡 M4 5h…"）判为假 → 先按行剔除 `//` 开头行再断言。
- **沙箱下推送必须由用户批准**：`~/.ssh` 属受保护路径，`git push` 在沙箱内一律 `Can't open user config file …/.ssh/config: Permission denied`。脚本 `%TEMP%\md_push_deploy.py` 按技能 `ssh-push-under-sandbox` 写（`GIT_SSH_COMMAND` 内路径**全用正斜杠**，否则 git 走 `sh -c` 会把反斜杠吃掉）。**首次申请被用户拒绝时不要自行重试**，先问用户；用户批准后同会话内不再询问。

## §12 移动端顶栏精简（2026-09-12 08:5x，build `20260912-0852`）

### 12.1 用户决议与落地

用户配三张手机截图提三点要求：① 首页取消顶栏「历史记录 / 收藏」两个按钮并**重排该行内容**；② 价格页同样取消两钮、把「价格」标题**居中**；③ 矿权页同样取消两钮、把「矿权」标题**居中**。

- `app.js::mdMobileTopTabs()`：删掉 `#mdFavBtn`/`#mdHistBtn` 两个 `<button class="md-fav-btn">` 及其红点 `<span class="md-badge">`，以及两个 click 绑定（原逻辑是点了就切 `body[data-filter-mode]`）。**入口未丢**：底部「我的」面板 `#mineSheet` 内仍有 `data-act="fav"`（★ 我的收藏）与 `data-act="history"`（🕘 浏览记录）。
- `mdUpdateFavBadges()` 退役为空实现 `function mdUpdateFavBadges(){}`——调用点（收藏点击、`storage` 变更）仍在，删函数会留死调用。
- `index.html`：`.md-top-brand` 由 `align-items:baseline` 改 `center` 并加 `min-height:36px`（否则移除 44px 圆钮后品牌行会塌成单行文字）；`body:not(.md-hide-catbar) .md-top-brand{justify-content:space-between}`（首页＝品牌左 / 日期右）；`body.md-hide-catbar .md-top-brand{justify-content:center}`（非首页分类栏与日期都隐藏，只剩 tab 名 → 居中）。
- 死 CSS 清理：删 `.md-fav-btn{…}` / `.md-fav-btn:active` / `.md-fav-btn svg` / `.md-badge{…}` / `.md-badge.show`；从 `@media(max-width:1100px)` 的两份 44px 触控热区清单里去掉 `.md-fav-btn`；`DESIGN.md` 的 pill 控件族举例同步去掉。
- build `20260912-0607` → `20260912-0852`（`sw.js` 的 `CACHE_NAME` 同步）。

### 12.2 实测数据（真实 Chrome 无头探针，四档视口）

| 视口 | 首页 mdTop 高 | 分类栏 fill | 日期 x | 日期截断 | 价格页 mdTop 高 | 标题居中偏差 |
|---|---|---|---|---|---|---|
| 390 | 92 | 100% | 236 | 无 | 47 | 0px |
| 360 | 92 | 100% | 206 | 无 | 47 | 0px |
| 320 | 92 | 100% | 166 | 无 | 47 | 0px |
| 414 | 92 | 100% | 260 | 无 | 47 | 0px |

- 四档视口下 `.md-fav-btn` 数 = 0、`.md-badge` 数 = 0；价格 tab 下 `date display=none`、`catBar display=none`。
- **顺带修掉 §11.3 遗留问题②**：原 ≤360px 品牌行日期被截断（`scrollW=127 > clientW=99.5/59.5`）——移除两个 44px 圆钮正好腾出所需宽度，320px 下也完整显示，无需再做短日期格式。
- 首页 mdTop 由 99px → 92px；价格/矿权页 mdTop = 47px（细长的单行标题栏）。

### 12.3 测试与闸门

- `test_mobile_opt_20260910.js` ③④⑤ 断言随设计**翻转**：原"按钮/红点存在"改为"不存在"；触发 `data-filter-mode` 的点击改从 `#mineSheet button[data-act]` 派发；新增品牌行 `justify-content` 三条 CSS 断言。**33 PASS / 0 FAIL**。
- `test_mobile_ux_batch.js` **67 PASS**、`test_qa_navtab_20260910.js` **14 PASS**、`preflight_check.py` ✅、`test_tagchip_contrast.py` ✅、`test_deploy_sw_gate.py` ✅、`test_asset_versioning.py` ✅。
- 线上实抓验收（`%TEMP%\md_live_verify.py`，attempt 1 全绿）：build `20260912-0852`、`CACHE_NAME` 同步、`.md-fav-btn`/`.md-badge` 规则与 `id="mdFavBtn"`/`id="mdHistBtn"`/`id="mdFavBadge"` 在**剥注释后**均不存在、品牌行三条 CSS 均在、`mdUpdateFavBadges(){}` 为空实现、"AI 搜"双语义图标与分类栏四等分**未回退**。
- 提交：main `3cf0416` / gh-pages `c418d01`。

### 12.4 复用的工具经验

- **断言注释坑（第二次踩）**：`!/\.md-fav-btn/` 会被自己解释"已删除"的注释里的类名打红 → **锚定规则体** `/\.md-fav-btn\s*[,{]/`，或先剥 `/*…*/` 与 `//` 行。本轮两处断言同时用了"锚定 + 剥注释"。
- **手机视口截图**：`%TEMP%\md_mobile_shot.py`——本地 `http.server` + `/_shot.html`（390×844 iframe 加载 `index.html`，按 hash 派发一次 `.mtab` click 切 tab），`chrome --headless=new --screenshot --window-size=390,844 --virtual-time-budget=25000` 抓三态 PNG 到 `%TEMP%\md_shots\`。坑：HTTP handler 类名别取 `H`/`W`（会覆盖同名的尺寸常量）。
- `mobile-preview.html`（站点上已部署的"手机视图模拟器"）可直接在 PC 上按设备档位看真机布局，不必截图。

## §13 检索能力统一收进「AI 搜」面板（2026-09-12 09:0x，build `20260912-0907`）

### 13.1 用户决议与落地

§11.3 遗留①（移动端顶栏搜索按钮恒不可见 → 首页检索条无入口）给出两条路：「恢复顶栏搜索图标」
或「把检索能力统一收进 AI 搜面板」。**用户定夺：后者**（顶栏保持干净）。

| 文件 | 改动 |
|---|---|
| `app.js` | 移除顶栏搜索按钮注入与事件绑定；删除 `mdOpenSearch()`；`mdMobileTabBar` 顶部注释同步记录决议 |
| `index.html` | 删除 `.md-search-btn` 全部 CSS（@media 内主体样式 + 间距 + 顶层 `display:none` + 44px 触控热区清单引用）与失效的 `body.md-search-open` 规则；面板标题 `💬 新闻问答` → `🔍 AI 搜 · 检索与问答` |
| `sw.js` + `index.html` | build `20260912-0852` → `20260912-0907`（`CACHE_NAME` 同步） |
| `test_mobile_ux_batch.js` | ② 两条断言**翻转**（按钮/CSS 必须不存在）+ 新增两条守护 |

**为什么 `mdOpenSearch()` 是死代码**：它是 `#mdSearchBtn` 的**唯一**调用点；而 `#mdSearchBtn` 恒为
`display:none` —— `index.html` 顶层 `.md-search-btn{display:none}`（原意"只在桌面隐藏"）与
`@media(max-width:768px)` 内的 `display:inline-flex` **同特异性、源码顺序靠后者胜** →
移动端从未显示过该按钮，该函数从未被触发。

### 13.2 移动端检索的现状（改动后）

- **唯一入口**：底栏 `AI 搜` tab → `#qaFloat` 面板（移动端全屏 `100dvh`）。
- **面板内检索闭环**：矿种/主题/时间三个筛选器 + `检索`（全库关键词）+ `AI`（读新闻后作答）；
  引导由**面板欢迎语**承担（`test_smoke_0908.js` 断言欢迎语含「检索」与「AI」）。
- **桌面检索条 `#newsFilterBar` 在移动端保持 `display:none`** —— 硬约束：它是 `app.js` 注入的桌面组件，
  删掉该规则会让它在移动端露出来。其移动端打开类 `body.md-search-open` 已无任何添加点，
  故 `body.md-search-open #newsFilterBar{display:block}` 与配套 `#nfClear` 两条规则一并删除。
- **这是升级不是删减**：被移除的入口原本打开的是「首页 DOM 列表内的关键词筛选」，
  而 `AI 搜` 面板的检索作用于**全库**（`mining_news.json` / `morning_report.json` 等）。
- `index.html` 中 `body[data-md-cat]:not([data-md-cat="tuijian"])… #newsFilterBar{display:none!important}`
  保留（与上一条重叠，属防御性，无害）。

### 13.3 未采纳：输入框 placeholder（不要"顺手"加）

本轮曾为 `#qaFloatInput` 补 `placeholder="搜关键词，或直接问 AI…"`，**已回退**：
`test_smoke_0908.js:219` 明确断言「输入框**不**显示占位提示词」—— 既有决议要求引导由欢迎语承担，
placeholder 冗余。**改这条断言之前不要加 placeholder。** `aria-label` 本轮已更新为「输入关键词检索或问题」（断言只要求非空）。

### 13.4 实测数据（真实 Chrome 无头探针，390/360/320）

| 视口 | 顶栏 `#mdSearchBtn` | CSSOM 内 `.md-search-btn` 规则数 | 品牌行 justify | 横向溢出 | 价格页 mdTop / 标题居中偏差 |
|---|---|---|---|---|---|
| 390 | 已移除 | 0 | space-between | 无 | 47px / 0px |
| 360 | 已移除 | 0 | space-between | 无 | 47px / 0px |
| 320 | 已移除 | 0 | space-between | 无 | 47px / 0px |

- 面板标题实测 `🔍 AI 搜 · 检索与问答`、`placeholder=""`、`#qaFloatSearch`/`#qaFloatAi` 均在；
  分类栏 fill 仍 100%（16px）、底栏 5 tab 图标 22×22、`.md-search-btn` 规则数 0。
- **「CSSOM 内规则数」比字符串匹配更硬**：在探针里遍历 `styleSheets[].cssRules[].selectorText`
  统计含 `.md-search-btn` 的选择器 = **0**，天然绕开"注释里写了类名"的干扰。
- 闸门：`preflight_check` ✅（build/SW 一致、div 收支平衡）· `test_mobile_ux_batch` **69 PASS** ·
  `test_qa_navtab` 14 PASS · `test_mobile_opt` 33 PASS · `test_smoke_0908` **60 PASS** ·
  `test_qa_features` 56 PASS · `test_tagchip_contrast` ✅ · `test_deploy_sw_gate` OK · `test_asset_versioning` ✅。
- 线上实抓验收（`%TEMP%\md_live_verify2.py`，attempt 1 全绿）：build `20260912-0907`、`CACHE_NAME` 同步、
  剥注释后 `.md-search-btn` / `body.md-search-open` / `id="mdSearchBtn"` / `function mdOpenSearch` **均不存在**、
  `#newsFilterBar{position:fixed…display:none` 仍在、面板标题与 placeholder 断言均符合。
- 提交：main `10c3e0e` / gh-pages `a77f5c8`。

### 13.5 ⚠️ 本轮踩到的工具坑（重要，会再遇到）

**同一条消息里对同一文件发多个并行编辑，会互相覆盖 —— 且部分"成功"是假的。**

- 现象：8 处改动全部返回 `Successfully edited file`，但读回磁盘发现 `index.html` 的 5 处**全部未落盘**，
  `app.js` 呈"半生效"混合态（4 处里只有 2 处生效）。
- 排查三步：`os.stat().st_mtime` → 直接读字节 → 查 `~/.workbuddy/projects/<slug>/*.jsonl` 的 mtime，
  **确认当时只有本会话活跃**，排除并发会话，定位为**并行编辑的读-改-写冲突**。
- **对策（已采用，后续默认如此）**：批量文本替换改用**单进程 Python 脚本** —— 读文件 →
  逐条 `t.count(old)==1` 断言（不唯一就报错）→ 一次写回 → **立即读回校验**；
  脚本落 `%TEMP%`（沙箱放行 `TEMP` 与家目录，`mining-daily` 在家目录下，可写）。
- 附带事实：`index.html` 是 **CRLF**、`app.js` 是 **LF**、`REFERENCE.md` 是 **LF**。
  脚本按 `raw.count(b'\r\n')` 判定行尾并在写回时还原，避免整文件 diff 假象。
- **另**：`Grep` 工具对刚被本会话改过的文件可能返回**滞后的行号与内容**；
  核对"是否真落盘"一律用 `Read` 或 Python 直接读字节，不要相信 Grep。
- 探针 `%TEMP%\md_probe_mobile.py` 已扩展：新增面板标题 / 输入框 / 两个按钮 / 样式表规则数四项实测。
  截图 `%TEMP%\md_mobile_shot.py` 新增 `qa` 档（点底栏「AI 搜」→ 面板打开），现输出 home/price/rights/qa 四张 PNG。


---

## §14 今日简报改「两层呈现」（2026-09-12 10:0x，build `20260912-1000`）—— ⚠️ 已同日二次修订，**要点层已被移除**，见 §15

### 14.1 用户诉求与解法选择

- **诉求（原话）**：「今日简报这个内容还是太多了，某天的新闻可能特别多，但不要全部内容都放在这里，要不然这一块太长了。还是要筛选一下内容把重要的信息放在这里。」
- **冲突点**：这与 **§9.2 / §10.1 刚定的「每节全量、单条不截断」方向相反**——那是 09-11、09-12 用户自己拍的板，且 §6 记载 09-06 发生过"截断后非价格内容全被吞掉"的事故。
- **解法（三选一，用户选「两层：要点 + 可展开完整」）**：**不砍内容，加一层**——
  - **要点层** `highlights`：3–5 条一句话（≤50 字），常驻首屏；
  - **完整层** `brief_sections`：五节全量原样保留，点「展开完整分类摘要（N 条）」才出现。
  - 于是「要全」与「别太长」同时成立，且**任意条数的一天首屏高度恒定**。
- **「重要」由谁判断**：用户选**生成时由模型挑**（另两个选项是纯规则挑、规则+模型结合）→ 因此**必须同步 06:00 / 08:00 两条自动化 prompt**（见 14.6）。

### 14.2 数据契约（morning_report.json 新增两字段）

| 字段 | 形态 | 用途 |
|---|---|---|
| `highlights` | `[{cat, t, u}]`，3–5 条 | 要点层。`cat`=所属分节（前端做小标）；`t`=一句话要点（≤50 字）；`u`=对应新闻 url（缺则前端渲染成纯文本） |
| `brief_sections` | `[{name, count, items:[{t,u,s}]}]` | 完整层。`t`=完整摘要（不截断）、`u`=原文 url（供点击跳转）、`s`=来源；**空节不收录** |
| `report` | 字符串（**保留不动**） | 前端兜底：缺上面两字段时回退旧的 markdown 渲染 |

- **要点链接的自动关联**：模型只写关键词 `k`，脚本按 `k` 在当日条目标题里找第一条匹配并填 `u`，随后 `pop('k')`。今日实测 5 条里 4 条命中（行情异动属价格数据、无对应新闻，正确留空）。
- **`report` 改由 `brief_sections` 拼出**，保证"展开看到的"与"结构化数据"永远一致；实测 4432 字 / 18 条**一字不差**（重构等价）。
- **空节不再渲染占位句**：以前无内容会输出「今日暂无新的勘查与技术动态。」这类句子白占高度，现直接不收录。

### 14.3 前端渲染（app.js / index.html）

- `renderBrief()` 新增三段：① **高异动前置行** `.brief-alert`（仅 `sections.anomalies.max_severity==='high'` 时出现，取前 3 项 + 总数）；② 要点层 `briefHighlightsHtml()`；③ 完整层 `briefSectionsHtml()`（节标题带条数徽标 `.sec-n`）。
- `briefJumpTo(url, ev)`：条目点击 → 复用现成的 `newsItemByUrl(url)` 在同页定位到对应新闻卡片 → `scrollIntoView({block:'center'})` + `.brief-flash` 1.6s 高亮；**目标不在 DOM 时静默不动作**（优雅降级）。事件委托绑在 `#briefMain` 上（`data-jump-bound` 标记防重复绑定）。
- `setupBriefClamp(twoLayer)`：**两层模式** = 要点层常驻、完整层由按钮切换（不做高度截断）；**旧模式**（无 highlights）= 原 420px 折叠 +「展开全部（N 条）」，**完整保留为兜底**。
- `briefSub` 文案：`hls.length ? '必看 N 条' : '按分类摘要'`（见 14.5 与 §9.1.3 的更新）。

### 14.4 实测数据（真实 Chrome headless iframe 探针 `%TEMP%\md_brief_probe.py`，三档视口）

| 视口 | 要点层 | 完整层 | 折叠态 `#briefMain` 高 | 展开态高 | 要点层占视口 | 横向溢出 |
|---|---|---|---|---|---|---|
| 1280×900 | 5 条 | 18 条（hidden） | **203px** | 2975px | 17.1% | 无 |
| 390×844 | 5 条 | 18 条（hidden） | 309.9px | 5394.5px | 29.7% | 无 |
| 360×844 | 5 条 | 18 条（hidden） | 353.5px | 5930px | 34.8% | 无 |

- 三档均：副标题「必看 5 条」、节徽标 `2,6,2,7,1`（与数据一致）、按钮「展开完整分类摘要（18 条）」↔「收起」切换正常、`a[data-jump]=19`、CSSOM 两层相关规则 15 条。
- **默认高度对比**：改造前 `#briefMain` 直接渲染全量 = 2975px（桌面），现在 203px —— 约 **1/14**。
- 高异动行实际文本：`今日异动 白银 -5.07%、碳酸锂 -4.59%、沪锡 -3.64%`（当日 `max_severity=high`）。

### 14.5 与既有决议的关系（重要，别误判为回退）

- **§9.2.5「单条不截断」、§9.2 / §10.1「每节全量」继续有效**——本次**没有**动 `fmt_bullet(max_len=0)` 与 `recent_items(limit=0)`。18 条一条未减，`report` 字数前后完全一致（4432）。
- **§9.1.3 已更新**：`briefSub` 由「固定『按分类摘要』」改为**「必看 N 条」**（N=highlights 条数）。它**仍禁止**拼侧栏口径的 `今日收录 N 条`（口径冲突见 §8.3）；「必看 N 条」是简报自身条数，口径自洽。
- **§6 废弃项不受影响**：`setupBriefClamp()` 的 420px 折叠**未删**，降级为无 `highlights` 时的兜底。

### 14.6 必须同步的两条自动化 prompt（已做）

- **06:00 抓取生成（`5cdcdfff`）**：§11.8 里"长度问题交给前端 setupBriefClamp"改为指向两层；新增 **§11.8a** 规定 `highlights` / `brief_sections` 的产出要求与挑选原则（severity=high → 政策/国标 → 重大并购与资源量 → 勘查成果，覆盖不同分节）；§11.8b 更新 `briefSub` 说明；§11.12 汇报项加 highlights 条数。
- **08:00 复验核对（`21dba82b`）**：§2.8 新增**简报两层复核项**（highlights 3–5 条、brief_sections 无空节且 `count==items.length`、页面默认只见要点层、`.brief-full` 带 hidden、有 `.brief-alert`、`a[data-jump]` 可跳、`node test_brief_layers.js` 须 0 失败）；§1.9 指向该回归脚本；输出项加 highlights 条数。
- **不改 prompt 的后果**：次日 06:00 的模型会认为 morning_report 结构就是 prompt 里描述的那样，从而**删掉这两个新字段**——前端兜底会让页面不报错，但两层退化为单层，属静默回退。

### 14.7 测试与闸门

- **新增 `test_brief_layers.js`（43 条断言）**，三块：
  - ① **数据契约**：highlights 存在且 3–5 条、每条有 cat/t 且 t≤56 字、u 均为 http(s)、不残留内部字段 `k`；brief_sections 至少 1 节、**无空节**、`count==items.length`、节名在五节白名单内、完整层总条数 == `report` 条目数。
  - ② **渲染**（jsdom + 本地 http + `beforeParse` 桥接 fetch）：要点层 li 数 == highlights、副标题「必看 N 条」、完整层默认 hidden 且 li == 总条数、节徽标数一致、无「今日暂无」、高异动行按 `max_severity` 出现、按钮展开/收起双向、`a[data-jump]` 存在且点击后目标卡片带 `brief-flash`。
  - ③ **回退路径**：http 层把 `highlights`/`brief_sections` 剥掉返回 → 页面必须仍渲染出 `report` 的 18 条 markdown 列表、无要点层、副标题回「按分类摘要」、按钮走「展开全部」路径。
- 全量（`%TEMP%\md_reg3.py`）：`brief_layers 43` · `mobile_ux_batch 69` · `qa_navtab 14` · `mobile_opt 33` · `smoke_0908 60` · `data_selfheal 11` · `data_integrity 9` · `tagchip 19` · `asset_versioning 15` · `price_history_unclosed 14` · `preflight` ✅ · `sw_gate` ✅ —— **零失败**。
- 线上实抓（`%TEMP%\md_live_verify3.py`，带 no-cache）：Pages 延迟故 attempt 1 读到旧版属正常，**attempt 2 全绿**。

### 14.8 本轮工具经验

- **`automation_update` 的 prompt 是整体字段**：自动化定义不在本地磁盘（`~/.workbuddy` 下只有 audit-log/traces 里的历史副本，项目里只有 `memory/automations/<id>/memory.md`），所以改 prompt 必须**完整重发**。为免转录出错，先 `mode=view` 取回全文再逐段核对（本轮两条长 prompt 均一次通过）。
- **数据层回填用 §9.2.7 的合并法**：备份 4 个分析 JSON → 重跑生成器 → **只取新增字段合并回原 JSON** → 其余 3 个从备份还原。实测 `字段差异=[]`、`updated` 未漂移，证明该法可靠。
- 探针/截图脚本新增：`%TEMP%\md_brief_probe.py`（折叠态/展开态几何 + CSSOM 规则数）、`%TEMP%\md_brief_shot.py`（折叠态/展开态 × 桌面/移动 共 3 张 PNG）。
- 给 Chrome 探针页传状态用 **URL hash**（`#1280x900-1`）最省事，无需在服务端解析 query。

## §15 简报改「五节结构化摘要 + 默认收起」（2026-09-12 10:2x，build `20260912-1022`）

> 本节是对 **§14 的同日二次修订**。§14 的「要点层」方案被用户否决（理由见 15.1），
> §14.1 的「两层」结论、§14.3 的前端渲染描述、§14.6 的自动化同步点均已被本节取代。
> **未变**：§14 与 §9.2 关于「内容一条不减」「单条不截断」「每节全量」的部分仍然有效。
>
> ⚠️ **2026-09-12 三次修订（§16）已推翻上面这句**：用户当天看完上线效果后反馈「展开后 4184 字仍然太多」，
> 「内容一条不减」被改为「逐条精炼（≤80 字）+ 剔除例行条目」。§15 的**结构性结论（要点层已删、五节结构化、
> 默认收起、420/380 两个数字）继续有效**，仅「内容长度」部分以 §16 为准。

### 15.1 用户决议与落地

- **用户反馈（原话）**：「我看了一下，这个内容还是不要了，要不然和下面的今日要闻重复了。」——截图圈掉了简报顶部的「今日异动」行 + 5 条要点。
- **追加定夺**（本轮 AskUserQuestion，用户选「默认收起，长度可控」）：删掉要点层后，五节完整摘要**默认收起**。
- **落地**：

| 文件 | 改动 |
|---|---|
| `app.js` | 删 `briefHighlightsHtml()`；`renderBrief()` 去掉高异动行与要点层渲染；`briefSectionsHtml()` 去掉 `hidden`；`briefSub` 固定「按分类摘要」；`setupBriefClamp()` 去掉两层分支、改无参，恢复单一折叠路径 |
| `index.html` | 删 `.brief-alert`/`.brief-alert-tag`/`.brief-hl*`/`.hl-cat` 全部 CSS 与暗色、≤600px 遗留规则，及死代码 `.brief-full[hidden]`；保留 `.brief-full .brief-sec`/`.sec-n`/`.brief-flash` |
| `sw.js` + `index.html` | build `20260912-1000` → `20260912-1022`（`CACHE_NAME` 同步） |
| `test_brief_layers.js` | 断言随新形态重写（41 条，含「要点层/异动行必须不存在」的反向守护） |

- **`highlights` 字段的处置**：**生成端继续产出、前端不再渲染**。理由：① 为它回退自动化 prompt 的风险大于收益；② 字段留着，将来若要恢复要点层无需再改生成端。故 §14.2 的数据契约中 `highlights` 一行仍有效，但状态改为「备用、不渲染」。
- **别把 420 与 380 搞混**：`setupBriefClamp()` 的 `LIMIT=420` 是「要不要折」的**判定阈值**；`.brief-md.brief-clamp{max-height:380px}` 是**折后高度**。改折叠高度要同时改这两处（判定值须 > 折后高度）。

### 15.2 实测数据（真实 Chrome headless iframe 探针 `%TEMP%\md_brief_probe2.py`，三档视口）

| 视口 | 要点层 / 异动行 | 分节层 | 节条数徽标 | 折叠态 mainH | 展开后 mainH | 按钮文案 |
|---|---|---|---|---|---|---|
| 1280 | 0 / 0 | hidden=false li=18 | 2,6,2,7,1 | **380** | 2756 | 展开全部（18 条） |
| 390 | 0 / 0 | hidden=false li=18 | 2,6,2,7,1 | **380** | 5068.6 | 展开全部（18 条） |
| 360 | 0 / 0 | hidden=false li=18 | 2,6,2,7,1 | **380** | 5560.5 | 展开全部（18 条） |

- 三档均：`briefSub="按分类摘要"`、`a[data-jump]=15`、**CSSOM 内 `.brief-hl` / `.hl-cat` / `.brief-alert` 规则数 = 0**（只剩 `.brief-full` 家族 3 条）、无横向溢出。
- `briefStrip` 整块高度：桌面 553px / 移动 545px（含头部行 + 卡片）。

### 15.3 测试与闸门（12 项，零失败）

`brief_layers 41` · `mobile_ux_batch 69` · `qa_navtab 14` · `mobile_opt 33` · `smoke_0908 60` · `data_selfheal 11` · `data_integrity 9` · `tagchip 19` · `asset_versioning 15` · `price_history_unclosed 14` · `preflight` ✅ · `sw_gate` ✅

- 线上实抓（`%TEMP%\md_live_verify4.py`，带 no-cache）：**attempt 1 全绿**。
- 提交 main `f4fbfc3`，gh-pages `d39e4d6`。

### 15.4 两条自动化 prompt 的同步点（已做）

- **06:00（`5cdcdfff`）**：§11.8a 由「两层呈现」改写为「五节结构化摘要 + 前端默认收起」；明确 `brief_sections` 为必须产物、`highlights` 为**照旧产出但不渲染**（原文加了「缺了也不影响页面，不要为它改动其它内容」）；§11.8b 的 `briefSub` 描述改为固定「按分类摘要」；步骤 8 的「长度问题交给前端两层渲染」改为「420px 折叠」。
- **08:00（`21dba82b`）**：§2.8 复核项重写——**出现 `.brief-hl`/`.hl-cat`/`.brief-alert`、副标题「必看 N 条」、按钮「展开完整分类摘要」、`.brief-full` 带 hidden，任一即为回退到已被否决的首版**，须删净并 bump build-version；`highlights` 明确「不作为复核项」；§1.9 补充 jsdom 需覆盖 `scrollHeight` 的坑；输出清单同步。

### 15.5 本轮工具经验

- **折叠/布局类逻辑 jsdom 测不出来**：jsdom 不做布局，`scrollHeight` 恒为 0 → `main.scrollHeight > 420` 永远 false → 折叠分支静默跳过、按钮恒 hidden。必须在 `beforeParse` 里 `Object.defineProperty(HTMLElement.prototype,'scrollHeight',{configurable:true,get:()=>900})`，折叠逻辑才被真实覆盖。**Chrome 探针仍是唯一能验证真实折叠高度的手段。**
- **注释里的数字要回查实现**：本轮一度把折叠高度写成 420px，实际 CSS 是 380px。写文档/注释时回查一次 CSS，别照抄历史说法。
- **删功能要连「反向守护」一起加**：只把「要点层存在」的断言翻转成「不存在」还不够，要补一条「数据侧即使有 `high` 级异动也不出现异动行」，防止将来有人从数据侧把已删的东西带回来。
- 脚本：`%TEMP%\md_brief_probe2.py`（新形态几何 + CSSOM 残留）、`%TEMP%\md_brief_shot.py`（4 张 PNG：桌面/移动 × 折叠/展开）。

### 15.6 仍可优化（未做，待用户）

- ~~移动端 `briefStrip` 整块 545px~~ → **§16 已把内容压到 1057 字**，整块高度随之下降；若仍嫌长，可把折叠高度降到 240–280px（需同时改 `.brief-md.brief-clamp` 的 `max-height` 与 `setupBriefClamp()` 的 `LIMIT`）。
- 简报与下方「今日要闻」仍同源（一个是精炼句，一个是标题速览），但**长度差已拉开**（66 字/条 vs 标题级），重复感大幅弱化。若继续去重，可考虑简报只保留「要闻未覆盖的类目」。

---

## §16 简报改「逐条精炼句 + 剔除例行条目」（2026-09-12 三次修订，build `20260912-1040`）

> 本节推翻 §9.2.5 / §10.1 / §15 关于「内容一条不减」的**长度**结论（§15 的**结构性**结论继续有效），
> 是简报口径的**当前唯一权威**。起因：§15 上线后用户当天反馈「展开后 3500 多字实在太多」。

### 16.1 用户诉求与决议

- **原话**：「今日简报的整体内容本身还能缩减吗？我看了一些今天的内容就有 3500 多字，文字实在是太多了。有没有什么方案把关键是信息总结一下就行，不要什么内容都总结。」
- **根因**：不是条数多（18 条 vs 当日新增 26 条，已算精选），而是**单条太长**——平均 **232 字/条**、最长 406 字；条目是 `news['summary']` 的**原样搬运**（与下方新闻卡片同源），等于把新闻列表又抄了一遍。
- **三项定夺**（AskUserQuestion）：
  1. 力度 = **精炼单条·保留全貌**（每条 ≤80 字，分类全保留，不砍成 5 条）
  2. 条目取舍 = **允许剔除低信息量例行条目**
  3. 今天这份 = **立即重做**（不等明天）

### 16.2 落地机制（`update_analysis_YYYYMMDD.py` 四个构件）

| 构件 | 作用 |
|---|---|
| `BRIEF_MAX = 80` | 单条硬上限 |
| `ROUTINE_NOTICE` | 例行条目关键词（装车发运/出厂检验/启运/工商变更/业绩说明会/投资者关系/机构调研/持续督导/核查意见/法律意见书/股东大会/董事会决议/监事会/异常波动/问询函/关注函/更正公告/补充公告/权益变动/减持/增持） |
| `BRIEF_DIGEST` | **逐条撰写的精炼句清单**：`[{cat, t, k}]`，`t` ≤80 字、只留「主体 + 动作 + 关键数字」，`k` = 关联原文关键词（用于在当日条目标题里匹配 url） |
| `digest_summary(body, max_len)` | 兜底截句：整句优先，单句超长退到逗号/分号，绝不在句中硬切（某节一条未写时用） |

- **三项硬校验（fail loud）**：条目超 80 字 / 分节名越界 / 混入 `ROUTINE_NOTICE` 关键词 → 直接 `RuntimeError` 拒绝生成。**这是预期拦截，不要放宽校验，要压缩内容**。
- 生成流程：`BRIEF_DIGEST` → 按 `k` 匹配 `u`/`s` → 按五节分组 → 某节为空则 `digest_summary()` 兜底 → `brief_sections` → `report` 由 `brief_sections` 拼出 → `highlights` 由各节首条派生（≤5 条）。
- **`highlights` 改为派生**（不再手写）：单一真源，杜绝与 `brief_sections` 漂移；前端仍不渲染。

### 16.3 数据契约变化（`morning_report.json`）

- `brief_sections[].items[].t` 语义变更：**从「完整摘要（不截断）」→「精炼句（≤80 字）」**。
- `report` 仍是 `brief_sections` 的拼接兜底文本，但随之下探到 **1283 字**。
- `highlights` 由手写改为派生（各节首条，≤5 条）。

### 16.4 实测数据

| 指标 | 改造前（§15） | 改造后（§16） |
|---|---|---|
| 条数 | 18 | **16**（剔除 2 条例行：贵州铝厂阳极车发运、无锡振华工商变更） |
| 纯文本字数 | 4184 | **1057**（-75%） |
| 平均每条 | 232 字 | **66 字** |
| 最长单条 | 406 字 | **79 字** |
| 分节条数 | 2,6,2,7,1 | **2,5,2,6,1** |
| `report` 字数 | 4432 | **1283** |

- 其余三个分析文件（`sentiment.json`/`signals.json`/`alerts.json`）重跑后**逐字节一致**（无附带漂移）。

### 16.5 测试与闸门（12 项，零失败）

`brief_layers 47` · `mobile_ux_batch 69` · `qa_navtab 14` · `mobile_opt 33` · `smoke_0908 60` · `data_selfheal 11` · `data_integrity 9` · `tagchip 19` · `asset_versioning 15` · `price_history_unclosed 14` · `preflight` ✅ · `sw_gate` ✅

- `test_brief_layers.js` 新增 6 条守护：每条 ≤80 字 / 总量 ≤1200 字 / 无例行条目 / 条数 < 当日新增 / 无「（原题：」噪声 / 以句末标点收尾。

### 16.6 两条自动化 prompt 的同步点（已做）

- **06:00（`5cdcdfff`）**：步骤 8 的「单条用完整摘要（不截断）、每节不限条数」**已作废**，改为 `BRIEF_DIGEST` 精炼句机制（≤80 字 / 剔除例行条目 / 条数 < 当日新增 / 四个构件照抄）；§11.8a 重写；汇报项加「精炼句字数」。
- **08:00（`21dba82b`）**：§2.8 加**反向守护**——简报出现「（原题：」、单条 >80 字、总量 >1200 字、`ROUTINE_NOTICE` 关键词、条数 ≥ 当日新增，任一即为回退，须拦下并 bump。

### 16.7 本轮工具经验

- **机械截句 ≠ 精炼**：`trunc80` 当年被否决是因为「切在半句」；本轮做法是**逐条重写**（保留关键数字、去掉修饰与次要细节），所以既能 ≤80 字又不破坏语义。**不要用截断实现本条**。
- **同文件多处文本替换一律用单进程 Python 脚本**（`count==1` 断言 + 写完立即读回）：本轮对 `update_analysis_20260912.py` 做整块替换 + 3 处压缩，一次成功；`Edit` 工具在同一消息内多次调用会互相覆盖（§13.5）。
- **长度校验用 `ast.literal_eval` 而不是正则**：源码里的 `\u201c` 转义在正则提取时是 6 个字符、运行时才是 1 个，正则会误报超长。用 `ast.parse` + `literal_eval` 取到的才是运行时真实值。
- **脚本行尾**：`update_analysis_20260912.py` 是 **CRLF**（整块替换时必须把新文本的 `\n` 还原成 `\r\n`，否则整文件 diff）。
