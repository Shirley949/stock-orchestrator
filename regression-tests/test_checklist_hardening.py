#!/usr/bin/env python3
"""test_checklist_hardening.py — P1c checklist 硬化 + 文档去硬编码（2026-09-03）。

retrospective_audit_20260902 提案⑤/议程 E（按 R5 重设计）+ D2/D3/议程 F 写侧：
全部「内联产生真相的命令，不内联真相的当前值」——视图计数（14/18）拒绝写入，
一律「以 --list 输出为准」；capstone 全路径命令行内联（evidence C3：两批各 fumble
一次路径猜成 scripts/）；错码前置核对（evidence D2：错码跑完 18 场景落盘 201KB
后才在 [verify] 行暴露）；失败轮落笔纪律（议程 F 写侧）。

红先绿后：本文件先于落码运行——模式 A/B 生成清单均无 --list/capstone/错码核对
（红证 /tmp/p1c_red_{A,B}.md 实测 0 命中），SKILL.md 硬编码「14 视图」3 处。

跑：python3 test_checklist_hardening.py
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from generate_checklist import generate_checklist  # noqa: E402

SKILL_MD = HERE.parent / "SKILL.md"

# 会腐烂的值禁止成文（G4）：视图计数无论 14 还是 18 都是给下一轮腐烂下订单
_ROTTING_COUNT = re.compile(r"\d+\s*视图")

_CAPSTONE_CMD = ("~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/lib/"
                 "capstone_panorama.py")
_SV_CMD = ("~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/"
           "snapshot_view.py")


def _gen(mode: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        out = f.name
    generate_checklist("深度分析测试股300054", stock_codes="300054",
                       mode=mode, output=out)
    text = Path(out).read_text(encoding="utf-8")
    Path(out).unlink(missing_ok=True)
    return text


class TestChecklistHardening(unittest.TestCase):
    def test_wrong_code_precheck_both_modes(self):
        """D2+裁决：错码前置核对行（runner [verify] 行 × 任务书 × --list 头部 code=）。"""
        for mode in ("A", "B"):
            with self.subTest(mode=mode):
                t = _gen(mode)
                self.assertIn("stock_name", t)
                self.assertIn("--list", t)

    def test_list_command_inline_both_modes(self):
        """议程 E：snapshot_view --list 全路径命令内联 + 「以 --list 输出为准」措辞。"""
        for mode in ("A", "B"):
            with self.subTest(mode=mode):
                t = _gen(mode)
                self.assertIn(_SV_CMD, t)
                self.assertIn("以 --list 输出为准", t)

    def test_capstone_full_path_mode_a(self):
        """议程 E：capstone lib/ 全路径命令行内联进 A 的 m6 capstone 步骤（evidence C3）。"""
        self.assertIn(_CAPSTONE_CMD, _gen("A"))

    def test_write_side_ledger_line_both_modes(self):
        """议程 F 写侧：失败轮关闭且引擎侧未修 → 落 ledger/memory 后再开下一股。"""
        for mode in ("A", "B"):
            with self.subTest(mode=mode):
                t = _gen(mode)
                self.assertIn("ledger/memory", t)

    def test_no_rotting_view_counts(self):
        """G4：checklist 生成物与 SKILL.md 均不得硬编码视图计数（拒绝 14 也拒绝 18）。"""
        for mode in ("A", "B"):
            self.assertIsNone(_ROTTING_COUNT.search(_gen(mode)), mode)
        skill = SKILL_MD.read_text(encoding="utf-8")
        hits = _ROTTING_COUNT.findall(skill)
        self.assertEqual(hits, [], f"SKILL.md 残留视图计数硬编码: {hits}")
        self.assertIn("以 --list 输出为准", skill)


if __name__ == "__main__":
    unittest.main(verbosity=2)
