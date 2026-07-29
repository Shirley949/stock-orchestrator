#!/usr/bin/env python3
"""peer 全链路回归测试（Bug 3）：handoff gate（L0）+ 消费（L2）。

背景（600584 实测）：runner.py A 模式写 s11_peer 占位 missing（无 websearch_peer_codes 键），
LLM 漏跑 `peer` 子命令，而旧 G15 对所有 missing 一律豁免（websearch_codes=None 跳过检查→PASS），
零数据照样 PASS。根因是 **handoff 不可靠**，非数据源。

L0 修复（零新 schema 字段，复用 websearch_peer_codes None↔list 信号）：
  - G15 weight 2→3（critical，weight≥3 是 verify_gates 唯一硬阻断杠杆）；
  - G15 never-run 检查：websearch_codes is None（占位无键=从未跑）→ 须诚实披露「无适用同业」否则 FAIL；
  - runner _generate_llm_fallback_tasks：占位 missing → emit peer 子命令（交回 LLM）；
  - checklist c19a：提示跑 peer 子命令。
L2 修复（消费最大化）：
  - m6 估值行：items[].metrics 核心6 + ≥2 peer 实际数值；
  - m1 差异化定位：gsjj_yw vs dominant_business 实证；
  - capstone _render_peer：核心6 主行 + 富字段次行（eps/营收/净利/资产负债率/每股净资产）。

信号编码（零新字段）：
  status=missing + websearch_peer_codes is None（占位无键）= 从未跑（600584 bug）
  status=missing + websearch_peer_codes 为 list = 跑了但全败
  status∈{ok,degraded} = 已完成
"""
import os, sys, unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', 'scripts')
sys.path.insert(0, os.path.join(SCRIPTS, 'lib'))
sys.path.insert(0, SCRIPTS)

from gate_definitions import check_g15, GATE_WEIGHTS
import capstone_panorama as cp

ROUTING = os.path.join(os.path.dirname(__file__), '..', '..', 'financial-data-routing')
sys.path.insert(0, ROUTING)


def _snap(peer_data, stock_type="半导体股"):
    return {"stock_type": stock_type, "s11_peer": {"data": peer_data}}


def _metrics(**kw):
    """默认核心 6 全填的 metrics。"""
    base = {"rev_yoy": 10, "np_yoy": 5, "pe": 15, "pb": 2, "roe": 12, "gross_margin": 30}
    base.update(kw)
    return base


class G15HandoffGateTests(unittest.TestCase):
    """L0：G15 三态 + 反编造 + never-run 根治。"""

    def test_weight_is_critical(self):
        """G15 weight=3（≥3 即 critical，verify_gates 唯一硬阻断杠杆）。"""
        self.assertGreaterEqual(GATE_WEIGHTS["G15"], 3)

    def test_never_run_no_disclosure_fails(self):
        """600584 bug 根治：占位 missing（无 websearch_peer_codes 键）+ 无披露 → FAIL。"""
        report = "我们分析了该公司的基本面与技术面。"
        snap = _snap({"status": "missing"})
        self.assertFalse(check_g15(report, snap),
                         "never-run + 无披露 应 FAIL（旧逻辑静默 PASS=bug）")

    def test_never_run_with_disclosure_passes(self):
        """占位 missing + 诚实披露「无适用同业」→ PASS（独家/垄断/次新 是有效结论）。"""
        for kw in ("无适用同业", "无可比", "独家", "垄断", "次新", "无同业", "尚无可比", "行业唯一", "无可比标的"):
            with self.subTest(kw=kw):
                self.assertTrue(check_g15(f"该公司{kw}，无对标。", _snap({"status": "missing"})),
                                f"披露「{kw}」应 PASS")

    def test_ran_but_failed_honest_passes(self):
        """跑了（websearch_peer_codes 非空 list）但全败 + 诚实披露限流 → PASS。"""
        report = "同业数据因限流未能获取。"
        snap = _snap({"status": "missing", "websearch_peer_codes": ["600183", "600587"]})
        self.assertTrue(check_g15(report, snap))

    def test_ran_but_failed_silent_fails(self):
        """跑了仍 missing 却不披露限流 → FAIL（根治「调了子命令但漏披露→假 PASS」）。"""
        report = "我们分析了该公司基本面。"
        snap = _snap({"status": "missing", "websearch_peer_codes": ["600183"]})
        self.assertFalse(check_g15(report, snap))

    def test_ok_with_data_and_src_passes(self):
        """ok + ≥2 valid 核心6 + s11_peer 溯源 → PASS（正常路径不误伤）。"""
        items = [{"code": "600183", "metrics": _metrics()},
                 {"code": "600587", "metrics": _metrics(pe=18, roe=10)}]
        report = "[src: snapshot.s11_peer] 同业对比 PE/PB/ROE 见上。"
        snap = _snap({"status": "ok", "items": items, "websearch_peer_codes": ["600183", "600587"]})
        self.assertTrue(check_g15(report, snap))

    def test_never_run_fabricated_fails(self):
        """never-run + 编造 peer 财务数字（无披露）→ FAIL（反编造）。"""
        report = "同业对比 PE:15 PB:2 ROE:12 毛利率:30%。"
        snap = _snap({"status": "missing"})
        self.assertFalse(check_g15(report, snap))

    def test_ok_no_items_integrity_fails(self):
        """status=ok 却无 items（声明有数据实际没有）→ FAIL（完整性矛盾）。"""
        snap = _snap({"status": "ok", "websearch_peer_codes": ["600183"]})
        self.assertFalse(check_g15("同业对比 [src: snapshot.s11_peer]", snap))


class FallbackTaskTests(unittest.TestCase):
    """L0：_generate_llm_fallback_tasks peer 任务 emit 四态。"""

    @classmethod
    def setUpClass(cls):
        import runner
        cls.runner = runner

    def _peer_tasks(self, snap):
        return [t for t in self.runner._generate_llm_fallback_tasks(snap)
                if t.get("task") == "peer_comparison"]

    def test_placeholder_emits_peer_task(self):
        """占位 missing（无 websearch_peer_codes 键）→ emit peer 任务（交回 LLM）。"""
        snap = {"stock_code": "600584.SH", "s11_peer": {"data": {"status": "missing"}},
                "s3_cninfo_pdf": {"data": {}}}
        tasks = self._peer_tasks(snap)
        self.assertEqual(len(tasks), 1)
        self.assertIn("600584.SH", tasks[0]["command"])
        self.assertIn("peer", tasks[0]["command"])

    def test_ran_but_failed_does_not_emit(self):
        """跑了（websearch_peer_codes 非空）→ 不 emit（已跑过，不重复交回）。"""
        snap = {"stock_code": "600584.SH",
                "s11_peer": {"data": {"status": "missing", "websearch_peer_codes": ["600183"]}},
                "s3_cninfo_pdf": {"data": {}}}
        self.assertEqual(self._peer_tasks(snap), [])

    def test_completed_does_not_emit(self):
        """已完成（status=ok）→ 不 emit。"""
        snap = {"stock_code": "600584.SH",
                "s11_peer": {"data": {"status": "ok", "websearch_peer_codes": ["600183"], "items": [{}]}},
                "s3_cninfo_pdf": {"data": {}}}
        self.assertEqual(self._peer_tasks(snap), [])

    def test_no_peer_scene_does_not_emit(self):
        """无 s11_peer（非 peer 场景）→ 不 emit。"""
        snap = {"stock_code": "600584.SH", "s3_cninfo_pdf": {"data": {}}}
        self.assertEqual(self._peer_tasks(snap), [])


class CapstoneRenderTests(unittest.TestCase):
    """L2：capstone _render_peer 核心6 + 富字段渲染。"""

    def _render(self, peer):
        L = []
        cp._render_peer(L, {"peer": peer})
        return "\n".join(L)

    def test_core6_and_rich_rendered(self):
        peer = {
            "status": "ok", "peers_count": 1, "target_report_period": "2026一季报",
            "target_metrics": _metrics(eps=0.52, rev=1.2e9, np=3e8, debt_ratio=40.2, nav_per_share=5.6),
            "items": [{"code": "600183", "name": "生益科技",
                       "metrics": _metrics(pe=18, roe=10, eps=0.4, debt_ratio=35.0)}],
        }
        out = self._render(peer)
        # 核心6 主行
        self.assertIn("PE 15", out)
        self.assertIn("ROE 12%", out)
        self.assertIn("生益科技", out)
        # 富字段次行（亿格式化）
        self.assertIn("EPS 0.52", out)
        self.assertIn("营收 12.00亿", out)      # 1.2e9 → 12.00亿
        self.assertIn("净利 3.00亿", out)        # 3e8 → 3.00亿
        self.assertIn("资产负债率 40.2%", out)

    def test_missing_status_warns_to_run_peer(self):
        """status=missing → 提示先跑 peer 模式（不静默空过 G30#1 反片面）。"""
        out = self._render({"status": "missing"})
        self.assertIn("missing", out)
        self.assertTrue("peer" in out)


class ConsumptionAnchorTests(unittest.TestCase):
    """L2：m6/m1 文档锚点存在（消费路径落地，非空泛）。"""

    @classmethod
    def setUpClass(cls):
        mods = os.path.join(os.path.dirname(__file__), '..', '..', 'stock-analysis-quality',
                            'references', 'modules')
        cls.m6 = open(os.path.join(mods, 'm6-decision.md'), encoding='utf-8').read()
        cls.m1 = open(os.path.join(mods, 'm1-narrative.md'), encoding='utf-8').read()

    def test_m6_peer_items_path_and_min2(self):
        """m6 估值行：items[].metrics 路径 + ≥2 peer 实际数值约束。"""
        self.assertIn("s11_peer.items[].metrics", self.m6)
        self.assertIn("≥2 家 peer", self.m6)

    def test_m1_gsjj_yw_anchor(self):
        """m1 差异化定位：gsjj_yw vs dominant_business 实证锚点。"""
        self.assertIn("gsjj_yw", self.m1)
        self.assertIn("dominant_business", self.m1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
