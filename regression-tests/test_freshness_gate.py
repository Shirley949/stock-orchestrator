#!/usr/bin/env python3
"""
test_freshness_gate.py —— Gate 级数值新鲜度回归（plan Step 7）

覆盖三道 freshness 兜底层（统一 latest_period 信封消费）：
  - **G30#1 户数 stale-value**（★ bug 原案）：snapshot 128685 vs 报告"10.12万"→ #1 FAIL
  - **G37 宏观 presence**：PMI/PPI/M2 latest_period 覆盖率 ≥ 2/3（数值窄带/派生口径不做，见 gate 注释）
  - **G38 分红有效性**：每股股利数值对齐（元/每10股）OR [src:]；不分红真空豁免
  - **G39 分类单源执法**：report-layer 读 classification——类型词 / forbidden_metric 估值框架（周期禁PE·成长禁PB）/ macro_sensitivity==high 须引宏观（C6，2026-07-22）

零网络、纯离线。gate 运行时层 fixtures 不在时由本单测 + test_freshness_helper.py 兜底 freshness 逻辑。
运行：python3 test_freshness_gate.py（或经 run_regression.sh 串联）。
"""
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS / "lib"))

import gate_definitions as gd


# ============================================================
# G30#1 户数 stale-value（★ bug 原案 gate 级回归）
# ============================================================

class TestG30HolderStaleValue(unittest.TestCase):
    """G30 #1 数值新鲜度：户数 snapshot=128685 vs 报告"10.12万"(=101200) → #1 FAIL。

    复刻五洲新春 bug（plan 验收 step 5 / 阶段 4）：报告引 stale 值须被 G30#1 抓到。
    """

    def _snap(self, holder=128685):
        return {"s8_a_share": {"data": {"shareholder_count": {
            "latest_period": {"value": holder, "period_label": "2026Q1"}}}},
            "classification": {"primary_type": "成长"}}

    def _capstone(self, holder_line):
        # 最小 capstone：证据全景（含户数）+ 三档情景表（让 #2/#3 不喧宾夺主）
        return (
            "# 综合研判\n\n## 证据全景\n"
            f"- 技术面：MACD 金叉。\n- {holder_line}\n\n"
            "## 三档情景\n"
            "- 乐观（40%）：目标价 65 元。应对：加仓。须克服的反方：估值偏高。\n"
            "- 中性（35%）：目标价 55 元。应对：持有。须克服的反方：增速放缓。\n"
            "- 悲观（25%）：目标价 45 元。应对：观望。须克服的反方：题材兑现。\n\n"
            "| 情景 | 概率 | 目标价 | 应对动作 | 反方证据 | 成立条件 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| 乐观 | 40% | 65元 | 加仓 | 估值偏高 | 量能持续 |\n"
            "| 中性 | 35% | 55元 | 持有 | 增速放缓 | 区间震荡 |\n"
            "| 悲观 | 25% | 45元 | 观望 | 题材落空 | 跌破支撑 |\n"
        )

    def test_stale_value_1012wan_fail(self):
        """★ 核心 bug case：报告"10.12万"(=101200) vs snap 128685 → 偏差 21% → #1 FAIL。"""
        r = gd._g30_run(self._capstone("股东户数 10.12万，环比+5%"), self._snap())
        self.assertIn(1, r["failed"])
        self.assertTrue(any("户数" in x and "stale" in x for x in r["reasons"]))

    def test_fresh_value_pass(self):
        """报告引正确值 128,685 → #1 不因户数 stale FAIL。"""
        r = gd._g30_run(self._capstone("股东户数 128,685 户，环比+27.1%"), self._snap())
        self.assertFalse(any("数值新鲜度" in x for x in r["reasons"]))

    def test_fresh_value_wan_unit_pass(self):
        """报告"12.87万"(×1e4=128700，偏差<1%) → 万单位对齐 PASS。"""
        r = gd._g30_run(self._capstone("股东户数 12.87万，环比+27.1%"), self._snap())
        self.assertFalse(any("数值新鲜度" in x for x in r["reasons"]))

    def test_stale_with_src_exempt(self):
        """stale 值但行带 [src:] 溯源 → 豁免（精确值交 G21）。"""
        r = gd._g30_run(self._capstone("股东户数 10.12万 [src: snapshot.s8_a_share]"), self._snap())
        self.assertFalse(any("数值新鲜度" in x for x in r["reasons"]))

    def test_not_mentioned_no_stale_finding(self):
        """报告完全不提户数（只提资金流）→ 不触发户数 stale（覆盖遗漏归 miss_quant，非此处）。"""
        r = gd._g30_run(self._capstone("资金流：主力净流入。"), self._snap())
        self.assertFalse(any("户数" in x for x in r["reasons"]))


class TestG30CloseStaleValue(unittest.TestCase):
    """G30 #1 close 数值新鲜度（plan §5.2 扩展）：daily_kline latest_period.value=收盘价，
    报告引旧收盘价 → #1 FAIL。close 是报告引用最频繁的数字，stale 风险高。"""

    def _snap(self, close=54.07):
        return {"s2_quote_kline": {"data": {"daily_kline": {
            "latest_period": {"value": close, "period_label": "2026-07-17"}}}},
            "classification": {"primary_type": "成长"}}

    def _cap(self, price_line):
        return (
            "# 综合研判\n\n## 证据全景\n"
            f"- 技术面：{price_line}\n\n"
            "## 三档情景\n"
            "- 乐观（40%）：目标价 65 元。应对：加仓。须克服的反方：估值偏高。\n"
            "- 中性（35%）：目标价 55 元。应对：持有。须克服的反方：增速放缓。\n"
            "- 悲观（25%）：目标价 45 元。应对：观望。须克服的反方：题材兑现。\n\n"
            "| 情景 | 概率 | 目标价 | 应对动作 | 反方证据 | 成立条件 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| 乐观 | 40% | 65元 | 加仓 | 估值偏高 | 量能持续 |\n"
            "| 中性 | 35% | 55元 | 持有 | 增速放缓 | 区间震荡 |\n"
            "| 悲观 | 25% | 45元 | 观望 | 题材落空 | 跌破支撑 |\n"
        )

    def test_close_fresh_pass(self):
        r = gd._g30_run(self._cap("现价 54.07 元，涨2.3%。"), self._snap())
        self.assertFalse(any("数值新鲜度" in x for x in r["reasons"]))

    def test_close_stale_fail(self):
        """snap 54.07，报告引旧 40.00 → 偏差 35% → #1 FAIL（消息保留小数 snapshot=54.07）。"""
        r = gd._g30_run(self._cap("现价 40.00 元，较年内低点反弹。"), self._snap())
        vf = [x for x in r["reasons"] if "数值新鲜度" in x]
        self.assertTrue(vf)
        self.assertIn("现价", vf[0])
        self.assertIn("54.07", vf[0])   # 小数格式保留
        self.assertIn(1, r["failed"])

    def test_close_not_mentioned_pass(self):
        """报告不提现价（只提资金流）→ 不触发 close stale（覆盖归 miss_quant）。"""
        r = gd._g30_run(self._cap("资金流主力净流入，量能放大。"), self._snap())
        self.assertFalse(any("现价" in x or "收盘价" in x for x in r["reasons"]))

    def test_close_stale_with_src_exempt(self):
        r = gd._g30_run(self._cap("现价 40.00 元 [src: snapshot.s2_quote_kline]。"), self._snap())
        self.assertFalse(any("数值新鲜度" in x for x in r["reasons"]))


# ============================================================
# G37 宏观数据有效性（presence ≥ 2/3）
# ============================================================

class TestG37MacroPresence(unittest.TestCase):
    """G37: PMI/PPI/M2 latest_period 覆盖率 ≥ 2/3。镜像 G31，纯数据层 gate。"""

    def _macro(self, pmi=None, ppi=None, m2=None):
        d = {"s6_macro": {"data": {}}}
        for k, v in (("pmi", pmi), ("ppi", ppi), ("m2", m2)):
            if v is not None:
                d["s6_macro"]["data"][k] = {"status": "ok",
                    "latest_period": {"value": v, "period_label": "2026年6月"}}
        return d

    def test_three_of_three_pass(self):
        self.assertTrue(gd.check_g37("PMI 50.3", self._macro(50.3, 104.1, 3e6)))

    def test_two_of_three_pass(self):
        self.assertTrue(gd.check_g37("", self._macro(50.3, 104.1)))

    def test_one_of_three_fail(self):
        """akshare 限流两指标挂 → 仅 1/3 → FAIL。"""
        self.assertFalse(gd.check_g37("PMI 50.3", self._macro(50.3)))

    def test_zero_of_three_fail(self):
        self.assertFalse(gd.check_g37("", {"s6_macro": {"data": {}}}))

    def test_independent_of_report(self):
        """presence 是数据层 gate，不读 report 内容（镜像 G31）。"""
        self.assertTrue(gd.check_g37("", self._macro(50.3, 104.1, 3e6)))


# ============================================================
# G38 分红有效性（每股股利数值新鲜度）
# ============================================================

class TestG38DividendValidity(unittest.TestCase):
    """G38: 每股股利数值对齐（元/每10股换算）OR [src:]；不分红真空豁免。"""

    def _div(self, per_share=None):
        if per_share is None:
            return {"valuation_snapshot": {"data": {"quote": {}}}}
        return {"valuation_snapshot": {"data": {"quote": {
            "dividend_latest_period": {"value": {"每股股利": per_share}}}}}}

    def test_per_share_fresh_pass(self):
        self.assertTrue(gd.check_g38("每股股利 0.12 元。", self._div(0.12)))

    def test_per_ten_share_aligned_pass(self):
        """报告"每10股派1.2元"= 0.12×10 → ×0.1 换算到每股 0.12 对齐。"""
        self.assertTrue(gd.check_g38("每10股派发现金红利 1.2 元（含税）。", self._div(0.12)))

    def test_stale_value_fail(self):
        """snap 0.12，报告引旧 0.05 → 偏差 58% → FAIL。"""
        self.assertFalse(gd.check_g38("每股股利 0.05 元（上年）。", self._div(0.12)))

    def test_vacuum_no_dividend_pass(self):
        """不分红公司（无 dividend_latest_period）→ 真空豁免。"""
        self.assertTrue(gd.check_g38("公司不分红。", self._div(None)))

    def test_yield_only_not_checked_pass(self):
        """只提"股息率%"（派生口径，非每股股利绝对值）→ 不校验数值。"""
        self.assertTrue(gd.check_g38("股息率 0.8%，低于国债。", self._div(0.12)))

    def test_not_mentioned_pass(self):
        """有分红历史但报告不提 → PASS（消费覆盖归 G30#1 估值维度，非 G38）。"""
        self.assertTrue(gd.check_g38("基本面良好。", self._div(0.12)))

    def test_stale_with_src_exempt(self):
        """stale 值 + [src:] → 豁免。"""
        self.assertTrue(gd.check_g38("每股股利 0.05 元 [src: snapshot]", self._div(0.12)))

    def test_negation_pass(self):
        """否定=有效「无分红」结论（如「几乎不分红」），非 stale 旧值 → 放行。"""
        self.assertTrue(gd.check_g38("股息率 0.147%（几乎不分红）。", self._div(0.12)))
        self.assertTrue(gd.check_g38("公司近年未分红。", self._div(0.12)))


# ============================================================
# 注册完整性（防 G37/G38/G39 注册漏项）
# ============================================================

class TestG37G39Registration(unittest.TestCase):
    """G37/G38/G39 须全注册到 5 处（profile_quick 不含，是当日技术面模式）。"""

    def test_registered_everywhere(self):
        for attr in ("GATE_CHECKERS", "GATE_WEIGHTS", "ALL_GATES", "SOFT_GATES"):
            for g in ("G37", "G38", "G39"):
                self.assertIn(g, getattr(gd, attr), f"{g} in {attr}")
        self.assertIs(gd.GATE_CHECKERS["G37"], gd.check_g37)
        self.assertIs(gd.GATE_CHECKERS["G38"], gd.check_g38)
        self.assertIs(gd.GATE_CHECKERS["G39"], gd.check_g39)
        for g in ("G37", "G38", "G39"):
            self.assertEqual(gd.GATE_WEIGHTS[g], 1)

    def test_in_full_not_quick(self):
        for g in ("G37", "G38", "G39"):
            self.assertIn(g, gd.PROFILES["profile_full"]["gates"])
            self.assertNotIn(g, gd.PROFILES["profile_quick"]["gates"])


# ============================================================
# G39 分类单源执法（report-layer，读 snapshot.classification）
# ============================================================

def _cls(primary, **kw):
    base = {"primary_type": primary}
    base.update(kw)
    return {"classification": base}


class TestG39Classification(unittest.TestCase):
    """G39 三查：#1 类型词 / #2 forbidden_metric 估值框架 / #3 macro_sensitivity==high 宏观引用。"""

    def test_vacuum_pass(self):
        """classification 缺失或 primary_type=None → PASS（LLM 兜底，不强执法）。"""
        self.assertTrue(gd.check_g39("任意报告", {}))
        self.assertTrue(gd.check_g39("任意报告", {"classification": {"primary_type": None}}))

    def test_check1_type_word(self):
        """#1 周期股报告须含"周期"。"""
        c = _cls("周期股", forbidden_metric="PE做主要", macro_sensitivity="high")
        # 含类型词 + PB(框架) + PPI(宏观) → PASS
        self.assertTrue(gd.check_g39("标的属周期股，PB 1.2倍，PPI 同比-2%", c))
        # 缺类型词 → FAIL
        self.assertFalse(gd.check_g39("标的属化工板块，PB 1.2倍，PPI -2%", c))

    def test_check2_valuation_framework_cyclic(self):
        """#2 周期股 forbidden=PE做主要 → 须引 PB/EV-EBITDA/股息率（非只 PE）。"""
        c = _cls("周期股", forbidden_metric="PE做主要", macro_sensitivity="high")
        # 引 PB → PASS（含类型词+PPI）
        self.assertTrue(gd.check_g39("周期股 PB 1.2倍，PPI -2%", c))
        # 只引 PE 不引推荐框架 → FAIL
        self.assertFalse(gd.check_g39("周期股 PE 15倍，PPI -2%", c))

    def test_check2_valuation_framework_growth(self):
        """#2 成长股 forbidden=PB做主要 → 须引 PS/PEG/DCF。"""
        c = _cls("成长股", forbidden_metric="PB做主要", macro_sensitivity="medium")
        # 成长 macro=medium → #3 不触发；引 PS → PASS
        self.assertTrue(gd.check_g39("成长股 PS 8倍，高增长", c))
        # 只引 PB → FAIL
        self.assertFalse(gd.check_g39("成长股 PB 3倍，高增长", c))

    def test_check2_mixed(self):
        """#2 混合型 is_mixed → 须引 PS/远期PE（混合框架词）。"""
        c = _cls("成长股", is_mixed=True, secondary_type="周期股",
                 forbidden_metric="PB做主要", macro_sensitivity="high", preferred_macro="PPI")
        # 引 远期PE + PPI → PASS（类型词"成长"在）
        self.assertTrue(gd.check_g39("成长+周期混合，远期PE 25倍，PPI -2%", c))
        # 只引 PB → FAIL（#2 框架）
        self.assertFalse(gd.check_g39("成长混合 PB 3倍，PPI -2%", c))

    def test_check2_skipped_when_no_forbidden(self):
        """#2 消费/防御 forbidden=None → 跳过框架查（无硬禁）。"""
        consume = _cls("消费股", macro_sensitivity="low")  # forbidden=None, macro=low
        # 消费股无框架要求、无宏观要求 → 任意（含类型词即可）
        self.assertTrue(gd.check_g39("消费股 茅台酒营收增长", consume))
        defend = _cls("防御股", macro_sensitivity="low")
        self.assertTrue(gd.check_g39("防御股 高股息现金流稳定", defend))

    def test_check3_macro_citation(self):
        """#3 macro_sensitivity==high（周期/金融/混合）→ 须引 ≥1 宏观。"""
        c = _cls("金融股", forbidden_metric="PE做主要", macro_sensitivity="high", preferred_macro="M2")
        # 引 PB(框架) + M2(宏观) → PASS
        self.assertTrue(gd.check_g39("金融股 PB 1.5倍，不良率 1.2%，M2 同比+8%", c))
        # 缺宏观 → FAIL（#3 反片面）
        self.assertFalse(gd.check_g39("金融股 PB 1.5倍，不良率 1.2%，业绩稳健", c))

    def test_realcase_301217_mixed(self):
        """301217 铜冠铜箔（成长→混合）真实 classification：须引 PS/远期PE + PPI。"""
        c = {"classification": {"primary_type": "成长股", "is_mixed": True, "secondary_type": "周期股",
                                "macro_sensitivity": "high", "preferred_macro": "PPI",
                                "valuation_framework": "PS/远期PE", "forbidden_metric": "PB做主要"}}
        self.assertTrue(gd.check_g39("标的属成长+周期混合股，远期PE 30倍，PPI 当月同比-2.3%", c))
        # 缺宏观 → FAIL
        self.assertFalse(gd.check_g39("成长混合股，远期PE 30倍，PCB铜箔放量", c))


if __name__ == "__main__":
    unittest.main(verbosity=2)
