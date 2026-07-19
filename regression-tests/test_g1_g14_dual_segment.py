#!/usr/bin/env python3
"""
test_g1_g14_dual_segment.py —— G1/G14 四段 Gate（技术面完整性 + TD 数据驱动）单测

2026-07 重构（plan cozy-stargazing-raccoon 阶段九）。覆盖拉取/存放/读取/消费全流程：
  G1（10 case）：
    01 正常 PASS（s4 ok + 技术词 + 量价消费）
    02 漏技术词 FAIL
    03 北交所 never_traded PASS（三态放行）
    04 停牌 no_trade PASS（tq=no_trade 不强求换手；s4 ok 须技术词）
    05 限流 fetch_failed FAIL
    06 never_traded 编造具体数值 FAIL（禁编造）
    07 never_traded 诚实标注 PASS
    08 港股 00700 not_applicable + never_traded PASS
    09 tq=ok 无换手 FAIL（603663 漏消费根因）
    10 旧 snapshot 退化（无 s4 → legacy 信号矩阵检查）
  G14（5 case）：setup 信号+逐根展示 / never_traded / 无信号提及 TD / 有信号无展示 FAIL / 旧退化

零网络、零外部文件依赖（snapshot 内联）。__file__ 相对定位 gate_definitions。
运行：python3 test_g1_g14_dual_segment.py  或经 run_regression.sh 串联。
"""
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_GATE_LIB = _HERE.parent / "scripts" / "lib"
import sys
sys.path.insert(0, str(_GATE_LIB))

import gate_definitions as g


# ---------------- snapshot/report helpers ----------------

def _s4(status="ok", signal_type="normal", technical=None, td=None):
    """构造 s4_technical 信封（三态：ok/failed/never_traded）。
    ok 态默认填 technical stub（G1②存放检查要求 data 非空）；never_traded/failed 不填。"""
    data = {}
    if technical is not None:
        data["technical"] = technical
    elif status == "ok":
        data["technical"] = {"macd": {"DIF": 0.52}}   # ok 态默认有技术数据
    if td is not None:
        data["td"] = td
    return {"s4_technical": {"status": status, "signal_type": signal_type, "data": data}}


def _tq(status="ok", turnover_pct=2.67):
    """构造 realtime_quote 四态信封（_turnover_status: ok/no_trade/not_applicable/fetch_failed）。"""
    return {"s2_quote_kline": {"data": {"realtime_quote": {
        "_turnover_status": status, "turnover_pct": turnover_pct}}}}


REP_FULL = (
    "技术面：MACD金叉 DIF=0.52，KDJ超卖 J=18，RSI=42，均线多头 MA20=38.5。"
    "TD 买Setup 9/9完成，Countdown 3/13。换手率2.67%，量比1.5，成交额7亿。"
)
REP_NO_TECH = "基本面良好，营收增长，利润回升。"           # 无任何技术词
REP_NO_TURN = "MACD金叉，KDJ超卖，RSI=42，均线多头，TD Setup 9。"  # 有技术词无换手
REP_NEVER_HONEST = "北交所股票，技术指标数据不可得（never_traded），仅做基本面分析。"
REP_NEVER_FORGED = "北交所股票，MACD DIF=0.52，KDJ K=85，RSI=72.3，均线多头排列。"  # never_traded 却编造数值
REP_NOSIG = "当前无TD信号，趋势中性。"                    # G14 无信号


class TestG1FourSegment(unittest.TestCase):
    """G1 技术面完整性（拉取/存放/读取/消费四段 + 三态 + 禁编造）。"""

    def test_01_normal_pass(self):
        self.assertTrue(g.check_g1(REP_FULL, {**_s4(), **_tq()}))

    def test_02_missing_tech_words_fail(self):
        self.assertFalse(g.check_g1(REP_NO_TECH, {**_s4(), **_tq()}))

    def test_03_bj_never_traded_pass(self):
        self.assertTrue(g.check_g1(
            REP_NEVER_HONEST, {**_s4("never_traded", "never_traded"), **_tq("not_applicable")}))

    def test_04_halt_no_trade_pass(self):
        # 停牌 tq=no_trade（不强求换手）+ s4 ok 须技术词
        self.assertTrue(g.check_g1(REP_NO_TURN, {**_s4("ok"), **_tq("no_trade")}))

    def test_05_fetch_failed_fail(self):
        self.assertFalse(g.check_g1(
            REP_FULL, {**_s4("failed", "fetch_failed"), **_tq()}))

    def test_06_never_traded_fabrication_fail(self):
        # never_traded + 报告编造具体数值 → FAIL（禁编造）
        self.assertFalse(g.check_g1(
            REP_NEVER_FORGED, {**_s4("never_traded", "never_traded"), **_tq("not_applicable")}))

    def test_07_never_traded_honest_pass(self):
        self.assertTrue(g.check_g1(
            REP_NEVER_HONEST, {**_s4("never_traded", "never_traded"), **_tq("not_applicable")}))

    def test_08_hk_00700_not_applicable_pass(self):
        # 港股 5 位码 → tq=not_applicable + s4 never_traded → PASS
        self.assertTrue(g.check_g1(
            REP_NEVER_HONEST, {**_s4("never_traded", "never_traded"), **_tq("not_applicable")}))

    def test_09_tq_ok_no_turnover_fail(self):
        # 603663 根因：tq=ok 却没消费换手/量比/成交额 → FAIL
        self.assertFalse(g.check_g1(REP_NO_TURN, {**_s4("ok"), **_tq("ok")}))

    def test_10_legacy_snapshot_degrade(self):
        # 旧 snapshot 无 s4 → 退化信号矩阵行数检查（保 fixture 漏报=0）
        rep_legacy = "信号矩阵 短期中期长期\n|a|b|c|\n|1|2|3|\n" * 4
        self.assertTrue(g.check_g1(rep_legacy, {}))

    def test_11_store_empty_fail(self):
        # s4 status=ok 但 data 全空（technical/td 都无）→ FAIL（未落盘）
        self.assertFalse(g.check_g1(REP_FULL, {**_s4("ok"), **_tq(), "s4_technical": {"status": "ok", "data": {}}}))


class TestG14DataDriven(unittest.TestCase):
    """G14 TD 序列数据驱动（s4.td）+ 报告逐根展示。"""

    def test_01_setup_signal_with_count_pass(self):
        td = {"summary": {"stage": "买Setup 9/9"}}
        self.assertTrue(g.check_g14(REP_FULL, _s4(td=td)))

    def test_02_never_traded_pass(self):
        self.assertTrue(g.check_g14(REP_FULL, _s4("never_traded", "never_traded")))

    def test_03_no_signal_mention_td_pass(self):
        td = {"summary": {"stage": "无信号"}}
        self.assertTrue(g.check_g14(REP_NOSIG, _s4(td=td)))

    def test_04_signal_no_display_fail(self):
        # 有信号（stage≠无信号）但报告无 TD 计数展示 → FAIL
        td = {"summary": {"stage": "买Countdown 6/13"}}
        self.assertFalse(g.check_g14("技术面 MACD 金叉，均线多头。", _s4(td=td)))

    def test_05_no_td_in_report_fail(self):
        td = {"summary": {"stage": "买Setup 9/9"}}
        self.assertFalse(g.check_g14("技术面 MACD 金叉，无 TD 内容。", _s4(td=td)))

    def test_06_legacy_degrade(self):
        # 旧 snapshot 无 td → 退化（TD + ≥9 计数行）
        rep = "TD 计数1\nTD 计数2\nTD 计数3\nTD 计数4\nTD 计数5\nTD 计数6\nTD 计数7\nTD 计数8\nTD 计数9\n"
        self.assertTrue(g.check_g14(rep, {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
