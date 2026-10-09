#!/usr/bin/env python3
"""token_audit --label 批次审计契约测试（2026-10-09 Phase 6 批）。

背景：12 票混拉合集会话审计被错标第一票码（A1 自提码扫到 603993 → stock=603993
入史/落单票目录）——批次审计无单一归巢目录，须 --label 接管命名与落点。
执法面：label 命名/落点 + history label 键 + 注释行 + R8 闸不松动（--stock 错靶
在 label 模式下仍必须非零零写入）+ 并存优先级钉死 + 无 label 回归极。
所有子进程统一 TOKEN_AUDIT_NO_HISTORY=1 + 隔离 HOME（防污染真环）。
"""
import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.join(HERE, "..", "scripts", "token_audit.py")

sys.path.insert(0, HERE)
from test_token_audit import _build_fixture  # noqa: E402  复用合成会话 fixture


def _run(fx, home, label="", stock=None, out=None, no_history=True):
    env = dict(os.environ)
    env["TOKEN_AUDIT_NO_HISTORY"] = "1" if no_history else "0"
    env["HOME"] = home
    cmd = [sys.executable, AUDIT, fx]
    if stock:
        cmd += ["--stock", stock]
    if label:
        cmd += ["--label", label]
    if out:
        cmd += ["-o", out]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)


def _mk_home(td):
    home = os.path.join(td, "home")
    os.makedirs(home, exist_ok=True)
    return home


class TokenAuditLabelTest(unittest.TestCase):
    def test_01_label_output_path(self):
        """正例：--label → md 落 {HOME}/analysis_report/token_audits/label-{label}-*.md，
        不落任何单票目录（批次无归巢目录）。"""
        with tempfile.TemporaryDirectory() as td:
            home = _mk_home(td)
            fx = os.path.join(td, "fx.jsonl")
            _build_fixture(fx)
            r = _run(fx, home, label="morning")
            self.assertEqual(r.returncode, 0, r.stderr)
            hits = glob.glob(os.path.join(
                home, "analysis_report", "token_audits", "label-morning-*.md"))
            self.assertEqual(len(hits), 1, hits)
            # 单票目录零写入（目录扫描被 label 分支短路）
            self.assertEqual(glob.glob(os.path.join(
                home, "analysis_report", "analysis_report-*")), [])

    def test_02_history_label_key(self):
        """正例：报告会话 + --label → history 条目含 label 键且 stock=label。"""
        with tempfile.TemporaryDirectory() as td:
            home = _mk_home(td)
            fx = os.path.join(td, "fx.jsonl")
            _build_fixture(fx, write_report=True)
            r = _run(fx, home, label="close", no_history=False)
            self.assertEqual(r.returncode, 0, r.stderr)
            hist = os.path.join(home, ".cache", "token_audit_history.jsonl")
            entries = [json.loads(x) for x in open(hist, encoding="utf-8") if x.strip()]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["label"], "close")
            self.assertEqual(entries[0]["stock"], "close")   # label 优先于自提码

    def test_03_annotation_and_title(self):
        """正例：混拉会话含自提码 → md 标题=label、自提码行带「未采用」注释。"""
        with tempfile.TemporaryDirectory() as td:
            home = _mk_home(td)
            fx = os.path.join(td, "fx.jsonl")
            _build_fixture(fx, user_text="帮我分析 688048 的盘面")
            r = _run(fx, home, label="morning")
            self.assertEqual(r.returncode, 0, r.stderr)
            md = open(glob.glob(os.path.join(
                home, "analysis_report", "token_audits", "label-morning-*.md"))[0],
                encoding="utf-8").read()
            self.assertIn("# Token 审计 — morning", md)
            self.assertIn("内容自提股票码：688048（未采用：--label 混拉批次，多码不归因单票）", md)

    def test_04_r8_guard_not_loosened(self):
        """护栏正例：--stock 错靶 + --label 并传 → R8 闸仍非零退出、md/历史零写入
        （label 模式禁止错靶豁免——闸只对 --stock 生效，传了就执法）。"""
        with tempfile.TemporaryDirectory() as td:
            home = _mk_home(td)
            fx = os.path.join(td, "fx.jsonl")
            _build_fixture(fx, user_text="帮我分析 688048 的盘面")
            r = _run(fx, home, label="morning", stock="688195", no_history=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("错目标审计拒绝执行", r.stderr)
            self.assertEqual(glob.glob(os.path.join(
                home, "analysis_report", "**", "*.md"), recursive=True), [],
                "错目标 md 必须零写入")
            self.assertFalse(os.path.exists(os.path.join(
                home, ".cache", "token_audit_history.jsonl")), "错目标历史零追加")

    def test_05_label_stock_coexist(self):
        """并存优先级钉死：--label + --stock 并传 → 输出路径归 label 分支，
        标题归 --stock（R8 闸照常执法面）。"""
        with tempfile.TemporaryDirectory() as td:
            home = _mk_home(td)
            fx = os.path.join(td, "fx.jsonl")
            _build_fixture(fx)
            r = _run(fx, home, label="morning", stock="TEST")
            self.assertEqual(r.returncode, 0, r.stderr)
            hits = glob.glob(os.path.join(
                home, "analysis_report", "token_audits", "label-morning-*.md"))
            self.assertEqual(len(hits), 1, hits)
            self.assertIn("# Token 审计 — TEST", open(hits[0], encoding="utf-8").read())

    def test_06_no_label_regression(self):
        """回归极：无 --label → 老路径行为不变（-o 指定 + 注释行不出现）。"""
        with tempfile.TemporaryDirectory() as td:
            home = _mk_home(td)
            fx = os.path.join(td, "fx.jsonl")
            _build_fixture(fx)
            out = os.path.join(td, "out.md")
            r = _run(fx, home, out=out)
            self.assertEqual(r.returncode, 0, r.stderr)
            md = open(out, encoding="utf-8").read()
            self.assertNotIn("混拉批次", md)
            self.assertIn("semantics v3.1", md)


if __name__ == "__main__":
    unittest.main()
