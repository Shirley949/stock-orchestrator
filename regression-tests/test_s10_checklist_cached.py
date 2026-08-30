#!/usr/bin/env python3
"""test_s10_checklist_cached — check_data_completeness 三态收单语义两极固化（场景十）。

背景（2026-08-27 000657 B 双跑实证）：fetch 层三态 ok|failed|cached，cached=已过新鲜度闸
的当日缓存命中；引擎侧消费统一 in ("ok","cached")。旧代码裸 =="ok" 导致同日二跑起
cached 信封被漏计（daily_kline False），属 B v2 复用管道高频化后的潜伏面。

断言（离线纯函数，不碰网络）：
  1. 正例 ok     → True（原行为不回退）
  2. 正例 cached → True（本次修复面）
  3. 反例 failed → False（不误放行）
  4. 键缺失      → False（不误判）
  5. macro_data 判定点同族：pmi cached → True / ppi failed 不影响
"""

import os
import sys
import unittest

_ROUTING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "financial-data-routing")
sys.path.insert(0, _ROUTING)

import runner  # noqa: E402


def _snap(envelopes: dict) -> dict:
    """envelopes: {scene: {data_key: status}} → 最小 snapshot 形态。"""
    snap = {}
    for scene, kvs in envelopes.items():
        snap[scene] = {"scene": scene,
                       "data": {k: {"status": st} for k, st in kvs.items()},
                       "_warnings": []}
    return snap


class TestS10ChecklistCached(unittest.TestCase):
    def test_ok_true(self):
        """正例：ok 原行为不回退。"""
        c = runner.check_data_completeness(
            _snap({"s2_quote_kline": {"daily_kline": "ok"}}))
        self.assertTrue(c["checks"]["daily_kline"])
        self.assertEqual(c["completed"], 1)

    def test_cached_true(self):
        """核心修复面：cached 必须计为可用（同日二跑即 cached 态）。"""
        c = runner.check_data_completeness(
            _snap({"s2_quote_kline": {"daily_kline": "cached"}}))
        self.assertTrue(c["checks"]["daily_kline"])
        self.assertEqual(c["completed"], 1)

    def test_failed_false(self):
        c = runner.check_data_completeness(
            _snap({"s2_quote_kline": {"daily_kline": "failed"}}))
        self.assertFalse(c["checks"]["daily_kline"])

    def test_missing_false(self):
        c = runner.check_data_completeness(_snap({}))
        self.assertFalse(c["checks"]["daily_kline"])

    def test_macro_same_family(self):
        snap = _snap({"s6_macro": {"pmi": "cached", "ppi": "failed"}})
        c = runner.check_data_completeness(snap)
        self.assertTrue(c["checks"]["macro_data"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
