# -*- coding: utf-8 -*-
"""
preflight_check.py — 矿业资讯速览自动化前置/回归健康检查。

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
  8. 站点标题（浏览器标签页）必须是「矿业资讯速览 · YYYY-MM-DD」，且日期与 build-version 同日
     （例外：午夜后补丁 —— 见 check_site_title 内的注释，仅放行 build 时间 < 01:00 的 +1 天）
     ——2026-09-12 用户反馈「标签页只有一个光秃秃的日期」后固化。09-07 起生成脚本把
     <title> 从「矿业新闻日报 2026-09-04」写成了纯日期，站名丢失且无人察觉。
     约定见 REFERENCE.md §39；deploy_pages.sync_site_title() 是同一约定的自愈兜底。

  9. 百度统计站点 ID 必须与 tongji 后台「代码获取」给出的 32 位 ID 逐字一致
     ——2026-09-14 事故：页面装的是另一站点条目的 ID，后台「代码安装错误」且数据恒 0；
     可站内一切正常（hm.js 200 / 信标 200 均真机实测通过），    极难自查。约定见 REFERENCE.md §42.8。

  10. 公司模块 v11 重建指纹（§42.19 回退指纹㉓㉔㉕）：index.html 内联 <style> 的
      v11 CSS 必留指纹（标题三级层级 / 折叠机制 / 已读态覆盖）+ app.js 折叠逻辑与
      文案精简红线（禁「按市值/知名度」「家有内容」「（最新动态）」）。把"被动保护"
      升级为"主动断言"，06:00 重建后 / 08:00 复验前自动跑（见 check_company_v11）。

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
import datetime
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
SITE_NAME = '矿业资讯速览'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
# 百度统计站点 ID（tongji.baidu.com → 使用设置 → 网站列表 → 代码获取）。
# 2026-09-14 事故：页面里装的是另一站点条目的 ID，导致后台「代码安装错误」+ 恒 0 数据。
# 换 ID 必须同步改：index.html 埋点、本常量、test_smoke_0908.js 断言（三处）。
BAIDU_SITE_ID = 'd28d60ab8b38f6641816d109448723ff'

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


def check_no_footer_install_entry(text):
    """页脚不得再出现「💻 添加到桌面 / 📱 安装到主屏幕」入口（2026-09-13 三期按用户要求删除）。

    背景：该文字链指向 #installGuideSection，与电脑端右上角 #pwaHeaderBtn、手机端底部
    浮条 #mobileInstallBar、「我的」面板 #mineInstallCard 重复，用户判定无意义（见 §42.7）。
    **删的是「页脚入口」**——指引区容器、@media 隐藏规则、data-view=install 视图分支
    与 switchView 映射全部保留，默认视图下该区块本就静态可见。

    注意：本检查只喂 index.html（`html_text`）——app.js 里的「添加到桌面 / 添加到主屏幕」
    是安装引导正文与对照表的合法文案，与页脚入口无关，不得一并拦。
    """
    findings = []
    hits = []
    if FOOTER_INSTALL_NODE_ID in text:
        hits.append('节点 %s' % FOOTER_INSTALL_NODE_ID)
    if FOOTER_INSTALL_PHRASE in text:
        hits.append('文案「%s」' % FOOTER_INSTALL_PHRASE)
    if hits:
        findings.append('❌ 页脚安装入口回归：%s — 2026-09-13 已按用户要求删除（见 REFERENCE.md §42.7），不得加回'
                        % ' / '.join(hits))
    else:
        findings.append('✅ 页脚安装入口未回归（「💻 添加到桌面 / 📱 安装到主屏幕」已删除）')
    return not hits, findings


def check_digest_badge_wording(text):
    """要闻区徽标文案须为「本期」，不得回退为「今日」（2026-09-14，见 §42.8）。

    背景：该条由 renderDigest 渲染，取数是「当日发布优先 → 今日收录补齐 → 全库最新」
    （app.js computeDigestPicks），跨日；区块内非当日条目本就由 .digest-dtag 标着日期
    —— 曾同时出现「今日」徽标与「09-06」条目，自相矛盾。用户 2026-09-14 判定改为「本期」。

    注意：只喂 index.html（html_text）；app.js 侧注释已同步改名，不在此拦。
    """
    findings = []
    m = re.search(r'<span class="digest-badge"[^>]*>([^<]*)</span>', text)
    if not m:
        findings.append('❌ 找不到 .digest-badge 徽标（要闻区标题结构被改动，见 REFERENCE.md §42.8）')
        return False, findings
    word = m.group(1).strip()
    if word == DIGEST_BADGE_BAD:
        findings.append('❌ 要闻徽标回退为「%s」——2026-09-14 已按用户要求改为「%s」（见 §42.8）'
                        % (DIGEST_BADGE_BAD, DIGEST_BADGE_OK))
        return False, findings
    if word != DIGEST_BADGE_OK:
        findings.append('❌ 要闻徽标为「%s」，契约值应为「%s」（见 §42.8）' % (word, DIGEST_BADGE_OK))
        return False, findings
    findings.append('✅ 要闻徽标文案正确（「%s」，非「%s」）' % (DIGEST_BADGE_OK, DIGEST_BADGE_BAD))
    return True, findings


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


# 价格单位去重契约（2026-09-13）：分组标题已声明单位，同单位卡片不重复写。
# 见 REFERENCE.md §42.11。生成侧由 generate_common.unit_class() 产出该 class。
# 页脚安装入口契约（2026-09-13 三期按用户要求删除）——见 REFERENCE.md §42.7。
# 只对 index.html 生效；app.js 里同名文案属安装引导正文，不得一并拦。
FOOTER_INSTALL_NODE_ID = 'CbHPZGigo3bSeq2LYmfY5V'
FOOTER_INSTALL_PHRASE = '添加到桌面 / \U0001f4f1 安装到主屏幕'
# 要闻区标题契约（2026-09-14 按用户要求改定）——见 REFERENCE.md §42.8。
# 徽标须为「本期」：日报每日 06:00 收「前一天」新闻，且要闻池含跨日补齐条目，
# 「今日」在事实上错（区块内非当日条目本就由 .digest-dtag 标着日期），
# 又与侧栏「今日新增」（实时未读口径）撞车。只对 index.html 生效。
DIGEST_BADGE_OK = '本期'
DIGEST_BADGE_BAD = '今日'

SAME_UNIT_CLASS = 'pc-unit-same'
SHFE_SAME_UNIT_N = 8      # 国内盘 元/吨：沪铜铝铅锌锡镍 + 碳酸锂 + 电解钴
LME_SAME_UNIT_N = 6       # LME 全部 6 个 = 美元/吨
# 与分组单位不同的品种必须保留可见单位，否则会被误读成 /吨
KEEP_UNIT_SNIPPETS = [
    '<div class="pc-unit">元/克</div>',      # 上海金 Au99.99
    '<div class="pc-unit">元/千克</div>',    # 白银 Ag(T+D)
]


def check_price_unit_dedup(text):
    """价格区单位去重契约：同单位隐藏、异单位保留、标题声明单位。

    背景：用户反馈「分组标题已写人民币/吨、美元/吨，每行再写一遍单位是重复」。
    防漂移：生成脚本若被改回不输出 class，或把异单位也隐藏，这里拦住。
    """
    findings = []
    ok = True

    n_shfe = text.count(f'<div class="pc-unit {SAME_UNIT_CLASS}">元/吨</div>')
    n_lme = text.count(f'<div class="pc-unit {SAME_UNIT_CLASS}">美元/吨</div>')
    if n_shfe == SHFE_SAME_UNIT_N and n_lme == LME_SAME_UNIT_N:
        findings.append(f'✅ 同单位已去重（国内 {n_shfe} + LME {n_lme} 张卡隐藏重复单位）')
    else:
        findings.append(
            f'❌ 同单位去重数量异常：国内 {n_shfe}/{SHFE_SAME_UNIT_N}、LME {n_lme}/{LME_SAME_UNIT_N}'
            f' — 生成脚本可能被改回输出裸 pc-unit（契约见 REFERENCE.md §42.11）')
        ok = False

    kept_missing = [s for s in KEEP_UNIT_SNIPPETS if s not in text]
    if kept_missing:
        findings.append(f'❌ 异单位被误隐藏或改写：{kept_missing} — 上海金/白银单位必须可见（否则被误读成 /吨）')
        ok = False
    else:
        findings.append('✅ 异单位保留可见（元/克、元/千克）')

    if "content:'国内盘 · 人民币/吨'" in text:
        findings.append('✅ 国内盘分组标题已声明单位（人民币/吨）')
    else:
        findings.append("❌ 国内盘分组标题未声明单位（应含 content:'国内盘 · 人民币/吨'）")
        ok = False

    return ok, findings



def check_company_v11(html_text, app_text):
    """矿业公司模块 v11 重建指纹闸门（REFERENCE.md §42.19 v11 / 回退指纹㉓㉔㉕）。

    背景（优化清单 A3 / 用户待办③）：v11 的抗重建原本只靠「生成脚本不碰
    `#companySection` 内联 <style>」的**被动保护**——一旦 generate_*.py 改成整段
    重建、或误改内联样式，v11 会在次日 06:00 静默回退，08:00 复验前用户已看到坏版。
    这里把 v11 必留指纹做成**主动断言**，每次 preflight（06:00 重建后 / 08:00 复验前）
    都跑，把"被动保护"升级为"主动锁死"。

    扫两块（与契约边界对齐）：
      html_text —— index.html #companySection 内联 <style>（重建边界真身）
      app_text  —— app.js（运行时文案 / 折叠逻辑源；不扫整文件，因为 index.html
                  内联样式的**历史注释**里本就含「按市值·知名度排序」等字样，
                  整文件禁语会误红——文案红线只针对渲染源 app.js）
    """
    findings = []
    ok = True

    # —— ① 重建边界：index.html 内联 <style> 的 v11 CSS 指纹（缺任一即回退＝㉓）——
    CSS_FINGERPRINTS = [
        ('.co-title{font-size:calc(var(--fs-body) + 2px);color:var(--ink-900);',
         '条目标题三级层级（近黑 --ink-900 + calc(+2px)，v11①）'),
        ('calc(var(--fs-body) - 1px)',
         '正文/摘要最浅档字号（co-summary/co-body 共用，v11①）'),
        ('calc(var(--fs-body) + 3px)',
         '.co-feed-name 修正（避免与条目标题倒挂，v11③）'),
        ('.co-nav-g-body[hidden]{display:none}',
         '右栏分组折叠机制（组头 <button> + 组内 [hidden]，v11②）'),
        ('.co-item.read .co-summary,.co-item.read .co-body{color:var(--ink-400)}',
         '已读态摘要降档（防与未读倒挂，v11①）'),
        ('body.dark .co-item.read .co-summary,body.dark .co-item.read .co-body{color:var(--ink-300)}',
         '暗色已读态覆盖（v11①，第162条断言锁死）'),
    ]
    for snippet, desc in CSS_FINGERPRINTS:
        if snippet in html_text:
            findings.append('✅ %s' % desc)
        else:
            findings.append('❌ 缺失 %s — #companySection 内联样式可能被重建脚本改写（§42.19 v11㉓）' % desc)
            ok = False

    # —— ② 运行时源：app.js 折叠逻辑 + button 形态（缺任一即回退＝㉔）——
    RUNTIME_MARKERS = [
        ('class="co-nav-g-h"', '组头为可点 <button>（非旧 div 装饰，v11②）'),
        ('function toggleCoGroup', 'toggleCoGroup 折叠/展开句柄（仅隐藏不移除，v11②）'),
        ('md_co_groups', '折叠状态持久化 localStorage 键（v11②）'),
    ]
    for marker, desc in RUNTIME_MARKERS:
        if marker in app_text:
            findings.append('✅ %s' % desc)
        else:
            findings.append('❌ 缺失 %s — 折叠逻辑回退（§42.19 v11㉔）' % desc)
            ok = False

    # —— ③ 文案精简红线：app.js 渲染源不得出现旧冗余文案（出现即回退＝㉕）——
    FORBIDDEN = [
        ('按市值', '组头「按市值/知名度」排名标注（v11② 已删）'),
        ('知名度', '组头排名标注（v11② 已删）'),
        ('家有内容', 'coNavH 旧「…家有内容 · …」（v11② 已删）'),
        ('（最新动态）', '「全部公司（最新动态）」旧文案（v11② 已改「全部公司」）'),
    ]
    for bad, desc in FORBIDDEN:
        if bad in app_text:
            findings.append('❌ 出现 %s — 文案精简红线被打破（§42.19 v11㉕）' % desc)
            ok = False
        else:
            findings.append('✅ 无 %s' % desc)
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


def check_baidu_stat_id(text):
    """百度统计站点 ID 必须与 tongji 后台「代码获取」给出的 ID 逐字一致。

    2026-09-14 定因：页面里装的是 89ca069c…（另一个站点条目的 ID），而本账号
    下 pliucugb-cyber.github.io 的 ID 是 7d2d850a… —— tongji 后台「首页代码状态」
    显示「代码安装错误」、实时访客恒为 0，可页面侧一切正常（hm.js 200、信标
    hm.gif 200 均已真机实测通过）。正是百度官方排障文档所说的「装错了代码」。
    这里做成硬闸门，防止再次写错 ID 而无人察觉。

    只扫 index.html（app.js 内没有埋点）。
    """
    findings = []
    m = re.search(r'hm\.baidu\.com/hm\.js\?([0-9a-f]{32})', text)
    if not m:
        findings.append('❌ 找不到百度统计代码（hm.baidu.com/hm.js?<32位ID>）'
                        '——页脚计数已迁百度统计，缺失即等于无法计量访问')
        return False, findings
    got = m.group(1)
    if got != BAIDU_SITE_ID:
        findings.append('❌ 百度统计 ID 不符：页面=%s 后台应为=%s'
                        '（装错代码 ⇒ 后台恒 0 数据 + 显示「代码安装错误」，'
                        '见 REFERENCE.md §42.8）' % (got, BAIDU_SITE_ID))
        return False, findings
    findings.append('✅ 百度统计 ID 正常：%s' % got)
    return True, findings


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
    """站点标题（浏览器标签页）必须是「矿业资讯速览 · YYYY-MM-DD」，且日期与 build-version 同日。

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
            # 跨午夜补丁（2026-09-13 00:3x 首次需要）：站点标题日期 = **日报内容的日期**，
            #   而 build-version = **构建时刻**。午夜之后打补丁时，二者必然差 1 天。
            #   只放行「build 比标题晚 1 天 **且 build 时间在 00:00–00:59**」这一种情形：
            #   06:00 生成侧若漏改标题（标题=昨天、build=今天 06:xx），时间部分 > 01:00 → 仍被拦，
            #   这条守卫防的「标题退回纯日期 / 漏改标题」依然有效。
            mh = re.search(r'<meta name="build-version" content="(\d{8})-(\d{2})(\d{2})"', text)
            midnight_patch = False
            if mh:
                try:
                    t = datetime.date(int(m2.group(1)[:4]), int(m2.group(1)[5:7]), int(m2.group(1)[8:10]))
                    b = datetime.date(int(mh.group(1)[:4]), int(mh.group(1)[4:6]), int(mh.group(1)[6:8]))
                    midnight_patch = ((b - t).days == 1) and int(mh.group(2)) < 1
                except ValueError:
                    midnight_patch = False
            if midnight_patch:
                findings.append('✅ 标题日期 %s，build %s-…（午夜后补丁，允许差 1 天）'
                                % (m2.group(1), mb.group(1)))
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
    # 单独保留 app.js 原文，供 check_company_v11 做"文案精简红线"扫描——
    # 不混入 index.html（其内联样式历史注释含「按市值·知名度」字样，整文件禁语会误红）
    app_text = app_js.read_text(encoding='utf-8') if app_js.exists() else ''

    sections = [
        ('生成 marker', check_markers(text)),
        ('已删功能守护', check_no_marketpulse(text)),
        ('已删入口守护', check_no_footer_install_entry(html_text)),
        ('要闻文案守护', check_digest_badge_wording(html_text)),   # 只扫 index.html
        ('关键功能', check_functions(text)),
        ('关键容器', check_containers(text)),
        ('价格单位去重', check_price_unit_dedup(html_text)),   # 只扫 index.html，避免 app.js 干扰计数
        ('公司模块 v11 指纹', check_company_v11(html_text, app_text)),   # §42.19 v11 重建边界 + 折叠逻辑 + 文案红线
        ('build-version', check_build_version(text)),
        ('站点标题', check_site_title(html_text)),
        ('百度统计 ID', check_baidu_stat_id(html_text)),
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
