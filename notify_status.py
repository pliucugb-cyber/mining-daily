# -*- coding: utf-8 -*-
"""
notify_status.py — 自动化失败/异常主动通知（方案 C）。

目的：今天的问题是用户「主动发现慢」，系统没有主动告警。
本脚本在任务失败/异常/被跳过时：
  1. 播放 Windows 提示音（用户已确认 Windows Notify.wav / tada.wav 可听到）；
  2. 写 .last_run_status.json 状态文件（用户可随时查看最近一次运行状态）。

用法（在 automation 运行环境、项目目录下执行）：
  python notify_status.py fail <任务名> [错误信息]   # 播放 Windows Notify + 写 status=fail
  python notify_status.py warn <任务名> [提示信息]   # 播放 Windows Notify + 写 status=warn（被跳过/需注意）
  python notify_status.py ok   <任务名> [信息]       # 仅写 status=ok（不发声；完成 tada 由任务 prompt 播放）

状态文件 .last_run_status.json 不应被 git 提交。

说明：Windows 提示音用 PowerShell System.Media.SoundPlayer 播放（用户环境实测可用）；
不使用 Add-Type / [console]::beep()（被安全策略拦截或无声）。
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
STATUS = ROOT / '.last_run_status.json'
SOUND_NOTIFY = 'C:/Windows/Media/Windows Notify.wav'


def _play(sound):
    try:
        ps = f'(New-Object System.Media.SoundPlayer \'{sound}\').PlaySync()'
        subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       check=False, capture_output=True, timeout=30)
    except Exception as e:
        print(f'play_sound_error:{e}')


def _write_status(status, task, msg):
    data = {
        'status': status,
        'task': task,
        'msg': msg or '',
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'ts': int(time.time()),
    }
    try:
        STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        print(f'write_status_error:{e}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('kind', choices=['fail', 'warn', 'ok'])
    ap.add_argument('task')
    ap.add_argument('msg', nargs='?', default='')
    args = ap.parse_args()

    if args.kind == 'fail':
        _play(SOUND_NOTIFY)
        _write_status('fail', args.task, args.msg)
        print('NOTIFIED_FAIL')
    elif args.kind == 'warn':
        _play(SOUND_NOTIFY)
        _write_status('warn', args.task, args.msg)
        print('NOTIFIED_WARN')
    else:  # ok：仅写状态，不重复发声
        _write_status('ok', args.task, args.msg)
        print('NOTIFIED_OK')


if __name__ == '__main__':
    main()
