#!/usr/bin/env python3
"""G30 capstone 表格 label 格式回归测试。

背景：2026-07-19 宁德时代实测暴露 G30 口径矛盾——同一 gate 内 _g30_parse_matrix_table
(用 cells+in，宽容) 识别 `**中性**` 加粗 label，但 _g30_scenario_probs 走的
_g30_find_scenarios (严格正则 _G30_SCENARIO_TABLE_RE) 不识别→#3 概率闭合 FAIL，
而 #2/#4 却 PASS。修复：TABLE_RE label 两侧容忍 markdown 强调符，向 parse_matrix 对齐。

本测试锁住：加粗 label 不再致 #3 假 FAIL（核心回归点）+ 不破坏不加粗兼容 + #2/#3/#6 仍正常拦截。
"""
import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts', 'lib'))
import gate_definitions as gd

# 完整结构 capstone 模板（默认全 PASS，各 case 按需扰动）
CAP = """### 综合研判 Capstone（G30）

#### 证据全景

量化：ROE/净利率/毛利率/杜邦/周转率/权益乘数/扣非、营收/收入/增速/同比/合同负债、PE/PB/估值/目标价、货币资金/有息负债/商誉/负债率/现金、信号/资金流/筹码/股东户数/换手/支撑/阻力、一致预期/评级/研报/预测、龙虎榜/上榜/席位、北向/外资/持股比例、分产品/分行业/分地区/海外/关税。
定性：护城河/龙头/市占率/技术优势/规模优势，治理/管理层/战略，前瞻/催化/展望/渗透率/扩产/新产品。
[src: snapshot.s1_financial][src: snapshot.s4_technical][src: 见模块前述]

#### 情景矩阵

| 情景 | 概率 | 目标价 | 应对动作 | 成立条件 | 反方证据 |
|------|------|--------|---------|---------|---------|
| {l1} | {p1} | 348元 | 观望 | 若区间震荡反复 | 然而资金承压 |
| {l2} | {p2} | 450元 | 建仓 | 触发放量突破压力位 | 但是均线空头排列 |
| {l3} | {p3} | 342元 | 减仓 | 一旦跌破强支撑 | 尽管外资重仓托底 |

综合建议：信号矛盾，观望为主，突破确认后跟进。
"""


def _cap(l1="**中性**", l2="**乐观**", l3="**悲观**",
         p1="**45%**", p2="**30%**", p3="**25%**", main="综合建议：信号矛盾，观望为主，突破确认后跟进。"):
    body = CAP.format(l1=l1, l2=l2, l3=l3, p1=p1, p2=p2, p3=p3)
    # 替换主推荐行（默认含信号矛盾+观望）
    body = body.replace("综合建议：信号矛盾，观望为主，突破确认后跟进。", main)
    return "# 报告\n\n" + body + "\n\n## 模块七\n"


CAP_PROSE_TEMPLATE = """### 综合研判 Capstone（G30）

#### 证据全景

量化：ROE/净利率/毛利率/杜邦/周转率/权益乘数/扣非、营收/收入/增速/同比/合同负债、PE/PB/估值/目标价、货币资金/有息负债/商誉/负债率/现金、信号/资金流/筹码/股东户数/换手/支撑/阻力、一致预期/评级/研报/预测、龙虎榜/上榜/席位、北向/外资/持股比例、分产品/分行业/分地区/海外/关税。
定性：护城河/龙头/市占率/技术优势/规模优势，治理/管理层/战略，前瞻/催化/展望/渗透率/扩产/新产品。
[src: snapshot.s1_financial][src: snapshot.s4_technical][src: 见模块前述]

#### 情景矩阵

**中性**（45%）：目标价 348 元，应对观望，若区间震荡反复。然而资金承压。

**乐观**（30%）：目标价 450 元，应对建仓，触发放量突破压力位。但是均线空头排列。

**悲观**（25%）：目标价 342 元，应对减仓，一旦跌破强支撑。尽管外资重仓托底。

综合建议：信号矛盾，观望为主，突破确认后跟进。
"""


def _cap_prose(main="综合建议：信号矛盾，观望为主，突破确认后跟进。"):
    """散文情景标题版 capstone（Layer2 风格：**中性**（45%）：…，无表格）。
    锁住 HEADER_RE 去 | 后散文情景仍被识别——不退化成 probs<3→#3 假 FAIL。"""
    return "# 报告\n\n" + CAP_PROSE_TEMPLATE.replace(
        "综合建议：信号矛盾，观望为主，突破确认后跟进。", main) + "\n\n## 模块七\n"


class TestG30LabelFormat(unittest.TestCase):
    """核心：label 加粗 vs 不加粗行为一致（口径对齐回归）。"""

    def test_bold_label_passes(self):
        """加粗 label + 完整结构 → PASS（修复前 #3 假 FAIL）。"""
        r = gd._g30_run(_cap(), {})
        self.assertTrue(r["passed"], f"加粗 label 应 PASS，但 failed={r['failed']}, reasons={r['reasons']}")

    def test_plain_label_passes(self):
        """不加粗 label + 完整结构 → PASS（不破坏兼容）。"""
        r = gd._g30_run(_cap(l1="中性", l2="乐观", l3="悲观", p1="45%", p2="30%", p3="25%"), {})
        self.assertTrue(r["passed"], f"不加粗 label 应 PASS，failed={r['failed']}, reasons={r['reasons']}")

    def test_bold_plain_equivalent(self):
        """加粗与不加粗的 failed 列表须一致（口径矛盾已消除）。"""
        rb = gd._g30_run(_cap(), {})
        rp = gd._g30_run(_cap(l1="中性", l2="乐观", l3="悲观", p1="45%", p2="30%", p3="25%"), {})
        self.assertEqual(rb["failed"], rp["failed"], "加粗/不加粗 label 应口径一致")

    def test_prob3_not_affected_by_bold(self):
        """加粗 label 不再触发 #3（核心回归点）。"""
        r = gd._g30_run(_cap(), {})
        self.assertNotIn(3, r["failed"], "#3 概率闭合不应因 label 加粗而 FAIL")

    def test_mixed_label_table_passes(self):
        """混合 label 表格（部分加粗、部分裸）→ PASS。

        HEADER_RE 去 | 后表格行不被散文正则误匹配，统一交 TABLE_RE，
        find_scenarios 三行全识别→probs=[45,30,25]→#3 PASS（配套修复点，防 return early 漏识别）。
        """
        r = gd._g30_run(_cap(l1="中性", l2="**乐观**", l3="**悲观**"), {})
        self.assertTrue(r["passed"], f"混合 label 表格应 PASS，failed={r['failed']}, reasons={r['reasons']}")
        self.assertNotIn(3, r["failed"], "混合 label 不应致 #3 假 FAIL")


class TestG30HardChecksStillWork(unittest.TestCase):
    """#2/#3/#6 等硬检查在加粗 label 下仍正常拦截（修复未弱化 gate）。"""

    def test_prob_not_summing_fails(self):
        """概率和≠100 → #3 FAIL（加粗 label 下仍拦截）。"""
        r = gd._g30_run(_cap(p1="**50%**", p2="**40%**", p3="**20%**"), {})  # 和=110
        self.assertIn(3, r["failed"])

    def test_missing_counter_fails(self):
        """反方证据列单元格空 → #2 FAIL。"""
        cap = CAP.format(l1="**中性**", l2="**乐观**", l3="**悲观**",
                         p1="**45%**", p2="**30%**", p3="**25%**").replace(
            "然而资金承压", "").replace("但是均线空头排列", "").replace("尽管外资重仓托底", "")
        r = gd._g30_run("# 报告\n\n" + cap + "\n\n## 模块七\n", {})
        self.assertIn(2, r["failed"])

    def test_contradiction_non_hold_fails(self):
        """信号矛盾但主推荐=建仓 → #6 FAIL。"""
        r = gd._g30_run(_cap(main="综合建议：信号矛盾，建议建仓加仓。"), {})
        self.assertIn(6, r["failed"])


class TestG30ProseScenarios(unittest.TestCase):
    """HEADER_RE 去 | 后散文情景标题仍被识别（非表格报告回归）。"""

    def test_prose_scenarios_pass(self):
        """散文情景标题（**中性**（45%）：…）→ 全 6 检查 PASS。"""
        r = gd._g30_run(_cap_prose(), {})
        self.assertTrue(r["passed"], f"散文情景应 PASS，failed={r['failed']}, reasons={r['reasons']}")

    def test_prose_find_scenarios_count(self):
        """散文情景标题被 find_scenarios 识别为 3 个（HEADER 分支，非表格）。"""
        cap = gd._g30_find_capstone(_cap_prose())
        scens = gd._g30_find_scenarios(cap)
        self.assertEqual(len(scens), 3, f"散文情景应识别3个，实际{[s[0] for s in scens]}")
        self.assertEqual(gd._g30_scenario_probs(cap), [45.0, 30.0, 25.0])


if __name__ == "__main__":
    unittest.main()
