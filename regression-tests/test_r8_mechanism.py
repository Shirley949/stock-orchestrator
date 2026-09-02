# -*- coding: utf-8 -*-
"""R8 机制档两极自测（failure-family 2026-08-30）：precheck exit 3 / verify_gates 快照读不到
exit 1 / update_checklist 未知 cid 硬闸。三处共同主题=「静默降级通道」改 fail-fast，
每处正例（正常流不受影响）反例（错误流必拦）各一。
"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"

# 可通过 precheck 的最小 A 快照（核心场景 ok + 收单 ≥4）
OK_SNAP = {
    "mode": "A",
    "s1_financial": {"data": {"income_statement": {"status": "ok", "data": [{"x": 1}] * 8},
                              "balance_sheet": {"status": "ok", "data": [{"合同负债": 1.0}]},
                              "segment_composition": {"status": "ok", "dimension_status": {}}}},
    "s2_quote_kline": {"data": {"kline": {"status": "ok"}}},
    "s5_events": {"data": {"news": {"status": "ok"}}},
    "s10_checklist": {"completed": 12, "total": 12, "missing": []},
}


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


class PrecheckExit3(unittest.TestCase):
    def test_poles(self):
        with tempfile.TemporaryDirectory() as td:
            clean = os.path.join(td, "clean.json")
            warn = os.path.join(td, "warn.json")
            json.dump(OK_SNAP, open(clean, "w"))
            json.dump({**OK_SNAP, "_warnings": ["sina kline 限流，已降级"]}, open(warn, "w"))
            # 正例：无 _warnings → exit 0 干净通过
            r = _run([sys.executable, str(SCRIPTS / "precheck.py"), clean])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("✅ 数据预检通过", r.stderr)
            # 反例：_warnings 非空 → ⚠️有条件通过 + exit 3（不再混进 exit 0）
            r3 = _run([sys.executable, str(SCRIPTS / "precheck.py"), warn])
            self.assertEqual(r3.returncode, 3, r3.stderr)
            self.assertIn("⚠️ 有条件通过", r3.stderr)
            self.assertIn("_warnings=1", r3.stderr)


class VerifyGatesSnapshotHardFail(unittest.TestCase):
    def test_poles(self):
        with tempfile.TemporaryDirectory() as td:
            rep = os.path.join(td, "r.md")
            snap = os.path.join(td, "s.json")
            out = os.path.join(td, "o.json")
            # F3 mtime 闸要求报告 mtime ≥ 快照：先写快照后写报告（写序即合同）
            json.dump(OK_SNAP, open(snap, "w"))
            open(rep, "w", encoding="utf-8").write("# 报告\n正文。\n")
            base = [sys.executable, str(SCRIPTS / "verify_gates.py"), "--report", rep,
                    "--quiet", "--no-sidecar", "--output", out]
            # 正例：快照可读 → 不触发硬闸（产出判决 JSON；报告本身 FAIL 与否不是本测对象）
            r = _run(base + ["--data-snapshot", snap])
            self.assertNotIn("拒静默降级", r.stderr)
            self.assertTrue(os.path.exists(out), r.stderr[-300:])
            # 反例①：传了但不存在 → exit 1 + ❌（不再「仅基于报告内容校验」假跑）
            os.unlink(out)
            r1 = _run(base + ["--data-snapshot", os.path.join(td, "nope.json")])
            self.assertEqual(r1.returncode, 1)
            self.assertIn("拒静默降级", r1.stderr)
            self.assertFalse(os.path.exists(out))
            # 反例②：传了但非 JSON → exit 1
            bad = os.path.join(td, "bad.json")
            open(bad, "w").write("{not json")
            r2 = _run(base + ["--data-snapshot", bad])
            self.assertEqual(r2.returncode, 2 if False else 1)   # fail-fast 硬闸 exit 1
            self.assertIn("解析失败", r2.stderr)


class UpdateChecklistUnknownCid(unittest.TestCase):
    def test_poles(self):
        with tempfile.TemporaryDirectory() as td:
            cl = os.path.join(td, "checklist.md")
            snap = os.path.join(td, "s.json")
            open(cl, "w", encoding="utf-8").write(
                "- [ ] <!--c05--> 合同负债\n- [ ] <!--c99--> 未知项\n")
            json.dump(OK_SNAP, open(snap, "w"))
            base = [sys.executable, str(SCRIPTS / "update_checklist.py"),
                    "--file", cl, "--evidence-from", snap]
            # 反例：未知 cid 无映射 → exit 1 且零打勾（旧=静默跳过校验照常打勾）
            r = _run(base + ["--check", "c99"])
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("未知 cid", r.stdout + r.stderr)
            self.assertNotIn("[x]", open(cl, encoding="utf-8").read())   # 零写入
            # 正例：已知 cid + evidence 有效 → 打勾
            r2 = _run(base + ["--check", "c05"])
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            self.assertIn("[x] <!--c05-->", open(cl, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
