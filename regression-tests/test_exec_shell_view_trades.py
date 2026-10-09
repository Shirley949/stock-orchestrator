#!/usr/bin/env python3
"""exec_shell 导出面 trades/v31_fit + printer 渲染契约测试（2026-10-09 Phase 6 批）。

背景（孤儿审计同族第 4 例收口）：导出投影原只出 {summary, trades_n, end_state}，
trades 逐笔与 v31_declaration 适用性声明全链零消费（引擎算了、报告层从未显示）；
本批导出 trades/th_* 阈值键并接通三面（printer 行 + b-trade-sheet 模板行 + 合集渲染）。
执法面：导出面键形状两极 + printer 渲染两极（防再孤儿——新引擎字段三件套同批落地）。
离线（复用黄金闸门 fixtures），零网络。
"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(SKILL_ROOT / "financial-data-routing"))
import snapshot_view as sv  # noqa: E402
import execution_shell as es  # noqa: E402
import report_views as rv  # noqa: E402

FIX = SKILL_ROOT / "financial-data-routing" / "test_fixtures_exec_shell"


def _mk_shell(results=None, declaration=None, drop_results=False, drop_decl=False):
    v = {"status": "ok", "rules_id": "v3.3+T11 2026-10-06",
         "today": {"action": "NONE", "end_position": "空仓", "trigger": "t"},
         "orders": [], "pfd": {"ratio_5d": -0.37, "as_of_date": "2026-09-30",
                               "th": -0.1, "status": "ok"},
         "comparison": {"v33_t11": {"net_pnl": 0, "trades_n": 0, "end_position": "空仓"},
                        "v31_ref": {"net_pnl": 0, "end_position": "空仓"}},
         "fold": {"ledger_rows": 1, "kline_start_v33_t11": "ledger首日"},
         "context_panel": {"news_n": 0, "announcements_n": 0, "xq_voice_n": 0}}
    if not drop_results:
        v["results"] = results if results is not None else {
            "v33_t11": {"summary": {"net_pnl": 0}, "trades_n": 0, "trades": [],
                        "end_state": {"position": "空仓"}}}
    if not drop_decl:
        if declaration is not None:
            v["v31_declaration"] = declaration
    return v


def _render(v):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sv._print_exec_shell(v)
    return buf.getvalue()


def _enrich_300433(ledger=True):
    """层B 同构最小 enrich（黄金闸门 fixture；flow 供 PFD 面）。"""
    df = es.pd.read_csv(FIX / "kline" / "300433.csv", dtype={"date": str})
    df["date"] = df["date"].astype(str).str[:10]
    for cl in ["open", "high", "low", "close", "volume"]:
        df[cl] = df[cl].astype(float)
    df = df[df["date"] >= "2024-06-01"].reset_index(drop=True)
    snap = {"stock_code": "300433", "mode": "B",
            "s2_quote_kline": {"data": {"daily_kline": {"data_full": [
                {"date": r["date"], "open": r["open"], "high": r["high"],
                 "low": r["low"], "close": r["close"], "volume": r["volume"]}
                for _, r in df.iterrows()]}}}}
    ledger_rows = []
    if ledger:
        ledger_rows = [json.loads(l) for l in
                       open(FIX / "decisions" / "300433" / "modeb_decisions.jsonl",
                            encoding="utf-8")]
    return es.enrich_execution_shell(snap, ledger_rows, as_of="2026-09-30",
                                     kline_start="2024-09-30")


class TestExportFace(unittest.TestCase):
    def test_01_export_trades_key(self):
        """正例：导出面 trades 键 = list，len==trades_n，逐笔 9 字段在。"""
        eb = _enrich_300433()
        r = eb["results"]["v33_t11"]
        self.assertIsInstance(r["trades"], list)
        self.assertEqual(len(r["trades"]), r["trades_n"])
        for t in r["trades"]:
            for k in ("date", "action", "price", "shares", "fee", "commission",
                      "chg_pct", "pnl", "reason"):
                self.assertIn(k, t)

    def test_02_export_v31_th_keys(self):
        """正例：v31_declaration 阈值键导出（判据单一真相源）。"""
        eb = _enrich_300433()
        d = eb["v31_declaration"]
        self.assertEqual(d["th_ep_dd"], es.V31_FIT_EP_DD_TH)
        self.assertEqual(d["th_base_mult"], es.V31_FIT_BASE_MULT_TH)
        self.assertEqual(d["th_ep_dd"], -15)
        self.assertEqual(d["th_base_mult"], 1.5)
        self.assertEqual(d["weight"], 0)
        self.assertIn("tag", d)

    def test_03_error_form_no_export(self):
        """反例极：no_ledger 降级形态 → 无 results 键（error 形态不加导出键）。"""
        eb = _enrich_300433(ledger=False)
        self.assertEqual(eb["status"], "no_ledger")
        self.assertNotIn("results", eb)

    def test_04_fit_tag_constants_value_unchanged(self):
        """反例护栏：常量提值后字面语义不变（回放路径零触碰的静态锚）。"""
        self.assertEqual(es.V31_FIT_EP_DD_TH, -15)
        self.assertEqual(es.V31_FIT_BASE_MULT_TH, 1.5)


class TestPrinterRender(unittest.TestCase):
    def test_05_trades_rendered_last3(self):
        """正例：trades 5 笔 → 只渲染尾 3 笔，逐字形态。"""
        tr = [{"date": f"2026-10-0{i}", "action": "BUY" if i % 2 else "SELL_ALL",
               "price": 50.0 + i, "shares": 100 * i, "reason": f"触发{i}"}
              for i in range(1, 6)]
        out = _render(_mk_shell(results={"v33_t11": {"summary": {}, "trades_n": 5,
                                                     "trades": tr, "end_state": {}}}))
        self.assertEqual(out.count("逐笔（近3）"), 3)
        self.assertIn("[SELL_ALL] 2026-10-04 54 × 400股 ｜ 触发4", out)
        self.assertIn("[BUY] 2026-10-05 55 × 500股 ｜ 触发5", out)
        self.assertNotIn("触发1", out)  # 尾 3 之外的早期笔不渲染
        self.assertNotIn("触发2", out)

    def test_06_trades_empty_or_missing(self):
        """反例极：0 笔 → 无逐笔行；旧快照缺 results 键 → 零输出不崩。"""
        self.assertNotIn("逐笔", _render(_mk_shell()))
        out = _render(_mk_shell(drop_results=True))
        self.assertNotIn("逐笔", out)
        self.assertIn("今日动作", out)  # 其余行照常

    def test_07_v31_decl_with_th(self):
        """正例：声明+阈值键 → 适用性行含 tag/declaration/判据数值。"""
        d = {"tag": "平滑/过渡态（v3.1 参考线适用性中性；两方案差异历史均 <3%）",
             "declaration": "本股当前为平滑/过渡态：v3.1 参考适用性中性（v3.1 仅适合少数平缓爬升股）",
             "weight": 0, "th_ep_dd": -15, "th_base_mult": 1.5}
        out = _render(_mk_shell(declaration=d))
        self.assertIn("v3.1 适用性：", out)
        self.assertIn("（判据：episode 回撤 ≤ -15% 或 base_mult ≥ 1.5 → 不适用）", out)

    def test_08_v31_decl_legacy_no_th(self):
        """反例极：旧快照 declaration 无 th 键 → 行出但无判据段；无声明键 → 行省。"""
        d = {"tag": "t", "declaration": "decl-text", "weight": 0}
        out = _render(_mk_shell(declaration=d))
        self.assertIn("v3.1 适用性：t ｜ decl-text", out)
        self.assertNotIn("判据", out)
        out2 = _render(_mk_shell(drop_decl=True))
        self.assertNotIn("v3.1 适用性", out2)


class TestDirZhLift(unittest.TestCase):
    def test_09_dir_zh_module_level(self):
        """DIR_ZH 提升后模块级可 import（合集渲染件唯一实现复用，禁本地重写）。"""
        self.assertEqual(rv.DIR_ZH, {"bull": "看多", "bear": "看空", "neutral": "中性"})

    def test_10_head_draft_unchanged(self):
        """反例护栏：局部别名保渲染行为——bull/bear/neutral 三值照常映射。"""
        base = {"close": 10.0, "kelly_fraction": 0.0, "state_tuple": {},
                "multi_period": {}, "direction_rows": {}}
        self.assertIn("看多", rv._render_head_draft_v3({**base, "direction": "bull"}))
        self.assertIn("看空", rv._render_head_draft_v3({**base, "direction": "bear"}))
        self.assertIn("中性", rv._render_head_draft_v3({**base, "direction": "neutral"}))

    def test_11_view_registered(self):
        """视图注册仍在：exec_shell 挂 s4_technical.data.execution_shell。"""
        self.assertEqual(sv.VIEW_PATHS["exec_shell"],
                         ("s4_technical", "data", "execution_shell"))


if __name__ == "__main__":
    unittest.main()
