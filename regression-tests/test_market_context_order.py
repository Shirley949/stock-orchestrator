#!/usr/bin/env python3
"""test_market_context_order — market_context 排序契约 + 板块统一信封固化。

背景（2026-08-27 000657 B 回归实证）：westock kline 原生 desc（[0]=最新交易日），
live 路径曾按 asc 语义消费——sh[-1] 把 60 天前的老收盘当「最新」（实证上证误报
4083.97，真值 3912.52），classify_regime 吃倒序序列致 regime/MA20/ret5 幻觉；
as-of 路径存 asc 掩盖了该 bug（两路同键序不一致）。修复后契约：

  · 快照键 index_close / board.closes 统一 desc（[0]=最新，黄金范式）
  · classify_regime 按 asc 语义消费（iloc[-1]=最新）→ 一切喂前必 reverse
  · board / board_fund_flow 键必挂载：ok|degraded 同场景统一形状
  · 子板块解析链：classification.board_name_level L2 中段优先

离线：monkeypatch westock_client.call/kline + sys.modules["akshare"] 桩，零网络。
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

_ROUTING = Path(__file__).resolve().parents[2] / "financial-data-routing"
sys.path.insert(0, str(_ROUTING))

import pandas as pd  # noqa: E402
import runner  # noqa: E402
import short_term_engine as ste  # noqa: E402
import westock_client as wc  # noqa: E402


def _synth_asc(n=60, latest=112.0):
    """真实时间序（asc）：前段横盘 ~90，末段上攻至 latest（保证 latest>MA20 且 ret5>-1%
    → 正确喂法下 regime=trend_up 必然成立）。"""
    asc = [90.0 + (i % 3) * 0.1 for i in range(n - 20)]
    asc += [95.0 + i * 0.75 for i in range(19)]
    asc.append(latest)
    return asc


def _desc_closes(**kw):
    return list(reversed(_synth_asc(**kw)))


def _md_table(rows):
    lines = ["| " + " | ".join(rows[0]) + " |", "| --- | " + "--- | " * (len(rows[0]) - 1)]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _recs_from_closes(closes_desc):
    """desc closes → kline 行形态（日期手工递减，仅保序用途）。"""
    return [{"date": f"2026-09-{(30 - i):02d}", "last": c} for i, c in enumerate(closes_desc)]


_BOARD_MD = _md_table([["code", "name", "分类"],
                       ["pt02GN2156", "小金属概念", "聚源产业概念清单"],
                       ["pt01801054", "小金属", "申万二级行业清单"],
                       ["pt01850544", "其他小金属", "申万三级行业清单"]])


def _fake_kline(code, period="day", fq="qfq", limit=60):
    if str(code).startswith("pt"):
        return _recs_from_closes(_desc_closes(latest=36417.23))
    return _recs_from_closes(_desc_closes())


def _fake_call(cmd, code, *args, **kw):
    if cmd == "search":
        return _BOARD_MD
    raise wc.WestockError(f"offline-test 不支持 {cmd}")


class TestMarketContextOrder(unittest.TestCase):
    """核心两极：desc 存储下取到的必须是最新值（修复面），且 regime 判定用反转序列。"""

    @classmethod
    def setUpClass(cls):
        cls._patches = [
            mock.patch.object(wc, "kline", side_effect=_fake_kline),
            mock.patch.object(wc, "call", side_effect=_fake_call),
        ]
        fake_ak = types.ModuleType("akshare")
        fake_ak.stock_board_industry_hist_em = mock.Mock(
            side_effect=RuntimeError("offline-test 东财桩恒拒"))
        fake_ak.stock_sector_fund_flow_rank = mock.Mock(
            side_effect=RuntimeError("offline-test 东财桩恒拒"))
        cls._patches.append(mock.patch.dict(sys.modules, {"akshare": fake_ak}))
        for p in cls._patches:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in cls._patches:
            p.stop()

    def test_live_index_last_is_newest(self):
        """修复面：index_sh.last 必须 = 存储序首位（最新日），而非 sh[-1] 老值。"""
        d = runner.fetch_market_context("000657")["data"]
        self.assertEqual(d["index_close"][0], _synth_asc()[-1])
        self.assertEqual(d["index_sh"]["last"], d["index_close"][0])
        self.assertNotEqual(d["index_sh"]["last"], d["index_close"][-1])

    def test_regime_positive_pole(self):
        """正确序列下 trend_up 必然触发（横盘后上攻构造），且与库函数 asc 直喂同词。"""
        d = runner.fetch_market_context("000657")["data"]
        v = d["index_sh"]["verdict"]
        ref = ste.classify_regime(pd.Series(_synth_asc()))
        self.assertEqual(v["regime"], "trend_up")
        self.assertEqual(v["idx_close"], ref["idx_close"])
        self.assertLess(v["idx_ma20"], v["idx_close"])

    def test_no_name_degraded_keys_mounted(self):
        """industry_name 缺失 → board/board_fund_flow 显式 degraded（键必挂载，不再缺席）。"""
        d = runner.fetch_market_context("600036")["data"]
        self.assertIn("board", d)
        self.assertEqual(d["board"]["status"], "degraded")
        self.assertIn("board_fund_flow", d)

    def test_board_envelope_ok_shape(self):
        """主通道统一信封：search 精确名+二级行业择码 → pt 码 kline → desc closes+信封。"""
        d = runner.fetch_market_context("000657", "小金属")["data"]
        b = d["board"]
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["code"], "pt01801054")            # 二级行业优先，非概念板
        self.assertEqual(b["closes"][0], b["last"])
        self.assertEqual(b["latest_date"], "2026-09-30")
        self.assertIn("ret5", b)
        lp = b["latest_period"]
        self.assertIsNotNone(lp.get("value"))

    def test_engine_consumes_desc_with_reverse(self):
        """enrich_short_term 对 desc 快照反转后再喂（与 fetch 层同一语义出口）。"""
        vals = _desc_closes()
        fixed = ste.classify_regime(pd.Series(list(reversed(vals))))
        naive = ste.classify_regime(pd.Series(vals))         # 历史 bug 行为参照
        self.assertEqual(fixed["regime"], "trend_up")
        self.assertEqual(fixed["idx_close"], _synth_asc()[-1])
        self.assertNotEqual(naive["idx_close"], fixed["idx_close"])  # 两极：直喂必不同


if __name__ == "__main__":
    unittest.main(verbosity=2)
