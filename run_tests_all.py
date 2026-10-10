# -*- coding: utf-8 -*-
"""run_tests_all.py — 日报测试套件的统一跑法（带单例超时与总预算）。

为什么要有它
------------
2026-10-10 06:00 轮在「测试套件」阶段卡了 71 分钟未跑完，直接拖到平台把会话掐断、
当天版本 09:13 才上线（用户要求 08:30 前看到）。根因之一是**没有任何单例超时**：
一个测试挂死就能拖垮整轮。本脚本就是为此加的闸门。

三条硬保障
----------
1. **单例超时**：每个测试 240s（可 --per-test 覆盖）。超时即 `taskkill /F /T` 杀**整棵进程树**
   （node 常派生孙进程），记 TIMEOUT，继续跑下一个——绝不因一个测试挂死拖垮全局。
2. **总预算**：默认 2100s（35min，可 --budget 覆盖）。超预算后剩余测试记 SKIP，
   脚本立即收敛返回，保证有界退出。
3. **自起静态服务**：test_p3_* 等需 `http://127.0.0.1:8899/`；本脚本在进程内起一个
   后台 HTTP 服务（daemon 线程），跑完即回收，免去手动起 server。

回传口径
--------
stdout 只打紧凑汇总（每个测试一行 + 总计），完整输出落 `tmp/run_tests_all_<ts>.log`，
JSON 明细落 `tmp/run_tests_all_<ts>.json`（两者都在 gitignore 的 tmp/ 下）。

退出码
------
0 = 全部跑完且 0 失败；1 = 有失败或超时；2 = 预算耗尽有 SKIP。

用法
----
    python run_tests_all.py                 # §42.9 基线核心集（默认，约 20 个）
    python run_tests_all.py --all           # 全量闸门：全部 test_*.js + test_*.py
    python run_tests_all.py price company   # 只跑文件名含这些子串的
    python run_tests_all.py --per-test 120 --budget 900
"""
import os
import re
import sys
import json
import time
import glob
import socket
import threading
import subprocess
import http.server
import socketserver
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
TMP = ROOT / 'tmp'
TMP.mkdir(exist_ok=True)

NODE = r'C:/Users/中铝矿业投并部/.workbuddy/binaries/node/versions/22.22.2-3/node.exe'
if not Path(NODE).exists():
    NODE = 'node'
PY = sys.executable

PROBE_PORT = 8899

# §42.9 基线核心集（改了哪块就跑对应测试；这里是「每轮必跑」的收敛集）
CORE = [
    'test_brief_layers.js',
    'test_smoke_0908.js',
    'test_mobile_ux_batch.js',
    'test_qa_features.js',
    'test_fav_history_aggregate.js',
    'test_price_unit_dedup.js',
    'test_price_heatmap.js',
    'test_event_calendar.js',
    'test_company_section.js',
    'test_sw_cache_update.js',
    'test_pwa_install_behavior.js',
    'test_rights_register.js',
    'test_data_integrity.js',
    'test_pwa_install.py',
    'test_kyregister.py',
    'test_price_history_unclosed.py',
    'test_automation_lock.py',
]

SUMMARY_RE = re.compile(r'(PASS|FAIL|通过|失败)', re.I)
# 两种书写顺序都要认：「17 PASS」与「通过 14」。
PASS_PATS = [re.compile(r'(\d+)\s*(?:个)?\s*(?:PASS|通过|passed)', re.I),
             re.compile(r'(?:PASS|通过|passed)\s*[:：=\s]*(\d+)', re.I)]
FAIL_PATS = [re.compile(r'(\d+)\s*(?:个)?\s*(?:FAIL|失败|failed)', re.I),
             re.compile(r'(?:FAIL|失败|failed)\s*[:：=\s]*(\d+)', re.I)]


def _last_num(patterns, text):
    val = None
    for pat in patterns:
        for m in pat.finditer(text):
            val = m.group(1)
    return val


def _free_port(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(('127.0.0.1', port))
        return False  # 已被占用
    except OSError:
        return True
    finally:
        s.close()


def _start_probe_server():
    """在进程内起 http://127.0.0.1:8899 静态服务；端口被占则跳过（用已有服务）。"""
    if not _free_port(PROBE_PORT):
        return None
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(
        *a, directory=str(ROOT), **k)

    class Srv(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    try:
        httpd = Srv(('127.0.0.1', PROBE_PORT), handler)
    except OSError:
        return None
    httpd.RequestHandlerClass.log_message = lambda *a, **k: None  # 静音访问日志
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def _kill_tree(pid):
    try:
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                       capture_output=True, timeout=20)
    except Exception:
        pass


def _run_one(path, per_test, env):
    exe = [NODE, path] if path.endswith('.js') else [PY, path]
    t0 = time.time()
    p = subprocess.Popen(exe, cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    timed_out = False
    try:
        out, _ = p.communicate(timeout=per_test)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(p.pid)
        try:
            out, _ = p.communicate(timeout=20)
        except Exception:
            out = b''
        rc = 'TIMEOUT'
    txt = (out or b'').decode('utf-8', 'replace')
    dur = time.time() - t0

    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    summ = ''
    for l in reversed(lines[-12:]):
        if SUMMARY_RE.search(l):
            summ = l
            break
    tail = '\n'.join(lines[-12:])
    scope = summ if summ else tail
    mp = _last_num(PASS_PATS, scope)
    mf = _last_num(FAIL_PATS, scope)
    return {
        'file': path, 'rc': rc, 'timeout': timed_out,
        'summary': summ[:140], 'pass': mp,
        'fail': mf, 'dur': round(dur, 1),
        'output': txt,
    }


def main():
    args = sys.argv[1:]
    per_test = 240
    budget = 2100
    run_all = False
    filters = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--all':
            run_all = True
        elif a == '--per-test':
            i += 1
            per_test = int(args[i])
        elif a == '--budget':
            i += 1
            budget = int(args[i])
        else:
            filters.append(a)
        i += 1

    if run_all:
        files = sorted(glob.glob('test_*.js')) + sorted(glob.glob('test_*.py'))
    else:
        files = [f for f in CORE if Path(f).exists()]
    if filters:
        files = [f for f in files if any(fl in f for fl in filters)]
    if not files:
        print('NO_TESTS_MATCHED')
        return 1

    env = dict(os.environ)
    env['NODE_PATH'] = str(ROOT / 'node_modules')
    env['PYTHONIOENCODING'] = 'utf-8'

    httpd = _start_probe_server()
    print(f'RUN_TESTS_ALL  n={len(files)}  per_test={per_test}s  budget={budget}s'
          f'  probe8899={"on" if httpd else "external/skip"}')

    ts = time.strftime('%Y%m%d-%H%M%S')
    rows = []
    t_start = time.time()
    for f in files:
        left = budget - (time.time() - t_start)
        if left <= 5:
            rows.append({'file': f, 'rc': 'SKIP', 'timeout': False, 'summary': '预算耗尽',
                         'pass': None, 'fail': None, 'dur': 0.0, 'output': ''})
            print(f'{f:<40} SKIP(预算耗尽)')
            continue
        r = _run_one(f, min(per_test, int(left)), env)
        rows.append(r)
        flag = 'TIMEOUT' if r['timeout'] else str(r['rc'])
        cnt = f"{r['pass'] or '-'}P/{r['fail'] or '-'}F"
        print(f"{f:<40} rc={flag:<8} {cnt:<12} {r['dur']:>6.1f}s  {r['summary'][:70]}")

    if httpd:
        try:
            httpd.shutdown()
        except Exception:
            pass

    total_dur = round(time.time() - t_start, 1)
    fails = [r for r in rows if r['timeout'] or (r['rc'] not in (0, 'SKIP'))]
    skips = [r for r in rows if r['rc'] == 'SKIP']
    hard_fail = [r for r in rows if r['timeout'] or
                 (isinstance(r['rc'], int) and r['rc'] != 0)]
    print(f'\nTOTAL n={len(rows)} fail={len(hard_fail)} skip={len(skips)} dur={total_dur}s')
    if hard_fail:
        print('FAILED: ' + ', '.join(r['file'] for r in hard_fail))

    log_path = TMP / f'run_tests_all_{ts}.log'
    with open(log_path, 'w', encoding='utf-8') as fh:
        for r in rows:
            fh.write(f"########## {r['file']}  rc={r['rc']}  {r['dur']}s ##########\n")
            fh.write(r['output'] or '')
            fh.write('\n\n')
    json_path = TMP / f'run_tests_all_{ts}.json'
    with open(json_path, 'w', encoding='utf-8') as fh:
        json.dump([{k: v for k, v in r.items() if k != 'output'} for r in rows],
                  fh, ensure_ascii=False, indent=1)
    print(f'LOG={log_path}')
    print(f'JSON={json_path}')

    if skips:
        return 2
    return 1 if hard_fail else 0


if __name__ == '__main__':
    sys.exit(main())
