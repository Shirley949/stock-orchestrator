#!/usr/bin/env python3
"""test_full_archive — full/ 合并存档 + detect_prior_data 复用体系回归（模式B v2 §2.5⑤）。

5 断言（离线纯函数，不碰网络；runner._FULL_ARCHIVE_DIR 打向临时沙箱）：
  1. 存档全量性：_archive_full_snapshot 落盘后顶层场景键 ⊇ snapshot 场景键
  2. 同日复用：detect_prior_data 只复用 >0 阈值场景（valuation）；阈值0高频场景恒重拉
  3. A∪B 合并：同日先 A 后 B 存档，A 场景（s1/s5等）在合并档中存活
  4. cleanup 白名单：clean_dir 只清顶层 *.json，full/ 子目录不受影响（脚本行为快照）
  5. 90 天旧档识别：days_old 正确 + 高频全刷新 + valuation 视阈值（>7d 时也重拉）
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
_ROUTING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "financial-data-routing")
sys.path.insert(0, _ROUTING)

import runner  # noqa: E402


def _scene(name: str, status: str = "ok") -> dict:
    return {"scene": name, "data": {"status": status, "latest_period": None}, "_warnings": []}


class TestFullArchive(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_dir = runner._FULL_ARCHIVE_DIR
        # 沙箱模拟真实结构：<tmp>/full/（_archive_full_snapshot 会 makedirs）
        runner._FULL_ARCHIVE_DIR = os.path.join(self._tmp.name, "full")

    def tearDown(self):
        runner._FULL_ARCHIVE_DIR = self._orig_dir
        self._tmp.cleanup()

    def _archive_path(self, code: str, d: date) -> str:
        return os.path.join(runner._FULL_ARCHIVE_DIR, f"{code}_{d.strftime('%Y%m%d')}.json")

    def test_1_archive_completeness(self):
        """断言1：存档全量性（场景键 ⊇ snapshot 场景键）。"""
        snap = {"mode": "A", "stock_code": "600000", "timestamp": "2026-08-26T10:00:00",
                "s1_financial": _scene("s1_financial"), "s2_quote_kline": _scene("s2_quote_kline"),
                "s5_events": _scene("s5_events"), "lhb": _scene("lhb"),
                "_warnings": ["w1"]}
        path = runner._archive_full_snapshot(snap, "600000")
        self.assertTrue(os.path.exists(path))
        archived = json.load(open(path))
        snap_keys = {k for k in snap if not k.startswith("_")}
        self.assertTrue(snap_keys.issubset(archived.keys()),
                        f"存档缺场景: {snap_keys - set(archived.keys())}")

    def test_2_same_day_reuse_only_lowfreq(self):
        """断言2：同日高频场景恒重拉（阈值0=永不复用），valuation（7d）复用。"""
        today = date.today()
        snap_a = {"mode": "A", "timestamp": today.isoformat(),
                  "s2_quote_kline": _scene("s2_quote_kline"),
                  "valuation_snapshot": _scene("valuation_snapshot"),
                  "s_margin": _scene("s_margin")}
        runner._archive_full_snapshot(snap_a, "600000")
        b_snap = {}
        with mock.patch("sys.stderr"):
            diag = runner.detect_prior_data(b_snap, "600000")
        # 阈值0 的高频场景不复制进 B snapshot（恒重拉）
        self.assertNotIn("s2_quote_kline", b_snap, "高频场景（K线）同日不得复用")
        self.assertNotIn("s_margin", b_snap, "高频场景（融资）同日不得复用")
        # valuation 7d 阈值 → 同日复用 + reused_from 标记
        self.assertIn("valuation_snapshot", b_snap, "valuation 7d 阈值内应复用")
        self.assertEqual(b_snap["valuation_snapshot"]["data"]["reused_from"],
                         f"full/600000_{today.strftime('%Y%m%d')}.json")
        self.assertEqual(diag["days_old"], 0)

    def test_3_ab_union_merge(self):
        """断言3：同日先 A 后 B，合并档 = A∪B 并集（A 场景存活）。"""
        today = date.today()
        snap_a = {"mode": "A", "timestamp": today.isoformat(),
                  "s1_financial": _scene("s1_financial"),
                  "s5_events": _scene("s5_events"),
                  "s2_quote_kline": _scene("s2_quote_kline")}
        runner._archive_full_snapshot(snap_a, "600001")
        snap_b = {"mode": "B", "timestamp": today.isoformat(),
                  "s2_quote_kline": _scene("s2_quote_kline"),   # 覆盖同名键
                  "market_context": _scene("market_context"),
                  "intraday_60min": _scene("intraday_60min")}
        path = runner._archive_full_snapshot(snap_b, "600001")
        merged = json.load(open(path))
        for k in ("s1_financial", "s5_events", "s2_quote_kline",
                  "market_context", "intraday_60min"):
            self.assertIn(k, merged, f"A∪B 合并档缺 {k}")
        self.assertEqual(merged["mode"], "B")   # 本次运行覆盖元数据（场景以并集保真）

    def test_4_cleanup_safeguards_full_dir(self):
        """断言4：cleanup clean_dir 的 glob 只匹配顶层 *.json，full/ 子目录天然豁免。"""
        import glob
        today = date.today()
        runner._archive_full_snapshot({"mode": "B", "timestamp": today.isoformat()}, "600002")
        # 模拟 clean_dir 语义：$dir/*.json 不跨目录（cleanup_stale_cache.sh 清 skill-snapshots 顶层）
        top_level = glob.glob(os.path.join(self._tmp.name, "*.json"))
        full_level = glob.glob(os.path.join(self._tmp.name, "full", "*.json"))
        self.assertFalse(any("full" in p for p in top_level),
                         "clean_dir glob 会误伤 full/ —— 契约破坏")
        self.assertGreater(len(full_level), 0, "full/ 应有存档")

    def test_5_stale_archive_identification(self):
        """断言5：90 天旧档识别 + 高频全刷新 + valuation 超阈值也重拉。"""
        old = date.today() - timedelta(days=90)
        snap_old = {"mode": "A", "timestamp": old.isoformat(),
                    "s2_quote_kline": _scene("s2_quote_kline"),
                    "valuation_snapshot": _scene("valuation_snapshot"),
                    "classification": {"primary_type": "周期股"}}
        # 手工写旧档（文件名带旧日期；_archive_full_snapshot 用 now() 命名，这里直接构造）
        os.makedirs(runner._FULL_ARCHIVE_DIR, exist_ok=True)
        with open(self._archive_path("600003", old), "w", encoding="utf-8") as f:
            json.dump(snap_old, f, ensure_ascii=False)
        b_snap = {}
        with mock.patch("sys.stderr"):
            diag = runner.detect_prior_data(b_snap, "600003")
        self.assertEqual(diag["days_old"], 90, "90 天旧档 days_old 识别错误")
        self.assertEqual(diag["archive_mode"], "A")
        # 90 天 > 7 天阈值 → valuation 也重拉；高频全部重拉 → 无任何场景被复制
        self.assertEqual(b_snap, {}, "90 天旧档不得复制任何场景（classification 由实时分类器提供）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
