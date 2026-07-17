#!/usr/bin/env python3
"""
test_lhb_northbound_processor.py —— LHB / 北向 processed 纯函数契约测试（v2 深度重构）

断言 `_process_lhb_signals` / `_process_northbound_signals` 的返回形与四情境语义：
  · 真·空(never_listed / no_northbound_data) → status=ok，signals=[]（有效信号，非失败）
  · 拉取失败(_fetch_failed) → status=failed
  · 降级(event_only_summary / top10_trading_activity) → status=ok + 对应 L/N 码
  · 正常 → 编码 signals[]（L1-L5 / N1-N2）+ trend + inflection + aggregates

设计要点（v2）：
  · LHB 时间窗=90天；total_count=90天内上榜次数；seats/daily 均已 90d 过滤
  · 北向=1 季度；holding_ratio_prev/change_qoq/trend_direction 全 null；
    signal_type 不含 foreign_accumulating/foreign_reducing（比例 QoQ 1Q 不可得）
  · signal_type 标量保留（m4/m6/m7 向后兼容）；signals[] 加法式
  · 一致性：偶尔上榜(seats 非空 + recent_count_30d=0)是合法态，不报错不误判

零网络、纯离线（直接喂构造的 raw envelope 给纯函数）。运行见同目录 run_regression.sh。

用法：
    python3 test_lhb_northbound_processor.py        # 或经 run_regression.sh 串联
"""
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta

_ROUTING = Path(__file__).resolve().parents[2] / "financial-data-routing"
sys.path.insert(0, str(_ROUTING))

from runner import _process_lhb_signals, _process_northbound_signals  # noqa: E402


def _d(days_ago):
    """相对今天的 YYYYMMDD 日期（测试确定性）。"""
    return (datetime.now().date() - timedelta(days=days_ago)).strftime("%Y%m%d")


def _codes(p):
    return [s["code"] for s in (p.get("signals") or [])]


# ============================================================
# LHB processor
# ============================================================

class TestLhbProcessor(unittest.TestCase):

    def test_never_listed_is_ok_not_failed(self):
        """真·空(从未上榜) → status=ok/never_listed，非 failed（决策A 核心）。"""
        raw = {"detail_dates": [], "seats": [], "daily": []}
        p = _process_lhb_signals(raw)
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["signal_type"], "never_listed")
        self.assertEqual(p["signals"], [])
        self.assertEqual(p["total_count"], 0)

    def test_fetch_failed(self):
        """双源全挂 → status=failed。"""
        p = _process_lhb_signals({"_fetch_failed": True})
        self.assertEqual(p["status"], "failed")
        self.assertEqual(p["signal_type"], "fetch_failed")

    def test_event_only_daily_present(self):
        """东财无席位但 daily 有 → event_only_summary；institutional_buy_seats=null（非 0）。"""
        raw = {"detail_dates": [], "seats": [],
               "daily": [{"日期": _d(5), "全榜净额_万元": 100.0, "_reason_cat": "游资接力"}]}
        p = _process_lhb_signals(raw)
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["signal_type"], "event_only_summary")
        self.assertIsNone(p["institutional_buy_seats"])
        self.assertIn("L5", _codes(p))

    def test_event_only_throttled_all_empty(self):
        """全空但有限流信号 → 降级 event_only_summary（不误判 never_listed）。"""
        raw = {"detail_dates": [], "seats": [], "daily": [], "_throttled": True}
        p = _process_lhb_signals(raw)
        self.assertEqual(p["signal_type"], "event_only_summary")
        self.assertIn("L5", _codes(p))

    def test_institutional_bullish_L1(self):
        seats = [{"日期": _d(3), "营业部": "机构专用", "净额": 1e8, "类型": "x", "_reason_cat": "机构净买入"},
                 {"日期": _d(3), "营业部": "机构专用", "净额": 5e7, "_reason_cat": "机构净买入"},
                 {"日期": _d(3), "营业部": "机构专用", "净额": 3e7, "_reason_cat": "机构净买入"}]
        raw = {"detail_dates": [_d(3)], "seats": seats, "daily": [{"日期": _d(3)}]}
        p = _process_lhb_signals(raw)
        self.assertEqual(p["status"], "ok")
        self.assertIn("L1", _codes(p))
        self.assertGreaterEqual(p["aggregates"]["inst_buy_seats"], 3)

    def test_hot_money_L2(self):
        seats = [{"日期": _d(2), "营业部": "某某证券股份营业部", "净额": 2e8, "_reason_cat": "游资接力"}]
        raw = {"detail_dates": [_d(2)], "seats": seats, "daily": [{"日期": _d(2)}]}
        p = _process_lhb_signals(raw)
        self.assertIn("L2", _codes(p))

    def test_frequent_and_trend(self):
        """90天内≥3次上榜 → L3；total_count≥3 → trend 有值。"""
        dates = [_d(5), _d(15), _d(25), _d(40), _d(60)]
        seats = [{"日期": d, "营业部": "x", "净额": 1e8, "_reason_cat": "游资接力"} for d in dates]
        raw = {"detail_dates": dates, "seats": seats, "daily": [{"日期": d} for d in dates]}
        p = _process_lhb_signals(raw)
        self.assertEqual(p["total_count"], 5)
        self.assertIsNotNone(p["trend"])
        self.assertIn(p["trend"]["direction"], ("heating", "cooling", "flat"))
        self.assertEqual(p["trend"]["window_days"], 90)
        self.assertIn("L3", _codes(p))

    def test_low_freq_no_trend(self):
        """total_count<3 → trend/inflection=None（短路，仿 detect_holder_distribution）。"""
        dates = [_d(10), _d(50)]
        seats = [{"日期": d, "营业部": "x", "净额": 1e8, "_reason_cat": "游资接力"} for d in dates]
        raw = {"detail_dates": dates, "seats": seats, "daily": []}
        p = _process_lhb_signals(raw)
        self.assertIsNone(p["trend"])
        self.assertIsNone(p["inflection"])

    def test_occasional_seats_present_recent30_zero_is_legal(self):
        """偶尔上榜（90天内上过、近30天没有）是合法态，不报错不误判失败。"""
        seats = [{"日期": _d(60), "营业部": "x", "净额": 1e8, "_reason_cat": "游资接力"}]
        raw = {"detail_dates": [_d(60)], "seats": seats, "daily": []}
        p = _process_lhb_signals(raw)
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["recent_count_30d"], 0)
        self.assertGreater(p["total_count"], 0)

    def test_signal_type_scalar_preserved(self):
        """signal_type 标量保留（m4/m6/m7 向后兼容，决策B）。"""
        seats = [{"日期": _d(2), "营业部": "x", "净额": 2e8, "_reason_cat": "游资接力"}]
        raw = {"detail_dates": [_d(2)], "seats": seats, "daily": [{"日期": _d(2)}]}
        p = _process_lhb_signals(raw)
        self.assertIn("signal_type", p)
        self.assertIn("severity", p)
        self.assertIn("summary", p)

    def test_aggregates_reason_cat_dist(self):
        seats = [{"日期": _d(2), "营业部": "机构专用", "净额": 1e8, "_reason_cat": "机构净买入"},
                 {"日期": _d(2), "营业部": "y", "净额": 2e8, "_reason_cat": "游资接力"}]
        raw = {"detail_dates": [_d(2)], "seats": seats, "daily": [{"日期": _d(2)}]}
        p = _process_lhb_signals(raw)
        dist = p["aggregates"]["reason_cat_dist"]
        self.assertEqual(dist.get("机构净买入"), 1)
        self.assertEqual(dist.get("游资接力"), 1)


# ============================================================
# Northbound processor（1 季度 · 仅水平信号）
# ============================================================

class TestNorthboundProcessor(unittest.TestCase):

    def test_no_northbound_data_is_ok(self):
        """真·非标的 → status=ok/no_northbound_data，非 failed。"""
        p = _process_northbound_signals({"data_source": "westock", "quarterly_holding": []})
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["signal_type"], "no_northbound_data")
        self.assertEqual(p["signals"], [])

    def test_1q_null_fields(self):
        """1Q：prev/change_qoq/trend_direction 全 null（无法算比例 QoQ）。"""
        raw = {"data_source": "westock", "quarterly_holding": [{"持股比例": 12.0}]}
        p = _process_northbound_signals(raw)
        self.assertIsNone(p["holding_ratio_prev"])
        self.assertIsNone(p["change_qoq"])
        self.assertIsNone(p["trend_direction"])

    def test_strong_foreign_N1(self):
        p = _process_northbound_signals({"data_source": "westock", "quarterly_holding": [{"持股比例": 12.0}]})
        self.assertEqual(p["signal_type"], "strong_foreign_conviction")
        self.assertIn("N1", _codes(p))

    def test_minimal_foreign_N2(self):
        p = _process_northbound_signals({"data_source": "westock", "quarterly_holding": [{"持股比例": 0.3}]})
        self.assertEqual(p["signal_type"], "minimal_foreign")
        self.assertIn("N2", _codes(p))

    def test_moderate_no_signal(self):
        p = _process_northbound_signals({"data_source": "westock", "quarterly_holding": [{"持股比例": 5.0}]})
        self.assertEqual(p["signal_type"], "moderate_foreign")
        self.assertEqual(p["signals"], [])

    def test_no_accumulating_or_reducing(self):
        """1Q 绝不产生 foreign_accumulating/foreign_reducing（流向信号需 2Q）。"""
        for ratio in [0.6, 5.0, 12.0]:
            raw = {"data_source": "westock", "quarterly_holding": [{"持股比例": ratio}]}
            p = _process_northbound_signals(raw)
            self.assertNotIn(p["signal_type"], ("foreign_accumulating", "foreign_reducing"),
                             f"ratio={ratio} 不应产生流向信号")

    def test_top10_fallback(self):
        p = _process_northbound_signals({"data_source": "top10_deal", "top10_fallback": {"count": 3}})
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["signal_type"], "top10_trading_activity")

    def test_fetch_failed(self):
        p = _process_northbound_signals({"_fetch_failed": True})
        self.assertEqual(p["status"], "failed")

    def test_trend_basis_1q(self):
        p = _process_northbound_signals({"data_source": "westock", "quarterly_holding": [{"持股比例": 12.0}]})
        self.assertEqual(p["trend"]["quarters"], 1)
        self.assertEqual(p["trend"]["basis"], "latest_quarter_only")
        self.assertIsNone(p["trend"]["direction"])
        self.assertIsNone(p["inflection"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
