# 矿业日报 · 补跑手册（PIPELINE）

> **用途**：08:30 外部看门狗发现「线上不是今天」时，按本文件补跑。
> **权威口径**：形态契约、测试基线、假 FAIL 坑一律以 `REFERENCE.md §42` 为准，本文件**不复制**指纹，只给命令与顺序。
> 本文件与 automation「矿业资讯 05:30 抓取生成」的流程等价；两处若漂移，**以 §42 与当日脚本为准**，并回头把本文件补齐。

项目根：`C:\Users\中铝矿业投并部\mining-daily`
`PY` = `C:/Users/中铝矿业投并部/.workbuddy/binaries/python/versions/3.13.12/python.exe`
长输出脚本一律 `PY runq.py <脚本> [参数]`（日志落 `tmp/`，只回 ≤1800 字）。

---

## 0. 互斥锁（第一步，必做）

```
PY automation_lock.py check gen          # FREE(0) / LOCKED(1) / STALE(3)
PY automation_lock.py acquire recover    # STALE 时先 release gen，再 acquire recover
```

- `LOCKED` ⇒ 05:30 实例仍在跑。**不要抢**：`notify warn` 后让路，交给主链路（并发写 `index.html` 会出脏版本）。
- 本轮**结束必须** `PY automation_lock.py release recover`（含异常分支）。
- `.automation.lock` / `.last_run_status.json` / `.preflight_status.json` / `.watchdog_alert.json` 均**不** `git add`。

## 1. 前置健康检查

```
PY preflight_check.py --fail-on-error
```
非 0 ⇒ `git checkout -- index.html` 后重跑；仍失败 ⇒ release + `notify fail` 并停止。

## 2. 行情（顺序不可颠倒）

```
PY fetch_lme.py            # date 字段是「剔除未收盘 bar」的基准
PY fetch_price_history.py
PY test_price_history_unclosed.py     # 期望 14 通过 / 0 失败
```
走势图末点＝最近已收盘日；末点价须 == `lme_data.json.price`。国内盘 08:30 前未开盘属正常。

## 3. 候选池

```
PY fetch_news.py --report-date <今日> --days 2      # 不加 --merge
```
产出 `data/news_candidates_<今日>.json`（≈150–200 条）。**不 commit、不 deploy**。
⚠️ `--source <key>` 会**覆盖**候选池与 `fetch_health_<今日>.json` ⇒ 补抓前后都要 `cp` 备份/还原。

## 4. 采集与整理（LLM 判断环节）

优先从候选池挑，真实发生 + 信源合规 + 链接可达；**覆盖七桶不偏科**。
- 七桶：💼矿权交易｜🔍找矿成果与勘查技术｜📜政策与监管｜📊市场与价格｜🏭行业动态｜🌐国际矿业动态｜💰并购与投资（判定见 §2）。
- 剔除：SMM 会议预告/直播等营销服务类；长江有色「日报/周报/月评」纯报价；摘要空或等于标题须补 2–3 句。
- 低价值公告不收（清单见 §3）：只留并购重组/资产收购/对外投资/重大合同/投产扩产/产量业绩。
- 境外条目按 §4 硬门槛：中文意译 + 2–3 句摘要 + 保留英文原题（`orig_title=`）+ 美元/吨附 ≈元/吨。
- 白名单 27 域（以 `source_whitelist.py` 为准），**严禁编造**。

```
PY source_whitelist.py --check-file index.html --fail-on-error    # 违规删/换，重跑至通过
```

## 5. 重建页面

用**当日** `generate_<YYYYMMDD>.py`；**当日脚本不存在**（05:30 早期挂掉的情况）时：
> 复制最近一天的 `generate_*.py` 为新日期文件，改日期、按 §42「生成侧必留清单」逐项保留形态指纹，再按当日数据重建。

```
PY generate_<YYYYMMDD>.py
```
日期/Badge/时间改当天；新条目 `is-new`；删 30 日外条目；价格数值唯一来源＝`lme_data.json`/`lme-data.js`（严禁手抄）。
形态必须与 `REFERENCE.md §42` 一致（简报 / 布局 / 矿权双视图 / AI 搜 / 我的面板 / 收藏沉浸式 / PWA / 信标与日期 / 价格单位去重 / 热力图 / 区间榜 / 事件日历 / 矿业公司板块）。

## 6. 并购注入（失败跳过）

```
PY fetch_ma.py --report-date <今日> --days 1
PY inject_ma.py --report-date <今日> --days 30
```

## 7. 导出与分类

```
PY export_news_json.py                 # 刷新 NEWS_DATA.updated
PY classify_llm.py                     # 只补 region 空的新条目，幂等
PY runq.py fetch_company.py            # 全量重采 44 家公司 → company_news.json（失败不阻断）
```
⚠️ `export_news_json.py` 与 `classify_llm.py` 写月库为 `indent=1`，而月库既定格式是 `indent=2` + LF ⇒ 跑完**须重序列化**：
`json.dumps(d, ensure_ascii=False, indent=2)` + `newline='\n'`，并置 `d['count']=len(d['news'])`。

## 8. 四个分析文件

```
PY update_analysis_<YYYYMMDD>.py
```
产出 `morning_report.json`（含 `brief_sections` 五节 + 逐条精炼句 ≤80 字）/`sentiment.json`/`signals.json`/`alerts.json`。口径见 §16、指纹见 §42.1。

## 9. 链接校验

```
PY validate_urls.py
```

## 10. 提交

```
git add <本次实际改动的文件，显式列名；含 company_news.json>
git commit -m "..."
git push origin main
```
提交前 `git log --oneline -3 origin/main`；远端被推进先 `git pull --rebase`。
排除：`.automation.lock` / `.last_run_status.json` / `.preflight_status.json` / `.watchdog_alert.json` / `data/news_candidates_*.json` / `data/backcheck_*.md` / `data/fetch_*.json` / `tmp/**`。

## 11. 数字落地守门（发布前最后一道机械闸）

```
PY verify_numbers.py --strict
```
非 0 ⇒ **立即中止 deploy**，release + `notify fail`，人工核对。

## 12. 部署

```
PY deploy_pages.py
```
GitHub Pages 有 1–2 分钟延迟 ⇒ 核对必须**轮询到 `build-version` 变成本次新值**，不能以「HTTP 200」判定成功。

## 13. 验收（用看门狗自身）

```
PY watchdog.py check --json      # 期望 verdict=FRESH、exit 0
```
非 FRESH ⇒ 回到第 12 步排查（`deploy_pages.py` 输出 / `sync_sw_cache_name`）。

## 14. 收尾

`release recover` + `PY notify_status.py ok "矿业日报08:30补跑" "已补跑并同步线上"` + 播 tada；
异常分支：先 `release recover`，再 `PY notify_status.py fail "矿业日报08:30补跑" "<原因>"`（播 Windows Notify）。
