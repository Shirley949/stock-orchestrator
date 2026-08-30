# -*- coding: utf-8 -*-
"""第3批 F2/F3 族清扫两极用例（2026-08-30）：新收集路径 FAIL 必 fires + 干净输入 PASS。

覆盖 11 门收集化改造 + G63 词表扩「阻力」的直调两极——每门至少一对正反例，
FAIL 侧断言 reasons 含具体信息（行摘录/真值/维度名），证明「收集后丢弃」已灭。
判决面由 /tmp/replay 23 用例重放 + HEAD A/B 保证零翻转；本文件只钉 reasons 面。
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
from gate_definitions import (
    check_g15, check_g16, check_g23, check_g53, check_g54, check_g56,
    check_g57, check_g58, check_g60, check_g61, check_g63, check_g66, GateResult)


def _res(r):
    """gate 返回值 → (passed, reasons)：bool 与 GateResult(dict 子类) 统一。"""
    if isinstance(r, GateResult):
        return bool(r.get("passed")), list(r.get("reasons") or [])
    return bool(r), []


def _cl_snap(v_yuan=200_000_000):
    return {"s1_financial": {"data": {"balance_sheet": {"data": [{"合同负债": v_yuan}]}}}}


class G16ConflictCollection(unittest.TestCase):
    def test_fail_single_and_multi_conflict(self):
        # 反例①单冲突：8.5亿 vs 真值 2亿（偏离>50%，无 [src:]）→ FAIL 且 reason 带真值
        p, rs = _res(check_g16("合同负债 8.5 亿，环比抬升。", _cl_snap()))
        self.assertFalse(p)
        self.assertIn("8.5亿 vs snapshot 真值 2.00亿", rs[0])
        # 反例②双冲突：两条全量收集（旧代码只报首条即早退）
        p, rs = _res(check_g16("合同负债 8.5 亿。\n合同负债 0.5 亿。", _cl_snap()))
        self.assertFalse(p)
        self.assertEqual(len(rs), 2)

    def test_fail_six_conflicts_tail_note(self):
        # 6 条冲突 → top5 + 「另有 1 处」尾注（镜像 G63 范式）
        rep = "\n".join(f"合同负债 {v} 亿（第{i}处）。" for i, v in enumerate([8.5, 0.5, 9.9, 0.1, 7.7, 6.6]))
        p, rs = _res(check_g16(rep, _cl_snap()))
        self.assertFalse(p)
        self.assertEqual(len(rs), 6)
        self.assertIn("另有 1 处", rs[-1])

    def test_pass_aligned_value(self):
        # 正例：对齐真值 + 核对关键词 → PASS
        self.assertTrue(check_g16("合同负债 2.00 亿，与订单核对无偏差。", _cl_snap()))


class G15PeerFabrication(unittest.TestCase):
    SNAP = {"s11_peer": {"data": {"status": "missing", "discovered_peer_codes": []}}}

    def test_fail_fabrication_reason(self):
        p, rs = _res(check_g15("同业对比：可比公司 PE:15.2，ROE:8。", self.SNAP))
        self.assertFalse(p)
        self.assertIn("无 peer 数据", rs[0])
        self.assertIn("编造", rs[0])

    def test_pass_no_peer_number(self):
        # 正例：有同业措辞但无 peer 财务数字（诚实降级）→ PASS
        self.assertTrue(check_g15("同业对比数据不可得（本次未拉取）。", self.SNAP))
        # 正例：跑了但限流 + 诚实披露 → PASS（discovered 非空须含限流词）
        self.assertTrue(check_g15("同业对比数据因限流不可得。",
                                  {"s11_peer": {"data": {"status": "missing",
                                                         "discovered_peer_codes": ["300308"]}}}))


class G23DimCoverage(unittest.TestCase):
    def test_fail_reports_missing_dims(self):
        snap = {"_quality_markers": {"D3_dividend": {"status": "ok"}}}   # 仅 D3 ok，阈值 2
        p, rs = _res(check_g23("任意报告", snap))
        self.assertFalse(p)
        self.assertIn("1/2", rs[0])
        for dim in ("D4股东", "D5分产品", "D6分地区"):
            self.assertIn(dim, rs[0])          # 三个缺口全量报（旧裸 False 丢弃）

    def test_pass_meets_threshold(self):
        snap = {"_quality_markers": {"D3_dividend": {"status": "ok"},
                                     "D4_holders": {"status": "ok"}}}
        self.assertTrue(check_g23("报告含实控人表述。", snap))


class G53VolumePriceCollection(unittest.TestCase):
    REP = "## 技术面\nK线 均线多头，盘中放量而日终缩量，量价背离。"

    def _snap(self, vp):
        return {"s4_technical": {"data": {"volume_price": vp}}}

    def test_fail_both_collected(self):
        # 放量+缩量同时零支撑 → 一轮报两条（旧代码裸 False 只报/丢一条）。
        # 支撑要件设计：vm=None（>1 支撑放量 / <1 支撑缩量 均不成立），vr=0.9（不>1）
        vp = {"volume_state": "平量", "volume_ratio_rt": 0.9, "volume_vs_ma20": None,
              "consistency": "", "divergence": ""}
        p, rs = _res(check_g53(self.REP, self._snap(vp)))
        self.assertFalse(p)
        self.assertEqual(len(rs), 2)
        self.assertIn("「放量」零支撑", rs[0])
        self.assertIn("「缩量」零支撑", rs[1])
        self.assertIn("volume_state=平量", rs[0])      # 真值入 reason

    def test_pass_supported(self):
        # 正例：只写「放量」且 volume_state=放量 支撑 → PASS（双口径各自寻支撑）
        rep = "## 技术面\nK线 均线多头，盘中放量，量能充足。"
        self.assertTrue(check_g53(rep, self._snap({"volume_state": "放量",
                                                   "volume_ratio_rt": 1.8})))


class G54StateTypeCollection(unittest.TestCase):
    REP = "## 技术面\n均线 MACD 环境：上升趋势，ADX 走强。"

    def _snap(self, state):
        return {"s4_technical": {"data": {"signals": {"state": state}}}}

    def test_fail_bad_types_collected(self):
        # 两键非字符串 → 全量收集（旧裸 False）
        p, rs = _res(check_g54(self.REP, self._snap({"adx_state": 123, "bias_state": "中性",
                                                     "obv_trend": ["up"]})))
        self.assertFalse(p)
        self.assertEqual(len(rs), 2)
        self.assertIn("adx_state 非 None 但也不是字符串（int）", rs[0])
        self.assertIn("obv_trend 非 None 但也不是字符串（list）", rs[1])

    def test_pass_all_strings(self):
        self.assertTrue(check_g54(self.REP, self._snap({"adx_state": "上升趋势",
                                                        "obv_trend": "上升"})))


class G56FiveBlocksCollection(unittest.TestCase):
    def test_fail_reports_all_missing_blocks(self):
        rep = "## 标的概况\n类型：成长股，估值框架待展开。\n"
        p, rs = _res(check_g56(rep, {}))
        self.assertFalse(p)
        self.assertEqual(len(rs), 4)                    # 主营/历史/当前/同行 全量报
        for name in ("主营/业务", "历史阶段", "当前阶段定位", "同行差异化"):
            self.assertTrue(any(name in r for r in rs))

    def test_pass_all_blocks(self):
        rep = ("## 标的概况\n类型：成长。\n主营：光模块。\n历史：2011 上市。\n"
               "当前所处阶段定位：放量初期。\n同行差异化：对标龙头。\n")
        self.assertTrue(check_g56(rep, {}))


class G57GrowthTierFabrication(unittest.TestCase):
    def test_fail_six_lines_tail_note(self):
        rep = "\n".join(["公司预增 50%，展现高成长动能。"] * 6)
        p, rs = _res(check_g57(rep, {}))                # growth_tier 缺失 → None → 反编造臂
        self.assertFalse(p)
        self.assertEqual(len(rs), 6)
        self.assertIn("growth_tier=None", rs[0])
        self.assertIn("另有 1 处", rs[-1])

    def test_pass_clean_and_consumed(self):
        self.assertTrue(check_g57("行业景气，无业绩预告表述。", {}))          # 反例侧正例
        self.assertTrue(check_g57("业绩预告预增，高增长可期。",
                                  {"consensus_forecast": {"data": {"company_guidance": {
                                      "latest_period": {"value": {"growth_tier": "high"}}}}}}))


class G58PercentileCollection(unittest.TestCase):
    SNAP = {"valuation_snapshot": {"data": {"valuation_percentile": {
        "pe_ttm": {"applicable": True, "pct_5y": 35.0},
        "pb": {"applicable": True, "pct_5y": 28.0},
        "ev_ebitda": {"applicable": True, "pct_5y": 12.0}}}}}

    def test_fail_three_dims_collected(self):
        rep = "## 估值分析\n市盈 PE 中枢稳定，结论：估值适中。\n"   # 无分位数/无 src
        p, rs = _res(check_g58(rep, self.SNAP))
        self.assertFalse(p)
        self.assertEqual(len(rs), 3)                    # 三维缺口全量报（旧只报首个）
        self.assertIn("pe_ttm(真值 pct_5y=35.0)", " ".join(rs))
        self.assertIn("pb(真值 pct_5y=28.0)", " ".join(rs))
        self.assertIn("ev_ebitda(真值 pct_5y=12.0)", " ".join(rs))

    def test_pass_src_grounded(self):
        rep = ("## 估值分析\nPE 分位 [src: snapshot.valuation_snapshot.data.valuation_percentile.pe_ttm]；"
               "PB 分位 [src: snapshot.valuation_snapshot.data.valuation_percentile.pb]；"
               "EV/EBITDA 分位 [src: snapshot.valuation_snapshot.data.valuation_percentile.ev_ebitda]。\n")
        self.assertTrue(check_g58(rep, self.SNAP))


class G60BareAndRD(unittest.TestCase):
    REP = ("## 综合研判\n### 证据全景\n"
           "| 护城河 | 偏多 | 三单品独占 |\n"
           "| 治理战略 | 偏多 | 质押 0% |\n"
           "| 前瞻催化 | 偏多 | 第二曲线 |\n"
           "研发强度 12.5%（第一梯队）。\n")
    SNAP = {"s1_financial": {"data": {"income_statement":
           {"data": [{"研发费用": 5.0, "营业总收入": 100.0}]}}}}   # 真值 5%

    def test_fail_bare_lines_and_rd_collected(self):
        p, rs = _res(check_g60(self.REP, self.SNAP))
        self.assertFalse(p)
        self.assertEqual(len(rs), 4)                    # 3 裸奔行 + 1 研发强度偏离，合并清单
        self.assertTrue(any("护城河" in r for r in rs[:3]))
        self.assertTrue(any("前瞻催化" in r for r in rs[:3]))
        self.assertIn("报告 12.5% vs snapshot 研发费用÷营业总收入=5.00%", rs[3])

    def test_pass_src_anchored_and_aligned(self):
        rep = ("## 综合研判\n### 证据全景\n"
               "| 护城河 | 偏多 | 研发强度 5.0% [src: snapshot.s1_financial.data.income_statement] |\n"
               "| 治理战略 | 偏多 | 质押 0% [src: snapshot.governance] |\n"
               "| 前瞻催化 | 偏多 | 第二曲线 [src: snapshot.s1_financial.data.segment_composition] |\n")
        self.assertTrue(check_g60(rep, self.SNAP))


class G61ConsumeDims(unittest.TestCase):
    SNAP = {"s_stock_evaluation": {"data": {"status": "ok", "processed": {
        "conclusions": [
            {"dimension": "控盘程度", "text": "轻度控盘", "severity": "info", "source_api": "em"},
            {"dimension": "融资杠杆", "text": "融资余额上升", "severity": "info", "source_api": "em"}],
        "latest_period": {"raw_date": "2026-08-29", "value": 1, "period_type": "day"}}}}}

    def test_fail_missing_dims_collected(self):
        p, rs = _res(check_g61("报告完全未提相关结论。", self.SNAP))
        self.assertFalse(p)
        self.assertEqual(len(rs), 2)                    # 两维缺口全量报（旧裸 False）
        self.assertIn("「控盘程度」", rs[0])
        self.assertIn("「融资杠杆」", rs[1])

    def test_pass_surfaced_with_src(self):
        rep = ("千股千评：轻度控盘 [src: snapshot.s_stock_evaluation.data.processed.conclusions]，"
               "融资余额连续上升。")
        self.assertTrue(check_g61(rep, self.SNAP))


class G63ResistanceWord(unittest.TestCase):
    """词表扩「阻力」（F4 审查：m3:22/120/129/163 教写「阻力位/TDST阻力」，旧词表漏扫）。"""
    SNAP = {"s4_technical": {"data": {"fibonacci": {
        "levels": {"0.382": 100.0}, "swing_high": 105.0, "swing_low": 95.0}}}}

    def test_fail_resistance_transcription_error(self):
        # 「阻力」行数字 97.0 距最近真值 95 偏 2.1% ∈(0.5%,5%] → 转录错（旧词表不扫此行=漏报）
        rep = "## 技术面\n均线 均多头，上方阻力 97.0 元待突破。\n"
        p, rs = _res(check_g63(rep, self.SNAP))
        self.assertFalse(p)
        self.assertIn("97.0", rs[0])
        self.assertIn("95.0", rs[0])

    def test_fail_resistance_rounding_hint(self):
        # 报告 95.5 距真值 95 偏 0.53% ∈(0.5%,5%] 转录带，且距渲染值 MA20=95.6 仅 0.1%
        # ≤1.5% → R6 reason 分流为「取整渲染值」提示（照抄精确到分）
        snap = dict(self.SNAP)
        snap["s4_technical"] = {"data": {"fibonacci": self.SNAP["s4_technical"]["data"]["fibonacci"],
                                         "technical": {"ma": {"MA_20": 95.6}}}}
        p, rs = _res(check_g63("## 技术面\n均线 均多头，上方阻力 95.5 元。\n", snap))
        self.assertFalse(p)
        self.assertIn("取整渲染值", rs[0])
        self.assertIn("95.6", rs[0])

    def test_pass_exact_true_value(self):
        self.assertTrue(check_g63("## 技术面\n均线 均多头，上方阻力 95.00 元。\n", self.SNAP))


class G66OppCollection(unittest.TestCase):
    SNAP = {"mode": "B", "s4_technical": {"data": {"short_term_enrich": {"multi_period": {
        "resonance_level": "long_resonance",
        "monthly": {"state": "up"}, "daily": {"state": "down"}}}}}}

    def test_fail_opp_violations_collected(self):
        # 月线真值 up 却写 down；日线真值 down 却写 up → 两处全量收集（旧裸 False）
        rep = ("周期状态表：\n| 月线 | down 弱势 |\n| 周线 | up 强势 |\n| 日线 | up 强势 |\n"
               "60分钟 震荡。整体多头共振。")
        p, rs = _res(check_g66(rep, self.SNAP))
        self.assertFalse(p)
        self.assertEqual(len(rs), 2)
        self.assertIn("月线 状态对拍矛盾：快照 state=up", rs[0])
        self.assertIn("日线 状态对拍矛盾：快照 state=down", rs[1])

    def test_pass_consistent_rows(self):
        rep = ("周期状态表：\n| 月线 | up 强势 |\n| 周线 | up 强势 |\n| 日线 | down 弱势 |\n"
               "60分钟 震荡。整体多头共振。")
        self.assertTrue(check_g66(rep, self.SNAP))


if __name__ == "__main__":
    unittest.main(verbosity=2)
