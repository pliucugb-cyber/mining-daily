# -*- coding: utf-8 -*-
"""
automation_lock.py — 矿业日报自动化任务互斥锁（方案 B）。

目的：防止 06:00 抓取生成 与 08:00 复验核对 并发操作同一批文件
（同时改 index.html / 推 git 会造成脏版本）。

用法（在 automation 运行环境、项目目录下执行）：
  python automation_lock.py acquire <name> [--ttl 分钟]   # 获取锁；若被占用则退出码 2（拒绝）
  python automation_lock.py release <name>               # 释放锁
  python automation_lock.py check  <name> [--ttl 分钟]    # 查状态：FREE(0) / LOCKED(1) / STALE(3)

对外协议（06:00 / 08:00 自动化依赖，勿改）：
  acquire → "ACQUIRED:<name>"(0) 或 "LOCKED:held_by=<name>:started=<ts>"(2)
  release → "RELEASED"(0)
  check   → "FREE"(0) / "LOCKED:held_by=<name>"(1) / "STALE"(3)

锁文件 .automation.lock（JSON：{name, started, pid}）。该文件不应被 git 提交。

2026-09-10 P1 加固（第 2 批）：
  1) 原子创建：改用 os.open(O_CREAT|O_EXCL)，消除旧版「先读后写」的 TOCTOU 竞态
     ——两个实例同时启动时会同时判定 FREE 并双双拿到锁。
  2) pid 存活校验：持锁进程已崩溃/被杀时（残留锁文件），旧版要硬等满 ttl（默认 120 分钟）
     才能再次运行，等于把次日任务卡死；现在检测到 pid 已死即安全抢占。
"""
import argparse
import errno
import json
import os
import sys
import time
from pathlib import Path

from logutil import get_logger

ROOT = Path(__file__).parent
LOCK = ROOT / '.automation.lock'
DEFAULT_TTL = 120  # 分钟：覆盖两次任务间隔（60 分）+ 容错

# 注意：本脚本的 stdout 是**机器协议**（ACQUIRED:/LOCKED:/RELEASED/FREE/STALE），
# 06:00 与 08:00 自动化直接解析它。这些行**必须**保持裸 print，不得加日志前缀，
# 否则调用方的 startswith / split(':') 会失效。
# 只有下面这条人类诊断 logger 走统一格式（且保持在 stderr，不污染协议输出）。
log = get_logger('automation_lock', stream=sys.stderr)


def _read():
    if not LOCK.exists():
        return None
    try:
        return json.loads(LOCK.read_text(encoding='utf-8'))
    except Exception:
        # 坏文件：当作无人持有，但保留文件以便后续覆盖
        return {'name': '?', 'started': 0, 'pid': None}


def _pid_alive_windows(pid):
    """Windows：只读探测进程是否存在（OpenProcess + 立即 CloseHandle）。

    刻意不用 os.kill(pid, 0)——Windows 上它的语义是「可终止」而非「存在探测」，
    实测对不存在的 pid（如 999997）也不报错，会把残留锁误判成「进程还活着」，
    导致崩溃后的锁永远抢不回来；且对真实 pid 存在误终止风险。
    """
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return True                     # 查询失败 → 保守视为存活
            return code.value == STILL_ACTIVE   # 已退出则有明确退出码
        finally:
            k32.CloseHandle(h)
    except Exception:
        return True          # 探测失败 → 保守视为存活，不抢占


def _pid_alive(pid):
    """跨平台判断进程是否存活。无法判断时保守返回 True（不抢占，避免误伤）。"""
    if not pid:
        return True
    if pid == os.getpid():
        return True
    if os.name == 'nt':
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except ValueError:
        return True
    except PermissionError:
        return True          # 进程存在但无权限 → 视为存活
    except OSError as e:
        if getattr(e, 'errno', None) == errno.ESRCH:
            return False
        return True
    return True


def _try_create(name):
    """原子创建锁文件：只有一个进程能成功（O_EXCL）。成功返回 True。"""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0)
    try:
        fd = os.open(str(LOCK), flags)
    except FileExistsError:
        return False
    except OSError:
        return False
    payload = {'name': name, 'started': time.time(), 'pid': os.getpid()}
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        return False
    return True


def _recent(data, ttl):
    return (time.time() - data.get('started', 0)) < ttl * 60


def acquire(name, ttl):
    data = _read()
    if data:
        held_by = data.get('name')
        alive = _pid_alive(data.get('pid'))
        if _recent(data, ttl) and alive:
            print(f'LOCKED:held_by={held_by}:started={data.get("started")}')
            return 2
        age = (time.time() - data.get('started', 0)) / 60.0
        log.warning('抢占失效锁：原持有者=%s, 进程存活=%s, 已过 %.1f 分钟', held_by, alive, age)
        try:
            LOCK.unlink()
        except OSError:
            pass
    if not _try_create(name):
        # 极小概率：抢占过程中被另一实例先一步创建
        now = _read() or {'name': '<race>', 'started': 0}
        print(f'LOCKED:held_by={now.get("name")}:started={now.get("started")}')
        return 2
    print(f'ACQUIRED:{name}')
    return 0


def release(name):
    data = _read()
    if not data:
        print('RELEASED')
        return 0
    if data.get('name') != name:
        log.warning('锁由 %s 持有，%s 无权释放，已跳过', data.get('name'), name)
        print('RELEASED')
        return 0
    try:
        LOCK.unlink()
    except OSError:
        pass
    print('RELEASED')
    return 0


def check(name, ttl):
    data = _read()
    if not data or not data.get('started'):
        print('FREE')
        return 0
    if _recent(data, ttl) and _pid_alive(data.get('pid')):
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
