# -*- coding: utf-8 -*-
"""
test_preflight_div.py — preflight 的 div 收支检查「作用范围」回归测试（2026-09-11）

事故：preflight_check.py::main() 为了避免「关键功能缺失」误报，把 app.js 全文拼进
index.html 文本再统一跑各项检查。但 app.js 是 JS 不是 HTML：
  · 模板字符串可以只写半个标签（另一半在别处拼）；
  · 注释/字符串里随时可能出现字面 `<div>`；
而 check_div_balance 只剔除 index.html 内的 <script>/<style> 块，对「拼进来的 app.js」
毫无防护 —— 于是 app.js 里任何一处不成对的 `<div>` 都会让闸门误红。

实况：2026-09-11 一处 JS 注释写了字面 `<div>` → 闸门报「有 1 个 <div> 未闭合」
→ preflight exit 1 → 06:00 自动化会据此判定 index.html 脏状态、`checkout -- index.html`
后中止当日生成。

修复：把拼接文本（含 app.js）与 HTML 原文分开，div 收支只吃 HTML 原文。
本测试锁三件事：
  ① check_div_balance 本身能抓出真正不平衡的 HTML；
  ② main() 里喂给 check_div_balance 的**不是**喂给 check_functions 的那份拼接文本（AST 断言）；
  ③ 端到端跑一次 preflight_check.py，要求 exit 0 且给出「div 收支平衡」。

运行：python test_preflight_div.py
"""
import ast
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import preflight_check as pf   # noqa: E402

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


print("\n===== ① check_div_balance 本身 =====")
ok, _ = pf.check_div_balance('<div class="a"><div class="b"></div></div>')
check("平衡 HTML → 通过", ok is True)
ok, f = pf.check_div_balance('<div class="a"><div class="b"></div>')
check("少一个 </div> → 不通过", ok is False, f)
ok, f = pf.check_div_balance('</div>')
check("多余 </div> → 不通过", ok is False, f)
# 这行正是事故形态：JS 注释里出现字面 <div>。作为 HTML 它确实不平衡——
# 所以关键在于「它不该被喂进来」，而不是让 check_div_balance 去理解 JS。
ok, _ = pf.check_div_balance('// 不再把 li 塞进 <div>\n')
check("（说明）字面 <div> 若被当作 HTML 必然误报 → 故必须排除 app.js", ok is False)

print("\n===== ② main() 不得把 app.js 拼接文本喂给 div 检查（AST 断言）=====")
src = (BASE / "preflight_check.py").read_text(encoding="utf-8")
tree = ast.parse(src)
main_fn = next((n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
check("找到 main()", main_fn is not None)

args_of = {}
if main_fn:
    for node in ast.walk(main_fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.args and isinstance(node.args[0], ast.Name):
            args_of.setdefault(node.func.id, node.args[0].id)
    div_arg = args_of.get("check_div_balance")
    fn_arg = args_of.get("check_functions")
    check("main() 里能找到两处调用", bool(div_arg) and bool(fn_arg),
          "div=%s functions=%s" % (div_arg, fn_arg))
    check("★ div 检查用的不是「含 app.js 的拼接文本」",
          div_arg is not None and div_arg != fn_arg,
          "div 吃 %s；functions 吃 %s" % (div_arg, fn_arg))
    check("★ div 检查吃的是 HTML 原文（html_text）",
          div_arg == "html_text", div_arg)

print("\n===== ③ 端到端跑一次 preflight =====")

PY = sys.executable
r = subprocess.run([PY, str(BASE / "preflight_check.py")],
                   capture_output=True, text=True, cwd=str(BASE))
out = (r.stdout or "") + (r.stderr or "")
check("preflight_check.py exit 0", r.returncode == 0,
      "exit=%d" % r.returncode)
check("输出含「div 收支平衡」", "div 收支平衡" in out,
      "未闭合" in out and "误报：出现「未闭合」" or "")
check("输出不含「<div> 未闭合」", "<div> 未闭合" not in out)

print("\n===== 汇总 =====")
print("  通过 %d / 失败 %d" % (pass_n, fail_n))
sys.exit(1 if fail_n else 0)
