# -*- coding: utf-8 -*-
"""
fetch_price_history.py — 拉取各品种近 15 个交易日日 K 收盘价，产出前端走势图数据
运行: python fetch_price_history.py
产出: price-history.js  (var PRICE_HISTORY = {...})  — index.html 引入
      price_history_detail.json (同内容存档，便于溯源)
数据源:
  国内主力/上金所/GFEX → 新浪财经 InnerFuturesNewService.getDailyKLine（CU0/AL0/.../LC0）
  LME 六大金属       → 东方财富 push2his 日K（109.LCPT 等；东财限流时自动保留旧数据）
注意: 电解钴为 SMM 现货报价，无连续日 K，不入图（前端该卡片不可点击）。
"""
import json, time, subprocess, datetime, os, sys, re

BASE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
BARS = 15  # 保留最近 15 个交易日

# slug 必须与 index.html 价格卡 data-slug 一一对应
# kind: sina=新浪国内主力, em=东财push2his
INSTRUMENTS = [
    ("slug",   "kind", "code",          "name",   "unit"),
    ("cum",    "sina", "CU0",           "沪铜",   "元/吨"),
    ("alm",    "sina", "AL0",           "沪铝",   "元/吨"),
    ("pbm",    "sina", "PB0",           "沪铅",   "元/吨"),
    ("znm",    "sina", "ZN0",           "沪锌",   "元/吨"),
    ("snm",    "sina", "SN0",           "沪锡",   "元/吨"),
    ("nim",    "sina", "NI0",           "沪镍",   "元/吨"),
    ("au9999", "sina", "AU0",           "上海金", "元/克"),
    ("agtd",   "sina", "AG0",           "白银",   "元/千克"),
    ("lcm",    "sina", "LC0",           "碳酸锂", "元/吨"),
    ("lcpt",   "em",   "109.LCPT",      "LME 铜", "USD/吨"),
    ("lalt",   "em",   "109.LALT",      "LME 铝", "USD/吨"),
    ("lznt",   "em",   "109.LZNT",      "LME 锌", "USD/吨"),
    ("lldt",   "em",   "109.LLDT",      "LME 铅", "USD/吨"),
    ("lnkt",   "em",   "109.LNKT",      "LME 镍", "USD/吨"),
    ("ltnt",   "em",   "109.LTNT",      "LME 锡", "USD/吨"),
]
INSTRUMENTS = INSTRUMENTS[1:]

EM_API = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={sec}"
          "&klt=101&fqt=0&lmt=" + str(BARS) + "&end=20500101"
          "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55")
SINA_API = ("https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20t=/"
            "InnerFuturesNewService.getDailyKLine?symbol={sym}")


def curl(url, timeout=20):
    r = subprocess.run(
        ["curl", "-s", "-m", str(timeout), "-A", UA,
         "-H", "Accept: */*", "-H", "Referer: https://finance.sina.com.cn/", url],
        capture_output=True, timeout=timeout + 5)
    return r.stdout.decode("utf-8", errors="replace")


def fetch_sina(sym, retry=3):
    """新浪国内主力日K → [(date, close)]"""
    for i in range(retry):
        try:
            t = curl(SINA_API.format(sym=sym))
            # jsonp 形如 ...var t=([{...},...]);  — 用切片而非正则（稳妥）
            a = t.find("var t=(")
            if a < 0:
                raise RuntimeError("jsonp 无 var t= 标记 len=%d" % len(t))
            a += len("var t=(")
            b = t.rfind("]);")
            if b <= a:
                raise RuntimeError("jsonp 无 ]); 收尾 len=%d" % len(t))
            raw = t[a:b + 1]  # [ ... ]
            # 新浪偶发截断：尾部最后一条记录可能不完整 → 逐级丢弃尾部坏记录重试
            while True:
                try:
                    arr = json.loads(raw)
                    break
                except json.JSONDecodeError:
                    idx = raw.rfind('},')
                    if idx < 0:
                        raise
                    raw = raw[:idx + 1] + ']'
            pts = [[x["d"], round(float(x["c"]), 2)] for x in arr[-BARS:]]
            return pts
        except Exception as e:
            if i == retry - 1:
                raise
            time.sleep(1.5 * (i + 1))


def fetch_em(sec, retry=3):
    """东财日K → [(date, close)]；被限流(空响应/断连)时抛异常"""
    for i in range(retry):
        try:
            t = curl(EM_API.format(sec=sec), timeout=15)
            if not t.strip():
                raise RuntimeError("空响应(限流)")
            d = json.loads(t)
            data = d.get("data") or {}
            klines = data.get("klines") or []
            pts = []
            for line in klines:
                parts = line.split(",")
                pts.append([parts[0], round(float(parts[2]), 2)])
            if len(pts) >= 2:
                # 写通缓存：限流日的兜底
                os.makedirs(os.path.join(BASE, "data", "em_kline_cache"), exist_ok=True)
                with open(os.path.join(BASE, "data", "em_kline_cache", sec.split(".")[1] + ".json"),
                          "w", encoding="utf-8") as f:
                    json.dump({"secid": sec, "points": pts}, f, ensure_ascii=False)
            return pts
        except Exception as e:
            if i == retry - 1:
                # 缓存兜底
                cp = os.path.join(BASE, "data", "em_kline_cache", sec.split(".")[1] + ".json")
                if os.path.exists(cp):
                    try:
                        return json.load(open(cp, encoding="utf-8"))["points"]
                    except Exception:
                        pass
                raise
            time.sleep(2.0 * (i + 1))


def main():
    # 合并模式：本次抓取失败的品种保留旧数据（接口限流时部分品种会失败，不清空）
    detail_path = os.path.join(BASE, "price_history_detail.json")
    old = {}
    if os.path.exists(detail_path):
        try:
            old = json.load(open(detail_path, encoding="utf-8")).get("series", {})
        except Exception:
            old = {}
    series, failed = {}, []
    for slug, kind, code, name, unit in INSTRUMENTS:
        try:
            pts = fetch_sina(code) if kind == "sina" else fetch_em(code)
        except Exception as e:
            failed.append("%s(%s): %s" % (name, code, e))
            if slug in old and len(old[slug].get("points", [])) >= 2:
                series[slug] = old[slug]
                print("  %-6s %-10s 本次失败保留旧数据 %d根(截至 %s)"
                      % (name, code, len(old[slug]["points"]), old[slug]["points"][-1][0]))
            continue
        if len(pts) >= 2:
            src = "sina" if kind == "sina" else "eastmoney"
            # 新浪夜盘延迟：若旧数据(Eastmoney)有更新的交易日，拼接到尾部保持连续
            if slug in old:
                extra = [p for p in old[slug].get("points", []) if p[0] > pts[-1][0]]
                if extra:
                    pts = pts + extra
                    src += "+em补尾"
            series[slug] = {"name": name, "unit": unit, "code": code,
                            "source": src, "points": pts}
            print("  %-6s %-10s %d根  最新 %s %s" % (name, code, len(pts), pts[-1][0], pts[-1][1]))
        time.sleep(0.8)
    payload = {
        "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": "日K收盘价。国内主力=新浪财经、LME=东方财富 push2his；电解钴为SMM现货无连续日K不入图",
        "series": series,
    }
    js = ("// price-history.js — 由 fetch_price_history.py 自动生成，勿手改\n"
          "// 更新时间: " + payload["updated"] + "\n"
          "var PRICE_HISTORY=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";")
    with open(os.path.join(BASE, "price-history.js"), "w", encoding="utf-8") as f:
        f.write(js)
    with open(detail_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print("OK: %d/%d 个品种 → price-history.js / price_history_detail.json" % (len(series), len(INSTRUMENTS)))
    if failed:
        print("失败品种:", " | ".join(failed), file=sys.stderr)
        sys.exit(2 if len(failed) >= len(INSTRUMENTS) else 0)


if __name__ == "__main__":
    main()
