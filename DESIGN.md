# DESIGN.md — 矿业日报（mining-daily）

> 版本 v2 · 2026-09-08 · 设计系统架构：Diana
> 参考混搭：**Linear 的密度与排版节奏 + Stripe 的数据可信感 + IBM Carbon 的中性灰阶与无障碍标准**
> 定位：中文行业资讯 + 行情数据的**高密度阅读型**静态页（PWA），桌面双栏、移动单列。
> 目标行数 280-350 · 所有数值可直接复制使用 · 供 AI 编程代理消费

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

**光影与质感**：纯扁平 + 极低饱和阴影。阴影色统一走 `rgba(0, 55, 112, …)` 蓝调（取自 Stripe），避免中性黑阴影在浅灰底上发脏。深色模式不用阴影，改用 1px 亮边框表达层级。

---

## 2. Color Palette & Roles（调色板与角色）

### 2.1 Primary / Neutral 中性灰阶（IBM Carbon 对比度标准）

| 角色 | CSS 变量 | HEX | 使用场景 |
|---|---|---|---|
| 标题文字 | `--ink-900` | `#16202b` | 页面标题、卡片标题（对比度 15.3:1） |
| 正文文字 | `--ink-700` | `#3d4b5a` | 摘要、列表正文（8.9:1） |
| 次要文字 | `--ink-500` | `#6b7a89` | 来源、时间、表头（4.9:1，满足 AA） |
| 弱化文字 | `--ink-300` | `#94a3b8` | 已读条目、占位提示（**不用于正文**） |
| 分隔线 | `--line-1` | `#e5eaf0` | 卡片内分隔、列表项之间 |
| 控件边框 | `--line-2` | `#d5dde5` | 输入框、按钮、筛选器边框 |

### 2.2 Brand & Dark 品牌与深色

| 角色 | CSS 变量 | HEX | 使用场景 |
|---|---|---|---|
| 品牌主色 | `--brand` | `#0e7490` | 选中态背景、链接、区块竖条 |
| 品牌深色 | `--brand-ink` | `#0b5a70` | 品牌文字、hover 态（7.2:1） |
| 品牌浅底 | `--brand-soft` | `#e6f4f7` | NEW 徽章底、选中项浅底 |
| 深色模式底 | `--dark-bg` | `#141b24` | `body.dark` 页面底 |
| 深色模式卡 | `--dark-surface` | `#1b2430` | 深色卡片 |
| 深色模式线 | `--dark-line` | `#2a3542` | 深色分隔与边框 |
| 深色模式字 | `--dark-ink` | `#e8eef3` | 深色正文（13.8:1） |

### 2.3 Accent / Interactive 强调与交互

| 角色 | CSS 变量 | HEX | 使用场景 |
|---|---|---|---|
| 链接 hover | `--accent-hover` | `#128fa8` | 标题 hover 色 |
| 聚焦环 | `--focus-ring` | `#0e749040` | 键盘聚焦 2px 外环 |
| 战略徽章 | `--tag-strategy` | `#4f46e5` | 「战略」徽章文字 |
| 重大徽章 | `--tag-major` | `#d93a2b` | 「重大」徽章文字 |

### 2.4 Semantic 语义色（中国市场习惯：涨红跌绿）

| 角色 | CSS 变量 | HEX | 使用场景 |
|---|---|---|---|
| 涨 / 上升 | `--up` | `#d93a2b` | 价格上涨、正向变化 |
| 跌 / 下降 | `--down` | `#128a5f` | 价格下跌、负向变化 |
| 平 / 持平 | `--flat` | `#6b7a89` | 无变化 |
| 成功 | `--success` | `#128a5f` | 操作成功提示 |
| 警告 | `--warning` | `#b7791f` | 数据过期、待确认 |
| 危险 | `--danger` | `#c0392b` | 删除、失效链接 |
| 信息 | `--info` | `#0e7490` | 说明、提示条 |

### 2.5 Surface 表面层级

| 层级 | CSS 变量 | HEX |
|---|---|---|
| 页面底 | `--bg` | `#f5f7fa` |
| 卡片 / 面板 | `--surface` | `#ffffff` |
| 次级块（表头、代码块） | `--surface-2` | `#f5f7fa` |
| 三级块（芯片、标签底） | `--surface-3` | `#eef2f6` |

### 2.6 Shadow Colors 阴影色

统一蓝调，禁止纯黑阴影：
```css
--shadow-color-sm: rgba(0, 55, 112, 0.06);
--shadow-color-md: rgba(0, 55, 112, 0.08);
--shadow-color-lg: rgba(16, 32, 43, 0.12);
```

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
.btn-ghost{background:transparent;color:#6b7a89;border:1px solid transparent;
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
.input::placeholder{color:#94a3b8}
.input:focus{border-color:#0e7490;outline:none;
  box-shadow:0 0 0 3px rgba(14,116,144,.12)}
```

### 4.4 Navigation（侧栏目录 / 顶部工具条）

```css
.nav-item{font-size:13px;color:#6b7a89;padding:7px 12px;border-radius:8px;
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
.tag-chip{font-size:12px;padding:2px 8px;border-radius:4px;
  background:#eef2f6;color:#3d4b5a}
```
**硬约束**：每条新闻 `.tag-chip` ≤ 2 个，徽章 ≤ 2 个。

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

**新闻条目（核心组件）**
```css
.news-item{padding:12px 16px;border-bottom:1px solid #e5eaf0;background:#fff}
.news-title{font-size:14px;font-weight:500;line-height:1.5;color:#16202b}
.news-meta{font-size:12px;color:#6b7a89;margin-top:4px;display:flex;gap:8px}
.news-sum{font-size:13px;line-height:1.6;color:#3d4b5a;margin-top:6px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.news-item.read .news-title{color:#94a3b8}
.news-item.read .news-sum{color:#94a3b8}
```
> **关键修订**：已读态用 `--ink-300` 文字色，**不用** `opacity:.55`——透明度会让 13px 中文在白底上发灰模糊。

**价格行（密度核心）**
```css
.px-row{display:grid;grid-template-columns:1fr auto auto;gap:12px;
  padding:8px 0;border-bottom:1px solid #e5eaf0;align-items:baseline}
.px-name{font-size:12px;color:#6b7a89}
.px-val{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums;
  font-family:var(--font-num)}
.px-chg{font-size:12px;font-variant-numeric:tabular-nums;min-width:56px;text-align:right}
.px-chg.up{color:#d93a2b} .px-chg.down{color:#128a5f}
```

**区块标题**
```css
.sec-title{font-size:16px;font-weight:600;line-height:1.4;color:#16202b;
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

### 6.4 Backdrop Effects

侧栏与弹窗遮罩可用 `backdrop-filter: blur(4px)`；**主内容区禁用毛玻璃**（会降低文字对比度且拖慢低端机渲染）。

---

## 7. Do's and Don'ts

**Do's**
1. 所有颜色、字号、间距、圆角**必须走 CSS 变量**，禁止硬编码
2. 价格、涨跌幅、计数一律 `tabular-nums`
3. 已读态用文字色降级，不用整块透明度
4. hover / focus 过渡统一 120ms，`ease`
5. 每个可交互元素都有 `:focus-visible` 焦点环
6. 区块间距 32px、卡片间距 16px，同层级保持一致
7. 强调色全页占比 < 5%，只用于关键信息与选中态
8. 深色模式用边框而非阴影表达层级

**Don'ts**
1. 禁止 11.5 / 12.5 / 13.5px 等半像素级字号
2. 禁止字重 700+（中文小字会糊）
3. 禁止纯黑 `rgba(0,0,0,…)` 阴影（浅灰底上发脏）
4. 禁止用 `opacity` 处理已读态与禁用态
5. 禁止同一层级出现两种间距值
6. 禁止渐变、发光、装饰性动效
7. 禁止为「好看」增加信息密度之外的装饰元素
8. 禁止在深色模式沿用浅色阴影值

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

---

## 9. Agent Prompt Guide（AI 代理提示指南）

### 9.1 Quick Reference（快速参考）

```
色：ink-900 #16202b / ink-700 #3d4b5a / ink-500 #6b7a89 / ink-300 #94a3b8
线：#e5eaf0 / 控件边 #d5dde5 | 面：#f5f7fa / #fff / #eef2f6
品牌：#0e7490 / 深 #0b5a70 / 浅底 #e6f4f7
语义：涨 #d93a2b 跌 #128a5f 警告 #b7791f 危险 #c0392b
字：24/20/16/14/13/12/10 — 字重仅 400/500/600 — 禁半像素级
圆角：4(徽章) / 8(控件) / 12(卡片)
间距：4/8/12/16/24/32 — 卡内 16 — 区块间 32
阴影：0 1px 3px rgba(0,55,112,.06) — 深色模式关阴影用边框
动效：120ms ease，仅 hover/focus
```

### 9.2 Component Prompts（可直接复制）

1. **新闻条目卡片**
   > 生成一个新闻列表项：14px/500 标题（hover 变 #128fa8）、12px 元信息行（来源 · 时间 · 分类 chip）、13px/1.6 摘要两行截断，卡片 16px 内边距、12px 圆角、1px #e5eaf0 边框。已读态标题与摘要转 #94a3b8，不用 opacity。

2. **价格数据行**
   > 生成紧凑价格行：左品种名 12px，中价格 15px/600 等宽数字，右涨跌幅 12px（涨 #d93a2b 跌 #128a5f 平 #6b7a89），行高 8px 上下 padding，底边 1px #e5eaf0。桌面 2–3 列网格。

3. **区块标题**
   > 生成区块标题：16px/600，左侧 3px #0e7490 竖条，左内边距 12px，上间距 32px 下间距 12px。

4. **筛选器组**
   > 生成横向筛选芯片组：12px、8px 圆角、padding 6px 14px，默认白底 #d5dde5 边框，选中态 #0e7490 底白字，hover 边框转品牌色。

5. **深色模式卡片**
   > 把这张卡片适配深色模式：背景 #1b2430，边框 #2a3542，关闭全部 box-shadow，标题 #e8eef3、正文 #b6c2ce、次要 #8b9bad，品牌色转 #38bdf8。

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
