#!/usr/bin/env python3
"""kline no_cache 恒真拉契约测试（2026-10-09 trap engine#kline_cache:sameday_postclose_bar_miss 根修）。

背景：KLINE 当日缓存陪跑全天（staleness 粒度=天），盘后重拉仍命中盘中旧 K 线
（fetch_time=12:33 status=cached 实证）→ kline_max 恒=T-1，盘后定格形态同日不可达，
违背 b-trade-sheet §7「当日盘后跑（kline_max=当日）以全天数据定格成交」文档化设计。
根修 = daily_kline no_cache 恒真拉（sina 单次直调稳定 ~0.7s，批量自然间隔无限流实证；
失败退火重试 + THS fallback 双兜底）。

执法面（全离线 monkeypatch，零网络）：
  1. no_cache 两次调用数据变化 → 恒返回新值（不读缓存）
  2. no_cache 不污染 _mem_cache（盘后分片无 kline 键）
  3. 默认路径缓存语义不变（护栏：没把普通缓存改坏）
  4. fail_cache 语义保留（no_cache 失败后同 run 同 key 不重打）
  5. fetch_log 照记（cached 缺席但拉取留痕）
  6. runner 调用点源码契约（stock_zh_a_daily 带 no_cache=True）
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts" / "lib"))
sys.path.insert(0, str(HERE.parent / "scripts"))
from data_snapshot import DataSnapshot  # noqa: E402

ROUTING = HERE.parent.parent / "financial-data-routing"


def _kline_result(last_close, status="ok"):
    today = datetime.now().strftime("%Y-%m-%d")
    return {"status": status, "api_used": "stock_zh_a_daily",
            "params": {"symbol": "sz002202", "adjust": "qfq"},
            "rows": 3, "columns": ["date", "close"], "_date_column": "date",
            "data_full": [{"date": "2026-10-07", "close": 16.0},
                          {"date": "2026-10-08", "close": 16.37},
                          {"date": today, "close": last_close}],
            "_warnings": []}


class KlineNoCacheTest(unittest.TestCase):
    def _mk_ds(self):
        ds = DataSnapshot("TESTKLINE")
        tmp = tempfile.mkdtemp()
        ds._cache_dir = Path(tmp)
        ds._cache_path = Path(tmp) / "TESTKLINE_test.json"
        ds._mem_cache = {}
        ds._fail_cache = {}
        ds._fetch_log = []
        return ds

    def test_01_no_cache_always_fresh(self):
        """正例：数据变化后 no_cache 第二次调用返回新值（不读缓存）。"""
        ds = self._mk_ds()
        ds._call_akshare = lambda api, params, empty_is_ok=False: _kline_result(16.35)
        r1 = ds.fetch_or_cache("stock_zh_a_daily", {"symbol": "sz002202"}, no_cache=True)
        self.assertEqual(r1["status"], "ok")
        self.assertEqual(r1["data_full"][-1]["close"], 16.35)
        ds._call_akshare = lambda api, params, empty_is_ok=False: _kline_result(999.0)
        r2 = ds.fetch_or_cache("stock_zh_a_daily", {"symbol": "sz002202"}, no_cache=True)
        self.assertEqual(r2["status"], "ok")
        self.assertEqual(r2["data_full"][-1]["close"], 999.0, "no_cache 必须返回新拉值")

    def test_02_no_cache_no_pollution(self):
        """正例：no_cache 不写 _mem_cache（同日盘后分片无 kline 键）。"""
        ds = self._mk_ds()
        ds._call_akshare = lambda api, params, empty_is_ok=False: _kline_result(16.35)
        ds.fetch_or_cache("stock_zh_a_daily", {"symbol": "sz002202"}, no_cache=True)
        self.assertEqual(ds._mem_cache, {})

    def test_03_default_cache_semantics_unchanged(self):
        """护栏：默认（无 no_cache）路径缓存读写原样——第二次命中返回 cached 旧值。"""
        ds = self._mk_ds()
        ds._call_akshare = lambda api, params, empty_is_ok=False: _kline_result(16.35)
        r1 = ds.fetch_or_cache("stock_zh_a_daily", {"symbol": "sz002202"})
        self.assertEqual(r1["status"], "ok")
        ds._call_akshare = lambda api, params, empty_is_ok=False: _kline_result(888.0)
        r2 = ds.fetch_or_cache("stock_zh_a_daily", {"symbol": "sz002202"})
        self.assertEqual(r2["status"], "cached")
        self.assertEqual(r2["data_full"][-1]["close"], 16.35)

    def test_04_fail_cache_retained(self):
        """正例：no_cache 失败后 fail_cache 语义保留（同 run 同 key 不重打限流 API）。"""
        ds = self._mk_ds()
        calls = []

        def failing(api, params, empty_is_ok=False):
            calls.append(1)
            return {"status": "failed", "error": "rate-limited", "_warnings": []}

        ds._call_akshare = failing
        r1 = ds.fetch_or_cache("stock_zh_a_daily", {"symbol": "sz002202"}, no_cache=True)
        self.assertEqual(r1["status"], "failed")
        r2 = ds.fetch_or_cache("stock_zh_a_daily", {"symbol": "sz002202"}, no_cache=True)
        self.assertEqual(r2["status"], "failed")
        self.assertEqual(len(calls), 1, "失败记忆必须短路第二次网络调用")

    def test_05_fetch_log_recorded(self):
        """正例：no_cache 拉取留痕（fetch_log 照记，审计可见）。"""
        ds = self._mk_ds()
        ds._call_akshare = lambda api, params, empty_is_ok=False: _kline_result(16.35)
        ds.fetch_or_cache("stock_zh_a_daily", {"symbol": "sz002202"}, no_cache=True)
        self.assertEqual(len(ds._fetch_log), 1)
        self.assertEqual(ds._fetch_log[0]["api"], "stock_zh_a_daily")
        self.assertEqual(ds._fetch_log[0]["status"], "ok")

    def test_06_runner_callsite_contract(self):
        """源码契约：runner live kline 调用点必须带 no_cache=True（stock_zh_a_daily qfq）。"""
        src = (ROUTING / "runner.py").read_text(encoding="utf-8")
        self.assertIn('"stock_zh_a_daily", {"symbol": _format_daily_symbol(stock_code), "adjust": "qfq"},\n        no_cache=True,',
                      src, "live s2 kline 调用点丢失 no_cache=True（回归=缓存陪跑复发）")


if __name__ == "__main__":
    unittest.main()
