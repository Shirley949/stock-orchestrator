#!/usr/bin/env python3
"""test_diag_contract — 诊断契约 v2（diag 五字段 + 引擎修复批）两极测试。

S1 测试先行：首轮跑必须**红在且仅红在「新功能缺席」**（用例标注 [RED-缺席]）；
既有行为用例（[GREEN-既有]/[GREEN-不变]）首轮即绿。S2（引擎修复）/S3（diag 管线）
/S4（补线）逐项转绿，此后全量保持绿——回归层防退化。

覆盖（plan 四节 C2-C15，fixture 真值已 2026-08-31 实测）：
  TestG63Percentile      C2/C3    分位剥离（金安 94.78/99 实锤）+ 执法力反例
  TestG30MainRec         C4/C5    主推荐两遍扫描 + 否定窗（金安实锤）+ 正例不误伤
  TestG55Collection      C6       五臂收集化（德福实锤；301511 VWAP 真值 89.83）
  TestG56Collection      C7       七臂收集化 + GATE_HINTS G56 剔除夹带的 SGR 句
  TestG62HeaderSignature C8-C11   表头签名（德福实锤）/硬臂执法力/引擎软披露/披露豁免
  TestG21Suggestions     C12/C13  PATH_ALIASES 六条 suggestion + 全量诚实（cap5+diag）
  TestR5Reasons          C14      28 门裸 False 补线（源码级全量 + 行为级抽样）
  TestDiagContract       C15/L2   FAIL 100% 带 diag（fixtures+真实 FAIL 对）+ 绕过 lint

跑：python3 test_diag_contract.py
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "scripts"))
sys.path.insert(0, str(_HERE.parent / "scripts" / "lib"))

import gate_definitions as gd  # noqa: E402
from gate_definitions import (  # noqa: E402
    GATE_HINTS, check_g21, check_g55, check_g56, check_g62, check_g63,
    check_g47, _g30_extract_main_rec_action)
from verify_gates import verify_gates  # noqa: E402

CORPUS = Path(os.path.expanduser("~/.cache/skill-snapshots/full"))
SNAP_636 = CORPUS / "002636_20260831.json"   # 金安（G63 分位实锤票）
SNAP_511 = CORPUS / "301511_20260831.json"   # 德福（G55 VWAP 89.83 / G62 引擎 7/4/2）


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# C2/C3 — G63 分位剥离（E1）
# ---------------------------------------------------------------------------
class TestG63Percentile(unittest.TestCase):
    """金安实锤重构：『换手率 99 分位』的 99 被当价位，距真值 94.78 偏 4.5% 误判转录错。"""

    @classmethod
    def setUpClass(cls):
        if not SNAP_636.exists():
            raise unittest.SkipTest("语料缺席：002636_20260831.json")
        cls.data = _load(SNAP_636)

    def _m3(self, body: str) -> str:
        return "## 三、技术分析\n" + body + "\nTD 共振。\n"

    def test_c2_percentile_not_price(self):
        """[RED-缺席] C2：分位数非价位——改后须 PASS（改前实测 FAIL，偏 4.5% 误伤）。"""
        ret = check_g63(self._m3("换手率 99 分位，支撑 94.78 承接"), self.data)
        ok = ret if isinstance(ret, bool) else ret.get("passed", True)
        self.assertTrue(ok, f"分位数仍被当价位：{ret if isinstance(ret, bool) else ret.get('reasons')}")

    def test_c2b_fraction_percentile(self):
        """[RED-缺席] C2b（P5）：分数形式 99/100 分位——分子分母一起剥，改后须 PASS。"""
        ret = check_g63(self._m3("换手率 99/100 分位，支撑 94.78 承接"), self.data)
        self.assertTrue(ret if isinstance(ret, bool) else ret.get("passed", ret is True),
                        "分数形式分位残留 99 仍被当价位")

    def test_c3_enforcement_kept(self):
        """[GREEN-既有] C3：真转录错（95.5 vs 94.78 偏 0.8%）——改前改后均须 FAIL。"""
        ret = check_g63(self._m3("阻力 95.5。"), self.data)
        ok = ret if isinstance(ret, bool) else ret.get("passed", True)
        self.assertFalse(ok, "宽松化后执法力回退：真转录错逃逸")

    def test_c3b_support_exact_still_pass(self):
        """[GREEN-既有] C3b：照抄真值 94.78 精确命中——恒 PASS。"""
        ret = check_g63(self._m3("支撑 94.78 承接。"), self.data)
        ok = ret if isinstance(ret, bool) else ret.get("passed", True)
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# C4/C5 — G30#5 主推荐两遍扫描 + 否定窗（E2）
# ---------------------------------------------------------------------------
class TestG30MainRec(unittest.TestCase):

    CAP_4LENS = (
        "## 六、综合研判\n### 四镜头\n"
        "综合结论：四镜头合计……筹码面不支持现价加仓。\n"
        "### 建议\n投资建议：持有观望。\n"
    )

    def test_c4_negation_window(self):
        """[RED-缺席] C4：四镜头否定句不得劫持主推荐——须取投资建议行的「持有」。"""
        self.assertEqual(_g30_extract_main_rec_action(self.CAP_4LENS), "持有",
                         "主推荐动作被「不支持现价加仓」污染")

    def test_c5_positive_anchors(self):
        """[GREEN-既有] C5：正例两形态——强锚行提取不受两遍改造影响。"""
        self.assertEqual(_g30_extract_main_rec_action("投资建议：持有。"), "持有")
        self.assertEqual(_g30_extract_main_rec_action("操作建议：逢低加仓。"), "加仓")

    def test_c5b_weak_anchor_fallback(self):
        """[GREEN-既有] C5b：无强锚行时仍回退弱锚（含「结论」行）——不丢执法。"""
        self.assertEqual(_g30_extract_main_rec_action("综合结论：建议减持观望。"), "减持")


# ---------------------------------------------------------------------------
# C6 — G55 五臂收集化（E3）
# ---------------------------------------------------------------------------
class TestG55Collection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not SNAP_511.exists():
            raise unittest.SkipTest("语料缺席：301511_20260831.json")
        cls.data = _load(SNAP_511)

    # 六维仅覆盖 3 维（缺 位置/筹码）+ 仓位越界 + VWAP 写「字段为空」→ 三臂齐触发
    REPORT = ("## 三、技术分析（m3 golden）\n"
              "ADX 22 环境偏强；换手 3.2% 量能放大；MACD 金叉趋势向上。\n"
              "仓位建议 30%，盈亏比 2:1。\n"
              "VWAP：字段为空。\n")

    def _run(self):
        return check_g55(self.REPORT, self.data)

    def test_c6_all_arms_reported(self):
        """[RED-缺席] C6：三臂齐报（维度覆盖/越界仓位/VWAP）——改前只报首臂。"""
        ret = self._run()
        reasons = (ret.get("reasons") if isinstance(ret, dict) else None) or []
        self.assertFalse(ret.get("passed", True) if isinstance(ret, dict) else ret,
                         "三臂构造必 FAIL")
        self.assertGreaterEqual(len(reasons), 3,
                                f"须三臂齐报（一轮修完），实际 {len(reasons)} 条：{reasons}")

    def test_c6_vwap_reason_carries_truth(self):
        """[RED-缺席] C6：VWAP 臂 reason 须携带真值 89.83 与照抄路径。"""
        ret = self._run()
        reasons = (ret.get("reasons") if isinstance(ret, dict) else None) or []
        joined = "".join(reasons)
        self.assertIn("89.83", joined, "VWAP 臂 reason 未携带引擎真值")
        self.assertIn("s2_quote_kline.data.realtime_quote.vwap", joined)

    def test_c6_noop_without_m3(self):
        """[GREEN-既有] C6：无 m3 段不执法（no-op 三态）。"""
        self.assertTrue(check_g55("## 一、标的概况\n业务叙事，无技术段。", self.data))


# ---------------------------------------------------------------------------
# C7 — G56 七臂收集化 + GATE_HINTS 修正（E3）
# ---------------------------------------------------------------------------
class TestG56Collection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not SNAP_511.exists():
            raise unittest.SkipTest("语料缺席：301511_20260831.json")
        cls.data = _load(SNAP_511)   # primary_type=成长股

    # 五块全有（不触发五块臂）；类型词缺失 + 🆕 残留 + 资金无指路 → 三臂齐触发
    REPORT = ("## 一、标的概况\n"
              "主营铜箔。历史阶段已过产能爬坡。当前阶段定位放量期。同行差异化显著。\n"
              "🆕 新接线信号。\n资金面近期活跃。\n"
              "## 二、下文\n后续模块。\n")

    def test_c7_all_arms_reported(self):
        """[RED-缺席] C7：类型缺失/🆕 残留/指路缺失三臂齐报——改前只报首臂。"""
        ret = check_g56(self.REPORT, self.data)
        reasons = (ret.get("reasons") if isinstance(ret, dict) else None) or []
        self.assertGreaterEqual(len(reasons), 3,
                                f"须三臂齐报，实际 {len(reasons)} 条：{reasons}")
        joined = "".join(reasons)
        self.assertIn("成长", joined)       # 类型臂携带 primary_type 真值
        self.assertIn("🆕", joined)

    def test_c7_gate_hints_no_sgr(self):
        """[RED-缺席] C7：GATE_HINTS G56 条目不得再夹带 G51 的 SGR 句。"""
        self.assertNotIn("SGR", GATE_HINTS.get("G56", ""),
                         "G56 hint 夹带 G51 SGR 数据核对句（G51 hint 已覆盖）")

    def test_c7_noop_without_m1(self):
        """[GREEN-既有] C7：无标的概况段不执法。"""
        self.assertTrue(check_g56("## 五、估值\n无 m1 段。", self.data))


# ---------------------------------------------------------------------------
# C8-C11 — G62 表头签名 + 引擎软披露（E4）
# ---------------------------------------------------------------------------
class TestG62HeaderSignature(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not SNAP_511.exists():
            raise unittest.SkipTest("语料缺席：301511_20260831.json")
        cls.data = _load(SNAP_511)   # 引擎 tally advisory = 7偏多/4中性/2偏空

    CLAIM = "信号方向 tally：5 偏多 / 6 中性 / 3 偏空（本表裁决口径）。"
    # 证据全景表（表头第 2 列字面=方向）实数 5/6/3
    TALLY_TABLE = ("| 维度 | 方向 | 现状（拉取值） |\n|---|---|---|\n"
                   + "".join(f"| ①{c} | 偏多 | v |\n" for c in "abcde")
                   + "".join(f"| ②{c} | 中性 | v |\n" for c in "abcdef")
                   + "".join(f"| ③{c} | 偏空 | v |\n" for c in "ghi"))
    # §3.2 污染表：表头第 2 列=状态（非「方向」），单元格裸方向词——不得计入
    POLLUTED_TABLE = ("| 指标 | 状态 | 解读 |\n|---|---|---|\n"
                      "| KDJ | 中性 | 高位钝化 |\n| RSI | 中性 | 强势区 |\n")

    def test_c8_header_signature_kills_pollution(self):
        """[RED-缺席] C8：§3.2 表（第2列=状态）污染计数——改后须 PASS（改前误 FAIL）。"""
        report = "## 三、技术分析\n" + self.POLLUTED_TABLE + "\n## 六、综合研判\n" \
                 + self.CLAIM + "\n" + self.TALLY_TABLE
        ret = check_g62(report, self.data)
        ok = ret if isinstance(ret, bool) else ret.get("passed", True)
        self.assertTrue(ok, f"污染表仍被计入 tally：{getattr(ret, 'get', lambda k, d: d)('reasons')}")

    def test_c9_hard_arm_enforcement(self):
        """[GREEN-既有] C9：自称 6/5/3 vs 表格 5/6/3——改前改后均须 FAIL（防放松）。"""
        report = "## 六、综合研判\n信号方向 tally：6 偏多 / 5 中性 / 3 偏空。\n" + self.TALLY_TABLE
        ret = check_g62(report, self.data)
        ok = ret if isinstance(ret, bool) else ret.get("passed", True)
        self.assertFalse(ok, "硬臂执法力回退：自称与表格不符却 PASS")

    def test_c10_engine_soft_disclosure(self):
        """[RED-缺席] C10（T2）：自称 5/6/3 vs 引擎 7/4/2 未披露——passed=True 但
        reasons 须披露引擎 advisory + 照抄命令（SOFT 不 FAIL，F1 铁证）。"""
        report = "## 六、综合研判\n" + self.CLAIM + "\n" + self.TALLY_TABLE
        ret = check_g62(report, self.data)
        self.assertIsInstance(ret, dict, "软臂必须富返回（携带披露 reason）")
        self.assertTrue(ret.get("passed"), "T2 软臂不得 FAIL（引擎≠自称是合法设计）")
        joined = "".join(ret.get("reasons") or [])
        self.assertIn("7偏多/4中性/2偏空", joined.replace(" ", ""),
                      "reason 未携带引擎 advisory 真值")
        self.assertIn("capstone_panorama.py", joined, "reason 未携带照抄命令")

    def test_c10b_soft_diag_fields(self):
        """[RED-缺席] C10b：软臂 diag.expected=引擎 advisory、found=自称串、degraded=False。"""
        report = "## 六、综合研判\n" + self.CLAIM + "\n" + self.TALLY_TABLE
        ret = check_g62(report, self.data)
        diag = ret.get("diag") if isinstance(ret, dict) else None
        self.assertIsInstance(diag, dict, "软臂须发射 diag")
        self.assertIn("7偏多", str(diag.get("expected")).replace(" ", ""))
        self.assertIn("5偏多", str(diag.get("found")).replace(" ", ""))
        self.assertFalse(diag.get("degraded", True))

    def test_c11_disclosed_exempt(self):
        """[RED-缺席] C11：自称句明示分歧（含引擎值）→ 整体 PASS 且无软披露 reason。
        （实测旧引擎 bug：自称 regex 无锚定，先抓到披露句里的引擎 7/4/2 当 claimed
        → 明示分歧写法在旧引擎下必炸——E4 须让披露句合法，claimed 取本表裁决值。）"""
        report = ("## 六、综合研判\n信号方向 tally：引擎 7偏多/4中性/2偏空，本表裁决 "
                  "5 偏多 / 6 中性 / 3 偏空（估值维下调）。\n" + self.TALLY_TABLE)
        ret = check_g62(report, self.data)
        ok = ret if isinstance(ret, bool) else ret.get("passed", True)
        self.assertTrue(ok, "披露分歧句被抓成 claimed=引擎值 → 明示分歧写法必炸")
        if isinstance(ret, dict):
            joined = "".join(ret.get("reasons") or [])
            self.assertNotIn("引擎", joined, "已披露分歧仍发软提示=噪声")

    def test_c11b_space_variant_disclosure(self):
        """[RED-缺席] C11b（P6）：披露句空格变体「7 偏多/4 中性/2 偏空」同样豁免。"""
        report = ("## 六、综合研判\n信号方向 tally：引擎 7 偏多/4 中性/2 偏空，本表裁决 "
                  "5 偏多 / 6 中性 / 3 偏空。\n" + self.TALLY_TABLE)
        ret = check_g62(report, self.data)
        ok = ret if isinstance(ret, bool) else ret.get("passed", True)
        self.assertTrue(ok, "空格变体披露句未豁免")


# ---------------------------------------------------------------------------
# C12/C13 — G21 PATH_ALIASES suggestion + 全量诚实（E5）
# ---------------------------------------------------------------------------
class TestG21Suggestions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not SNAP_511.exists():
            raise unittest.SkipTest("语料缺席：301511_20260831.json")
        cls.data = _load(SNAP_511)

    BAD6 = ("## 六、综合研判\n"
            "[src: snapshot.s4_technical.data.technical.relative_strength]\n"
            "[src: snapshot.s4_technical.data.td.daily]\n"
            "[src: snapshot.s1_financial.data.cash_flow_statement]\n"
            "[src: snapshot.s9_news]\n"
            "[src: snapshot.signals.events.0]\n"
            "[src: snapshot.s11_peer.data.market_relative]\n")

    def test_c12_alias_suggestions(self):
        """[RED-缺席] C12：六条坏路径 reason 须各含真路径/去下标指引。"""
        ret = check_g21(self.BAD6, self.data)
        self.assertIsInstance(ret, dict)
        joined = "".join(ret.get("reasons") or [])
        for hint in ("s4_technical.data.relative_strength",   # technical. 假层
                     "s4_technical.data.td",                   # td.daily/.weekly → td
                     "s1_financial.data.cash_flow",            # _statement 后缀
                     "s5_events.data.news",                    # s9_news → 真场景
                     "去下标",                                   # .0 数值下标
                     "s11_peer.data"):
            self.assertIn(hint, joined, f"suggestion 缺真路径指引：{hint}")

    def test_c12b_numeric_subscript_still_fails(self):
        """[GREEN-既有] C12b：`.0` 下标仍 FAIL——suggestion 是指引不是豁免（不放宽）。"""
        ret = check_g21(self.BAD6, self.data)
        self.assertFalse(ret.get("passed", True) if isinstance(ret, dict) else bool(ret))

    def test_c13_full_honesty(self):
        """[RED-缺席] C13：7 处坏路径——reasons cap5 + 「共 7 处」改口 + diag 全量 7 条
        + 无「本清单为全量」自相矛盾句。"""
        report = self.BAD6 + "[src: snapshot.s7_nonexistent]\n"
        ret = check_g21(report, self.data)
        self.assertIsInstance(ret, dict)
        reasons = ret.get("reasons") or []
        self.assertLessEqual(len([r for r in reasons if r.startswith("[src:]")]), 5,
                             "reasons 直列须 cap 5")
        joined = "".join(reasons)
        self.assertNotIn("本清单为全量", joined, "cap5 与「全量」并存=自相矛盾")
        self.assertIn("共 7 处", joined)
        diag = ret.get("diag")
        self.assertIsInstance(diag, dict)
        found = diag.get("found")
        self.assertEqual(len(found), 7, f"diag.found 须全量 7 条，实际 {found}")


# ---------------------------------------------------------------------------
# C14 — R5 裸 False 门补线（E7；源码级全量 + 行为级抽样）
# ---------------------------------------------------------------------------
class TestR5Reasons(unittest.TestCase):
    # 2026-08-31 grep 实测（28 门/62 处）；执行时以 grep 重跑为准——此处断言「零残留」
    # 审计 v2（2026-08-31 v2.1）：原 EXPECTED_BARE_GATES 28 门白名单作废——v2.1 已将
    # 7 处尾注裸 False 全部补线，断言升级为全库零裸 False（纯裸 + 尾注形态都算）。
    # 历史 28 门清单存档于 REFACTOR_LOG（G1/G6/G8/G12/G14/G15/G16/G19/G20/G21/G23/
    # G25/G26/G28/G29/G31/G38/G39/G40/G41/G42/G43/G44/G47/G48/G49/G53/G61）。

    @staticmethod
    def _bare_false_checkers() -> dict:
        """源码扫描：{gate: [行号]} 仍裸 `return False` 的 checker（v2.1 含尾注形态——
        `return False   # 注释` 曾整体逃避旧 regex `return False\s*$`，即 C14 盲区本体）。"""
        src = Path(gd.__file__).read_text(encoding="utf-8").splitlines()
        cur, out = None, {}
        for i, ln in enumerate(src, 1):
            m = re.match(r"def (check_g\d+)\(", ln)
            if m:
                cur = m.group(1)[6:].upper()
                out[cur] = []
            elif re.match(r"^(def|class)\s", ln):
                cur = None
            if cur and re.search(r"return False\s*(?:#.*)?$", ln):
                out[cur].append(i)
        return {k: v for k, v in out.items() if v}

    def test_c14_no_bare_false_left(self):
        """[RED-缺席→v2.1 全库执法] C14 源码级：零裸 `return False` 残留（含尾注形态）。"""
        left = self._bare_false_checkers()
        self.assertFalse(left, f"仍有裸 False 未补线（含尾注形态）：{left}")

    def test_c14_g47_reason_carries_trigger(self):
        """[RED-缺席] C14 行为级抽样：G47 presence FAIL 须返回原生 reason 含触发真值
        （非注册表 fail_hint 通用句）。"""
        # 找一份 shareholder_dynamics 有材料级方向的快照，构造报告不含 presence 词
        target = None
        for p in sorted(CORPUS.glob("*.json")):
            d = _load(p)
            sd = gd._snapshot_get(d, "s5_events.data.risk_signals.processed.shareholder_dynamics")
            if isinstance(sd, dict) and sd.get("status") == "ok" and (
                    sd.get("verdict") in ("净减持", "净增持", "分歧")):
                target = (p, d)
                break
        if not target:
            self.skipTest("语料无 shareholder_dynamics 材料级方向票")
        _, data = target
        ret = check_g47("## 一、叙事\n全文无股东行为词。", data)
        self.assertIsInstance(ret, gd.GateResult, "presence FAIL 须原生 GateResult")
        reason = "".join(ret.get("reasons") or [])
        self.assertNotEqual(reason, "")
        self.assertNotEqual(reason, gd.GATE_REGISTRY["G47"]["fail_hint"],
                             "reason 仍是通用 fail_hint——未携带触发真值")
        self.assertTrue(any(k in reason for k in ("净减", "净增", "分歧", "前十大", "内部人", "董监高")),
                        "reason 未携带股东方向触发真值")


# ---------------------------------------------------------------------------
# C15/L2 — diag 管线（E9）：FAIL 100% 带 diag + 绕过 lint
# ---------------------------------------------------------------------------
class TestDiagContract(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not SNAP_511.exists():
            raise unittest.SkipTest("语料缺席：301511_20260831.json")
        cls.data = _load(SNAP_511)
        # C15 素材：构造报告（G55 三臂 + G21 六坏路径 → 至少 2 门 FAIL）
        cls.report = ("## 三、技术分析\nADX 环境；换手量能；MACD 趋势。\n"
                      "仓位 30%。VWAP：字段为空。\n## 六、综合研判\n"
                      "[src: snapshot.s9_news]\n[src: snapshot.signals.events.0]\n")

    @staticmethod
    def _fail_details(result):
        return [d for d in result["details"] if d["status"] == "fail"]

    def test_c15_l1_all_fails_carry_diag(self):
        """[RED-缺席] C15 L1 总闸：全部 FAIL detail 带 diag（checker 发射或 degraded 合成）。"""
        res = verify_gates(self.report, self.data, "profile_full")
        fails = self._fail_details(res)
        self.assertGreaterEqual(len(fails), 2, "fixture 须至少 2 门 FAIL")
        missing = [d["gate"] for d in fails if not d.get("diag")]
        self.assertEqual(missing, [], f"FAIL 项缺 diag：{missing}")

    def test_c15_degraded_flagged_honestly(self):
        """[RED-缺席] C15：框架合成的 diag 须 degraded=True（诚实标注引擎未预计算真值）。"""
        res = verify_gates(self.report, self.data, "profile_full")
        degraded = [d["gate"] for d in self._fail_details(res)
                    if isinstance(d.get("diag"), dict) and d["diag"].get("degraded")]
        # fixture 至少一门走框架合成（非焦点门清单内的裸 False 触发），断言其标注诚实
        for g in degraded:
            diag = next(d["diag"] for d in self._fail_details(res) if d["gate"] == g)
            self.assertTrue(diag.get("fix"), "degraded diag 仍须带 fix（fail_hint 兜底）")

    def test_c15b_real_fail_pairs_carry_diag(self):
        """[RED-缺席] C15b：3 个真实(报告,快照)对（replay 基线 FAIL 对）重算——
        FAIL 项 100% 带 diag。"""
        sys.path.insert(0, str(_HERE))
        from test_archive_replay import _pair_candidates, _gate_vector
        pairs = [p for p in _pair_candidates()]
        fail_pairs = []
        for pid, rpt, snap, prof in pairs:
            vec = _gate_vector(rpt, snap, prof)
            if vec["verdict"] == "FAIL":
                fail_pairs.append((pid, rpt, snap, prof))
            if len(fail_pairs) >= 3:
                break
        if len(fail_pairs) < 1:
            self.skipTest("语料无 FAIL 对")
        for pid, rpt, snap, prof in fail_pairs:
            res = verify_gates(rpt.read_text(encoding="utf-8"),
                               _load(snap), prof)
            missing = [d["gate"] for d in self._fail_details(res) if not d.get("diag")]
            self.assertEqual(missing, [], f"{pid} FAIL 项缺 diag：{missing}")

    def test_l2_bypass_lint(self):
        """[RED-缺席] L2：fix 字符串含绕过话术 → result['diag_lint'] 警告（不 FAIL）。"""
        g1 = gd.GATE_CHECKERS.get("G1")
        def _fake(report, data):
            return gd.GateResult(passed=False, reasons=["测试"],
                                 diag={"fix": "把措辞绕过 gate 检查即可通过"})
        gd.GATE_CHECKERS["G1"] = _fake
        try:
            res = verify_gates("## 一、空报告\n", self.data, "profile_full")
        finally:
            if g1:
                gd.GATE_CHECKERS["G1"] = g1
        self.assertIn("diag_lint", res, "绕过话术未触发 diag_lint 警告")


# ---------------------------------------------------------------------------
# v2.1（2026-08-31）—— 11 站点 reason 真值化：行为级 / 逐臂崩溃面 / [数据层] 契约 /
# 渲染双形态 + bool 返回运行时防线。零翻转构造保证：verify_gates 只消费 verdict，
# reason 升级 verdict 天然中性；以下测试锁地板防回退。
# ---------------------------------------------------------------------------
_V21_CASES = [
    # (站点名, checker, snapshot, bad_report, 必含真值tokens, 行定位marker|None, PASS变体)
    ("G57-high", gd.check_g57,
     {"consensus_forecast": {"data": {"company_guidance":
         {"latest_period": {"value": {"growth_tier": "high"}}}}}},
     "# 报告\n## 模块四 业绩\n公司发布业绩预增公告，上限显著。\n",
     ["high", "高成长"], None,
     "# 报告\n## 模块四 业绩\n公司预增属高成长档 [src: snapshot.consensus_forecast."
     "data.company_guidance.latest_period.value.growth_tier]\n"),
    ("G57-mod", gd.check_g57,
     {"consensus_forecast": {"data": {"company_guidance":
         {"latest_period": {"value": {"growth_tier": "moderate"}}}}}},
     "# 报告\n## 模块四 业绩\n公司发布业绩预增公告。\n",
     ["moderate", "中成长"], None,
     "# 报告\n## 模块四 业绩\n业绩预增属中增长档 [src: snapshot.consensus_forecast."
     "data.company_guidance.latest_period.value.growth_tier]\n"),
    ("G21-m5src", gd.check_g21,
     {"valuation_snapshot": {"data": {"quote": {"peTtm": 15.3, "pbRatio": 2.1}}}},
     "# 报告\n## 模块五 估值分析\nPE 15 倍估值中等 [src: snapshot.valuation_snapshot.data.quote.peTtm]\n"
     "## 模块六 结论\n观望\n",
     ["仅 1", "src"], None,
     "# 报告\n## 模块五 估值分析\nPE 15 倍 [src: snapshot.valuation_snapshot.data.quote.peTtm]，"
     "PB 2.1 [src: snapshot.valuation_snapshot.data.quote.pbRatio]\n## 模块六 结论\n观望\n"),
    ("G32", gd.check_g32, {"lhb": {"data": {"processed": {"status": "failed"}}}},
     "任意报告文本\n", ["[数据层]", "status=failed"], None, None),
    ("G33", gd.check_g33, {"northbound": {"data": {"processed": {"status": "failed"}}}},
     "任意报告文本\n", ["[数据层]", "status=failed"], None, None),
    ("G53", gd.check_g53,
     {"s4_technical": {"status": "ok", "data": {"turnover": {"pct_250": 80}}}},
     "# 报告\n## 模块三 技术分析\n换手率处于自身第60分位，均线多头排列。\n",
     ["pct_250=80", "60"], "第60分位",
     "# 报告\n## 模块三 技术分析\n换手率处于自身第80分位，均线多头排列。\n"),
    ("G61", gd.check_g61, {"s_stock_evaluation": {"data": {"status": "failed"}}},
     "任意报告文本\n", ["[数据层]", "status=failed"], None, None),
    ("G51a", gd.check_g51, {"computed_metrics": {}},
     "# 报告\n## 模块二 财务\nSGR=27.40%，可持续增长空间充足。\n",
     ["27.40"], "SGR=27.40",
     "# 报告\n## 模块二 财务\nSGR 未计算（无信封），不展开。\n"),
    ("G51b", gd.check_g51,
     {"computed_metrics": {"sgr": {"status": "ok", "applicability": "金融股不适用", "value": None}}},
     "# 报告\n## 模块二 财务\nSGR 不适用；但历史可持续增长率约 25%。\n",
     ["25", "金融股不适用"], "可持续增长率约 25%",
     "# 报告\n## 模块二 财务\nSGR 不适用（金融股）。\n"),
    ("G52", gd.check_g52, {"s4_technical": {"status": "ok", "data": {}}},
     "# 报告\n## 模块三 技术分析\n量价配合，ATR 3.2 元，破位风险可控。\n",
     ["3.2"], "ATR 3.2",
     "# 报告\n## 模块三 技术分析\n量价配合，ATR 未计算。\n"),
    ("G58", gd.check_g58, {"valuation_snapshot": {"data": {}}},
     "# 报告\n## 模块五 估值分析\n当前 PE 处于 75% 分位，同业对比偏贵。\n",
     ["75"], "75% 分位",
     "# 报告\n## 模块五 估值分析\n分位数据缺失，不展开分位判断。\n"),
]


def _verdict_and_reasons(fn, report, data):
    ret = fn(report, data)
    if isinstance(ret, dict):
        return bool(ret.get("passed")), " | ".join(ret.get("reasons") or []), ret.get("diag")
    return bool(ret), "", None


class TestV21ArmReasons(unittest.TestCase):
    """11 站点行为级：FAIL 保持 + 真值 token 直达 + 违规行号 + diag 六键 + PASS 变体不翻转。"""

    _DIAG_KEYS = ("subcheck", "expected", "found", "fix", "src", "degraded")

    def test_fail_keeps_verdict_carries_truth(self):
        for name, fn, snap, bad, tokens, marker, _good in _V21_CASES:
            with self.subTest(site=name):
                ok, joined, diag = _verdict_and_reasons(fn, bad, snap)
                self.assertFalse(ok, f"{name} 未 FAIL（verdict 回退）")
                for t in tokens:
                    self.assertIn(t, joined, f"{name} reason 缺真值 {t!r}：{joined[:120]}")
                if marker:
                    ln = next(i for i, l in enumerate(bad.split("\n"), 1) if marker in l)
                    self.assertIn(f"L{ln}", joined, f"{name} 未定位违规行 L{ln}")
                self.assertIsInstance(diag, dict, f"{name} 无 diag")
                for k in self._DIAG_KEYS:
                    self.assertIn(k, diag, f"{name} diag 缺 {k}")
                self.assertFalse(diag.get("degraded"), f"{name} 原生 diag 须 degraded=False")

    def test_pass_variant_stays_pass(self):
        for name, fn, snap, _bad, _tokens, _marker, good in _V21_CASES:
            if good is None:  # G32/G33/G61 的 PASS 变体 = 合法快照（status ok/missing）
                continue
            with self.subTest(site=name):
                ok, _, _ = _verdict_and_reasons(fn, good, snap)
                self.assertTrue(ok, f"{name} PASS 变体翻转")

    def test_data_layer_pass_variants(self):
        """G32/G33/G61 合法态（ok+真空 / missing）PASS——[数据层] 前缀只出现在失败臂。"""
        ok, joined, _ = _verdict_and_reasons(
            gd.check_g32, "x", {"lhb": {"data": {"processed":
                {"status": "ok", "signal_type": "never_listed"}}}})
        self.assertTrue(ok)
        self.assertNotIn("[数据层]", joined)
        self.assertTrue(gd.check_g61("x", {"s_stock_evaluation": {"data": {"status": "missing"}}}))


class TestV21CrashPaths(unittest.TestCase):
    """定理边界封闭（裁决⑥）：verdict 等价只在双方都跑完时成立——v2.1 新增的真值查找/
    行号定位是新的崩溃面，逐臂 × {scene 缺, 字段 None, 类型异常} 断言无新崩溃。
    Battery B 形态：以真实冻结快照 deepcopy 挖键构造缺失态。"""

    @classmethod
    def setUpClass(cls):
        cls.base = _load(SNAP_511) if SNAP_511.exists() else {}

    def _variants(self, path):
        """path 如 'consensus_forecast.data.company_guidance' → 三种破坏态快照列表"""
        import copy
        out = []
        # ① scene 缺：整棵键删除
        v1 = copy.deepcopy(self.base)
        top = path.split(".")[0]
        v1.pop(top, None)
        out.append(("scene缺", v1))
        # ② 字段 None：沿路径逐层置 None（取最深存在的层）
        v2 = copy.deepcopy(self.base)
        cur = v2
        keys = path.split(".")
        for k in keys[:-1]:
            if not isinstance(cur, dict):
                break
            cur = cur.get(k) if isinstance(cur.get(k), dict) else None
            if cur is None:
                break
        if isinstance(cur, dict):
            cur[keys[-1]] = None
        out.append(("字段None", v2))
        # ③ 类型异常：裸 error 信封（真实形态——CLAUDE.md 记载 API 坏 JSON 会落 {"error": ...}）。
        #    注：scene=list 形态不在测试面——违反 runner schema（scene 恒 dict/None），且其对
        #    `s4.get` 的 AttributeError 是 v2.1 之前就存在的原生前置行崩溃，非本批新增崩溃面。
        v3 = copy.deepcopy(self.base)
        v3[top] = {"error": "Expecting value: line 1 column 1 (char 0)"}
        out.append(("类型异常", v3))
        return out

    def test_all_arms_survive_missing_paths(self):
        ARM_PATHS = [
            ("G57", gd.check_g57, "consensus_forecast.data.company_guidance"),
            ("G21", gd.check_g21, "valuation_snapshot.data"),
            ("G32", gd.check_g32, "lhb.data.processed"),
            ("G33", gd.check_g33, "northbound.data.processed"),
            ("G51", gd.check_g51, "computed_metrics.sgr"),
            ("G52", gd.check_g52, "s4_technical.data.atr"),
            ("G53", gd.check_g53, "s4_technical.data.turnover"),
            ("G58", gd.check_g58, "valuation_snapshot.data.valuation_percentile"),
            ("G61", gd.check_g61, "s_stock_evaluation.data"),
        ]
        rep = ("# 报告\n## 模块三 技术分析\n换手率处于第60分位，均线多头；ATR 3.2 元。\n"
               "## 模块五 估值分析\nPE 处于 75% 分位 [src: snapshot.valuation_snapshot.data.quote.peTtm]\n"
               "SGR=27.40% 可持续增长；业绩预增公告高成长。\n")
        for gname, fn, path in ARM_PATHS:
            for mode, snap in self._variants(path):
                with self.subTest(gate=gname, mode=mode):
                    ret = fn(rep, snap)   # 唯一断言：不抛异常（返回形状合法）
                    self.assertIsInstance(ret, (bool, dict))


class TestV21DataLayerContract(unittest.TestCase):
    """[数据层] 机器可检契约（裁决②B）：A=fix 禁改稿动词；B=degraded:True ⇔ 无 found。"""

    _EDIT_VERBS = re.compile(r"照抄|改写|删除|删或改|补写")

    def test_data_layer_fix_has_no_edit_verbs(self):
        for name, fn, snap, bad, _t, _m, _g in _V21_CASES:
            ok, joined, diag = _verdict_and_reasons(fn, bad, snap)
            if not ok and "[数据层]" in joined:
                with self.subTest(site=name):
                    self.assertIsInstance(diag, dict)
                    self.assertIsNone(
                        self._EDIT_VERBS.search(diag.get("fix") or ""),
                        f"{name} [数据层] fix 含改稿动词：{diag.get('fix')}")
                    self.assertFalse(diag.get("degraded"), "[数据层] 原生 diag 须 degraded=False")

    def test_degraded_iff_no_found_on_real_failures(self):
        """规则 B 全库一致性：真实验证跑一遍，FAIL 项 degraded=True ⟺ found 空。"""
        if not SNAP_511.exists():
            self.skipTest("语料缺席")
        report = ("## 三、技术分析\nADX 环境；换手量能；MACD 趋势。\n仓位 30%。VWAP：字段为空。\n"
                  "## 六、综合研判\n[src: snapshot.s9_news]\n[src: snapshot.signals.events.0]\n")
        res = verify_gates(report, _load(SNAP_511), "profile_full")
        checked = 0
        for d in res["details"]:
            if d["status"] != "fail" or not isinstance(d.get("diag"), dict):
                continue
            diag = d["diag"]
            has_found = diag.get("found") not in (None, [], "", {})
            self.assertEqual(bool(diag.get("degraded")), not has_found,
                             f"{d['gate']}：degraded={diag.get('degraded')} 与 found={diag.get('found')!r} 不自洽")
            checked += 1
        self.assertGreater(checked, 0, "fixture 须至少 1 个 FAIL 项参与一致性检查")


class TestV21DualFormRenderAndBoolWarn(unittest.TestCase):
    """渲染层双形态兼容（裁决④b）：diag 六键门与 fail_hint 兜底门过渡期共存不炸；
    bool 返回运行时 warn（裁决①）机制在位。"""

    @classmethod
    def setUpClass(cls):
        if not SNAP_511.exists():
            raise unittest.SkipTest("语料缺席：301511_20260831.json")
        cls.data = _load(SNAP_511)
        cls.report = ("## 三、技术分析\nADX 环境；换手量能；MACD 趋势。\n仓位 30%。VWAP：字段为空。\n"
                      "## 六、综合研判\n[src: snapshot.s9_news]\n[src: snapshot.signals.events.0]\n")

    def test_dual_form_coexist(self):
        res = verify_gates(self.report, self.data, "profile_full")
        fails = [d for d in res["details"] if d["status"] == "fail"]
        native = [d for d in fails if isinstance(d.get("diag"), dict)
                  and not d["diag"].get("degraded")]
        fallback = [d for d in fails if isinstance(d.get("diag"), dict)
                    and d["diag"].get("degraded")]
        self.assertTrue(native, "须存在原生 diag 形态 FAIL（G21/G55 等带真值门）")
        self.assertTrue(fallback, "须存在 fail_hint 兜底形态 FAIL（bool 门，过渡期合同）")
        for d in native + fallback:   # 两形态都完整渲染：reasons + diag 键在场
            self.assertIn("reasons", d)
            self.assertIsInstance(d["diag"], dict)
        self.assertIn("action_required", res)   # 渲染出口不炸

    def test_bool_return_warn_fires(self):
        """bool 返回门 FAIL 时 warn 上浮 sidecar（升级硬断言的条件=一轮 cron 零命中）。
        2026-09-01 起改为注入裸 bool checker——WP 批转化后真实夹具已无裸 bool-FAIL
        火种（301511 夹具 G11 等已 GateResult 化），机制证明不再依赖哪门恰好 lossy。"""
        orig = gd.GATE_CHECKERS.get("G6")
        gd.GATE_CHECKERS["G6"] = lambda r, d: False      # 注入裸 bool FAIL
        try:
            res = verify_gates(self.report, self.data, "profile_full")
        finally:
            gd.GATE_CHECKERS["G6"] = orig
        self.assertIn("bool_return_warn", res,
                      "裸 bool FAIL 在场时须有 warn；若缺失=warn 机制本身失效")
        self.assertIn("G6", res["bool_return_warn"])
        self.assertIsInstance(res["bool_return_warn"], list)


# ---------------------------------------------------------------------------
# 批2 — trap_corpus.yaml 永久陷阱语料（裁决C-1/C-2：形态进 fixture 才是回归保护）
# ---------------------------------------------------------------------------
class TestTrapCorpus(unittest.TestCase):
    """消费 regression-tests/trap_corpus.yaml，按 check 字段分发断言。
    新陷阱先入 references/trap_ledger.yaml（签名/修法），再在此语料登记形态 case。"""

    @classmethod
    def setUpClass(cls):
        p = _HERE / "trap_corpus.yaml"
        if not p.exists():
            raise unittest.SkipTest("trap_corpus.yaml 缺席")
        cls.cases = yaml.safe_load(p.read_text(encoding="utf-8"))["cases"]

    def test_corpus_schema(self):
        """每条 case 带 id/gate/check/line/source 且 id 唯一（新增形态的最低合同）。"""
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)), f"corpus id 重复：{ids}")
        for c in self.cases:
            for key in ("gate", "check", "line", "source"):
                self.assertIn(key, c, f"case {c.get('id')} 缺 {key}")

    def test_tokenizer_no_percentile_number(self):
        """批2#1：分位族全形态（分位/百分位/分位数/分数）数字不得泄漏为价位候选。
        修前实锤（HEAD 旧引擎逐字复跑）：『94 百分位』『第99百分位』泄漏 94/99 →
        G63 误判转录错（偏 0.8%/4.5%）；修后 E1 剥全形态。"""
        cases = [c for c in self.cases if c["check"] == "tokenizer_no_percentile_number"]
        self.assertGreaterEqual(len(cases), 4, "分位族四形态语料不齐")
        for c in cases:
            got = gd._extract_price_candidates(c["line"])
            self.assertEqual(got, [], f"{c['id']}：分位数字泄漏为价位候选 {got}")

    def test_g63_e2e_bai_percentile_flip(self):
        """批2#1 单元级翻转对账：语境词行含『94 百分位』+照抄真值 94.78——
        修前 FAIL（94≈94.78 偏 0.8% 误伤，语料现存 7 处活雷）→ 修后 PASS。"""
        if not SNAP_636.exists():
            raise unittest.SkipTest("语料缺席：002636_20260831.json")
        body = "换手率处于 94 百分位，量能节奏中性，支撑 94.78 附近承接有效。"
        ret = check_g63("## 三、技术分析\n" + body + "\nTD 共振。\n", _load(SNAP_636))
        ok = ret if isinstance(ret, bool) else ret.get("passed", True)
        self.assertTrue(ok, f"百分位数字仍被对拍真值误伤：{ret}")

    def test_g30_synonym_surface(self):
        """批2#5：fatal event_type 与报告措辞同义不同形（增发×定增，德福实锤）不漏
        surface；执法力反例（配售=两者皆非）仍须报缺失。修前 HEAD 复跑误报 finding。"""
        snap_min = {"s5_events": {"data": {"risk_signals": {"processed": {
            "status": "ok",
            "timeline": {"status": "ok", "future": [], "active": [],
                         "fatal_events": [{"event_type": "增发", "level1_content": "增发新股"}]},
        }}}}}
        cases = [c for c in self.cases if c["check"] == "g30_synonym_surface"]
        self.assertTrue(cases, "g30 同义词语料缺席")
        for c in cases:
            rpt = f"## 4.1.1 大事提醒时间线\n{c['line']}\n"
            self.assertEqual(gd._g30_announcement_registry_findings(snap_min, rpt), [],
                             f"{c['id']}：同义措辞仍被误报漏 surface")
        # 执法力保持：既非 event_type 也非同义词 → 仍须 finding
        self.assertTrue(gd._g30_announcement_registry_findings(
            snap_min, "## 4.1.1 大事提醒时间线\n配售事项已披露。\n"),
            "同义归一过宽：真漏 surface 逃逸")

    def test_g30_first_action(self):
        """批2#2 七句评测（裁决C-2 口径：5 误判翻转 + 2 回归锚）。E2v2 = 否定窗
        标点截断 + 紧邻否定词（没有|难以|不再|放弃|拒绝 ≤2 字符）。修前实测 1/7。"""
        from gate_definitions import _g30_first_action
        cases = [c for c in self.cases if c["check"] == "g30_first_action"]
        self.assertGreaterEqual(len(cases), 7, "G30#5 七句评测语料不齐")
        hits = 0
        for c in cases:
            got = _g30_first_action(c["line"])
            if got == c["expect"]:
                hits += 1
            else:
                self.fail(f"{c['id']}：want={c['expect']} got={got}")
        self.assertEqual(hits, len(cases))

    def test_g21_registry_hint(self):
        """批2#4：G21 坏路径第 1 层走 registry（data_contracts.SCENES）——scene 在
        注册表而快照未生成 → [数据层] 归因（非路径拼写问题）；拼写错 → 近邻建议，
        禁退化为裸路径报错。修前两者均无建议可给。"""
        snap = {"mode": "A", "s4_technical": {"data": {"td": {"daily": 1}}}}
        cases = [c for c in self.cases if c["check"] == "g21_registry_hint"]
        self.assertGreaterEqual(len(cases), 2, "g21 registry 语料不齐")
        for c in cases:
            hint = gd._explain_bad_path(snap, c["line"])
            self.assertIn(c["expect"], hint, f"{c['id']}：提示缺 registry/数据层 归因——{hint}")


class TestWP1aWordGates(unittest.TestCase):
    """WP1a（2026-09-01）：G7/G8/G9 词表门 FAIL 臂 reason 真值化（reason-only，verdict 中性）。

    三门分类（[数据层] 家族归类）：全部 FAIL 臂均为写作侧词表/披露门，无 [数据层] 臂
    （G8 rows=0 臂含报告侧「如实披露」动作，故不带前缀）。
    """

    _DIAG_KEYS = ("subcheck", "expected", "found", "fix", "src", "degraded")

    FA = {"s1_financial": {"data": {"financial_abstract": {"data": [
        {"选项": "常用指标", "指标": "扣非净利润", "20260630": 7.7e8, "20250630": 0.73e8}]}}}}
    CF = {"s1_financial": {"data": {"cash_flow": {"status": "ok", "data": [
        {"报告日": "2026-06-30", "经营活动产生的现金流量净额": 3.59e8}]}}}}
    INC = {"s1_financial": {"data": {"income_statement": {"data": [
        {"报告日": "2026-06-30", "净利润": 1.0e9}, {"报告日": "2026-03-31", "净利润": 0.1e9}]}}}}

    def _ret(self, fn, rpt, snap):
        r = fn(rpt, snap)
        return (bool(r.get("passed")), " | ".join(r.get("reasons") or []), r.get("diag")) \
            if isinstance(r, dict) else (bool(r), "", None)

    def _assert_fail_truth(self, ok, joined, diag, tokens, line_no=None, line_txt=None):
        self.assertFalse(ok, "verdict 回退（应 FAIL）")
        for t in tokens:
            self.assertIn(t, joined, f"reason 缺真值 {t!r}：{joined[:120]}")
        if line_no is not None:
            self.assertIn(f"L{line_no}", joined, f"未定位违规行 L{line_no}：{joined[:120]}")
            self.assertIn(line_txt[:10], joined)
        self.assertIsInstance(diag, dict, "无 diag")
        for k in self._DIAG_KEYS:
            self.assertIn(k, diag, f"diag 缺 {k}")
        self.assertFalse(diag["degraded"], "原生 diag 须 degraded=False")
        self.assertTrue(diag["fix"], "fix 非空")

    # ---------- G7 扣非对比 ----------

    def test_g7_fail_truth_and_anchor(self):
        rpt = "# 报告\n净利润 7.67 亿，同比高增。\n"   # 有『净利润』缺『扣非』→ L2 锚
        ok, joined, diag = self._ret(gd.check_g7, rpt, self.FA)
        self._assert_fail_truth(ok, joined, diag,
                                 ["扣非净利润", "7.70亿", "2026-06-30", "0.73亿"], 2, "净利润 7.67 亿")
        self.assertIn("缺 扣非；已含 净利润", diag["found"])

    def test_g7_pass_and_degraded(self):
        self.assertIs(gd.check_g7("扣非净利润 7.70 亿 vs 净利润 7.67 亿", self.FA), True)  # PASS=字面 bool
        ok, joined, diag = self._ret(gd.check_g7, "基本面稳健", {})
        self._assert_fail_truth(ok, joined, diag, ["无扣非行（降级纯文本档）", "全文 0 处"])

    def test_g7_crash_injections(self):
        dirty = {"s1_financial": {"data": {"financial_abstract": {"data": [
            None, "x", {"指标": "扣非净利润", "20260630": None}]}}}}
        for snap in ({}, {"s1_financial": None}, dirty,
                     {"s1_financial": {"data": {"financial_abstract": None}}}):
            r = gd.check_g7("无词报告", snap)          # 逐臂 None/脏注入：不崩溃 + 类型合法
            self.assertIsInstance(r, (bool, dict))

    # ---------- G8 现金流三件套 ----------

    def test_g8_fail_truth_and_anchor(self):
        rpt = "# 报告\n自由现金流充裕。\n"              # 有 FCF 系词缺 CFO 系词 → L2 锚
        ok, joined, diag = self._ret(gd.check_g8, rpt, self.CF)
        self._assert_fail_truth(ok, joined, diag,
                                 ["经营活动产生的现金流量净额", "3.59亿", "2026-06-30"], 2, "自由现金流")
        self.assertIn("CFO/经营性现金流", diag["found"])

    def test_g8_rows0_arm_and_pass(self):
        # rows=0 细分（pending #2 成文规则）：failed=error 信封 → [数据层] 禁改稿动词；
        # ok=源端真空 → 双选（重跑 or 如实披露）
        snap_f = {"s1_financial": {"data": {"cash_flow": {"status": "failed", "data": []}}}}
        ok, joined, diag = self._ret(gd.check_g8, "x", snap_f)
        self.assertFalse(ok)
        self.assertIn("[数据层]", joined)
        self.assertIn("rows=0 且 status=failed", joined)
        self.assertNotIn("如实标注", diag["fix"])          # 禁改稿动词
        snap_v = {"s1_financial": {"data": {"cash_flow": {"status": "ok", "data": []}}}}
        ok, joined, diag = self._ret(gd.check_g8, "x", snap_v)
        self.assertFalse(ok)
        self.assertIn("源端真空", joined)
        self.assertIn("如实标注", diag["fix"])             # 双选修法
        self.assertIs(gd.check_g8("FCF 转正，经营性现金流为正", self.CF), True)

    def test_g8_crash_injections(self):
        dirty = {"s1_financial": {"data": {"cash_flow": {"data": [
            None, {"报告日": "2026-06-30", "经营活动产生的现金流量净额": False}]}}}}
        for snap in ({}, {"s1_financial": {"data": {}}}, dirty,
                     {"s1_financial": {"data": {"cash_flow": {"data": "not-a-list"}}}}):
            r = gd.check_g8("无词", snap)               # False 占位值经 _fmt_yi 归『—』不炸
            self.assertIsInstance(r, (bool, dict))

    # ---------- G9 利润归因 ----------

    def test_g9_fail_truth_delta_and_anchor(self):
        rpt = "# 报告\n业绩归因于费用管控。\n"           # 有『归因』缺『净利润』→ L2 锚
        ok, joined, diag = self._ret(gd.check_g9, rpt, self.INC)
        self._assert_fail_truth(ok, joined, diag,
                                 ["10.00亿", "1.00亿", "Δ+9.00亿"], 2, "业绩归因")
        self.assertIn("归因于〈", diag["fix"])

    def test_g9_pass_variants_and_data_full(self):
        self.assertIs(gd.check_g9("利润归因：净利提升", self.INC), True)
        self.assertIs(gd.check_g9("归因于营收，净利润同步", self.INC), True)
        sina = {"s1_financial": {"data": {"income_statement":
            {"data_full": [{"报告日": "2026-06-30", "净利润": 5e8},
                           {"报告日": "2026-03-31", "净利润": 4e8}]}}}}
        ok, joined, _ = self._ret(gd.check_g9, "无归因句", sina)   # data_full 单键路径（Sina）
        self.assertFalse(ok)
        self.assertIn("5.00亿", joined)

    def test_g9_crash_injections(self):
        for snap in ({}, {"s1_financial": {"data": {"income_statement": {"data": [{}, "x", 5]}}}},
                     {"s1_financial": {"data": {"income_statement": {"data": [None, None]}}}}):
            r = gd.check_g9("无词", snap)
            self.assertIsInstance(r, (bool, dict))


class TestWP1bG28(unittest.TestCase):
    """WP1b 轨1（2026-09-01）：G28 杜邦面板两臂 reason 真值化（reason-only）。

    语义现状澄清：闭合校验 2026-08-30 已废弃（ROE 口径随报告期切换，跨字段反算不成立），
    本批真值化的是**现状**两臂——①面板可用性（status/scene 在场性）②核心四字段在场性；
    「闭合差值/混装形态提示」属已废弃设计，混装口径风险由轨2 mixed_caliber 政策承接。
    两臂均为纯数据臂（不查报告，改稿不能过）→ [数据层] 家族，fix 禁改稿动词。
    归档 49 对实测：13 个 FAIL 全为臂①且 dupont=NoneType（scene 未生成），臂②现场 0 次。
    """

    _DIAG_KEYS = ("subcheck", "expected", "found", "fix", "src", "degraded")
    _CORE = {"净资产收益率": 12.5, "归属母公司股东的销售净利率": 8.3,
             "资产周转率(次)": 0.42, "权益乘数": 2.1}

    def _ret(self, rpt, snap):
        r = gd.check_g28(rpt, snap)
        return (bool(r.get("passed")), r.get("reasons", [""])[0], r.get("diag")) \
            if isinstance(r, dict) else (bool(r), "", None)

    def _assert_datalayer(self, ok, joined, diag, tokens):
        self.assertFalse(ok)
        self.assertIn("[数据层]", joined)
        for t in tokens:
            self.assertIn(t, joined)
        for k in self._DIAG_KEYS:
            self.assertIn(k, diag)
        self.assertFalse(diag["degraded"])
        for verb in ("照抄", "改写", "补写", "删除"):     # 禁改稿动词（[数据层] lint 规则 A）
            self.assertNotIn(verb, diag["fix"])

    def test_arm1_scene_missing(self):
        ok, joined, diag = self._ret("", {})              # 归档 13 例的真实形态
        self._assert_datalayer(ok, joined, diag,
                               ["dupont scene 整体未生成", "重跑 s1_financial 拉取"])

    def test_arm1_status_failed(self):
        snap = {"s1_financial": {"data": {"dupont": {"status": "failed", "data": {}}}}}
        ok, joined, diag = self._ret("", snap)
        self._assert_datalayer(ok, joined, diag, ["status=failed"])

    def test_arm2_partial_missing_carries_truth(self):
        core = dict(self._CORE, 权益乘数=None)
        snap = {"s1_financial": {"data": {"dupont": {"status": "ok", "data": core}}}}
        ok, joined, diag = self._ret("", snap)
        self._assert_datalayer(ok, joined, diag,
                               ["缺核心字段『权益乘数』", "净资产收益率=12.5", "资产周转率(次)=0.42"])
        self.assertIn("缺 权益乘数", diag["found"])

    def test_arm2_all_missing_and_pass(self):
        snap = {"s1_financial": {"data": {"dupont": {"status": "ok", "data": {}}}}}
        ok, joined, diag = self._ret("", snap)
        self._assert_datalayer(ok, joined, diag, ["四字段全缺"])
        self.assertIs(gd.check_g28("", {"s1_financial": {"data":
            {"dupont": {"status": "ok", "data": dict(self._CORE)}}}}), True)  # PASS=字面 bool

    def test_crash_injections(self):
        for snap in ({"s1_financial": None},
                     {"s1_financial": {"data": {"dupont": None}}},
                     {"s1_financial": {"data": {"dupont": {"status": "ok", "data": None}}}},
                     {"s1_financial": {"data": {"dupont": {"status": "ok", "data": "x"}}}}):
            r = gd.check_g28("", snap)                    # data None/非 dict → 兜底不炸
            self.assertIsInstance(r, (bool, dict))


class TestWP1bWordGates(unittest.TestCase):
    """WP1b 词表门批（2026-09-01）：G11/G12/G13/G17/G19/G22/G26/G31/G37 lossy 臂 reason 真值化。

    分类：G11/G12/G13/G17/G19/G22/G26=写作侧词表/消费门（改稿可过）；
    G31/G37=纯数据覆盖臂 → [数据层]（禁改稿动词）；G26 arm1 按 rows=0 细分规则
    （failed=error 信封→[数据层]；缺失/其它→双选）。
    """

    _DIAG_KEYS = ("subcheck", "expected", "found", "fix", "src", "degraded")
    _DL_VERBS = ("照抄", "改写", "补写", "删除")

    def _ret(self, fn, rpt, snap):
        r = fn(rpt, snap)
        return (bool(r.get("passed")), r.get("reasons", [""])[0], r.get("diag")) \
            if isinstance(r, dict) else (bool(r), "", None)

    def _fail_truth(self, fn, rpt, snap, tokens, datalayer=False, no_l_anchor=False):
        ok, joined, diag = self._ret(fn, rpt, snap)
        self.assertFalse(ok, "verdict 回退")
        for t in tokens:
            self.assertIn(t, joined, f"缺真值 {t!r}：{joined[:120]}")
        if not no_l_anchor:
            self.assertRegex(joined, r"L\d+:")
        self.assertIsInstance(diag, dict)
        for k in self._DIAG_KEYS:
            self.assertIn(k, diag)
        self.assertFalse(diag["degraded"])
        if datalayer:
            self.assertIn("[数据层]", joined)
            for v in self._DL_VERBS:
                self.assertNotIn(v, diag["fix"])
        else:
            self.assertNotIn("[数据层]", joined)
        return diag

    def test_g11_cutoff_declaration(self):
        d = self._fail_truth(gd.check_g11, "# 报告\n正文无声明无表格。", {"timestamp": "2026-08-31T09:00:00"},
                             ["数据截止 2026-08-31", "照抄声明"], no_l_anchor=True)
        self.assertIn("0/0 张", d["found"])
        self.assertIs(gd.check_g11("# 数据截止：2026-08-31", {}), True)

    def test_g12_limitations_count(self):
        d = self._fail_truth(gd.check_g12, "存在局限一处，不足一处。", {},
                             ["命中 2 处（需 ≥3）", "≥3 条具体局限"])
        self.assertIs(gd.check_g12("局限1；局限2；不足3；限制4", {}), True)

    def test_g13_holding_decision(self):
        d = self._fail_truth(gd.check_g13, "建议持有", {"holding_status": {"cost": 12.3}},
                             ["holding_status={'cost': 12.3}", "持仓语境"], no_l_anchor=True)
        self.assertIs(gd.check_g13("无词", {}), True)            # auto_pass
        # F4b② 预申翻转形态：裸决策句（零持仓语境词）旧全文单词条件过、现 FAIL——
        # 「决策：持有」不引用用户持仓（成本/仓位）= 忽略持仓语境的通用建议
        self.assertNotEqual(gd.check_g13("决策：持有", {"holding_status": "x"}), True)

    def test_g17_tariff_disclosure(self):
        tv = {"computed_metrics": {"tariff_vulnerability": {"level": "fatal"}}}
        d = self._fail_truth(gd.check_g17, "关税风险存在", tv,
                             ["level=fatal", "缺 §7.1.1 估值折让", "L1"])
        self.assertIs(gd.check_g17("关税存在，折让 -5%～-10%", tv), True)
        self.assertIs(gd.check_g17("无词", {"computed_metrics": {}}), True)  # none 放行

    def test_g19_forecast_range_or_disclaimer(self):
        d = self._fail_truth(gd.check_g19, "# 报告\n预期营收向好，方向明确。", {},
                             ["无数值区间", "无法量化/难以预测"])
        self.assertIs(gd.check_g19("预期营收增速 15~20 亿", {}), True)   # N~M 直连（%会挡）
        self.assertIs(gd.check_g19("预期影响难以预测", {}), True)

    def test_g22_segment_table_src(self):
        seg = {"s1_financial": {"data": {"segment_composition":
            {"dimension_status": {"product": {"status": "disclosed_ok"}}}}}}
        d = self._fail_truth(gd.check_g22, "分业务收入见表", seg,
                             ["disclosed_ok 维度=['product']", "溯源"])
        self.assertIn("segment_composition.product", d["fix"])
        self.assertIs(gd.check_g22("分业务表 [src: snapshot.s1_financial.data.segment_composition.product]", seg), True)
        self.assertIs(gd.check_g22("无表", {}), True)           # 无 disclosed 维放行

    def test_g26_fund_flow_consumption_and_envelope(self):
        ff = {"s3_fund_flow": {"data": {"fund_flow": {"status": "ok", "items": [
            {"name": "特大单", "in": 0.0, "out": 0.24}, {"name": "大单", "in": 2.51, "out": 0.0},
            {"name": "中单", "in": 1.0, "out": 1.0}, {"name": "小单", "in": 3.0, "out": 2.0}]}}}}
        d = self._fail_truth(gd.check_g26, "正文无资金词", ff,
                             ["特大单 in=0.0/out=0.24", "大单 in=2.51/out=0.0"], no_l_anchor=True)
        self.assertIs(gd.check_g26("主力资金净流入", ff), True)
        # arm1 信封细分两极：failed→[数据层] 禁改稿动词；缺失→双选
        dlf = self._fail_truth(gd.check_g26, "x", {"s3_fund_flow": {"data":
            {"fund_flow": {"status": "failed"}}}}, ["status=failed"], datalayer=True, no_l_anchor=True)
        dvac = self._fail_truth(gd.check_g26, "x", {}, ["scene 整体未生成", "如实标注"],
                                no_l_anchor=True)
        # 脏注入：items 含非 dict 行不炸（crash-fix 面）
        r = gd.check_g26("无词", {"s3_fund_flow": {"data": {"fund_flow":
            {"status": "ok", "items": [None, 5, {"name": "特大单"}] * 4}}}})
        self.assertIsInstance(r, (bool, dict))

    def test_g31_quote_coverage_datalayer(self):
        q = {"valuation_snapshot": {"data": {"quote": {"peTtm": 25.0, "pbRatio": None, "totalMarketCap": None}}}}
        d = self._fail_truth(gd.check_g31, "", q, ["pbRatio、totalMarketCap 为 None", "peTtm=25.0"],
                             datalayer=True, no_l_anchor=True)
        self.assertIs(gd.check_g31("", {"valuation_snapshot": {"data":
            {"quote": {"peTtm": 25.0, "pbRatio": 3.0, "totalMarketCap": 1e10}}}}), True)
        self._fail_truth(gd.check_g31, "", {}, ["非 dict"], datalayer=True, no_l_anchor=True)

    def test_g37_macro_coverage_datalayer(self):
        mac = {"s6_macro": {"data": {"pmi": {"latest_period": {"value": 50.3}}}}}
        d = self._fail_truth(gd.check_g37, "", mac, ["ppi、m2 latest_period 缺值", "pmi=50.3"],
                             datalayer=True, no_l_anchor=True)
        self.assertIs(gd.check_g37("", {"s6_macro": {"data": {
            "pmi": {"latest_period": {"value": 50.3}}, "ppi": {"latest_period": {"value": 104.1}}}}}), True)
        # 脏注入：latest_period 非 dict / scene 缺失不炸
        for snap in ({"s6_macro": {"data": {"pmi": "not-dict", "ppi": {"latest_period": "x"}, "m2": None}}},
                     {}, {"s6_macro": None}):
            r = gd.check_g37("", snap)
            self.assertIsInstance(r, (bool, dict))

    def test_dirty_injections_word_gates(self):
        """逐门脏注入（scene 缺失/None/非 dict）：不炸 + 类型合法。"""
        cases = (
            (gd.check_g11, {"timestamp": None}), (gd.check_g12, None),
            (gd.check_g13, {"holding_status": 5}), (gd.check_g17, {"computed_metrics": None}),
            (gd.check_g19, None), (gd.check_g22, {"s1_financial": None}),
            (gd.check_g31, {"valuation_snapshot": {"data": {"quote": "x"}}}),
        )
        for fn, snap in cases:
            r = fn("无词正文", snap)
            self.assertIsInstance(r, (bool, dict))


class TestWP1bLegacyGates(unittest.TestCase):
    """WP1b legacy+真值门批（2026-09-01）：G1/G14 + G6/G15/G16/G21/G34/G35/G36。

    分类：G1(never_traded 反编造+降级档)/G6(短历史+rows=0 细分)/G14(计数展示)/G15(诚实披露)
    /G16(grounded+回退偏差)/G21(report-only websearch 下限) = 写作侧可修臂；
    G6 rows=0·failed、G15 ok<2、G34/35/36 marker 异常 = 纯数据臂 → [数据层]（禁改稿动词）。
    """

    _DIAG_KEYS = ("subcheck", "expected", "found", "fix", "src", "degraded")
    _DL_VERBS = ("照抄", "改写", "补写", "删除")

    def _ret(self, fn, rpt, snap):
        r = fn(rpt, snap)
        return (bool(r.get("passed")), r.get("reasons", [""])[0], r.get("diag")) \
            if isinstance(r, dict) else (bool(r), "", None)

    def _fail_truth(self, fn, rpt, snap, tokens, datalayer=False, no_l_anchor=True):
        ok, joined, diag = self._ret(fn, rpt, snap)
        self.assertFalse(ok, "verdict 回退")
        for t in tokens:
            self.assertIn(t, joined, f"缺真值 {t!r}：{joined[:120]}")
        self.assertIsInstance(diag, dict)
        for k in self._DIAG_KEYS:
            self.assertIn(k, diag)
        self.assertFalse(diag["degraded"])
        if datalayer:
            self.assertIn("[数据层]", joined)
            for v in self._DL_VERBS:
                self.assertNotIn(v, diag["fix"])
        else:
            self.assertNotIn("[数据层]", joined)
        return diag

    def test_g1_never_traded_fabrication(self):
        snap = {"s4_technical": {"status": "never_traded"}}
        d = self._fail_truth(gd.check_g1, "## 技术面\nMACD：-0.52，KDJ 80。", snap,
                             ["never_traded", "疑似编造"], no_l_anchor=True)
        self.assertIn("MACD", d["found"])

    def test_g1_never_traded_clean_pass(self):
        snap = {"s4_technical": {"status": "never_traded"}}
        ok, _, _ = self._ret(gd.check_g1, "## 技术面\n技术指标数据不可得，如实标注。", snap)
        self.assertTrue(ok)

    def test_g1_legacy_no_matrix(self):
        d = self._fail_truth(gd.check_g1, "## 正文\n纯粹正文。", {},
                             ["降级档", "缺『信号/矩阵』词"], no_l_anchor=True)
        self.assertIn("signal_matrix_legacy", d["subcheck"])

    def test_g6_rows0_failed_datalayer(self):
        snap = {"s1_financial": {"data": {"income_statement":
               {"status": "failed", "data": []}}}}
        self._fail_truth(gd.check_g6, "正文。", snap,
                         ["rows=0", "status=failed", "重跑"], datalayer=True)

    def test_g6_rows0_vacuum_dual(self):
        snap = {"s1_financial": {"data": {"income_statement":
               {"status": "empty", "data": []}}}}
        self._fail_truth(gd.check_g6, "正文。", snap,
                         ["源端真空", "如实标注"], no_l_anchor=True)

    def test_g6_short_history_truth(self):
        rows = [{"报告期": "2025-12-31"}, {"报告期": "2025-09-30"}, {"报告期": "2025-06-30"}]
        snap = {"s1_financial": {"data": {"income_statement": {"status": "ok", "data": rows}}}}
        d = self._fail_truth(gd.check_g6, "正文 2024Q1 与 2024Q2 两期。", snap,
                             ["仅 3 期", "2 个季度表述"], no_l_anchor=True)
        self.assertIn("2025-12", d["found"])

    def test_g14_stage_no_count(self):
        snap = {"s4_technical": {"status": "ok",
               "data": {"td": {"summary": {"stage": "买Setup 7/9"}}}}}
        d = self._fail_truth(gd.check_g14, "## 三\nTD 序列健康。", snap,
                             ["stage=买Setup 7/9", "0 处）"], no_l_anchor=True)
        self.assertIn("买Setup 7/9", d["fix"])

    def test_g14_count_pass(self):
        snap = {"s4_technical": {"status": "ok",
               "data": {"td": {"summary": {"stage": "买Setup 7/9"}}}}}
        ok, _, _ = self._ret(gd.check_g14, "## 三\nTD Setup 7/9 进行中，持有。", snap)
        self.assertTrue(ok)

    def test_g15_placeholder_undisclosed(self):
        snap = {"s11_peer": {"data": {"status": "missing", "items": []}}}
        d = self._fail_truth(gd.check_g15, "## 正文\n纯粹正文。", snap,
                             ["从未跑", "未披露"], no_l_anchor=True)
        self.assertIn("0 处", d["found"])
        self.assertIn("无适用同业", d["fix"])

    def test_g15_ok_lt2_datalayer(self):
        core = {k: 1.0 for k in ("rev_yoy", "np_yoy", "pe", "pb", "roe", "gross_margin")}
        snap = {"s11_peer": {"data": {"status": "ok", "items": [
            {"name": "甲", "metrics": core},
            {"name": "乙", "metrics": {k: 1.0 for k in ("rev_yoy",)}}]}}}
        self._fail_truth(gd.check_g15, "正文。", snap,
                         ["1/2 家", "重跑"], datalayer=True)

    def test_g16_grounded_missing(self):
        snap = {"s1_financial": {"data": {"balance_sheet": {"data": [{"合同负债": 3.5e9}]}}}}
        d = self._fail_truth(gd.check_g16,
                             "在手订单核对：合同负债 30.5 亿，交叉核对通过。", snap,
                             ["35.00 亿", "照抄"], no_l_anchor=True)
        self.assertIn("35.00 亿", d["fix"])

    def test_g16_fallback_deviation_over(self):
        d = self._fail_truth(gd.check_g16, "合同负债与订单核对，偏差 40%，已交代。", {},
                             ["偏差 40%", "偏差过大"], no_l_anchor=True)
        self.assertIn("40.0%", d["found"])

    def test_g21_empty_snapshot_floor(self):
        d = self._fail_truth(gd.check_g21, "数据 [src: websearch 官网公告]。", {},
                             ["report-only 降级档", "仅 1 个"], no_l_anchor=True)
        self.assertIn("≥2", d["expected"])

    def test_g34_datalayer(self):
        snap = {"_quality_markers": {"segment_product": {"status": "fetch_failed"}}}
        self._fail_truth(gd.check_g34, "正文。", snap,
                         ["G34", "status=fetch_failed", "重跑"], datalayer=True)

    def test_g34_valid_pass(self):
        snap = {"_quality_markers": {"segment_product": {"status": "disclosed_ok"}}}
        ok, _, _ = self._ret(gd.check_g34, "正文。", snap)
        self.assertTrue(ok)


class TestWP1bLegacyInjection(unittest.TestCase):
    """WP1b legacy 批崩溃面注入（裁决⑥惯例）：truthy 非 dict / 缺键 / 空容器逐臂封闭。

    覆盖 crash-fix ×3（G14 summary / G15 items 元素 / G34-36 marker，出定理域：
    旧引擎这些输入直接崩，守卫后按缺臂 FAIL——注入测试背书非定理背书）。
    """

    def _no_crash(self, fn, rpt, snap):
        try:
            r = fn(rpt, snap)
            return bool(r.get("passed")) if isinstance(r, dict) else bool(r)
        except Exception as e:
            self.fail(f"注入输入崩溃: {type(e).__name__}: {e}")

    def test_g14_summary_non_dict(self):
        snap = {"s4_technical": {"status": "ok", "data": {"td": {"summary": "x"}}}}
        v = self._no_crash(gd.check_g14, "TD 序列。", snap)
        self.assertTrue(v, "summary 非 dict → stage 不可读 → 无信号档（提及 TD 即过；旧引擎此处直接崩）")

    def test_g15_items_non_dict(self):
        snap = {"s11_peer": {"data": {"status": "ok", "items": ["x", {"name": "乙"}]}}}
        self._no_crash(gd.check_g15, "同业对比。", snap)   # <2 valid → FAIL，不崩

    def test_g34_marker_non_dict(self):
        snap = {"_quality_markers": {"segment_product": "x"}}
        self.assertFalse(self._no_crash(gd.check_g34, "正文。", snap), "marker 非 dict → FAIL [数据层]")

    def test_g6_income_data_non_list(self):
        snap = {"s1_financial": {"data": {"income_statement": {"status": "ok", "data": "x"}}}}
        v = self._no_crash(gd.check_g6, "2024Q1 2024Q2 2024Q3 2024Q4 2023Q1 2023Q2。", snap)
        self.assertTrue(v, "data 非 list → 纯文本降级档（6 季度词在场 → PASS）")

    def test_g16_balance_non_list(self):
        snap = {"s1_financial": {"data": {"balance_sheet": {"data": "x"}}}}
        v = self._no_crash(gd.check_g16, "合同负债 30 亿，核对偏差 5%。", snap)
        self.assertTrue(v, "balance data 非法 → _extract None → 文本回退档 PASS")

    def test_g1_s4_non_dict(self):
        v = self._no_crash(gd.check_g1, "正文。", {"s4_technical": "x"})
        self.assertFalse(v, "s4 非 dict → legacy 降级档 FAIL")

class TestF4aScopeNarrow(unittest.TestCase):
    """F4a verdict-affecting 批（2026-09-01，裁决 B）：G49 片段级 / G16 行内 / G67 语境锚。

    pre-declare 对账（单元级逐条；归档级另由 diff_engine 重放）：
      G49 翻转①「卖方研报」跨行共现 FAIL→PASS（R12 watch 形态，fixture 已同步刷新）；
      G16 翻转②真值仅在非 CL 行撞数 旧假 grounded PASS→FAIL；
      G67 翻转③量价数值仅在无量价语境行 旧假 PASS→FAIL。
    """

    _DIAG_KEYS = ("subcheck", "expected", "found", "fix", "src", "degraded")

    def _v(self, fn, rpt, snap):
        r = fn(rpt, snap)
        return bool(r.get("passed")) if isinstance(r, dict) else bool(r)

    def _fail_reason(self, fn, rpt, snap):
        r = fn(rpt, snap)
        self.assertIsInstance(r, dict)
        self.assertFalse(r["passed"])
        return "".join(r.get("reasons") or [])

    # ---- G49 片段级（套 G48 R5 范式）----
    def test_g49_crossline_no_longer_fires(self):
        snap = {"s5_events": {"data": {"risk_signals": {"processed":
               {"buy_sell_pressure": {"status": "unclear"}}}}}}
        # 翻转①：跨行「卖方研报」覆盖度语境 + 「买卖力量」→ 不再误伤
        self.assertTrue(self._v(gd.check_g49,
            "买卖力量：无结论。\n观点层：卖方研报 0 覆盖、机构评级仅 1 家。", snap))

    def test_g49_same_fragment_still_fires(self):
        snap = {"s5_events": {"data": {"risk_signals": {"processed":
               {"buy_sell_pressure": {"status": "unclear"}}}}}}
        r = self._fail_reason(gd.check_g49,
            "买卖力量：买方占优，材料级活动明确。", snap)
        self.assertIn("同片段", r)

    def test_g49_verdict_presence_unchanged(self):
        snap = {"s5_events": {"data": {"risk_signals": {"processed":
               {"buy_sell_pressure": {"status": "ok", "verdict": "buy_dominant"}}}}}}
        self.assertTrue(self._v(gd.check_g49, "m9.2：买方阵营占优。", snap))
        r = self._fail_reason(gd.check_g49, "正文无阵营词。", snap)
        self.assertIn("buy_dominant", r)

    # ---- G16 行内 grounded（套 G63 语境范式）----
    _G16_SNAP = {"s1_financial": {"data": {"balance_sheet": {"data": [{"合同负债": 3.5e9}]}}}}

    def test_g16_inline_aligned_pass(self):
        self.assertTrue(self._v(gd.check_g16,
            "订单核对：合同负债 35.00 亿，交叉核对通过。", self._G16_SNAP))

    def test_g16_foreign_line_hit_now_fails(self):
        # 翻转②：真值数仅在非 CL 行（股价行撞 35.0）——旧全文扫假 grounded，现行内须 FAIL
        r = self._fail_reason(gd.check_g16,
            "当前股价 35.0 元。\n合同负债与在手订单核对，偏差口径已交代。", self._G16_SNAP)
        self.assertIn("可照抄", r)

    def test_g16_section_judgeline_pass(self):
        # 归档裁决补锚（002138 顺络电子，2026-09-01）：「### 合同负债」标题节内的
        # 判读行不必逐行重复字面词——节内 0.29 亿 = 合法语境消费（G63 section 范式，
        # 初版行级作用域曾误伤此形态，归档重放抓出后收正）
        snap = {"s1_financial": {"data": {"balance_sheet": {"data": [{"合同负债": 2.9e7}]}}}}
        self.assertTrue(self._v(gd.check_g16,
            "### 4.1 合同负债 8 期趋势\n| 报告期 | 合同负债(万元) |\n"
            "| 2026H1 | 2894 |\n判读：绝对量小（0.29 亿），方向上最新期创新高，核对通过。",
            snap))

    def test_g16_src_on_cl_line_pass(self):
        self.assertTrue(self._v(gd.check_g16,
            "合同负债 30.5 亿 [src: snapshot.s1_financial.data.balance_sheet]，核对完成。",
            self._G16_SNAP))

    # ---- G67 量价语境锚 ----
    _G67_SNAP = {"mode": "B", "s4_technical": {"data": {"short_term_enrich":
        {"volume_check": {"state": "ok", "vol_ratio_5d": 2.3,
                          "amount_mult_20d": 1.8, "week_volume_mult": 1.2,
                          "amplified": True, "pullback_shrink": False}}}}}

    def test_g67_context_pass(self):
        self.assertTrue(self._v(gd.check_g67,
            "量价：5日量比 2.3，20日成交额倍数 1.8。", self._G67_SNAP))

    def test_g67_foreign_context_now_fails(self):
        # 翻转③：2.3 仅出现在估值语境行（无 量比/成交 词）——旧全文对拍假 PASS
        r = self._fail_reason(gd.check_g67,
            "估值：市盈率 2.3，PEG 1.1。", self._G67_SNAP)
        self.assertIn("量价语境", r)
        self.assertIn("无量价语境行", r)

    def test_g67_flag_mismatch_unchanged(self):
        r = self._fail_reason(gd.check_g67,
            "量价：5日量比 2.3；amplified=false", self._G67_SNAP)
        self.assertIn("amplified", r)


class TestF4bG69Narrow(unittest.TestCase):
    """F4b① G69 收窄（2026-09-01 裁决 B，F4a 待遇）：消费=维度词+src_token 同行 且
    行内无披露词（_contextual_presence forbid 首用；词表从 m37 披露措辞合同推导）。

    pre-declare 对账（裁决 B 条件 3 三件套）：
      ① 探针判决保持 True（3 真消费 + 1 披露行，need=3）——仅注记更新；
      ② 真实翻转形态=2 真+1 假票（披露行挂 [src:] 被计入）旧 PASS→FAIL；
      ③ 跨行拼「消费」票（src 与维度词分散两行）旧 PASS→FAIL。
    """

    _SNAP = {"mode": "B",
             "s3_fund_flow": {"data": {"fund_flow": {"status": "ok", "net_flow": -0.5}}},
             "s_margin": {"data": {"status": "ok", "finance_value_yi": 3.2}},
             "valuation_snapshot": {"data": {"valuation_percentile":
                 {"status": "ok", "pe_ttm": {"pct_5y": 50}}}},
             "s4_technical": {"data": {"chip": {"status": "ok", "chipProfitRate": 0.6}}}}

    def _v(self, rpt):
        r = gd.check_g69(rpt, self._SNAP)
        return bool(r.get("passed")) if isinstance(r, dict) else bool(r)

    def test_honest_full_consumption_pass(self):
        self.assertTrue(self._v(
            "| 当日资金流 | 主力净流出 [src: snapshot.s3_fund_flow.data.fund_flow] |\n"
            "| 融资杠杆 | 余额 3.2 亿 [src: snapshot.s_margin.data] |\n"
            "| 估值分位 | pe pct_5y 50 [src: snapshot.valuation_snapshot.data.valuation_percentile] |\n"
            "| 获利盘 | 获利 60% [src: snapshot.s4_technical.data.chip] |"))

    def test_crossline_join_now_fails(self):
        # pre-declare ③：src 与维度词分散两行，旧两独立全文条件可拼出「消费」
        self.assertFalse(self._v(
            "杠杆资金温和 [src: snapshot.s_margin.data]。\n"
            "估值不贵 [src: snapshot.valuation_snapshot.data.valuation_percentile]。\n"
            "另节提到主力动向与获利情况、资金流（叙述，无 src）。"))

    def test_disclosure_line_not_counted_2true_1fake(self):
        # pre-declare ②（真实翻转形态）：披露行挂 [src:] 旧被计入 → 旧 PASS 现 FAIL
        r = gd.check_g69(
            "| 当日资金流 | 数据降级如实披露 [src: snapshot.s3_fund_flow.data.fund_flow]（本维未消费）|\n"
            "| 融资杠杆 | 余额 3.2 亿 [src: snapshot.s_margin.data] |\n"
            "| 估值分位 | pe pct_5y 50 [src: snapshot.valuation_snapshot.data.valuation_percentile] |",
            self._SNAP)
        self.assertIsInstance(r, dict)
        self.assertFalse(r["passed"])
        self.assertIn("不计入", "".join(r["reasons"]))
        self.assertIn("披露行不计入", r["diag"]["found"])
        self.assertIn("2/3", r["diag"]["found"])
        for k in ("subcheck", "expected", "found", "fix", "src", "degraded"):
            self.assertIn(k, r["diag"])

    def test_three_true_one_disclosure_pass(self):
        # pre-declare ①（REAL_WATCH G69 探针语义）：3 真消费 + 1 披露行 → True 不变
        self.assertTrue(self._v(
            "| 当日资金流 | 数据降级如实披露 [src: snapshot.s3_fund_flow.data.fund_flow]（本维未消费）|\n"
            "| 融资杠杆 | 余额 3.2 亿 [src: snapshot.s_margin.data] |\n"
            "| 估值分位 | pe pct_5y 50 [src: snapshot.valuation_snapshot.data.valuation_percentile] |\n"
            "| 获利盘 | 获利 60% [src: snapshot.s4_technical.data.chip] |"))

    def test_degraded_dim_shrinks_denominator(self):
        snap = dict(self._SNAP)
        snap["s4_technical"] = {"data": {"chip": {"status": "failed"}}}
        snap["valuation_snapshot"] = {"data": {}}  # 估值维缺席 → 分母=2
        r = gd.check_g69(
            "| 当日资金流 | 主力净流出 [src: snapshot.s3_fund_flow.data.fund_flow] |\n"
            "| 融资杠杆 | 余额 3.2 亿 [src: snapshot.s_margin.data] |", snap)
        self.assertTrue(bool(r.get("passed")) if isinstance(r, dict) else bool(r))

    def test_contextual_presence_scope_contract(self):
        # 共享 API 三 scope 语义钉死（presence 批消费同一实现，裁决 B：一次设计到位）
        rpt = "## 节A\n持仓 30%。\n- 决策：维持不动。\n## 节B\n行业政策讨论。"
        self.assertIsNotNone(gd._contextual_presence(  # section：同节跨行合法（002138 型）
            rpt, ("决策",), anchors=("持仓", "仓位"), scope="section"))
        self.assertIsNone(gd._contextual_presence(  # line：跨行不命中
            rpt, ("决策",), anchors=("持仓", "仓位"), scope="line"))
        self.assertIsNone(gd._contextual_presence(  # forbid：披露单元被否决
            "主力净流出 [src: x]（本维未消费）", ("主力",), anchors=("src",),
            forbid=("未消费",)))
        self.assertIsNotNone(gd._contextual_presence(  # 干净行正常命中
            "主力净流出 [src: x]", ("主力",), anchors=("src",),
            forbid=("未消费",), scope="line"))

class TestF4bPresenceBatch(unittest.TestCase):
    """F4b② presence 批（2026-09-01 裁决 C）：逐门逐门 commit，本类按门增量填充。

    预申表（窗口语义逐门显式，禁默认）：
      G25 事件消费：scope=section（初申 line 被重放证伪：002130/300223 等 5 对合法消费
          = 节标题带事件词 + src 挂节内明细行，行级全假 FAIL → 窗口修正，改锚表不改报告；
          翻转 6 对中仅 000657 存留 = B 模式报告×cache 全量快照配对伪影）
      G13 持仓决策：scope=section（「操作决策如下：\\n- 维持现有仓位」跨行同节合法，裁决例句）
      G29 危险 surface：scope=line，anchor=资产安全对象词（m2 §2.10 flags 文本天然同行）；
          消费臂维持现状（字段词即对象词，无干净锚——占行显式，防默认收窄）
      G39 #1 类型句：scope=line，anchor=分类陈述词（属/类型/分类，m1 开篇句合同）；
          #2 框架词/#3 宏观词维持现状（触发词自锚：估值框架词/宏观指标名本身即语境，
          否定句「PB 不作主要锚」是合法内容，加锚反假 FAIL）——占行显式
    重放裁决规则（制度化）：翻转中若原出现本属合法内容（002138 型）=锚表不全→改锚表；
    只有真污染才裁「预期收紧」。
    """

    def _v(self, fn, rpt, snap):
        r = fn(rpt, snap)
        return bool(r.get("passed")) if isinstance(r, dict) else bool(r)

    # ---- G25（门 1/4）----
    _G25_SNAP = {"s5_events": {"data": {"news": {
        "high_value": [{"title": "并购"}], "_python_layer": "completed"}}}}

    def test_g25_anchored_consumption_pass(self):
        self.assertTrue(self._v(gd.check_g25,
            "事件扫描：近 3 月新闻分桶（高价值 1 条/中价值 60 条）"
            "[src: snapshot.s5_events.data.news.high_value]", self._G25_SNAP))

    def test_g25_word_only_with_foreign_src_now_fails(self):
        # 预申翻转形态：事件词散落 + src 挂别节（旧两独立全文条件可拼出消费）
        r = gd.check_g25(
            "近期无重大事件扰动。\n估值锚 [src: snapshot.valuation_snapshot.data.quote]",
            self._G25_SNAP)
        self.assertIsInstance(r, dict)
        self.assertFalse(r["passed"])
        self.assertIn("同节", "".join(r["reasons"]))
        for k in ("subcheck", "expected", "found", "fix", "src", "degraded"):
            self.assertIn(k, r["diag"])

    def test_g25_section_scope_crossline_pass(self):
        # 重放证伪行级预申的实锤形态（002130/300223 型）：节标题带事件词，
        # src 挂节内明细行——同节跨行合法消费，行级锚假 FAIL
        self.assertTrue(self._v(gd.check_g25,
            "## 六、市场情绪与重大事件\n\n"
            "事件时间线（28 条事件）：\n\n"
            "| 日期 | 事件 | 意义 |\n|---|---|---|\n"
            "| 2026-08-29 | 披露中报 [src: snapshot.s5_events.data.risk_signals.processed.timeline] | 兑现日 |",
            self._G25_SNAP))

    def test_g25_cross_section_join_still_fails(self):
        # 跨节拼不算消费：事件词在技术节叙事里，s5_events src 在全景表另一节
        self.assertFalse(self._v(gd.check_g25,
            "## 五、技术面\n离散事件（缺口高频反复）：8 月以来跳空缺口交替。\n\n"
            "## 九、全景表\nrisk [src: snapshot.s5_events.data.risk_signals.processed.timeline]",
            self._G25_SNAP))

    # ---- G13（门 2/4；休眠门：holding_status 管道无 producer，归档 56 对 0 在场，
    #      锚表按 m11 WP1b 骨架合同推导，单测钉双向）----

    def test_g13_ruling_example_crossline_pass(self):
        # 裁决 C 例句：「操作决策如下：\n- 维持现有仓位」跨行同节合法（行级锚假 FAIL）
        self.assertTrue(self._v(gd.check_g13,
            "## 八、操作建议\n操作决策如下：\n- 维持现有仓位，不加仓不减仓。",
            {"holding_status": "成本12.5/仓位50%"}))

    def test_g13_governance_word_cross_section_fails(self):
        # 预申翻转形态：治理叙事词（董事会决策）+ 持仓词散在不同节——跨节拼不算
        r = gd.check_g13(
            "## 二、公司治理\n董事会决策程序规范，重大事项集体审议。\n\n"
            "## 八、操作建议\n当前仓位较重者可考虑持有。",
            {"holding_status": "成本12.5"})
        self.assertIsInstance(r, dict)
        self.assertFalse(r["passed"])
        self.assertIn("同节", "".join(r["reasons"]))
        for k in ("subcheck", "expected", "found", "fix", "src", "degraded"):
            self.assertIn(k, r["diag"])

    def test_g13_same_section_governance_passes_known_loose(self):
        # 已知宽向（预申显式）：bare「成本」锚覆盖营业成本语境——治理节「董事会决策」
        # 与「营业成本」同节会过（假 PASS 方向，weight-2 容忍；收紧须新证据走 F4 预申报）
        self.assertTrue(self._v(gd.check_g13,
            "## 二、公司治理\n董事会决策程序规范；营业成本上升压缩毛利。",
            {"holding_status": "成本12.5"}))

    # ---- G29（门 3/4；预飞 16 个 🚨 归档对 14 对真同行，2 对 000657=配对伪影）----
    _G29_SNAP = {"computed_metrics": {"asset_safety": {
        "status": "ok", "level": "🚨", "cash_to_debt": 0.30}}}

    def test_g29_flags_sentence_pass(self):
        # m2 §2.10 flags 句式合同：对象词与危险词同行
        self.assertTrue(self._v(gd.check_g29,
            "资产安全体检：cash_to_debt=0.30，资金链紧张；商誉占净资产 25%，减值风险大。",
            self._G29_SNAP))

    def test_g29_foreign_danger_word_now_fails(self):
        # 预申翻转形态（近真空收紧）：危险词在别节（估值/关税风险）、对象词在财务节
        # ——旧全文 re.search 任一危险词即过
        r = gd.check_g29(
            "## 七、风险提示\n估值风险偏高，关税是主要风险源。\n\n"
            "## 二、财务体检\n货币资金 3.2 亿，有息负债 10.7 亿，商誉 0.8 亿。",
            self._G29_SNAP)
        self.assertIsInstance(r, dict)
        self.assertFalse(r["passed"])
        self.assertIn("同行", "".join(r["reasons"]))
        for k in ("subcheck", "expected", "found", "fix", "src", "degraded"):
            self.assertIn(k, r["diag"])

    def test_g29_disclosure_row_not_counted(self):
        # 降级披露行挂对象词+危险词不算 surface（forbid 守卫，G69 同哲学）
        self.assertFalse(self._v(gd.check_g29,
            "资产安全 status=degraded（模式 B 未拉取三表，cash_to_debt/商誉不可计算），存在风险。",
            self._G29_SNAP))

    def test_g29_consume_arm_unchanged(self):
        # 消费臂维持现状（预申显式）：非 🚨 档字段词全文扫描不收窄（字段词即对象词自锚无意义）
        snap = {"computed_metrics": {"asset_safety": {"status": "ok", "level": "⚠️"}}}
        self.assertTrue(self._v(gd.check_g29, "商誉很低，资产干净。", snap))
        r = gd.check_g29("盈利能力稳定。", snap)
        self.assertIsInstance(r, dict)
        self.assertFalse(r["passed"])
        self.assertIn("字段词", "".join(r["reasons"]))

    # ---- G39（门 4/4；预飞 54 活跃对：#1 词根泄漏 16 对旧判全靠散落词根，
    #      15/16 全词压根未出现；#2/#3 维持现状显式占行）----
    _G39_SNAP = {"classification": {
        "primary_type": "成长股", "valuation_framework": "PS",
        "forbidden_metric": "PB", "macro_sensitivity": "medium"}}
    _G39_CYC_SNAP = {"classification": {
        "primary_type": "周期股", "valuation_framework": "PB",
        "forbidden_metric": "PE", "macro_sensitivity": "high"}}

    def test_g39_contract_sentence_pass(self):
        self.assertTrue(self._v(gd.check_g39,
            "标的属周期股，PB 估值框架（股息率辅助）[src: snapshot.classification]；"
            "PPI 同比回落利好成本端。", self._G39_CYC_SNAP))

    def test_g39_corpus_variant_sentence_pass(self):
        # 语料实锤变体（688502）：「本文按成长股框架分析（classification 置信度…）」
        self.assertTrue(self._v(gd.check_g39,
            "本文按成长股框架分析（classification 置信度 0.95）：PS 估值为主。", self._G39_SNAP))

    def test_g39_morpheme_leak_now_fails(self):
        # 预申收紧形态：词根散落（技术面多周期/gap 行成长性）+ 框架词在场——
        # 旧 `core in report` 全文扫描即过 #1
        r = gd.check_g39(
            "## 三、技术面\n多周期共振与方向预测；周期状态表显示 RSI 中性。\n\n"
            "## 估值\nPS 估值为主（PB 不作主要锚）。", self._G39_SNAP)
        self.assertIsInstance(r, dict)
        self.assertFalse(r["passed"])
        self.assertIn("类型结论", "".join(r["reasons"]))
        for k in ("subcheck", "expected", "found", "fix", "src", "degraded"):
            self.assertIn(k, r["diag"])

    def test_g39_mixed_type_sentence_pass(self):
        snap = {"classification": {
            "primary_type": "周期股", "is_mixed": True, "secondary_type": "成长股",
            "valuation_framework": "PS", "forbidden_metric": "PE",
            "macro_sensitivity": "high"}}
        self.assertTrue(self._v(gd.check_g39,
            "标的属周期股+成长股混合，PS 估值；PPI 回落。", snap))

    def test_g39_fw_macro_arms_unchanged(self):
        # #2/#3 维持现状占行（裁决 C ①）：否定句「PB 不作主要锚」是合法内容，
        # 框架词/宏观词自锚不加语境锚——本测试钉 #2 缺框架词 FAIL / #3 缺宏观 FAIL 原语义
        snap2 = {"classification": {
            "primary_type": "消费股", "macro_sensitivity": "medium"}}  # forbidden=None → 跳过#2
        self.assertTrue(self._v(gd.check_g39, "标的属消费股，估值合理。", snap2))
        snap3 = {"classification": {
            "primary_type": "周期股", "valuation_framework": "PB",
            "forbidden_metric": "PE", "macro_sensitivity": "high"}}
        r = gd.check_g39("标的属周期股，PB 估值。", snap3)  # #3 macro 缺
        self.assertIsInstance(r, dict)
        self.assertFalse(r["passed"])
        self.assertIn("宏观", "".join(r["reasons"]))

    def test_g25_bare_word_no_src_now_fails(self):
        # 旧臂 1 只要「事件」词任意处在即过（high=0+medium>0 时不查 src）——纯词散落
        snap = {"s5_events": {"data": {"news": {
            "medium_value": [{"title": "行业新闻"}], "_python_layer": "completed"}}}}
        self.assertFalse(self._v(gd.check_g25, "近期事件面平静，无新催化剂。", snap))

    def test_g25_timeline_src_counts(self):
        # 事件检测读 timeline（m4 单一事件源）——timeline src 同样含 s5_events 锚
        self.assertTrue(self._v(gd.check_g25,
            "事件面：近 180 天 timeline 无致命码 [src: snapshot.s5_events.data.risk_signals.processed.timeline]",
            self._G25_SNAP))

    def test_g25_python_layer_guard_unchanged(self):
        snap = {"s5_events": {"data": {"news": {"high_value": [{}], "_python_layer": ""}}}}
        r = gd.check_g25("事件 [src: snapshot.s5_events.data.news]", snap)
        self.assertIsInstance(r, dict)
        self.assertFalse(r["passed"])
        self.assertIn("_python_layer", "".join(r["reasons"]))

if __name__ == "__main__":
    unittest.main(verbosity=2)
