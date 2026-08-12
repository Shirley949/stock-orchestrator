# -*- coding: utf-8 -*-
"""m5 估值模块 gate 三态/反编造单测（F-G1/G2/G3/G4）。

mirror test_g48 范式：from gate_definitions import check_g{45,58,59,21}。
· G58 估值分位必写+反编造（applicable 须 surface；无数据禁编造分位%）
· G59 §5.3 估值结论 verdict presence
· G45 目标价口径溯源（F-G4 收紧：目标价 N元 行须自身带 [src:]/不确定性）
· G21 m5 verified [src:] 计数（F-G3：m5 段 ≥2 个 verified snapshot src）
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
from gate_definitions import check_g45, check_g58, check_g59, check_g21


# ---------- 快照构造 ----------
def _snap_pct(applicable_pe=True, pct_5y=0.268, has_vp=True, pe_tm=None):
    """valuation_snapshot.data.valuation_percentile。has_vp=False→整体缺失（测反编造）。"""
    if not has_vp:
        return {"valuation_snapshot": {"data": {}}}
    pe = {"applicable": False, "pct_5y": None}
    if applicable_pe:
        pe = {"applicable": True, "pct_5y": pct_5y}
    return {"valuation_snapshot": {"data": {"valuation_percentile": {"pe_ttm": pe}}}}


def _snap_full_m5_src():
    """G21 测试用：snapshot 含 m5 报告所引的全部路径（peTtm/peLyr/pbRatio）。"""
    return {"valuation_snapshot": {"data": {"quote": {
        "peTtm": 21.52, "peLyr": 25.33, "pbRatio": 4.82}}}}


# ---------- G58 ----------
class CheckG58(unittest.TestCase):
    def test_applicable_src_grounded_pass(self):
        rep = "### 模块五\nPE(TTM) 21.52 近五年 26.8% 分位 [src: snapshot.valuation_snapshot.data.valuation_percentile.pe_ttm]"
        self.assertTrue(check_g58(rep, _snap_pct()))

    def test_applicable_value_aligned_pass(self):
        # 无 [src:] 但 pct 数值对齐（26.8 ×0.01=0.268≈0.268）
        rep = "### 模块五\nPE(TTM) 21.52 处近五年 26.8% 分位，中性偏低。"
        self.assertTrue(check_g58(rep, _snap_pct(pct_5y=0.268)))

    def test_applicable_missing_fail(self):
        # applicable 但 m5 完全没提分位 → 漏报 FAIL
        rep = "### 模块五\nPE(TTM) 21.52。PB 4.82。估值偏低。"
        self.assertFalse(check_g58(rep, _snap_pct()))

    def test_not_applicable_exempt(self):
        # 亏损 applicable=false → 豁免 PASS（不要求 surface）
        rep = "### 模块五\nPE 亏损不适用。估值偏低。"
        self.assertTrue(check_g58(rep, _snap_pct(applicable_pe=False)))

    def test_fabrication_when_no_data_fail(self):
        # 无 valuation_percentile 数据却写具体分位% → 反编造 FAIL
        rep = "### 模块五\nPE(TTM) 处近五年 26.8% 分位。"
        self.assertFalse(check_g58(rep, _snap_pct(has_vp=False)))

    def test_no_data_no_percentile_pass(self):
        # 无数据 + 不编造分位 → 豁免 PASS
        rep = "### 模块五\nPE(TTM) 21.52。估值偏低。"
        self.assertTrue(check_g58(rep, _snap_pct(has_vp=False)))

    def test_no_m5_section_with_applicable_fail(self):
        # Fix A 3 态：有 applicable 分位数据 + 报告无估值段（found=False）= 漏报 FAIL。
        # G58 是 profile_full/mode-A gate，全量报告必有估值段；无段 + applicable = 结构缺陷。
        # （修复前 `模块五` 关键词太窄 + `if not m: return True` 逃逸致永远 PASS——本测试原编码旧 bug 行为）
        self.assertFalse(check_g58("无估值段的报告", _snap_pct()))


# ---------- G59 ----------
class CheckG59(unittest.TestCase):
    def test_with_verdict_pass(self):
        for kw in ("偏贵", "偏贱", "高估", "低估", "估值合理", "估值适中", "估值偏低", "估值偏高"):
            self.assertTrue(check_g59(f"#### 5.3 估值结论\n当前价 395 元，{kw}，具配置价值。", {}),
                            f"verdict 词 {kw} 应 PASS")

    def test_without_verdict_fail(self):
        self.assertFalse(check_g59("#### 5.3 估值结论\n历史定位 PE 21.52。同业定位领先。\n合理估值区间 460 元。", {}))

    def test_no_conclusion_section_exempt(self):
        self.assertTrue(check_g59("### 模块五\n无 5.3 结论段。", {}))


# ---------- G45 (F-G4 收紧) ----------
class CheckG45(unittest.TestCase):
    def test_target_price_with_src_pass(self):
        rep = "- 上行空间 +37%（vs 目标价 543.03 元）[src: snapshot.valuation_snapshot.data.targetPrice.average]"
        self.assertTrue(check_g45(rep, {}))

    def test_target_price_with_uncertainty_pass(self):
        rep = "- 合理估值约 500 元（粗略估计，仅供参考）"
        self.assertTrue(check_g45(rep, {}))

    def test_bare_target_price_no_src_fail(self):
        # 目标价 N元 行自身无 [src:] 无不确定性 → FAIL（防 websearch 冒充 API）
        rep = "- 机构一致目标价 543.03 元，上行空间大。\n- PE 21.52 [src: snapshot.valuation_snapshot.data.quote.peTtm]"
        self.assertFalse(check_g45(rep, {}))

    def test_no_target_price_pass(self):
        self.assertTrue(check_g45("当前价 395.30 元，PE 21.52。", {}))

    def test_target_word_without_yuan_pass(self):
        # 「目标价表见 m10」无 N元 → 不触发
        self.assertTrue(check_g45("目标价完整表见 m10 §10A.2。", {}))


# ---------- G21 (F-G3 m5 计数) ----------
class CheckG21M5(unittest.TestCase):
    def _rep(self, m5_body):
        return f"### 模块一\n标的概况成长股。\n### 模块五\n{m5_body}\n### 模块六\n决策裁决。"

    def test_m5_two_src_pass(self):
        rep = self._rep("PE 21.52 [src: snapshot.valuation_snapshot.data.quote.peTtm] "
                        "PB 4.82 [src: snapshot.valuation_snapshot.data.quote.pbRatio]")
        self.assertTrue(check_g21(rep, _snap_full_m5_src()))

    def test_m5_thin_src_fail(self):
        # m5 段仅 1 个 verified src → FAIL（橡皮章估值）
        rep = self._rep("PE 21.52 [src: snapshot.valuation_snapshot.data.quote.peTtm] 估值偏低。")
        self.assertFalse(check_g21(rep, _snap_full_m5_src()))

    def test_m5_no_src_fail(self):
        rep = self._rep("估值偏低，具配置价值。")   # 无任何 [src:]
        self.assertFalse(check_g21(rep, _snap_full_m5_src()))

    def test_no_m5_section_exempt(self):
        # 无「模块五」段 → 不执法 m5 计数（仅路径验证）
        rep = "### 模块一\nPE 21.52 [src: snapshot.valuation_snapshot.data.quote.peTtm]"
        # m5 计数不触发；路径验证通过 → PASS
        self.assertTrue(check_g21(rep, _snap_full_m5_src()))

    def test_m5_bare_scene_src_counts(self):
        # bare-scene src（无 snapshot. 前缀）也计入 verified
        rep = self._rep("PE 21.52 [src: valuation_snapshot.data.quote.peTtm] "
                        "目标价 [src: valuation_snapshot.data.targetPrice.average]")
        snap = {"valuation_snapshot": {"data": {"quote": {"peTtm": 21.52}, "targetPrice": {"average": 543}}}}
        self.assertTrue(check_g21(rep, snap))


if __name__ == "__main__":
    unittest.main(verbosity=2)
