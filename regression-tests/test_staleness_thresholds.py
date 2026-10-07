#!/usr/bin/env python3
"""staleness 阈值契约测试（2026-10-07 假期假阳性修复批）。

背景（002222 国庆实证）：短阈值类（KLINE=5/默认=7 自然日）被长假系统性击穿——
9-30 数据在 10-06 看 6 自然日 > 5，告警「陈旧」但数据实为全局最新（A股国庆闭市
至 10-07）。修复：短阈值类统一 10 自然日（最长闭市 8 天 + 2 边际），无日历依赖、
无本地缓存；macro/financial/季度/龙虎榜不动（60/180/10000 尺度无假期假阳性）。

两极：假期向量（9-30@10-06，6 天 ≤10）不告警；真陈旧向量（9-15@10-06，21 天）
照告且文案带 G72 点名 token `staleness`。now 注入实现可测（缺省=当前时刻，向后兼容）。
"""
import sys
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts" / "lib"))

from quality_checks import compute_staleness, get_staleness_threshold  # noqa: E402
from data_snapshot import DataSnapshot  # noqa: E402

_NOW = datetime(2026, 10, 6, 18, 0, 0)


def _result(latest: str) -> dict:
    return {"status": "ok", "_date_column": "date", "data_full": [{"date": latest}]}


class TestStalenessThresholds(unittest.TestCase):
    def test_01_threshold_table_freeze(self):
        """阈值表冻结：短阈值类=10（闭市 8+边际 2）；长阈值类不动。"""
        self.assertEqual(get_staleness_threshold("stock_zh_a_daily"), 10)
        self.assertEqual(get_staleness_threshold("curl_eastmoney_kline"), 10)
        self.assertEqual(get_staleness_threshold("stock_comment_detail_zlkp_jgcyd_em"), 10)
        self.assertEqual(get_staleness_threshold("some_unknown_api"), 10)  # 默认类同口径
        self.assertEqual(get_staleness_threshold("macro_pmi"), 60)
        self.assertEqual(get_staleness_threshold("stock_financial_abstract"), 180)
        self.assertEqual(get_staleness_threshold("stock_zh_a_gdhs_detail_em"), 180)
        self.assertEqual(get_staleness_threshold("stock_lhb_stock_detail_em"), 10_000)

    def test_02_holiday_no_false_positive(self):
        """正例（假期向量）：9-30 数据在 10-06 看=6 天 ≤10 → 不告警（修复前 6>5 误报）。"""
        self.assertIsNone(DataSnapshot._check_staleness(
            _result("2026-09-30"), max_age_days=10, now=_NOW))

    def test_03_genuinely_stale_still_warns(self):
        """反例（真陈旧必须仍告警——防宽松化换绿）：21 天 >10 → 告警带 G72 token。"""
        warn = DataSnapshot._check_staleness(
            _result("2026-09-15"), max_age_days=10, now=_NOW)
        self.assertIsNotNone(warn)
        self.assertIn("[staleness]", warn)
        self.assertIn("2026-09-15", warn)
        self.assertIn("21 天", warn)
        self.assertIn("阈值 10 天", warn)

    def test_04_boundary_exact(self):
        """边界两极：age==10 不告警（>10 才告）；age==11 告警。"""
        self.assertIsNone(DataSnapshot._check_staleness(
            _result("2026-09-26"), max_age_days=10, now=_NOW))
        self.assertIsNotNone(DataSnapshot._check_staleness(
            _result("2026-09-25"), max_age_days=10, now=_NOW))

    def test_05_compute_staleness_now_injection(self):
        """compute_staleness now 注入：days_old 与 _check_staleness 同口径。"""
        days_old, latest = compute_staleness(
            "stock_zh_a_daily", [{"date": "2026-09-30"}], "date", now=_NOW)
        self.assertEqual(days_old, 6)
        self.assertEqual(latest.strftime("%Y-%m-%d"), "2026-09-30")

    def test_06_default_max_age_backward_compat(self):
        """向后兼容：不传 now 行为不变（用真实当前时刻，极陈旧数据必告警）。"""
        warn = DataSnapshot._check_staleness(_result("2000-01-01"), max_age_days=10)
        self.assertIsNotNone(warn)


if __name__ == "__main__":
    unittest.main()
