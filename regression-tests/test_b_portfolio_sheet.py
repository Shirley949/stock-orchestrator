#!/usr/bin/env python3
"""b_portfolio_sheet 合集渲染契约测试（2026-10-09 Phase 6 批）。

执法面：title 两分支/表头逐字/DIR_ZH 同一对象/NONE 语义/触发表盘中盘后/零 hit/
触及后收回/账本四词状态机/盘中待定格/旧快照降级/selfcheck 篡改零写出/缺档严格/
allow-stale/未知方向/现价兜底——空态全覆盖。
离线合成快照 fixture（BP_SNAPSHOT_DIR 隔离），零网络。
"""
import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(os.path.dirname(HERE))
BP = os.path.join(HERE, "..", "scripts", "b_portfolio_sheet.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, os.path.join(SKILL_ROOT, "financial-data-routing"))
import b_portfolio_sheet as bp  # noqa: E402
import report_views as rv  # noqa: E402

V31_TAG = "平滑/过渡态（v3.1 参考线适用性中性；两方案差异历史均 <3%）"
V31_DECL = "本股当前为平滑/过渡态：v3.1 参考适用性中性（v3.1 仅适合少数平缓爬升股）"


def _mk_snap(code, name, direction="neutral", current=10.0, change_pct=1.0,
             low=None, mnt=0.5, action="NONE", end_pos="空仓", user_position=None,
             t0_status="ok", t0_rows=None, as_of_time="14:00:00",
             replay_pos="空仓", trades=None, v31_tag=V31_TAG, close=10.1,
             net_flow=0.5, include_t0=True):
    s = {"classification": {"stock_name": name},
         "s2_quote_kline": {"data": {"realtime_quote": {
             "current": current, "change_pct": change_pct, "low": low}},
             "b_head_unused": True},
         "s3_fund_flow": {"data": {"fund_flow": {"net_flow": net_flow}}},
         "s4_technical": {"data": {
             "b_head": {"direction": direction, "close": close,
                        "period_label": "2026-10-08"},
             "execution_shell": {
                 "today": {"action": action, "end_position": end_pos,
                           "trigger": "t"},
                 "results": {"v33_t11": {
                     "summary": {"end_position": replay_pos, "net_pnl": 0},
                     "trades": trades if trades is not None else []}},
                 "user_position": user_position,
                 "v31_declaration": {"tag": v31_tag, "declaration": V31_DECL,
                                     "weight": 0, "th_ep_dd": -15,
                                     "th_base_mult": 1.5}}}}}
    if include_t0:
        s["s4_technical"]["data"]["t0_check"] = {
            "status": t0_status, "rows": t0_rows or [],
            "as_of_date": "2026-10-09", "as_of_time": as_of_time,
            "context": {"main_net_today": mnt}}
    return s


def _hit(item="ATR 止损位", price=10.72, kind="below_stop", verdict="已触发",
         extreme=10.7, hit_time="09:30-10:30"):
    return {"item": item, "price": price, "kind": kind, "verdict": verdict,
            "today": {"hit": True, "extreme": extreme, "hit_time": hit_time}}


def _write_dir(td, snaps):
    d = os.path.join(td, "full")
    os.makedirs(d, exist_ok=True)
    for c, s in snaps.items():
        with open(os.path.join(d, f"{c}_20261009.json"), "w", encoding="utf-8") as fh:
            json.dump(s, fh, ensure_ascii=False)
    return d


def _run(td, snaps, label="t", codes=None, date="20261009", extra=()):
    if codes is None:
        codes = ",".join(snaps.keys())
    snap_dir = _write_dir(td, snaps)
    out = os.path.join(td, "out.md")
    env = dict(os.environ)
    env["BP_SNAPSHOT_DIR"] = snap_dir
    cmd = [sys.executable, BP, "--label", label, "--date", date, "-o", out, *extra]
    if codes:
        cmd += ["--codes", codes]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    md = open(out, encoding="utf-8").read() if os.path.exists(out) else None
    return r, md, out


class BPortfolioSheetTest(unittest.TestCase):
    def test_01_title_12_and_3(self):
        """title：12 票/3 票两分支（{m}-{d}{相位}{K}票合集）。"""
        snaps = {f"60000{i}": _mk_snap(f"60000{i}", f"票{i}") for i in range(1, 4)}
        r, md, _ = _run(tempfile.mkdtemp(), snaps, codes="600001,600002,600003")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# 10-9盘中3票合集", md)

    def test_02_table_headers_verbatim(self):
        """表头逐字：三表 + 块3 标题。"""
        snaps = {"600001": _mk_snap("600001", "票一")}
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 0, r.stderr)
        for h in ("| 股票 | 现价（元） | 今日 | 主力（亿） | 方向 | 今日动作 |",
                  "| 股票 | 仓位 | 档位 | 价位（元） | 当日实况 | 确认 |",
                  "| 股票 | 仓位 | 规则 | 参照价（元） | 当日实况 | 确认 |",
                  "## 账本总持仓（v3.3+T11 纸面仓）",
                  "## 机械触发 · 决策档（T-1 档位 × 当日实况 · 待收盘定格）",
                  "## 机械触发 · 持仓纪律（个人仓位 · 收盘确认为准）"):
            self.assertIn(h, md)

    def test_03_dir_zh_same_object(self):
        """同语义单实现：bp.DIR_ZH is rv.DIR_ZH（禁本地重写）。"""
        self.assertIs(bp.DIR_ZH, rv.DIR_ZH)

    def test_04_none_semantics_and_notes(self):
        """NONE（空仓）行 + 两注行（回放语义 + v3.1 判据照抄阈值）。"""
        snaps = {"600001": _mk_snap("600001", "票一")}
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| 票一 | 10.0 | +1.0% | +0.5 | 中性 | NONE（空仓） |", md)
        self.assertIn("> 今日动作=回放引擎截至 2026-10-08 收盘的纸面态"
                      "（盘中跑不含当日）——「NONE（空仓）」≠ 今天不该买，当日触发见下两表。", md)
        self.assertIn("判据 episode 回撤 ≤-15%（崩塌反转型）或 base_mult ≥1.5 倍"
                      "（透支高位型）即不适用，本批 0 票不适用。", md)

    def test_05_hit_rows_intraday(self):
        """表2 盘中：hit 行全集 + kind→确认映射 + 仓位格。"""
        up = {"shares": 1200, "cost": 12.29, "action": "HOLD", "ladder": 9.5,
              "atr_stop": 8.8, "reason": "持有"}
        snaps = {"600001": _mk_snap("600001", "票一", user_position=up, low=9.9,
                                    t0_rows=[_hit(), _hit(item="减仓带（压力1）",
                                                          price=11.0, kind="reduce_band",
                                                          verdict="已触及", extreme=11.1,
                                                          hit_time="10:30-11:30")])}
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| 票一 | 1200股 @成本12.29 | ATR 止损位·已触发 | 10.72 "
                      "| 今低 10.7 @09:30-10:30 | 收盘确认 |", md)
        self.assertIn("| 票一 | 1200股 @成本12.29 | 减仓带（压力1）·已触及 | 11.0 "
                      "| 今高 11.1 @10:30-11:30 | 触及即执行 |", md)

    def test_06_postclose_confirmation(self):
        """盘后：标题已收盘 + 确认列联动已收盘确认 + 持仓纪律确认联动。"""
        up = {"shares": 100, "cost": 10.0, "action": "SELL_ALL", "ladder": 11.0,
              "reason": "你的梯子触发（现价 9.9 ≤ 梯子 11.0）→ 清仓（盘中价触发，收盘确认）"}
        snaps = {"600001": _mk_snap("600001", "票一", current=9.9, low=9.8,
                                    user_position=up, t0_status="hidden",
                                    t0_rows=[_hit()])}
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# 10-9盘后1票合集", md)
        self.assertIn("## 机械触发 · 决策档（T-1 档位 × 当日实况 · 已收盘）", md)
        self.assertIn("| 今低 10.7 @09:30-10:30 | 已收盘确认 |", md)
        self.assertIn("| 票一 | 100股 @成本10.0 | 梯子清仓 | 11.0 "
                      "| 你的梯子触发（现价 9.9 ≤ 梯子 11.0）→ 清仓"
                      "（盘中价触发，收盘确认） | 已收盘确认 |", md)

    def test_07_zero_hit_row(self):
        """零 hit → 一行表（表永不省略）。"""
        snaps = {"600001": _mk_snap("600001", "票一",
                                    t0_rows=[{"item": "x", "price": 1,
                                              "today": {"hit": False}}])}
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("|—|—|—|—|—|今日无决策档触发（T-1 全部档位未破/未触及）|", md)

    def test_08_recover_row(self):
        """触及后收回：HOLD ∧ low<ladder ∧ cur≥ladder → 曾破/已收回 行。"""
        up = {"shares": 100, "cost": 12.0, "action": "HOLD", "ladder": 9.5,
              "reason": "持有"}
        snaps = {"600001": _mk_snap("600001", "票一", current=10.0, low=9.2,
                                    user_position=up)}
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| 票一 | 100股 @成本12.0 | 梯子清仓 | 9.5 "
                      "| 今低 9.2 曾破，现价 10.0 已收回 | 以收盘为准 |", md)

    def test_09_trade_words_state_machine(self):
        """账本四词：BUY→新增+ / BUY_ADD→加仓+ / SELL_PART→减仓− / SELL_ALL→清仓−。"""
        trades = [
            {"date": "2026-10-09", "action": "BUY", "price": 10.0, "shares": 100,
             "reason": "首仓"},
            {"date": "2026-10-09", "action": "BUY_ADD", "price": 10.5, "shares": 100,
             "reason": "加仓"},
            {"date": "2026-10-09", "action": "SELL_PART", "price": 11.0, "shares": 100,
             "reason": "部分止盈"},
            {"date": "2026-10-08", "action": "BUY", "price": 9.0, "shares": 100,
             "reason": "昨日不入"},
        ]
        up = {"shares": 200, "cost": 10.0, "action": "HOLD", "ladder": 8.0,
              "reason": "持有"}
        snaps = {"600001": _mk_snap("600001", "票一", user_position=up,
                                    t0_status="hidden", trades=trades)}
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("- 票一 新增+ 100股 @10.0（首仓）", md)
        self.assertIn("- 票一 加仓+ 100股 @10.5（加仓）", md)
        self.assertIn("- 票一 减仓− 100股 @11.0（部分止盈）", md)
        self.assertNotIn("@9.0", md)   # 非当日 trades 不入

    def test_10_intraday_pending_line(self):
        """盘中：今日尚无账本变动（待收盘定格）行。"""
        snaps = {"600001": _mk_snap("600001", "票一")}
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("- 当前：全部空仓（1 票回放期末均空仓）", md)
        self.assertIn("- 今日：尚无账本变动（回放截至 2026-10-08，盘中运行待收盘定格；"
                      "盘中触发见上两表）", md)

    def test_11_legacy_no_trades_postclose_degrade(self):
        """盘后 + 旧快照缺 trades 键 → 降级尾注 + exit 3。"""
        snaps = {"600001": _mk_snap("600001", "票一", t0_status="hidden")}
        del snaps["600001"]["s4_technical"]["data"]["execution_shell"]["results"]["v33_t11"]["trades"]
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("trades 键缺档（旧快照），当日账本变动不可考", md)

    def test_12_selfcheck_tamper_zero_write(self):
        """selfcheck 篡改 → False（对拍不等逐条打印）。"""
        with tempfile.TemporaryDirectory() as td:
            snap_dir = _write_dir(td, {"600001": _mk_snap("600001", "票一")})
            bp.SNAP_DIR = snap_dir   # 进程内调用需覆写（子进程走 env）
            snaps, paths, _ = bp.load_snapshots(["600001"], "20261009", False)
            bp._CELLS.clear()
            bp._CELLS.append(("600001", "s2_quote_kline.data.realtime_quote.current",
                              "现价", 999.0))   # 篡改值 ≠ 落盘 10.0
            self.assertFalse(bp.selfcheck(snaps, paths))

    def test_13_missing_strict_and_allow_stale(self):
        """缺当日档：严格 exit 1；--allow-stale 取旧档+披露 exit 3。"""
        snaps = {"600001": _mk_snap("600001", "票一")}
        with tempfile.TemporaryDirectory() as td:
            snap_dir = _write_dir(td, snaps)
            # 旧档改名到 20261008
            os.rename(os.path.join(snap_dir, "600001_20261009.json"),
                      os.path.join(snap_dir, "600001_20261008.json"))
            env = dict(os.environ)
            env["BP_SNAPSHOT_DIR"] = snap_dir
            out = os.path.join(td, "o.md")
            r = subprocess.run([sys.executable, BP, "--label", "t",
                                "--codes", "600001",
                                "--date", "20261009", "-o", out],
                               capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r.returncode, 1)
            self.assertFalse(os.path.exists(out))
            out2 = os.path.join(td, "o2.md")
            r2 = subprocess.run([sys.executable, BP, "--label", "t",
                                 "--codes", "600001",
                                 "--date", "20261009", "-o", out2,
                                 "--allow-stale"],
                                capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r2.returncode, 3, r2.stderr)
            self.assertIn("降级用旧档 600001←20261008",
                          open(out2, encoding="utf-8").read())

    def test_14_unknown_direction_raw(self):
        """未知 direction 原文直出（禁编中文）。"""
        snaps = {"600001": _mk_snap("600001", "票一", direction="bullish_x")}
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| bullish_x |", md)

    def test_15_current_fallback_chain(self):
        """现价兜底链：rq.current None → b_head.close + 尾注 + exit 3。"""
        snaps = {"600001": _mk_snap("600001", "票一", current=None)}
        r, md, _ = _run(tempfile.mkdtemp(), snaps)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("| 票一 | 10.1 |", md)
        self.assertIn("现价缺 rq.current → 取 b_head.close 兜底", md)

    def test_16_v31_not_applicable_named(self):
        """v3.1 不适用批：注内点名 + N/K 中性计数。"""
        snaps = {"600001": _mk_snap("600001", "票一"),
                 "600002": _mk_snap("600002", "票二",
                                    v31_tag="崩塌反转型（v3.3 主方案适用；v3.1 平滑型参考失配）")}
        r, md, _ = _run(tempfile.mkdtemp(), snaps, codes="600001,600002")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1/2 票适用性中性", md)
        self.assertIn("本批 1 票不适用：票二（✗崩塌反转型）。", md)


if __name__ == "__main__":
    unittest.main()
