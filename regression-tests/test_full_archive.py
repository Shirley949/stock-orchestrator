#!/usr/bin/env python3
"""test_full_archive — full/ 合并存档 + detect_prior_data 复用体系回归（模式B v2 §2.5⑤）。

6 断言（离线纯函数，不碰网络；runner._FULL_ARCHIVE_DIR 打向临时沙箱）：
  1. 存档全量性：_archive_full_snapshot 落盘后顶层场景键 ⊇ snapshot 场景键
  2. 同日复用：低频按各自阈值复用（valuation 7d / s_margin 0=仅同日）；高频5场景恒重拉
     （2026-08-26 用户指令扩容：时间不敏感数据吃 A 档免限流——s_margin T-1 发布当日不变）
  3. A∪B 合并：同日先 A 后 B 存档，A 场景（s1/s5等）在合并档中存活
  4. cleanup 白名单：clean_dir 只清顶层 *.json，full/ 子目录不受影响（脚本行为快照）
  5. 90 天旧档识别：days_old 正确 + 高频全刷新 + valuation>7d 重拉；静态 classification 复用
  6. s1 深度校验两极：A 档三表真数据复用 / B 档 SEGMENTSV 全failed骨架重拉（2026-08-26）
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
        """断言2：同日低频按各自阈值复用（valuation 7d / s_margin 0=仅同日），高频5场景恒重拉。"""
        today = date.today()
        snap_a = {"mode": "A", "timestamp": today.isoformat(),
                  "s2_quote_kline": _scene("s2_quote_kline"),
                  "s3_fund_flow": _scene("s3_fund_flow"),          # 高频代表：盘中资金流
                  "valuation_snapshot": _scene("valuation_snapshot"),
                  "s_margin": _scene("s_margin")}
        runner._archive_full_snapshot(snap_a, "600000")
        b_snap = {}
        with mock.patch("sys.stderr"):
            diag = runner.detect_prior_data(b_snap, "600000")
        # 盘中价在变的高频场景同日也不复用
        for hf in ("s2_quote_kline", "s3_fund_flow", "market_context", "intraday_60min", "s4_technical"):
            self.assertNotIn(hf, b_snap, f"高频场景 {hf} 同日不得复用")
        # s_margin 融资余额 T-1 发布、当日不变 → 同日复用（0 阈值语义）
        self.assertIn("s_margin", b_snap, "融资余额（T-1 发布，当日不变）同日应复用")
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
        # 90 天 > 7 天阈值 → valuation 重拉；高频全部重拉
        for k in ("s2_quote_kline", "valuation_snapshot"):
            self.assertNotIn(k, b_snap, f"90 天旧档 {k} 应重拉")
        # classification 静态行业归属（3650d 阈值）→ 复用（2026-08-26 用户指令：时间不敏感数据吃 A 档）
        self.assertIn("classification", b_snap, "静态 classification 跨 90 天应复用")
        self.assertEqual(b_snap["classification"]["primary_type"], "周期股")


    def test_6_s1_deep_substance(self):
        """断言6（2026-08-26 用户指令）：s1 深度校验两极——
        A 档三表真数据/主营构成 → 复用；B 档 SEGMENTSV 全failed骨架/failed壳 → 重拉。"""
        today = date.today()

        def _stmt(status="ok", n=2):
            return {"status": status, "source": "ths", "data": [{"报告日": "2026-03-31"}] * n}

        # 极A：A 档 s1 三表真数据 + 三维主营构成 → 复用
        snap_a = {"mode": "A", "timestamp": today.isoformat(),
                  "s1_financial": {"scene": "s1_financial", "_warnings": [], "data": {
                      "income_statement": _stmt(), "balance_sheet": _stmt(), "cash_flow": _stmt(),
                      "segment_composition": {"product": [{"name": "光学", "revenue_ratio": 45}],
                                              "industry": [], "geo": []}}}}
        runner._archive_full_snapshot(snap_a, "600006")
        b_snap = {}
        with mock.patch("sys.stderr"):
            diag = runner.detect_prior_data(b_snap, "600006")
        self.assertIn(next(s for s in diag["reused_scenes"] if s.startswith("s1_financial")),
                      diag["reused_scenes"], f"A 档 s1 应复用: {diag}")
        seg = b_snap["s1_financial"]["data"]["segment_composition"]
        self.assertEqual(seg["product"][0]["name"], "光学")
        # 极B：B 档 SEGMENTSV 全 failed 骨架（300433 实测形态）→ 重拉，不复制空壳
        snap_b = {"mode": "B", "timestamp": today.isoformat(),
                  "s1_financial": {"scene": "s1_financial", "_warnings": [], "data": {
                      "segment_composition": {
                          "schema_version": "2.0",
                          "dimension_status": {d: {"status": "fetch_failed"}
                                               for d in ("product", "industry", "geo")},
                          "product": [], "industry": [], "geo": []}}}}
        runner._archive_full_snapshot(snap_b, "600007")
        b_snap2 = {}
        with mock.patch("sys.stderr"):
            diag2 = runner.detect_prior_data(b_snap2, "600007")
        self.assertNotIn("s1_financial", b_snap2, "SEGMENTSV 骨架不得复用")
        self.assertIn("s1_financial(档内无效壳)", diag2["refreshed_scenes"])
        # 极C：s1 status=failed 整体失败壳 → 重拉
        snap_c = {"mode": "A", "timestamp": today.isoformat(),
                  "s1_financial": {"scene": "s1_financial",
                                   "data": {"status": "failed", "error": "boom"}, "_warnings": []}}
        runner._archive_full_snapshot(snap_c, "600008")
        b_snap3 = {}
        with mock.patch("sys.stderr"):
            runner.detect_prior_data(b_snap3, "600008")
        self.assertNotIn("s1_financial", b_snap3, "failed 壳不得复用")


if __name__ == "__main__":
    unittest.main(verbosity=2)
