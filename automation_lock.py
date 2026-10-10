# -*- coding: utf-8 -*-
"""
automation_lock.py — 矿业日报自动化任务互斥锁（方案 B+ 心跳版）。

目的：防止 05:30 抓取生成 与 08:00 复验核对 并发操作同一批文件
（同时改 index.html / 推 git 会造成脏版本）。

用法（在 automation 运行环境、项目目录下执行）：
  python automation_lock.py acquire <name> [--ttl 分钟] [--force]  # 获取锁；被占用退出码 2
  python automation_lock.py release <name>                        # 释放锁（须同名）
  python automation_lock.py check  <name> [--ttl 分钟]             # FREE(0)/LOCKED(1)/STALE(3)
  python automation_lock.py renew  <name>                         # 刷新心跳（长任务用）

对外协议（05:30 / 08:00 自动化依赖，勿改）：
  acquire → "ACQUIRED:<name>"(0) 或 "LOCKED:held_by=<name>:started=<ts>"(2)
  release → "RELEASED"(0)
  check   → "FREE"(0) / "LOCKED:held_by=<name>"(1) / "STALE"(3)
  renew   → "RENEWED:<name>"(0) / "NOOP"(0)      # 新增动作，未改既有协议

锁文件 .automation.lock（JSON：{name, started, pid, beat}）。该文件不应被 git 提交。

────────────────────────────────────────────────────────────────────────
2026-10-10 P1 修复：互斥曾经形同虚设
────────────────────────────────────────────────────────────────────────
【根因】锁里写的 `pid` 是**执行 acquire 的那个短命子进程**：`acquire` 一返回、
该进程即退出，而判定条件是 `_recent(ttl) and alive` → `alive` 恒为 False
→ **第二个实例必然抢占成功**，本该防并发的保护完全不存在。
实测（10-10 09:20）：
    acquire testA          → ACQUIRED
    1 秒后 check testA     → STALE(3)      ← 本该 LOCKED
    acquire testB          → ACQUIRED(0)   ← 本该被拒
    log: 抢占失效锁：原持有者=testA, 进程存活=False, 已过 0.4 分钟

【修法】持有者不是「进程」而是**一次 agent 会话**，pid 无从可靠判定存活
（会话跨越无数个短命子进程）。于是改为 **心跳 + 纯时间戳**：
  · 锁的「新鲜度」= now - max(started, beat) < ttl；新鲜即 LOCKED，过期才可抢占。
  · 长任务用 `runq.py` 每次跑脚本时调 `heartbeat()` 刷新 `beat`（见 runq.py），
    也可显式 `renew <name>`；只要任务还在干活，锁就一直新鲜 → 正确阻塞并发。
  · 任务挂死/被杀 → 心跳停止 → 超过 ttl（默认 60 分钟）即判 STALE → 下一轮可自动接管。
  · `--force` 供人工在明确知道无人持有锁时强制接管（应急用）。

【TTL 取值】默认 60 分钟。生成链路目标 ≤2 小时、且 05:30→08:00 间隔 150 分钟：
心跳保证「活着就一直锁着」；只有真正 >60 分钟无任何脚本执行才算失效，
足以让 08:00 兜底在 05:30 任务挂死时接管，又不会误伤正常的慢任务。
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
DEFAULT_TTL = 60  # 分钟：无心跳多久即判失效（心跳版，见模块 docstring）

# 注意：本脚本的 stdout 是**机器协议**（ACQUIRED:/LOCKED:/RELEASED/FREE/STALE/RENEWED/NOOP），
# 05:30 与 08:00 自动化直接解析它。这些行**必须**保持裸 print，不得加日志前缀，
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


def _write_atomic(data):
    """原子写锁文件：tmp + os.replace，避免读到半截 JSON。"""
    tmp = LOCK.with_suffix('.lock.tmp')
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(payload)
    os.replace(tmp, LOCK)


def _pid_alive_windows(pid):
    """Windows：只读探测进程是否存在（OpenProcess + 立即 CloseHandle）。

    仅用于**诊断日志**（报告原持有者进程是否还活着），不再参与互斥判定。
    刻意不用 os.kill(pid, 0)——Windows 上它的语义是「可终止」而非「存在探测」。
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
        return True          # 探测失败 → 保守视为存活


def _pid_alive(pid):
    """跨平台判断进程是否存活。**仅供诊断日志**，不参与锁判定。"""
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
    now = time.time()
    payload = {'name': name, 'started': now, 'pid': os.getpid(), 'beat': now}
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        return False
    return True


def _fresh(data, ttl):
    """锁是否新鲜：心跳时间（beat，无则退回 started）在 ttl 分钟内。

    2026-10-10 起不再看 pid——见模块 docstring：持有者是一次 agent 会话，
    其 pid 是短命子进程，判定必然误判为「已死」。
    """
    last = max(data.get('beat') or 0, data.get('started') or 0)
    return (time.time() - last) < ttl * 60


def heartbeat():
    """尽力刷新锁心跳（供 runq.py 调用）：锁文件存在则把 beat 更新为当前时间。

    不改变持有者、不创建锁。任何异常都吞掉（纯尽力而为，绝不影响主流程）。
    返回 True/False 仅供诊断。
    """
    try:
        data = _read()
        if not data or not data.get('started'):
            return False
        data['beat'] = time.time()
        _write_atomic(data)
        return True
    except Exception:
        return False


def acquire(name, ttl, force=False):
    data = _read()
    if data and not force:
        if _fresh(data, ttl):
            print(f'LOCKED:held_by={data.get("name")}:started={data.get("started")}')
            return 2
        # 过期：记一条诊断（含 pid 是否存活，仅参考）
        alive = _pid_alive(data.get('pid'))
        age = (time.time() - (data.get('beat') or data.get('started') or 0)) / 60.0
        log.warning('抢占失效锁：原持有者=%s, 进程存活=%s, 已过 %.1f 分钟', data.get('name'), alive, age)
        try:
            LOCK.unlink()
        except OSError:
            pass
    elif data and force:
        log.warning('--force 强制接管：原持有者=%s', data.get('name'))
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


def renew(name):
    """刷新心跳：仅当锁由 <name> 持有时把 beat 置为当前时间。"""
    data = _read()
    if not data or data.get('name') != name:
        print('NOOP')
        return 0
    try:
        data['beat'] = time.time()
        _write_atomic(data)
    except OSError:
        print('NOOP')
        return 0
    print(f'RENEWED:{name}')
    return 0


def check(name, ttl):
    data = _read()
    if not data or not data.get('started'):
        print('FREE')
        return 0
    if _fresh(data, ttl):
        print(f'LOCKED:held_by={data.get("name")}')
        return 1
    print('STALE')
    return 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['acquire', 'release', 'check', 'renew'])
    ap.add_argument('name')
    ap.add_argument('--ttl', type=int, default=DEFAULT_TTL)
    ap.add_argument('--force', action='store_true',
                    help='acquire 时强制接管（无视新鲜度，应急人工用）')
    args = ap.parse_args()
    if args.action == 'acquire':
        sys.exit(acquire(args.name, args.ttl, force=args.force))
    if args.action == 'release':
        sys.exit(release(args.name))
    if args.action == 'renew':
        sys.exit(renew(args.name))
    sys.exit(check(args.name, args.ttl))


if __name__ == '__main__':
    main()
