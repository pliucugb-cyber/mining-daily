# -*- coding: utf-8 -*-
"""
preflight_check.py — 矿业日报自动化前置/回归健康检查。

目的：把散落在 automation prompt 里的"页面规范检查"收敛到代码，
防止再次出现「prompt 与页面代码脱节 → 自动化把页面往旧规范拉 → 卡死」的问题。

检查项（全部静态，针对与脚本同目录的 index.html）：
  1. 三个生成 marker（今日新增 / 往期内容 / 详细安装指引）各恰好 1 次
  2. 市场脉搏条（已删除功能）不得残留
  3. 关键功能函数/标识必须存在（搜索/CSV/PDF/防横跳/矿权专区）
  4. 价格区两行容器、矿权专区容器存在
  5. 排除 <script>/<style> 后的 <div> 收支平衡
  6. build-version meta 存在

退出码（2026-09 改）：
  **默认** 任一检查失败 → exit 1。旧行为是「默认只报告、exit 0」，
  失败也返回 0 会让自动化「看起来通过」，属于静默失败，已修正。
  --no-fail     只报告不中断（人工排查时用）
  --fail-on-error  保留为 no-op 兼容参数：06:00 自动化 prompt 里写死了这个
                 参数，删掉会让它拿到非预期退出码。它现在是默认行为，
                 传不传都一样，请勿移除该参数名。

写入 .preflight_status.json（供自动化读取；注意：该文件不应被 git 提交，
加进 deploy_pages 的 git-add 排除名单）。
"""
import json
import re
import sys
import time
from pathlib import Path

from logutil import get_logger

log = get_logger('preflight')

ROOT = Path(__file__).parent
HTML = ROOT / 'index.html'
STATUS = ROOT / '.preflight_status.json'


def check_markers(text):
    """三个 gen_today.py marker 各恰好 1 次。"""
    findings = []
    markers = {
        '今日新增': '<!-- ==================== 今日新增',
        '往期内容': '<!-- ==================== 往期内容',
        '详细安装指引': '<!-- ==================== 详细安装指引',
    }
    for label, prefix in markers.items():
        cnt = text.count(prefix)
        if cnt == 0:
            findings.append(f'❌ 缺失生成 marker：{label}（{prefix}...）— gen_today.py 将因 pos<0 退出')
        elif cnt > 1:
            findings.append(f'❌ 生成 marker 重复 {cnt} 次：{label} — 工作树脏（自动化多轮注入），需 git checkout 还原')
        else:
            findings.append(f'✅ 生成 marker 正常：{label}（1 次）')
    ok = not any(f.startswith('❌') for f in findings)
    return ok, findings


def check_no_marketpulse(text):
    findings = []
    bad = ['#marketPulse', 'renderMarketPulse', 'market-pulse', 'marketPulseRow', '.mp-']
    hits = [b for b in bad if b in text]
    if hits:
        findings.append(f'❌ 市场脉搏条（已删除功能）残留：{hits} — 自动化回退，需清除')
    else:
        findings.append('✅ 市场脉搏条无残留（已删除功能未回归）')
    ok = not hits
    return ok, findings


def check_functions(text):
    findings = []
    required = [
        'function setupNewsFilterBar',
        'function exportPriceCsv',
        'function exportRightsCsv',
        'function downloadCsv',
        'function exportPdf',
        'function renderRightsSection',
        'function bindRights',
        'clients.navigate',
        '_clearHtmlCache',
    ]
    missing = [f for f in required if f not in text]
    if missing:
        findings.append(f'❌ 关键功能缺失：{missing} — 自动化可能破坏了现有功能')
    else:
        findings.append('✅ 关键功能均在（搜索/CSV/PDF/防横跳/矿权专区）')
    ok = not missing
    return ok, findings


def check_containers(text):
    findings = []
    containers = {
        'priceCardsShfe（国内价格行）': 'id="priceCardsShfe"',
        'priceCardsLme（LME 价格行）': 'id="priceCardsLme"',
        'rightsSection（矿权专区）': 'id="rightsSection"',
    }
    miss = [k for k, v in containers.items() if v not in text]
    if miss:
        findings.append(f'❌ 关键容器缺失：{miss}')
    else:
        findings.append('✅ 价格区两行 + 矿权专区容器均在')
    ok = not miss
    return ok, findings


def check_build_version(text):
    findings = []
    m = re.search(r'name="build-version"\s+content="([^"]+)"', text)
    if m:
        findings.append(f'✅ build-version 存在（{m.group(1)}）')
        ok = True
    else:
        findings.append('❌ 缺失 <meta name="build-version"> — 改页面必须 bump 版本戳')
        ok = False
    return ok, findings


def check_div_balance(text):
    """排除 <script>/<style> 块后，检查 div 收支平衡（栈法）。"""
    findings = []
    cleaned = re.sub(r'<script\b[^>]*>.*?</script>', '', text, flags=re.S)
    cleaned = re.sub(r'<style\b[^>]*>.*?</style>', '', cleaned, flags=re.S)
    stack = []
    problems = []
    for m in re.finditer(r'<div\b[^>]*>|</div>', cleaned):
        tag = m.group(0)
        if tag == '</div>':
            if stack:
                stack.pop()
            else:
                problems.append('出现多余的 </div>（无对应开标签）')
        else:
            stack.append(1)
    if stack:
        problems.append(f'有 {len(stack)} 个 <div> 未闭合')
    if problems:
        findings.append(f'❌ div 收支不平衡：{problems}')
        ok = False
    else:
        findings.append('✅ div 收支平衡（排除 script/style 后）')
        ok = True
    return ok, findings


def main():
    argv = set(sys.argv[1:])
    # --fail-on-error 是 06:00 自动化在用的历史参数，现为默认行为（no-op，仅兼容保留）
    fail = '--no-fail' not in argv

    if not HTML.exists():
        log.error('找不到 %s', HTML)
        sys.exit(1)
    text = HTML.read_text(encoding='utf-8')

    sections = [
        ('生成 marker', check_markers(text)),
        ('已删功能守护', check_no_marketpulse(text)),
        ('关键功能', check_functions(text)),
        ('关键容器', check_containers(text)),
        ('build-version', check_build_version(text)),
        ('div 收支', check_div_balance(text)),
    ]

    all_ok = True
    rule = '=' * 60
    log.info(rule)
    log.info('preflight_check — %s', HTML)
    log.info(rule)
    for name, (ok, findings) in sections:
        log.info('[%s]', name)
        for f in findings:
            log.info('  %s', f)
        if not ok:
            all_ok = False

    log.info(rule)
    if all_ok:
        log.info('✅ 全部通过')
    else:
        log.error('❌ 存在异常，自动化应中止并告警')
    log.info(rule)

    STATUS.write_text(json.dumps({
        'ok': all_ok,
        'checks': {n: ok for n, (ok, _) in sections},
        'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
    }, ensure_ascii=False, indent=2), encoding='utf-8')

    if not all_ok:
        if fail:
            sys.exit(1)
        log.warning('已指定 --no-fail，仅报告不中断（exit 0）')


if __name__ == '__main__':
    main()
