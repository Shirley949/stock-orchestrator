# -*- coding: utf-8 -*-
"""m6 综合研判 gate 三态/反捏造单测（G-G2 G60）。

mirror test_m5_gates 范式：from gate_definitions import check_g60。
· G60 Layer1 ⑪护城河/⑫治理战略/⑬前瞻催化 三定性维度行各须含 ≥1 [src:] 锚点（或标「无源」豁免）
· 反捏造：研发强度X% 须≈snapshot（研发费÷营收）
· 三态：有锚/标无源 PASS / 无 m6 段豁免 / 裸奔或捏造 FAIL
· 限证据全景子节——投资建议叙事提护城河无 src 合法，不误伤
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
from gate_definitions import check_g60
from capstone_panorama import _latest_annual_roe, _signal_direction_tally


# ---------- 快照构造 ----------
def _snap_rd(rev=276917000000.0, rd=11377000000.0):
    """income_statement.data[0] 含 研发费用/营业总收入 → rd_intensity = rd/rev。"""
    return {"s1_financial": {"data": {"income_statement": {
        "data": [{"营业总收入": rev, "研发费用": rd}]}}}}


# 三定性锚行齐全 + [src:] 的 golden-shaped Layer1
_GOLDEN_LAYER1 = """### 模块六：综合研判（收口裁决）

#### Layer 1 — 证据全景（13 维盘点清单）

| 维度 | 现状 | 方向 | 数据锚点 |
|---|---|---|---|
| ①财务质量 | ROE 12.08% | 偏多 | [src: snapshot.s1_financial.data.dupont] |
| ⑪护城河 | 🔒研发强度4.11%（研发费113.77亿÷营收2769亿）；〔定性补充·无源〕品牌 | 偏多 | [src: snapshot.s1_financial.data.income_statement] |
| ⑫治理战略 | 🔒P2注销型回购+P5激励；质押仅0.68%低 | 偏多 | [src: snapshot.s5_events.data.risk_signals.processed.catalyst] |
| ⑬前瞻催化 | 🔒储能19.2%放量+consensus高增 | 偏多 | [src: snapshot.s1_financial.data.segment_composition] |

#### 投资建议
基本面强，护城河深厚，回调建仓。
"""


# ---------- G60 ----------
class CheckG60(unittest.TestCase):
    def test_three_qual_rows_with_src_pass(self):
        # 三定性行各带 [src:] → PASS
        self.assertTrue(check_g60(_GOLDEN_LAYER1, _snap_rd()))

    def test_naked_qual_row_no_src_fail(self):
        # ⑪护城河行无 [src:] 无「无源」标注 → 裸奔 FAIL
        rep = _GOLDEN_LAYER1.replace(
            "[src: snapshot.s1_financial.data.income_statement]",
            "").replace("〔定性补充·无源〕", "")
        # ⑪行变裸奔（无 src 无无源）
        self.assertFalse(check_g60(rep, _snap_rd()))

    def test_pure_qual_marked_no_source_exempt(self):
        # 真空/干净票：定性行纯叙事显式标「无源」→ 豁免 PASS（无锚数据可引）
        rep = """### 模块六：综合研判（收口裁决）
#### Layer 1 — 证据全景
| ⑪护城河 | 〔定性补充·无源〕品牌壁垒深厚 | 偏多 | — |
| ⑫治理战略 | 〔定性补充·无源〕管理层稳定 | 偏多 | — |
| ⑬前瞻催化 | 〔定性补充·无源〕行业景气 | 偏多 | — |
"""
        self.assertTrue(check_g60(rep, {}))

    def test_rd_intensity_fabricated_fail(self):
        # 研发强度写 12%（snapshot 实为 4.11%）→ 反捏造 FAIL
        rep = _GOLDEN_LAYER1.replace("研发强度4.11%", "研发强度12%")
        self.assertFalse(check_g60(rep, _snap_rd()))

    def test_rd_intensity_aligned_pass(self):
        # 研发强度4.11% ≈ snapshot(rd/rev=0.0411→4.11%) → PASS
        self.assertTrue(check_g60(_GOLDEN_LAYER1, _snap_rd()))

    def test_no_m6_section_exempt(self):
        # 无综合研判段 → 不执法 PASS
        self.assertTrue(check_g60("### 模块五\nPE 21.52。", _snap_rd()))

    def test_advice_narrative_moat_no_src_pass(self):
        # 投资建议叙事提「护城河」无 src 合法（限证据全景子节，不误伤）
        rep = """### 模块六：综合研判（收口裁决）
#### Layer 1 — 证据全景
| ⑪护城河 | 🔒研发强度4.11% | 偏多 | [src: snapshot.s1_financial.data.income_statement] |
| ⑫治理战略 | 🔒回购 | 偏多 | [src: snapshot.s5_events.data.risk_signals.processed.catalyst] |
| ⑬前瞻催化 | 🔒储能19% | 偏多 | [src: snapshot.s1_financial.data.segment_composition] |
#### 投资建议
核心逻辑：护城河深厚，治理优秀，前景看好。
"""
        self.assertTrue(check_g60(rep, _snap_rd()))

    def test_two_rows_with_src_one_naked_fail(self):
        # ⑪⑫ 有 src，⑬ 裸奔 → FAIL（任一裸奔即 FAIL）
        rep = """### 模块六：综合研判（收口裁决）
#### Layer 1 — 证据全景
| ⑪护城河 | 🔒研发强度4.11% | 偏多 | [src: snapshot.s1_financial.data.income_statement] |
| ⑫治理战略 | 🔒回购 | 偏多 | [src: snapshot.s5_events.data.risk_signals.processed.catalyst] |
| ⑬前瞻催化 | 储能放量前景好 | 偏多 | — |
"""
        self.assertFalse(check_g60(rep, _snap_rd()))


# ---------- _latest_annual_roe + tally ①财务质量 年报优先（600036 RCA）----------
def _fi_rows(*pairs):
    """构造 financial_indicators rows：[(日期, 加权ROE), ...]。"""
    return [{"日期": d, "加权净资产收益率(%)": r} for d, r in pairs]


class TallyAnnualRoeTests(unittest.TestCase):
    """600036 招行 RCA：最新期 2026Q1=3.37（YTD）套年化阈值 → 误判偏空；
    须优先最近年报 2025=13.44 → 偏多（高质量股正确）。"""

    def test_latest_annual_roe_picks_max_date_annual(self):
        # 含多期年报 + interim，取最大日期的年报行（不信 rows[0] 顺序）
        rows = _fi_rows(("2018-03-31", 4.99), ("2025-12-31", 13.44),
                        ("2026-03-31", 3.37), ("2024-12-31", 14.49))
        data = {"s1_financial": {"data": {"financial_indicators": {"data": rows}}}}
        self.assertEqual(_latest_annual_roe(data), 13.44)   # 2025 年报（max 12-31）

    def test_latest_annual_roe_data_full_fallback(self):
        # data 键缺失 → data_full 兜底（读三表范式）
        rows = _fi_rows(("2025-12-31", 13.44))
        data = {"s1_financial": {"data": {"financial_indicators": {"data_full": rows}}}}
        self.assertEqual(_latest_annual_roe(data), 13.44)

    def test_latest_annual_roe_no_annual_returns_none(self):
        # 次新股只有 Q1（无年报）→ None（调用方退回最新期值）
        rows = _fi_rows(("2026-03-31", 3.37))
        data = {"s1_financial": {"data": {"financial_indicators": {"data": rows}}}}
        self.assertIsNone(_latest_annual_roe(data))

    def test_tally_quality_dim_prefers_annual_not_interim(self):
        # 600036 实测：最新期 3.37（YTD）会误判偏空，年报 13.44 须判偏多
        values = {"quality": {"indicators": {"value": {"加权净资产收益率(%)": 3.37}}}}
        rows = _fi_rows(("2025-12-31", 13.44), ("2026-03-31", 3.37))
        data = {"s1_financial": {"data": {"financial_indicators": {"data": rows}}}}
        t = _signal_direction_tally(values, data, [])
        dims = dict(t["per_dim"])
        self.assertEqual(dims["财务质量"], "偏多")   # 年报 13.44 ≥10 → 偏多（非偏空）

    def test_tally_quality_dim_fallback_interim_when_no_annual(self):
        # 无年报 → 退回最新期 3.37 → 偏空（诚实：年化基准不可得，仍按最新期判，解读提示警示）
        values = {"quality": {"indicators": {"value": {"加权净资产收益率(%)": 3.37}}}}
        rows = _fi_rows(("2026-03-31", 3.37))
        data = {"s1_financial": {"data": {"financial_indicators": {"data": rows}}}}
        t = _signal_direction_tally(values, data, [])
        self.assertEqual(dict(t["per_dim"])["财务质量"], "偏空")


# ---------- G60 空转根修（2026-08-28）：## 级 capstone 形态 ----------
_H2_CAPSTONE = """## 🎯 模块六：综合研判（收口裁决）

### 证据全景

- ①财务质量：ROE 12.08% [src: snapshot.s1_financial.data.dupont]
- {moha_line}
- ⑫治理战略：P2注销型回购 [src: snapshot.s5_events.data.risk_signals.processed.catalyst]
- ⑬前瞻催化：储能19.2%放量 [src: snapshot.s1_financial.data.segment_composition]

### 情景-动作矩阵

| 情景 | 概率 | 目标价 | 应对动作 | 成立条件 | 反方证据 |
|------|------|--------|---------|---------|---------|
| 中性 | 45% | 348元 | 观望 | 若区间震荡 | 然而资金承压 |
| 乐观 | 30% | 450元 | 建仓 | 触发放量突破 | 但是均线空头 |
| 悲观 | 25% | 342元 | 减仓 | 一旦跌破支撑 | 尽管外资托底 |

### 投资建议

观望为主。

## 📋 模块八：数据时效与局限性

略。
"""


class CheckG60H2Capstone(unittest.TestCase):
    """真实报告形态（## 级 capstone + ### 子节）执法回归。

    空转 bug：旧边界正则 ^#{1,3} 在 ## capstone 的第一个 ### 子节处截断 → sec 恒空
    → 26 份归档全程不执法（植入裸奔定性行仍 PASS，2026-08-28 T18 实测 25/25）。
    单测此前只测 ### 级 capstone（模板文档形态），恰好绕开此 bug。"""

    MOHA_NAKED = "- ⑪护城河：品牌与渠道优势明显"
    MOHA_SRC = "- ⑪护城河：研发强度4.11% [src: snapshot.s1_financial.data.income_statement]"

    def test_h2_naked_qual_row_fails(self):
        """## capstone 下裸奔定性行 → FAIL（旧引擎空转 PASS——红验证 2026-08-28）。"""
        rep = _H2_CAPSTONE.format(moha_line=self.MOHA_NAKED)
        self.assertFalse(check_g60(rep, _snap_rd()),
                         "## 级 capstone 下裸奔护城河行应 FAIL（空转已修）")

    def test_h2_src_qual_row_passes(self):
        rep = _H2_CAPSTONE.format(moha_line=self.MOHA_SRC)
        self.assertTrue(check_g60(rep, _snap_rd()))

    def test_h2_decoy_layer1_still_reachable(self):
        """诱饵（### 4.2 股东行为综合研判）在前，Layer1 仍可达并执法（裸奔行 FAIL）。"""
        rep = "### 4.2 股东行为综合研判（ST3）\n\n机构调研频繁。\n\n" + \
            _H2_CAPSTONE.format(moha_line=self.MOHA_NAKED)
        self.assertFalse(check_g60(rep, _snap_rd()), "诱饵不应令 G60 退回空转")

    def test_tally_summary_line_not_flagged(self):
        """helper tally 汇总行（含维度名）非三定性维度行，不属 ① 执法对象——
        锁定 2026-08-28 skip 修复（6/26 归档曾误伤：蓝思/中钨/宏明/赛微/领益/特变B）。"""
        rep = _H2_CAPSTONE.format(moha_line=self.MOHA_SRC).replace(
            "- ⑫治理战略：",
            "**信号方向 tally：3 偏多 / 6 中性 / 5 偏空**——典型的\"深护城河\"结构。\n- ⑫治理战略：")
        self.assertTrue(check_g60(rep, _snap_rd()), "tally 汇总行提及护城河不应触发裸奔 FAIL")


class PanoramaLocatorUnified(unittest.TestCase):
    """capstone_panorama._find_capstone 统一委托 section_locator（双实现收编）。"""

    def test_decoy_anchors_real_capstone(self):
        import capstone_panorama as cp
        doc = ("### 4.2 股东行为综合研判（ST3）\n\n机构调研频繁。\n\n"
               "## 🎯 模块六：综合研判（收口裁决）\n\n### 证据全景\n\n内容。\n")
        cap = cp._find_capstone(doc)
        self.assertTrue(cap.startswith("## 🎯 模块六"),
                        f"应锚真 capstone（旧实现切到文末含诱饵），实际: {cap.splitlines()[0]}")

    def test_bounded_slice(self):
        """切片有界（不再切到文末）：后续模块不混入。"""
        import capstone_panorama as cp
        doc = ("## 🎯 模块六：综合研判（收口裁决）\n\n### 证据全景\n\n内容。\n\n"
               "## 📋 模块八\n\n后续模块内容。\n")
        self.assertNotIn("模块八", cp._find_capstone(doc))


if __name__ == "__main__":
    unittest.main(verbosity=2)
