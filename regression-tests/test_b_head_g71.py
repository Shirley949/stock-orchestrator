#!/usr/bin/env python3
"""test_b_head_g71.py — b_head 引擎视图 + G71 头块 gate 机械化测试。

固化 2026-08-30 plan（b-snapshot-5-eager-tome）一·C 节 18 份真实 B 快照实测的结论：
- TestBHeadCalc      C2/C3/C4：5 日聚合 / 亿元换算 / 筹码带换算
- TestBHeadBranches  C5-C10：neutral / bear(概率锚+破位措辞) / bull / 次新 / 资金降级 / 尾盘空
- TestBHeadDraft     head_draft_md 模板钉死项（情景表/措辞/去重/gap 阈值）
- TestBHeadNoop      C11/C12：A 快照 no-op + 截断残骸不崩
- TestBHeadCorpus    C1：~/.cache/skill-snapshots/full 全部 B 快照金票回放（无语料则 skip）
- TestG71            C13/C14：四极反例 + 已失守变体正例 + v2 金票正例（归档在则跑）
- TestG71ProbTableGate P0(2026-09-03)：④收窄 corpus——FLIP/INVARIANT/ENUMERATION
  （trap_ledger G71#projection:panorama_pct_misread；证据=retrospective_audit_20260902）

跑：python3 test_b_head_g71.py
"""
import copy
import glob
import json
import os
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROUTING = _HERE.parent.parent / "financial-data-routing"
sys.path.insert(0, str(_ROUTING))
sys.path.insert(0, str(_HERE.parent / "scripts" / "lib"))

import report_views as rv  # noqa: E402
from gate_definitions import GATE_CHECKERS, GateResult  # noqa: E402

CORPUS_DIR = os.path.expanduser("~/.cache/skill-snapshots/full")
V2_REPORT = os.path.expanduser(
    "~/analysis_report/analysis_report-glm5.3-蓝思科技-300433/"
    "analysis_report-glm5.3-蓝思科技-300433.md")


# ---------------------------------------------------------------------------
# 合成 B 快照（结构/键名 = 2026-08-30 18 票真实语料实测；数值取 300433_20260828）
# ---------------------------------------------------------------------------

def _dk_rows():
    rows = []
    data = [  # desc：rows[0]=最新
        ("2026-08-28", 39.06, 40.09, 38.19, 38.23, 47.89e8, 0.0246),
        ("2026-08-27", 39.08, 39.27, 38.38, 39.05, 41.49e8, 0.0215),
        ("2026-08-26", 37.91, 39.60, 37.91, 39.02, 49.56e8, 0.0256),
        ("2026-08-25", 37.49, 39.00, 35.79, 37.90, 49.19e8, 0.0264),
        ("2026-08-24", 37.31, 38.10, 36.52, 37.95, 45.72e8, 0.0245),
        ("2026-08-21", 37.30, 37.80, 36.47, 37.19, 38.35e8, 0.0207),
    ]
    for d, o, h, l, c, amt, tov in data:
        rows.append({"date": d, "open": o, "high": h, "low": l, "close": c,
                     "amount": amt, "turnover": tov, "outstanding_share": 4.967e9})
    return rows


def _b_snapshot(direction="neutral", probability=None, tail_signal="尾盘连阴",
                fund_status="ok", insufficient=False, stops_above=False):
    rq = {"status": "ok", "open": 39.06, "high": 40.09, "low": 38.19,
          "current": 38.23, "close": 38.23, "pre_close": 39.05,
          "change_pct": -2.1, "turnover_pct": 2.46, "amount_yuan": 47.89e8}
    if direction == "neutral":
        df = {"status": "ok", "direction": "neutral", "confidence": "NEUTRAL",
              "probability": None, "sample_win_rate": None, "rule_name": None,
              "horizon_days": 15,
              "expected_range": {"low": 33.123, "high": 43.337},
              "evidence": {"ret20_pct": 21.06}}
    else:
        df = {"status": "ok", "direction": direction, "confidence": "MED",
              "probability": probability, "sample_win_rate": probability,
              "rule_name": "up_stall", "horizon_days": 15,
              "expected_range": {"low": 33.123, "high": 43.337},
              "evidence": {"ret20_pct": 21.06}}
    if insufficient:
        df = {"status": "insufficient_history", "direction": None,
              "confidence": None, "probability": None, "sample_win_rate": None,
              "rule_name": None, "horizon_days": None, "expected_range": None,
              "evidence": None, "reason": "上市历史不足 130 交易日"}
    # stops_above=True：模拟破位态（stop 价 > 现价，实测 7/18 票形态）
    if stops_above:
        stops = [{"level": "h60_ma60", "price": 39.919, "dist_pct": 4.4,
                  "rule": "60m MA60 得失", "triggered": True},
                 {"level": "daily_ma20", "price": 39.527, "dist_pct": 3.4,
                  "rule": "日MA20-2%×2日", "triggered": True}]
    else:
        stops = [{"level": "h60_ma60", "price": 36.919, "dist_pct": -3.43,
                  "rule": "60m MA60 得失", "triggered": False},
                 {"level": "daily_ma20", "price": 35.527, "dist_pct": -7.07,
                  "rule": "日MA20-2%×2日", "triggered": False}]
    if fund_status == "ok":
        ff = {"status": "ok", "net_flow": -2.98, "trend_5d": -2.84,
              "trend_10d": 11.58, "trend_20d": 13.15,
              "items": [{"name": "特大单", "in": 0.0, "out": 2.1},
                        {"name": "大单", "in": 0.0, "out": 0.88},
                        {"name": "中单", "in": 0.0, "out": 0.89},
                        {"name": "小单", "in": 3.87, "out": 0.0}]}
    else:
        ff = {"status": "failed", "error": "westock fund flow 空响应"}
    return {
        "mode": "B", "stock_code": "300433",
        "s2_quote_kline": {"data": {
            "realtime_quote": rq,
            "daily_kline": {"status": "ok", "data": _dk_rows(),
                            "latest_period": {"raw_date": "2026-08-28",
                                              "period_label": "2026-08-28",
                                              "as_of": "2026-08-30",
                                              "value": 38.23}}}},
        "s4_technical": {"data": {
            "chip": {"chipAvgCost": 37.65, "chipProfitRate": 55.23,
                     "chipConcentration90": 26.35, "chipConcentration70": 18.46},
            "support_resistance": {"layers": [
                {"name": "压力2", "price": 47.92},
                {"name": "压力1", "price": 38.43},
                {"name": "强支撑", "price": 37.4},
                {"name": "第一支撑", "price": 35.79},
                {"name": "深度支撑", "price": 30.8}]},
            "short_term_enrich": {
                "direction_forecast": df,
                "multi_period": {"resonance_level": "long_resonance"},
                "risk_control": {
                    "stops": stops,
                    "atr": {"atr14": 1.84, "atr_pct": 4.81, "atr_stop": 34.55},
                    "kelly": ({"kelly_fraction": 0.0, "capped_at": 0.25,
                               "note": "无方向置信，不建议开仓"}
                              if direction == "neutral" and not insufficient
                              else {"kelly_fraction": 0.25, "capped_at": 0.25,
                                    "note": None}),
                    "take_profit_ladder": [
                        {"gain_pct": 8, "protect": "保本"},
                        {"gain_pct": 15, "protect": "锁定+5%"},
                        {"gain_pct": 25, "protect": "锁定+12%"}]}}}},
        "s3_fund_flow": {"data": {"fund_flow": ff}},
        "intraday_60min": {"data": {"report_view": {
            "tail_signal": tail_signal, "ma60_state": "above",
            "ma60": 36.92, "last_close": 38.23}}},
    }


def _build(snap):
    rv.attach_report_views(snap)
    s4 = snap.get("s4_technical", {}).get("data", {})
    return s4.get("b_head")


def _res(checker, report, data):
    out = checker(report, data)
    return (bool(out), list(out.get("reasons", [])) if isinstance(out, dict) else [])


# ---------------------------------------------------------------------------
# C2/C3/C4：聚合与换算
# ---------------------------------------------------------------------------

class TestBHeadCalc(unittest.TestCase):
    def setUp(self):
        self.bh = _build(_b_snapshot())
        if self.bh is None:
            self.failTest("F2 未实现：attach 后 s4_technical.data.b_head 缺失")

    def failTest(self, msg):  # py3.10 兼容：等价 unittest.failTest
        raise self.failureException(msg)

    def test_five_day_agg(self):
        """C2：high_5d/low_5d/ret5d == recent[:5] 手工重算。"""
        self.assertEqual(self.bh["high_5d"], 40.09)
        self.assertEqual(self.bh["low_5d"], 35.79)
        self.assertEqual(self.bh["ret5d_pct"], round((38.23 / 37.95 - 1) * 100, 2))

    def test_amount_yi(self):
        """C3：amount_yi == round(amount_yuan/1e8, 2)。"""
        self.assertEqual(self.bh["amount_yi"], 47.89)

    def test_chip_band(self):
        """C4：band90 = avgCost ∓ c90%×avgCost；获利盘透传。"""
        self.assertEqual(self.bh["band90_low"], round(37.65 - 0.2635 * 37.65, 2))
        self.assertEqual(self.bh["band90_high"], round(37.65 + 0.2635 * 37.65, 2))
        self.assertEqual(self.bh["chip_profit_rate"], 55.23)

    def test_gap_and_shadow(self):
        self.assertEqual(self.bh["open_gap_pct"], round((39.06 / 39.05 - 1) * 100, 2))
        self.assertEqual(self.bh["tail_signal"], "尾盘连阴")


# ---------------------------------------------------------------------------
# C5-C10：分支
# ---------------------------------------------------------------------------

class TestBHeadBranches(unittest.TestCase):
    def test_neutral_draft(self):
        """C5 前置：neutral → 60/25/15 + 主推=中性。"""
        bh = _build(_b_snapshot())
        self.assertIn("中性·区间震荡（主推）", bh["head_draft_md"])
        self.assertIn("| 60%", bh["head_draft_md"])
        self.assertIn("未落规则覆盖带", bh["head_draft_md"])

    def test_bear_anchored_and_above_side(self):
        """C5：bear p=0.66 → 概率锚 66；破位态措辞。"""
        bh = _build(_b_snapshot(direction="bear", probability=0.66, stops_above=True))
        self.assertIn("| 66%", bh["head_draft_md"])
        self.assertIn("悲观·顺势回落（主推）", bh["head_draft_md"])
        self.assertEqual(bh["stop_side"]["h60_ma60"], "above")
        self.assertIn("已失守", bh["head_draft_md"])
        self.assertIn("反抽不过减仓", bh["head_draft_md"])
        # 破位态悲观目标走 ATR/深度支撑分支，非纪律位
        self.assertEqual(bh["pess_target_1"], 34.55)
        self.assertEqual(bh["pess_target_2"], 30.8)

    def test_bear_normal_side(self):
        """破位反例：stops 在下方时悲观目标=纪律位两档、无「已失守」。"""
        bh = _build(_b_snapshot(direction="bear", probability=0.66))
        self.assertEqual(bh["stop_side"]["h60_ma60"], "below")
        self.assertEqual(bh["pess_target_1"], 36.919)
        self.assertEqual(bh["pess_target_2"], 35.527)
        self.assertNotIn("已失守", bh["head_draft_md"])

    def test_bull_synthetic(self):
        """C7：bull 合成 → 主推=乐观·p 锚 61。"""
        bh = _build(_b_snapshot(direction="bull", probability=0.61))
        self.assertIn("乐观·顺势上行（主推）", bh["head_draft_md"])
        self.assertIn("| 61%", bh["head_draft_md"])

    def test_insufficient_history(self):
        """C8：次新 → 透传 reason、direction=None、禁编方向。"""
        bh = _build(_b_snapshot(insufficient=True))
        self.assertIsNone(bh["direction"])
        self.assertIn("上市历史不足", bh["head_draft_md"])
        self.assertNotIn("方向预测：bull", bh["head_draft_md"])
        self.assertNotIn("方向预测：bear", bh["head_draft_md"])

    def test_fund_flow_failed(self):
        """C9：资金流降级 → status=failed + 主力锚词保留。"""
        bh = _build(_b_snapshot(fund_status="failed"))
        self.assertEqual(bh["fund_status"], "failed")
        self.assertIsNone(bh["main_net_yi"])
        self.assertIn("主力/散户", bh["head_draft_md"])
        self.assertIn("降级", bh["head_draft_md"])

    def test_tail_none(self):
        """C10：tail_signal=None → 尾盘中性。"""
        bh = _build(_b_snapshot(tail_signal=None))
        self.assertIsNone(bh["tail_signal"])
        self.assertIn("尾盘中性", bh["head_draft_md"])

    def test_kelly_note_fallback(self):
        """修正#4：kelly note=None → capped_at 兜底句，禁渲染「（None）」。"""
        bh = _build(_b_snapshot(direction="bear", probability=0.66))
        self.assertIn("capped_at", bh["kelly_note"])
        self.assertNotIn("（None）", bh["head_draft_md"])


# ---------------------------------------------------------------------------
# head_draft_md 模板钉死项
# ---------------------------------------------------------------------------

class TestBHeadDraft(unittest.TestCase):
    def setUp(self):
        self.md = _build(_b_snapshot())["head_draft_md"]

    def test_fixed_lines(self):
        for anchor in ["## 核心结论（数据截止 2026-08-28 收盘）",
                       "**现价 38.23 元（-2.1%，成交 47.89 亿、换手 2.46%）**",
                       "预期区间 [33.123 ~ 43.337]",
                       "（目标价=引擎区间/止盈梯/纪律位换算，仅供参考）",
                       "ATR 止损参考 34.55",
                       "集中度 26.35%",
                       "净流出 2.98 亿 vs 小单净流入 3.87 亿",
                       "kelly=0.0"]:
            self.assertIn(anchor, self.md)

    def test_discipline_label_form(self):
        """G71 执法对象形：「36.919（60m MA60 档）失守减仓」。"""
        self.assertIn("36.919（60m MA60 档）失守减仓", self.md)
        self.assertIn("35.527（日 MA20 档）失守清短线仓", self.md)

    def test_cost_band_suffix(self):
        """修正#3：成本带独立尾缀（关键位行行尾），不嵌支撑序列。"""
        self.assertTrue(
            any(l.rstrip().endswith("成本带 37.65") for l in self.md.splitlines()),
            "成本带应为关键位行独立尾缀")

    def test_capstone_row_words(self):
        """情景标签词根（G30）。"""
        for w in ["中性·", "乐观·", "悲观·"]:
            self.assertIn(w, self.md)


# ---------------------------------------------------------------------------
# C11/C12：no-op 与健壮性
# ---------------------------------------------------------------------------

class TestBHeadNoop(unittest.TestCase):
    def test_a_snapshot_noop(self):
        """C11：A 快照不挂 b_head；kline 视图照常（加法式）。"""
        snap = _b_snapshot()
        snap["mode"] = "A"
        snap["s4_technical"]["data"].pop("short_term_enrich")
        rv.attach_report_views(snap)
        self.assertNotIn("b_head", snap["s4_technical"]["data"])
        kv = snap["s2_quote_kline"]["data"]["daily_kline"]["report_view"]
        self.assertEqual(kv["status"], "ok")

    def test_truncated_no_crash(self):
        """C12：残缺快照 attach 不崩。"""
        rv.attach_report_views({"mode": "B", "stock_code": "x"})
        rv.attach_report_views({"mode": "B", "s4_technical": {"data": None}})


# ---------------------------------------------------------------------------
# C1：真实语料金票回放（无语料则 skip）
# ---------------------------------------------------------------------------

class TestBHeadCorpus(unittest.TestCase):
    def test_all_b_snapshots_replay(self):
        files = sorted(glob.glob(os.path.join(CORPUS_DIR, "*.json")))
        bfiles = []
        for f in files:
            try:
                if json.load(open(f)).get("mode") == "B":
                    bfiles.append(f)
            except Exception:
                continue
        if len(bfiles) < 10:
            self.skipTest(f"语料不足（{len(bfiles)} 份 B 快照）")
        ok, sides, pess_branch, drafts = 0, 0, 0, {}
        for f in bfiles:
            snap = json.load(open(f))
            rv.attach_report_views(snap)
            bh = snap.get("s4_technical", {}).get("data", {}).get("b_head")
            self.assertIsNotNone(bh, f"{os.path.basename(f)} b_head 未挂载")
            self.assertEqual(bh["status"], "ok", os.path.basename(f))
            self.assertTrue(bh["head_draft_md"], os.path.basename(f))
            # 数字==raw 精确相等（现价族）
            rq = snap["s2_quote_kline"]["data"]["realtime_quote"]
            self.assertEqual(bh["close"], rq.get("current") or rq.get("close"),
                             os.path.basename(f))
            # side/pess 分支自洽（stop 价 vs close 现算对拍）
            rc = snap["s4_technical"]["data"]["short_term_enrich"]["risk_control"]
            close = bh["close"]
            stops = {s["level"]: s["price"] for s in rc.get("stops", []) if s.get("price")}
            for lvl, px in stops.items():
                expect = "above" if px > close else "below"
                self.assertEqual(bh["stop_side"].get(lvl), expect,
                                 f"{os.path.basename(f)} {lvl}")
                if expect == "above":
                    sides += 1
            first = stops.get("h60_ma60")
            if first is not None and first > close:
                pess_branch += 1
                self.assertNotEqual(bh["pess_target_1"], first,
                                    f"{os.path.basename(f)} 破位票悲观目标不得=纪律位")
            drafts[os.path.basename(f)] = bh["head_draft_md"]
            ok += 1
        # 300054 两日幂等（同 as-of 数据 → 逐字节一致）
        a = drafts.get("300054_20260828.json")
        b = drafts.get("300054_20260829.json")
        if a is not None and b is not None:
            self.assertEqual(a, b, "300054 两日快照渲染应逐字节一致（幂等）")
        self.assertGreaterEqual(ok, 10)
        self.assertGreaterEqual(sides, 2, "真实语料应含破位态样本（实测 7 票）")
        self.assertGreaterEqual(pess_branch, 2, "破位票悲观目标应走 ATR/深度支撑分支")


# ---------------------------------------------------------------------------
# C13/C14：G71 两极
# ---------------------------------------------------------------------------

_HEAD_OK = """# 300433 模式B

📅 数据截止 2026-08-28 收盘

## 核心结论（数据截止 2026-08-28 收盘）

**现价 38.23 元（-2.1%，成交 47.89 亿、换手 2.46%）**。近 5 日**宽幅震荡**（区间 35.79～40.09，涨跌 0.74%；20 日 21.06%）。今日分时：平开（0.03%），冲高回落，收长上影阴线（尾盘连阴）。

**引擎方向预测：neutral（置信 NEUTRAL，视野 15 日）**——未落规则覆盖带，预期区间 [33.123 ~ 43.337]：

| 情景 | 概率 | 目标价 | 动作 |
|------|------|--------|------|
| 中性·区间震荡（主推） | 60% | 33.123~43.337 | 区间思路，不追高 |
| 乐观·上破压力 | 25% | 41.29 → 43.96 | 突破加仓，移动止盈 |
| 悲观·失守支撑 | 15% | 36.919 → 35.527 | 失守减仓 |

（目标价=引擎区间/止盈梯/纪律位换算，仅供参考）

- **关键位**：压力 38.43（压力1）→ 47.92（压力2）；现价 38.23；支撑 37.4（强支撑）→ 35.79（第一支撑）→ 30.8（深度）；成本带 37.65
- **纪律位**：36.919（60m MA60 档）失守减仓、35.527（日 MA20 档）失守清短线仓；ATR 止损参考 34.55
- **筹码**：90% 筹码分布在约 27.73～47.57 元（集中度 26.35%，围绕平均成本 37.65），获利盘 55.23%
- **主力/散户**：当日特大+大单净流出 2.98 亿 vs 小单净流入 3.87 亿；5 日 -2.84 / 20 日 13.15 亿——分歧
- **仓位**：kelly=0.0（无方向置信，不建议开仓）

## 1. 技术面

正文。

## 5. 综合研判与操作建议

### 情景-动作矩阵

| 情景 | 概率 | 目标价 | 动作 |
|------|------|--------|------|
| 中性（主推） | 60% | 33.123~43.337 | 区间思路 |
| 乐观 | 25% | 41.29 | 突破加仓 |
| 悲观 | 15% | 36.919 | 失守减仓 |
"""


class TestG71(unittest.TestCase):
    def setUp(self):
        if "G71" not in GATE_CHECKERS:
            self.failTest = None
            raise self.failureException("O3 未实现：GATE_CHECKERS 缺 G71")
        self.check = GATE_CHECKERS["G71"]
        self.snap = _b_snapshot()

    def test_no_head_fail(self):
        """反例 a：无头块 → 存在性 FAIL。"""
        ok, reasons = _res(self.check, "# 报告\n\n## 5. 操作建议\n正文\n", self.snap)
        self.assertFalse(ok)
        self.assertTrue(any("核心结论" in r for r in reasons), reasons)

    def test_missing_slot_fail(self):
        """反例 b：缺筹码槽 → 完整性 FAIL。"""
        report = _HEAD_OK.replace(
            "- **筹码**：90% 筹码分布在约 27.73～47.57 元（集中度 26.35%，围绕平均成本 37.65），获利盘 55.23%\n", "")
        ok, reasons = _res(self.check, report, self.snap)
        self.assertFalse(ok)
        self.assertTrue(any("筹码" in r for r in reasons), reasons)

    def test_wrong_stop_price_fail(self):
        """反例 c：纪律位 36.919→37.9（>1%）→ 标签对拍 FAIL。"""
        report = _HEAD_OK.replace("36.919（60m MA60 档）失守减仓",
                                  "37.9（60m MA60 档）失守减仓")
        ok, reasons = _res(self.check, report, self.snap)
        self.assertFalse(ok)
        self.assertTrue(any("60m MA60" in r or "纪律位" in r for r in reasons), reasons)

    def test_head_prob_drift_fail(self):
        """反例 d：头表中性 60%→55% 与 capstone 60% 漂移 → FAIL。"""
        report = _HEAD_OK.replace("| 中性·区间震荡（主推） | 60% |",
                                  "| 中性·区间震荡（主推） | 55% |")
        ok, reasons = _res(self.check, report, self.snap)
        self.assertFalse(ok)
        self.assertTrue(any("capstone" in r or "概率" in r for r in reasons), reasons)

    def test_broken_state_wording_pass(self):
        """正例 e：破位态「已失守·反抽不过」变体措辞须 PASS（防 regex 漏破位态）。"""
        snap = _b_snapshot(stops_above=True)
        bh = _build(snap)  # attach 到 snap 本体（pess 对拍分支随之启用）
        self.assertEqual(snap["s4_technical"]["data"]["b_head"]["stop_side"]["h60_ma60"],
                         "above")
        # 纪律位行=纪律位原价（带已失守标签）；悲观表行=引擎 pess 分支（ATR/深度支撑）
        report = _HEAD_OK.replace(
            "36.919（60m MA60 档）失守减仓、35.527（日 MA20 档）失守清短线仓",
            "39.919（60m MA60 档已失守）反抽不过减仓、"
            "39.527（日 MA20 档已失守）反抽不过清短线仓")
        report = report.replace("| 悲观·失守支撑 | 15% | 36.919 → 35.527 |",
                                f"| 悲观·失守支撑 | 15% | {bh['pess_target_1']}"
                                f" → {bh['pess_target_2']} |")
        ok, reasons = _res(self.check, report, snap)
        self.assertTrue(ok, reasons)

    def test_broken_pess_mismatch_fail(self):
        """反例 f：破位票悲观行仍写纪律位价（>1% 偏差）→ pess 分支对拍 FAIL。"""
        snap = _b_snapshot(stops_above=True)
        _build(snap)  # 挂 b_head（pess=34.55/30.8）；报告悲观行写纪律位 39.919 → 必 FAIL
        ok, reasons = _res(self.check, _HEAD_OK, snap)
        self.assertFalse(ok)
        self.assertTrue(any("悲观目标" in r for r in reasons), reasons)

    def test_golden_head_pass(self):
        """C14：模板标准头块 + 自洽快照 → PASS。"""
        snap = copy.deepcopy(self.snap)
        ok, reasons = _res(self.check, _HEAD_OK, snap)
        self.assertTrue(ok, reasons)

    def test_a_snapshot_shortcircuit(self):
        """A 快照 mode 短路 → 空报告也 True。"""
        snap = copy.deepcopy(self.snap)
        snap["mode"] = "A"
        ok, _ = _res(self.check, "", snap)
        self.assertTrue(ok)

    def test_v2_report_flags_missing_slots(self):
        """C14（对齐裁决 2026-08-31）：v2 措辞早于模板 v2——现价埋在情景表、无分时槽，
        恰是用户 Request C 点名的第 1/3 优先槽位 → G71 必须标记缺『现价/分时』
        （其余 8 槽 + 纪律位对拍 + 投影在 v2 全过——证明执法面收敛在真缺口上）。"""
        if not (os.path.exists(V2_REPORT) and os.path.exists(
                os.path.join(CORPUS_DIR, "300433_20260828.json"))):
            self.skipTest("v2 报告或语料快照缺席")
        report = open(V2_REPORT, encoding="utf-8").read()
        snap = json.load(open(os.path.join(CORPUS_DIR, "300433_20260828.json")))
        ok, reasons = _res(self.check, report, snap)
        self.assertFalse(ok)
        self.assertEqual(len(reasons), 1, reasons)  # 收敛：仅槽位一项
        self.assertIn("现价", reasons[0])
        self.assertIn("分时", reasons[0])


# ---------------------------------------------------------------------------
# P0（2026-09-03）：G71④ 概率表收窄 corpus —— FLIP / INVARIANT / ENUMERATION
# 证据源：~/retrospective_audit_20260902/evidence/{batch1,batch2}_edits.json
# 修前 old 原文 verbatim 入 fixture；「-R」后缀 = trap_ledger 自记形态重建（非 verbatim）。
# 红先绿后：FLIP/ENUMERATION 在收窄落码前必红（旧引擎假漂移/首实例即止），
# 落码后转绿；INVARIANT 收窄前后都必须 FAIL（执法面不得缩过真漂移）。
# ---------------------------------------------------------------------------

_PANORAMA_ROWS_FLIP = [
    # 300054（①偏空行不在词根面，保留 verbatim 证形态；④中性行=④臂事件行）
    ("300054",
     "| ①估值 | 偏空 | PE(TTM) 73.74（近五年 76% 分位）/ PB 12.31（近五年 96% 分位）；"
     "机构目标价 86.68（买入 100%，2 家） | `[src: snapshot.valuation_snapshot.data.valuation_percentile]` |\n"
     "| ④前瞻预期 | 中性 | westock 目标价 86.68 元（买入 100%，机构 2 家）——机构预期与短线趋势背离"
     " | `[src: snapshot.valuation_snapshot.data.targetPrice]` |"),
    ("002407",
     "| ③技术·资金·筹码 | 中性 | 趋势偏空（均线空头排列+60m MA60 下方）vs 量能偏多（OBV 积累、"
     "RS 全面跑赢）；获利盘 10.89% 出清后期 | `[src: snapshot.s4_technical.data.volume_price]` "
     "`[src: snapshot.s4_technical.data.chip_behavior]` |"),
    ("002851-r1",
     "| ③技术·资金·筹码 | 中性 | 破位整理（短中期均线失守+纪律位双失守）vs TD9 买向有效（66.7%）"
     "+20 日主力净流入 9.5 亿；获利盘 19.48% 出清较充分 | `[src: snapshot.s4_technical.data.volume_price]` "
     "`[src: snapshot.s4_technical.data.chip_behavior]` |"),
    ("002851-r2",
     "| ③技术·资金·筹码 | 中性 | 破位整理（短中期均线失守+纪律位双失守）vs TD9 买向历史有效档"
     "+20 日主力净流入 9.5 亿；获利盘 19.48% 出清较充分 | `[src: snapshot.s4_technical.data.volume_price]` "
     "`[src: snapshot.s4_technical.data.chip_behavior]` |"),
    ("301217-R",
     "| ④前瞻预期 | 中性 | 机构覆盖 2 家（买入 100%）；估值处近五年 82% 分位——预期与短线趋势背离"
     " | `[src: snapshot.valuation_snapshot.data.targetPrice]` |"),
]


def _panorama_report(rows):
    """金票头块 + §5 内插入证据全景表（表头无「概率」列，含裸 % 事件行）。"""
    return _HEAD_OK.replace(
        "## 5. 综合研判与操作建议\n\n### 情景-动作矩阵",
        "## 5. 综合研判与操作建议\n\n### 证据全景（非概率表）\n\n"
        "| 维度 | 方向 | 证据 | 数据锚点 |\n|------|------|------|---------|\n"
        + rows + "\n\n### 情景-动作矩阵")


class TestG71ProbTableGate(unittest.TestCase):
    """G71④ 收窄锚：概率执法面 = 表头含「概率」列的表（m38 §38.1 表头合同）。

    FLIP：非概率表（证据全景）中性行的裸 % 不入④执法面——收窄前 FAIL、收窄后 PASS。
    INVARIANT：带概率表头的表内数值漂移，收窄前后都必须 FAIL（防收窄缩过真漂移）。
    ENUMERATION：cap 切片内多张概率表同词根冲突 → reason 全枚举
    （旧引擎首实例即止，修一轮暴露下一个——两轮教训的结构性修复）。
    """

    def setUp(self):
        self.check = GATE_CHECKERS["G71"]
        self.snap = _b_snapshot()

    def test_flip_panorama_rows_pass(self):
        for label, rows in _PANORAMA_ROWS_FLIP:
            with self.subTest(label):
                ok, reasons = _res(self.check, _panorama_report(rows), self.snap)
                self.assertTrue(ok, f"{label}: {reasons}")

    def test_invariant_cap_matrix_drift_still_fails(self):
        rep = _panorama_report(_PANORAMA_ROWS_FLIP[0][1]).replace(
            "| 中性（主推） | 60% |", "| 中性（主推） | 55% |")
        ok, reasons = _res(self.check, rep, self.snap)
        self.assertFalse(ok)
        self.assertTrue(any("漂移" in r for r in reasons), reasons)

    def test_enumeration_multi_prob_table_conflict(self):
        extra = ("\n### 复核表（第二张概率表）\n\n"
                 "| 情景 | 概率 | 目标价 | 动作 |\n|------|------|--------|------|\n"
                 "| 中性（复核） | 50% | 33.123~43.337 | 区间思路 |\n")
        rep = _panorama_report(_PANORAMA_ROWS_FLIP[0][1]) + extra
        ok, reasons = _res(self.check, rep, self.snap)
        self.assertFalse(ok)
        r = next(x for x in reasons if "漂移" in x)
        self.assertIn("60", r)   # 两张概率表的冲突值须同轮全数上桌
        self.assertIn("50", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
