# -*- coding: utf-8 -*-
"""
test_watchdog.py — watchdog.py（外部看门狗·感知层）的纯函数单测 + 防回退源码守卫。

不联网：只测解析与判定逻辑（fetch 由 run_check 的 live_url 注入隔离，
本单测不调用网络路径）。运行：PY test_watchdog.py
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import watchdog as W  # noqa: E402

pass_n = 0
fail_n = 0


def check(name, cond, extra=''):
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print('  PASS  %s' % name)
    else:
        fail_n += 1
        print('  FAIL  %s   %s' % (name, extra))


# 真实线上片段（含 data-page-node-id 干扰属性）
LIVE_SNIPPET = ('<h1 data-page-node-id="X">⛏️ 矿业资讯速览 '
                '<span class="date-badge" data-page-node-id="hCCkUOj51jKh8M4hgHwkAC">'
                '2026年10月10日 星期六</span></h1>')
BUILD_SNIPPET = ('<meta name="build-version" content="20261010-0705" '
                 'data-page-node-id="Or8MMXVChjPjb6rSx8wH8w">')
BUILD_REVERSED = '<meta content="20261009-0611" name="build-version">'

TODAY = '2026-10-10'
YEST = '2026-10-09'
# 注意：徽标是中文日期（2026年10月10日），不能拿 ISO 串做 replace。
YEST_SNIPPET = LIVE_SNIPPET.replace('2026年10月10日', '2026年10月9日')
YEST_BUILD = BUILD_SNIPPET.replace('20261010', '20261009')

print('===== ① parse_badge =====')
check('标准徽标 → 日期', W.parse_badge(LIVE_SNIPPET) == TODAY, W.parse_badge(LIVE_SNIPPET))
check('个位数月日补零', W.parse_badge('<span class="date-badge">2026年1月3日 星期六</span>') == '2026-01-03')
check('无徽标 → None', W.parse_badge('<h1>无</h1>') is None)
check('空串/None → None', W.parse_badge('') is None and W.parse_badge(None) is None)
check('徽标含空格容忍', W.parse_badge('<span class="date-badge"> 2026 年 10 月 10 日 </span>') == TODAY)

print('===== ② parse_build / parse_build_raw =====')
check('name→content 顺序', W.parse_build(BUILD_SNIPPET) == TODAY)
check('content→name 逆序', W.parse_build(BUILD_REVERSED) == YEST)
check('build 原文', W.parse_build_raw(BUILD_SNIPPET) == '20261010-0705')
check('无 build → None', W.parse_build('<html></html>') is None)

print('===== ③ decide：四种判定 =====')
d = W.decide(LIVE_SNIPPET, LIVE_SNIPPET, TODAY)
check('线上今日 → FRESH', d['verdict'] == W.VERDICT_FRESH, d['verdict'])
d = W.decide(YEST_SNIPPET, LIVE_SNIPPET, TODAY)
check('本机今日/线上昨日 → STALE_DEPLOY', d['verdict'] == W.VERDICT_STALE_DEPLOY, d['verdict'])
d = W.decide(YEST_SNIPPET, YEST_SNIPPET, TODAY)
check('两边都昨日 → STALE_GENERATE', d['verdict'] == W.VERDICT_STALE_GENERATE, d['verdict'])
d = W.decide(None, LIVE_SNIPPET, TODAY)
check('抓不到线上 → UNREACHABLE', d['verdict'] == W.VERDICT_UNREACHABLE, d['verdict'])
d = W.decide('<html>无标记</html>', LIVE_SNIPPET, TODAY)
check('线上无任何日期标记 → UNREACHABLE', d['verdict'] == W.VERDICT_UNREACHABLE, d['verdict'])
d = W.decide(None, LIVE_SNIPPET, TODAY)
check('本机缺 index.html（None）也不崩', d['local'] == TODAY)

print('===== ④ 徽标优先于 build-version（§42.8 日期唯一来源）=====')
mixed_live = LIVE_SNIPPET + YEST_BUILD
d = W.decide(mixed_live, LIVE_SNIPPET, TODAY)
check('徽标=今日、build=昨日 → FRESH（认徽标）',
      d['verdict'] == W.VERDICT_FRESH, '%s live=%s' % (d['verdict'], d['live']))
only_build = YEST_SNIPPET.replace('date-badge', 'x-badge') + BUILD_SNIPPET
d = W.decide(only_build, LIVE_SNIPPET, TODAY)
check('徽标缺失时用 build 兜底 → FRESH', d['verdict'] == W.VERDICT_FRESH, d['verdict'])

print('===== ④b local_only（OS 计划任务路径，不联网）=====')
d = W.decide(None, LIVE_SNIPPET, TODAY, local_only=True)
check('本机今日 → LOCAL_OK', d['verdict'] == W.VERDICT_LOCAL_OK, d['verdict'])
check('local_only 不设 live', d['live'] is None and d['local_only'] is True)
d = W.decide('随便什么线上内容', YEST_SNIPPET, TODAY, local_only=True)
check('本机昨日 → STALE_GENERATE（忽略线上）',
      d['verdict'] == W.VERDICT_STALE_GENERATE, d['verdict'])
d = W.decide(None, None, TODAY, local_only=True)
check('本机 index.html 缺失 → STALE_GENERATE', d['verdict'] == W.VERDICT_STALE_GENERATE)

print('===== ⑤ 退出码映射 =====')
check('FRESH=0', W.EXIT[W.VERDICT_FRESH] == 0)
check('LOCAL_OK=0', W.EXIT[W.VERDICT_LOCAL_OK] == 0)
check('STALE_DEPLOY=1', W.EXIT[W.VERDICT_STALE_DEPLOY] == 1)
check('STALE_GENERATE=2', W.EXIT[W.VERDICT_STALE_GENERATE] == 2)
check('UNREACHABLE=3', W.EXIT[W.VERDICT_UNREACHABLE] == 3)
check('五个 verdict 都有退出码', len(W.EXIT) == 5)

print('===== ⑥ today_cn 格式 =====')
t = W.today_cn()
check('返回 YYYY-MM-DD', len(t) == 10 and t[4] == '-' and t[7] == '-', t)

print('===== ⑦ 源码守卫（防回退）=====')
src = open(os.path.join(BASE, 'watchdog.py'), encoding='utf-8').read()
check('用直连 opener（ProxyHandler({}))', 'build_opener(urllib.request.ProxyHandler({}))' in src)
check('无裸 urllib.request.urlopen( 调用（会走死代理）', 'urllib.request.urlopen(' not in src)
check('线上 URL 常量存在', 'pliucugb-cyber.github.io/mining-daily' in src)
check('徽标正则存在', 'date-badge' in src)
check('四个 verdict 常量齐备', all(s in src for s in (
    'FRESH', 'STALE_DEPLOY', 'STALE_GENERATE', 'UNREACHABLE', 'LOCAL_OK')))
check('alert 用 Windows Notify 音（SoundPlayer，非 beep）',
      'Windows Notify.wav' in src and 'SoundPlayer' in src)
check('fetch 有硬墙钟保护（daemon 线程 + TimeoutError）',
      'threading.Thread' in src and 'daemon=True' in src and '硬墙钟' in src)
check('支持 --local-only（OS 计划任务不联网路径）', "'--local-only'" in src)
check('alert 支持 --skip-if-locked（避免活动中误报）', "'--skip-if-locked'" in src)

print('\n===== 汇总 =====')
print('  通过 %d / 失败 %d' % (pass_n, fail_n))
sys.exit(1 if fail_n else 0)
