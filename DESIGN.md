# DESIGN.md — 矿业日报（mining-daily）

> 版本 v3 · 2026-09-11 · 设计系统架构：Diana
> 参考混搭：**Linear 的密度与排版节奏 + Stripe 的数据可信感 + IBM Carbon 的中性灰阶与无障碍标准**
> 定位：中文行业资讯 + 行情数据的**高密度阅读型**静态页（PWA），桌面双栏、移动单列。
> 目标行数 280-350 · 所有数值可直接复制使用 · 供 AI 编程代理消费
>
> **v3 修订原则（重要）**：凡是"规范所写"与"实现 + 测试"冲突的，一律**以实现为准改规范**，
> 而不是让代码退回规范——因为本项目的多数偏离是**有意识的无障碍修正**，且已由测试锁定。
> 详细对账见 **附录 D**。v3 共修正 **4 处规范自身不达 AA 的取值**、**19 项规范↔实现冲突**（含组件命名与提示词同步）、
> 补齐 **5 类已实现的例外**（pill 几何 / 枚举调色板 / 「问」球渐变 / 移动端字号 / `#mdBootWarn` z-index）、
> 标注 **4 组已失效 token**，并**清理 70 个零渲染死类 / 119 条死规则**（index.html −3.2%）。
> v3 之后如需引入新的偏离，请同步更新附录 D，否则下一轮审计会再次把规范当权威而误判。

---

## 1. Visual Theme & Atmosphere（视觉主题与氛围）

**设计哲学**：这是一个每天清晨被快速扫读的行业日报，不是营销页。设计的一切服务于「三秒内判断今天有没有值得看的东西」——所以信**息密度优先，但用统一的间距体系留出呼吸感**，而不是靠放大留白。

**视觉基调**：专业、克制、可信赖。介于「财经终端」与「企业文档」之间——比 Bloomberg 温和，比新闻门户严谨。

**核心视觉特征（5 个）**
1. **克制的线条**：分隔靠 1px 浅灰线，不靠色块与阴影堆叠
2. **单一强调色**：青蓝 `#0e7490` 只用于品牌、选中态、链接与关键数字，全页强调色占比 < 5%
3. **等宽数字**：所有价格、涨跌幅、计数使用 `tabular-nums`，跳动时不抖
4. **弱化的已读态**：用文字色降级而非整块透明度，保证小字号可读性
5. **零装饰**：无渐变、无插画、无动效装饰；仅在 hover/聚焦有 120ms 过渡
   （唯一例外：移动端底部「问」AI 球——渐变 + 外发光 + 脉冲，因为它必须与其它 tab 强区分，见 §7 Don'ts 6）

**光影与质感**：纯扁平 + 极低饱和阴影。阴影色统一走 `rgba(0, 55, 112, …)` 蓝调（取自 Stripe），避免中性黑阴影在浅灰底上发脏。深色模式不用阴影，改用 1px 亮边框表达层级。

---

## 2. Color Palette & Roles（调色板与角色）

### 2.1 Primary / Neutral 中性灰阶（IBM Carbon 对比度标准）

| 角色 | CSS 变量 | HEX（亮） | HEX（暗） | 对比度 亮/暗（on `--surface`） | 使用场景 |
|---|---|---|---|---|---|
| 标题文字 | `--ink-900` | `#16202b` | `#e8eef3` | 16.46 / 13.38 | 页面标题、卡片标题 |
| 正文文字 | `--ink-700` | `#3d4b5a` | `#b6c2ce` | 8.93 / 8.64 | 摘要、列表正文 |
| 次要文字 | `--ink-500` | `#5f6d7a` | `#8b9bad` | **5.31** / 5.51 | 来源、时间、表头、灰字控件 |
| 弱化文字 | `--ink-300` | `#64737f` | `#8394a5` | **4.88** / 5.03 | 已读条目、占位提示 |
| 分隔线 | `--line-1` | `#e5eaf0` | `#2a3542` | — | 卡片内分隔、列表项之间 |
| 控件边框 | `--line-2` | `#d5dde5` | `#35424f` | — | 输入框、按钮、筛选器边框 |

> **v3 修正**：`--ink-500` 与 `--ink-300` 的旧值（`#6b7a89` / `#94a3b8`）**实算分别只有 4.40 / 2.56**，
> 都不到 AA。规范写的"4.9:1"是错的——这是 v2 最严重的问题，按旧值产出的样式在实测中会被判不及格。
> 现改为实现中已生效的值，并附实测对比度。
> **`--ink-300` 的定位**：仍只用于"已读/占位"等**非正文**文字。它在白底 4.88、`--surface-2` 4.55 达标，
> 但在 `--surface-3`(`#eef2f6`) 上为 **4.34**（暗色 `#26313f` 上 4.23）——这是已知且**已接受**的
> 0.16 缺口，涉及 2 处（`.toc-count-fresh.is-empty`、`.rc-deadline.rc-expired`）。若将来要补，
> 应新增专用 token 而不是抬 `--ink-300` 本体（抬本体会压平"已读/未读"的层级差）。

### 2.2 Brand & Dark 品牌与深色

| 角色 | CSS 变量 | HEX（亮） | HEX（暗） | 使用场景 |
|---|---|---|---|---|
| 品牌主色 | `--brand` | `#0e7490` | `#38bdf8` | 选中态背景、链接、区块竖条 |
| 品牌深色 | `--brand-ink` | `#0b5a70` | `#7dd3fc` | 品牌文字、hover 态 |
| 品牌浅底 | `--brand-soft` | `#e6f4f7` | `#123040` | NEW 徽章底、选中项浅底 |
| 链接 hover | `--accent-hover` | `#0f788d` | `#7dd3fc` | 标题 hover 色 |

> **v3 修正（机制层，重要）**：v2 曾列出 `--dark-bg / --dark-surface / --dark-line / --dark-ink`
> 四个深色变量。**这四个变量在实现中根本不存在**，按 v2 写样式会得到一对无效的 `var()`。
>
> 实际机制是**同名覆盖**：`body.dark{ … }` 把**上面同一批变量名**（`--ink-* / --line-* / --bg /
> --surface-* / --brand* / --accent-hover`）整体重新赋值。所以写组件样式时**只需写一遍**
> `color:var(--ink-700)`，深色模式自动跟随；**不要**去写 `body.dark .x{color:#b6c2ce}` 这类平行规则，
> 那正是本项目历史上一再出现的"漏改"来源。
>
> 完整暗色映射见 §2.1 / §2.4 / §2.5 各表的"HEX（暗）"列。

### 2.3 Accent / Interactive 强调与交互

| 角色 | CSS 变量 | HEX（亮） | HEX（暗） | 使用场景 |
|---|---|---|---|---|
| 战略徽章字 | `--tag-strategy` | `#4f46e5` | `#8b8cf9` | 「战略」徽章文字 |
| 战略徽章底 | `--tag-strategy-bg` | `#eeedfe` | `#232a4d` | 「战略」徽章底色 |
| 重大徽章字 | `--tag-major` | `#c0392b` | `#ff6b5b` | 「重大」徽章文字 |
| 重大徽章底 | `--tag-major-bg` | `#fceaea` | `#3a2020` | 「重大」徽章底色 |

> **`--focus-ring` 不存在**（v3 标注）：v2 把它写成 token `#0e749040`，但实现里没有这个变量，
> 聚焦环一律写**字面值** `outline:2px solid rgba(14,116,144,.25)`（等价于 8 位 hex `#0e749040`）。
> 若将来要收敛，正确做法是在 `:root` 补 `--focus-ring: rgba(14,116,144,.25)` 再替换全部字面值，
> **不要**继续沿用"文档里有、代码里没有"的状态。
> **`--tag-major` 由 `#d93a2b` 改为 `#c0392b`**：前者是 §2.4 的 `--up`（涨），与"重大"语义混用会让
> 读者分不清"红"是涨还是重要；实现已统一到 `--danger` 的深红。

### 2.4 Semantic 语义色（中国市场习惯：涨红跌绿）

| 角色 | CSS 变量 | HEX（亮） | HEX（暗） | 对比度（亮） | 使用场景 |
|---|---|---|---|---|---|
| 涨 / 上升 | `--up` | `#d93a2b` | `#ff6b5b` | 4.57 | 价格上涨、正向变化 |
| 跌 / 下降 | `--down` | `#0e7a52` | `#35c48d` | **5.35** | 价格下跌、负向变化 |
| 平 / 持平 | `--flat` | ~~`#6b7a89`~~ | ~~`#8b9bad`~~ | — | **⚠️ 已失效（v3）** |
| 成功 | `--success` | `#0e7a52` | `#35c48d` | 5.35 | 操作成功提示 |
| 警告 | `--warning` | `#966319` | `#e0a83a` | 5.13 | 数据过期、待确认 |
| 危险 | `--danger` | `#c0392b` | `#ff6b5b` | 5.44 | 删除、失效链接 |
| 信息 | `--info` | `#0e7490` | `#38bdf8` | 5.36 | 说明、提示条 |

> **`--down` 由 `#128a5f` 改为 `#0e7a52`**：v2 的值实算仅 **4.35**，不达 AA（而规范却把它列在
> "语义色"这种要能安全承载小字号的用途上）。实现用的 `#0e7a52` 为 5.35，与之同值的 `--success` 一并更新。
> **`--warning` 由 `#b7791f` 改为 `#966319`**：v2 值实算 **3.64**，同样不到 AA。
> **`--flat` 已失效**：全仓 `var(--flat)` 引用 **0 次**——"持平"语义实际由 `.pc-chg{color:var(--ink-500)}`
> 承担。token 定义仍在 `:root`/`body.dark` 里（留作占位），但**不要再使用**；下次清理可一并删除。
> **`--up` 也用作 hover 色**（热榜/要闻标题）：这是**有意的热度表达**而非误用。它是红字而非红底白字，
> 在白底上 4.57 达标，无对比度损失。评审曾按 §2.4"语义色不得挪用"判为违规，v3 明确此项**属例外**。
> （上表对比度均按 `--surface` = `#fff` 实算；`--danger` 在浅底徽章如 `#e8f8f0` 上是 4.87，仍达标。）

### 2.5 Surface 表面层级

| 层级 | CSS 变量 | HEX |
|---|---|---|
| 页面底 | `--bg` | `#f5f7fa` |
| 卡片 / 面板 | `--surface` | `#ffffff` |
| 次级块（表头、代码块） | `--surface-2` | `#f5f7fa` |
| 三级块（芯片、标签底） | `--surface-3` | `#eef2f6` |

### 2.6 Shadow Colors 阴影色

统一蓝调，禁止纯黑阴影。

> **v3 修正**：v2 在此定义了 `--shadow-color-sm/md/lg` 三个**纯颜色** token，但实现中不存在——
> 实现把"颜色 + 偏移 + 模糊"直接封装成 **5 层完整阴影**（`--shadow-xs…xl`，见 §6.1），
> 组件直接引用整条阴影值，无需再拆颜色。
>
> 因此本节的正确用法是：**引用 §6.1 的 `--shadow-xs/sm/md/lg/xl`**，不要按 v2 的写法引用
> `var(--shadow-color-md)`（会静默失效，得到 `box-shadow:none`）。蓝调基准仍为
> `rgba(0,55,112,…)`（Stripe），大阴影用 `rgba(16,32,43,…)` 加深。

---

## 3. Typography Rules（排版规则）

### 3.1 Font Family

```css
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
             "Hiragino Sans GB", "Microsoft YaHei", "Source Han Sans SC", sans-serif;
--font-num: "SF Mono", "JetBrains Mono", ui-monospace, Consolas, monospace;
```
中文优先苹方 / 微软雅黑；数字与价格用等宽字体族并开启 `font-variant-numeric: tabular-nums`。

### 3.2 Type Scale（7 级，禁止半像素级）

| 级别 | CSS 变量 | Size | Weight | Line Height | Letter Spacing | 用途 |
|---|---|---|---|---|---|---|
| Display | `--fs-display` | 24px | 600 | 1.3 | -0.01em | 页面主标题 |
| H1 区块 | `--fs-h1` | 20px | 600 | 1.35 | -0.005em | 区块主标题（今日新增 / 往期） |
| H2 小节 | `--fs-h2` | 16px | 600 | 1.4 | 0 | 区块标题、弹窗标题 |
| H3 卡片 | `--fs-h3` | 14px | 500 | 1.5 | 0 | 新闻条目标题、卡片标题 |
| Body | `--fs-body` | 13px | 400 | 1.6 | 0 | 摘要、列表正文 |
| Meta | `--fs-meta` | 12px | 400 | 1.5 | 0 | 来源 / 时间 / 表头 / 按钮 |
| Nano | `--fs-nano` | 10px | 500 | 1.4 | 0.02em | 徽章、脚注、版权 |

**设计哲学**
- **字重只有 3 档**：400 / 500 / 600。禁止 700+（中文粗体在小字号下糊成一团）。
- **禁用 11.5 / 12.5 / 13.5px** 这类半像素级——Windows 下亚像素渲染会让字发虚，是「看着不精致」的隐形主因。
- 行高随字号递减：24→1.3，13→1.6。中文行高比西文略大，1.6 是密度与可读性的平衡点。
- 中文**不使用** letter-spacing 正值（会散），标题可用 -0.01em 收紧。

---

## 4. Component Stylings（组件样式）

### 4.1 Buttons（4 变体）

```css
/* Primary */
.btn-primary{background:#0e7490;color:#fff;border:1px solid #0e7490;
  border-radius:8px;padding:6px 14px;font-size:12px;font-weight:500;
  transition:background .12s ease}
.btn-primary:hover{background:#0b5a70}
.btn-primary:active{background:#094a5c}

/* Secondary */
.btn-secondary{background:#fff;color:#3d4b5a;border:1px solid #d5dde5;
  border-radius:8px;padding:6px 14px;font-size:12px}
.btn-secondary:hover{border-color:#0e7490;color:#0b5a70;background:#e6f4f7}

/* Ghost */
.btn-ghost{background:transparent;color:var(--ink-500);border:1px solid transparent;
  border-radius:8px;padding:6px 10px;font-size:12px}
.btn-ghost:hover{background:#eef2f6;color:#16202b}

/* Danger */
.btn-danger{background:#fff;color:#c0392b;border:1px solid #f0c9c4;
  border-radius:8px;padding:6px 14px;font-size:12px}
.btn-danger:hover{background:#c0392b;color:#fff}

/* 通用聚焦环（键盘可达性） */
.btn:focus-visible{outline:2px solid #0e749040;outline-offset:2px}
```
高度：桌面 32px（padding 6px + 12px 字 + 边框），移动端触控区 ≥ 44px。

> **例外：pill（药丸）控件几何**（v3 明确）。本项目另有一族 **pill 控件**——主题/阅读模式切换、
> 筛选 chip、日期徽章、`--tag-*` 徽章、`.rr-type`、`.md-fav-btn` 等，它们的实际高度为
> **34–38px**、圆角为 **17/19/20px 或 999px**。
>
> 这不是"违反 §4.1"，而是**另一族控件**：32px 是对 `.btn`（6px padding + 12px 字 + 1px 边框）的推导值，
> 与 pill 不是同一控件族；pill 的圆角就是"高 ÷ 2"，**高度不改则圆角本就正确**。
> 把 pill 圆角改成 8px 会破坏药丸造型，属大范围视觉回归。
>
> **判定规则**：矩形按钮按 32px/8px；pill 按"高度自洽 + 全圆角"。新增 pill 时请沿用此规则，
> 不要再按 §9.1 的 4/8/12 硬套。

### 4.2 Cards

```css
.card{background:#fff;border:1px solid #e5eaf0;border-radius:12px;
  padding:16px;box-shadow:0 1px 3px rgba(0,55,112,.06)}
.card-hover:hover{border-color:#0e7490;box-shadow:0 4px 12px rgba(0,55,112,.08);
  transform:translateY(-1px);transition:all .12s ease}
```
- 卡片内边距 **16px**（移动端 12px）
- 卡片之间 **16px**，区块之间 **32px**
- 深色：`background:#1b2430; border-color:#2a3542; box-shadow:none`

### 4.3 Inputs

```css
.input{background:#fff;border:1px solid #d5dde5;border-radius:8px;
  padding:7px 12px;font-size:13px;color:#16202b;height:34px}
.input::placeholder{color:#64737f}
.input:focus{border-color:#0e7490;outline:none;
  box-shadow:0 0 0 3px rgba(14,116,144,.12)}
```

### 4.4 Navigation（侧栏目录 / 顶部工具条）

```css
.nav-item{font-size:13px;color:var(--ink-500);padding:7px 12px;border-radius:8px;
  display:flex;align-items:center;gap:8px}
.nav-item:hover{background:#eef2f6;color:#16202b}
.nav-item.active{background:#e6f4f7;color:#0b5a70;font-weight:500}
.nav-item.active::before{content:"";width:3px;height:14px;border-radius:2px;
  background:#0e7490;margin-right:-4px}
```

### 4.5 Badges / Tags

```css
.badge{font-size:10px;font-weight:500;padding:1px 6px;border-radius:4px;
  line-height:1.5;white-space:nowrap}
.badge-new{background:#e6f4f7;color:#0b5a70}
.badge-strategy{background:#eeedfe;color:#4f46e5}
.badge-major{background:#fceaea;color:#c0392b}
.tag-chip{font-size:12px;font-weight:600;padding:1px 8px;border-radius:4px;
  line-height:1.6;letter-spacing:.3px;white-space:nowrap;cursor:pointer}
  /* 只含结构；配色见下方 .tc-* 表 */
```
**硬约束**：每条新闻 `.tag-chip` ≤ 2 个，徽章 ≤ 2 个。

> **v3 修订：`.tag-chip` 配色改为「按类别枚举」**（原为单一灰底）。原因：标签的颜色承载**类别语义**
> （战略/矿种/矿权/勘查/资本/政策/市场/培训/国际/科技），单一灰底会把这个语义抹平。
>
> **实现方式**（改动时请照此办理）：
> - 结构仍在 `.tag-chip` 基类（`font-size/padding/border-radius/…`）；
> - 配色由 **`.tag-chip.tc-<类别>`** 承担，类别名与 `app.js` 的 `TAG_STYLE` 一一对应；
> - **深色必须写成 `body.dark .tag-chip.tc-X`**（特异性 0,3,1），否则会被兜底的
>   `body.dark .tag-chip`（0,2,1）压掉；
> - 未知类别回落 `.tc-default`；
> - ⚠️ **不要用 `chip.style.color/background` 内联下发**——内联样式恒压过所有选择器，
>   本项目曾因此让暗色下 11 组配色**全部失效**（2026-09-11 F6）。
>
> **允许此处硬编码 hex**（§7 Do's 第 1 条的例外）：这是**枚举型调色板**，11 类 × 亮暗 = 22 个值，
> 互相之间无复用关系，token 化只会增加 22 个一次性变量；与 §4.5 徽章色、§4.3 语义色同属
> "调色板字面值"一类。**除此之外的颜色仍必须走变量。**

| 类别 | class | 亮色（字 / 底） | 暗色（字 / 底） | 对比度 亮 / 暗 |
|---|---|---|---|---|
| 战略 | `.tc-strategy` | `#b45309` / `#fef3c7` | `#fbbf24` / `#3a2c14` | 4.51 / 8.11 |
| 矿种 | `.tc-metal` | `#ba4a00` / `#fdf2e9` | `#fb923c` / `#3b2313` | 4.68 / 6.46 |
| 矿权 | `.tc-rights` | `#2573a6` / `#ebf5fb` | `#38bdf8` / `#123040` | 4.65 / 6.44 |
| 勘查 | `.tc-explore` | `#117c67` / `#e8f8f5` | `#34d399` / `#10322c` | 4.67 / 7.21 |
| 资本 | `.tc-capital` | `#c0392b` / `#fdedec` | `#f87171` / `#3a1f1f` | 4.79 / 5.44 |
| 政策 | `.tc-policy` | `#8e44ad` / `#f4ecf7` | `#c084fc` / `#2f1f3d` | 5.08 / 5.74 |
| 市场 | `.tc-market` | `#0e7490` / `#e0f2fe` | `#22d3ee` / `#10313a` | 4.67 / 7.63 |
| 培训 | `.tc-edu` | `#6d4c41` / `#efebe9` | `#d6d3d1` / `#2f2622` | 6.42 / 9.92 |
| 国际 | `.tc-global` | `#475569` / `#f1f5f9` | `#94a3b8` / `#26313f` | 6.92 / 5.14 |
| 科技 | `.tc-tech` | `#0f766e` / `#ccfbf1` | `#2dd4bf` / `#0f3330` | 4.86 / 7.34 |
| 兜底 | `.tc-default` | `#667172` / `#f4f6f7` | `#94a3b8` / `#26313f` | 4.65 / 5.14 |

> 亮色原有 4 组不达 AA（矿种 3.78 / 矿权 3.89 / 勘查 3.00 / 兜底 3.21），已按"保留底、压暗字"修正。
> 暗色 padding 里 `border-radius` 走 `--r-sm`(4px)；移动端 `<768px` 另有更小字号规则。
> 回归测试：`test_tagchip_contrast.py`（19 项，含亮/暗对比度、类别集合一致性、反内联回退）。

### 4.6 Modals / Dialogs

```css
.mask{position:fixed;inset:0;background:rgba(16,32,43,.45);z-index:1000;
  animation:fade .12s ease}
.dialog{background:#fff;border-radius:12px;padding:24px;max-width:520px;
  box-shadow:0 12px 32px rgba(16,32,43,.12);z-index:1010;
  animation:pop .16s cubic-bezier(.2,.8,.3,1)}
@keyframes pop{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:none}}
```

### 4.7 项目特有组件

> **v3 说明**：以下三块是**可复制的参考实现**，类名已对齐线上真实渲染（`.news-item` / `.news-title` / `.news-summary` / `.news-meta` / `.news-tags` / `.tag-chip`；价格区为 `.price-card` / `.pc-name` / `.pc-value` / `.pc-chg`；区块标题为 `.section-title`）。v2 曾用 `.news-sum` / `.px-name` / `.px-val` / `.px-chg` / `.sec-title`——**这些名字线上不存在**（只在 v1 文档 `docs/design-spec.html` 里），照抄会得到「改了没用」的死代码。

**新闻条目（核心组件）**
```css
.news-item{padding:12px 16px;border-bottom:1px solid #e5eaf0;background:#fff}
.news-title{font-size:14px;font-weight:500;line-height:1.5;color:#16202b}
.news-meta{font-size:12px;color:var(--ink-500);margin-top:4px;display:flex;gap:8px}
.news-summary{font-size:13px;line-height:1.6;color:#3d4b5a;margin-top:6px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.news-item.read .news-title{color:var(--ink-300)}
.news-item.read .news-summary{color:var(--ink-300)}
```
> **关键修订**：已读态用 `--ink-300` 文字色，**不用** `opacity:.55`——透明度会让 13px 中文在白底上发灰模糊。
> **移动端**（`@768`）：`.news-item` 改为卡片（`1px --line-2` + `--r-lg` + `--shadow-sm`），`.news-summary` 加 `-webkit-line-clamp:3`；详见 §8.4。

**价格行（密度核心）**
```css
.price-card{display:grid;grid-template-columns:…;gap:12px;
  padding:8px 0;border-bottom:1px solid #e5eaf0;align-items:baseline}
.pc-name{font-size:12px;color:var(--ink-500)}
.pc-value{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums;
  font-family:var(--font-num)}
.pc-chg{font-size:12px;font-variant-numeric:tabular-nums;min-width:56px;text-align:right}
.pc-chg.up{color:var(--up)} .pc-chg.down{color:var(--down)}
```
> ⚠️ `renderLmePrices()` **不得**触碰 `.pc-name` / `.pc-chg` 的 `textContent`，也**不得**用其它数据源覆盖卡片价——数值唯一来源是当日 `lme_data.json`。

**区块标题**
```css
.section-title{font-size:16px;font-weight:600;line-height:1.4;color:#16202b;
  padding-left:12px;border-left:3px solid #0e7490;margin:32px 0 12px}
```

---

## 5. Layout Principles（布局原则）

### 5.1 Spacing System（4px 基数）

| Token | 值 | 用途 |
|---|---|---|
| `--s1` | 4px | 图标与文字间隙 |
| `--s2` | 8px | 行内元素 gap |
| `--s3` | 12px | 条目内小间距、卡片内边距（移动端） |
| `--s4` | 16px | **卡片内边距（标准）**、卡片间距 |
| `--s5` | 24px | 弹窗内边距、大卡片间距 |
| `--s6` | 32px | **区块之间** |
| `--s7` | 40px | 空态/大留白区块（`--empty` 类容器） |

> v3 补记：`--s7` 在实现中已存在并使用（v2 遗漏），但**不要**用它替代 `--s6` 做区块间距——
> 区块间距仍是 32px，40px 只用于"整块空态提示"这类需要额外呼吸感的地方。

### 5.2 Grid System

| 断点 | 布局 | 说明 |
|---|---|---|
| ≥1101px | `minmax(0,1fr) 300px` | 主列 + 右栏 sticky |
| ≥1440px | `minmax(0,1fr) 320px` | 右栏加宽 |
| <1101px | 单列 | 右栏内容降级为顶部横条 |

### 5.3 Container

```css
.container{max-width:1360px;margin:0 auto;padding:16px}
```
移动端 `padding:12px`。

### 5.4 Section Spacing 与留白哲学

区块之间 32px、卡片之间 16px、卡片内 16px。
**留白哲学**：留白来自「统一且不随意突破的间距体系」，不是把元素拉大。同一层级间距必须一致——间距不一致比间距小更显廉价。

---

## 6. Depth & Elevation（深度与层级）

### 6.1 Shadow System（5 层）

```css
--shadow-xs: 0 1px 2px rgba(16,32,43,.04);
--shadow-sm: 0 1px 3px rgba(0,55,112,.06);
--shadow-md: 0 4px 12px rgba(0,55,112,.08);
--shadow-lg: 0 12px 32px rgba(16,32,43,.12);
--shadow-xl: 0 24px 48px rgba(16,32,43,.16);
```
- 卡片默认 `--shadow-sm`，hover `--shadow-md`，弹窗 `--shadow-lg`
- **深色模式全关阴影**：改用 `#2a3542` 边框 + 卡片背景提亮表达层级

### 6.2 Surface Layers

`background(#f5f7fa)` → `surface(#fff)` → `elevated(#fff + shadow-md)` → `overlay(dialog + shadow-lg)`

### 6.3 Z-index Scale

| 层级 | 值 |
|---|---|
| 内容流 | 0 / auto |
| sticky 工具条、右栏 | 100 |
| 侧栏导航 | 200 |
| AI 悬浮球 | 900 |
| 遮罩 mask | 1000 |
| 弹窗 dialog | 1010 |
| Toast / 通知 | 1100 |

实现中对应的 token：`--z-sticky:100 / --z-sidebar:200 / --z-fab:900 / --z-mask:1000 / --z-dialog:1010 / --z-toast:1100`。

> **已知例外（v3 登记，2026-09-11 已收敛）**：启动故障自愈横幅 `#mdBootWarn` 原用 `z-index:99999`，
> **超出本表上限**。它是 2026-09-11 事故当天为"页面全挂时唯一可见的出口"临时加的，
> 刻意凌驾一切；但保留 99999 会让"z-index 有天花板"这条约束失效。
>
> 处置结论：**已收敛** —— 新增 `--z-critical:1200`（index.html `:root` token 行），
> 横幅 `z-index` 改为 `var(--z-critical)`，并同步更新本表（§9.1 z 列已含 critical 1200）。
> 1200 仍高于 `.qa-fab`（900）、遮罩（1000）、弹窗（1010）与 toast（1100），遮挡需求满足，
> 同时恢复了"z-index 有天花板"约束（上限 1200）。

### 6.4 Backdrop Effects

侧栏与弹窗遮罩可用 `backdrop-filter: blur(4px)`；**主内容区禁用毛玻璃**（会降低文字对比度且拖慢低端机渲染）。

---

## 7. Do's and Don'ts

**Do's**
1. 所有颜色、字号、间距、圆角**必须走 CSS 变量**，禁止硬编码
   > **v3 例外 · 枚举调色板**：`.tag-chip.tc-<类别>` 与 `--tag-*` 这类「按类别的有限调色板」允许写 HEX 字面量——它们不是可复用的语义 token，且必须**成对**给出亮/暗两套并各自 ≥4.5。除此之外任何裸 HEX 都算硬编码。
2. 价格、涨跌幅、计数一律 `tabular-nums`
3. 已读态用文字色降级，不用整块透明度
4. hover / focus 过渡统一 120ms，`ease`
5. 每个可交互元素都有 `:focus-visible` 焦点环
6. 区块间距 32px、卡片间距 16px，同层级保持一致
7. 强调色全页占比 < 5%，只用于关键信息与选中态
8. 深色模式用边框而非阴影表达层级
9. **配色一律由 CSS 类驱动**：状态/分类配色写成 `.x` + `body.dark .x`（同元素多类时用 `body.dark .x.y` 提特异性），**禁止用 `el.style.color/background` 内联下发**——内联样式恒压过任何选择器（含 `body.dark …`），会把暗色配色**静默吃掉**。F6 事故即此：11 组暗色 chip 全部失效，且亮色另有 4 组不达 AA，页面上却看不出报错。
10. 改配色时**亮/暗必须在同一次改动内成对写**，并加测试锁住（参考 `test_tagchip_contrast.py`：逐行锚定解析 + 类别集一致性 + 11×2 对 ≥4.5）

**Don'ts**
1. 禁止 11.5 / 12.5 / 13.5px 等半像素级字号
2. 禁止字重 700+（中文小字会糊）
3. 禁止纯黑 `rgba(0,0,0,…)` 阴影（浅灰底上发脏）
4. 禁止用 `opacity` 处理已读态与禁用态
5. 禁止同一层级出现两种间距值
6. 禁止渐变、发光、装饰性动效
   > **v3 例外 · H2**：移动端底部「问」tab 的 AI 球保留 `linear-gradient(135deg,#6366f1,#8b5cf6,#22d3ee)` + 外发光 + `qaOrbPulse` 脉冲——它是**全页唯一**的 AI 入口，需要与其它 tab 在视觉上强区分（已决定保留，勿"顺手清零"）。除它以外不得再新增渐变/发光/装饰动效。
7. 禁止为「好看」增加信息密度之外的装饰元素
8. 禁止在深色模式沿用浅色阴影值
9. 禁止在 `app.js` 里为**主题/分类配色**写 `style.color` / `style.background`（同 Do's 9）；需要状态配色就加 class，别绕道内联

---

## 8. Responsive Behavior（响应式行为）

### 8.1 Breakpoints

| 名称 | 范围 | 关键变化 |
|---|---|---|
| xs 手机 | <480px | 单列，卡片内边距 12px，隐藏次要元信息 |
| sm 大屏手机 | 480–767px | 单列，价格区 1 列 |
| md 平板 | 768–1100px | 单列，右栏降级为顶部横条 |
| lg 桌面 | 1101–1439px | **双栏**：主列 + 300px 右栏 |
| xl 宽屏 | ≥1440px | 双栏，右栏 320px，容器 1360px |

### 8.2 Touch Targets

移动端所有可点击元素最小 **44×44px**；图标按钮通过 padding 扩展触控区，不放大图标本身。

### 8.3 折叠策略

- ≥1101px：会展、热榜进右栏 sticky
- <1101px：右栏内容按「热榜 → 会展」顺序降级为主列顶部横条，条目保留可搜索
- 矿权列表移动端从紧凑行改单条卡片（字段纵向排列）

### 8.4 Font Scaling

字号**不随断点缩放**（13px 中文在手机上已是最低可读值）。仅卡片内边距 16→12px、区块间距 32→24px 收紧。

> **v3 例外 · 移动端信息流放大（有意为之，测试锁定）**
> `@media(max-width:768px)` 段把 `.news-title` 提到 **16px**、`.news-summary` 提到 **14px**，同时把 `.news-item` 从「分隔线列表行」改成**卡片**（`1px --line-2` + `--r-lg` + `--shadow-sm`，`body.dark` 下背景回落 `--bg`、边框 `--line-1`）——目的是让手机上的信息流不那么空。这是**有意的例外**，由 `test_mobile_ux_batch.js:65-67` 锁定，不是遗留硬编码。
>
> ⚠️ **已知级联问题（v3 记录，暂不修）**：同文件内 `@media(max-width:600px)` 段（**源序在 768 段之后**）又把 `.news-title` 收回 `--fs-h3`(14px)、`.news-summary` 收回 `--fs-meta`(12px) 并加 3 行截断，`@media(max-width:360px)` 段另给 15px。同特异性下**后出现者胜**，因此 16px **实际只作用于 601–768px 窗口**，手机（<600px）仍是 14px。若确实期望手机也放大，需调换源序或把放大规则改挂更窄断点——属**待决项**，不要在无测试的情况下顺手改数字。

---

## 9. Agent Prompt Guide（AI 代理提示指南）

### 9.1 Quick Reference（快速参考）

```
色(亮)：ink-900 #16202b / ink-700 #3d4b5a / ink-500 #5f6d7a / ink-300 #64737f
线：#e5eaf0(--line-1) / 控件边 #d5dde5(--line-2) | 面：#f5f7fa(--bg) / #fff(--surface) / #eef2f6(--surface-3)
品牌：--brand #0e7490 / 深 #0b5a70 / 浅底 #e6f4f7 / hover #0f788d
语义：涨 --up #d93a2b 跌 --down #0e7a52 警告 --warning #966319 危险 --danger #c0392b 信息 --info #0e7490
  平：用 --ink-500；~~--flat #6b7a89~~ 已失效（0 引用，勿新用）
暗(全部由 body.dark{} 同名覆盖)：底 #141b24 / 卡 #1b2430 / 面2 #202b38 / 面3 #26313f / 线 #2a3542·#35424f
  ink 900/700/500/300 = #e8eef3 / #b6c2ce / #8b9bad / #8394a5；品牌→#38bdf8；涨跌→#ff6b5b / #35c48d；warning→#e0a83a
  ⚠️ 没有 --dark-bg / --dark-surface / --dark-* 这套变量，机制就是「同名覆盖」
字：24/20/16/14/13/12/10 — 字重仅 400/500/600 — 禁半像素级
圆角：4(徽章) / 8(控件) / 12(卡片) — pill 控件用 999 或自一致半高（34–38px 高）
间距：--s1..--s6 = 4/8/12/16/24/32（另有 --s7 40px，仅空状态用）— 卡内 16 — 区块间 32
阴影：0 1px 3px rgba(0,55,112,.06) — 深色模式关阴影(--shadow-xs/sm/md→none)用边框
z：sticky 100 / sidebar 200 / fab 900 / mask 1000 / dialog 1010 / toast 1100 / **critical 1200**（#mdBootWarn 逃生横幅用 --z-critical:1200，2026-09-11 收敛自 99999）
动效：120ms ease，仅 hover/focus
```

### 9.2 Component Prompts（可直接复制）

1. **新闻条目卡片**
   > 生成一个新闻列表项：14px/500 标题（hover 变 `var(--accent-hover)` #0f788d）、12px 元信息行（来源 · 时间 · 分类 chip）、13px/1.6 摘要两行截断，卡片 16px 内边距、12px 圆角、1px `var(--line-1)` 边框。已读态标题与摘要转 `var(--ink-300)`，不用 opacity。

2. **价格数据行**
   > 生成紧凑价格行：左品种名 12px（`.pc-name`，用 `var(--ink-500)`），中价格 15px/600 等宽数字，右涨跌幅 12px（`.pc-chg`；涨 `var(--up)` 跌 `var(--down)`，平用 `var(--ink-500)`），行高 8px 上下 padding，底边 1px `var(--line-1)`。桌面 2–3 列网格。

3. **区块标题**
   > 生成区块标题：16px/600，左侧 3px `var(--brand)` 竖条，左内边距 12px，上间距 32px 下间距 12px。

4. **筛选器组**
   > 生成横向筛选芯片组：12px、8px 圆角、padding 6px 14px，默认 `var(--surface)` 底 + `var(--line-2)` 边框，选中态 `var(--brand)` 底白字，hover 边框转品牌色。

5. **深色模式卡片**
   > 把这张卡片适配深色模式：背景 #1b2430(`--surface`)，边框 #2a3542(`--line-1`)，`--shadow-xs/sm/md` 置 none，标题 #e8eef3(`--ink-900`)、正文 #b6c2ce(`--ink-700`)、次要 #8b9bad(`--ink-500`)，品牌色转 #38bdf8(`--brand`)。**写 `body.dark{}` 同名覆盖，不要另起 `--dark-*` 变量。**

6. **分类标签 chip（枚举调色板）**
   > 生成分类标签：10px 字号、`var(--r-sm)` 圆角、padding 1px 8px。配色**按类别枚举**，写成 `.tag-chip.tc-<类别>` 与 `body.dark .tag-chip.tc-<类别>` **两组规则**（亮/暗各一套，对比度各自 ≥4.5，共 11 类）。JS 侧 `TAG_STYLE` **只存 label**，绝不设 `chip.style.color/background`；className 形如 `tag-chip tc-metal`，未知类别回落 `.tc-default`。

### 9.3 Iteration Guide（迭代建议 10 条）

1. 先注入 `:root` 变量再替换硬编码，**不要边改边加变量**
2. 替换顺序：颜色 → 字号 → 间距 → 圆角 → 阴影，一次只做一类，便于 diff
3. 改样式**不动 HTML 结构、不改 class 名**（本项目有生成脚本依赖）
4. 每次改动后跑 `test_smoke_0908.js`，25 项全绿再继续
5. 价格区重构只改 CSS 布局，不增删 DOM 节点
6. hover 效果必须有对应 `:focus-visible`，保证键盘可达
7. 深色模式与浅色模式**同一次改动内完成**，避免遗漏
8. 改完必须同时 bump `build-version` 与 `sw.js` 的 `CACHE_NAME`
9. 用真实浏览器截图确认后再部署，不要只看 jsdom
10. 发现「这里好像差一点」时，先回到 token 检查是否用错层级，而不是临时加数值
11. **不要在 JS 里写主题/分类配色的内联样式**（见 §7 Do's 9）；状态配色一律加 class，暗色用 `body.dark .x.y` 提特异性。这是 F6 事故的根因，且**内联样式失效时页面不报错**——只是"没生效"，肉眼很容易放过
12. 改完配色/结构后跑一遍**死选择器审计**（`~/.workbuddy/skills/dead-css-selector-audit`）：删 CSS 前只删「生产代码零引用」的 A 级项，B 级（JS 里出现过但不在 `class=` 位置）默认视为存活；反过来新增 class 后也要确认 CSS 真的命中
13. 任何「看起来是错的」值，先分清是**规范过期**还是**实现漏改**：若实现值被测试锁定且对比度更优，改的是规范（v3 原则），不是实现
14. **CSS 注释内禁止出现「星号紧跟斜杠」的连续两字符**——会提前闭合注释，浏览器按无效选择器丢弃下一条规则，审计脚本也会把注释文字当成选择器（2026-09-11 实测踩到过）

---

## 附录 A：品牌参考与混搭理由

| 来源 | 取用部分 | 理由 |
|---|---|---|
| **Linear** | 密度与排版节奏：12/13/14 三级正文体系、4px 间距基数、极简边框、微阴影、弱化装饰 | 同为「高频扫读的信息流」，其行高与间距比例可直接套用于新闻列表 |
| **Stripe** | 数据可信感：深蓝文字 `#0d253d` 系、专业灰 `#64748d`、低饱和蓝调阴影 `rgba(0,55,112,.08)`、表格数据呈现 | 本页含大量行情数字，需要金融级的专业与可信 |
| **IBM Carbon** | 中性灰阶与无障碍：`#161616` 级深文字、`#f4f4f4` 底、`#e0e0e0` 线、明确对比度门槛、克制圆角 | 面向企业与政府信源的日报，需要 IBM 式的严谨与可读性保障 |

**未取用**：Linear 的紫色主调（与行业调性不符，改用品牌青蓝 `#0e7490`）、Stripe 的渐变（违反零装饰原则）、IBM 的直角（改 12px 圆角提升亲和力）。

## 附录 B：对 v1（docs/design-spec.html）的审阅修订

| # | v1 问题 | v2 修订 |
|---|---|---|
| 1 | 只有颜色与字号，**缺组件级 CSS**（按钮/输入/导航/弹窗无参数） | 补齐 4.1–4.7 全部组件的可复制 CSS |
| 2 | 缺阴影与层级体系 | 新增第 6 章：5 层蓝调阴影 + z-index 规范 + 深色模式去阴影 |
| 3 | 缺响应式细节 | 新增第 8 章：5 个断点 + 44px 触控 + 折叠策略 |
| 4 | 字号 6 级但未标字重与字距 | 补全 Type Scale 的 weight / line-height / letter-spacing，并限定字重仅 3 档 |
| 5 | 已读态只提了「用文字色」 | 明确写入组件 CSS 并列入 Don'ts（禁 opacity） |
| 6 | 无品牌参考依据 | 新增附录 A：Linear + Stripe + IBM 混搭与取用/舍弃说明 |
| 7 | 无 Do's / Don'ts 与代理提示 | 补齐第 7、9 章 |
| 8 | 未说明深色模式阴影策略 | 明确：深色关闭阴影，改用亮边框表达层级 |

## 附录 C：项目硬约束（改样式时不可破坏）

- `class="section" id="todaySection" / "archiveSection" / "rightsSection"` 三个锚点字符串必须原样保留——每日 `generate_YYYYMMDD.py` 靠它切分动态区
- 会展 IIFE 关键词 `EXPO_WORDS` / `window.__expoIsExpo` / `#expoMini`、热榜 `#hotListSection`、矿权 `.rights-list` / `.rights-row` 选择器不得改名
- 改完 index.html 必须 bump `<meta name="build-version">`，改完 sw.js 必须 bump `CACHE_NAME`
- 验证链：`preflight_check.py` → `test_smoke_0908.js` → `deploy_pages.py`（唯一推送源）

## 附录 D：v2 → v3 规范对账表（2026-09-11）

**v3 修订原则**：规范与实现冲突时，**以实现为准**——因为所有偏离都是经过实测的无障碍修正、且被测试锁定；滞后的是规范，不是代码。下表逐条列出 v2 写了什么、实现实际是什么、v3 怎么处理。

| # | 位置 | v2 原描述 | 实现现状 | 判定 | v3 处理 |
|---|---|---|---|---|---|
| 1 | §2.1 | `--ink-500 #6b7a89`（对比度 4.40，**自身不达 AA**） | `#5f6d7a`（5.31） | 规范错 | 改为实现值 |
| 2 | §2.1 | `--ink-300 #94a3b8`（2.56，**严重不达**） | `#64737f`（4.88） | 规范错 | 改为实现值 |
| 3 | §2.4 | `--down #128a5f`（4.35） | `#0e7a52`（5.35） | 规范错 | 改为实现值 |
| 4 | §2.4 | `--warning #b7791f`（3.64） | `#966319`（5.13） | 规范错 | 改为实现值 |
| 5 | §2.4 | `--flat` 作为「平」色 | 仅 `:root`/`body.dark` 两处**声明**，`var(--flat)` **0 处使用** | 死 token | 标 `~~已失效~~`；「平」用 `--ink-500` |
| 6 | §2.2 | `--dark-bg / --dark-surface / --dark-line / --dark-ink` | **四个都不存在**；机制是 `body.dark{}` **同名覆盖** | 规范错 | 重写机制说明，禁新造 `--dark-*` |
| 7 | §2.3 | `--focus-ring` | 不存在；焦点环用字面 `rgba(14,116,144,.25)`（3 处） | 规范错 | 删变量说明 |
| 8 | §2.6 | `--shadow-color-sm/md/lg` | 不存在；正确用法是 §6.1 的 5 条完整阴影 | 规范错 | 替换为说明 |
| 9 | §4.1 | 控件统一 32px 高 / 8px 圆角 | pill（药丸）控件 34–38px / 999px 或 19–20px | 实现超越规范 | 补「pill 例外」段 |
| 10 | §4.3 | placeholder `#94a3b8` | `#64737f` | 同 #2 | 改实现值 |
| 11 | §4.5 | `.tag-chip` 单一配色 | **11 组按类别枚举**，亮/暗各一套 | 规范缺章节 | 补完整对照表 + 实现规则 |
| 12 | §4.7 | `.news-sum` / `.px-name` / `.px-val` / `.px-chg` / `.sec-title` | 线上实为 `.news-summary` / `.pc-name` / `.pc-value` / `.pc-chg` / `.section-title` | 规范错（v1 遗留名） | 全部改名 + 加警示 |
| 13 | §5.1 | 间距 6 级 | 另有 `--s7:40px`（空状态专用） | 规范不全 | 补一行 + 限定用途 |
| 14 | §6.3 | z-index 表最大 1100 | `#mdBootWarn` 用 `99999` | 实现例外 | **已收敛**（2026-09-11）→ 新增 `--z-critical:1200`，横幅改 `var(--z-critical)`，表上限升至 1200 |
| 15 | §7 | Do's 1「禁硬编码颜色」 | 枚举 chip **必须**写 HEX | 规范自相矛盾 | 加「枚举调色板」例外 |
| 16 | §7 | Don'ts 6「禁渐变/发光」 | 「问」球是渐变 + 发光 + 脉冲 | 实现例外 | 登记 H2 例外（**决定保留**） |
| 17 | §8.4 | 「字号不随断点缩放」 | `@768` 有意放大 `.news-title`→16px / `.news-summary`→14px | 实现例外 | 登记例外，并记录 `@600` 反向收回的级联问题 |
| 18 | §9.1 / §9.2 | 提示词含 `#6b7a89` / `#94a3b8` / `#128a5f` / `#b7791f` / `#128fa8` | 均已换新值 | 规范过期 | 全量同步，并新增 1 条 chip 提示 |
| 19 | 附录 C | 锚点写作 `#col-rail` | 页面元素是 `<aside class="col-rail">`（**无 id**），原规则全部失效 | 规范错 | 已修为 `.col-rail` |

**v3 已完成：死 CSS 清理（2026-09-11）**

原评审报告给出「80 条死选择器」，**该数字不准确**——它是审计脚本两个盲区叠加的结果。修正后实测并已清理：

| 项 | 数值 |
|---|---|
| 内联 CSS 声明的类 | 413（修正后；原报 424 含注释文本误判） |
| 判定为零引用的 A 级死类 | **70**（原报 80） |
| 删除的规则 | **119 条整条 + 7 条部分选择器** |
| index.html 体积 | 329,729 → 319,254 字节（**−3.2%**） |
| 清理后 A 级死类 | **0**（不变量，可复跑审计验证） |

**审计脚本的两个盲区（已修，都会导致误删活代码）**

1. **字符串拼接构造类名**被当成「零引用」。例：`chip.className='tag-chip tc-'+类别` —— 完整类名 `tc-metal` 等在源码里从不整体出现，于是 **11 个刚加的 F6 活类全部被判死**。修正：字面量**以 `-` 结尾**且该行含 class 语境时，把尾部 `xxx-` 视作前缀，凡以此前缀开头的已声明类一律视为存活。⚠️ 关键细节：**不能**对任意字面量取「以 `-` 结尾的片段」——`'rc-normal'` 会被错误地截出前缀 `rc-`，从而把真正死掉的 `.rc-grid/.rc-title/...` 全部救活，清理就失效了。
2. **CSS 注释被当作选择器**。`/* … */` 里的类名会进入「已声明」集合（`.px-row`/`.qa-ai` 就是这么来的），属性选择器 `[href$=".js"]` 也会被截出假类名 `.js`。修正：解析前把注释**等长置空**（保持偏移可用），并先剥掉 `[...]` 再取类名。

**顺带修掉一个真实 bug**：警示注释里写了 `.rc-grid*/.rc-region/...`，其中「星号紧跟斜杠」**提前闭合了 CSS 注释**，使后续文字被当成选择器 → 浏览器按无效选择器丢弃了下一条规则（`.rights-card`），审计脚本同样误解析。全仓 `/*` 与 `*/` 计数因此不配平（114 vs 116）。已重写该注释，并立规矩：**CSS 注释内禁止出现「星号紧跟斜杠」的连续两字符**。

**扫描集必须收敛**：`docs/`（v1 设计稿）、`tmp/`（备份与预览副本）、`*.bak*`、`*preview*.html` 都会污染结果——它们含历史类名（`.px-val`/`.sec-title`）或旧版整页副本，会把真死类「救活」或把假类名塞进声明集。只扫生产文件。

**保留项（不动）**

- `.rc-deadline`（含 `.rc-urgent/.rc-soon/.rc-normal/.rc-expired`）与 `.rc-extra` —— 仍由 `renderRightsSection()` 输出，属 B 级存活。
- 全部 **B 级「疑似」类**（`.ai`/`.notice`/`.risk`/`.user`/`.loading`/`.na`/`.au-*`/`.lv-major`/`.pchart-up|down`/`.rc-*` 四态/`#*Section` 同名类等）：它们在 JS 里被赋值或出现在 JS 字符串中，脚本无法证明其死亡 → **默认视为存活**。宁可留白，不可误删。

**验证方式（三层）**

1. 结构：10 个 `<style>` 块括号全平衡、无 `,{` / `{，` / 连续逗号 / 空 `@media` 残留；声明类集合只减不增（消失项必须恰好是已判定删除的那些）。
2. 渲染：把页面跑进 jsdom（真实 defer 语义）后收集**渲染后 DOM 的全部类名**，与被删的 70 个类求差集 → **0 命中**；同时 6 张价格卡仍与 `lme_data.json` 一致、无 JS 报错、无残留占位符（`_tmp/_dead_class_render_check.js`，10/0）。
3. 回归：全部 jsdom 套件 + Python 闸门通过。唯一失败 `test_smoke_0908` ⑪ 已用 HEAD 快照复跑确认为**既存失败**（非回归）。
   ⚠️ 清理时发现 `test_p3_20260910.js` 曾把 `.ba-mkt`/`.rr-date` 当「必须存在」的名锚点——这两个类早已不渲染，断言是「靠残留 CSS 才成立」的空洞断言。已把锚点换成仍渲染的 `.rr-region`。

**仍未处理（另立专项）**

- **`--ink-300` on `--surface-3` = 4.34/4.23**（差 0.16 未达 4.5，共 2 处：`.toc-count-fresh.is-empty`、`.rc-deadline.rc-expired`）——**接受现状**。将来修法是新增一个更深的灰 token，**不是**抬高 `--ink-300`（会连带影响正文对比）。
- **移动端「会议」tab 与会展条目重复**（评审项 A4）——**已修复**（2026-09-11）：根因是 expo/vault IIFE 的 `init()` 开头 `if(!isDesktop()) return;` 把 vault 迁移也挡在移动端外，会展条目既留主信息流又进「会议」tab。改为「vault 迁移在所有视口执行、仅桌面迷你卡由 isDesktop() 把关」，重复源消除；回归测试见 `test_a4_expo_mobile.js`。
- **`#mdBootWarn` 的 `z-index:99999`** —— **已收敛**（2026-09-11）：改为 `var(--z-critical)`（1200），新增 `--z-critical` token，表上限升至 1200。详见 §6.3 例外处置结论。

**验证入口**：`test_tagchip_contrast.py`(19) · `test_mobile_ux_batch.js` · `test_preflight_div.py`(11) · `preflight_check.py` · `_tmp/_dead_class_render_check.js`(10)。

**审计工具**：`~/.workbuddy/skills/dead-css-selector-audit`（已按上述两个盲区更新）。


