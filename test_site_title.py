#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_site_title.py —— 站点标题（浏览器标签页）约定闸门

背景（2026-09-12 用户反馈）
--------------------------
用户指着浏览器标签页说「这里的名称修改一下」。当时标签页上只有一个光秃秃的日期
「2026-09-12」，完全看不出是什么站。

根因不是忘了写，而是**09-07 的一次回退**：
    09-04~09-06：html.replace('<title>矿业新闻日报 2026-09-04</title>', ...)   ← 有站名
    09-07 起    ：html = re.sub(r'<title>\\d{4}-\\d{2}-\\d{2}</title>', '<title>%s</title>' % REPORT, html)
                                                     ↑ 只写日期，站名从此丢失
此后每天生成都沿用这个写法，没人察觉。

所以本轮不只是把标题改回来，而是把它做成**有约束的约定**（REFERENCE.md §39）：
  ① index.html 静态标题 = 「矿业新闻日报 · YYYY-MM-DD」；
  ② deploy_pages.sync_site_title() 在每次部署前按 build-version **自动派生**标题
     （与 sw.js 的 CACHE_NAME 同源）。这是关键：生成脚本每天新写、写什么标题不可控，
     只有落点和 build-version 绑定的自愈才不依赖任何脚本/prompt 的自觉；
  ③ preflight_check.check_site_title() 做前置闸门（06:00 自动化真正会跑的那一步）；
  ④ 最新一份 generate_*.py 必须用宽松正则 + 断言，不得退回纯日期写法。

本测试把 ①~④ 全部锁住；③④ 里的函数都**实跑**（不只查字符串存在），
避免写出「永远返回 True」的假守卫。

运行：python test_site_title.py
"""
import io
import os
import re
import sys
import glob
import shutil
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import deploy_pages as dp          # noqa: E402
import preflight_check as pf       # noqa: E402

SITE = '矿业新闻日报'
PASS = 0
FAIL = 0


def check(name, cond, why=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  PASS  %s%s' % (name, ('  → ' + why) if why else ''))
    else:
        FAIL += 1
        print('  FAIL  %s%s' % (name, ('  → ' + why) if why else ''))


def read(path):
    with io.open(path, encoding='utf-8-sig', newline='') as f:
        return f.read()


index_html = read(os.path.join(ROOT, 'index.html'))
manifest = read(os.path.join(ROOT, 'manifest.json'))

# ==================== ① index.html 标题 ====================
print('===== ① index.html 站点标题 =====')
titles = re.findall(r'<title>([^<]*)</title>', index_html)
check('index.html 恰好 1 个 <title>', len(titles) == 1, '实际 %d 个（多出来的是内联 SVG 的标题）' % len(titles))
title = titles[0].strip() if titles else ''
m = re.match(r'^%s · (\d{4}-\d{2}-\d{2})$' % re.escape(SITE), title)
check('标题形如「%s · YYYY-MM-DD」' % SITE, bool(m),
      '实际 %r；只剩纯日期即为 09-07 的回退（站名丢失）' % title)

check('标题仍含完整日期（app.js qaReportDate 的兜底依赖 document.title）',
      bool(re.search(r'\d{4}-\d{2}-\d{2}', title)),
      'qaReportDate() 在 #todaySection 缺失时回退解析 document.title')

mb = re.search(r'<meta name="build-version" content="(\d{8})-(\d{4})"', index_html)
check('build-version 存在且形状合法', bool(mb), '形如 20260912-2221')
def _title_matches_build(td, bd, hh):
    """标题日期与 build 是否合法配比：同日，或**午夜后补丁**（+1 天且 build 时间 < 01:00）。

    2026-09-13 00:3x 实测需要：站点标题日期 = 日报**内容**日期，build-version = **构建时刻**，
    午夜后打补丁时二者必然差 1 天（内容仍是前一天的日报）。仅放行 00:00–00:59 这一段 ——
    06:00 生成侧若漏改标题（build 06:xx）仍会被拦，守卫没有放松。
    """
    import datetime as _dt
    try:
        t = _dt.date(*[int(x) for x in td.split('-')])
        b = _dt.date(int(bd[:4]), int(bd[4:6]), int(bd[6:8]))
    except ValueError:
        return False
    d = (b - t).days
    return d == 0 or (d == 1 and int(str(hh)[:2]) < 1)   # hh 可能是 '0031'（HHMM）

if m and mb:
    check('标题日期与 build-version 同日（或午夜后补丁：+1 天且 build 时间 < 01:00）',
          _title_matches_build(m.group(1), mb.group(1), mb.group(2)),
          '标题 %s / build-version %s-%s' % (m.group(1), mb.group(1), mb.group(2)))

# ==================== ② manifest.json 与页面一致 ====================
print('\n===== ② manifest.json（安装到主屏的名字与配色）=====')
import json  # noqa: E402
mf = json.loads(manifest)
check('manifest.name == %s' % SITE, mf.get('name') == SITE, '实际 %r' % mf.get('name'))
check('manifest.short_name 非空且 ≤6 字', 1 <= len(mf.get('short_name', '')) <= 6,
      '主屏图标标签放不下长名（实际 %r）' % mf.get('short_name'))
mt = re.search(r'<meta name="theme-color" content="([^"]+)"', index_html)
check('manifest.theme_color 与 meta theme-color 一致',
      bool(mt) and mf.get('theme_color') == mt.group(1),
      'manifest=%r / meta=%r（不一致会导致安装后状态栏颜色与页面不同）'
      % (mf.get('theme_color'), mt.group(1) if mt else None))

# ==================== ③ preflight 前置闸门（实跑） ====================
print('\n===== ③ preflight_check.check_site_title（实跑）=====')
pf_src = read(os.path.join(ROOT, 'preflight_check.py'))
check('定义了 check_site_title', 'def check_site_title' in pf_src)
check('已注册进 sections', "('站点标题', check_site_title(html_text))" in pf_src,
      '只定义不注册 = 闸门不生效')
check('注册的是 html_text 而非 text',
      "check_site_title(html_text)" in pf_src,
      '⚠️ app.js 的图表模板里也有 <title> 字面量，喂拼接文本会误判')
ok, _ = pf.check_site_title(index_html)
check('对当前 index.html 判定通过', ok)
bad = index_html.replace('<title>%s · %s</title>' % (SITE, m.group(1)),
                         '<title>%s</title>' % m.group(1), 1) if m else ''
ok_bad, f_bad = pf.check_site_title(bad)
check('对「纯日期」旧标题判定失败', not ok_bad,
      '否则就是恒真的假守卫（%s）' % (f_bad[0][:40] if f_bad else ''))
d1 = m.group(1) if m else '2026-01-01'
ok_day, _ = pf.check_site_title(
    index_html.replace('<title>%s · %s</title>' % (SITE, d1), '<title>%s · 2000-01-01</title>' % SITE, 1))
check('标题日期与 build-version 不同日 → 失败', not ok_day,
      '防止「页面更新了、标题还停在昨天」')

# ==================== ④ deploy 自愈（实跑） ====================
print('\n===== ④ deploy_pages.sync_site_title（实跑）=====')
dp_src = read(os.path.join(ROOT, 'deploy_pages.py'))
check('定义了 sync_site_title', 'def sync_site_title' in dp_src)
main_block = dp_src.split('def main(')[1] if 'def main(' in dp_src else ''
check('main() 里已调用', 'sync_site_title()' in main_block)
check('调用在复制文件之前',
      'sync_site_title()' in main_block and '已复制' in main_block
      and main_block.index('sync_site_title()') < main_block.index('已复制'),
      '必须在 shutil.copy2 之前改源文件，否则复制到工作副本的仍是旧标题')

tmp = tempfile.mkdtemp(prefix='md-title-')
orig_root = dp.ROOT
try:
    dp.ROOT = tmp
    p = os.path.join(tmp, 'index.html')
    bad_html = index_html.replace('<title>%s · %s</title>' % (SITE, d1),
                                  '<title>%s</title>' % d1, 1)
    with io.open(p, 'w', encoding='utf-8', newline='') as f:
        f.write(bad_html)
    got = dp.sync_site_title()
    after = read(p)
    check('把纯日期标题自愈为规范形式', got == '%s · %s' % (SITE, d1) and
          ('<title>%s · %s</title>' % (SITE, d1)) in after,
          '拿到 %r' % got)
    check('自愈只动标题、其余内容不变',
          after.replace('<title>%s · %s</title>' % (SITE, d1), '<title>%s</title>' % d1, 1) == bad_html)
    before = after
    dp.sync_site_title()
    check('幂等：重复执行不再改动', read(p) == before, '否则每次部署都produce无意义 diff')
    # build-version 形状异常时必须 fail-fast，而不是静默放过
    with io.open(p, 'w', encoding='utf-8', newline='') as f:
        f.write(bad_html.replace('content="%s-%s"' % (mb.group(1), mb.group(2)),
                                 'content="oops"', 1) if mb else bad_html)
    try:
        dp.sync_site_title()
        check('build-version 异常时抛错（拒绝部署）', False, '静默放过会推出错标题')
    except RuntimeError:
        check('build-version 异常时抛错（拒绝部署）', True)
finally:
    dp.ROOT = orig_root
    shutil.rmtree(tmp, ignore_errors=True)

# ==================== ⑤ 生成脚本模板（动态取最新一份） ====================
print('\n===== ⑤ 最新一份 generate_*.py 的标题写法 =====')
gens = sorted(glob.glob(os.path.join(ROOT, 'generate_2026*.py')))
check('存在 generate_2026*.py', bool(gens))
if gens:
    newest = os.path.basename(gens[-1])
    g = read(gens[-1])
    check('%s 定义了 SITE_NAME' % newest, "SITE_NAME = '%s'" % SITE in g)
    check('%s 用宽松正则 <title>[^<]*</title> 覆写' % newest,
          "re.subn(r'<title>[^<]*</title>'" in g)
    check('%s 有 _n_title 断言' % newest, 'assert _n_title == 1' in g)
    check('%s 有标题格式断言' % newest, "'站点标题格式不符'" in g)
    check('%s 已无「纯日期」写法' % newest, "'<title>%s</title>' % REPORT" not in g,
          '09-07 的回退写法，禁再出现')

# ==================== ⑥ 站名一致（同域其它入口） ====================
print('\n===== ⑥ 站名一致 =====')
for f in ('404.html', 'server.py', 'redirect_server.py'):
    p = os.path.join(ROOT, f)
    if os.path.isfile(p):
        check('%s 站名一致' % f, SITE in read(p), '同域入口应显示同一站名')

print('\n===== 结果：%d PASS / %d FAIL =====' % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
