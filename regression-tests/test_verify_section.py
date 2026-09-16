#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批0.5 --section 逐章旁路 三 fixture（plan sunny-petting-summit 批0.5 · 红先绿后）：

正例  东材归档报告逐章 --section → 各章 PASS（零假 FAIL）+ 各章覆盖门 ⊆ 终验活跃门
      + 终验 57 门全绿不变（旁路未削弱终验合同）。
反例  缺章报告（删 capstone 章）→ 全文终验仍 FAIL（G30 完整性门未被旁路豁免）。
半章  残段报告 → --partial 结构确认（零门执行，无内容臂假 FAIL）；
      同残段不带 --partial 的 --section 全臂跑 = FAIL（内容缺失该报——--partial 是
      恢复三态表的「残段确认」分路器，不是豁免器）。
机制  锚未命中 exit 2 fail-loud（禁静默全文回退）；--section 不覆写 sidecar（切片验证
      禁污染全文终验真相源）；dispatch 合同形状锁定（final 集 + G30 capstone 适用性）。

引擎真相偏差（相对 plan B-1 表，均已实证、REFACTOR_LOG 挂账）：
  G12/G22 由逐章集移 final——G12=全文局限词计数、G22=跨章合取（分业务措辞 §3.2 +
  segment_composition src 复引 §4/§11），pass 条件横跨章界，逐章跑必假 FAIL。
  G16/G39/G59 加章标题适用锚（满足行分别在 §四订单 / §一分类 / §七估值章）。
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCH = HERE.parent
sys.path.insert(0, str(ORCH / "scripts"))
sys.path.insert(0, str(ORCH / "scripts" / "lib"))

import gate_definitions as gd  # noqa: E402
import verify_gates as vg  # noqa: E402

# fixture 源 = 东材归档报告（plan 批0.5 指定；缺失即红，报错指路）
REP = Path("/home/ubuntu/analysis_report/analysis_report-glm5.3f-东材科技-modeA-601208/"
           "analysis_report_601208_modeA.md")
SNAP = REP.with_name("runner_snapshot_601208_modeA.json")

ANCHORS = ["速览", "一、标的分类", "二、公司概况", "三、财务分析", "四、订单",
           "五、技术面", "六、消息面", "七、估值", "八、机构共识", "九、风险",
           "十、公司治理", "十一、综合研判", "局限性"]

PROFILE_GATES = gd.get_profile("profile_full")["gates"]
DISPATCHED = set(vg.SECTION_ARM_DISPATCH["chapter"]) | set(vg.SECTION_ARM_DISPATCH["snapshot"])


def _section_result(report, anchor, data):
    sl, heading, line_no = vg.locate_section_slice(report, anchor)
    run = vg.section_run_gates(PROFILE_GATES)
    applied = [g for g in run if vg._section_gate_applies(g, sl, heading)]
    r = vg.verify_gates(sl, data, "profile_full",
                        restrict_gates=applied, section_anchor=anchor)
    # 与 CLI 同款：逐章阈值=0（任一 FAIL 即 FAIL）
    if r["failed"] + r["errors"] > 0:
        r["verdict"] = "FAIL"
    return r, applied, (sl, heading, line_no)


@unittest.skipUnless(REP.exists() and SNAP.exists(),
                     f"东材归档 fixture 缺失（{REP}）——归档不可删，缺即红")
class TestVerifySection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.report = REP.read_text(encoding="utf-8")
        cls.data = vg.load_data_snapshot(str(SNAP))

    # ── 正例：逐章零假 FAIL + 覆盖 ⊆ 终验 ──────────────────────────────
    def test_positive_per_chapter_no_spurious_fail(self):
        final_r = vg.verify_gates(self.report, self.data, "profile_full")
        self.assertEqual(final_r["verdict"], "PASS",
                         f"fixture 前提破坏：归档报告终验应全绿（fail={final_r['failed_gates']}）")
        self.assertEqual(final_r["active_gates"], len(PROFILE_GATES))
        for anchor in ANCHORS:
            with self.subTest(anchor=anchor):
                r, applied, _ = _section_result(self.report, anchor, self.data)
                self.assertEqual(r["verdict"], "PASS",
                                 f"『{anchor}』逐章假 FAIL：{r['failed_gates']}")
                self.assertEqual(r["failed_gates"], [])
                # 覆盖门 ⊆ 终验活跃门；final 门永不进逐章
                self.assertTrue(set(applied) <= set(PROFILE_GATES))
                self.assertEqual(set(applied) & set(vg.SECTION_FINAL_ONLY), set())

    # ── 反例：缺章终验仍 FAIL（完整性门未被旁路豁免） ────────────────────
    def test_negative_mutilated_capstone_full_verify_fails(self):
        s = self.report.index("## 十一、综合研判")
        e = self.report.index("## 十二、数据时效")
        mutilated = self.report[:s] + self.report[e:]
        r = vg.verify_gates(mutilated, self.data, "profile_full")
        self.assertEqual(r["verdict"], "FAIL", "缺 capstone 终验必须 FAIL（G30 完整性执法）")
        self.assertIn("G30", r["failed_gates"])

    # ── 半章：残段 --partial 零门结构确认 / 全臂跑该 FAIL ────────────────
    def test_half_chapter_stump_partial_vs_full_arms(self):
        idx = self.report.index("## 五、技术面分析")
        nl1 = self.report.index("\n", idx) + 1
        nl3 = self.report.index("\n", self.report.index("\n", nl1) + 1) + 1
        stump = self.report[:idx] + self.report[idx:nl3]  # §5 标题 + 2 行正文
        # --partial：定位成功 + 明示零门执行（内容臂不跑防假 FAIL）
        sl, heading, line_no = vg.locate_section_slice(stump, "五、技术面")
        self.assertIn("五、技术面分析", heading)
        self.assertLessEqual(len(sl), len(stump))
        # 同残段全臂 --section = FAIL（内容缺失该报，非假信号）
        r, applied, _ = _section_result(stump, "五、技术面", self.data)
        self.assertEqual(r["verdict"], "FAIL",
                         "残段全臂跑应 FAIL（半写状态须暴露）；--partial 才是残段确认通道")
        # CLI --partial：exit 0 + 零门执行明示
        p = subprocess.run(
            [sys.executable, str(ORCH / "scripts" / "verify_gates.py"),
             "--report", str(REP), "--data-snapshot", str(SNAP),
             "--section", "五、技术面", "--partial"],
            capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("零门执行", p.stdout)

    # ── 机制：锚未命中 fail-loud / sidecar 不覆写 / dispatch 合同形状 ────
    def test_mechanics_anchor_miss_sidecar_dispatch(self):
        # 锚未命中 → exit 2 + 显式报错（禁静默全文回退伪造假绿）
        p = subprocess.run(
            [sys.executable, str(ORCH / "scripts" / "verify_gates.py"),
             "--report", str(REP), "--data-snapshot", str(SNAP),
             "--section", "不存在的章锚"],
            capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("章锚未命中", p.stderr)
        # --section 不覆写 sidecar（全文终验真相源归 c70 终验独占）
        sidecar = REP.with_suffix(".verified.json")
        before = sidecar.stat().st_mtime_ns if sidecar.exists() else None
        p = subprocess.run(
            [sys.executable, str(ORCH / "scripts" / "verify_gates.py"),
             "--report", str(REP), "--data-snapshot", str(SNAP),
             "--section", "五、技术面", "--quiet"],
            capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        if before is not None:
            self.assertEqual(sidecar.stat().st_mtime_ns, before,
                             "--section 覆写了 sidecar（切片结果污染全文真相源）")
        # dispatch 合同形状（含批0.5 引擎真相偏差的固化）
        self.assertEqual(sorted(vg.SECTION_FINAL_ONLY),
                         ["G11", "G12", "G21", "G22", "G80"])
        self.assertIn("G30", vg.SECTION_ARM_DISPATCH["chapter"])
        for g in vg.SECTION_FINAL_ONLY:
            self.assertNotIn(g, DISPATCHED)
        # G30 capstone 适用性：capstone 切片 True / 技术面切片 False
        cap, _, _ = vg.locate_section_slice(self.report, "十一、综合研判")
        tech, _, _ = vg.locate_section_slice(self.report, "五、技术面")
        self.assertTrue(vg._section_gate_applies("G30", cap, "十一、综合研判"))
        self.assertFalse(vg._section_gate_applies("G30", tech, "五、技术面"))


if __name__ == "__main__":
    unittest.main()
