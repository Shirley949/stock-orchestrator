#!/usr/bin/env python3
"""test_verify_banner.py — 横幅三分前缀 + get_profile fail-loud（P0 2026-09-03）。

不变式：✅ 当且仅当 verdict=PASS 且 n_fail（失败+错误）=0；软过打 ⚠️、硬败打 🔴。
retrospective_audit_20260902：批2 会话读横幅只计硬 FAIL，G11 软过被 ✅ 前缀中和
（「只有 G71」误报）——先修可见性，阈值语义变更另行预申报。
fail-loud：未知 profile 名 SystemExit（静默 fallback=执法面变脸+sidecar 失真潜伏雷）。
跑：python3 test_verify_banner.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import verify_gates  # noqa: E402
from gate_definitions import PROFILES, get_profile  # noqa: E402


class TestBannerThreeWay(unittest.TestCase):
    def test_clean_pass(self):
        line = verify_gates._banner_line("PASS", 0, 2)
        self.assertTrue(line.startswith("✅"), line)
        self.assertIn("失败 0", line)

    def test_soft_pass_warns(self):
        """软过（残留未过 gate 但 verdict=PASS）必须 ⚠️ 且携带残留数。"""
        line = verify_gates._banner_line("PASS", 2, 2)
        self.assertTrue(line.startswith("⚠️"), line)
        self.assertIn("2", line)
        self.assertNotIn("✅", line)

    def test_hard_fail(self):
        line = verify_gates._banner_line("FAIL", 3, 2)
        self.assertTrue(line.startswith("🔴"), line)

    def test_invariant_green_iff_zero(self):
        """核心不变式：✅ ⇔ verdict=PASS 且 n_fail=0（两极全枚举验证）。"""
        for verdict in ("PASS", "FAIL"):
            for n in (0, 1, 2, 5):
                line = verify_gates._banner_line(verdict, n, 2)
                self.assertEqual(line.startswith("✅"),
                                 verdict == "PASS" and n == 0, line)


class TestProfileFailLoud(unittest.TestCase):
    def test_unknown_profile_exits(self):
        """未出名（拼错形态）→ SystemExit，不返回 full 配置。"""
        with self.assertRaises(SystemExit):
            get_profile("quick")  # 漏 profile_ 前缀的真实拼错形态

    def test_known_profiles_resolve(self):
        for name in sorted(PROFILES):
            prof = get_profile(name)
            self.assertIn("gates", prof)
            self.assertIn("fail_threshold", prof)


if __name__ == "__main__":
    unittest.main(verbosity=2)
