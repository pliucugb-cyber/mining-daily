#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_pwa_install.py —— PWA「装到桌面」可安装性闸门

背景（2026-09-12 用户反馈）
--------------------------
用户：「想把日报安装到桌面一直不成功，Chrome 里这两种方式（安装 / 创建快捷方式）都试了都不行。」

排查结论（用真 Chrome 的 DevTools 协议直接问，见 REFERENCE.md §41）：
    Page.getInstallabilityErrors → 0 条错误
即**网站侧完全合规**，Chrome 本体认为它「可安装」。失败发生在安装的**执行环节**。

2026-09-12 深夜用户**实测确诊**：那台国行小米**接上科学上网后「安装」立刻成功**
⇒ 唯一卡点就是「手机能不能连 Google 服务」（安卓 Chrome 装 PWA = 让 Google Play 服务
现场生成一个真正的应用包 / WebAPK，**不走系统安装器** —— 所以「安装未知应用」权限
在这条路上根本不是卡点，那是第一轮的错误归因，已更正）。
⇒ 结论性设计：对国内用户（绝大多数手机够不到 Google 服务）「安装」基本不可用，
  卡片必须**默认主推各浏览器通用的「添加到主屏幕」**，并把微信内置浏览器这个最常见
  入口单独点破（微信自己没有「添加到桌面」入口，须先「⋯ → 在浏览器打开」）。

但排查中确实发现两个**站内**该修的问题，本测试即为它们上锁：
  ① manifest 未声明 `id`、未把已存在的 maskable 图标挂进清单 → 图标被塞进白圆缩小、
     应用身份只靠 start_url（将来改 start_url 会被当成新应用）；
  ② app.js 的安装卡片**只在页面初始化时渲染一次**，而 beforeinstallprompt 往往之后
     才触发 → 「立即安装」按钮永远不出现，用户只能照文字去翻浏览器菜单。

本闸门覆盖：
  ① manifest.json 必填/硬化字段（含 id）——check_manifest() 可实跑，用坏输入验它真会判假；
  ② 每个图标的声明尺寸 == **真实 PNG 尺寸**（声明 512 实际 192 这类错误会直接让 Chrome 拒装）；
  ③ index.html head 的清单引用 + iOS/移动端独立运行声明；
  ④ app.js 安装链路的三个重渲染时机（防回退守卫，本轮修的正是这个）；
  ⑤ key 漂移守卫（localStorage 键字面量各只准出现一次）；
  ⑥ 通用引导（按浏览器给具体菜单项 + 微信「在浏览器打开」+ 小米桌面快捷方式权限
     + 不再错误归因「安装未知应用」）；
  ⑦ 2026-09-12 第二轮：文案只讲手机（不提电脑端）、浏览器入口收敛成单一对照表、
     「我的」面板的「点外面关闭」改用事件派发时的路径判断
     （原先点「装不上？点这里」会因就地重渲染把 e.target 摘离 DOM 而被误判成外部点击 →
      面板关闭、弹回首页，用户实测反馈）。

运行：python test_pwa_install.py
"""
import io
import os
import re
import sys
import json
import struct

ROOT = os.path.dirname(os.path.abspath(__file__))
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
    return bool(cond)


def read(path):
    with io.open(path, encoding='utf-8-sig', newline='') as f:
        return f.read()


def png_size(path):
    """读 PNG 头的 IHDR 拿真实宽高；不是 PNG 返回 None。"""
    if not os.path.isfile(path):
        return None
    b = open(path, 'rb').read()
    if len(b) < 24 or b[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', b[16:24])


def check_manifest(mf, root):
    """返回 (ok, errs)。设计成可被实跑——坏输入必须判假，否则就是恒真的假守卫。"""
    errs = []
    for k in ('name', 'short_name', 'start_url', 'scope', 'display',
              'theme_color', 'background_color', 'id'):
        if not mf.get(k):
            errs.append('缺字段 %s' % k)
    if mf.get('display') != 'standalone':
        errs.append('display 应为 standalone（否则装出来仍带浏览器外壳）')
    if mf.get('start_url') not in ('./', '.'):
        errs.append('start_url 应为相对路径 ./（站点部署在 /mining-daily/ 子路径）')
    if mf.get('prefer_related_applications'):
        errs.append('prefer_related_applications 不得为 true（会抑制安装提示）')
    icons = mf.get('icons') or []
    if not icons:
        errs.append('icons 为空（Chrome 要求至少 192 与 512）')
    any_sz, mask_sz = set(), set()
    for ic in icons:
        src = ic.get('src') or ''
        pur = ic.get('purpose') or 'any'
        real = png_size(os.path.join(root, src.lstrip('./').replace('/', os.sep)))
        if real is None:
            errs.append('图标缺失或非合法 PNG：%s' % src)
            continue
        if '%dx%d' % real != (ic.get('sizes') or ''):
            errs.append('%s 声明 %r 但实际 %dx%d' % (src, ic.get('sizes'), real[0], real[1]))
        if 'maskable' in pur:
            mask_sz.add(real[0])
        if 'any' in pur:
            any_sz.add(real[0])
    for need in (192, 512):
        if need not in any_sz:
            errs.append('缺 %d×%d 的 any 图标' % (need, need))
        if need not in mask_sz:
            errs.append('缺 %d×%d 的 maskable 图标（否则主屏图标被塞进白圆缩小）' % (need, need))
    return (len(errs) == 0), errs


index_html = read(os.path.join(ROOT, 'index.html'))
app_js = read(os.path.join(ROOT, 'app.js'))
manifest_raw = read(os.path.join(ROOT, 'manifest.json'))

# ==================== ① manifest.json ====================
print('===== ① manifest.json 可安装性字段 =====')
try:
    mf = json.loads(manifest_raw)
    check('manifest.json 是合法 JSON', True)
except Exception as e:
    mf = {}
    check('manifest.json 是合法 JSON', False, str(e))

ok, errs = check_manifest(mf, ROOT)
check('manifest 通过全部可安装性字段校验', ok, '；'.join(errs) if errs else '共 %d 个图标' % len(mf.get('icons', [])))

check('manifest.id 已显式声明（固定应用身份）',
      mf.get('id') == '/mining-daily/',
      '实际 %r。Chrome 缺 id 时用 start_url 当身份，将来改 start_url 会被视为新应用/装不上' % mf.get('id'))
check('manifest 引用了 maskable 图标（4 个图标：any 2 + maskable 2）',
      len(mf.get('icons', [])) == 4 and
      sum(1 for i in mf.get('icons', []) if 'maskable' in (i.get('purpose') or '')) == 2,
      '实际 %d 个图标' % len(mf.get('icons', [])))
check('manifest.lang / categories 已填（用于系统识别与商店归类）',
      bool(mf.get('lang')) and isinstance(mf.get('categories'), list))

# —— 实跑：坏输入必须判假（否则是恒真的假守卫）——
m_no_id = dict(mf); m_no_id.pop('id', None)
ok_bad, e_bad = check_manifest(m_no_id, ROOT)
check('实跑：删掉 id → 闸门判假', not ok_bad, '否则 id 守卫等于没写')

m_bad_size = json.loads(json.dumps(mf))
for ic in m_bad_size.get('icons', []):
    if ic.get('src') == './icon-192.png':
        ic['sizes'] = '512x512'
ok_bad2, e_bad2 = check_manifest(m_bad_size, ROOT)
check('实跑：图标声明尺寸与实际不符 → 闸门判假', not ok_bad2,
      '这类错误会让 Chrome 直接拒绝安装（%s）' % (e_bad2[0][:46] if e_bad2 else ''))

m_browser = json.loads(json.dumps(mf)); m_browser['display'] = 'browser'
ok_bad3, _ = check_manifest(m_browser, ROOT)
check('实跑：display=browser → 闸门判假', not ok_bad3, '否则装出来会带浏览器外壳又是「装了没用」')

m_missing = json.loads(json.dumps(mf))
m_missing['icons'] = [{'src': './not-exist.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'}]
ok_bad4, _ = check_manifest(m_missing, ROOT)
check('实跑：图标文件不存在 → 闸门判假', not ok_bad4, '线上 404 的图标是「装不上」的常见硬原因')

# ==================== ② index.html head 声明 ====================
print('\n===== ② index.html head：清单引用 + 独立运行声明 =====')
head = index_html[:index_html.find('</head>')] if '</head>' in index_html else index_html[:6000]

mlink = re.search(r'<link rel="manifest" href="([^"]+)"', head)
check('有 <link rel="manifest">', bool(mlink), '实际 %r' % (mlink.group(1) if mlink else None))
check('清单用相对路径引用（子路径部署也能取到）',
      bool(mlink) and not mlink.group(1).startswith('/'),
      '站点在 /mining-daily/ 子路径下，绝对路径 /manifest.json 会 404')

check('mobile-web-app-capable=yes（安卓独立运行）',
      re.search(r'<meta name="mobile-web-app-capable" content="yes"', head) is not None)
check('apple-mobile-web-app-capable=yes（iOS 添加到主屏后独立运行）',
      re.search(r'<meta name="apple-mobile-web-app-capable" content="yes"', head) is not None,
      '缺它时 iPhone 装到桌面仍带 Safari 外壳 —— 用户观感就是「装了没用」')
check('apple-mobile-web-app-status-bar-style 已声明',
      'apple-mobile-web-app-status-bar-style' in head)
at = re.search(r'<meta name="apple-mobile-web-app-title" content="([^"]*)"', head)
check('apple-mobile-web-app-title == manifest.short_name',
      bool(at) and at.group(1) == mf.get('short_name'),
      'iOS 主屏名取这个值：实际 %r / manifest.short_name=%r'
      % (at.group(1) if at else None, mf.get('short_name')))
check('有 apple-touch-icon（iOS 主屏图标来源）',
      'apple-touch-icon' in head)
check('有 theme-color（安装后状态栏配色）',
      re.search(r'<meta name="theme-color" content="#[0-9a-fA-F]{3,8}"', head) is not None)

# ==================== ③ app.js 安装链路 ====================
print('\n===== ③ app.js 安装卡片链路 =====')
check('定义了 mdRenderInstallCard', 'function mdRenderInstallCard(){' in app_js)
check('定义了 mdBindInstallCard（事件委托绑定）', 'function mdBindInstallCard(){' in app_js)
check('定义了 mdArmInstallStallWatch（失败守望）', 'function mdArmInstallStallWatch(){' in app_js)

bip = re.search(r"addEventListener\('beforeinstallprompt'.*?\n\}\);", app_js, re.S)
check('beforeinstallprompt 处理块存在', bool(bip))
check('⚠️ beforeinstallprompt 到达后重渲染卡片（本轮修复的核心）',
      bool(bip) and 'mdRenderInstallCard()' in bip.group(0),
      '原先只在初始化渲染一次 → 事件到达时按钮该出现却永远不出现')

ainst = re.search(r"addEventListener\('appinstalled'.*?\n\}\);", app_js, re.S)
check('appinstalled 处理块存在', bool(ainst))
check('appinstalled 后重渲染卡片并清掉失败记忆',
      bool(ainst) and 'mdRenderInstallCard()' in ainst.group(0)
      and 'MD_PWA_STALL_KEY,null' in ainst.group(0))

mine_branch = re.search(r"else if\(go==='mine'\)\{\n\s*if\(autoOpen\)\{([^\n]*)", app_js)
check('进入「我的」面板时重渲染卡片',
      bool(mine_branch) and 'mdRenderInstallCard()' in mine_branch.group(1),
      '否则用户打开面板看到的仍是初始化那一刻的旧卡片')

check('安装按钮用 data-pwa（未复活已删除的 data-act="install"）',
      'data-pwa="install"' in app_js and 'data-act="install"' not in app_js)
check('卡片含三类排障元素类名（warn / help / diag）',
      all(k in app_js for k in ('mine-install-warn', 'mine-install-help', 'mine-install-diag')))
check('排障文案点名真实卡点（Google 服务）',
      'Google 服务' in app_js,
      '安卓 Chrome 的「安装」要靠 Google 服务生成 WebAPK，国内手机够不到 —— 必须写清')
# 「安装未知应用」是第一轮的**错误归因**（2026-09-12 深夜实测确诊：接上科学上网后「安装」
#   立刻成功 ⇒ 卡点是 Google 服务，不是系统权限）。app.js 里留着解释这次误判的**注释**，
#   那不是文案；所以这里只扫**卡片渲染函数体内的字符串**，扫全文件必然误判。
def _card_user_text(src):
    parts = []
    for fn in ('mdPwaShortcutTable', 'mdPwaShortcutGeneric', 'mdPwaCurrentShortcut',
               'mdPwaShortcutStep', 'mdPwaShortcutPlain', 'mdPwaHeroHTML', 'mdPwaHelpHTML',
               'mdRenderInstallCard'):
        m = re.search(r'function %s\(\)\{.*?\n\}' % fn, src, re.S)
        if m:
            parts.append(m.group(0))
    blob = '\n'.join(parts)
    blob = re.sub(r'//[^\n]*', '', blob)                 # 去行注释
    blob = re.sub(r'/\*.*?\*/', '', blob, flags=re.S)     # 去块注释
    return blob

_card_text = _card_user_text(app_js)
assert _card_text, '未能从 app.js 提取到卡片文案区，锚点失效'
check('卡片**文案**不再把「安装未知应用」权限当卡点（2026-09-12 实测更正）',
      '安装未知应用' not in _card_text,
      '该权限是上一轮的错误归因；WebAPK 由 Google 服务生成应用包、不经过系统安装器')
check('实跑：把错误归因写回卡片文案 → 闸门必须判假',
      '安装未知应用' in _card_user_text(app_js.replace(
          'return \'<div class="mine-install-helpbody">\'',
          'return \'<div class="mine-install-helpbody">安装未知应用权限\'')),
      '否则这条守卫只是「恰好没写」，而不是真的会拦')
check('卡片文案给出小米「桌面快捷方式」权限这条实测可行路径（2026-09-12 用户实测）',
      '桌面快捷方式' in _card_text and '权限管理' in _card_text,
      'MIUI/HyperOS 上 Chrome 的「添加到主屏幕」需要该权限；用户实测：允许后立刻成功')
check('卡片默认主推通用路径（按当前浏览器给具体菜单项）',
      'function mdPwaShortcutStep(){' in app_js and 'function mdPwaIsWeChat(){' in app_js,
      '用户手机/浏览器五花八门，泛泛说「添加到主屏幕」等于没说')
check('覆盖微信内置浏览器这一最常见入口（给出「在浏览器打开」）',
      '在浏览器打开' in app_js and 'MicroMessenger' in app_js)
check('微信内不显示「安装为独立应用」按钮（点了必然无效，不误导）',
      'window.__deferredPrompt && !mdPwaIsWeChat()' in app_js)
check('已安装态仍保留（standalone 下不显示安装引导）',
      'IS_STANDALONE' in app_js and '已安装到主屏幕' in app_js)

# —— 2026-09-12 用户第二轮反馈：文案只讲手机 + 覆盖全浏览器 + 修「展开排障却跳首页」——
check('卡片文案只讲手机、不提电脑端（用户要求：电脑版在浏览器里点一下就装上了）',
      '电脑' not in _card_text,
      '扫的是卡片渲染函数体内的字符串（已去注释），不含别处的代码注释')
_BROWSERS = ('Chrome', '小米浏览器', '华为浏览器', 'UC 浏览器', 'QQ 浏览器',
             '三星浏览器', 'Edge', 'Firefox')
_hit = [n for n in _BROWSERS if n in _card_text]
check('卡片按浏览器逐个给入口（覆盖 >=6 种，不只讲 Chrome）',
      len(_hit) >= 6, '命中 %d/%d：%s' % (len(_hit), len(_BROWSERS), '/'.join(_hit)))
check('浏览器入口收敛成一张对照表（折叠态与展开态同源，不再各写一份）',
      app_js.count('function mdPwaShortcutTable(){') == 1
      and 'function mdPwaCurrentShortcut(){' in app_js
      and 'function mdPwaShortcutGeneric(){' in app_js,
      '原先每个浏览器一行 if-return，展开态要再抄一遍 → 必然「改一处漏一处」')
# —— 2026-09-12 用户第三轮反馈：自动识别浏览器只给一条 + 删表内标记 + 修 EdgA 漏判 ——
check('手机 Edge 的 UA（EdgA/）能被识别',
      'Edg[AE]?' in app_js,
      '用户实测：手机 Edge 的 UA 是 EdgA/（Edg/ 只在桌面版）；漏判后会落到 Chrome/ 分支，'
      '把指引和标记统统打到「安卓 Chrome」那条上')
check('「安卓 Chrome」判定排除国产厂商与 WebView（它们的 UA 同样含 Chrome/）',
      'MD_PWA_NOT_CHROME_RE' in app_js and 'mdPwaLooksLikePlainChrome' in app_js,
      'vivo / OPPO / 夸克 / 百度 / 搜狗 / 360 的 UA 都含 Chrome/，只判 Chrome 会给出错误的菜单方向')
check('对照表里不再给当前浏览器打标记（用户要求删除）',
      '你现在用的浏览器' not in _card_text and '你现在用的浏览器' not in app_js,
      '该标记实测会打在错的那条上 → 改为顶部 hero 只给一条')
check('帮助正文顶部只给一条「你该怎么做」（识别到浏览器就给那一条）',
      'function mdPwaHeroHTML(){' in app_js and '>检测到：' in app_js,
      '用户要求：自动识别浏览器，只出现对应浏览器的操作提醒')
check('对照表与常见问题收进折叠、不再一屏平铺（用户反馈文字太多）',
      app_js.count('<details class="pwa-fold"') >= 2 and 'class="pwa-list"' in app_js,
      '次要信息默认收起；行距与配色由 index.html 的 .pwa-* 规则提供')
check('安装帮助新增样式规则齐全（行动卡 / 折叠 / 行式对照表）',
      all(k in index_html for k in ('.pwa-hero', '.pwa-fold', '.pwa-row-name')),
      '样式缺失会让「颜色区分 + 折叠」在真机上失效')

check('「点外面关闭我的」改用事件派发时的路径判断（就地重渲染不再被误判成外部点击）',
      'e.composedPath()' in app_js and 'mdPath.indexOf(sheet)>=0' in app_js,
      '2026-09-12 用户实测：点「装不上？点这里」会把面板关掉、弹回首页')
check('旧的「closest 单判」写法已删除（防回退到会跳首页的版本）',
      "if(e.target.closest('#mineSheet')||(e.target.closest('.mtab')" not in app_js)

# —— key 漂移守卫：键值字面量各只准出现一次 ——
print('\n===== ④ key 漂移守卫（防「改一处漏一处」）=====')
for key in ('md_pwa_install_tried', 'md_pwa_install_stalled'):
    n = app_js.count("'%s'" % key)
    check('字面量 %s 在 app.js 只出现 1 次' % key, n == 1, '实际 %d 次' % n)
check('键名常量集中定义（MD_PWA_TRY_KEY / MD_PWA_STALL_KEY）',
      app_js.count('var MD_PWA_TRY_KEY=') == 1 and app_js.count('var MD_PWA_STALL_KEY=') == 1)

# ==================== ⑤ sw.js 与版本 ====================
print('\n===== ⑤ sw.js / build-version =====')
bv = re.search(r'<meta name="build-version" content="([^"]+)"', index_html)
sw = read(os.path.join(ROOT, 'sw.js'))
cache = re.search(r"const\s+CACHE_NAME\s*=\s*'([^']*)'", sw)
check('build-version 与 sw.js CACHE_NAME 同源',
      bool(bv) and bool(cache) and cache.group(1) == 'mining-daily-' + bv.group(1),
      'build=%s / cache=%s' % (bv.group(1) if bv else None, cache.group(1) if cache else None))
check('sw.js 预缓存清单含 manifest 之外的图标不影响安装（图标走 stale-while-revalidate）',
      'manifest' in sw)

print('\n===== 结果：%d PASS / %d FAIL =====' % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
