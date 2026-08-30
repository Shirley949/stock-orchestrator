#!/usr/bin/env python3
"""peer 全链路回归测试：G15 三态门禁 + 反编造 + capstone 渲染 + 消费锚点。

G15 契约（s11_peer.data 三态，discovered_peer_codes None↔list 信号）：
  - never-run（discovered_peer_codes 缺键=None）+ 无「无适用同业」披露 → FAIL（防零数据假 PASS）
  - ran-but-failed（list 非空 + status=missing）+ 不披露限流 → FAIL；披露限流 → PASS
  - completed（status∈{ok,degraded}）+ ≥2 valid 核心6 + [src:s11_peer] 溯源 → PASS
  - 反编造：never-run 编造 peer 财务数字 → FAIL；完整性：status=ok 无 items → FAIL
  - weight≥3（critical，verify_gates 硬阻断杠杆）

capstone _render_peer：核心6 主行 + 行业位置/市场表现（target_rank/market_performance，东财同业一等公民）。
消费锚点：m6 估值行 items[].metrics + ≥2 peer；m1 target_rank(行业位置) vs dominant_business。
"""
import os, re, sys, unittest

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
        """600584 bug 根治：占位 missing（无 discovered_peer_codes 键）+ 无披露 → FAIL。"""
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
        """跑了（discovered_peer_codes 非空 list）但全败 + 诚实披露限流 → PASS。"""
        report = "同业数据因限流未能获取。"
        snap = _snap({"status": "missing", "discovered_peer_codes": ["600183", "600587"]})
        self.assertTrue(check_g15(report, snap))

    def test_ran_but_failed_silent_fails(self):
        """跑了仍 missing 却不披露限流 → FAIL（根治「调了子命令但漏披露→假 PASS」）。"""
        report = "我们分析了该公司基本面。"
        snap = _snap({"status": "missing", "discovered_peer_codes": ["600183"]})
        self.assertFalse(check_g15(report, snap))

    def test_ok_with_data_and_src_passes(self):
        """ok + ≥2 valid 核心6 + s11_peer 溯源 → PASS（正常路径不误伤）。"""
        items = [{"code": "600183", "metrics": _metrics()},
                 {"code": "600587", "metrics": _metrics(pe=18, roe=10)}]
        report = "[src: snapshot.s11_peer] 同业对比 PE/PB/ROE 见上。"
        snap = _snap({"status": "ok", "items": items, "discovered_peer_codes": ["600183", "600587"]})
        self.assertTrue(check_g15(report, snap))

    def test_never_run_fabricated_fails(self):
        """never-run + 编造 peer 财务数字（无披露）→ FAIL（反编造）。"""
        report = "同业对比 PE:15 PB:2 ROE:12 毛利率:30%。"
        snap = _snap({"status": "missing"})
        self.assertFalse(check_g15(report, snap))

    def test_ok_no_items_integrity_fails(self):
        """status=ok 却无 items（声明有数据实际没有）→ FAIL（完整性矛盾）。"""
        snap = _snap({"status": "ok", "discovered_peer_codes": ["600183"]})
        self.assertFalse(check_g15("同业对比 [src: snapshot.s11_peer]", snap))


class CapstoneRenderTests(unittest.TestCase):
    """L2：capstone _render_peer 核心6 主行渲染（em items[].metrics 仅核心6）。"""

    def _render(self, peer):
        L = []
        cp._render_peer(L, {"peer": peer})
        return "\n".join(L)

    def test_core6_rendered(self):
        peer = {
            "status": "ok", "peers_count": 1, "target_report_period": "2026一季报",
            "target_metrics": _metrics(),
            "items": [{"code": "600183", "name": "生益科技",
                       "metrics": _metrics(pe=18, roe=10)}],
        }
        out = self._render(peer)
        # 核心6 主行（目标 + peer）
        self.assertIn("PE 15", out)
        self.assertIn("ROE 12%", out)
        self.assertIn("生益科技", out)


class ConsumptionAnchorTests(unittest.TestCase):
    """L2：m6/m1 文档锚点存在（消费路径落地，非空泛）。"""

    @classmethod
    def setUpClass(cls):
        mods = os.path.join(os.path.dirname(__file__), '..', '..', 'stock-analysis-quality',
                            'references', 'modules')
        cls.m6 = open(os.path.join(mods, 'm6-decision.md'), encoding='utf-8').read()
        cls.m1 = open(os.path.join(mods, 'm1-narrative.md'), encoding='utf-8').read()

    def test_m6_peer_items_path_and_min2(self):
        """m6 估值行：dot-split 真路径 + ≥2 peer 实际数值约束。

        2026-08-30 R1 协同改：原断言冻结 `s11_peer.items[].metrics`（[] 记法，G21 必 FAIL
        的坏路径——三重锁死之一），随 m6-decision.md:42 修正为 `s11_peer.data.items`
        同提交改红为绿；新增负断言：src 模板禁含 `[`（防 [] 记法回潮）。
        """
        self.assertIn("snapshot.s11_peer.data.items", self.m6)
        self.assertIn("≥2 家 peer", self.m6)
        # 负断言：m6 的 [src: snapshot...] 标签里不得再出现 [] 下标记法
        for m in re.finditer(r"\[src:\s*snapshot\.([^\]]+)\]", self.m6):
            self.assertNotIn("[", m.group(1),
                             f"src 标签禁 [] 记法（G21 dot-split 必 FAIL）: {m.group(1)}")

    def test_m1_differentiation_anchor(self):
        """m1 差异化定位：target_rank(行业位置) + dominant_business 实证锚点。"""
        self.assertIn("target_rank", self.m1)
        self.assertIn("dominant_business", self.m1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
