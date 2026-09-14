"""test_view_envelope_contract — 视图信封合同：VIEW_PATHS 挂载视图终端节点必带 {view, status} 头。

合同消费方 = snapshot_view --list 挂载列（信任终端节点带 status 键）；
构建器漏头 → 挂载列恒打 None（歧义值误导「视图缺失」判断——--list 是存在性 oracle/c50b 视图认知重建依据）。
本测试钉两端：①构建器产出带头 + 投影键面不回退（hermetic 单元）②--list 挂载列消费头（合成快照端到端两极）。
intraday_60min.report_view 不在 VIEW_PATHS（b_head 的数据输入），不属本合同面。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent / "financial-data-routing"))

from report_views import build_market_context_report_view          # noqa: E402
from short_term_engine import _build_report_view                   # noqa: E402

SV = str(_HERE.parent / "scripts" / "snapshot_view.py")

_STE_ENRICH = {
    "direction_forecast": {"status": "ok", "direction": "neutral", "confidence": "NEUTRAL",
                           "probability": None, "horizon_days": 15, "rule_name": None,
                           "regime": "trend_down", "evidence": {"close": 20.98},
                           "expected_range": {"low": 19.1, "high": 22.8}},
    "multi_period": {"daily": {"state": "空方"}},
    "volume_check": {"amplified": True},
    "risk_control": {"stops": [{"level": "L1", "price": 19.5}], "kelly": 0},
    "divergence": None,
}


class TestBuilderEnvelopeHead(unittest.TestCase):
    """构建器单元：产出必带 {view, status} 头 + 投影键面不回退。"""

    def test_short_term_head_and_projection(self):
        v = _build_report_view(_STE_ENRICH)
        self.assertEqual(v["view"], "short_term")
        self.assertIn(v["status"], ("ok", "empty", "failed"))
        for key in ("forecast_line", "regime", "expected_range", "stops", "kelly"):
            self.assertIn(key, v)

    def test_market_context_head_and_projection(self):
        v = build_market_context_report_view({
            "index_sh": {"verdict": {"regime": "trend_down"}, "last": 3888.11},
            "index_cyb": {"ret5": 0.01},
            "board": {"name": "小金属", "status": "degraded"},
            "board_fund_flow": {"name": "小金属"}})
        self.assertEqual(v["view"], "market_context")
        self.assertEqual(v["status"], "ok")
        self.assertEqual(v["sh_regime"], "trend_down")
        self.assertEqual(v["sh_close"], 3888.11)
        self.assertEqual(v["cyb_ret5"], 0.01)
        self.assertEqual(v["board"]["status"], "degraded")


class TestListConsumesHead(unittest.TestCase):
    """端到端两极：合成快照 → --list 挂载列带头视图显示 ok / 缺席视图 ❌，全列零 None。"""

    def test_mount_column_has_no_none(self):
        snap = {"stock_code": "600392", "timestamp": "contract-test",
                "s4_technical": {"data": {"short_term_enrich": {
                    "report_view": _build_report_view(_STE_ENRICH)}}},
                "market_context": {"data": {"report_view": build_market_context_report_view({})}}}
        fd, p = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(snap, fh, ensure_ascii=False)
            r = subprocess.run([sys.executable, SV, p, "--list"], capture_output=True, text=True)
        finally:
            os.unlink(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertNotIn("None", out)
        for name in ("short_term", "market_context"):
            line = next(l for l in out.splitlines() if l.strip().startswith(name))
            self.assertTrue(line.rstrip().endswith(" ok"), f"{name} 挂载列应显示 ok: {line}")
        self.assertIn("❌ 未挂载", out)   # 负极：合成快照无 s1/s2 等，缺席视图仍显式报未挂载


if __name__ == "__main__":
    unittest.main()
