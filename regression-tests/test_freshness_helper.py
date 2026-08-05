#!/usr/bin/env python3
"""
test_freshness_helper.py —— 共享 freshness helper 单测（plan Step 5.1）

覆盖 _extract_latest_value + _check_value_freshness（G37/G38/G30#1 数值对齐公共地基）。
复刻 G16 多精度范式，泛化为任意 latest_period 字段。

**核心 bug case（必含）**：户数 snapshot=128685 vs 报告"10.12万"（=101200，stale 值）→
_check_value_freshness 须返 False（catches 户数 stale-value bug，plan 验收 step 5）。

零网络、纯离线。gate 运行时层 fixtures 不在时由本单测兜底 freshness 逻辑。
运行：python3 test_freshness_helper.py（或经 run_regression.sh 串联）。
"""
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS / "lib"))

import gate_definitions as gd


# ============================================================
# _extract_latest_value
# ============================================================

class TestExtractLatestValue(unittest.TestCase):
    """从 latest_period 信封取标量 value（含 dividend 兄弟键回退）。"""

    def test_scalar_value(self):
        # 户数 latest_period.value = 标量 holder_count
        data = {"s8_a_share": {"data": {"shareholder_count": {
            "latest_period": {"value": 128685, "period_label": "2026Q1"}}}}}
        v = gd._extract_latest_value(data, "s8_a_share.data.shareholder_count")
        self.assertEqual(v, 128685.0)

    def test_dict_value_with_key(self):
        # balance_sheet latest_period.value = dict，取子键"合同负债"
        data = {"s1_financial": {"data": {"balance_sheet": {
            "latest_period": {"value": {"合同负债": 858465.2, "货币资金": 4e8}}}}}}
        v = gd._extract_latest_value(data, "s1_financial.data.balance_sheet", "合同负债")
        self.assertAlmostEqual(v, 858465.2)

    def test_close_scalar(self):
        data = {"s2_quote_kline": {"data": {"daily_kline": {
            "latest_period": {"value": 54.07}}}}}
        v = gd._extract_latest_value(data, "s2_quote_kline.data.daily_kline")
        self.assertAlmostEqual(v, 54.07)

    def test_dividend_sibling_key_fallback(self):
        # dividend_history 是裸 list；信封在兄弟键 quote.dividend_latest_period
        data = {"valuation_snapshot": {"data": {"quote": {
            "dividend_history": [{"reportEndDate": "20251231"}],
            "dividend_latest_period": {"value": {"每股股利": 0.12}, "raw_date": "20251231"}}}}}
        v = gd._extract_latest_value(data, "valuation_snapshot.data.quote", "每股股利")
        self.assertAlmostEqual(v, 0.12)

    def test_vacuum_latest_period_none(self):
        # 信号族真空：processed.latest_period = None
        data = {"lhb": {"data": {"processed": {"latest_period": None}}}}
        self.assertIsNone(gd._extract_latest_value(data, "lhb.data.processed"))

    def test_missing_envelope(self):
        self.assertIsNone(gd._extract_latest_value({}, "s8_a_share.data.shareholder_count"))

    def test_non_numeric_value(self):
        data = {"x": {"latest_period": {"value": "N/A"}}}
        self.assertIsNone(gd._extract_latest_value(data, "x"))


# ============================================================
# _check_value_freshness
# ============================================================

class TestCheckValueFreshness(unittest.TestCase):
    """报告是否 grounded snap_value（多精度 + src 豁免 + 真空豁免）。"""

    def test_holder_count_fresh_pass(self):
        """报告含正确值 128685（或 12.87万）→ grounded."""
        report = "## 股东户数\n最新期股东户数 128,685 户，环比+27.1%。"
        self.assertTrue(gd._check_value_freshness(report, 128685, ["股东户数", "户数"]))

    def test_holder_count_fresh_wan_pass(self):
        """报告用"万"单位且对齐 → grounded（12.87万 ×1e4=128700，偏差<1%）。"""
        report = "股东户数 12.87万，环比+27.1%。"
        self.assertTrue(gd._check_value_freshness(report, 128685, ["股东户数", "户数"]))

    def test_holder_count_stale_fail(self):
        """★ 核心 bug case：报告用 stale 值 10.12万（=101200）vs snap 128685 → 不 grounded → False。
        偏差 21% > tol 15%，无 [src:] → FAIL。这正是户数 stale-value bug 的 gate 兜底。"""
        report = "股东户数 10.12万，环比+5%。"
        self.assertFalse(gd._check_value_freshness(report, 128685, ["股东户数", "户数"]))

    def test_holder_count_stale_with_src_pass(self):
        """stale 值但行带 [src:] 溯源 → grounded（精确值交 G21）。"""
        report = "股东户数 10.12万 [src: snapshot.s8_a_share]。"
        self.assertTrue(gd._check_value_freshness(report, 128685, ["股东户数", "户数"]))

    def test_holder_count_not_mentioned_fail(self):
        """snapshot 有值但报告完全没提该字段 → False（未消费）。"""
        report = "## 技术面\nMACD 金叉，量能放大。"
        self.assertFalse(gd._check_value_freshness(report, 128685, ["股东户数", "户数"]))

    def test_vacuum_snap_none_pass(self):
        """snap_value=None（真空豁免）→ True，不强制报告消费。"""
        self.assertTrue(gd._check_value_freshness("无关文本", None, ["股东户数"]))

    def test_close_aligned_pass(self):
        """close=54.07，报告"现价54.07元" → grounded。"""
        self.assertTrue(gd._check_value_freshness("现价 54.07 元，涨2.3%", 54.07, ["现价", "收盘价", "最新价"]))

    def test_close_stale_fail(self):
        """close=54.07，报告引旧值 40.00 → 偏差 35%>15% → False。（50.12 仅偏 7.9%<15% 算对齐）"""
        self.assertFalse(gd._check_value_freshness("现价 40.00 元", 54.07, ["现价", "收盘价"]))

    def test_contract_liab_yi_pass(self):
        """合同负债 snap=858465.2(元)→报告"0.0858亿"或直接"85.8万"对齐 → grounded。
        85.8万 ×1e4=858000 ≈858465（偏差<1%）。"""
        self.assertTrue(gd._check_value_freshness("合同负债 85.8万", 858465.2, ["合同负债"]))

    def test_multiple_lines_one_aligned_pass(self):
        """多行中只要有一行 grounded 即 PASS（哪怕他行用了错值）。"""
        report = "股东户数 10.12万（旧）\n修正：股东户数 128685 户（最新）"
        self.assertTrue(gd._check_value_freshness(report, 128685, ["股东户数", "户数"]))

    def test_tol_boundary(self):
        """偏差恰在 tol 内 → grounded（snap=100，报告 114，偏差 14% < 15%）。"""
        self.assertTrue(gd._check_value_freshness("现价 114 元", 100, ["现价"], tol=0.15))


if __name__ == "__main__":
    unittest.main(verbosity=2)
