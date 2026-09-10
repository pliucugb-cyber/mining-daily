# -*- coding: utf-8 -*-
"""test_deploy_sw_gate.py — 守护「sw.js 必须可解析才能部署」的闸门（2026-09-10 事故回归）。

事故复盘：sw.js 第 10 行被写坏成 `const P260910-1900';`（SyntaxError）后原样上线。
成因链有两环，本测试逐一钉死：
  ① deploy_pages.sync_sw_cache_name() 的正则匹配不到被改坏的行 → `new == src` →
     打印「已是最新」后 **静默 return**，把语法错误的 sw.js 推上线。→ 现在必须 fail-fast。
  ② 整条流水线没有任何一步真正解析 sw.js（preflight 只查 index.html/app.js）。→ 现在有 check_sw_js。

运行：python test_deploy_sw_gate.py
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deploy_pages as dp          # noqa: E402
import preflight_check as pc       # noqa: E402

GOOD_SW = ("// ok\nconst CACHE_NAME = 'mining-daily-20260910-2030';\n"
           "self.addEventListener('install', () => {});\n")
# 事故原样的损坏行：没有合法的 CACHE_NAME 声明，且本身是语法错误
CORRUPT_SW = ("// corrupted\nconst P260910-1900';\n"
              "self.addEventListener('install', () => {});\n")
# CACHE_NAME 形状正常，但文件另有语法错误（校验必须抓得住）
SYNTAX_BAD_SW = ("const CACHE_NAME = 'mining-daily-20260910-2355';\n"
                 "const = ;\n")
HTML = '<meta name="build-version" content="20260910-2355">\n'

NEW_NAME = 'mining-daily-20260910-2355'


class DeploySwGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='mdsw_')
        self._root = dp.ROOT
        self._pc_root = pc.ROOT
        self._pc_html = pc.HTML
        dp.ROOT = self.tmp
        pc.ROOT = __import__('pathlib').Path(self.tmp)
        pc.HTML = pc.ROOT / 'index.html'
        with io.open(os.path.join(self.tmp, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(HTML)

    def tearDown(self):
        dp.ROOT = self._root
        pc.ROOT = self._pc_root
        pc.HTML = self._pc_html
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, content):
        p = os.path.join(self.tmp, 'sw.js')
        with io.open(p, 'w', encoding='utf-8') as f:
            f.write(content)
        return p

    def _read(self):
        with io.open(os.path.join(self.tmp, 'sw.js'), encoding='utf-8') as f:
            return f.read()

    def test_rewrites_cache_name_and_validates(self):
        """正常路径：按 build-version 改写 CACHE_NAME，并跑完校验不报错。"""
        self._write(GOOD_SW)
        dp.sync_sw_cache_name()
        self.assertIn("const CACHE_NAME = '%s'" % NEW_NAME, self._read())

    def test_idempotent(self):
        """同一版本重复同步：结果一致、不报错。"""
        self._write(GOOD_SW)
        dp.sync_sw_cache_name()
        dp.sync_sw_cache_name()
        self.assertIn("const CACHE_NAME = '%s'" % NEW_NAME, self._read())

    def test_fail_fast_when_cache_name_line_destroyed(self):
        """事故场景：CACHE_NAME 行被写坏 → 必须抛错终止部署，而不是静默跳过。"""
        self._write(CORRUPT_SW)
        with self.assertRaises(RuntimeError):
            dp.sync_sw_cache_name()
        # 坏文件必须原样保留（不得被改成半成品）
        self.assertIn("const P260910-1900';", self._read())

    def test_validate_rejects_syntax_error(self):
        """CACHE_NAME 形状正常但文件语法错误 → validate 必须拦下。"""
        if dp._node_exe() is None:
            self.skipTest('未找到 node，跳过语法校验用例')
        self._write(SYNTAX_BAD_SW)
        with self.assertRaises(RuntimeError):
            dp.validate_sw_js(NEW_NAME)

    def test_validate_rejects_version_mismatch(self):
        """CACHE_NAME 与 build-version 派生值不一致 → 必须拦下。"""
        self._write(GOOD_SW)
        with self.assertRaises(RuntimeError):
            dp.validate_sw_js('mining-daily-19990101-0000')

    def test_preflight_detects_corrupt_sw(self):
        """preflight_check.check_sw_js 必须能识别坏 sw.js（06:00 自动化闸门）。"""
        self._write(CORRUPT_SW)
        ok, findings = pc.check_sw_js('')
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith('❌') for f in findings), findings)

    def test_preflight_accepts_healthy_sw(self):
        """健康 sw.js：CACHE_NAME 与 build-version 一致且可解析 → 通过。"""
        if dp._node_exe() is None:
            self.skipTest('未找到 node，跳过语法校验用例')
        self._write("const CACHE_NAME = '%s';\nself.addEventListener('install', () => {});\n" % NEW_NAME)
        ok, findings = pc.check_sw_js('')
        self.assertTrue(ok, findings)


if __name__ == '__main__':
    unittest.main(verbosity=2)
