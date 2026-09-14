#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_domestic_reach.py —— 信源可达性探针（方案 B·抓取上云决策用）

目的：
    从「当前运行环境」实测 fetch_news.py 中每个启用信源的 list_url 是否可达。
    - 在境内机器 / 境内云服务器上跑  → 模拟国内节点能抓哪些源；
    - 在境外机器（如 GitHub Actions）上跑 → 模拟境外节点能抓哪些源。
    两次结果对照，直接回答「国内云能否整体替代 GitHub」。

输出：
    - 终端逐源表：KEY / 是否境外 / HTTP状态 / 首字节时延 / 读取字节 / 错误
    - data/probe_domestic_reach.json：结构化结果，供历史对比

说明：
    - 只读前 20KB 判定可达，不下载全量、不解析正文，纯连通性探测。
    - 纯标准库，零第三方依赖；可在云服务器 / 本地 / CI 任意环境直接跑。
"""
import importlib.util
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request

TIMEOUT = int(os.environ.get("PROBE_TIMEOUT", "12"))  # 单源超时（秒），可用 PROBE_TIMEOUT 覆盖
READ_BYTES = 20000    # 只读前 20KB 判定可达


def load_sources():
    """动态读取 fetch_news.py 的 SOURCES，保持与抓取逻辑同源、不硬编码。"""
    spec = importlib.util.spec_from_file_location("fn", "fetch_news.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SOURCES


def probe(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    t0 = time.time()
    try:
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; mining-daily-probe/1.0)",
                "Accept": "*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            data = r.read(READ_BYTES)
            dt = round(time.time() - t0, 2)
            return {"ok": True, "status": r.status, "bytes": len(data),
                    "dt": dt, "err": ""}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "bytes": 0,
                "dt": round(time.time() - t0, 2), "err": "HTTP %d" % e.code}
    except (socket.timeout, urllib.error.URLError) as e:
        return {"ok": False, "status": 0, "bytes": 0,
                "dt": round(time.time() - t0, 2), "err": type(e).__name__}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": 0, "bytes": 0,
                "dt": round(time.time() - t0, 2),
                "err": type(e).__name__ + ":" + str(e)[:60]}


def main():
    try:
        sources = load_sources()
    except Exception as e:  # noqa: BLE001
        print("⚠️ 无法动态读取 SOURCES（%s），请确认 fetch_news.py 在同目录" % e)
        raise SystemExit(1)

    host = socket.gethostname()
    print("=== 信源可达性探针（运行节点 = %s）===" % host)
    print("（本机若在企业内网，结论近似「境内云节点」；若走代理则不代表纯净国内网络）\n")

    rows = []
    for c in sources:
        if not c.get("enabled"):
            continue
        url = c.get("list_url")
        if not url:
            continue
        res = probe(url)
        rows.append((c["key"], bool(c.get("foreign")), url, res))

    # 境外源优先展示，便于一眼看国内节点能不能抓境外
    rows.sort(key=lambda x: (not x[1], x[0]))

    print("%-14s %-4s %-5s %-7s %-9s %s" % ("KEY", "境外", "状态", "时延", "字节", "URL / 错误"))
    print("-" * 80)
    for key, foreign, url, r in rows:
        flag = "🌍" if foreign else "  "
        st = str(r["status"]) if (r["ok"] or r["status"]) else "—"
        mark = "" if r["ok"] else "  ✗ " + r["err"]
        print("%-14s %-4s %-5s %-7s %-9s %s" % (
            key, flag, st, r["dt"], r["bytes"], mark or url[:52]))
    print("-" * 80)

    reachable = sum(1 for x in rows if x[3]["ok"])
    foreign_rows = [x for x in rows if x[1]]
    fr = sum(1 for x in foreign_rows if x[3]["ok"])
    print("启用源 %d | 可达 %d | 境外源 %d | 境外可达 %d"
          % (len(rows), reachable, len(foreign_rows), fr))

    # 结构化留痕
    import os
    os.makedirs("data", exist_ok=True)
    out = {
        "node": host,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "rows": [
            {"key": k, "foreign": f, "url": u, "ok": r["ok"], "status": r["status"],
             "dt": r["dt"], "bytes": r["bytes"], "err": r["err"]}
            for k, f, u, r in rows
        ],
    }
    with open("data/probe_domestic_reach.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)
    print("\n已保存 data/probe_domestic_reach.json")

    # 决策提示
    if fr < len(foreign_rows):
        print("\n⚠️ 有 %d 个境外源不可达 → 国内节点不能单独替代 GitHub，"
              "需保留 GitHub 抓境外源 或 给云服务器配代理"
              % (len(foreign_rows) - fr))
    else:
        print("\n✅ 全部境外源可达 → 国内节点可独立承担完整抓取，GitHub 可退役")


if __name__ == "__main__":
    main()
