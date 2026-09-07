# -*- coding: utf-8 -*-
"""
automation_lock.py — 矿业日报自动化任务互斥锁（方案 B）。

目的：防止 09:00 抓取生成 与 10:00 复验核对 并发操作同一批文件
（今日 09:00 因网络慢卡死、若与 10:00 叠加会同时改 index.html / 推 git，造成脏版本）。

用法（在 automation 运行环境、项目目录下执行）：
  python automation_lock.py acquire <name> [--ttl 分钟]   # 获取锁；若被近期占用则退出码 2（拒绝）
  python automation_lock.py release <name>               # 释放锁
  python automation_lock.py check  <name> [--ttl 分钟]    # 查状态：FREE(0) / LOCKED(1) / STALE(3)

锁文件 .automation.lock（JSON：{name, started, pid}）。该文件不应被 git 提交。
判定：started 距今 < ttl 分钟 视为「近期占用」。
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
LOCK = ROOT / '.automation.lock'
DEFAULT_TTL = 120  # 分钟：覆盖两次任务间隔（60 分）+ 容错


def _read():
    if not LOCK.exists():
        return None
    try:
        return json.loads(LOCK.read_text(encoding='utf-8'))
    except Exception:
        return {'name': '?', 'started': 0, 'pid': None}


def _write(name):
    LOCK.write_text(json.dumps({
        'name': name, 'started': time.time(), 'pid': os.getpid()
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def _recent(data, ttl):
    return (time.time() - data.get('started', 0)) < ttl * 60


def acquire(name, ttl):
    data = _read()
    if data and _recent(data, ttl):
        print(f'LOCKED:held_by={data.get("name")}:started={data.get("started")}')
        return 2
    _write(name)
    print(f'ACQUIRED:{name}')
    return 0


def release(name):
    data = _read()
    if data and data.get('name') == name and LOCK.exists():
        try:
            LOCK.unlink()
        except Exception:
            pass
    print('RELEASED')
    return 0


def check(name, ttl):
    data = _read()
    if not data:
        print('FREE')
        return 0
    if _recent(data, ttl):
        print(f'LOCKED:held_by={data.get("name")}')
        return 1
    print('STALE')
    return 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['acquire', 'release', 'check'])
    ap.add_argument('name')
    ap.add_argument('--ttl', type=int, default=DEFAULT_TTL)
    args = ap.parse_args()
    if args.action == 'acquire':
        sys.exit(acquire(args.name, args.ttl))
    if args.action == 'release':
        sys.exit(release(args.name))
    sys.exit(check(args.name, args.ttl))


if __name__ == '__main__':
    main()
