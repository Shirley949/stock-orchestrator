# -*- coding: utf-8 -*-
"""G50 公告登记表 severity 一致性 gate 测试（照数据写，防夸大/防编造）。

mirror test_g48 范式：from gate_definitions import check_g50。
三态：空/failed/无登记表→豁免 PASS；登记表码标 critical 须数据真有 critical（夸大 FAIL）；
登记表码须存在于 announcements（编造 FAIL）；一致→PASS；否定语境不误伤。
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
from gate_definitions import check_g50


def _snap(announcements, status="ok"):
    """构造最小 snapshot：s5_events.data.risk_signals.processed.{announcements,status}。"""
    return {"s5_events": {"data": {"risk_signals": {"processed": {"announcements": announcements, "status": status}}}}}


def _reg(rows):
    """渲染 m4 §4.2 公告重要性一览登记表；rows=[(code,name,sev), ...]，critical 加粗。"""
    lines = ["#### 4.2 公告重要性一览", "", "| 码 | 类型 | severity |", "|----|------|----------|"]
    for code, name, sev in rows:
        cc, sc = (f"**{code}**", f"**{sev}**") if sev == "critical" else (code, sev)
        lines.append(f"| {cc} | {name} | {sc} |")
    return "\n".join(lines) + "\n"


ANN_M1_CRIT = [{"code": "M1", "name": "股东减持", "severity": "critical"}]
ANN_M4_WARN = [{"code": "M4", "name": "违规/处罚", "severity": "warning"}]
ANN_MIX = [{"code": "M1", "name": "股东减持", "severity": "critical"},
           {"code": "M4", "name": "违规/处罚", "severity": "warning"},
           {"code": "M9", "name": "对外担保", "severity": "info"}]


class CheckG50SeverityConsistency(unittest.TestCase):
    def test_no_data_exempt(self):
        # announcements 空 / status=failed → 真空豁免
        self.assertTrue(check_g50(_reg([("M1", "减持", "critical")]), _snap([])))
        self.assertTrue(check_g50("任意报告无登记表。", _snap(ANN_M1_CRIT, status="failed")))

    def test_no_registry_section_exempt(self):
        # 数据有公告但报告无登记表小节 → 豁免（presence 归 G30#1，G50 只校验已有登记表）
        self.assertTrue(check_g50("公司基本面良好，盈利稳健。", _snap(ANN_MIX)))

    def test_exaggeration_fail(self):
        # 数据 M4 是 warning（审计变更），登记表却标 critical → 夸大 FAIL
        self.assertFalse(check_g50(_reg([("M4", "违规/处罚", "critical")]), _snap(ANN_M4_WARN)))

    def test_fabrication_fail(self):
        # 数据无 M2，登记表却写 M2 critical → 编造 FAIL
        self.assertFalse(check_g50(_reg([("M2", "股权质押", "critical")]), _snap(ANN_M1_CRIT)))

    def test_consistent_pass(self):
        # 登记表 severity 与数据一致（M1 critical / M4 warning / M9 info）→ PASS
        reg = _reg([("M1", "股东减持", "critical"),
                    ("M4", "违规/处罚", "warning"),
                    ("M9", "对外担保", "info")])
        self.assertTrue(check_g50(reg, _snap(ANN_MIX)))

    def test_warning_not_flagged(self):
        # 登记表标 warning/info 不触发夸大（只查 critical 一致性）→ PASS
        self.assertTrue(check_g50(_reg([("M4", "违规/处罚", "warning")]), _snap(ANN_MIX)))

    def test_negation_not_false_positive(self):
        # 登记表写「非critical」否定语境 → 不误判夸大 PASS
        reg = "#### 4.2 公告重要性一览\n| M4 | 违规 | 非critical（仅warning） |\n"
        self.assertTrue(check_g50(reg, _snap(ANN_M4_WARN)))


if __name__ == "__main__":
    unittest.main()
