#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
source_coverage_report.py — 信源覆盖率自检（每日）

定位
----
把 fetch_news.py 已经产出的 fetch_health_*.json（逐源产出 + 基线中位数 + 状态）转成
既给机器正则解析、又给人看的覆盖率报告：data/source_coverage_<日期>.txt。
本机（WorkBuddy 主链路）与云服务器两边都能跑，产出格式一致。

⚠️ 2026-10-21 更正两处过时描述：
  1) 旧注释称 shadow_diff 比的是「云构建产物 vs 云部署镜像」（自我比对）——不对。
     实际上 /var/www/mining-daily 由 `git reset --hard origin/gh-pages` 刷新，
     而 gh-pages 唯一写者是本机 → shadow_diff 的「线上」侧是**本机产物**，
     「云」侧才是云端产物。它是**跨源内容池差异**，不是部署健康信号。
  2) 旧注释称本文件会被 bot commit、WorkBuddy 经 GitHub API 读取——不对。
     本文件未被 git 跟踪，**播报直接读本机 data/ 目录**；GitHub main 上没有。

为什么需要它
------------
- 影子报告 shadow_diff 比的是「云构建产物 vs 云部署镜像」（自我比对），只能看部署齐不齐，
  **看不出抓取质量**。它的 100% 是假信号（空比空也会报 100%）。
- 真正的抓取质量在 fetch_health_*.json 里：每个源今日产出、基线中位数、ok/suspect 状态。
  但它是 JSON，WorkBuddy 播报需要稳定可读的纯文本行 —— 本脚本就是做这层转换 + 连续失败统计。

用法（在本机仓库根目录或云服务器 /opt/md-src 下，fetch_news 跑完之后执行）
----
    python source_coverage_report.py                  # 今天，读 fetch_health
    python source_coverage_report.py --date 2026-10-18
    python source_coverage_report.py --probe          # 对 0 产出源做存活探测（区分"源挂了"vs"真没新闻"）
    python source_coverage_report.py --days 5         # 连续失败统计回看天数（默认 5）

输出
----
    data/source_coverage_<日期>.txt
    机器可读行（供 WorkBuddy 播报正则提取）：
        信源总数: N  启用: M  健康: X  偏低: Y  疑似失败: Z  禁用: W
        疑似失败源: geoglobal, mining, cjys
        覆盖率: NN%
    之后是给人看的分源表格。
本文件落在 data/ 下。**未被 git 跟踪**（.gitignore 覆盖 data/），
播报助手直接读本机 data/source_coverage_<日期>.txt；云端如需，需另行采集回传。
"""
import argparse
import datetime
import json
import os
import re
import ssl
import sys
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
sys.path.insert(0, BASE_DIR)

# 复用 fetch_news 的源清单与 UA/网络配置，避免两份配置漂移
try:
    import fetch_news as fn
    SOURCES = fn.SOURCES
    UA = fn.UA
except Exception as e:
    SOURCES = None
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
    sys.stderr.write("警告：未能导入 fetch_news（%s），源清单回退为空\n" % e)

CTX = ssl.create_default_context()
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=CTX))


def probe(url, timeout=12):
    """存活探测：HEAD 优先，失败回退 GET(前 1 字节)。区分 源挂了 / 重定向 / 超时。"""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method,
                                        headers={"User-Agent": UA,
                                                 "Accept": "*/*",
                                                 "Range": "bytes=0-0"})
            with _OPENER.open(req, timeout=timeout) as r:
                return "ok(%d)" % r.status
        except urllib.error.HTTPError as e:
            # 308 重定向（metal 源已知问题）、403/404 等都算"能连上但内容异常"
            return "http%d" % e.code
        except Exception as e:
            last = str(e)[:60]
            continue
    return "err:%s" % last


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def recent_health(dates):
    """按日期倒序读 fetch_health，返回 {date: {key: status}}。"""
    out = {}
    for d in dates:
        h = load_json(os.path.join(DATA_DIR, "fetch_health_%s.json" % d))
        if h:
            out[d] = {s["key"]: s.get("status", "ok") for s in h.get("sources", [])}
    return out


def consecutive_suspect(key, recent):
    """从最新日期往回数，连续 suspect 的天数（含今天）。"""
    cnt = 0
    for d in recent:  # recent 已倒序
        if recent[d].get(key) == "suspect":
            cnt += 1
        else:
            break
    return cnt


def main():
    ap = argparse.ArgumentParser(description="云服务器信源覆盖率自检")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--days", type=int, default=5, help="连续失败统计回看天数")
    ap.add_argument("--probe", action="store_true", help="对 0 产出源做存活探测")
    args = ap.parse_args()
    date = args.date

    health = load_json(os.path.join(DATA_DIR, "fetch_health_%s.json" % date))
    if not health:
        sys.stderr.write("未找到 fetch_health_%s.json（fetch_news 是否今日已跑？）\n" % date)
        sys.exit(2)

    # 近 N 天日期（倒序），用于连续失败统计
    base = datetime.date.fromisoformat(date)
    dates = [(base - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
             for i in range(args.days)]
    recent = recent_health(dates)

    src_by_key = {s["key"]: s for s in health.get("sources", [])}
    cfg_by_key = {c["key"]: c for c in (SOURCES or [])}

    total = len(cfg_by_key) or len(src_by_key)
    enabled = [k for k, c in cfg_by_key.items() if c.get("enabled")] if cfg_by_key \
        else [k for k, s in src_by_key.items() if s.get("status") != "disabled"]
    n_enabled = len(enabled)
    n_healthy = 0
    n_low = 0          # 有产出但低于基线（非 suspect、count>0 且明显偏低）—— 这里以 status=ok 且有 baseline 但 count<median*0.6 计
    n_suspect = 0
    n_disabled = total - n_enabled
    healthy_enabled = 0
    suspect_list = []

    rows = []
    for key in enabled:
        s = src_by_key.get(key, {})
        cfg = cfg_by_key.get(key, {})
        name = cfg.get("name") or s.get("name") or key
        count = s.get("count", 0)
        med = s.get("baseline_median", 0) or 0
        status = s.get("status", "ok")
        consec = consecutive_suspect(key, recent)
        # 存活探测（仅对 0 产出源，省时间）
        probe_res = ""
        if args.probe and count == 0:
            url = cfg.get("list_url") or ""
            if url:
                probe_res = "  探测=%s" % probe(url)
        if status == "suspect":
            n_suspect += 1
            suspect_list.append("%s(%s)" % (name, key))
            flag = "⚠️疑似失败"
        elif count == 0:
            # 0 产出但 status 非 suspect（如基线本身为 0 的禁用/稳定空源）
            flag = "○空(基线0)"
            if med == 0:
                n_healthy += 1
                healthy_enabled += 1
        elif med and count < med * 0.6:
            n_low += 1
            flag = "↓偏低"
        else:
            n_healthy += 1
            healthy_enabled += 1
            flag = "✓健康"
        rows.append((name, key, count, int(med), flag, consec, probe_res))

    coverage = (healthy_enabled * 100 // n_enabled) if n_enabled else 0

    # ---- 机器可读行（必须稳定，供 WorkBuddy 正则提取） ----
    machine_lines = [
        "信源总数: %d  启用: %d  健康: %d  偏低: %d  疑似失败: %d  禁用: %d"
        % (total, n_enabled, n_healthy, n_low, n_suspect, n_disabled),
        "疑似失败源: %s" % (", ".join(suspect_list) if suspect_list else "无"),
        "覆盖率: %d%%" % coverage,
    ]

    # ---- 人看表格 ----
    table = []
    table.append("分源明细（今日产出 / 基线中位数 / 状态 / 连续失败天数）")
    table.append("%-22s %-10s %5s %6s %-12s %s" % ("名称", "key", "今日", "基线", "状态", "连续失败"))
    for name, key, count, med, flag, consec, probe_res in sorted(
            rows, key=lambda r: (r[4] != "⚠️疑似失败", r[2])):
        table.append("%-22s %-10s %5d %6d %-12s %d天%s"
                     % (name[:22], key, count, med, flag, consec, probe_res))

    out_text = "\n".join(machine_lines) + "\n\n" + "\n".join(table) + "\n"

    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, "source_coverage_%s.txt" % date)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_text)

    # 控制台摘要
    print(" | ".join(machine_lines))
    print("报告已写入：%s" % out_path)
    if suspect_list:
        print("⚠️ 疑似失败源：%s" % ", ".join(suspect_list))


if __name__ == "__main__":
    main()
