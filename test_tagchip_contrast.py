# -*- coding: utf-8 -*-
"""
test_tagchip_contrast.py — 关键词标签（.tag-chip）配色回归测试（2026-09-11，视觉评审 F6）

背景：
  app.js injectTags() 原先把 TAG_STYLE 里的 color/bg 用 chip.style.color / chip.style.background
  内联下发。内联样式恒压过任何选择器（包括 body.dark .tag-chip），于是：

    1. 暗色模式下 11 组标签配色全部失效，统一回落到 --surface-3/--ink-500
       —— 彩色标签承载的「类别」语义在暗色下被抹平；
    2. 亮色下另有 4 组不达 AA：metal 3.78 / rights 3.89 / explore 3.00 / default 3.21。

修复：
  · app.js：TAG_STYLE 只留 label（配色单一真源迁走）；chip 类名改为 `tag-chip tc-<类别>`；
    不再注入任何内联颜色。
  · index.html：新增 `.tag-chip.tc-*`（亮）与 `body.dark .tag-chip.tc-*`（暗）两套规则。

本测试锁住：
  ① 亮/暗 11 组配对的实测对比度均 ≥4.5；
  ② 每个类别都有亮、暗两条规则（防"只补了一半"）；
  ③ TAG_STYLE 的类别集合与 CSS 类别集合完全一致（防新增类别时漏写配色）；
  ④ app.js 不再存在内联注入（防回退）。

运行：python test_tagchip_contrast.py
"""
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

pass_n = 0
fail_n = 0


def check(name, cond, extra=""):
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print("  PASS  " + name + ("  -> " + str(extra) if extra else ""))
    else:
        fail_n += 1
        print("  FAIL  " + name + ("  -> " + str(extra) if extra else ""))


def read(p):
    with io.open(os.path.join(BASE, p), encoding="utf-8", errors="replace") as f:
        return f.read()


# ---------------- WCAG 2.x 相对亮度 / 对比度 ----------------
def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(h):
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


html = read("index.html")
app = read("app.js")

# ---------------- 解析 CSS 规则 ----------------
# ⚠️ 必须按行锚定首字符，不能用 `\.tag-chip\.tc-([\w-]+)\s*\{` 这种"任意位置"正则：
#    暗色规则是 `body.dark .tag-chip.tc-X{...}`，其中也含子串 `.tag-chip.tc-X{`，
#    不加锚点会被后出现的暗色规则覆盖掉亮色条目 —— 于是"亮色校验"实际在校验暗色值，
#    表面 GREEN 却漏掉亮色回归（本文件 2026-09-11 初版即踩此坑，已修）。
light = {}
dark = {}
for _line in html.split("\n"):
    s = _line.strip()
    m = re.match(r"^body\.dark\s+\.tag-chip\.tc-([\w-]+)\s*\{(.*)\}$", s)
    if m:
        fg = re.search(r"color\s*:\s*(#[0-9a-fA-F]{6})", m.group(2))
        bg = re.search(r"background\s*:\s*(#[0-9a-fA-F]{6})", m.group(2))
        if fg and bg:
            dark[m.group(1)] = (fg.group(1), bg.group(1))
        continue
    m = re.match(r"^\.tag-chip\.tc-([\w-]+)\s*\{(.*)\}$", s)
    if m:
        fg = re.search(r"color\s*:\s*(#[0-9a-fA-F]{6})", m.group(2))
        bg = re.search(r"background\s*:\s*(#[0-9a-fA-F]{6})", m.group(2))
        if fg and bg:
            light[m.group(1)] = (fg.group(1), bg.group(1))

# ---------------- 解析 app.js 的 TAG_STYLE 类别 ----------------
m = re.search(r"const TAG_STYLE\s*=\s*\{(.*?)\n\};", app, re.S)
style_block = m.group(1) if m else ""
js_classes = set(re.findall(r"^\s*([A-Za-z][\w-]*)\s*:\s*\{", style_block, re.M))

print("\n===== ① 类别集合一致性 =====")
check("TAG_STYLE 解析到类别", len(js_classes) >= 10, "%d 个：%s" % (len(js_classes), ",".join(sorted(js_classes))))
check("每个 TAG_STYLE 类别都有亮色规则",
      js_classes <= set(light), "缺：" + ",".join(sorted(js_classes - set(light))))
check("每个 TAG_STYLE 类别都有暗色规则",
      js_classes <= set(dark), "缺：" + ",".join(sorted(js_classes - set(dark))))
check("CSS 亮色规则数 == 类别数 + default",
      len(light) == len(js_classes) + 1, "light=%d js=%d" % (len(light), len(js_classes)))
check("CSS 暗色规则数 == 类别数 + default",
      len(dark) == len(js_classes) + 1, "dark=%d js=%d" % (len(dark), len(js_classes)))
check("存在 .tc-default 兜底（亮）", "default" in light)
check("存在 .tc-default 兜底（暗）", "default" in dark)

print("\n===== ② 亮色配对对比度（目标 ≥4.5）=====")
# 防"解析串台"：亮/暗两套必须确实不同（初版正则会把暗色值读进亮色字典）
check("亮色与暗色取值确实不同（解析未串台）", light != dark)
check("亮色取样核对 metal = #ba4a00 on #fdf2e9",
      light.get("metal") == ("#ba4a00", "#fdf2e9"), str(light.get("metal")))
check("亮色取样核对 explore = #117c67 on #e8f8f5",
      light.get("explore") == ("#117c67", "#e8f8f5"), str(light.get("explore")))
bad_light = []
for cls, (fg, bg) in sorted(light.items()):
    v = contrast(fg, bg)
    ok = v >= 4.5
    if not ok:
        bad_light.append(cls)
    print("  %-4s %-9s %s on %s = %.2f" % ("OK" if ok else "BAD", cls, fg, bg, v))
check("亮色 11 组全部 ≥4.5", not bad_light, "不达标：" + ",".join(bad_light))

print("\n===== ③ 暗色配对对比度（目标 ≥4.5）=====")
bad_dark = []
for cls, (fg, bg) in sorted(dark.items()):
    v = contrast(fg, bg)
    ok = v >= 4.5
    if not ok:
        bad_dark.append(cls)
    print("  %-4s %-9s %s on %s = %.2f" % ("OK" if ok else "BAD", cls, fg, bg, v))
check("暗色 11 组全部 ≥4.5", not bad_dark, "不达标：" + ",".join(bad_dark))

print("\n===== ④ 反回退：不得再内联注入颜色 =====")
check("app.js 无 chip.style.color/background 注入",
      not re.search(r"chip\.style\.(color|background)", app))
check("app.js 通过 tc-<类别> 类名下发育色",
      "tag-chip tc-" in app)
check("TAG_STYLE 内不再维护 color/bg（单一真源）",
      not re.search(r"strategy\s*:\s*\{\s*color", app))
check("injectTags 未回退到 chip.className='tag-chip' 裸写法",
      "chip.className='tag-chip';" not in app)

print("\n===== ⑤ 特异性：暗色规则必须压过 body.dark .tag-chip =====")
# body.dark .tag-chip        -> (0,2,1)
# body.dark .tag-chip.tc-X   -> (0,3,1)  必须写成后者
m2 = re.search(r"body\.dark\s+\.tag-chip\s*\{", html)
check("仍存在 body.dark .tag-chip 兜底规则", bool(m2))
bare_dark_tc = re.findall(r"body\.dark\s+\.tag-chip\s*\{[^}]*color\s*:", html)
check("暗色类别规则均带 .tc- 后缀（未写成裸 body.dark .tag-chip 覆盖色）",
      len(bare_dark_tc) <= 1,
      "裸规则数=%d（含兜底 1 条为正常）" % len(bare_dark_tc))
check("暗色 hover 已改为提亮（否则深底越 hover 越暗）",
      "body.dark .tag-chip:hover{filter:brightness(1.15)}" in html)

print("\n===== 汇总 =====")
print("  通过 %d / 失败 %d" % (pass_n, fail_n))
sys.exit(1 if fail_n else 0)
