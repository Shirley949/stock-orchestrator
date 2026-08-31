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
        """bool 返回门存在时 warn 上浮 sidecar（升级硬断言的条件=一轮 cron 零命中）。"""
        res = verify_gates(self.report, self.data, "profile_full")
        self.assertIn("bool_return_warn", res,
                      "M 级 bool-expression 门在场时须有 warn；若为空说明已全量 GateResult 化，"
                      "可将 verify_gates warn 升硬断言")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
