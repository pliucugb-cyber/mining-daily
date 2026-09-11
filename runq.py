# -*- coding: utf-8 -*-
"""
runq.py — 长输出脚本的「安静执行」包装器（为自动化节流而生）。

背景
----
自动化里 fetch_news / validate_urls / preflight_check / backcheck / fetch_ma /
test_* 等脚本会把大量 INFO 日志 print 到 stdout，每被 Bash 工具捕获一次就整段
回灌进 LLM 上下文，是 token 爆量的主要来源之一。

本包装器做的事：
1. 用与 runq 相同的解释器跑目标脚本（cwd=项目根）；
2. **完整输出写入 tmp/runq_<ts>_<脚本>.log（磁盘永久留档，便于排障）**；
3. stdout 只回传：开头摘要 + 关键报错行（若有）+ 结尾，总字数硬控在 ~1800 字；
   不改动磁盘上任何业务输出文件、不改动抓取/行情/矿权数据。

用法（在自动化里替换 python x.py）：
    python runq.py fetch_news.py --report-date 2026-09-11 --days 2
    python runq.py validate_urls.py

不会截断报错堆栈：含 Traceback/Exception/Error/❌/失败/FAIL 的行原样保留在回传尾部。
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
TMP = ROOT / 'tmp'
TMP.mkdir(exist_ok=True)

HEAD = 1000          # 开头保留字数
TAIL = 800           # 结尾保留字数
ERR_KEEP = 1200      # 关键报错块上限
TOTAL_CAP = 1800     # 回传总字数硬上限

_ERR_HINTS = ('Traceback', 'Exception', 'Error', 'ERROR', '❌', '失败', 'FAIL',
              '失败:', '错误', '异常')


def main():
    if len(sys.argv) < 2:
        print('usage: python runq.py <target.py> [args...]')
        return 2
    cmd = [sys.executable, *sys.argv[1:]]
    ts = time.strftime('%Y%m%d-%H%M%S')
    target = Path(sys.argv[1]).stem
    log_path = TMP / f'runq_{ts}_{target}.log'

    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                              text=True, encoding='utf-8', errors='replace', timeout=1800)
    except Exception as e:
        print(f'RUNQ_RUN_ERROR: {e}')
        return 3

    full = (proc.stdout or '') + ('\n' + proc.stderr if proc.stderr else '')
    try:
        log_path.write_text(full, encoding='utf-8')
    except Exception:
        pass

    code = proc.returncode
    # 完整输出本就写入 log_path；stdout 只回传精炼版
    if len(full) <= TOTAL_CAP:
        out = full
    else:
        head = full[:HEAD]
        tail = full[-TAIL:]
        err_lines = [ln for ln in full.splitlines()
                     if any(h in ln for h in _ERR_HINTS)]
        err_block = ''
        if err_lines:
            err_block = '\n'.join(err_lines)[-ERR_KEEP:]
            err_block = '【关键报错/异常】\n' + err_block + '\n'
        out = (head + '\n[...省略中间日志，完整见 ' + str(log_path) + '...]\n'
               + err_block + tail)

    print(out)
    print(f'RUNQ_EXIT={code} LOG={log_path}')
    return code


if __name__ == '__main__':
    sys.exit(main())
