#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""section_locator 单测：候选迭代 + 切片验签 的劫持免疫与零回归边界。

覆盖（对应 2026-08-28 方案验证电池 T1-T11/T9b/T2 边界）：
  · 真实形态锚定：## 章号前缀 / ### 模板形态 / emoji 前缀 → ok@heading
  · 六起事故诱饵形态全部跳过（唯特偶 4.2 / 君正 11.4 / 株冶 3.5.4 / 赛微双诱饵 /
    ## 速览散文投资建议 T9a）
  · no_anchor：m6 缺失 / 触发词仅在散文表格（heading 边界固化）
  · T9b 已接受残留锁定：## 诱饵 + 其下 ### 投资建议 子标题仍锚诱饵（= 旧语义，
    无已知事故形态；此用例防未来无意识变化）
  · T2 边界：capstone 前的特征词标题（非 5 词候选）不会成为锚
  · weak 车道：模式 B 形态（情景 label 无特征子节标题）→ ok@weak
  · slice_of 边界：同级截断 / --- 截断 / #### 不截断
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
from section_locator import locate, slice_of, CAPSTONE_HEAD_RE  # noqa: E402

# 合规迷你 capstone（### 模板形态，含特征子节 + 情景 label）
CAP_GOOD = """### 综合研判 Capstone

#### 证据全景

量化与定性维度盘点若干 [src: snapshot.s1_financial]。

#### 情景矩阵

| 情景 | 概率 | 应对动作 | 成立条件 | 反方证据 |
|------|------|---------|---------|---------|
| 乐观 | 40% | 建仓 | 若放量突破 | 然而均线空头 |
| 基准 | 35% | 观望 | 若区间震荡 | 但是资金承压 |
| 悲观 | 25% | 减仓 | 一旦跌破支撑 | 尽管外资托底 |

#### 投资建议

观望为主。

## 模块八

数据时效说明。
"""


def _with_prefix(prefix: str, capstone: str = CAP_GOOD) -> str:
    return prefix + "\n\n" + capstone


class TestLocateRealForms(unittest.TestCase):
    def test_h2_chapter_prefix(self):
        rep = _with_prefix("## 七、公司治理与股东回报\n\n分红稳定。", "## 八、综合研判\n\n" + CAP_GOOD.split("\n", 1)[1])
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("## 八、综合研判"))

    def test_h3_template_form(self):
        sl, d = locate(CAP_GOOD)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("### 综合研判 Capstone"))

    def test_emoji_prefix(self):
        rep = "## 🎯 模块六：综合研判（收口裁决）\n\n" + CAP_GOOD.split("\n", 2)[2]
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("## 🎯 模块六"))


class TestLocateHijackImmunity(unittest.TestCase):
    """六起事故诱饵形态：全部应跳过诱饵、锚到真 capstone（旧取首语义会锚诱饵）。"""

    def test_pre_h3_weiteou_42(self):
        rep = _with_prefix("### 4.2 股东行为综合研判（ST3）\n\n机构调研频繁。")
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("### 综合研判 Capstone"))

    def test_pre_h3_junzheng_llm(self):
        rep = _with_prefix("### 11.4 资金流与共识（LLM 研判）\n\n主力净流入。")
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("### 综合研判 Capstone"))

    def test_pre_h3_zhuye_sensitivity(self):
        rep = _with_prefix("### 3.5.4 价格敏感性测算（±30% 情景）\n\n敏感性测算表。")
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("### 综合研判 Capstone"))

    def test_dual_decoy_saiwei(self):
        rep = _with_prefix(
            "### Q6：值不值得买？——三情景裁决\n\n结论一句话。\n\n"
            "### 7.5.1 政策传导链（定性研判）\n\n传导路径。")
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("### 综合研判 Capstone"))

    def test_h2_tldr_prose_only(self):
        """T9a：## 级速览诱饵 + 散文「投资建议」（非 heading）→ 验签拒、锚真 capstone。"""
        rep = _with_prefix("## ⚡ 速览：综合研判结论（TL;DR）\n\n投资建议：观望。三档情景中中性概率 50%。",
                           "## 🎯 模块六：综合研判（收口裁决）\n\n" + CAP_GOOD.split("\n", 2)[2])
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("## 🎯 模块六"))

    def test_h2_tldr_subheading_residual(self):
        """T9b 已接受残留（2026-08-28 拍板）：## 诱饵 + 其下 ### 投资建议 子标题 →
        heading 级验签通过、仍锚诱饵（= 旧取首语义，无已知事故形态）。锁定现状，
        防未来无意识变化；若要提高验签阈值（≥2 特征子节）须重评芯碁微装形态。"""
        rep = _with_prefix("## 速览：综合研判\n\n### 投资建议\n\n观望。",
                           "## 🎯 模块六：综合研判（收口裁决）\n\n" + CAP_GOOD.split("\n", 2)[2])
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("## 速览：综合研判"), "残留形态行为变化=回归红线")


class TestLocateNoAnchor(unittest.TestCase):
    def test_m6_missing(self):
        rep = "# 报告\n\n## 一、概况\n\n基本面描述。\n\n## 二、财务\n\n营收增长 20%。\n"
        sl, d = locate(rep)
        self.assertEqual(d, "no_anchor")

    def test_trigger_in_prose_and_table_only(self):
        """触发词仅出现在散文/表格行 → 不锚（heading 边界固化，防正则放宽回归）。"""
        rep = "# 报告\n\n本节做综合研判：中性概率 50%。\n\n| 乐观 | 42% |\n|---|---|\n\n"
        self.assertEqual(locate(rep)[1], "no_anchor")

    def test_feat_word_heading_without_trigger_not_candidate(self):
        """T2 边界：capstone 前的特征词标题（含「全景」但非 5 词候选）不会成为锚。"""
        rep = _with_prefix("### 全景速览\n\n一览数据。")
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("### 综合研判 Capstone"))


class TestLocateWeakLane(unittest.TestCase):
    def test_mode_b_form_ok_weak(self):
        """模式 B 形态：情景 label 在、无 A 形态特征子节标题 → ok@weak（B 线零误报）。"""
        rep = ("## 九、m6 综研判定：用户二元问题的直接回答\n\n"
               "三档情景：中性概率 60%（乐观 20% / 悲观 20%），区间震荡为主。\n\n"
               "## 十、Gate 自评区\n\n略。\n")
        sl, d = locate(rep)
        self.assertEqual(d, "ok@weak")
        self.assertTrue(sl.startswith("## 九、m6 综研判定"))


class TestSliceOf(unittest.TestCase):
    def test_stops_at_same_level(self):
        rep = "## A 标题\n\n内容。\n\n## B 标题\n\n更多。"
        m = CAPSTONE_HEAD_RE.search("## A 综合研判\n\n内容。\n\n## B 标题\n\n更多。")
        sl = slice_of("## A 综合研判\n\n内容。\n\n## B 标题\n\n更多。", m)
        self.assertNotIn("## B 标题", sl)

    def test_hr_cuts(self):
        doc = "## A 综合研判\n\n内容。\n\n---\n\n## B\n\n更多。"
        m = CAPSTONE_HEAD_RE.search(doc)
        self.assertNotIn("---", slice_of(doc, m))

    def test_h4_not_truncating(self):
        doc = "## A 综合研判\n\n#### Layer 1 — 证据全景\n\n行1\n\n### 情景矩阵\n\n行2"
        m = CAPSTONE_HEAD_RE.search(doc)
        sl = slice_of(doc, m)
        self.assertIn("Layer 1", sl)


class TestM3SectionHijack(unittest.TestCase):
    """m3 定位（gate_definitions._m3_section，G52-55/G63 共用）劫持回归。

    康强事故：Q&A 报告 Q1 标题含「技术面」→ 旧取首语义锚 Q1 段 → G52/53/54/55/63
    六门连锁假象。修复后候选迭代+内容验签（技术特征词）跳过 Q&A 诱饵。"""

    def test_qa_tech_word_decoy_skipped(self):
        import gate_definitions as gd
        rep = ("## 〇、用户七大问题逐题直答\n\n"
               "### Q1 是不是值得买？（技术面位置与风险）\n\n估值合理，风险中等。\n\n"
               "## 五、技术分析（m3）\n\nTD 序列四步；支撑 87.01，压力 95.2；MA20 走平。\n")
        sec = gd._m3_section(rep)
        self.assertTrue(sec.startswith("## 五、技术分析"), f"应锚真 m3，实际: {sec.splitlines()[0]}")
        self.assertIn("TD 序列四步", sec)

    def test_no_m3_section_empty(self):
        import gate_definitions as gd
        self.assertEqual(gd._m3_section("# 报告\n\n## 一、概况\n\n内容。\n"), "")


if __name__ == "__main__":
    unittest.main()
