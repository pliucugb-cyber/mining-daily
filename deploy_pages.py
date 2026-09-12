#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy_pages.py —— 把矿业日报的静态站点同步到 GitHub Pages（gh-pages 分支）

背景
----
WorkBuddy 的「发布为应用」链接绑定的是**本机目录绝对路径**，换一台电脑（路径变了）
就会生成新链接，同事手里的地址失效。GitHub Pages 的地址只跟「账号 + 仓库名」有关，
与在哪台电脑发布无关，因此作为对外长期地址。

本脚本把站点必需的静态文件复制到一个独立工作副本（tmp/ghpages，其 .git 指向 gh-pages
分支），提交并推送。GitHub 侧把 Pages 的 Source 设为 gh-pages 分支后，push 即自动生效。

用法
----
    python deploy_pages.py            # 有变更才提交推送；无变更直接退出
    python deploy_pages.py --force    # 无变更也强制推一次（用于首次建站/排障）

说明
----
- 部署前会按 build-version 自动派生两个值：sw.js 的 CACHE_NAME、index.html 的
  <title>（「矿业新闻日报 · YYYY-MM-DD」，约定见 REFERENCE.md §39）；
- 只包含前端真正用到的文件（页面、数据 js、图标、manifest、sw），
  不含 Python 脚本、data/ 抓取缓存、__pycache__ 等。
- 遵循「未编造、可溯源」：只搬运已有文件，不生成任何内容。
"""
import os
import re
import io
import sys
import time
import shlex
import shutil
import hashlib
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from logutil import get_logger  # noqa: E402

_log = get_logger('deploy')


def log(msg):
    """立即输出——自动化场景下输出常被管道缓冲，卡住时看不到进度。

    改走 logutil 统一格式（时间戳 + 级别 + 模块名），排查时能直接看出卡在哪一步。
    StreamHandler 每次 emit 都会 flush，与原来的 print(flush=True) 等效。
    msg 里若含 % 也不会被误格式化：logging 只在传 args 时才做 % 替换。
    """
    _log.info(msg)
SITE_NAME = '矿业新闻日报'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
WORK = os.path.join(ROOT, 'tmp', 'ghpages')
REMOTE = 'git@github.com:pliucugb-cyber/mining-daily.git'
BRANCH = 'gh-pages'

# 站点必需文件（缺一不可；缺失会直接报错终止，避免推一个坏站点上去）
REQUIRED = [
    'index.html',
    'app.js',
    'news-data.js',
    'lme-data.js',
    'price-history.js',
    'sw.js',
    'manifest.json',
    'icon-192.png',
    'icon-512.png',
    'icon-192-maskable.png',
    'icon-512-maskable.png',
]

# 可选附带（供后续前端化 / 排查用，缺失不报错）
OPTIONAL = [
    'mining_news.json',
    'price_history_detail.json',
    'price_history.json',
    'lme_data.json',
    'morning_report.json',
    'alerts.json',
    'knowledge.json',
    'mobile-preview.html',   # 手机调试预览页（2026-09-07 曾被白名单漏掉导致线上 404）
]


def run(cmd, cwd=None, check=True):
    """执行命令，返回 (returncode, stdout+stderr)。

    2026-09-10 P1（第 2 批）：去掉 shell=True。
    原实现把整条命令交给 shell 解析，参数里的空格/引号/特殊字符需要二次转义，
    一旦某天把分支名或提交信息拼进去就容易出错或被注入；改为 argv 数组直传更安全，
    且 Windows / Linux 行为一致。cmd 既可传字符串（内部 shlex.split），也可直接传列表。
    """
    # 定时任务里跑 git 时严禁任何交互式等待：否则一个 rebase/编辑器提示就能把整轮流程挂死
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GIT_EDITOR'] = 'true'
    env['GIT_SEQUENCE_EDITOR'] = 'true'
    env['GIT_MERGE_AUTOEDIT'] = 'no'
    args = list(cmd) if isinstance(cmd, (list, tuple)) else shlex.split(cmd)
    p = subprocess.run(args, cwd=cwd, shell=False, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode('utf-8', errors='replace')
    if check and p.returncode != 0:
        shown = cmd if isinstance(cmd, str) else ' '.join(cmd)
        raise RuntimeError('命令失败: %s\n%s' % (shown, out))
    return p.returncode, out


# 2026-09-11 新增：部署期给 4 个脚本标签打「内容指纹」。
#
# 背景（09-11 事故第三轮复盘的结论）：
#   GitHub Pages 对静态资源返回 Cache-Control: max-age=600，而 <script src="app.js">
#   这种固定 URL 会命中**浏览器 HTTP 缓存**；再叠加 SW 缓存，用户完全可能长期在跑
#   旧的 app.js，却已经拿到新的 index.html —— 「新页 + 旧逻辑」混装正是「区块停在
#   加载中」的经典成因（旧 app.js 没有本轮的自愈逻辑，页面自己救不回来）。
#
# 做法：对每个脚本按文件内容取 md5 前 8 位，改写成 app.js?v=<hash>。
#   内容不变 → URL 不变（不影响缓存收益）；内容一变 → URL 就变，浏览器与 SW
#   都只能去网络取新版，混装状态在机制上不可能出现。
#
# 注意：只改工作副本 tmp/ghpages 里的 index.html，**不动源文件**——
#   本地开发与 jsdom 测试仍用无后缀 URL（各测试用 `src="app.js"[^>]*` 匹配，两者都兼容）。
#   sw.js 的注册 URL 仍必须是 './sw.js'，绝不可加指纹（加了会导致 SW 反复重装）。
BUST_FILES = ['app.js', 'news-data.js', 'lme-data.js', 'price-history.js']


def bust_asset_versions():
    """把工作副本 index.html 里的脚本引用改写为带内容指纹的 URL。"""
    idx = os.path.join(WORK, 'index.html')
    if not os.path.isfile(idx):
        raise RuntimeError('工作副本缺少 index.html，无法打脚本指纹')
    with io.open(idx, encoding='utf-8', newline='') as f:
        src = f.read()
    out = src
    marks = []
    for name in BUST_FILES:
        p = os.path.join(ROOT, name)
        if not os.path.isfile(p):
            raise RuntimeError('缺少 %s，无法打脚本指纹（拒绝部署）' % name)
        with open(p, 'rb') as f:
            h = hashlib.md5(f.read()).hexdigest()[:8]
        # 先吞掉可能残留的旧指纹，避免出现 app.js?v=aaa?v=bbb
        pat = re.compile(r'src="%s(\?v=[^"]*)?"' % re.escape(name))
        out, n = pat.subn(lambda _m, _n=name, _h=h: 'src="%s?v=%s"' % (_n, _h), out)
        if n == 0:
            raise RuntimeError('index.html 中找不到 src="%s"，指纹改写失败（拒绝部署）' % name)
        marks.append('%s?v=%s' % (name, h))
    if out != src:
        tmp = idx + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write(out)
        # 兜底：改写只应动 4 处 src，字节数变化很小；出入过大说明正则写坏了
        if abs(len(out) - len(src)) > 400 or len(out) < 1000:
            raise RuntimeError('index.html 指纹改写结果异常（%d → %d 字节），拒绝写入'
                               % (len(src), len(out)))
        os.replace(tmp, idx)
        log('[deploy_pages] 已打脚本指纹：%s' % '、'.join(marks))
    else:
        log('[deploy_pages] 脚本指纹已是最新：%s' % '、'.join(marks))
    return marks


def _node_exe():
    """定位 node 可执行文件（供 sw.js 语法校验用）。找不到返回 None。"""
    cand = shutil.which('node')
    if cand:
        return cand
    import glob as _glob
    for pat in (
        os.path.join(os.path.expanduser('~'), '.workbuddy', 'binaries', 'node',
                     'versions', '*', 'node.exe'),
        os.path.join(os.path.expanduser('~'), '.workbuddy', 'binaries', 'node',
                     'versions', '*', 'bin', 'node'),
    ):
        hits = sorted(_glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def validate_sw_js(required_version=None):
    """对 sw.js 做「CACHE_NAME 形状 + 语法」双重校验；不合格抛 RuntimeError（拒绝部署）。

    2026-09-10 事故根治点：sw.js 曾被写坏成 `const P260910-1900';`（语法错误）后
    被原样推上线 → SW 永远无法更新 → 用户卡在旧的/不完整的缓存里，页面区块一直
    停在「加载中…」。此前 pipeline 里没有任何一步会真正解析 sw.js，故加此闸门。
    """
    sw_path = os.path.join(ROOT, 'sw.js')
    with io.open(sw_path, encoding='utf-8') as f:
        src = f.read()
    m = re.search(r"const\s+CACHE_NAME\s*=\s*'([^']*)'", src)
    if not m:
        raise RuntimeError(
            "sw.js 缺少合法的 CACHE_NAME 声明（形如 const CACHE_NAME = 'mining-daily-<build-version>';）。"
            "这会让 SW 无法解析 → 用户卡在旧缓存、页面停在「加载中…」。请先修复 sw.js 再部署。")
    if required_version and m.group(1) != required_version:
        raise RuntimeError('sw.js CACHE_NAME=%r 与 build-version 派生值 %r 不一致，拒绝部署。'
                           % (m.group(1), required_version))
    node = _node_exe()
    if node:
        p = subprocess.run([node, '--check', sw_path],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if p.returncode != 0:
            raise RuntimeError('sw.js 语法校验失败（node --check）：\n'
                               + p.stdout.decode('utf-8', errors='replace'))
    else:
        log('[deploy_pages] ⚠️ 未找到 node，跳过 sw.js 语法校验（仅校验 CACHE_NAME 形状）')
    log('[deploy_pages] sw.js 校验通过（CACHE_NAME=%s）' % m.group(1))
    return m.group(1)


def sync_sw_cache_name():
    """2026-09-10 P1：SW 的 CACHE_NAME 由 index.html 的 build-version 自动派生。

    此前靠人手把 v78→v79 递增，漏改就会出现「页面更新了、SW 还拿着旧缓存」。
    build-version 已是事实上的版本源（改 index.html 必须 bump），直接拿它派生缓存名：
    版本变 → sw.js 字节变 → 浏览器重新安装 SW → activate 里清掉旧缓存。
    同一版本重复部署结果一致（幂等），不会造成无谓的全量重下。

    2026-09-10 事故修复：旧实现用 `const CACHE_NAME = '[^']*'` 精确匹配，一旦该行被写坏
    （变成 `const P260910-1900';`）就再也匹配不上 → `new == src` → 打印「已是最新」后
    **静默 return**，把语法错误的 sw.js 原样推上线。现在两道保险：
      ① 匹配不到 CACHE_NAME 声明 → 直接抛错终止部署（fail-fast，不再静默）；
      ② 改写前后一律走 validate_sw_js()（形状 + node --check 语法 + 版本一致）。
    """
    html_path = os.path.join(ROOT, 'index.html')
    sw_path = os.path.join(ROOT, 'sw.js')
    if not (os.path.isfile(html_path) and os.path.isfile(sw_path)):
        return
    with io.open(html_path, encoding='utf-8') as f:
        m = re.search(r'<meta name="build-version" content="([^"]+)"', f.read())
    if not m:
        raise RuntimeError('index.html 未找到 build-version，无法派生 SW 缓存名（拒绝部署）')
    bv = re.sub(r'[^0-9A-Za-z._-]', '-', m.group(1).strip())
    name = 'mining-daily-' + bv
    with io.open(sw_path, encoding='utf-8', newline='') as f:
        src = f.read()
    pat = re.compile(r"const\s+CACHE_NAME\s*=\s*'[^']*'")
    if not pat.search(src):
        raise RuntimeError(
            "sw.js 中找不到可改写的 `const CACHE_NAME = '...'` 声明。"
            "若该行已被写坏，请手工恢复为 const CACHE_NAME = '%s'; 后重试"
            "（拒绝部署语法错误的 sw.js）。" % name)
    # 用函数式替换，避免替换串里的反斜杠/组引用被 re 解释
    new = pat.sub(lambda _m: "const CACHE_NAME = '%s'" % name, src, count=1)
    if new != src:
        buf = new.encode('utf-8')
        orig = src.encode('utf-8')
        # 兜底：本次改写只替换一个版本号 token，字节数理应几乎不变。
        # 若出入很大，说明正则/替换写坏了（可能截断整个文件）→ 拒绝写入。
        if abs(len(buf) - len(orig)) > 200 or len(buf) < 20:
            raise RuntimeError('sw.js 改写结果异常（原 %d 字节 → 新 %d 字节），拒绝写入'
                               % (len(orig), len(buf)))
        tmp = sw_path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(buf)
        os.replace(tmp, sw_path)
        log('[deploy_pages] SW 缓存名同步为 %s（由 build-version 自动派生）' % name)
    else:
        log('[deploy_pages] SW 缓存名已是最新：%s' % name)
    # 无论是否改写过，都必须通过校验（这是本次事故的根治点）
    validate_sw_js(name)


def sync_site_title():
    """2026-09-12：站点标题（浏览器标签页）由 build-version 自动派生。

    用户 2026-09-12 反馈：标签页上只有一个光秃秃的日期「2026-09-12」，看不出是什么站。
    根因是 09-07 的生成脚本把 <title> 从「矿业新闻日报 2026-09-04」改成了纯日期
    （`re.sub(r'<title>\\d{4}-\\d{2}-\\d{2}</title>', '<title>%s</title>' % REPORT, html)`），
    此后每天的标签页都只剩日期。

    做法与 sync_sw_cache_name() 完全同源：build-version 已经是事实上的版本源
    （形如 20260912-2205），直接从中取日期拼出规范标题「矿业新闻日报 · 2026-09-12」。
    这样**无论当日生成脚本怎么写标题，推上线的标题都一致**——不依赖生成脚本或
    automation prompt 的自觉（生成脚本每天新写，写什么标题不可控）。

    幂等：标题已规范时不写盘、不产生 diff。
    """
    html_path = os.path.join(ROOT, 'index.html')
    if not os.path.isfile(html_path):
        return None
    with io.open(html_path, encoding='utf-8', newline='') as f:
        src = f.read()
    m = re.search(r'<meta name="build-version" content="(\d{4})(\d{2})(\d{2})-\d{4}"', src)
    if not m:
        raise RuntimeError('index.html 的 build-version 形状异常（应形如 20260912-2205），'
                           '无法派生站点标题（拒绝部署）')
    ct = len(re.findall(r'<title>', src))
    if ct == 0:
        raise RuntimeError('index.html 中找不到 <title>，无法规范化站点标题（拒绝部署）')
    # 取第一个：head 里的真标题永远在 <style> 之前（源文件里就在第 18 行）
    pat = re.compile(r'<title>[^<]*</title>')
    # 2026-09-13（午夜后补丁实测）：**优先保留标题里已有的日期**，只有在标题里压根没有日期时
    #   才用 build-version 兜底。理由：标题日期 = 日报**内容**的日期，build-version = **构建时刻**，
    #   午夜后打补丁时二者必然差 1 天 —— 若无条件按 build 派生，会把标题推到次日（内容却还是
    #   前一天的日报）→ 误导读者。「标题是不是停在昨天」由 preflight_check.check_site_title()
    #   把关（那才是管日期的地方）；本函数的职责收敛为「补站名 / 纠格式」。
    _mt = pat.search(src)
    _md = re.search(r'\d{4}-\d{2}-\d{2}', _mt.group(0)) if _mt else None
    _day = _md.group(0) if _md else '%s-%s-%s' % (m.group(1), m.group(2), m.group(3))
    want = '%s · %s' % (SITE_NAME, _day)
    new = pat.sub(lambda _m: '<title>%s</title>' % want, src, count=1)
    if new == src:
        log('[deploy_pages] 站点标题已规范：%s' % want)
        return want
    orig = src.encode('utf-8')
    buf = new.encode('utf-8')
    # 兜底：只替换一个标题串，字节数变化理应很小；出入过大说明正则写坏了
    if abs(len(buf) - len(orig)) > 200 or len(buf) < 1000:
        raise RuntimeError('index.html 标题改写结果异常（原 %d 字节 → 新 %d 字节），拒绝写入'
                           % (len(orig), len(buf)))
    tmp = html_path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(buf)
    os.replace(tmp, html_path)
    log('[deploy_pages] 站点标题规范化：<title>%s</title>' % want)
    return want


def main():
    force = '--force' in sys.argv
    # 4.0) 先按 build-version 同步 SW 缓存名与站点标题，再复制文件（保证推上去的就是新的）
    sync_sw_cache_name()
    sync_site_title()

    # 1) 校验必需文件齐全
    missing = [f for f in REQUIRED if not os.path.isfile(os.path.join(ROOT, f))]
    if missing:
        log('[deploy_pages] 缺少必需文件，已终止：%s' % ', '.join(missing))
        return 2

    # 2) 准备工作副本
    os.makedirs(WORK, exist_ok=True)
    if not os.path.isdir(os.path.join(WORK, '.git')):
        log('[deploy_pages] 首次初始化工作副本 %s' % WORK)
        run('git init', cwd=WORK)
        run('git checkout -b %s' % BRANCH, cwd=WORK)
        run('git config user.email "mining-daily@local"', cwd=WORK)
        run('git config user.name "mining-daily"', cwd=WORK)
        # remote 可能已存在（重复运行），先尝试新增，失败则覆盖 URL
        code, _ = run('git remote add origin %s' % REMOTE, cwd=WORK, check=False)
        if code != 0:
            run('git remote set-url origin %s' % REMOTE, cwd=WORK)
    else:
        # 确保停在正确分支
        run('git checkout %s' % BRANCH, cwd=WORK, check=False)

    # 3) 清理工作副本中"本轮不再需要"的文件（保留 .git）
    #    刻意不做"先清空再全量复制"：那样每轮都会删除十几个文件，
    #    既触发批量删除确认、也让 git 每次都认为全部文件变动。
    #    只删除确实已不在清单里的文件，日常运行删除数为 0。
    keep = set(REQUIRED + OPTIONAL + ['.nojekyll'])
    for name in os.listdir(WORK):
        if name == '.git' or name in keep:
            continue
        p = os.path.join(WORK, name)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            os.remove(p)
        log('[deploy_pages] 移出清单：%s' % name)

    # 4) 复制站点文件
    copied = []
    for f in REQUIRED + OPTIONAL:
        src = os.path.join(ROOT, f)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(WORK, f)
        shutil.copy2(src, dst)
        copied.append(f)
    log('[deploy_pages] 已复制 %d 个文件：%s' % (len(copied), ', '.join(copied)))

    # 4.2) 脚本指纹（内容寻址）：消除「新 HTML + 旧 app.js」混装
    bust_asset_versions()

    # 4.5) .nojekyll —— 跳过 GitHub Pages 的 Jekyll 构建
    #   Pages 默认对站点跑 Jekyll：会忽略下划线开头的文件/目录，还可能把 {{ }} 当 Liquid 模板处理。
    #   本项目是已经构建好的纯静态文件，跳过构建更稳妥、发布也更快。
    #   注意：这个文件只放在 gh-pages 分支里，不放项目根 —— 项目根的 server.py 按安全约定
    #   会拦截以 . 开头的静态路径，放那边反而访问不到。
    nojekyll = os.path.join(WORK, '.nojekyll')
    if not os.path.exists(nojekyll):
        with open(nojekyll, 'w') as f:
            f.write('')

    # 5) 提交（工作区有变更才提交）
    run('git add -A', cwd=WORK)
    code, status = run('git status --porcelain', cwd=WORK)
    if status.strip():
        import datetime
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        run('git commit -m "站点更新 %s"' % stamp, cwd=WORK)
        log('[deploy_pages] 已生成本地提交。')
    else:
        log('[deploy_pages] 工作区与上一次提交一致。')

    # 6) 推送
    # 注意：这里**不能**因为"工作区无变更"就跳过推送。
    # 若上一轮推送失败（断网、SSH 未就绪），本地会留下一个未推送的提交；
    # 下一轮工作区恰好无变更时若直接 return，这个提交将永远推不上去，线上内容被卡住。
    # git push 本身是幂等的（无新提交时返回 Everything up-to-date），故每轮都推一次最稳妥。
    log('[deploy_pages] 推送到 %s 分支…' % BRANCH)
    code, out = run('git push -u origin %s' % BRANCH, cwd=WORK, check=False)
    if code != 0:
        log('[deploy_pages] 第 1 次推送失败，3 秒后按「本地文件为准」合并远程再推：\n%s' % out)
        time.sleep(3)
        # 关键：这里绝不能用 git pull --rebase。
        # 非交互环境下 rebase 一旦需要人工介入就会停在中间态，之后每一轮定时任务都会失败。
        # 本站内容是「从 main 复制过来」的全量快照，历史合并一律以本地文件为准（-X ours）。
        run('git fetch origin %s' % BRANCH, cwd=WORK, check=False)
        run('git merge -X ours --no-edit FETCH_HEAD', cwd=WORK, check=False)
        code, out = run('git push -u origin %s' % BRANCH, cwd=WORK, check=False)
        if code != 0:
            log('[deploy_pages] 推送仍失败：\n%s' % out)
            log('[deploy_pages] 排查：检查 ~/.ssh/config 是否正确、公钥是否已加到 GitHub、网络是否可达。')
            return 1

    log('[deploy_pages] 推送成功。')
    code, out = run('git log -1 --format="%h %s"', cwd=WORK)
    log('[deploy_pages] 线上版本：%s' % out.strip())
    log('[deploy_pages] 站点地址：https://pliucugb-cyber.github.io/mining-daily/')
    return 0


if __name__ == '__main__':
    sys.exit(main())
