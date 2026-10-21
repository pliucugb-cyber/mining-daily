#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_cron.py — 把云服务器 crontab 里"矿业日报"相关任务改为调用 shadow_run.sh（幂等）

背景
----
服务器 cron 里跑的是旧版内联命令（不含 git fetch/reset），
导致云端代码冻结在 10-16，10-19 修的 metal 308 重定向一直进不来。
新版 shadow_run.sh 已在 main（提交 f95558d），把 cron 指向它即可。

为什么单独一个脚本
------------------
cron 行的替换涉及引号/时间字段/多行拆分，用 sed 极易转义出错。
这里用 Python 逐行处理，只认"整行"是相关任务才动，绝不误伤其他任务。

判定"矿业日报相关行"的关键词（任一命中即算）
    md-src / fetch_news / bprime.pipeline / shadow_run / shadow_diff / deploy_pages

幂等
----
已存在调用 shadow_run.sh 的行 → 直接跳过，不重复添加。
"""
import argparse
import re
import subprocess
import sys

KEYWORDS = ["md-src", "fetch_news", "bprime.pipeline", "shadow_run",
            "shadow_diff", "deploy_pages"]

NEW_LINE = "30 7 * * * /opt/md-src/shadow_run.sh >> /var/log/md-shadow.log 2>&1"


def read_crontab():
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if r.returncode != 0:
        return ""
    return r.stdout


def is_related(line):
    """是否为矿业日报相关任务行（忽略注释与空行）。"""
    s = line.strip()
    if not s or s.startswith("#"):
        return False
    return any(k in s for k in KEYWORDS)


def already_uses_script(lines):
    for l in lines:
        s = l.strip()
        if s.startswith("#"):
            continue
        if re.search(r"/opt/md-src/shadow_run\.sh", s):
            return True
    return False


def build_new(lines):
    """返回 (新行列表, 说明)。保留非相关行，替换相关行。"""
    out = []
    replaced = 0
    for l in lines:
        if is_related(l):
            if replaced == 0:
                out.append(NEW_LINE)
                replaced += 1
            # 其余相关行丢弃（它们会被 shadow_run.sh 覆盖）
        else:
            out.append(l)
    if replaced == 0:
        out.append(NEW_LINE)
        return out, "未找到相关任务行，已追加新任务"
    return out, f"已替换 {replaced} 条相关任务行为 shadow_run.sh 调用"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写入 crontab（默认 dry-run 只打印）")
    ap.add_argument("--time", default="30 7", help="新任务的时间字段，默认 '30 7'（每天 7:30）")
    args = ap.parse_args()

    global NEW_LINE
    if args.time:
        NEW_LINE = f"{args.time} * * * /opt/md-src/shadow_run.sh >> /var/log/md-shadow.log 2>&1"

    cur = read_crontab()
    lines = cur.splitlines()

    if already_uses_script(lines):
        print("[SKIP] crontab 已经在调用 /opt/md-src/shadow_run.sh，无需改动。")
        print("---- 当前 crontab ----")
        print(cur.rstrip() or "(空)")
        return 0

    new_lines, note = build_new(lines)
    new_text = "\n".join(new_lines).rstrip() + "\n"

    print(f"[INFO] {note}")
    print("---- 变更前 ----")
    print(cur.rstrip() or "(空)")
    print("---- 变更后 ----")
    print(new_text.rstrip())

    if not args.apply:
        print("[DRY-RUN] 未写入。加 --apply 生效。")
        return 0

    # 备份
    ts = subprocess.run(["date", "+%Y%m%d-%H%M%S"], capture_output=True, text=True).stdout.strip()
    bak = f"/root/crontab.bak.{ts}"
    with open(bak, "w", encoding="utf-8") as f:
        f.write(cur)
    print(f"[OK] 已备份原 crontab → {bak}")

    p = subprocess.run(["crontab", "-"], input=new_text, text=True)
    if p.returncode != 0:
        print(f"[ERR] crontab 写入失败：{p.stderr.strip()}")
        print(f"      回滚：crontab {bak}")
        return 1

    print("[OK] crontab 已更新。")
    print("---- 当前 crontab ----")
    print(subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout.rstrip())
    print(f"[INFO] 回滚命令：crontab {bak}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
