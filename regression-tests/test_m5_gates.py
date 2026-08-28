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

    # ---- C 修复（2026-08-27）：候选∪级联锚定，根治 5.3/7.5.3 章节号劫持 ----
    def test_hijack_by_m4_5_3_fixed(self):
        """① m4 情绪章「### 5.3 机构动向」(无词)在前不再劫持——真 5.3 估值节含词 → PASS（旧 FAIL）。"""
        rep = "### 5.3 机构动向\n调研频繁。\n\n#### 5.3 估值结论\n估值偏低。\n"
        self.assertTrue(check_g59(rep, {}), "级联后真 5.3 节含判定词应 PASS")

    def test_hijack_by_subsection_7_5_3_fixed(self):
        """② 「#### 7.5.3」子节号（[^\d]* 挡板）不劫持——真 5.3 节含词 → PASS（旧 FAIL）。"""
        rep = "#### 7.5.3 宏观跟踪\n平稳。\n\n#### 5.3 估值结论\n显著偏贵。\n"
        self.assertTrue(check_g59(rep, {}), "7.5.3 子节号不应被 ③ 级锚误匹配")

    def test_002025_shape_verdict_in_prev_summary(self):
        """③ 002025 形态：5.3 节小结含词 + 5.4 估值结论节无词 → PASS（级联任一切片含词即可）。"""
        rep = ("### 5.3 一致预期与机构目标价\n目标价 543 元。小结：PE 处于历史偏贵水位。\n\n"
               "### 5.4 估值结论\n各项指标平稳。\n")
        self.assertTrue(check_g59(rep, {}), "5.3 节小结含词即应 PASS")

    def test_renumbered_conclusion_enforced(self):
        """④ 改号执法（唯一收紧点）：无 5.3 + 「### 8.4 估值结论」无词 → FAIL（② 扩执法面）。"""
        self.assertFalse(check_g59("### 8.4 估值结论\n各项平稳。\n", {}))

    def test_true_miss_still_fails(self):
        """⑤ 判定词真缺失（有锚无词）→ FAIL 保持。"""
        self.assertFalse(check_g59("#### 5.3 估值结论\n各项指标平稳。\n", {}))

    def test_no_anchor_exempt(self):
        """⑥ 无任何 5.3/估值结论锚 → 豁免（report-only / 非估值报告）；
        正文裸提「5.3」不泄漏锚定（[^\d\n]* 不跨行——「### 模块五\n无 5.3 结论段」须仍豁免）。"""
        self.assertTrue(check_g59("### 6.1 风险提示\n市场有风险。\n", {}))
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

    def test_m5_subsection_src_counts(self):
        # R1（2026-08-16）：m5 段切片统一 _module_section（level-aware）——
        # 修复前内联切片停在任意级别 header，#### 子节内的锚被截丢 → 误 FAIL。
        # 导语 0 锚、锚全在 #### 子节 → 修复后 PASS（修复前 FAIL）。
        m5 = ("估值导语。\n"
              "#### 5.1 横向对比\n"
              "PE 21.52 [src: snapshot.valuation_snapshot.data.quote.peTtm]\n"
              "#### 5.2 结论\n"
              "PB 4.82 [src: snapshot.valuation_snapshot.data.quote.pbRatio]")
        self.assertTrue(check_g21(self._rep(m5), _snap_full_m5_src()))

    def test_m5_subsection_thin_src_still_fail(self):
        # 反例：子节内也只 1 锚 → 仍 FAIL（放宽的只是切片范围，不是计数标准）
        m5 = ("估值导语。\n"
              "#### 5.1 横向对比\n"
              "PE 21.52 [src: snapshot.valuation_snapshot.data.quote.peTtm]")
        self.assertFalse(check_g21(self._rep(m5), _snap_full_m5_src()))


class CheckG58Hijack(unittest.TestCase):
    """G58 m5 定位劫持回归（2026-08-28 根修：候选迭代+内容验签）。

    事故形态五起：阳谷/晶方/福晶/领益的 m0「股票分类与估值框架」同模式 ×4 复发 +
    康强 Q&A「估值框架」。旧 `_module_section(模块五|估值分析|估值)` 单向取首——
    前置标题含「估值」即劫持切片 → 分位永不 grounded → 误报漏报 FAIL。
    修复后：首个切片含估值特征词（分位/市盈/PE/PB/市净/估值结论/目标价/同业对比）
    者胜出，诱饵切片（纯分类/问答内容）被跳过。红验证：2026-08-28 改前引擎两诱饵
    均 FAIL（m5 未 surface pe_ttm 估值分位）。"""

    def test_m0_valuation_frame_decoy_pass(self):
        """领益形态：`## 一、股票分类与估值框架（m0）` 前置 → 修复后锚真 m5，PASS。"""
        rep = ("## 一、股票分类与估值框架（m0）\n\n本股属周期成长混合型。\n\n"
               "## 七、估值分析（m5）\n\nPE(TTM) 21.52 近五年 26.8% 分位 "
               "[src: snapshot.valuation_percentile.pe_ttm]")
        self.assertTrue(check_g58(rep, _snap_pct()))

    def test_qa_valuation_frame_decoy_pass(self):
        """康强形态：Q&A 小节标题含「估值框架」→ 修复后跳过，锚真 m5，PASS。"""
        rep = ("## 〇、用户七大问题逐题直答\n\n### Q1 定价与估值框架\n\n答：估值合理。\n\n"
               "## 七、估值分析（m5）\n\nPE(TTM) 21.52 近五年 26.8% 分位 "
               "[src: snapshot.valuation_percentile.pe_ttm]")
        self.assertTrue(check_g58(rep, _snap_pct()))

    def test_no_decoy_missing_percentile_still_fails(self):
        """反极：无诱饵 + applicable 分位未 surface → 漏报照抓（执法不弱化）。"""
        rep = ("## 一、股票分类（m0）\n\n周期股。\n\n"
               "## 七、估值分析（m5）\n\nPE(TTM) 21.52，估值偏低。")
        self.assertFalse(check_g58(rep, _snap_pct()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
