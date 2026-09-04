#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_lme.py —— 抓取 LME 6 大基本金属实时价（美元/吨）
数据源：东方财富国际期货接口（数据来源 LME，经新浪/东财聚合）
URL: https://futsseapi.eastmoney.com/list/COMEX,NYMEX,COBOT,SGX,NYBOT,LME,MDEX,TOCOM,IPE
零第三方依赖：纯标准库 urllib（部署平台无需 pip install）
"""
import json, re, sys, urllib.request, urllib.error, math
from datetime import datetime, timezone, timedelta
from pathlib import Path

API_URL = "https://futsseapi.eastmoney.com/list/COMEX,NYMEX,COBOT,SGX,NYBOT,LME,MDEX,TOCOM,IPE"
PAGE_SIZE = 50
TOKEN = "58b2fa8f54638b60b87d69b31969089c"
OUT = Path(__file__).parent / "lme_data.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# LME 综合 03 主力合约代码（每个金属 1 个）
METALS = [
    ("LCPT", "LME 铜",  "铜"),
    ("LALT", "LME 铝",  "铝"),
    ("LZNT", "LME 锌",  "锌"),
    ("LLDT", "LME 铅",  "铅"),
    ("LNKT", "LME 镍",  "镍"),
    ("LTNT", "LME 锡",  "锡"),
]


def fetch_page(page_index):
    url = API_URL + "?" + urllib.parse.urlencode({
        "orderBy": "dm",
        "sort": "desc",
        "pageSize": str(PAGE_SIZE),
        "pageIndex": str(page_index),
        "token": TOKEN,
        "field": "dm,sc,name,p,zde,zdf,o,h,l,zjsj,vol,wp,np,ccl",
    })
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://quote.eastmoney.com/",
    })
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_all():
    """分页拿全（接口 total=640，分 13 页）。只筛 LME 6 行就够，不必全拉。"""
    first = fetch_page(0)
    total = first.get("total", 0)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    all_rows = list(first.get("list") or [])
    for p in range(1, pages):
        try:
            data = fetch_page(p)
            all_rows.extend(data.get("list") or [])
        except Exception as e:
            print(f"  第 {p} 页失败: {e}", file=sys.stderr)
    return all_rows


def parse(rows):
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    by_dm = {r.get("dm"): r for r in rows if r.get("dm")}
    out = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "updated": now,
        "source": "东方财富国际期货（LME 主力 03 合约）",
        "currency": "USD",
        "unit": "metric tonne",
        "metals": [],
    }
    for dm, zh, _en in METALS:
        r = by_dm.get(dm)
        if not r:
            out["metals"].append({"slug": dm.lower(), "zh": zh, "code": dm, "price": None, "err": f"{dm} not found"})
            continue
        try:
            price = float(r.get("p")) if r.get("p") not in (None, "", "-") else None
        except (ValueError, TypeError):
            price = None
        try:
            chg = float(r.get("zde")) if r.get("zde") not in (None, "", "-") else None
        except (ValueError, TypeError):
            chg = None
        try:
            chg_pct = float(r.get("zdf")) if r.get("zdf") not in (None, "", "-") else None
        except (ValueError, TypeError):
            chg_pct = None
        try:
            prev = float(r.get("zjsj")) if r.get("zjsj") not in (None, "", "-") else None
        except (ValueError, TypeError):
            prev = None
        out["metals"].append({
            "slug": dm.lower(), "zh": zh, "code": dm,
            "name": r.get("name", ""),
            "price": price, "chg": chg, "chg_pct": chg_pct, "prev": prev,
        })
    return out


def merge_with_prev(new):
    """把昨日的 price 作为今日的 prev（防止当日 prev 字段偶发为空）。"""
    if not OUT.exists():
        return new
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return new
    old_map = {m["slug"]: m.get("price") for m in old.get("metals", []) if m.get("price") is not None}
    for m in new["metals"]:
        if m.get("price") is None:
            continue
        # 接口返回的 zjsj 已经是昨结，如果取到了就用接口的，否则用昨日抓的
        if m.get("prev") is None:
            m["prev"] = old_map.get(m["slug"])
        # 如果 chg / chg_pct 缺，用 prev 算
        if m.get("prev") is not None:
            if m.get("chg") is None:
                m["chg"] = round(m["price"] - m["prev"], 2)
            if m.get("chg_pct") is None and m["prev"]:
                m["chg_pct"] = round((m["price"] - m["prev"]) / m["prev"] * 100, 2)
    return new


def main():
    try:
        rows = fetch_all()
    except urllib.error.URLError as e:
        print(f"ERR fetch: {e}", file=sys.stderr)
        if OUT.exists():
            print("网络失败，保留旧数据", file=sys.stderr)
            return 0
        OUT.write_text(json.dumps({
            "date": "", "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": API_URL, "currency": "USD", "unit": "metric tonne",
            "metals": [], "err": str(e)
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    data = parse(rows)
    data = merge_with_prev(data)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    js = "// LME 收盘价（fetch_lme.py 生成，单位：USD/吨）\nvar LME_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n"
    (Path(__file__).parent / "lme-data.js").write_text(js, encoding="utf-8")

    hit = sum(1 for m in data["metals"] if m.get("price") is not None)
    print(f"OK  {data['date']}  抓到 {hit}/6")
    for m in data["metals"]:
        if m.get("price") is not None:
            chg = m.get("chg") or 0
            pct = m.get("chg_pct") or 0
            sign = "+" if chg >= 0 else ""
            print(f"  {m['zh']:8s}  {m['price']:>12,.2f}  {sign}{chg:,.2f} ({sign}{pct:.2f}%)")
        else:
            print(f"  {m['zh']:8s}  {m.get('err','?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
