#!/usr/bin/env python3
"""test_g74_exec_shell.py — G74 执行壳消费对拍两极测试。

两极（Gate 修复验证硬规则 1）：反例必 FAIL 证执法臂活，正例必 PASS 证容差/豁免不误伤。
- TestModeGate       A 快照结构性放行（B gate 双保险之二）
- TestMissingArms    缺档两态（未写=PASS / 写了=[数据层] FAIL，fix 零改稿动词）
- TestPfdTolerance   舍入正例 -0.74 vs -0.7354=PASS；全精度=PASS；反例 -0.8/无数值=FAIL
- TestReasonTruth    FAIL reason 四件套（快照真值+路径+L{n}:『原句』+照抄修法，CLAUDE.md 规则5）
- TestActionGloss    今日动作括注 vs end_state.position（一致/不符/缺括注三态）

跑：python3 test_g74_exec_shell.py
"""
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "scripts" / "lib"))

from gate_definitions import GATE_CHECKERS  # noqa: E402

G74 = GATE_CHECKERS["G74"]

_ES = {
    "status": "ok",
    "pfd": {"ratio_5d": -0.7354, "as_of_date": "2026-09-30"},
    "results": {"v33_t11": {"end_state": {"position": "空仓"}}},
}


def _snap(mode="B", es=_ES):
    d = {"mode": mode, "s4_technical": {"data": {}}}
    if es is not None:
        d["s4_technical"]["data"]["execution_shell"] = es
    return d


def _passed(ret):
    return ret if isinstance(ret, bool) else ret.get("passed", True)


def _reasons(ret):
    return [] if isinstance(ret, bool) else list(ret.get("reasons") or [])


class TestModeGate(unittest.TestCase):
    def test_a_snapshot_structural_pass(self):
        # A 快照即使误跑也放行（mode 短路，双保险之二）
        rep = "- PFD（5 日主力净流占比）：-0.9\n- 今日动作：NONE（持仓）"
        self.assertTrue(_passed(G74(rep, _snap(mode="A"))))


class TestMissingArms(unittest.TestCase):
    def test_missing_and_unwritten_pass(self):
        self.assertTrue(_passed(G74("报告无执行壳内容，仅降级披露", _snap(es=None))))

    def test_missing_but_written_fail_datalayer(self):
        ret = G74("- PFD（5 日主力净流占比）：-0.74", _snap(es=None))
        self.assertFalse(_passed(ret))
        rs = _reasons(ret)
        self.assertTrue(any("[数据层]" in r for r in rs))
        # [数据层] fix 不含改稿动词（CLAUDE.md 规则5：fix 不含改稿动词）
        fix_r = next(r for r in rs if "[数据层]" in r)
        for w in ("改为", "改成", "补写", "修改报告", "删除该"):
            self.assertNotIn(w, fix_r, f"[数据层] reason 混入改稿动词: {fix_r}")


class TestPfdTolerance(unittest.TestCase):
    LINE = "- PFD（5 日主力净流占比）：{v}（as-of 2026-09-30；警戒线 -0.1；状态 ok）"

    def test_rounded_view_form_pass(self):
        # 正例：视图渲染舍入形 -0.74 vs 真值 -0.7354（diff=0.0046 ≤ 0.01）
        self.assertTrue(_passed(G74(self.LINE.format(v="-0.74"), _snap())))

    def test_full_precision_pass(self):
        self.assertTrue(_passed(G74(self.LINE.format(v="-0.7354"), _snap())))

    def test_wrong_value_fail(self):
        # 反例：偏差 0.0646 > 0.01
        ret = G74(self.LINE.format(v="-0.8"), _snap())
        self.assertFalse(_passed(ret))

    def test_no_number_fail(self):
        ret = G74("- PFD（5 日主力净流占比）：见视图", _snap())
        self.assertFalse(_passed(ret))
        self.assertIn("照抄快照值", _reasons(ret)[0])


class TestReasonTruth(unittest.TestCase):
    def test_fail_reason_carries_truth_line_and_fix(self):
        rep = "- PFD（5 日主力净流占比）：-0.8（as-of 2026-09-30）"
        r = _reasons(G74(rep, _snap()))[0]
        self.assertIn("-0.7354", r)                       # 快照真值
        self.assertIn("execution_shell.pfd.ratio_5d", r)  # 真值路径
        self.assertIn("L1:『", r)                          # 违规行引用
        self.assertIn("照抄", r)                           # 可照抄修法

    def test_all_arms_reported_not_fail_fast(self):
        # 全量 reasons：PFD 臂 + 动作臂同轮报出（CLAUDE.md 规则7）
        rep = "- PFD（5 日主力净流占比）：-0.8\n- 今日动作：NONE（持仓）"
        rs = _reasons(G74(rep, _snap()))
        self.assertGreaterEqual(len(rs), 2)


class TestActionGloss(unittest.TestCase):
    def test_gloss_match_pass(self):
        rep = "- 今日动作：NONE（空仓） ｜ 触发：窗口 2026-09-30→2026-09-30，最近一笔 0 笔内"
        self.assertTrue(_passed(G74(rep, _snap())))

    def test_gloss_mismatch_fail(self):
        ret = G74("- 今日动作：NONE（持仓）", _snap())
        self.assertFalse(_passed(ret))
        self.assertIn("end_state.position", _reasons(ret)[0])

    def test_no_gloss_fail_with_template(self):
        ret = G74("- 今日动作：NONE", _snap())
        self.assertFalse(_passed(ret))
        self.assertIn("（空仓）", _reasons(ret)[0])

    def test_pfd_wrong_and_gloss_ok_single_arm(self):
        # PFD 反例 + 动作正例：只报 PFD 臂（无误伤）
        rep = "- PFD（5 日主力净流占比）：-0.9\n- 今日动作：NONE（空仓）"
        rs = _reasons(G74(rep, _snap()))
        self.assertEqual(len(rs), 1)
        self.assertIn("PFD", rs[0])


if __name__ == "__main__":
    unittest.main()
