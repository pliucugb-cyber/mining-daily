# -*- coding: utf-8 -*-
"""
test_automation_lock.py — 自动化互斥锁回归测试（2026-10-10 P1）

背景
----
automation_lock.py 原判定 `_recent(ttl) and alive`，但锁里写的 `pid` 是**执行 acquire
的短命子进程** → acquire 一返回该进程即退出 → `alive` 恒为 False → **第二个实例必然
抢占成功**，本该防 05:30 / 08:00 并发的保护完全不存在。

修复
----
改为「心跳 + 纯时间戳」，不再看 pid：锁新鲜度 = now - max(started, beat) < ttl；
长任务经 runq.py 每次跑脚本刷新心跳；挂死 >ttl（默认 60 分钟）才可被接管。

本测试锁住：① 第二实例必被拒；② pid 消失但心跳新鲜仍 LOCKED；③ 过期可接管；
④ 释放/续约/强制接管；⑤ 源码守卫（旧 pid 判定已移除、runq 已挂心跳）。
测试在临时目录上跑，不碰真实 .automation.lock。

运行：python test_automation_lock.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import automation_lock as A  # noqa: E402

pass_n = 0
fail_n = 0


def check(name, cond, detail=''):
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print('  [PASS] %s%s' % (name, (' | ' + detail) if detail else ''))
    else:
        fail_n += 1
        print('  [FAIL] %s%s' % (name, (' | ' + detail) if detail else ''))


# 隔离到临时锁文件，绝不碰真实 .automation.lock
_TMP = tempfile.mkdtemp(prefix='md_lock_test_')
A.LOCK = Path(_TMP) / '.automation.lock'


def run(action, name, ttl=None, force=False):
    ttl = A.DEFAULT_TTL if ttl is None else ttl
    buf = io.StringIO()
    with redirect_stdout(buf):
        if action == 'acquire':
            rc = A.acquire(name, ttl, force=force)
        elif action == 'release':
            rc = A.release(name)
        elif action == 'renew':
            rc = A.renew(name)
        else:
            rc = A.check(name, ttl)
    return rc, buf.getvalue().strip()


try:
    print('===== ① 基础协议 =====')
    rc, out = run('check', 'x')
    check('无锁时 check=FREE(0)', rc == 0 and out == 'FREE', out)
    rc, out = run('acquire', 'testA')
    check('acquire 首次=ACQUIRED(0)', rc == 0 and out == 'ACQUIRED:testA', out)
    d = json.loads(A.LOCK.read_text(encoding='utf-8'))
    check('锁文件含 name/started/pid/beat',
          d.get('name') == 'testA' and bool(d.get('started')) and bool(d.get('beat')), str(sorted(d.keys())))

    print('===== ② ★ 回归：并发第二实例必须被拒 =====')
    rc, out = run('check', 'testA')
    check('check= LOCKED(1)', rc == 1 and out.startswith('LOCKED:held_by=testA'), out)
    rc, out = run('acquire', 'testB')
    check('★ 第二实例 acquire 被拒 = LOCKED(2)', rc == 2 and 'held_by=testA' in out, out)

    print('===== ③ ★ pid 消失但心跳新鲜仍锁（旧版此处误判 STALE）=====')
    d = json.loads(A.LOCK.read_text(encoding='utf-8'))
    d['pid'] = 999999  # 一个不存在的 pid
    A.LOCK.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    rc, out = run('check', 'testA')
    check('★ pid 不存在但心跳新鲜 → 仍 LOCKED(1)', rc == 1, out)
    rc, out = run('acquire', 'testC')
    check('★ pid 不存在也不得被抢占（旧版会 ACQUIRED）', rc == 2, out)

    print('===== ④ 心跳 / 续约 =====')
    check('heartbeat() 锁存在 → True', A.heartbeat() is True)
    rc, out = run('renew', 'testB')
    check('renew 名字不符 = NOOP(0)', rc == 0 and out == 'NOOP', out)
    rc, out = run('renew', 'testA')
    check('renew 同名 = RENEWED(0)', rc == 0 and out == 'RENEWED:testA', out)

    print('===== ⑤ 过期后可自动接管 =====')
    d = json.loads(A.LOCK.read_text(encoding='utf-8'))
    d['started'] = time.time() - 3600
    d['beat'] = time.time() - 3600
    A.LOCK.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    rc, out = run('check', 'testA')
    check('过期 → check=STALE(3)', rc == 3 and out == 'STALE', out)
    rc, out = run('acquire', 'testC')
    check('过期 → acquire 自动接管 = ACQUIRED(0)', rc == 0 and out == 'ACQUIRED:testC', out)

    print('===== ⑥ --force 强制接管 =====')
    rc, out = run('acquire', 'testD', force=True)
    check('--force 强制接管 = ACQUIRED(0)', rc == 0 and out == 'ACQUIRED:testD', out)

    print('===== ⑦ 释放 =====')
    rc, out = run('release', 'testC')
    check('release 名字不符 = RELEASED 但不解锁', rc == 0 and out == 'RELEASED' and A.LOCK.exists(), out)
    rc, out = run('release', 'testD')
    check('release 同名 = RELEASED 且删除锁', rc == 0 and not A.LOCK.exists(), out)
    rc, out = run('check', 'testD')
    check('释放后 check=FREE(0)', rc == 0 and out == 'FREE', out)
    rc, out = run('renew', 'testD')
    check('无锁时 renew = NOOP(0)', rc == 0 and out == 'NOOP', out)
    check('无锁时 heartbeat() → False', A.heartbeat() is False)

    print('===== ⑧ 源码守卫（防回退）=====')
    src = open(os.path.join(BASE, 'automation_lock.py'), encoding='utf-8').read()
    check('旧判定 `if _recent(` 已移除', 'if _recent(' not in src)
    check('新判定 `_fresh(data, ttl)` 出现 ≥2 处（acquire + check）',
          src.count('_fresh(data, ttl)') >= 2, 'n=%d' % src.count('_fresh(data, ttl)'))
    check('DEFAULT_TTL = 60（心跳版）', 'DEFAULT_TTL = 60' in src)
    check('协议串仍齐备（ACQUIRED/LOCKED:held_by/RELEASED/STALE）',
          all(s in src for s in ('ACQUIRED:', 'LOCKED:held_by=', 'RELEASED', 'STALE')))
    runq = open(os.path.join(BASE, 'runq.py'), encoding='utf-8').read()
    check('runq.py 已挂心跳 heartbeat()', 'heartbeat()' in runq)

finally:
    shutil.rmtree(_TMP, ignore_errors=True)

print('\n===== 汇总 =====')
print('  通过 %d / 失败 %d' % (pass_n, fail_n))
sys.exit(1 if fail_n else 0)
