# -*- coding: utf-8 -*-
"""
watchdog.py — 矿业日报「外部看门狗」的确定性感知层（零 LLM、零业务副作用）。

为什么需要它（2026-10-10）
--------------------------
国庆节后 05:30 起跑轮多次退化到 09:00–10:50 才上线；10-10 更因测试阶段挂死 71 分钟被
平台掐断，当天 09:13 才上线。同时 08:00 兜底任务在 10-10 因**平台侧启动失败**秒退
（success:false / 会话 jsonl 0 字节）。⇒「8:30 一定有内容」不能只靠平台侧的 agent 任务。

本脚本是最后一环里的**传感器**：只回答一个问题——线上页面是不是今天的？并把失败拆成
三种，好让恢复动作挑最便宜的那条：
  FRESH          线上日期 == 今天                 → 交付达成，什么都不用做。
  STALE_DEPLOY   本机日期 == 今天、线上不是        → 只需重跑 deploy_pages.py（便宜）。
  STALE_GENERATE 本机与线上都不是今天             → 需按 docs/PIPELINE.md 补跑整条链路。
  UNREACHABLE    抓不到 / 解析不出                 → 网络或 GitHub Pages 故障，人工看。
  LOCAL_OK       仅 --local-only：本机已是今天     → 供不联网的 OS 计划任务用（永不卡网络）。

子命令
------
  check  [--expect-date YYYY-MM-DD] [--local-only] [--json] [--quiet]   # 纯感知，无副作用
  alert  [--expect-date ...] [--local-only] [--skip-if-locked]          # check 后若异常：响铃+落盘+记日志
  show                                                                  # 打印上次 alert 记录

退出码：0 FRESH/LOCAL_OK / 1 STALE_DEPLOY / 2 STALE_GENERATE / 3 UNREACHABLE

分层用法（2026-10-10 设计）：
  · WorkBuddy 08:30 自动化  → `check --json`（联网、要能区分 DEPLOY/GENERATE）。
  · Windows 计划任务（真·外部）→ `alert --local-only --skip-if-locked`（不联网、不卡、只响铃）。

⚠️ 本机 HTTP 代理常驻注册表（HKCU …\\Internet Settings 的 ProxyEnable=1 → 127.0.0.1:7890）
   且代理进程经常没起；此时 `urllib.request.urlopen` 一律走死端口报 WinError 10061，
   与信源本身无关（见项目 memory §12）。故本脚本一律用 `build_opener(ProxyHandler({}))`
   直连（与 validate_urls.py / fetch_ma.py 同法）。
"""
import argparse
import json
import re
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
LOCAL_INDEX = ROOT / 'index.html'
LOCK_FILE = ROOT / '.automation.lock'
LAST_RUN = ROOT / '.last_run_status.json'
ALERT_FILE = ROOT / '.watchdog_alert.json'
TMP = ROOT / 'tmp'
LOG_FILE = TMP / 'watchdog.log'

LIVE_URL = 'https://pliucugb-cyber.github.io/mining-daily/index.html'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) mining-daily-watchdog'
SOUND_NOTIFY = 'C:/Windows/Media/Windows Notify.wav'

VERDICT_FRESH = 'FRESH'
VERDICT_STALE_DEPLOY = 'STALE_DEPLOY'
VERDICT_STALE_GENERATE = 'STALE_GENERATE'
VERDICT_UNREACHABLE = 'UNREACHABLE'
VERDICT_LOCAL_OK = 'LOCAL_OK'          # --local-only：本机已是今日（不校验线上）

EXIT = {VERDICT_FRESH: 0, VERDICT_STALE_DEPLOY: 1, VERDICT_STALE_GENERATE: 2,
        VERDICT_UNREACHABLE: 3, VERDICT_LOCAL_OK: 0}

# 直连 opener（绕过注册表里的死代理）。见模块 docstring。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 日期徽标（§42.8：头部红底 .date-badge 是全站日期的唯一来源）
_BADGE_RE = re.compile(r'class="date-badge"[^>]*>([^<]*)<')
_BADGE_DATE_RE = re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')
# build-version：<meta name="build-version" content="20261010-0705">
_BUILD_RE_A = re.compile(r'name="build-version"[^>]*?content="([^"]+)"')
_BUILD_RE_B = re.compile(r'content="([^"]+)"[^>]*?name="build-version"')
_BUILD_DATE_RE = re.compile(r'(\d{4})(\d{2})(\d{2})-\d{4}')


# ────────────────────────────── 纯函数（可单测，无 IO） ──────────────────────────────

def parse_badge(html):
    """从 HTML 里取「日期徽标」日期 → 'YYYY-MM-DD' 或 None。"""
    m = _BADGE_RE.search(html or '')
    if not m:
        return None
    d = _BADGE_DATE_RE.search(m.group(1))
    if not d:
        return None
    return '%s-%02d-%02d' % (d.group(1), int(d.group(2)), int(d.group(3)))


def parse_build(html):
    """从 HTML 里取 build-version 的日期部分 → 'YYYY-MM-DD' 或 None。"""
    m = _BUILD_RE_A.search(html or '') or _BUILD_RE_B.search(html or '')
    if not m:
        return None
    v = _BUILD_DATE_RE.search(m.group(1))
    if not v:
        return None
    return '%s-%s-%s' % (v.group(1), v.group(2), v.group(3))


def parse_build_raw(html):
    """取 build-version 原文（如 '20261010-0705'），取不到返回 None。"""
    m = _BUILD_RE_A.search(html or '') or _BUILD_RE_B.search(html or '')
    return m.group(1) if m else None


def decide(live_html, local_html, expect, local_only=False):
    """核心判定。返回 dict(verdict, live, local, live_build)。

    live/local 取「徽标日期优先、build-version 兜底」——徽标是内容日期（权威）。
    local_only=True 时不看线上，只判本机（供不联网的 OS 计划任务用）。
    """
    local_badge = parse_badge(local_html) if local_html is not None else None
    local_build = parse_build(local_html) if local_html is not None else None
    local = local_badge or local_build

    if local_only:
        verdict = VERDICT_LOCAL_OK if local == expect else VERDICT_STALE_GENERATE
        return {'verdict': verdict, 'live': None, 'local': local,
                'live_badge': None, 'live_build': None,
                'local_badge': local_badge, 'local_build': local_build,
                'local_only': True}

    live_badge = parse_badge(live_html) if live_html is not None else None
    live_build = parse_build(live_html) if live_html is not None else None
    live = live_badge or live_build

    if live is None:
        verdict = VERDICT_UNREACHABLE
    elif live == expect:
        verdict = VERDICT_FRESH
    elif local == expect:
        verdict = VERDICT_STALE_DEPLOY
    else:
        verdict = VERDICT_STALE_GENERATE
    return {'verdict': verdict, 'live': live, 'local': local,
            'live_badge': live_badge, 'live_build': live_build,
            'local_badge': local_badge, 'local_build': local_build,
            'local_only': False}


def today_cn():
    """北京时间的今天 → 'YYYY-MM-DD'。"""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%Y-%m-%d')


# ────────────────────────────── 带 IO 的取数 ──────────────────────────────

def fetch(url, timeout=20, attempts=2, deadline=45):
    """直连抓取（带 cache-buster）。整体墙钟硬上限 deadline 秒，超时抛 TimeoutError。

    ⚠️ 实测（2026-10-10）：在 Windows **计划任务**上下文中，DNS/连接可能无视
    socket timeout 长时间挂起（进程活着但不耗 CPU）。故用 daemon 线程做**硬墙钟**
    保护——线程超时后主流程照常返回/退出，不会被永久卡住。
    """
    box = {}

    def worker():
        last = None
        sep = '&' if '?' in url else '?'
        for i in range(attempts):
            u = '%s%st=%d' % (url, sep, int(time.time() * 1000))
            try:
                req = urllib.request.Request(u, headers={
                    'User-Agent': UA, 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
                with _OPENER.open(req, timeout=timeout) as r:
                    box['html'] = r.read().decode('utf-8', 'replace')
                    return
            except Exception as e:      # 网络异常（含 WinError 10061 死代理）
                last = e
                if i < attempts - 1:
                    time.sleep(1.5 * (i + 1))
        box['err'] = last

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join(deadline)
    if th.is_alive():
        raise TimeoutError('fetch 超过 %.0fs 硬墙钟：%s' % (deadline, url))
    if 'html' in box:
        return box['html']
    raise box['err'] if box.get('err') else RuntimeError('fetch failed')


def read_local():
    """读本机 index.html；不存在返回 None。"""
    try:
        return LOCAL_INDEX.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return None


def lock_state():
    """读互斥锁状态（供汇报/决策参考，不影响判定）。"""
    try:
        d = json.loads(LOCK_FILE.read_text(encoding='utf-8'))
        last = max(d.get('beat') or 0, d.get('started') or 0)
        return {'name': d.get('name'), 'age_min': round((time.time() - last) / 60.0, 1)}
    except Exception:
        return None


def last_run():
    """读 .last_run_status.json（供汇报参考）。"""
    try:
        d = json.loads(LAST_RUN.read_text(encoding='utf-8'))
        return {'status': d.get('status'), 'task': d.get('task'), 'time': d.get('time')}
    except Exception:
        return None


def run_check(expect=None, live_url=LIVE_URL, local_only=False):
    """执行一次完整感知。返回 (verdict, info dict)。"""
    expect = expect or today_cn()
    if local_only:
        info = decide(None, read_local(), expect, local_only=True)
        info['expect'] = expect
        info['live_build_raw'] = None
        info['reachable'] = None
        info['lock'] = lock_state()
        info['last_run'] = last_run()
        return info['verdict'], info
    try:
        live_html = fetch(live_url)
        reachable = True
    except Exception as e:
        live_html = None
        reachable = False
        err = '%s: %s' % (type(e).__name__, e)
    info = decide(live_html, read_local(), expect)
    info['expect'] = expect
    info['live_build_raw'] = parse_build_raw(live_html) if live_html else None
    info['reachable'] = reachable
    if not reachable:
        info['error'] = err
    info['lock'] = lock_state()
    info['last_run'] = last_run()
    return info['verdict'], info


def _log(info):
    """追加一行日志（tmp/watchdog.log）。best-effort。"""
    try:
        TMP.mkdir(exist_ok=True)
        line = '%s  %-15s live=%s local=%s expect=%s build=%s\n' % (
            time.strftime('%Y-%m-%d %H:%M:%S'), info.get('verdict'),
            info.get('live'), info.get('local'), info.get('expect'),
            info.get('live_build_raw'))
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass


def _play(sound=SOUND_NOTIFY):
    """播 Windows 提示音（与 notify_status.py 同法；不用 Add-Type/beep）。"""
    try:
        ps = "(New-Object System.Media.SoundPlayer '%s').PlaySync()" % sound
        subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       check=False, capture_output=True, timeout=30)
    except Exception:
        pass


def _alert(info):
    """落盘 .watchdog_alert.json + 记日志 + 响铃（同 (date,verdict) 只响一次）。"""
    prev = {}
    try:
        prev = json.loads(ALERT_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    key = '%s|%s' % (info.get('expect'), info.get('verdict'))
    if prev.get('key') == key:
        return False                      # 已就同一判定报过，避免重复响铃
    payload = dict(info)
    payload['key'] = key
    payload['alerted_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    payload['hint'] = {
        VERDICT_STALE_DEPLOY: '本机已是今日、线上不是 → 重跑 PY deploy_pages.py 即可',
        VERDICT_STALE_GENERATE: '本机与线上都不是今日 → 按 docs/PIPELINE.md 补跑整条链路',
        VERDICT_UNREACHABLE: '抓不到线上（网络/Pages 故障）→ 人工确认',
    }.get(info.get('verdict'), '')
    try:
        ALERT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                              encoding='utf-8')
    except Exception:
        pass
    _log(info)
    _play()
    return True


# ────────────────────────────── CLI ──────────────────────────────

def _print_human(info):
    live = info.get('live')
    print('WATCHDOG=%s live=%s local=%s expect=%s build=%s' % (
        info['verdict'], live if live else ('(未校验)' if info.get('local_only') else None),
        info.get('local'), info.get('expect'), info.get('live_build_raw')))
    if info.get('error'):
        print('  错误: %s' % info['error'])
    if info.get('lock'):
        print('  锁: %s（%.1f 分钟前心跳）' % (info['lock']['name'], info['lock']['age_min']))
    if info.get('last_run'):
        print('  上次运行: %s / %s / %s' % (
            info['last_run'].get('status'), info['last_run'].get('task'),
            info['last_run'].get('time')))


def cmd_check(args):
    verdict, info = run_check(args.expect_date, local_only=args.local_only)
    _log(info)
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    elif not args.quiet:
        _print_human(info)
    return EXIT[verdict]


def cmd_alert(args):
    verdict, info = run_check(args.expect_date, local_only=args.local_only)
    code = EXIT[verdict]
    if code == 0:
        _log(info)
        if not args.quiet:
            print('WATCHDOG=%s live=%s（无需告警）' % (
                verdict, info.get('live') or '（未联网校验）'))
        return 0
    # 有活动锁 ⇒ 说明 05:30/08:00 正在跑（多半正在恢复）→ 不误报。
    if args.skip_if_locked and info.get('lock') and \
            info['lock'].get('age_min', 1e9) < args.lock_ttl:
        _log(info)
        if not args.quiet:
            print('WATCHDOG=%s 但检测到活动锁 %s（%.1f 分钟前心跳）→ 判定为「正在运行」，不告警'
                  % (verdict, info['lock']['name'], info['lock']['age_min']))
        return 0
    # UNREACHABLE 默认不响铃（网络抖动/Pages 故障无法与真故障区分，避免噪声）。
    if verdict == VERDICT_UNREACHABLE and not args.alert_unreachable:
        _log(info)
        if not args.quiet:
            print('WATCHDOG=UNREACHABLE（抓不到线上，无法判定）→ 仅记日志，不告警')
        return code
    fired = _alert(info)
    if not args.quiet:
        _print_human(info)
        print('  告警: %s' % ('已响铃+落盘' if fired else '已就同一判定报过，跳过响铃'))
    return code


def cmd_show(args):
    try:
        d = json.loads(ALERT_FILE.read_text(encoding='utf-8'))
    except Exception:
        print('（无告警记录）')
        return 0
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description='矿业日报外部看门狗·确定性感知层')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('check', help='抓线上页面判定是否今日（无副作用）')
    p.add_argument('--expect-date', help='期望日期 YYYY-MM-DD（默认今天·北京时间）')
    p.add_argument('--local-only', action='store_true',
                   help='只看本机 index.html，不联网（计划任务/断网时用）')
    p.add_argument('--json', action='store_true')
    p.add_argument('--quiet', action='store_true')
    p.set_defaults(func=cmd_check)

    p = sub.add_parser('alert', help='check 后若异常：响铃+落盘+记日志')
    p.add_argument('--expect-date')
    p.add_argument('--local-only', action='store_true',
                   help='只看本机 index.html，不联网（推荐给 OS 计划任务：不会卡在网络上）')
    p.add_argument('--skip-if-locked', action='store_true',
                   help='检测到活动锁（有运行正在进行）时不告警，避免误报')
    p.add_argument('--alert-unreachable', action='store_true',
                   help='UNREACHABLE 时也响铃（默认不响，避免网络抖动噪声）')
    p.add_argument('--lock-ttl', type=float, default=60.0,
                   help='活动锁判定窗口（分钟，默认 60）')
    p.add_argument('--quiet', action='store_true')
    p.set_defaults(func=cmd_alert)

    p = sub.add_parser('show', help='打印上次告警记录')
    p.set_defaults(func=cmd_show)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    main()
