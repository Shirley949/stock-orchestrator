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


CAP_NOPROB = """### 综合研判 Capstone（G30）

#### 证据全景

量化：ROE/净利率/毛利率/杜邦/周转率/权益乘数/扣非、营收/收入/增速/同比/合同负债、PE/PB/估值/目标价、货币资金/有息负债/商誉/负债率/现金、信号/资金流/筹码/股东户数/换手/支撑/阻力、一致预期/评级/研报/预测、龙虎榜/上榜/席位、北向/外资/持股比例、分产品/分行业/分地区/海外/关税。
定性：护城河/龙头/市占率/技术优势/规模优势，治理/管理层/战略，前瞻/催化/展望/渗透率/扩产/新产品。
[src: snapshot.s1_financial][src: snapshot.s4_technical][src: 见模块前述]

#### 情景矩阵

**中性**（45%）：目标价 348 元，应对观望。然而资金承压。

**乐观**（30%）：目标价 450 元，应对建仓。但是均线空头排列。

**悲观**（25%）：目标价 342 元，应对减仓。尽管外资重仓托底。

| 情景（概率） | 目标价 | 应对动作 | 成立条件 | 反方证据 |
|------|------|--------|---------|---------|
| 中性 45% | 348元 | 观望 | 若区间震荡反复 | 然而资金承压 |
| 乐观 30% | 450元 | 建仓 | 触发放量突破压力位 | 但是均线空头排列 |
| 悲观 25% | 342元 | 减仓 | 一旦跌破强支撑 | 尽管外资重仓托底 |

综合建议：信号矛盾，观望为主，突破确认后跟进。
"""


class TestG30ProbFromTableColumn(unittest.TestCase):
    """B 修复（2026-08-27）：#3 概率改读情景表「概率」列（表优先+全行守卫+正则回退）。

    背景：旧 TABLE_RE 行正则要求带 %，裸数字概率列 → probs=[0,0,0]→#3 假 FAIL；
    声明+表格行双吃 → 6 情景重复计数（8/170 本地语料实锤）。表路径复用
    _g30_parse_matrix_table 选表结果，与 #2/#4 同表同源。"""

    def test_bare_digit_prob_column(self):
        """① 概率列裸数字（无 %）→ 表路径精确取值（旧路径 probs=[0,0,0]→#3 假 FAIL）。"""
        cap = gd._g30_find_capstone(_cap(p1="40", p2="35", p3="25"))
        self.assertEqual(gd._g30_scenario_probs(cap), [40.0, 35.0, 25.0])
        self.assertEqual(len(gd._g30_find_scenarios(cap)), 3, "表路径应返回 3 情景，非声明+表格双吃")

    def test_tolerant_prob_cell_formats(self):
        """② 约/％ 全角/尾部文字容忍 → 表路径 PASS。"""
        r = gd._g30_run(_cap(p1="约 40%", p2="约35％", p3="25%"), {})
        self.assertTrue(r["passed"], f"容忍格式应 PASS，failed={r['failed']}, reasons={r['reasons']}")
        cap = gd._g30_find_capstone(_cap(p1="约 40%", p2="约35％", p3="25%"))
        self.assertEqual(gd._g30_scenario_probs(cap), [40.0, 35.0, 25.0])

    def test_no_prob_col_falls_back_to_declarations(self):
        """③ 「情景（概率）」合并列形态（688308 实案）→ 无 prob 列 → 回退行首声明路径 PASS。"""
        rep = "# 报告\n\n" + CAP_NOPROB + "\n\n## 模块七\n"
        cap = gd._g30_find_capstone(rep)
        self.assertEqual(gd._g30_scenario_probs(cap), [45.0, 30.0, 25.0],
                         "无概率列应回退声明正则，而非表路径硬吃")
        r = gd._g30_run(rep, {})
        self.assertTrue(r["passed"], f"合并列形态应 PASS，failed={r['failed']}, reasons={r['reasons']}")

    def test_partial_parse_falls_back(self):
        """④ 概率列 1 行无数字（约）→ 整表回退正则（None 守卫，非表路径硬吃 None）。
        回退 TABLE_RE 对无 % 行给 0.0（旧 lenient 语义保持）→ 和=70 → #3 照 FAIL（执法不弱化）。"""
        cap = gd._g30_find_capstone(_cap(p2="约"))
        probs = gd._g30_scenario_probs(cap)
        self.assertEqual(probs, [45.0, 0.0, 25.0], f"部分解析应整表回退 TABLE_RE，实际 {probs}")
        self.assertTrue(all(p is not None for p in probs), "回退路径概率不得为 None")
        r = gd._g30_run(_cap(p2="约"), {})
        self.assertIn(3, r["failed"], "部分解析回退后 #3 仍应执法（和=70≠100）")

    def test_top_scenario_shared_impl(self):
        """⑤ capstone_panorama._top_scenario 共享 _g30_find_scenarios（lazy import）→ 与表 max 一致。"""
        import capstone_panorama as cp
        cap = gd._g30_find_capstone(_cap())
        self.assertEqual(cp._top_scenario(cap), ("中性", 45.0))
        self.assertIsNone(cp._top_scenario("无情景文本"), "空手文本应返回 None")


class TestG30CapstoneHijack(unittest.TestCase):
    """G30 capstone 定位劫持回归（2026-08-28 修复：候选迭代+切片验签）。

    事故形态六起（唯特偶 4.2「股东行为综合研判」/ 君正 §11.4「LLM 研判」/ 株冶 3.5.4
    「±30% 情景」/ 赛微 Q6「三情景裁决」+7.5.1「定性研判」双诱饵 / 厦钨 §7.3「研判」/
    东田微 m4 小节）：旧 `_G30_CAPSTONE_HEAD_RE` 单向取首个匹配 → 前置诱饵标题劫持切片
    → #1-#4 连锁 FAIL 且报内容层症状（写手误诊改内容不改标题）。
    修复后定位走 section_locator.locate（迭代全部候选 + heading 级验签）。"""

    @staticmethod
    def _with_decoy(decoy: str) -> str:
        """合规 CAP 前插诱饵标题（# 报告 与 capstone 之间）。"""
        return "# 报告\n\n" + decoy + "\n\n" + CAP.format(
            l1="中性", l2="乐观", l3="悲观", p1="45%", p2="30%", p3="25%"
        ) + "\n\n## 模块七\n"

    @staticmethod
    def _h2_capstone_report(prefix: str) -> str:
        """## 级 capstone 报告（真实报告形态）：CAP 模板首行（### 综合研判 Capstone（G30））
        换成 ## 综合研判，诱饵 prefix 在前。"""
        body = CAP.format(l1="中性", l2="乐观", l3="悲观", p1="45%", p2="30%", p3="25%")
        return "# 报告\n\n" + prefix + "\n\n## 综合研判\n\n" + \
            body.split("\n", 1)[1] + "\n\n## 模块七\n"

    def test_pre_h3_weiteou_42(self):
        """唯特偶形态：`### 4.2 股东行为综合研判（ST3）` 劫持 → 修复后 PASS。"""
        r = gd._g30_run(self._with_decoy("### 4.2 股东行为综合研判（ST3）\n\n机构调研频繁。"), {})
        self.assertTrue(r["passed"], f"诱饵应被跳过，failed={r['failed']}, reasons={r['reasons']}")

    def test_pre_h3_junzheng_llm(self):
        """君正形态：`### 11.4 …（LLM 研判）` 劫持 → 修复后 PASS。"""
        r = gd._g30_run(self._with_decoy("### 11.4 资金流与共识（LLM 研判）\n\n主力净流入。"), {})
        self.assertTrue(r["passed"], f"诱饵应被跳过，failed={r['failed']}, reasons={r['reasons']}")

    def test_pre_h3_zhuye_sensitivity(self):
        """株冶形态：`### 3.5.4 价格敏感性测算（±30% 情景）` 劫持 → 修复后 PASS。"""
        r = gd._g30_run(self._with_decoy("### 3.5.4 价格敏感性测算（±30% 情景）\n\n敏感性测算表。"), {})
        self.assertTrue(r["passed"], f"诱饵应被跳过，failed={r['failed']}, reasons={r['reasons']}")

    def test_dual_decoy_saiwei(self):
        """赛微双诱饵（Q6「三情景裁决」+ 7.5.1「定性研判」）→ 修复后 PASS。"""
        r = gd._g30_run(self._with_decoy(
            "### Q6：值不值得买？——三情景裁决\n\n结论一句话。\n\n"
            "### 7.5.1 政策传导链（定性研判）\n\n传导路径。"), {})
        self.assertTrue(r["passed"], f"双诱饵应被跳过，failed={r['failed']}, reasons={r['reasons']}")

    def test_h2_tldr_prose_decoy(self):
        """T9a：`## ⚡ 速览：综合研判结论` + 散文「投资建议」（非 heading）→ 验签拒诱饵，
        锚 ## 级真 capstone → PASS。"""
        rep = self._h2_capstone_report(
            "## ⚡ 速览：综合研判结论（TL;DR）\n\n投资建议：观望。三档情景中中性概率 50%。")
        r = gd._g30_run(rep, {})
        self.assertTrue(r["passed"], f"散文投资建议不应过 heading 验签，failed={r['failed']}")
        from section_locator import locate
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("## 综合研判"), "应锚 ## 级真 capstone 而非速览诱饵")

    def test_h2_tldr_subheading_residual(self):
        """T9b 已接受残留（2026-08-28 拍板）：`## 速览：综合研判` + 其下 `### 投资建议`
        子标题 → heading 级验签通过、仍锚诱饵（= 旧取首语义；该形态需双巧合，无已知
        事故）。锁定现状防无意识变化；提高验签阈值须重评芯碁微装形态（单特征子节）。"""
        rep = self._h2_capstone_report("## 速览：综合研判\n\n### 投资建议\n\n观望。")
        from section_locator import locate
        sl, d = locate(rep)
        self.assertEqual(d, "ok@heading")
        self.assertTrue(sl.startswith("## 速览：综合研判"), "残留形态行为变化=回归红线")
        r = gd._g30_run(rep, {})
        self.assertFalse(r["passed"], "残留形态下 capstone 内容不在切片 → 内容检查照常执法")

    def test_m6_missing_reason_routes_to_locator_layer(self):
        """m6 缺失：旧=静默全文回退+内容层症状（#2「情景块不足3」误诊形态）→
        修复后显式定位层 reason，写手第一眼归因。"""
        r = gd._g30_run("# 报告\n\n## 一、概况\n\n基本面描述。\n\n## 二、财务\n\n营收增长 20%。\n", {})
        self.assertFalse(r["passed"])
        self.assertIn("定位层", r["reasons"][0], f"reasons[0] 须定位层归因，实际: {r['reasons'][:1]}")

    def test_trigger_in_prose_only_not_anchored(self):
        """触发词仅在散文/表格行（无标题）→ 不锚，走定位层车道（heading 边界固化）。"""
        rep = "# 报告\n\n本节做综合研判：中性概率 50%。\n\n| 乐观 | 42% |\n|---|---|\n\n"
        r = gd._g30_run(rep, {})
        self.assertFalse(r["passed"])
        self.assertIn("定位层", r["reasons"][0])

    def test_feat_word_heading_no_trigger_not_candidate(self):
        """T2 边界：capstone 前的特征词标题（含「全景」但非 5 词候选）不会成为锚。"""
        r = gd._g30_run(self._with_decoy("### 全景速览\n\n一览数据。"), {})
        self.assertTrue(r["passed"], f"非候选标题不应扰动定位，failed={r['failed']}")


if __name__ == "__main__":
    unittest.main()
