# 视觉规范评审（Visual-Spec Review）— mining-daily

> 评审日期：2026-09-11 · 针对线上构建 `20260911-1804`（含 UX 横幅分级 ①②③④⑤）
> 范围：颜色对比度（WCAG 1.4.3 文本 ≥4.5:1、1.4.11 非文本/图标 ≥3:1）、层级 z-index、暗色 token 一致性
> 方法：扫描 `index.html` 全量 `<style>`，对每条声明实算对比度（非估算），并交叉核对 `DESIGN.md` v3 已登记项
> 性质：**只读评审，未改动任何代码**。所有修复建议待用户确认后实施（原约束「先出方案给我看」）

---

## 一、P1 — 对比度不达标（文本 < 4.5:1，需修复）

| # | 选择器（文件:行） | 当前值 | 实测对比度 | 问题 | 建议修复 |
|---|---|---|---|---|---|
| P1-1 | `.qa-float-tip` `index.html:579` | `color:#8a98a6` on `--surface` | **2.93:1** | 问答面板底部提示（10px）远低于 AA | 改 `var(--ink-300)`（`#64737f` 4.88）；暗色 `index.html:603` 的 `#7c8a99`→`var(--ink-500)`（4.42，临界，建议同步压到 `#8394a5`） |
| P1-2 | `.expo-mini-date` `index.html:1146` | `color:#93a3b2` | **2.59:1** | 会展迷你卡日期（10px）几乎不可读 | 改 `var(--ink-300)` 或 `var(--ink-500)` |
| P1-3 | `.pchart-down` `index.html:451` | `color:#27ae60` | **2.87:1** | ① 对比度不达标；② 用了硬编码绿而非 `--down`，语义色被绕过 | 改 `var(--down)`（`#0e7a52` 5.35，且中国习惯「跌=绿」语义正确）；暗色 `index.html:893` 的 `#5fd39a` 已达标，保留 |
| P1-4 | `.au-media` `index.html:401` | `color:#6b7280` on `#f0f4f8` | **4.37:1** | 仅差 0.13，临界未达 | 改 `var(--ink-500)`（`#5f6d7a` 5.53）；暗色 `index.html:405` 已用 `--ink-500`，达标 |
| P1-5 | `.nf-count` `index.html:1172` | `color:#5b7a99` | **4.49:1** | 仅差 0.01，临界未达（暗色已在 `index.html:1170` 修复为 `--ink-500` 5.34） | 亮色改 `var(--ink-500)`（`#5f6d7a` 6.11） |
| P1-6 | `.price-card.up .pc-chg`（`--up` on `--surface-2`） | `color:var(--up)` | **4.31:1**（on `--surface-2` `#f5f7fa`） | `--up`(#d93a2b) 在白底 4.57 达标，但价格条背景为 `--surface-2` 时跌到 4.31 | 确认价格卡背景走 `--surface`(白) 而非 `--surface-2`；若必须浅灰底，则涨跌幅改深色文字或抬 `--up` 本体（会牵连全局，需评估） |
| P1-7 | `body.dark .ai-empty/.ai-disabled` `index.html:639` | `color:#64748b` on 暗 `--surface` | **3.28:1** | 暗色硬编码灰，绕过了 `--ink-*` | 改 `var(--ink-300)`（暗 `#8394a5`，4.98 达标） |
| P1-8 | `body.dark .toc-count-fresh` `index.html:67` | 白字 on `background:#e74c3c` | **3.82:1** | 计数徽章白字在暗红底不达标 | ⚠️ **修正**：不能改 `var(--up)` 暗（`#ff6b5b` 白字仅 2.80，更差）。正确做法是暗色徽章底用**深红** `#d93a2b`（白字 4.57，与亮色同源），即 `body.dark .toc-count-fresh{color:#fff;background:#d93a2b}` |
| P1-9 | `.ai-keybox button` `index.html:629` | 白字 on `#3b82f6` | **3.76:1** | 提交按钮白字在蓝底不达标 | 按钮底改 `#2563eb`（已是 `:hover` 色，白字 5.19 达标）；或改 `var(--brand)`(`#0e7490` 白字 8.6) |

> 注：P1-1 / P1-8 / P1-9 为「白字 on 彩色底」型，修复本质是**压暗底色**而非换文字色；P1-3 / P1-4 / P1-5 / P1-7 为「灰字 on 浅/暗底」型，修复是**改用 token 灰**。

---

## 二、P2 — 次级问题（图标 3:1 或层级/规范一致性）

| # | 选择器（文件:行） | 问题 | 建议 |
|---|---|---|---|
| P2-1 | `.btn-star`(移动) `index.html:1029` | `color:#bdc3c7` on 白 = **1.81:1**，星标图标不达 3:1 | 移除移动端覆盖或改 `var(--ink-500)`；桌面 `index.html:231` 的 `#6b7a89`(4.83) 已达标 |
| P2-2 | `body.dark .btn-star` `index.html:843` | `color:#5a6875` on 暗底 = **2.71:1** | 改 `var(--ink-500)` 暗（`#8b9bad` 3.95，过图标 3:1） |
| P2-3 | `body.dark .btn-unread:hover` `index.html:846` | 白字 on `#2f8f7d` = **3.96:1** | 压暗底到 `#1f7a68` 类深青，使白字 ≥4.5 |
| P2-4 | `#mdBootWarn z-index:99999` | 超出 `DESIGN.md §6.3` z 表上限（1100） | `DESIGN.md` 已登记「观察 1 天后收敛」；自愈链已稳定（④⑤ 已上线 1 天+），建议收敛到新增 `--z-critical:1200` 并同步更新 §6.3 与 §9.1 |
| P2-5 | `.md-region-stuck` 内联色 `app.js:1732+` | ④⑤ 注入 `.md-region-stuck` 时写死 `border/color/background` 字面量 | 违反 F6 教训（内联恒压过 `body.dark`）。建议抽成 `.md-region-stuck` 类 + `body.dark .md-region-stuck` 两条规则，与 `.tag-chip.tc-*` 同机制 |

---

## 三、nit（可接受 / 待决策，不阻塞）

- 暗色多处硬编码灰（`#7c8a99`/`#64748b`/`#5a6875` 等）对比度若够格却绕过 `--ink-*` token —— 与 P1-7 同源，建议统一迁 token。
- `#mdBootWarn` 红 `#7f1d1d` / 琥黄 `#b45309` 为内联字面值（P2-4 同源）——**有意保留**：横幅须在任何主题下恒为红/琥黄，不可被 `body.dark` 覆盖；与 `--danger` 语义不同，属例外。
- `.qa-fu-chip` 14px 圆角（非 4/8/12 体系）、个别间距非 4 倍数、`.news-title` 15px（非 14 token）——低密度装饰性偏离，按 DESIGN.md「间距/字号同源」原则可后续统一，非紧急。

---

## 四、近期改动复核（已确认达标，不回退）

- **横幅分级 ①②③④⑤**：error 级白字 on `#7f1d1d`=10.02、info 级白字 on `#b45309`=5.02、单组件标注 `.md-region-stuck` 琥黄 ~4.9 —— 全部达标且分级正确。
- **死 CSS 清理**：命名死类 0 引用（审计脚本两盲区已修），`DESIGN.md` 附录 D 已登记。
- **`--ink-300` 暗色修正**：`#8394a5`(5.03) 已生效。
- **`.qa-table-wrap` 横滑**：`index.html:1936` 已配 `overflow-x:auto`，不再静默失效。
- **tag-chip 11×2**：`test_tagchip_contrast.py`(19) 全绿，且 `app.js` 已无 `chip.style.color/background` 内联（F6 根因消除）。

---

## 五、历史未决项现状（来自 DESIGN.md 附录 D）

| 项 | 状态 |
|---|---|
| `--ink-300` on `--surface-3` = 4.34/4.23（2 处） | **接受**（差 0.16），将来新增更深灰 token 而非抬 `--ink-300` |
| `#mdBootWarn z-index:99999` | 待收敛（见 P2-4） |
| 移动端「会议」tab 与会展条目重复（A4） | **产品决策，维持现状**（详见 `ux-ia-product-2026-09-11.md` 附 D） |

---

## 六、建议修复顺序（待确认）

1. **P1-8 / P1-9 / P1-3**（白字 on 彩色底类，最醒目、修复最小）— 各 1 行 CSS
2. **P1-1 / P1-2 / P1-4 / P1-5 / P1-7**（灰字改 token 类）— 各 1 行 CSS，建议成对写亮/暗
3. **P1-6**（需先确认价格条背景层级）
4. **P2-1/2/3**（图标 3:1，移动/暗色边界）
5. **P2-4/5**（层级收敛 + 抽类，结构改动，单独一轮并 bump build）

> 全部为 CSS 改动，需同步 bump `build-version` 与 `sw.js CACHE_NAME`，跑 `test_tagchip_contrast.py` + `preflight_check.py` 后部署。
