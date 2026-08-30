# -*- coding: utf-8 -*-
"""G48 待执行/进行中增减持计划消费 gate 三态测试（ST5 programs[] forward 信封）。

mirror test_peer_pipeline.check_g15 范式：from gate_definitions import check_g48。
三态：无活跃 program→豁免 PASS；有活跃+presence→PASS；有活跃+无 presence→FAIL；
反编造（无活跃却写「待执行X%」）→ FAIL；programs 缺失/failed→豁免。
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
from gate_definitions import check_g48


def _snap(programs, status="ok"):
    """构造最小 snapshot：s5_events.data.risk_signals.processed.{programs,status}。"""
    return {"s5_events": {"data": {"risk_signals": {"processed": {"programs": programs, "status": status}}}}}


ACTIVE = [{"direction": "减持", "status": "ongoing", "tier": "实控人",
           "announced_pct_cap": 0.03, "window_start": "2026-05-25", "window_end": "2026-08-22"}]
COMPLETED = [{"direction": "减持", "status": "completed"}]


class CheckG48ThreeState(unittest.TestCase):
    def test_no_programs_exempt(self):
        self.assertTrue(check_g48("近180天无材料级股东变动。", _snap([])))          # empty_is_ok 豁免
        self.assertTrue(check_g48("无待执行计划。", _snap([])))                     # 明说无待执行也 PASS

    def test_only_completed_exempt(self):
        # 全是已完成（影响已释放）→ 豁免，不门禁强制
        self.assertTrue(check_g48("该股东已完成减持，影响已释放。", _snap(COMPLETED)))

    def test_active_with_presence_pass(self):
        for kw in ("待执行", "进行中", "拟减持", "拟增持", "窗口", "计划", "增持", "减持"):
            self.assertTrue(check_g48(f"⏳{kw}：实控人拟减持不超3%。", _snap(ACTIVE)),
                            f"presence 词 {kw} 应 PASS")

    def test_active_without_presence_fail(self):
        # 有活跃计划但报告完全没提任何增减持/计划词 → FAIL
        self.assertFalse(check_g48("公司基本面稳健，盈利能力优秀。", _snap(ACTIVE)))

    def test_fabrication_fail(self):
        # 无活跃计划却声称「待执行 X%」→ 反编造 FAIL
        self.assertFalse(check_g48("⏳待执行减持1.5%悬顶。", _snap(COMPLETED)))
        self.assertFalse(check_g48("待执行增持2%计划。", _snap([])))

    def test_fabrication_narrow_no_false_positive(self):
        # 窄口径：无「待执行」+ 单独 % 不算编造（避免「回购进行中」/估值 PE 15% 误伤）
        self.assertTrue(check_g48("当前 PE 分位 15%。", _snap([])))
        self.assertTrue(check_g48("回购正在进行中。", _snap([])))   # 回购进行中非股东增减持计划

    def test_fragment_scope_r5(self):
        """R5 片段级收窄（2026-08-30，龙磁 300835 假阳性根修）：
        按 |。；;\n 切片段（逗号不切=子句仍算同句），「待执行」+ 数字% 同片段共现才 FAIL。
        """
        # ① 事故句重放：宽表行内 % 与「无待执行」被 | 隔开 → PASS（修复前全文 AND 误杀）
        self.assertTrue(check_g48(
            "| **股东层面风险** | 股东户数单季 +74.32%，散户化；无待执行增减持计划 |", _snap([])))
        # ② 诚实否定句 + 异句 %（PE 分位在别句）→ PASS
        self.assertTrue(check_g48("无待执行增减持计划。当前 PE 分位 15%。", _snap([])))
        # ③ 同片段捏造·逗号子句形态（% 在前）：片段内共现无法辨否定 → 仍 FAIL（反编造不失守）
        self.assertFalse(check_g48("实控人持股 12.5%，无待执行减持计划落地。", _snap([])))
        # ④ 同片段捏造·顺序形态（待执行在前）→ FAIL
        self.assertFalse(check_g48("待执行减持不超过 2% 的计划。", _snap([])))

    def test_missing_or_failed_exempt(self):
        self.assertTrue(check_g48("任意报告", {"s5_events": {"data": {"risk_signals": {}}}}))   # 无 processed
        self.assertTrue(check_g48("任意报告", _snap(None)))                                        # programs 非 list（failed 早退无 programs 键）
        # failed 的真实形态：_process_material_signals 拉取失败早退→processed.status=failed 且无 programs 键
        self.assertTrue(check_g48("任意报告",
                                  {"s5_events": {"data": {"risk_signals": {"processed": {"status": "failed"}}}}}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
