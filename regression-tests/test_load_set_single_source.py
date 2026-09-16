#!/usr/bin/env python3
"""
test_load_set_single_source.py —— 加载集单一真相源三方对拍（plan-compact-loop-fix-v4 批1）

锁三件事（机制=单源，文档=投影，fixture=锁）：
  1. 机制表（skill_dep_graph.MODE_MODULE_FILES）模块集 == orchestrator SKILL.md
     Phase 3 JIT 表 A/B 行主列（双向集合相等，多/漏两侧分列报）。
  2. m11 延迟语义：JIT A 行延读列点名 m11 → 机制 A 集 m11 带 load=deferred 且不占
     装载位；JIT B 行「同上」→ 机制 B 装载集不含 m11（缺席即其延迟表示）。
  3. quality SKILL.md 模块表投影相容（mechanism→quality 单向）：机制两集每个模块
     在投影表有行且模式标注相容（A∈{模式 A,全部}；B∈{模式 B,全部}；m11→排障时读）。
     反向不锁：投影表是目录（含条件模块 m35/m9 等非装载集成员）。

红极自证：comparator 注入坏样例（JIT B 行删 m39 / 投影表删 m39 行）必须报 mismatch，
同源未损坏文本必须干净通过——证明红得了，非恒绿空转。零网络纯离线。
"""
import re
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS / "lib"))

import skill_dep_graph as sdg

ORCH_SKILL = _HERE.parent / "SKILL.md"
QUALITY_SKILL = _HERE.parent.parent / "stock-analysis-quality" / "SKILL.md"
GEN_CHECKLIST = _SCRIPTS / "generate_checklist.py"
DEFERRED_STATUS = "⏸ 延迟读：首次 verify FAIL 才 Read"


def _token(basename: str) -> str:
    """m12-summary.md → m12；非 mNN- 前缀文件名原样返回"""
    m = re.match(r"m(\d+)-", basename)
    return f"m{m.group(1)}" if m else basename


def mech_modules(mode: str):
    """机制表模块集 → (main_tokens, deferred_tokens)"""
    main, deferred = set(), set()
    for entry in sdg.MODE_MODULE_FILES.get(mode, []):
        tok = _token(Path(entry["path"]).name)
        (deferred if entry.get("load") == "deferred" else main).add(tok)
    return main, deferred


def _jit_section(text: str) -> str:
    m = re.search(r"###\s*⚠️\s*模块 JIT 加载.*?(?=\n## )", text, re.S)
    return m.group(0) if m else ""


def parse_jit(text: str) -> dict:
    """JIT 表段 → {mode: (main_tokens, deferred_tokens)}
    B 行延迟列「同上 m11（…）」含括注里的 mNN 字样，不解析——同上=继承 A 延迟政策，
    由 compare 的 m11 规则显式执法（机制表示=B 装载集缺席）。"""
    out = {}
    for line in _jit_section(text).splitlines():
        m = re.match(r"\|\s*\*\*(A|B)\*\*\s*\|([^|]+)\|([^|]*)\|", line)
        if not m:
            continue
        mode, main_cell, defer_cell = m.group(1), m.group(2), m.group(3)
        main = {f"m{x}" for x in re.findall(r"m(\d+)", main_cell)}
        deferred = ({f"m{x}" for x in re.findall(r"m(\d+)", defer_cell)}
                    if mode == "A" else set())
        out[mode] = (main, deferred)
    return out


def parse_quality(text: str) -> dict:
    """quality 模块表 → {token: 模式标注}；只取含 references/modules/ 路径的行"""
    out = {}
    for line in text.splitlines():
        m = re.match(r"\|[^|]+\|\s*`?references/modules/(m[\w.-]+\.md)`?\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            out[_token(m.group(1))] = m.group(2)
    return out


def compare(mech: dict, jit: dict, quality_tags: dict) -> list:
    """三方对拍 → 违规清单（空=一致）。mech={"A":(main,deferred),...}"""
    issues = []
    for mode in ("A", "B"):
        if mode not in jit:
            issues.append(f"[{mode}] JIT 表缺 {mode} 行（JIT 段丢失/格式漂移）")
            continue
        main, deferred = mech[mode]
        jit_main, jit_deferred = jit[mode]
        if main != jit_main:
            issues.append(f"[{mode}] 装载集不一致: 机制多={sorted(main - jit_main)} "
                          f"JIT 多={sorted(jit_main - main)}")
        if deferred != jit_deferred:
            issues.append(f"[{mode}] 延迟集不一致: 机制={sorted(deferred)} JIT={sorted(jit_deferred)}")
    if "m11" in mech["B"][0]:
        issues.append("[B] m11 不得入 B 装载集（JIT B 行延迟列=「同上」，机制表示=缺席）")
    compat = {"A": {"模式 A", "全部"}, "B": {"模式 B", "全部"}}
    for mode in ("A", "B"):
        main, deferred = mech[mode]
        for tok in main | deferred:
            tag = quality_tags.get(tok)
            if tag is None:
                issues.append(f"[{mode}] 模块 {tok} 在 quality SKILL.md 模块表无行"
                              "（投影缺行/改名逃逸）")
            elif tok == "m11":
                if "排障" not in tag:
                    issues.append(f"[{mode}] m11 投影标注应含「排障时读」，实为「{tag}」")
            elif tag not in compat[mode]:
                issues.append(f"[{mode}] 模块 {tok} 投影标注「{tag}」与装载集不相容"
                              f"（应∈{sorted(compat[mode])}）")
    return issues


def _real_sources():
    mech = {mode: mech_modules(mode) for mode in ("A", "B")}
    jit = parse_jit(ORCH_SKILL.read_text(encoding="utf-8"))
    quality = parse_quality(QUALITY_SKILL.read_text(encoding="utf-8"))
    return mech, jit, quality


class TestThreeWaySingleSource(unittest.TestCase):
    def test_real_sources_consistent(self):
        mech, jit, quality = _real_sources()
        self.assertIn("A", jit, "JIT 段未解析出 A 行")
        self.assertIn("B", jit, "JIT 段未解析出 B 行")
        issues = compare(mech, jit, quality)
        self.assertEqual(issues, [], "三方漂移:\n" + "\n".join(issues))

    def test_v6l_alignment(self):
        """批1 收尾断言永久化：A=13+m11deferred（流水架构批1 补注册 m9-governance，12→13）；B=6（含 m39 无 m11）"""
        main_a, deferred_a = mech_modules("A")
        main_b, deferred_b = mech_modules("B")
        self.assertEqual(len(main_a), 13)
        self.assertIn("m9", main_a)
        self.assertEqual(deferred_a, {"m11"})
        self.assertIn("m39", main_b)
        self.assertNotIn("m11", main_b)
        self.assertEqual(len(main_b), 6)
        # resolve 透传：deferred 语义流到消费方（generate_checklist 装载表渲染依赖）
        res_a = sdg.resolve_required_files("A", "分析")
        m11_entries = [x for x in res_a if "m11-gates.md" in x["path"]]
        self.assertEqual(len(m11_entries), 1)
        self.assertEqual(m11_entries[0].get("load"), "deferred")
        res_b = sdg.resolve_required_files("B", "分析")
        self.assertFalse([x for x in res_b if "m11-gates.md" in x["path"]])

    def test_render_branch_present(self):
        """generate_checklist 装载表 deferred 渲染分支在位（静态锁，防误删）"""
        src = GEN_CHECKLIST.read_text(encoding="utf-8")
        self.assertIn(DEFERRED_STATUS, src)
        self.assertIn('f.get("load") == "deferred"', src)

    def test_scenario_module_split(self):
        """分表结构锁：scenario 表只准 /scenarios/ 路径，module 表只准 /modules/ 路径"""
        for mode in ("A", "B"):
            for e in sdg.MODE_SCENARIO_FILES[mode]:
                self.assertIn("/scenarios/", e["path"], f"scenario 表混入非场景路径: {e['path']}")
            for e in sdg.MODE_MODULE_FILES[mode]:
                self.assertIn("/modules/", e["path"], f"module 表混入非模块路径: {e['path']}")

    def test_paths_exist(self):
        for mode in ("A", "B"):
            for e in sdg.MODE_SCENARIO_FILES[mode] + sdg.MODE_MODULE_FILES[mode]:
                self.assertTrue((sdg.SKILL_ROOT / e["path"]).exists(),
                                f"{mode} 装载路径不存在: {e['path']}")


class TestRedPoles(unittest.TestCase):
    """红极自证： comparator 对坏样例必须报，对好样例必须净——两极都见"""

    def setUp(self):
        self.mech, self.jit, self.quality = _real_sources()
        base_issues = compare(self.mech, self.jit, self.quality)
        self.assertEqual(base_issues, [], "真实源已漂移，红极对照失效——先修三方一致性")

    def test_red_jit_drop_m39(self):
        orch = ORCH_SKILL.read_text(encoding="utf-8")
        bad = orch.replace("m38 / m39 / m3 / m36 / m37 / m6", "m38 / m3 / m36 / m37 / m6")
        self.assertNotEqual(bad, orch, "JIT B 行原文未命中替换锚（SKILL.md 格式漂移）")
        issues = compare(self.mech, parse_jit(bad), self.quality)
        self.assertTrue(any("[B]" in i for i in issues), f"JIT 坏样例未报: {issues}")

    def test_red_quality_drop_m39_row(self):
        quality_text = QUALITY_SKILL.read_text(encoding="utf-8")
        bad_lines = [l for l in quality_text.splitlines() if "m39-b-xq-voice.md" not in l]
        bad = "\n".join(bad_lines)
        self.assertNotEqual(bad, quality_text, "投影表未命中 m39 行（SKILL.md 格式漂移）")
        issues = compare(self.mech, self.jit, parse_quality(bad))
        self.assertTrue(any("m39" in i for i in issues), f"投影坏样例未报: {issues}")

    def test_red_m11_in_b_load_set(self):
        bad_mech = {
            "A": self.mech["A"],
            "B": (self.mech["B"][0] | {"m11"}, self.mech["B"][1]),
        }
        issues = compare(bad_mech, self.jit, self.quality)
        self.assertTrue(any("m11" in i for i in issues), f"m11 入 B 装载集未报: {issues}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
