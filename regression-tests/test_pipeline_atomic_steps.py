#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批 1（流水架构 v1.1）原子步 checklist fixture（plan sunny-petting-summit 1d）：

N1   序不变量：PHASE_STEPS[A][phase_3] 16 步序 = c60→c_m1→c61→c_d2→c_d3→c62→c63→c64→
     c65→c66→c_d4→c_d5→c67→c68→c_m10→c68b（m6<m9<m7<m8 冻结；c_m10 在 c68 后；c68b 末位）；
     步-锚三列表同序；MODE_MODULE_FILES['A'] JIT 序同源（m9 补注册、m12 末位）。
schema  16 步各有 ④ 锚 + 半章判定 grep 可编译；锚逐一在东材归档报告 locate 命中（fail-loud 面）。
渲染  checklist 含头部三行（原子步纪律）+ 三列表 + $SNAP/$SV/$VG 记号；mode B 产出零 A 面
     标记 + B phase_3 五步 desc 逐字冻结（M-3，B 面零触碰）。
禁词  c68b desc 带速览禁词合同（综合研判/情景/三档/概率/研判）；合成合规速览插顶后
     capstone 定位仍锚 §十一（section_locator 首验签者胜 = 劫持面封闭）。
N8   m6 文档「14 行（11 量化+3 定性）」× 引擎 tally「13 维」口径已互注（核对通过，无修正）。
D1   巡检范围=批 1 站点 6/7/8（新措辞在场+旧措辞零残留）；站点 1-5（c2 系）归批 2，本件不查。
"""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCH = HERE.parent
sys.path.insert(0, str(ORCH / "scripts"))
sys.path.insert(0, str(ORCH / "scripts" / "lib"))

import generate_checklist as gc  # noqa: E402
from skill_dep_graph import MODE_MODULE_FILES  # noqa: E402

EXPECTED_ORDER = ["c60", "c_m1", "c61", "c_d2_safety", "c_d3_growth", "c62", "c63",
                  "c64", "c65", "c66", "c_d4_dividend", "c_d5_governance", "c67",
                  "c68", "c_m10", "c68b"]

REP = Path("/home/ubuntu/analysis_report/analysis_report-glm5.3f-东材科技-modeA-601208/"
           "analysis_report_601208_modeA.md")
SNAP = REP.with_name("runner_snapshot_601208_modeA.json")
CLAUDE_MD = Path("/home/ubuntu/CLAUDE.md")

B_PHASE3_FROZEN = [  # 批 1 前 B phase_3 原文逐字（B 面零触碰锁）
    "m38 核心结论头块（G11 声明后、首章节前；整块照抄 b_head 视图 head_draft_md，数字禁改）",
    "m3 技术面",
    "m6 操作建议",
    "m36 短期多周期共振 + m37 筹码与资金结构",
    "m39 规则 R1-R6"[:0] + "站内声量 T1-B 七维消费 + 总评 surface（m39 规则 R1-R6：非真空维 [src:] 落地、d3 看空同节、引文逐字；G80-B 三臂执法）",
]

A_MARKERS = ["原子步纪律", "步-锚映射", "SNAP=", "SV=", "VG="]


def _render(prompt, mode, out):
    argv = [sys.executable, str(ORCH / "scripts" / "generate_checklist.py"),
            "--user-prompt", prompt, "--mode", mode, "--stock-codes", "601208",
            "--output", str(out)]
    import subprocess
    p = subprocess.run(argv, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return Path(out).read_text(encoding="utf-8")


class TestN1StepOrder(unittest.TestCase):
    def test_phase3_step_order_frozen(self):
        ids = [s["id"] for s in gc.PHASE_STEPS["A"]["phase_3"]]
        self.assertEqual(ids, EXPECTED_ORDER)
        # 关键冻结序：m6 < m9 < m7 < m8；c_m10 在 c68 后；c68b 末位
        for a, b in [("c66", "c_d4_dividend"), ("c_d4_dividend", "c_d5_governance"),
                     ("c_d5_governance", "c67"), ("c67", "c68"), ("c68", "c_m10")]:
            self.assertLess(ids.index(a), ids.index(b), f"{a} 必须先于 {b}")
        self.assertEqual(ids[-1], "c68b")
        self.assertNotIn("c59", ids)  # m12 改 c68b 挪末位

    def test_anchor_table_same_order_and_modules(self):
        anchor_ids = [r[0] for r in gc.PHASE3_STEP_ANCHORS]
        self.assertEqual(anchor_ids, EXPECTED_ORDER)
        # 模块列 × MODE_MODULE_FILES['A'] 同源（JIT 序：模块首现顺序一致）
        jit = [Path(f["path"]).name.split("-")[0] for f in MODE_MODULE_FILES["A"]
               if f.get("load") != "deferred"]
        first_in_step = []
        for _, mod, *_ in gc.PHASE3_STEP_ANCHORS:
            if mod not in first_in_step:
                first_in_step.append(mod)
        self.assertEqual(first_in_step, jit,
                         f"步-锚模块首现序 {first_in_step} ≠ JIT 序 {jit}")

    def test_m9_registered_m12_last(self):
        paths = [f["path"] for f in MODE_MODULE_FILES["A"]]
        self.assertTrue(any("m9-governance.md" in p for p in paths), "m9 须补注册进 A 装载集")
        self.assertTrue(paths[-2].endswith("m12-summary.md"), "m12 写作序末位（m11 deferred 恒最后）")
        self.assertTrue(paths[-1].endswith("m11-gates.md"))


class TestStepAnchorSchema(unittest.TestCase):
    @unittest.skipUnless(REP.exists(), f"东材归档 fixture 缺失（{REP}）")
    def test_anchors_locate_on_archive(self):
        import verify_gates as vg
        report = REP.read_text(encoding="utf-8")
        seen_headings = []
        for sid, mod, layout, sec_anchor, grep_pat in gc.PHASE3_STEP_ANCHORS:
            with self.subTest(step=sid):
                self.assertTrue(sec_anchor, f"{sid} 缺 ④ 锚")
                re.compile(grep_pat)  # 半章判定 grep 可编译
                sl, heading, line_no = vg.locate_section_slice(report, sec_anchor)
                self.assertGreater(line_no, 0)
                seen_headings.append(heading)
        # 终验步无锚（c70/c70b 不在映射表）
        self.assertNotIn("c70", [r[0] for r in gc.PHASE3_STEP_ANCHORS])

    def test_m12_top_insert_note_and_ban(self):
        c68b = next(s for s in gc.PHASE_STEPS["A"]["phase_3"] if s["id"] == "c68b")
        self.assertIn("插顶", c68b["desc"])
        self.assertIn("非 append", c68b["desc"])
        for w in ["综合研判", "情景", "三档", "概率", "研判"]:
            self.assertIn(w, c68b["desc"], f"c68b desc 须带禁词合同（缺 {w}）")


class TestRenderedChecklist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.a_md = _render("分析东材科技601208", "A",
                           str(Path(tempfile.mkdtemp()) / "cl_a.md"))
        cls.b_md = _render("分析东材科技601208", "B",
                           str(Path(tempfile.mkdtemp()) / "cl_b.md"))

    def test_a_has_header_table_notations(self):
        for line in gc.PHASE3_HEADER_LINES:
            self.assertIn(line, self.a_md)
        for sid in EXPECTED_ORDER:
            self.assertIn(f"<!--{sid}-->", self.a_md)
        self.assertIn("### 步-锚映射", self.a_md)
        for marker in ["SNAP=", "SV=", "VG="]:
            self.assertIn(marker, self.a_md)
        self.assertIn("插顶后必经 c70 终验", self.a_md)
        # 三列表 16 行（每步一行）
        table_rows = [ln for ln in self.a_md.split("\n") if re.match(r"^\| \d+ \| c", ln)]
        self.assertEqual(len(table_rows), len(EXPECTED_ORDER))

    def test_b_free_of_a_markers_and_frozen(self):
        for marker in A_MARKERS:
            self.assertNotIn(marker, self.b_md, f"B 面不得出现 A 面标记 {marker}")
        self.assertNotIn("原子步纪律", self.b_md)
        # B phase_3 五步 desc 逐字冻结（B 面零触碰）
        b_phase3 = gc.PHASE_STEPS["B"]["phase_3"]
        self.assertEqual([s["desc"] for s in b_phase3], B_PHASE3_FROZEN)


class TestM12TopInsertEndToEnd(unittest.TestCase):
    SYNTH_TLDR = (
        "## ⚡ 速览（TL;DR）\n\n"
        "**① 值得买吗**：观望（示例措辞，无禁词——不出现综合研判字样，不给三档概率表）。\n\n"
        "**② 面价背离度**：示例句，面 6/10 vs 价 4/10。\n\n---\n\n"
    )

    @unittest.skipUnless(REP.exists() and SNAP.exists(), "东材归档 fixture 缺失")
    def test_top_insert_keeps_capstone_anchor_and_verify_green(self):
        import verify_gates as vg
        from section_locator import locate
        report = REP.read_text(encoding="utf-8")
        data = vg.load_data_snapshot(str(SNAP))
        # 摘除原速览块（L『## ⚡ 速览』→『## 一、』前），模拟 c68b 前状态
        s = report.index("## ⚡ 速览")
        e = report.index("## 一、")
        stripped = report[:s] + report[e:]
        # 合成合规速览插顶：G11 声明行后、首章前
        g11_end = stripped.index("📅 数据截止")
        g11_end = stripped.index("\n", g11_end) + 1
        top_inserted = stripped[:g11_end] + "\n" + self.SYNTH_TLDR + stripped[g11_end:]
        # capstone 定位仍锚 §十一（合成速览无禁词 → 不构成候选，劫持面封闭）
        cap_slice, diag = locate(top_inserted)
        self.assertTrue(diag.startswith("ok@"), f"capstone 定位被劫持/丢失: {diag}")
        self.assertIn("## 十一、综合研判", cap_slice.split("\n")[0])
        # 全文终验不受插顶影响
        r = vg.verify_gates(top_inserted, data, "profile_full")
        self.assertEqual(r["verdict"], "PASS", f"插顶后终验破绿: {r['failed_gates']}")

    @unittest.skipUnless(REP.exists(), "东材归档 fixture 缺失")
    def test_archived_tldr_ban_words_note(self):
        # 归档速览含 1 处『情景』（[m6 §三情景推算] 括注）——禁词合同管新写作、不追改归档；
        # 此用例固化现状防误判：劫持面由 heading 级锚闭死（速览标题永不含锚词）。
        report = REP.read_text(encoding="utf-8")
        block = report[report.index("## ⚡ 速览"):report.index("## 一、")]
        self.assertLessEqual(len(re.findall(r"情景|研判|三档|概率", block)), 1)
        from section_locator import CAPSTONE_HEAD_RE
        self.assertIsNone(CAPSTONE_HEAD_RE.search(block.split("\n")[0]),
                          "速览标题行不得匹配 capstone 锚词")


class TestN8AndD1(unittest.TestCase):
    def test_n8_m6_dimension_reconciliation_documented(self):
        m6 = (Path.home() / ".hermes/skills/stock-analysis/stock-analysis-quality/"
              "references/modules/m6-decision.md").read_text(encoding="utf-8")
        self.assertIn("14 行", m6)
        self.assertIn("11 量化 + 3 定性", m6)
        # 14 表行 × 13 引擎维口径互注（⑭千股千评只入表、不入引擎 advisory）
        self.assertIn("13 维口径", m6)
        self.assertEqual(11 + 3, 14)

    def test_d1_batch1_sites_new_wording_zero_old(self):
        site6 = (ORCH / "scripts" / "generate_checklist.py").read_text(encoding="utf-8")
        site7 = (ORCH / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(CLAUDE_MD.exists())
        site8 = CLAUDE_MD.read_text(encoding="utf-8")
        for name, text, new in [
            ("站点6", site6, "台账=读过≠在context，重读将写章节合法"),
            ("站点7", site7, "台账仅记历史（读过≠在context），重读将写章节合法"),
            ("站点8", site8, "台账仅记历史读过，compact 后重读将写章节合法"),
        ]:
            self.assertIn(new, text, f"{name} 新措辞缺席")
        # 旧措辞零残留（站点 6/7/8 域；REFACTOR_LOG/_research 豁免）
        for name, text in [("站点6", site6), ("站点7", site7), ("站点8", site8)]:
            for old in ["已读项勿重读", "已读勿重读", "勿重读"]:
                self.assertNotIn(old, text, f"{name} 旧措辞残留: {old}")


if __name__ == "__main__":
    unittest.main()
