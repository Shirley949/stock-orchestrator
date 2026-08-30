# -*- coding: utf-8 -*-
"""R10 verify_doc_src_paths 两极自测（failure-family 机制层）：正例反例各亲见 True/False。

覆盖：好路径 0 error / 坏路径 error+exit 1 / websearch 跳过 / 无前缀合法 scene /
散文占位符 `<路径>` 跳过 / 条件性标注降级 WARN / dot-split 数值段语义镜像 G21。
"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import verify_doc_src_paths as V  # noqa: E402

SNAP = {"s11_peer": {"data": {"items": [{"x": 1}]}}, "s4_technical": {"data": {"chip": {"avg": 1}}}}


def _scan(doc_text, snaps=None):
    """临时文档 + 快照列表 → (errors, warns)。"""
    snaps = snaps or [("mini.json", SNAP)]
    errors, warns = [], []
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
        f.write(doc_text)
        p = f.name
    try:
        V.scan_doc(p, snaps, errors, warns)
    finally:
        os.unlink(p)
    return errors, warns


class ResolveSemantics(unittest.TestCase):
    def test_resolve_mirrors_g21_dot_split(self):
        self.assertIsNotNone(V.resolve(SNAP, "s11_peer.data.items"))        # list 止步父键
        self.assertIsNotNone(V.resolve(SNAP, "s4_technical.data.chip.avg"))
        self.assertIsNone(V.resolve(SNAP, "s11_peer.data.items[0]"))        # [] 记法不解析
        self.assertIsNone(V.resolve(SNAP, "s11_peer.data.items.0.x"))       # .0 非本例键


class TwoPoleScan(unittest.TestCase):
    def test_good_path_zero_error(self):
        e, w = _scan("结论 [src: snapshot.s11_peer.data.items] 支撑。\n")
        self.assertEqual((len(e), len(w)), (0, 0))

    def test_bad_path_errors(self):
        e, w = _scan("结论 [src: snapshot.s11_peer.data.items.metrics] 必挂。\n")
        self.assertEqual(len(e), 1)
        self.assertIn("items.metrics", e[0])
        self.assertEqual(len(w), 0)

    def test_websearch_skipped(self):
        e, w = _scan("补充 [src: websearch 目标价 一致预期] 非快照路径。\n")
        self.assertEqual((len(e), len(w)), (0, 0))

    def test_bare_scene_legal(self):
        e, _ = _scan("锚 [src: s4_technical.data.chip.avg] 无前缀合法 scene。\n")
        self.assertEqual(len(e), 0)
        e, _ = _scan("锚 [src: s4_technical.data.nokey] 坏路径。\n")
        self.assertEqual(len(e), 1)

    def test_placeholder_prose_skipped(self):
        e, w = _scan("统一写 `[src: snapshot.<路径>]` 前缀最稳。\n")
        self.assertEqual((len(e), len(w)), (0, 0))

    def test_conditional_annotation_downgrades(self):
        e, w = _scan("报告引 `[src: snapshot.web_research_findings.data.items]`（仅当写回成功、场景已存在）。\n")
        self.assertEqual(len(e), 0)
        self.assertEqual(len(w), 1)

    def test_multi_snapshot_any_resolves(self):
        snaps = [("a.json", {"x": 1}), ("b.json", {"y": 1})]
        e, _ = _scan("锚 [src: snapshot.y]。\n", snaps)                     # 仅 b 可解析 → 过
        self.assertEqual(len(e), 0)
        e, _ = _scan("锚 [src: snapshot.z]。\n", snaps)                     # 两档全不通 → error
        self.assertEqual(len(e), 1)
        self.assertIn("2 份快照全不通", e[0])


class CliExitCode(unittest.TestCase):
    def test_cli_exit_codes(self):
        """正例 exit 0（真文档树+冻结金票，坏路径=0 基线）；反例 exit 1（注入坏路径文档）。"""
        r = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "verify_doc_src_paths.py")],
                           capture_output=True, text=True, timeout=120)
        self.assertIn("坏路径 0", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout[-400:])
        with tempfile.TemporaryDirectory() as td:
            open(os.path.join(td, "bad.md"), "w", encoding="utf-8").write(
                "x [src: snapshot.definitely.not.here]\n")
            r2 = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "verify_doc_src_paths.py"),
                                 "--doc-root", td], capture_output=True, text=True, timeout=120)
            self.assertEqual(r2.returncode, 1)
            self.assertIn("definitely.not.here", r2.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
