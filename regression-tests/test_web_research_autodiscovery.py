#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v4.1/D3 自动发现契约测试——runner 缺 --accounting 时按约定路径携账（带 24h 窗）。

三场景：A 无约定文件→WARN 执法盲明示；B 窗内账→auto-discovered 携账；
C 窗外陈旧账→排除留痕+WARN（不静默）。自包含合成件（v4-6：禁外部固定路径）。
运行: python3 test_web_research_autodiscovery.py 或 run_regression.sh 契约层
"""
import glob
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTING = HERE.parent.parent / "financial-data-routing"
RUNNER = ROUTING / "runner.py"


class TestAutoDiscovery(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wr_autod_")
        self.items = f"{self.tmp}/items.json"
        json.dump([{"topic": "t1", "value": "v 1", "provider": "exa"}],
                  open(self.items, "w", encoding="utf-8"), ensure_ascii=False)

    def _mk_snapshot(self, path):
        json.dump({"stock_code": "999997", "stock_name": "合成票", "ts": "t",
                   "_warnings": [], "_data_summary": {"fetch_log": [], "total_fetches": 0}},
                  open(path, "w", encoding="utf-8"), ensure_ascii=False)
        return path

    def _run(self, snap):
        return subprocess.run(
            [sys.executable, str(RUNNER), "web_research", "999997",
             "--snapshot", snap, "--items", f"@{self.items}"],
            capture_output=True, text=True)

    def _scene(self, snap):
        return json.load(open(snap, encoding="utf-8")).get("web_research_findings", {}).get("data", {})

    def test_a_no_file_warns_blind_spot(self):
        tdir = "/tmp/999997"
        os.makedirs(tdir, exist_ok=True)
        for f in glob.glob(tdir + "/accounting*.json"):
            os.remove(f)
        snap = self._mk_snapshot(f"{self.tmp}/a.json")
        r = self._run(snap)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("无窗内文件", r.stderr)
        self.assertIn("执法盲", r.stderr)
        self.assertIsNone(self._scene(snap).get("accounting"), "无账不得伪造 accounting")

    def test_b_in_window_autocarried(self):
        tdir = "/tmp/999997"
        os.makedirs(tdir, exist_ok=True)
        acc = f"{tdir}/accounting_x.json"
        json.dump({"raw_n": 5, "kept": 1, "discarded": 4,
                   "caliber_flags": [{"file": "exa_a", "q": 1, "unit": "B", "min": 1, "max": 9}]},
                  open(acc, "w", encoding="utf-8"))
        snap = self._mk_snapshot(f"{self.tmp}/b.json")
        r = self._run(snap)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("auto-discovered", r.stderr)
        self.assertIn(acc, r.stderr, "携账路径须 stderr 留痕")
        acc_scene = self._scene(snap).get("accounting") or {}
        self.assertEqual(acc_scene.get("raw_n_total"), 5)

    def test_c_stale_excluded_with_trace(self):
        tdir = "/tmp/999997"
        os.makedirs(tdir, exist_ok=True)
        for f in glob.glob(tdir + "/accounting*.json"):   # 场景隔离: 清 B 的窗内文件
            os.remove(f)
        acc = f"{tdir}/accounting_stale.json"
        json.dump({"raw_n": 99, "kept": 0, "discarded": 0, "caliber_flags": []},
                  open(acc, "w", encoding="utf-8"))
        old = time.time() - 3 * 86400
        os.utime(acc, (old, old))
        snap = self._mk_snapshot(f"{self.tmp}/c.json")
        r = self._run(snap)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("排除陈旧账", r.stderr)
        self.assertIn(acc, r.stderr, "窗外候选须逐条留痕")
        self.assertIsNone(self._scene(snap).get("accounting"), "窗外账不得携入")


if __name__ == "__main__":
    unittest.main(verbosity=1)
