#!/usr/bin/env python3
"""test_g30_disclose_bucket.py — G30#1 披露义务 + _scene_bucket 三桶（P1b 2026-09-03）。

retrospective_audit_20260902 处置④：degraded/missing 改判「需披露的 gap」（独立桶，
非 present 亦非静默豁免——防 Goodhart 回流）。旧 `_scene_has_data` 黑名单语义把
status=degraded/missing 的非空信封（002202 实证：asset_safety={status:'degraded'}、
segment 富 dict status='missing'）落到 bool(val) 兜底判 present → gate 把从未到货的
维度当 present 强制覆盖（「真片面」假 FAIL）。

corpus 四段：
- FLIP：002202 形态快照 + 无披露报告 → 「真片面 ['资产安全','主营构成']」面退役，
  新面「披露义务 FAIL」点名 theme[path:status]
- PROTECTION（正外部性保护）：同快照 + 002202 §4.0 维表 verbatim 披露行 → 披露臂静默
  （强制出的诚实披露路线保持绿——审计 3d/112 正外部性不得回退）
- INVARIANT：真 present 维（s2_quote_kline ok+data）未覆盖 → 「有数据未纳入(真片面)」
  照旧 FAIL（覆盖执法不因三桶弱化）
- NEGATIVE：结构性缺席（scene 键 None，mode B 不拉 s1 等）→ 无披露义务（设计≠数据洞）

跑：python3 test_g30_disclose_bucket.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from capstone_panorama import _scene_bucket, panorama  # noqa: E402
from gate_definitions import check_g30  # noqa: E402

_BASE = """# 测试票 模式B 最小报告

📅 数据截止：2026-09-02

## 6. 综合研判

### 证据全景

- 多周期：月线/周线/日线共振，MA20 排列上升趋势 [src: snapshot.s2_quote_kline]
- 大盘环境：上证 trend_up，市场环境偏暖
- 量价：放量、量比 1.2、换手充分，MACD 量价配合，无背离 [src: snapshot.intraday_60min]

### 情景-动作矩阵

| 情景 | 概率 | 成立条件 | 目标价 | 动作 | 反方证据/风险 |
|---|---|---|---|---|---|
| 中性·区间震荡 | 60% | 若量能维持现水平 | 10~11 | 区间思路 | 上述共振失效则转弱 |
| 乐观·上破压力 | 25% | 触发放量突破压力位 | 11→12 | 突破加仓 | 假突破风险 |
| 悲观·失守支撑 | 15% | 一旦失守支撑位 | 9→8.5 | 失守减仓 | 跌破即趋势破坏 |
"""

# 002202 §4.0 维表披露行（verbatim，批1 L212 正外部性产物）
_DISCLOSED = """
| 维度 | 现状 | 说明 | 数据锚点 |
|------|------|------|---------|
| 资产安全 | status=degraded（现金/债务比、商誉等值未产出） | 本维数据降级，无法给出安全边际结论——B 模式不重拉三表，留待模式A补齐 | [src: snapshot.computed_metrics.asset_safety] |
| 主营构成 | 产品/行业/地区三维均 fetch_failed（SEGMENTSV 限流） | 结构占比缺失；业务范围参考：风机制造、风电服务、风电场投资 | [src: snapshot.s1_financial.data.segment_composition] |
"""


def _snap_002202():
    """002202 信封形态 verbatim（asset_safety 仅 status 键无 data；segment 富 dict 无 data）。"""
    return {
        "mode": "B",
        "computed_metrics": {"asset_safety": {"status": "degraded"}},
        "s1_financial": {"data": {"segment_composition": {
            "status": "missing", "note": "SEGMENTSV 限流",
            "product": {}, "industry": {}, "geo": {}}}},
    }


def _snap_absent_only():
    return {"mode": "B"}          # 全部 quant 路径缺席（mode B 不拉 s1/lhb 等）


def _snap_present_lhb():
    """INVARIANT 用：lhb processed 在场（其关键词 龙虎榜/席位 与 B 定性词零重叠，
    不会被最小报告顺带覆盖）。"""
    snap = _snap_002202()
    snap["lhb"] = {"data": {"processed": {"signals": [{"code": "L1"}], "signal_type": "x"}}}
    return snap


def _g30(report, data):
    out = check_g30(report, data)
    return out["passed"], out.get("reasons", []) if isinstance(out, dict) else []


def _rs(reasons):
    return " ".join(reasons)


class TestSceneBucket(unittest.TestCase):
    """三桶判定两极（含旧 bug 形态回归）。"""

    def test_envelope_poles(self):
        self.assertEqual(_scene_bucket({"status": "degraded"}), "gap")            # 002202 asset_safety
        self.assertEqual(_scene_bucket({"status": "missing", "product": {}}), "gap")  # 002202 segment
        self.assertEqual(_scene_bucket({"status": "failed"}), "failed")
        self.assertEqual(_scene_bucket({"status": "error", "data": {}}), "failed")
        self.assertEqual(_scene_bucket({"status": "throttled"}), "failed")
        self.assertEqual(_scene_bucket({"status": "ok", "data": {"a": 1}}), "present")
        self.assertEqual(_scene_bucket({"status": "ok", "data": [1, 2]}), "present")
        self.assertEqual(_scene_bucket(None), "absent")
        self.assertEqual(_scene_bucket([]), "absent")
        self.assertEqual(_scene_bucket(""), "absent")
        self.assertEqual(_scene_bucket({"status": "ok", "data": []}), "gap")      # 真·空（无披露义务）
        self.assertEqual(_scene_bucket({"data": {"status": "failed"}}), "failed")  # 嵌套信封

    def test_panorama_disclose_set(self):
        pan = panorama(_snap_002202())
        themes = sorted(d["theme"] for d in pan["disclose_quant"])
        self.assertEqual(themes, ["主营构成", "资产安全"])
        by_theme = {d["theme"]: d for d in pan["disclose_quant"]}
        self.assertEqual(by_theme["资产安全"]["status"], "degraded")
        self.assertEqual(by_theme["主营构成"]["status"], "missing")
        self.assertNotIn("资产安全", pan["present_quant"])   # 旧 bug：曾判 present
        self.assertEqual(panorama(_snap_absent_only())["disclose_quant"], [])


class TestG30DiscloseArm(unittest.TestCase):
    def test_flip_misfire_retired_disclosure_required(self):
        """002202 形态无披露：真片面面退役，披露义务面点名 theme[path:status]。"""
        ok, reasons = _g30(_BASE, _snap_002202())
        self.assertFalse(ok)
        rs = _rs(reasons)
        self.assertIn("披露义务", rs)
        self.assertIn("资产安全[computed_metrics.asset_safety:degraded]", rs)
        self.assertIn("主营构成[s1_financial.data.segment_composition:missing]", rs)
        self.assertFalse(any("有数据未纳入" in r and "资产安全" in r for r in reasons),
                         reasons)   # 旧「真片面 ['资产安全','主营构成']」假 FAIL 面退役

    def test_protection_disclosure_satisfies(self):
        """正外部性保护：002202 §4.0 维表披露行 verbatim → 披露臂静默、G30 转 PASS。"""
        ok, reasons = _g30(_BASE + _DISCLOSED, _snap_002202())
        self.assertTrue(ok, reasons)
        self.assertFalse(any("披露义务" in r for r in reasons), reasons)

    def test_invariant_present_still_enforced(self):
        """真 present 维未覆盖 → 真片面 FAIL 照旧（覆盖执法不弱化）。"""
        ok, reasons = _g30(_BASE, _snap_present_lhb())
        self.assertFalse(ok)
        self.assertTrue(any("有数据未纳入" in r and "龙虎榜资金" in r for r in reasons),
                        reasons)

    def test_negative_structural_absent_no_obligation(self):
        """结构性缺席（mode B 作用域外）→ 无披露义务、无覆盖义务 → G30 PASS。"""
        ok, reasons = _g30(_BASE, _snap_absent_only())
        self.assertTrue(ok, reasons)


if __name__ == "__main__":
    unittest.main(verbosity=2)
