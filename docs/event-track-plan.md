# 事件跟踪（Event Tracking）模块方案

> 状态：提案草案（未实现，未提交）。2026-10-25 由石语基于 ChatGPT 站审"最建议增加事件跟踪"立项。
> 目标：把散落进每日归档、14 天后即下线的"同一件事的连续进展"聚合成可长期追踪的事件时间线。

## 0.1 决策记录（2026-10-25 刘三拍板）

| 议题 | 结论 |
|---|---|
| 卡片形态 | **右栏新卡 + 移动端「事件」tab**（复用会议日程范式） |
| 自动化程度 | **全自动关联** —— 但落地为「自动聚类 + 人工确认闸门」，绝不静默上线（见 §6.5） |
| 本轮范围 | **仅方案定稿，暂不写代码** |
| 首批种子主题 | 矿权转让 · 并购大单 · 政策/关税（机构铜价分歧暂不入首批） |

---

## 0. 为什么做 / 解决什么痛点

当前站点每条新闻**独立成条、14 天闸门后下线**（会议资讯、会展均如此）。但矿业领域很多事是**跨周/跨月的连续叙事**：

- 一宗并购：宣布拟收购 → 尽职调查 → 签约 → 交割/终止
- 一项政策：征求意见稿 → 发布 → 施行
- 一次勘探：立项 → 阶段性成果 → 资源量核实
- 一场价格/关税博弈：预期 → 落地/落空 → 市场反应

现在的形态下，读者只能靠每天翻新闻自己拼时间线，且旧进展永久消失。事件跟踪 = 给这些**长生命周期叙事**一个常驻入口。

---

## 1. 与现有范式的关系（关键：复用，不另起炉灶）

最贴近的范本就是**「会议日程」模块**（2026-10-21 落地）。它已经验证了完整链路：

| 环节 | 会议日程（已有） | 事件跟踪（本方案） |
|---|---|---|
| 数据源 | `data/conferences.json`（manual+auto） | `data/events.json`（manual+auto） |
| 生成物 | `conference-data.js` → `window.CONFERENCE_DATA` | `event-data.js` → `window.EVENT_DATA` |
| 生成器 | `fetch_conferences.py`（含 `render_js`，逗号分隔红线） | `fetch_events.py`（同构，主要走 `--export-only`） |
| 前端渲染 | `app.js` 会议 IIFE（行 6429–6640） | 新增 `app.js` 事件 IIFE（同构） |
| 卡片锚点 | 右栏 `#expoMini`（index.html:3215） | 右栏新增 `#eventTrack`（紧随其后） |
| 移动端 | `mdMeetingConfHtml()`（行 3669）"会议"tab | 新增"事件"tab 同源渲染 |
| 部署 | `deploy_pages.py` REQUIRED/BUST_FILES 含 `conference-data.js` | 同样挂 `event-data.js` |
| 测试 | `test_conference_schedule.js`（54 断言，CORE） | 新增 `test_event_track.js`（约 40–50 断言，CORE） |

**核心复用点**：
- 新闻库已按月累积在 `data/news_YYYY-MM.json`，每条有**稳定 `id`**（`make_id(url)` = url 的 md5 前 12 位，见 `export_news_json.py:97`）+ `title/url/orig_date_full/category/tags/region/summary`。这是事件时间线"挂新闻"的稳定锚点。
- `regen-proof` 惯例：卡片静态 HTML/CSS 写在 index.html 的 `<style>` 与结构区，每日 `generate_*.py` 只定点替换数据段与 `build-version` 正则（generate_20261025.py:55），**不会冲掉自定义卡片代码**——会议卡已验证成立。
- 上线验证配方：`JSDOM.fromURL(url+'?cb='+Date.now(), {resources:'usable', runScripts:'dangerously', pretendToBeVisual:true})` + `beforeParse` 桩 `fetch`/`matchMedia` + 轮询 `readyState==='complete'` + 过滤 `Not implemented` 噪声（见 MEMORY）。

---

## 2. 数据模型（`data/events.json` / `event-data.js`）

```jsonc
{
  "updated": "2026-10-25",
  "manual": [   // 已采纳、已上线事件（人工维护，脚本永不覆盖）
      "id": "evt_purple_pt",          // 稳定事件 id（人工分配，建议 evt_<主题缩写>）
      "title": "江西安远甲水铂矿探矿权转让",
      "summary": "江西省地质局第七地质大队 → 安远濂江矿业，面积 1.176 km²。",
      "category": "矿权交易",          // 并购与投资 / 政策与法规 / 矿权交易 /
                                       // 勘探与项目 / 市场与价格 / 事故与风险 / 其他
      "status": "进行中",              // 进行中 / 已达成 / 已终止 / 观察中
      "priority": "normal",            // high / normal（影响排序与默认展开）
      "entities": ["安远濂江矿业", "江西省地质局"],  // 供自动建议匹配
      "keywords": ["铂矿", "探矿权转让"],
      "started": "2026-10-24",
      "timeline": [
        {
          "date": "2026-10-24",
          "title": "探矿权转让公示（赣自然探转公示〔2026〕60号）",
          "detail": "公示期 60 日，无异议后进入变更登记。",
          "news": ["c3c1968b894e"],    // 关联新闻 id（稳定锚点，不嵌整条内容）
          "source": "矿业权市场",
          "milestone": true
        }
        // ... 后续节点追加，不删历史
      ]
    }
  ],
  "review": []                        // 自动聚类产出的「待审核」候选（Phase 4）；人工采纳后移入 manual 上线，绝不静默发布
}
```

`render_js` 输出 `window.EVENT_DATA = { updated, source, items:[...] }`，**条目间必须有逗号**（照搬 fetch_conferences.py:564 的 `",\n".join` 红线，否则生成物语法非法 → 卡片整块静默空白）。

---

## 3. 前端形态（桌面 + 移动端）

**右栏卡片**（index.html `<aside class="col-rail">` 内，紧跟 `#expoMini`）：

```
┌─ 🔭 事件跟踪 ──────────────── 共 3 件进行中 ─┐
│ ● 进行中  江西安远甲水铂矿探矿权转让   矿权交易 │
│     转让公示中 · 更新于 1 天前                 │
│   ├ 10-24 探矿权转让公示（里程碑）            │
│   └ 展开时间线 ▾                             │
│ ● 观察中  机构铜价预测分歧：高盛看多vs花旗看空 市场与价格 │
│     更新于 1 天前                              │
│   └ 展开时间线 ▾                             │
│ （已达成/已终止事件默认折叠，点开可见，不显旧）   │
└─ 数据截至 2026-10-25 · 人工维护 ──────────────┘
```

设计要点（与会议卡对齐，差异点加粗）：
- **状态色码**：进行中=蓝/teal，观察中=琥珀，已达成=绿，已终止=灰。复用现有 `.k-机构观点` 一类亮/暗通用配色写法。
- **时间线可折叠**：默认展示最新 1–2 个里程碑 + "展开时间线"按钮（照搬会议卡"展开全部 N 场"交互）。
- **关联新闻可点**：时间线节点上的 `news:[id]` → 在 `window.NEWS_DATA` 里按 id 解析出标题/链接，渲染成可点条目；解析不到则测试报错（红线）。
- **与会议/新闻的本质差异——无 14 天闸门**：事件是长生命周期叙事，active 事件**不按日期下线**，按 `last_update` 倒序 + `priority` 排序；`已达成/已终止` 且超过 N 天无更新的事件降级折叠（不删、不显旧）。
- **移动端**：新增"事件"tab，复用 `mdMeetingConfHtml()` 同源渲染（行 3669）。

---

## 4. 集成点（落地清单）

1. 新增 `data/events.json`（manual 区先手填 2–3 个真实事件）。
2. 新增 `fetch_events.py`：`render_js` 同构 `fetch_conferences.py`，支持 `--export-only` / `--suggest`（建议模式见 §6）。
3. 新增 `event-data.js`（生成物，勿直改）。
4. `app.js` 新增事件 IIFE（`mdEventItems` / `mdEventHtml` / `renderEvent`），挂 `window.__mdEvent`。
5. `index.html`：`<aside class="col-rail">` 内追加 `#eventTrack` 卡片结构 + `<style>` 段 CSS（亮/暗）。
6. `deploy_pages.py`：REQUIRED（行 60）与 BUST_FILES（行 128）追加 `event-data.js`。
7. `generate_*.py`：regen-proof 已天然支持，无需改数据替换逻辑（卡片是静态结构）。
8. 新增 `test_event_track.js`，登记进 `run_tests_all.py` 的 CORE。
9. 上线验证：`JSDOM.fromURL(...?cb=...)` 真跑线上页面，断言卡片渲染 N 件、状态 chip、时间线折叠、新闻 id 可解析。

---

## 5. 分阶段实施

| 阶段 | 内容 | 交付物 | 风险 |
|---|---|---|---|
| **Phase 0** | 定稿 schema + 手填 2–3 个真实 10 月事件（从 `ma_2026-10.json` / 政策新闻取） | `events.json` 种子 | 低 |
| **Phase 1** | `fetch_events.py`（export-only）+ 数据完整性测试 | 生成物 + 测试 | 低 |
| **Phase 2** | `app.js` 事件 IIFE + `index.html` 卡片 + CSS + 移动端 tab | 前端 | 中（CSS 亮暗/折叠） |
| **Phase 3** | `deploy_pages.py` 接入 + 推送 + 线上 jsdom 验证 | 上线 | 中（缓存穿透） |
| **Phase 4（可选）** | 自动建议：扫新闻匹配 `entities/keywords` → `event_suggestions.json`，**绝不自动建事件** | 建议通道 | 低（只读） |
| **Phase 5** | 测试进 CORE + `REFERENCE.md` 写红线 | 文档 | 低 |

---

## 6. 护栏 / 红线（须写入 REFERENCE.md）

1. **人工优先**：`events.json` 的 `manual` 区脚本永不覆盖、永不删除（同 fetch_conferences.py:16）。
2. **生成物逗号分隔**：`render_js` 条目间必须有逗号，否则语法非法、卡片静默空白（同 fetch_conferences.py:564）。
3. **新闻只挂 id 不嵌内容**：时间线 `news:[id]` 仅存稳定新闻 id，渲染时现查 `NEWS_DATA`；解析不到 → 测试报错。
4. **不显旧**：`已达成/已终止` 且久无更新的事件降级折叠；active 事件按更新时间倒序，**不设 14 天闸门**（与新闻/会议卡相反）。
5. **自动聚类必经人工确认闸门（关键 · 用户选"全自动关联"后的落地形态）**：
   用户选定"全自动关联"方向，但为避免站审已指出的分类误标问题（机构预测误标政策等），自动管线**只产出「待审核」候选**——候选事件/时间线节点进 `events.json` 的 `review` 区，**绝不静默直接上线**；人工采纳后才移入 `manual` 并重新生成 `event-data.js` 上线。**静默自动发布错误关联 = 破红线。**（若日后确需无人值守发布，须显式开启 `--unattended` 且接受误关联风险，默认关。）

6. **新闻只挂 id 不嵌内容**：时间线 `news:[id]` 仅存稳定新闻 id，渲染时现查 `NEWS_DATA`；解析不到 → 测试报错。

---

## 7. 决策已定（见 §0.1，待开工）

四项岔路口已全部拍板，详见 §0.1。本轮仅方案定稿、**不写代码**；后续开工顺序建议：

1. Phase 0 先手填 3 个种子事件（矿权转让 / 并购大单 / 政策关税），跑通 schema 与生成物；
2. Phase 1–3 依次做生成器、前端、部署接入与线上验证；
3. Phase 4 再做「自动聚类 + 人工确认闸门」（即用户选的"全自动关联"安全形态）；
4. Phase 5 测试进 CORE + REFERENCE.md 写红线。

刘三确认开工后再进入 Phase 0。
