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
  7. sw.js 可解析（node --check）且 CACHE_NAME 与 build-version 一致
     ——2026-09-10 事故新增。此前没有任何门禁真正解析过 sw.js，一行语法错误
     （`const P260910-1900';`）直接上线，导致 SW 无法更新、页面区块永久停在「加载中…」。
  8. 站点标题（浏览器标签页）必须是「矿业新闻日报 · YYYY-MM-DD」，且日期与 build-version 同日
     ——2026-09-12 用户反馈「标签页只有一个光秃秃的日期」后固化。09-07 起生成脚本把
     <title> 从「矿业新闻日报 2026-09-04」写成了纯日期，站名丢失且无人察觉。
     约定见 REFERENCE.md §39；deploy_pages.sync_site_title() 是同一约定的自愈兜底。

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
import shutil
import subprocess
import sys
import time
from pathlib import Path

from logutil import get_logger

log = get_logger('preflight')

ROOT = Path(__file__).parent
HTML = ROOT / 'index.html'
SITE_NAME = '矿业新闻日报'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
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


def _find_node():
    """定位 node 可执行文件（供 sw.js 语法校验）。找不到返回 None。"""
    cand = shutil.which('node')
    if cand:
        return cand
    base = Path.home() / '.workbuddy' / 'binaries' / 'node' / 'versions'
    if base.exists():
        hits = sorted(list(base.glob('*/node.exe')) + list(base.glob('*/bin/node')))
        if hits:
            return str(hits[-1])
    return None


def check_sw_js(text):
    """sw.js 语法校验 + CACHE_NAME 与 build-version 一致性（2026-09-10 事故新增）。

    事故复盘：sw.js 第 10 行被写坏成 `const P260910-1900';`（语法错误）后原样上线
    → SW 永远无法更新 → 用户卡在旧的/不完整的缓存 → 页面区块一直停在「加载中…」。
    此前没有任何门禁真正解析过 sw.js（唯一相关测试只把 sw.js 当字符串做正则）。
    """
    findings = []
    sw = ROOT / 'sw.js'
    if not sw.exists():
        return False, ['❌ 找不到 sw.js']
    src = sw.read_text(encoding='utf-8')
    m = re.search(r"const\s+CACHE_NAME\s*=\s*'([^']*)'", src)
    if not m:
        findings.append("❌ sw.js 缺少合法的 CACHE_NAME 声明"
                        "（应形如 const CACHE_NAME = 'mining-daily-<build-version>';）")
    else:
        cname = m.group(1)
        bv = None
        if HTML.exists():
            mb = re.search(r'<meta name="build-version" content="([^"]+)"',
                           HTML.read_text(encoding='utf-8'))
            if mb:
                bv = re.sub(r'[^0-9A-Za-z._-]', '-', mb.group(1).strip())
        if bv and cname != 'mining-daily-' + bv:
            findings.append('❌ sw.js CACHE_NAME=%r 与 build-version 派生值 %r 不一致'
                            % (cname, 'mining-daily-' + bv))
        else:
            findings.append('✅ sw.js CACHE_NAME 与 build-version 一致：%s' % cname)
    node = _find_node()
    if node:
        p = subprocess.run([node, '--check', str(sw)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if p.returncode != 0:
            err = p.stdout.decode('utf-8', errors='replace').strip().splitlines()[:3]
            findings.append('❌ sw.js 语法错误（node --check）：' + ' | '.join(err))
        else:
            findings.append('✅ sw.js 语法校验通过（node --check）')
    else:
        findings.append('⚠️ 未找到 node，跳过 sw.js 语法校验（仅校验 CACHE_NAME 形状）')
    ok = not any(f.startswith('❌') for f in findings)
    return ok, findings


def check_site_title(text):
    """站点标题（浏览器标签页）必须是「矿业新闻日报 · YYYY-MM-DD」，且日期与 build-version 同日。

    2026-09-12 用户反馈后固化：标签页上只剩一个光秃秃的日期，看不出是什么站。
    根因是 09-07 的生成脚本把 <title> 从「矿业新闻日报 2026-09-04」改成了纯日期
    （见 REFERENCE.md §39）。这里把它做成前置闸门——标题一旦漂移（丢站名 / 格式变 /
    日期与 build-version 不同日），06:00 前置检查即报错，不会再无声退回纯日期。

    注意：只对 index.html 原始文本做检查（不喂 app.js——它的图表模板里也有 <title> 字面量）。
    """
    findings = []
    m = re.search(r'<title>([^<]*)</title>', text)
    if not m:
        findings.append('❌ 找不到 <title>')
        return False, findings
    title = m.group(1).strip()
    m2 = re.match(r'^%s · (\d{4}-\d{2}-\d{2})$' % SITE_NAME, title)
    if not m2:
        findings.append('❌ 站点标题格式不符：%r（应为「%s · YYYY-MM-DD」——'
                        '只剩纯日期即为 09-07 的回退，站名丢失，见 REFERENCE.md §39）'
                        % (title, SITE_NAME))
        return False, findings
    findings.append('✅ 站点标题正常：%s' % title)
    mb = re.search(r'<meta name="build-version" content="(\d{8})-\d{4}"', text)
    if mb:
        if m2.group(1).replace('-', '') == mb.group(1):
            findings.append('✅ 标题日期与 build-version 同日（%s）' % m2.group(1))
        else:
            findings.append('❌ 标题日期 %s 与 build-version %s 不同日——生成时漏改标题'
                            % (m2.group(1), mb.group(1)))
            return False, findings
    return True, findings


def main():
    argv = set(sys.argv[1:])    # --fail-on-error 是 06:00 自动化在用的历史参数，现为默认行为（no-op，仅兼容保留）
    fail = '--no-fail' not in argv

    if not HTML.exists():
        log.error('找不到 %s', HTML)
        sys.exit(1)
    text = HTML.read_text(encoding='utf-8')
    html_text = text          # ⚠️ div 收支只对 index.html 有意义，见下方 2026-09-11 说明
    # 2026-09-10 性能优化：应用逻辑已外置为 app.js(defer)，关键功能函数（setupNewsFilterBar /
    # exportPriceCsv / renderRightsSection / bindRights / _clearHtmlCache 等）现位于 app.js。
    # 一并纳入静态扫描，避免误报「关键功能缺失」导致自动化闸门误杀合法部署。
    #
    # ⚠️ 2026-09-11 修复：拼接出的 text 只可喂给「按名字找函数/容器/marker」这类检查，
    # **绝不能喂给 check_div_balance**。app.js 是 JS 不是 HTML：它的模板字符串可以只写半个
    # 标签（另一半在别处拼），注释/字符串里也随时可能出现字面 `<div>`——而 check_div_balance
    # 只剔除 index.html 内的 <script>/<style> 块，对「拼进来的 app.js」毫无防护，
    # 于是 app.js 里任何一处不成对的 `<div>` 都会让闸门误红。
    # 事故：2026-09-11 一处 JS 注释写了字面 `<div>` → div 收支误报「有 1 个 <div> 未闭合」
    # → preflight exit 1 → 06:00 自动化会据此判定 index.html 脏状态并 `checkout -- index.html` 后中止。
    app_js = ROOT / 'app.js'
    if app_js.exists():
        text = text + '\n' + app_js.read_text(encoding='utf-8')

    sections = [
        ('生成 marker', check_markers(text)),
        ('已删功能守护', check_no_marketpulse(text)),
        ('关键功能', check_functions(text)),
        ('关键容器', check_containers(text)),
        ('build-version', check_build_version(text)),
        ('站点标题', check_site_title(html_text)),
        ('sw.js 语法', check_sw_js(text)),
        ('div 收支', check_div_balance(html_text)),
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
