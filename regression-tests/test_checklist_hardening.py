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

    def test_phase_protocols_pointer(self):
        """T1 下沉批：phase-protocols.md 在仓且被 SKILL.md 指名（断链=红）。"""
        ref = HERE.parent / "references" / "phase-protocols.md"
        self.assertTrue(ref.is_file(), f"phase-protocols.md 缺失: {ref}")
        self.assertIn("phase-protocols.md", SKILL_MD.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# extract_position 多票 prompt 熔断（trap engine#checklist:extract_position_multi_prompt，
# 2026-10-09 close3 批实证：12 票整段 prompt 下每票清单都首位捕获 603993 的仓位）
# ---------------------------------------------------------------------------
from generate_checklist import extract_position  # noqa: E402

# close3 批真实原文形态（首位=603993，含全角小数点 52。85/29。63）
_MULTITICKET_PROMPT = (
    "洛阳钼业603993（仓位2500@17.32）,工业富联601138（仓位700@52。85）,"
    "三祥新材603663（仓位200@29。63）,博迁新材605376（仓位300@130.42）,"
    "特变电工600089（仓位2200@19.36）,水晶光电002273（仓位600@24.42）,"
    "昊华科技600378（仓位500@42.69）,领益智造002600（仓位1200@12.29）,"
    "星源材质300568（仓位600@15.72）,新易盛300502（仓位100@393.1）,"
    "铜冠铜箔301217（仓位200@98.67）,金风科技002202（仓位1300@22.72）"
)


class ExtractPositionMultiPromptTest(unittest.TestCase):
    """多票 prompt 禁首位猜测：熔断可观测 + 全角小数点归一 + --position 显式通道。"""

    def test_multiticket_returns_ambiguous(self):
        """反例：12 处仓位段 → ambiguous 熔断值，绝不返回首位数字。"""
        pos = extract_position(_MULTITICKET_PROMPT)
        self.assertEqual(pos.get("ambiguous"), 12)
        self.assertNotIn("shares", pos)

    def test_multiticket_checklist_fuses_no_position_line(self):
        """反例：多票 prompt 生成的 B 清单带 🚨 熔断行且零 --position 命令行（宁空仓不错仓）。"""
        md = generate_checklist(_MULTITICKET_PROMPT, stock_codes="300502", mode="B")
        self.assertIn("🚨 多票 prompt 熔断", md)
        # 命令续行形态（两空格缩进）必须缺席；熔断/双态提示文案里的 "--position \"shares=N" 指引文本不在此列
        self.assertNotIn('\n  --position "shares=', md)
        self.assertNotIn("shares=2500,cost=17.32", md)  # 首位捕获不复活（close3 受害形态）

    def test_fullwidth_decimal_normalized(self):
        """反例：全角句号小数（52。85）归一为 52.85，禁静默截断成 52。"""
        pos = extract_position("工业富联 仓位700@52。85")
        self.assertEqual(pos.get("shares"), 700)
        self.assertEqual(pos.get("cost"), 52.85)

    def test_single_ticket_still_resolves(self):
        """正例：单票 prompt 原文检出路径不回退（shares/cost 正解 + 清单带检出行）。"""
        pos = extract_position("模式B盘中分析 300502 仓位100@393.1")
        self.assertEqual(pos, {"shares": 100, "cost": 393.1})
        md = generate_checklist("模式B盘中分析 300502 仓位100@393.1",
                                stock_codes="300502", mode="B")
        self.assertIn("仓位已从原文检出：shares=100 cost=393.1", md)
        self.assertIn('--position "shares=100,cost=393.1"', md)

    def test_explicit_position_bypasses_parsing(self):
        """正例：--position 显式直传 → 显式传入行 + 直传 flag（多票批跑唯一免熔断通道）。"""
        md = generate_checklist("模式B盘中分析 300502", stock_codes="300502", mode="B",
                                explicit_position="shares=100,cost=393.1")
        self.assertIn("仓位已显式传入：shares=100,cost=393.1", md)
        self.assertIn('--position "shares=100,cost=393.1"', md)
        self.assertNotIn("仓位已从原文检出", md)

    def test_bad_explicit_position_shape_exits(self):
        """反例：--position 坏形态 CLI exit 1（确定性输入走确定性通道，坏了必须响）。"""
        import subprocess
        script = HERE.parent / "scripts" / "generate_checklist.py"
        r = subprocess.run(
            [sys.executable, str(script), "--user-prompt", "盘中分析 测试股",
             "--stock-codes", "300054", "--mode", "B",
             "--position", "shares=100 cost=393.1"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("形态非法", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
