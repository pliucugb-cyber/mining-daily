# -*- coding: utf-8 -*-
"""
test_price_history_unclosed.py — LME 价格「未收盘 bar」回归测试（2026-09-11）

背景（与本次 P0 无关的数据准确性事故）：
  价格卡页面写「LME 锡 54825 ▲+710」，而 lme_data.json 是 54115 ▼-1565，方向相反。

根因链：
  1. 06:00 fetch_lme.py 生成 lme_data.json（伦敦闭市窗口内），price = 最近一个【已收盘】
     交易日收盘价 54115；
  2. 08:00 复核重跑 fetch_price_history.py，此时伦敦已开市（北京 08:00 起），东财
     push2his 日K 多出一根【当日尚未收盘】的盘中 bar = 54825；
  3. 两者都挂当日日期，前端 renderLmePrices() 里 09-09 加的 `lastDate < dRef` 日期守卫
     因此放行，用盘中价覆盖了 LME_DATA 的收盘价 → 涨跌方向反转；且是就地改写 LME_DATA，
     连带问答 qaPriceBrief() 的答案一起错。

修复（两侧各一半）：
  · 数据侧：fetch_price_history.py 不再输出未收盘的 LME bar（drop_unclosed_lme_bar）。
    不变量 = 走势图末点日期 < lme_data.json 的 date。
  · 展示侧：renderLmePrices() 删除跨源覆盖，价格卡数值唯一来源 = LME_DATA。

本测试锁住：判据函数的行为 + 真实数据文件的不变量。

运行：python test_price_history_unclosed.py
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import fetch_price_history as fph   # noqa: E402  （模块有 __main__ 守卫，import 安全）

pass_n = 0
fail_n = 0


def check(name, cond, extra=""):
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print("  PASS  " + name + ("  -> " + str(extra) if extra else ""))
    else:
        fail_n += 1
        print("  FAIL  " + name + ("  -> " + str(extra) if extra else ""))


def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


print("\n===== ① drop_unclosed_lme_bar 判据 =====")

ref = "2026-09-11"
# 08:00 复核场景：末点是当日盘中 bar → 必须丢
pts = [["2026-09-09", 55680], ["2026-09-10", 54115], ["2026-09-11", 54825]]
out = fph.drop_unclosed_lme_bar([list(p) for p in pts], ref)
check("末点日期 == 基准日 -> 丢弃该 bar",
      len(out) == 2 and out[-1] == ["2026-09-10", 54115], out[-1])

# 06:00 常态场景：末点是已收盘的昨日 bar → 保留
pts = [["2026-09-09", 55680], ["2026-09-10", 54115]]
out = fph.drop_unclosed_lme_bar([list(p) for p in pts], ref)
check("末点日期 < 基准日 -> 不丢",
      len(out) == 2 and out[-1] == ["2026-09-10", 54115], out[-1])

# 至少保留 2 根（前端画线要求 points.length >= 2）
pts = [["2026-09-10", 54115], ["2026-09-11", 54825]]
out = fph.drop_unclosed_lme_bar([list(p) for p in pts], ref)
check("只有 2 根时即便末点未收盘也不丢（保底 2 根）", len(out) == 2, out)

# lme_data.json 陈旧多日：尾部多根都 >= 基准日 → 全部丢掉，但不低于 2 根
pts = [["2026-09-08", 54730], ["2026-09-09", 55680],
       ["2026-09-10", 54115], ["2026-09-11", 54825]]
out = fph.drop_unclosed_lme_bar([list(p) for p in pts], "2026-09-08")
check("基准日陈旧 -> 丢掉全部 >= 基准日的尾部 bar（仍留 2 根）",
      len(out) == 2 and out[-1] == ["2026-09-09", 55680], out[-1])

# ref 为空 → 退回北京当日兜底
today = fph.beijing_today()
out = fph.drop_unclosed_lme_bar([["2026-01-01", 1], ["2026-01-02", 2], [today, 3]], "")
check("ref 为空 -> 用北京当日兜底，丢掉今天那根",
      len(out) == 2 and out[-1][0] == "2026-01-02", out[-1])

# 空/单点输入不炸
check("空输入安全", fph.drop_unclosed_lme_bar([], ref) == [])
check("单点输入安全", fph.drop_unclosed_lme_bar([["2026-09-11", 1]], ref) == [["2026-09-11", 1]])

print("\n===== ② 真实数据不变量 =====")

detail_p = os.path.join(BASE, "price_history_detail.json")
lme_p = os.path.join(BASE, "lme_data.json")
have = os.path.exists(detail_p) and os.path.exists(lme_p)
check("price_history_detail.json / lme_data.json 均存在", have)

if have:
    detail = jload(detail_p)
    lme = jload(lme_p)
    ref = str(lme.get("date") or "").strip()
    series = detail.get("series", {})
    check("lme_data.json 有 date 字段", bool(ref), ref)

    lme_slugs = [row[0] for row in fph.INSTRUMENTS if row[1] == "em"]
    check("INSTRUMENTS 里 LME(em) 品种为 6 个", len(lme_slugs) == 6, lme_slugs)

    bad = []
    for slug in lme_slugs:
        s = series.get(slug)
        if not s or len(s.get("points", [])) < 2:
            bad.append(slug + " 序列缺失/点数不足")
            continue
        last_date = s["points"][-1][0]
        if last_date >= ref:
            bad.append("%s 末点 %s >= lme_data.date %s" % (slug, last_date, ref))
    check("★ LME 走势图末点日期 < lme_data.date（未收盘 bar 不得入图）",
          not bad, " | ".join(bad) if bad else "6/6 合规")

    # 与卡片同口径：走势图末点价 == lme_data.json 的 price
    lme_map = {m["slug"]: m for m in lme.get("metals", [])}
    mismatch = []
    for slug in lme_slugs:
        s, m = series.get(slug), lme_map.get(slug)
        if not s or not m or m.get("price") is None:
            continue
        chart_last = s["points"][-1][1]
        if abs(float(chart_last) - float(m["price"])) > 0.01:
            mismatch.append("%s 走势图末点=%s lme_data.price=%s" % (slug, chart_last, m["price"]))
    check("★ LME 走势图末点价 == lme_data.json 的 price（卡片/走势图同口径）",
          not mismatch, " | ".join(mismatch) if mismatch else "6/6 相等")

print("\n===== ③ 前端不得再跨源覆盖 LME_DATA =====")
app_p = os.path.join(BASE, "app.js")
if os.path.exists(app_p):
    with open(app_p, encoding="utf-8") as f:
        app_lines = f.readlines()
    code = [l for l in app_lines
            if not l.strip().startswith("//") and not l.strip().startswith("*")]
    code_txt = "".join(code)
    check("renderLmePrices() 内已无 `m.price=last` 跨源覆盖",
          "m.price=last" not in code_txt and "m.chg=chg" not in code_txt)
    check("仍保留 null 价显示 -- 的处理", "textContent='--'" in code_txt)
else:
    check("app.js 存在", False)

print("\n===== 汇总 =====")
print("  通过 %d / 失败 %d" % (pass_n, fail_n))
sys.exit(1 if fail_n else 0)
