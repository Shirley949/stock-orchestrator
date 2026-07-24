#!/usr/bin/env python3
"""
test_latest_extract.py —— 统一 latest_period 信封构造的单测（plan Step 1.3 / 验证 §2）

覆盖：
  1. 6 形态 sort_key 正确性 + 跨形态可比拟（year < month < quarter < day 同年）
  2. 信封 7 核心字段 + summary 可选 + extra 透传（reason/is_forward_looking）
  3. latest_value_from_section 双键兜底（data 优先 / data_full 兜底 / 单键不漏）
  4. 空输入 / 非字典 / 首行非 dict → (None, None)
  5. days_old 新鲜度计算（含 8 位紧凑 sort_key）
  6. period_label 自动 + hint 覆盖

零网络、纯离线。运行：python3 test_latest_extract.py（或经 run_regression.sh 串联）。
"""
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS / "lib"))

import latest_extract as le


class TestSortKey(unittest.TestCase):
    """6 形态 sort_key + 跨形态可比拟。"""

    def test_year(self):
        self.assertEqual(le.to_sort_key("2026", "year"), 20260000)

    def test_month_macro_format(self):
        # 宏观 "%Y年%m月份" 格式（quality_checks.parse_date 支持）
        self.assertEqual(le.to_sort_key("2026年06月份", "month"), 20260600)

    def test_quarter_q1_to_march(self):
        # Q1 (月=3) → 季末月 03
        self.assertEqual(le.to_sort_key("2026-03-31", "quarter"), 20260328)

    def test_quarter_q2_to_june(self):
        self.assertEqual(le.to_sort_key("2026-06-30", "quarter"), 20260628)

    def test_day(self):
        self.assertEqual(le.to_sort_key("2026-03-31", "day"), 20260331)

    def test_event_compact_8digit(self):
        # lhb latest_date "20260708" 8 位紧凑兜底
        self.assertEqual(le.to_sort_key("20260708", "event"), 20260708)

    def test_none_returns_none(self):
        self.assertIsNone(le.to_sort_key(None, "day"))
        self.assertIsNone(le.to_sort_key("2026", None))

    def test_unparseable_returns_none(self):
        self.assertIsNone(le.to_sort_key("not-a-date", "day"))

    def test_cross_form_comparable_same_year(self):
        """同年内 year < month < quarter(Q1) < day。"""
        y = le.to_sort_key("2026", "year")
        m = le.to_sort_key("2026年06月份", "month")
        q = le.to_sort_key("2026-03-31", "quarter")  # 20260328
        d = le.to_sort_key("2026-03-31", "day")       # 20260331
        self.assertLess(y, m)
        self.assertLess(m, 20260600 + 1)  # month 在 06 月
        # quarter Q1 (03月) 应 < month 06月
        q1 = le.to_sort_key("2026-03-31", "quarter")
        m06 = le.to_sort_key("2026年06月份", "month")
        self.assertLess(q1, m06)
        self.assertLess(q, d)  # 季末近似28 < 31


class TestEnvelope(unittest.TestCase):
    """信封构造。"""

    def test_seven_core_fields(self):
        env = le.make_latest_envelope("2026-03-31", "day", "actual", value=128685)
        for k in ("raw_date", "period_type", "period_label", "sort_key",
                  "as_of", "data_class", "value"):
            self.assertIn(k, env, f"缺字段 {k}")
        self.assertEqual(env["value"], 128685)
        self.assertEqual(env["data_class"], "actual")
        self.assertEqual(env["sort_key"], 20260331)
        self.assertEqual(env["period_label"], "2026-03-31")

    def test_summary_optional(self):
        env_no_sum = le.make_latest_envelope("2026", "year", "forecast", value=1.13)
        self.assertNotIn("summary", env_no_sum)
        env_sum = le.make_latest_envelope(
            "2026", "year", "forecast", value=1.13, summary="机构一致预期 EPS 1.13")
        self.assertEqual(env_sum["summary"], "机构一致预期 EPS 1.13")

    def test_extra_passthrough(self):
        """company_guidance reason / is_forward_looking 透传。"""
        env = le.make_latest_envelope(
            "2026-07-15", "event", "forecast",
            value={"predict_type": "预增", "predict_amt_mid": 7450},
            summary="中报预增 53.65%~78.14%",
            reason="核级海绵锆/纳米锆放量+新兴市场开拓",
            is_forward_looking=True,
            report_date="2026-06-30",
        )
        self.assertEqual(env["reason"], "核级海绵锆/纳米锆放量+新兴市场开拓")
        self.assertTrue(env["is_forward_looking"])
        self.assertEqual(env["report_date"], "2026-06-30")

    def test_period_label_hint_overrides(self):
        env = le.make_latest_envelope(
            "2026-07-15", "event", "forecast", value=1,
            period_label_hint="2026中报预增")
        self.assertEqual(env["period_label"], "2026中报预增")

    def test_raw_date_norm_from_datetime(self):
        from datetime import datetime
        env = le.make_latest_envelope(datetime(2026, 3, 31), "day", "actual", value=1)
        self.assertEqual(env["raw_date"], "2026-03-31")


class TestDualFallback(unittest.TestCase):
    """latest_value_from_section 双键兜底（CLAUDE.md 硬规则）。"""

    def test_data_preferred(self):
        sec = {"data": [{"holder_count": 128685}, {"holder_count": 100000}]}
        val, row = le.latest_value_from_section(sec, "holder_count")
        self.assertEqual(val, 128685)  # [0] = 最新
        self.assertEqual(row["holder_count"], 128685)

    def test_data_full_fallback(self):
        """Sina 路径只填 data_full，单读 data 会漏——双兜底必须命中。"""
        sec = {"data_full": [{"合同负债": 5.39e8}, {"合同负债": 4e8}]}
        val, row = le.latest_value_from_section(sec, "合同负债")
        self.assertEqual(val, 5.39e8)

    def test_data_preferred_over_data_full(self):
        """两键都有时取 data（主路径）。"""
        sec = {"data": [{"x": 1}], "data_full": [{"x": 99}]}
        val, _ = le.latest_value_from_section(sec, "x")
        self.assertEqual(val, 1)

    def test_empty_section(self):
        self.assertEqual(le.latest_value_from_section({}, "x"), (None, None))
        self.assertEqual(le.latest_value_from_section({"data": []}, "x"), (None, None))

    def test_non_dict_section(self):
        self.assertEqual(le.latest_value_from_section(None, "x"), (None, None))
        self.assertEqual(le.latest_value_from_section("not a dict", "x"), (None, None))

    def test_first_row_non_dict(self):
        self.assertEqual(le.latest_value_from_section({"data": [None]}, "x"), (None, None))

    def test_dual_fallback_disabled(self):
        """dual_fallback=False 时只读 data（即使 data_full 有值）。"""
        sec = {"data_full": [{"x": 99}]}
        self.assertEqual(le.latest_value_from_section(sec, "x", dual_fallback=False),
                         (None, None))


class TestDaysOld(unittest.TestCase):
    """freshness 计算（G32/G33/company_guidance 用）。"""

    def test_compact_8digit_sort_key(self):
        # lhb latest_date sort_key=20200622（300408 2219d 旧）
        d = le.days_old(20200622, as_of="2026-07-20")
        self.assertGreater(d, 2000)  # ~2219

    def test_recent(self):
        d = le.days_old(20260708, as_of="2026-07-20")
        self.assertEqual(d, 12)

    def test_none_sort_key(self):
        self.assertIsNone(le.days_old(None))

    def test_year_form_sort_key(self):
        # year sort_key=YYYY0000 → 补 0000 → 1月1日
        d = le.days_old(20230000, as_of="2026-07-20")
        self.assertGreater(d, 1000)


class TestPeriodLabel(unittest.TestCase):
    def test_quarter_label(self):
        self.assertEqual(le.make_period_label("2026-03-31", "quarter"), "2026Q1")
        self.assertEqual(le.make_period_label("2026-06-30", "quarter"), "2026Q2")

    def test_month_label(self):
        self.assertEqual(le.make_period_label("2026年06月份", "month"), "2026年6月")

    def test_hint_overrides(self):
        self.assertEqual(le.make_period_label("2026", "year", hint="2027E"), "2027E")

    def test_none_raw(self):
        self.assertEqual(le.make_period_label(None, "day"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
