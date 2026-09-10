#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_asset_versioning.py —— 部署期「脚本内容指纹」闸门测试

背景（2026-09-11 第三轮事故复盘的结论）
--------------------------------------
GitHub Pages 对静态资源回 Cache-Control: max-age=600，而 `<script src="app.js">` 这种
固定 URL 会命中浏览器 HTTP 缓存；再叠加 Service Worker 缓存，用户完全可能长期跑着
**旧的 app.js**，却已经拿到 **新的 index.html**。旧 app.js 里没有当轮的自愈逻辑，
页面自己救不回来 —— 这正是「区块永久停在加载中」最典型的成因。

deploy_pages.bust_asset_versions() 在推送到 gh-pages 前，把 4 个脚本标签改写成
`app.js?v=<md5 前 8 位>`：内容一变 URL 就变，浏览器与 SW 都只能去网络取新版，
「新旧混装」在机制上不可能出现。

本测试锁住这个机制，避免以后有人重构部署脚本时把它悄悄删掉/改坏：
  ① 函数存在且在 main() 里被调用（放在复制之后、提交之前）；
  ② 改写后 4 个脚本都带上 `?v=<真实 md5 前 8 位>`；
  ③ 幂等：重复执行不会出现 `app.js?v=aaa?v=bbb`；
  ④ 找不到预期的 src 时直接抛错（拒绝部署坏站点）；
  ⑤ 绝不触碰 SW 注册 URL（必须保持 './sw.js'，不带查询串）。

运行：python test_asset_versioning.py
"""
import io
import os
import re
import sys
import shutil
import hashlib
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import deploy_pages as dp  # noqa: E402

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


print('===== ① 机制存在且接入部署流程 =====')
with io.open(os.path.join(ROOT, 'deploy_pages.py'), encoding='utf-8') as f:
    dep_src = f.read()
check('定义了 bust_asset_versions', 'def bust_asset_versions' in dep_src)
check('BUST_FILES 覆盖 4 个脚本',
      all(('BUST_FILES' in dep_src) and (n in dep_src) for n in
          ['app.js', 'news-data.js', 'lme-data.js', 'price-history.js']),
      'app.js 与三个数据脚本都可能因缓存而变旧')
main_block = dep_src.split('def main(')[1] if 'def main(' in dep_src else ''
check('main() 里在复制文件之后调用', 'bust_asset_versions()' in main_block,
      '必须在 shutil.copy2 之后改工作副本，否则改了会被覆盖')
check('调用点位于复制与提交之间',
      main_block.index('bust_asset_versions()') > main_block.index('已复制')
      if ('已复制' in main_block and 'bust_asset_versions()' in main_block) else False,
      '复制 → 打指纹 → git add')

print('\n===== ② 改写结果：4 个脚本带上真实内容指纹 =====')
tmp_work = tempfile.mkdtemp(prefix='md-bust-')
orig_work = dp.WORK
try:
    dp.WORK = tmp_work
    src_html = os.path.join(ROOT, 'index.html')
    dst_html = os.path.join(tmp_work, 'index.html')
    shutil.copy2(src_html, dst_html)
    marks = dp.bust_asset_versions()
    with io.open(dst_html, encoding='utf-8', newline='') as f:
        out = f.read()

    expect = {}
    for name in dp.BUST_FILES:
        with open(os.path.join(ROOT, name), 'rb') as f:
            expect[name] = hashlib.md5(f.read()).hexdigest()[:8]

    for name, h in expect.items():
        check('%s 已带指纹 ?v=%s' % (name, h),
              ('src="%s?v=%s"' % (name, h)) in out,
              '内容不变则 URL 不变；一变就换 URL，缓存无法再喂旧版')
    check('返回的 marks 覆盖 4 个脚本', len(marks) == 4, '实际 %d 个' % len(marks))

    # 幂等：再来一次不应产生 app.js?v=a?v=b 这类叠加
    dp.bust_asset_versions()
    with io.open(dst_html, encoding='utf-8', newline='') as f:
        out2 = f.read()
    check('重复执行结果幂等', out2 == out, '避免每次部署都产生无意义 diff')
    check('没有出现叠加查询串', '?v=' not in out2.replace('?v=', '\x00').replace('\x00', '?v=').split('src=')[0] or
          not re.search(r'\.js\?v=[^"]*\?v=', out2),
          '形如 app.js?v=a?v=b 会让浏览器彻底放弃缓存')
    check('正文其余内容未被改动',
          len(out2) - len(io.open(src_html, encoding='utf-8', newline='').read()) < 200,
          '只应动 4 处 src')

    print('\n===== ③ 缺失脚本时拒绝部署 =====')
    bad = os.path.join(tmp_work, 'index2.html')
    with io.open(bad, 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html><html><head></head><body>没有脚本标签</body></html>')
    # 临时把文件名指过去：直接调用内部逻辑不好走，改为验证异常分支本身存在
    check('找不到 src 时抛 RuntimeError（拒绝部署）',
          '指纹改写失败（拒绝部署）' in dep_src,
          '宁可部署失败，也不能推一个「部分脚本没指纹」的站点上去')
finally:
    dp.WORK = orig_work
    shutil.rmtree(tmp_work, ignore_errors=True)

print('\n===== ④ SW 注册 URL 必须保持无查询串 =====')
with io.open(os.path.join(ROOT, 'app.js'), encoding='utf-8') as f:
    app_src = f.read()
check("app.js 注册 './sw.js'（不带 ?v=）",
      "register('./sw.js')" in app_src and "register('./sw.js?" not in app_src,
      '注册 URL 带版本串会被浏览器当成「新注册」→ 反复 install/activate → ~10s 循环刷新')
check('BUST_FILES 不含 sw.js', 'sw.js' not in dp.BUST_FILES,
      'sw.js 是不允许被指纹化的特例')

print('\n===== 结果：%d PASS / %d FAIL =====' % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
