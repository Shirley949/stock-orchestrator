#!/usr/bin/env python3
"""test_day_cache_lifecycle — 日分片生命周期：live save 落盘+自清 / as-of 不落盘 两极。

执法面（data_snapshot.py save/_sweep_stale_root）：
  正例：live save() 落盘当日分片（payload 含 entries/warnings/fetch_log/date）；
       清扫删非当日形态分片；他票当日分片保留；full/ 与 modeb_ledger/ 子目录豁免。
  反例：as-of 实例 save() 零落盘且不清扫（守卫先 return）；非形态散件
       （A_20240930.json/notes.json）不被自动清扫（形态白名单）；清扫异常容忍。
离线零网络（沙箱 TemporaryDirectory + 实例属性覆写，范式照 test_full_archive.py；
构造用虚构票号——__init__ 在属性覆写前只对真实缓存目录做 exist_ok mkdir+假码空读，零副作用）。
运行：python3 test_day_cache_lifecycle.py
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "scripts" / "lib"))

from data_snapshot import DataSnapshot  # noqa: E402

FAKE = "999981"   # 虚构票号：避开真实缓存分片的票码空间


def _mk_ds(as_of=None, sandbox=None):
    """构造 DataSnapshot 后把缓存路径整体打进沙箱。"""
    ds = DataSnapshot(FAKE, as_of=as_of)
    ds._cache_dir = Path(sandbox)
    ds._cache_path = ds._cache_dir / f"{FAKE}_{ds._today}.json"
    ds._mem_cache = {}
    ds._warnings = []
    ds._fetch_log = []
    return ds


def _shard(sandbox, code, yyyymmdd):
    p = Path(sandbox) / f"{code}_{yyyymmdd}.json"
    p.write_text("{}", encoding="utf-8")
    return p


class _SandboxBase(unittest.TestCase):
    """沙箱底座：预置旧日期/昨日形态分片 + 他票今日分片 + 散件 + 白名单子目录。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.sb = self._tmp.name
        self.yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        self.today = datetime.now().strftime("%Y%m%d")
        self.old_shard = _shard(self.sb, "888002", "20240930")
        self.yesterday_shard = _shard(self.sb, "888001", self.yesterday)
        self.today_other = _shard(self.sb, "888003", self.today)
        self.stray_a = _shard(self.sb, "A", "20240930")       # 非形态散件（A_*.json）
        sub = Path(self.sb) / "full"
        sub.mkdir()
        self.full_file = sub / "888001_20260101.json"
        self.full_file.write_text("{}", encoding="utf-8")
        led = Path(self.sb) / "modeb_ledger" / "888001"
        led.mkdir(parents=True)
        self.ledger_file = led / "modeb_decisions.jsonl"
        self.ledger_file.write_text('{"date": "2026-01-01"}\n', encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()


class TestLiveSaveAndSweep(_SandboxBase):
    """正例：live save 落盘 + 自清非当日形态片 + 白名单面全保留。"""

    def test_01_live_save_persists_and_sweeps(self):
        ds = _mk_ds(sandbox=self.sb)
        ds._mem_cache = {"abc123def456": {"status": "ok"}}
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ds.save()
        self.assertTrue(ds._cache_path.exists())
        payload = json.loads(ds._cache_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["stock_code"], FAKE)
        self.assertEqual(payload["date"], ds._today)
        for k in ("entries", "warnings", "fetch_log"):
            self.assertIn(k, payload)
        # 非当日形态分片被清
        self.assertFalse(self.old_shard.exists())
        self.assertFalse(self.yesterday_shard.exists())
        # 他票今日分片保留；非形态散件保留（形态白名单）
        self.assertTrue(self.today_other.exists())
        self.assertTrue(self.stray_a.exists())
        # 子目录豁免
        self.assertTrue(self.full_file.exists())
        self.assertTrue(self.ledger_file.exists())
        self.assertIn("自清非当日日分片", err.getvalue())

    def test_02_stray_notes_json_not_swept(self):
        notes = Path(self.sb) / "notes.json"
        notes.write_text("{}", encoding="utf-8")
        ds = _mk_ds(sandbox=self.sb)
        with contextlib.redirect_stderr(io.StringIO()):
            ds.save()
        self.assertTrue(notes.exists())

    def test_03_sweep_failure_tolerated(self):
        ds = _mk_ds(sandbox=self.sb)
        with mock.patch.object(DataSnapshot, "_sweep_stale_root",
                               side_effect=RuntimeError("boom")):
            ds.save()   # 清扫异常不得抛出、落盘不受扰
        self.assertTrue(ds._cache_path.exists())
        self.assertTrue(any("清扫旧分片失败" in w for w in ds._warnings))


class TestAsOfNoPersist(_SandboxBase):
    """反例：as-of save 零落盘 + 不清扫（守卫先 return）。"""

    def test_01_asof_save_no_file_no_sweep(self):
        ds = _mk_ds(as_of="2024-09-30", sandbox=self.sb)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ds.save()
        self.assertFalse(ds._cache_path.exists())   # 零落盘
        self.assertTrue(self.old_shard.exists())    # 不清扫
        self.assertIn("跳过日分片落盘", err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
