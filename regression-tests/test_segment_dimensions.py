#!/usr/bin/env python3
"""
test_segment_dimensions.py —— 三维主营构成（产品/行业/地区）+ 海外敞口 + 跨维派生信号单测

Phase 3 §3.4 测试矩阵（金牌范式仿 test_overseas_derivation.py）。覆盖：
  ① geo_region.classify_region 不变量（外销→overseas 立讯 bug fix；华东→domestic 不误报；
     东南亚→overseas；其他地区→unknown）
  ② geo_region.compute_overseas_pct 双向（direct 显式 + alt 残差；precedence 非 max）
  ③ runner._compute_overseas_status 五态（geo.status 派生：activated / domestic_only /
     underivable_geo_vacuum / underivable_geo_failed / underivable_but_historical）
  ④ runner._compute_concentration_composite（region×product CR1 合取 → composite_severe 跳级）
  ⑤ runner._compute_tariff_vulnerability（三维合取：fatal / partial / low / none）
  ⑥ runner._compute_product_industry_alignment（4 象限 + underivable）
  ⑦ runner._cr1_from_revenue
  ⑧ gate G34/G35/G36（三维对称 5 态）+ G17（tariff_vulnerability 触发）+ G22（segment 数据驱动）

零网络、零外部文件依赖（snapshot 内联）。__file__ 相对定位 runner / geo_region / gate_definitions。
运行：python3 test_segment_dimensions.py  或经 run_regression.sh 串联。
"""
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROUTING = _HERE.parent.parent / "financial-data-routing"
_GATE_LIB = _HERE.parent / "scripts" / "lib"
import sys
sys.path.insert(0, str(_ROUTING))
sys.path.insert(0, str(_GATE_LIB))

import runner
import gate_definitions as g
from geo_region import classify_region, compute_overseas_pct


# ---------------- snapshot helpers ----------------

def _snap_seg(product=None, industry=None, geo=None, dim_status=None):
    """构造 snapshot：s1_financial.data.segment_composition（canonical v2.0 子集）。"""
    seg = {}
    if product is not None:
        seg["product"] = product
    if industry is not None:
        seg["industry"] = industry
    if geo is not None:
        seg["geo"] = geo
    if dim_status is not None:
        seg["dimension_status"] = dim_status
    return {"s1_financial": {"data": {"segment_composition": seg}}}


def _metrics(has=None, pct=None):
    """computed_metrics 子集（_compute_overseas_status 读 has_overseas_exposure/reported_overseas_pct）。"""
    m = {}
    if has is not None:
        m["has_overseas_exposure"] = has
    if pct is not None:
        m["reported_overseas_pct"] = pct
    return m


def _dim(status, top1_name="", top1_ratio=None, report_date=None):
    d = {"status": status}
    if top1_name:
        d["top1_name"] = top1_name
    if top1_ratio is not None:
        d["top1_ratio"] = top1_ratio
    if report_date:
        d["report_date"] = report_date
    return d


# ============================================================
# ① classify_region 不变量
# ============================================================
class ClassifyRegionTest(unittest.TestCase):

    def test_waixiao_overseas_fix(self):
        """外销 → overseas（立讯 85.2% bug fix：旧 4 词全漏）。"""
        self.assertEqual(classify_region("外销"), "overseas")

    def test_neixiao_domestic(self):
        """内销 → domestic。"""
        self.assertEqual(classify_region("内销"), "domestic")

    def test_overseas_keywords(self):
        for n in ("境外", "国外", "海外", "出口", "以外"):
            self.assertEqual(classify_region(n), "overseas", f"{n} 应 overseas")

    def test_foreign_country_bloc(self):
        """国名/洲名 exact → overseas（含 东南亚 补集）。"""
        for n in ("美国", "东南亚", "欧洲", "东盟", "亚太"):
            self.assertEqual(classify_region(n), "overseas", f"{n} 应 overseas")

    def test_domestic_regions(self):
        """境内/大区/省/市 → domestic（不误报海外）。"""
        for n in ("境内", "国内", "中国大陆", "华东", "华南", "华北", "广东省", "深圳市"):
            self.assertEqual(classify_region(n), "domestic", f"{n} 应 domestic")

    def test_qita_unknown(self):
        """其他地区 → unknown（无 domestic 锚，交残差路径）。"""
        self.assertEqual(classify_region("其他地区"), "unknown")

    def test_empty_unknown(self):
        self.assertEqual(classify_region(""), "unknown")
        self.assertEqual(classify_region(None), "unknown")


# ============================================================
# ② compute_overseas_pct 双向 + precedence
# ============================================================
class OverseasPctTest(unittest.TestCase):

    def test_lixun_waixiao_direct_85(self):
        """立讯：外销85.2/内销14.8 → direct≈85.2（外销=overseas 显式行）。"""
        r = compute_overseas_pct(
            [{"name": "外销", "revenue": 85.2}, {"name": "内销", "revenue": 14.8}],
            name_key="name", val_key="revenue")
        self.assertAlmostEqual(r["pct"], 85.2, places=1)
        self.assertEqual(r["status"], "overseas_direct")
        self.assertTrue(r["has_overseas_signal"])

    def test_jingwai_direct_40(self):
        """境内60/境外40 → direct=40%。"""
        r = compute_overseas_pct(
            [{"name": "境内", "revenue": 60}, {"name": "境外", "revenue": 40}],
            name_key="name", val_key="revenue")
        self.assertAlmostEqual(r["pct"], 40.0, places=1)
        self.assertEqual(r["status"], "overseas_direct")

    def test_domestic_only_no_signal(self):
        """华东/华南 纯国内 → domestic_only，pct=None。"""
        r = compute_overseas_pct(
            [{"name": "华东", "revenue": 80}, {"name": "华南", "revenue": 20}],
            name_key="name", val_key="revenue")
        self.assertIsNone(r["pct"])
        self.assertFalse(r["has_overseas_signal"])

    def test_precedence_direct_over_alt(self):
        """precedence：有显式 overseas 行时取 direct（精确），不用 alt 残差。

        境内40/境外40/其他地区20：direct=40%，alt=(100-40)/100=60%——取 direct=40 非 max=60。
        """
        r = compute_overseas_pct([
            {"name": "境内", "revenue": 40},
            {"name": "境外", "revenue": 40},
            {"name": "其他地区", "revenue": 20},
        ], name_key="name", val_key="revenue")
        self.assertAlmostEqual(r["pct"], 40.0, places=1)
        self.assertEqual(r["status"], "overseas_direct")

    def test_alt_residual_only_when_no_direct(self):
        """alt 残差推断：无显式 overseas 行 + 有 domestic 锚 → 残差即海外。

        内销60/其他地区40：direct=0，alt=(100-60)/100=40%。
        """
        r = compute_overseas_pct([
            {"name": "内销", "revenue": 60},
            {"name": "其他地区", "revenue": 40},
        ], name_key="name", val_key="revenue")
        self.assertAlmostEqual(r["pct"], 40.0, places=1)
        self.assertEqual(r["status"], "overseas_inferred")

    def test_no_domestic_anchor_no_alt(self):
        """无 domestic 锚（纯未归类垃圾）→ alt 不计算，不误判。"""
        r = compute_overseas_pct([
            {"name": "其他地区", "revenue": 60},
            {"name": "分部资产", "revenue": 40},
        ], name_key="name", val_key="revenue")
        self.assertIsNone(r["pct"])   # 无 domestic 锚，alt=None
        self.assertEqual(r["status"], "domestic_only")

    def test_empty_and_garbage(self):
        self.assertEqual(compute_overseas_pct([])["status"], "no_data")
        self.assertEqual(
            compute_overseas_pct([{"name": "境外", "revenue": "N/A"}],
                                 name_key="name", val_key="revenue")["status"], "no_data")


# ============================================================
# ③ _compute_overseas_status 五态（geo.status 派生）
# ============================================================
class OverseasStatusTest(unittest.TestCase):

    def test_activated(self):
        snap = _snap_seg(dim_status={"geo": _dim("disclosed_ok")})
        self.assertEqual(runner._compute_overseas_status(snap, _metrics(has=True, pct=40)),
                         {"status": "activated", "pct": 40})

    def test_domestic_only(self):
        snap = _snap_seg(dim_status={"geo": _dim("disclosed_ok")})
        self.assertEqual(runner._compute_overseas_status(snap, _metrics(has=None, pct=2)),
                         {"status": "domestic_only", "pct": 2})

    def test_underivable_geo_vacuum(self):
        """geo not_disclosed → 真空（不查非零）。"""
        snap = _snap_seg(dim_status={"geo": _dim("not_disclosed")})
        self.assertEqual(runner._compute_overseas_status(snap, _metrics(has=True, pct=40)),
                         {"status": "underivable_geo_vacuum", "pct": None})

    def test_underivable_geo_failed(self):
        """geo fetch_failed → 拉取失败（区别于真空）。"""
        snap = _snap_seg(dim_status={"geo": _dim("fetch_failed")})
        self.assertEqual(runner._compute_overseas_status(snap, _metrics(has=True, pct=40)),
                         {"status": "underivable_geo_failed", "pct": None})

    def test_underivable_but_historical(self):
        """geo stale_disclosure → 诚实保留历史值（三环 case：止 2023，境外 20.1%）。"""
        snap = _snap_seg(dim_status={"geo": _dim("stale_disclosure", report_date="2023-12-31")})
        out = runner._compute_overseas_status(snap, _metrics(has=True, pct=20.11))
        self.assertEqual(out["status"], "underivable_but_historical")
        self.assertAlmostEqual(out["pct"], 20.11, places=2)
        self.assertEqual(out["as_of"], "2023-12-31")


# ============================================================
# ④ _compute_concentration_composite（合取 → 跳级）
# ============================================================
class ConcentrationCompositeTest(unittest.TestCase):

    def test_severe_conjunction(self):
        """region_cr1=0.8 > 0.7 AND product_cr1=0.6 > 0.5 → composite_severe（单点失败跳级）。"""
        snap = _snap_seg(
            geo=[{"revenue": 80}, {"revenue": 20}],
            product=[{"revenue": 60}, {"revenue": 40}])
        out = runner._compute_concentration_composite(snap)
        self.assertAlmostEqual(out["region_cr1"], 0.8, places=2)
        self.assertAlmostEqual(out["product_cr1"], 0.6, places=2)
        self.assertTrue(out["composite_severe"])

    def test_not_severe_region_below_threshold(self):
        """region_cr1=0.6 < 0.7 → 不跳级（即使 product 集中）。"""
        snap = _snap_seg(
            geo=[{"revenue": 60}, {"revenue": 40}],
            product=[{"revenue": 80}, {"revenue": 20}])
        out = runner._compute_concentration_composite(snap)
        self.assertFalse(out["composite_severe"])

    def test_missing_dim_no_crash(self):
        """缺维（空 geo）→ region_cr1=None，severe=False。"""
        snap = _snap_seg(product=[{"revenue": 80}, {"revenue": 20}])
        out = runner._compute_concentration_composite(snap)
        self.assertIsNone(out["region_cr1"])
        self.assertFalse(out["composite_severe"])


# ============================================================
# ⑤ _compute_tariff_vulnerability（三维合取）
# ============================================================
class TariffVulnerabilityTest(unittest.TestCase):

    def _snap(self, top1_product, industry_name):
        return _snap_seg(dim_status={"product": _dim("disclosed_ok", top1_name=top1_product)},
                         ) | {"s55_industry": {"data": {"industry": {"industry_name": industry_name}}}}

    def test_fatal_all_three(self):
        """海外 activated + 变压器(出口敏感) + 电力设备(制裁敏感) → fatal（特变 case）。"""
        snap = self._snap("变压器", "电力设备")
        out = runner._compute_tariff_vulnerability(snap, {"status": "activated", "pct": 13})
        self.assertEqual(out["level"], "fatal")
        self.assertTrue(out["product_sensitive"])
        self.assertTrue(out["industry_sensitive"])

    def test_partial_one_sensitive(self):
        """海外 activated + 变压器 + 食品（行业不敏感）→ partial。"""
        snap = self._snap("变压器", "食品饮料")
        out = runner._compute_tariff_vulnerability(snap, {"status": "activated", "pct": 40})
        self.assertEqual(out["level"], "partial")

    def test_low_neither_sensitive(self):
        """海外 activated + 服装 + 纺织（均不敏感）→ low。"""
        snap = self._snap("服装", "纺织")
        out = runner._compute_tariff_vulnerability(snap, {"status": "activated", "pct": 50})
        self.assertEqual(out["level"], "low")

    def test_none_domestic_only(self):
        """海外 domestic_only → none（无敞口无关税脆弱性）。"""
        snap = self._snap("变压器", "电力设备")
        out = runner._compute_tariff_vulnerability(snap, {"status": "domestic_only", "pct": None})
        self.assertEqual(out["level"], "none")

    def test_none_underivable(self):
        """海外 underivable_geo_vacuum → none（不可得，不强制）。"""
        snap = self._snap("变压器", "电力设备")
        out = runner._compute_tariff_vulnerability(snap, {"status": "underivable_geo_vacuum", "pct": None})
        self.assertEqual(out["level"], "none")

    def test_fatal_real_tebian_scan_all(self):
        """特变真实 case：top1='电气设备产品'(变压器 2024H2 并入) 非'变压器'关键词，
        旧 top1-only + 旧词表 → 漏判 false-negative；全表扫描 + 电气设备族词表 → fatal。"""
        snap = _snap_seg(product=[
            {"name": "电气设备产品", "revenue_ratio": 0.275, "revenue": 267},
            {"name": "煤炭产品", "revenue_ratio": 0.174, "revenue": 170},
            {"name": "电线电缆产品", "revenue_ratio": 0.160, "revenue": 156},
            {"name": "新能源产品及工程", "revenue_ratio": 0.139, "revenue": 135},
            {"name": "输变电成套工程", "revenue_ratio": 0.051, "revenue": 49},
        ]) | {"s55_industry": {"data": {"industry": {"industry_name": "电力设备"}}}}
        out = runner._compute_tariff_vulnerability(snap, {"status": "activated", "pct": 13})
        self.assertEqual(out["level"], "fatal")
        self.assertTrue(out["product_sensitive"])
        self.assertTrue(out["industry_sensitive"])
        names = {p["name"] for p in out["sensitive_products"]}
        self.assertIn("电气设备产品", names)     # 变压器并入，电气设备族命中
        self.assertIn("输变电成套工程", names)    # 输变电族命中
        self.assertIn("电线电缆产品", names)      # 电缆命中
        self.assertNotIn("煤炭产品", names)       # 非敏感不命中
        self.assertNotIn("新能源产品及工程", names)  # 新能源过宽，不入词表（光伏/锂电才入）

    def test_scan_all_catches_non_top1(self):
        """top1 非敏感、#2 出口敏感 → 全表扫描仍 prod_sens=True（top1-only 会漏判）。"""
        snap = _snap_seg(product=[
            {"name": "动力煤", "revenue_ratio": 0.60, "revenue": 600},
            {"name": "光伏组件", "revenue_ratio": 0.20, "revenue": 200},
        ]) | {"s55_industry": {"data": {"industry": {"industry_name": "电力设备"}}}}
        out = runner._compute_tariff_vulnerability(snap, {"status": "activated", "pct": 30})
        self.assertTrue(out["product_sensitive"])
        self.assertEqual(out["level"], "fatal")
        self.assertEqual(out["sensitive_products"][0]["name"], "光伏组件")

    def test_steel_industry_partial(self):
        """宝钢 case：产品维=收入性质(销售商品,无钢材名) → prod_sens=False，但 s55=钢铁(制裁敏感)
        + 海外 activated → partial。验证「钢铁」入制裁表后钢铁出口商不再漏判（Section 232）。"""
        snap = _snap_seg(product=[
            {"name": "销售商品", "revenue_ratio": 0.969, "revenue": 969},
            {"name": "提供劳务", "revenue_ratio": 0.018, "revenue": 18},
        ]) | {"s55_industry": {"data": {"industry": {"industry_name": "钢铁"}}}}
        out = runner._compute_tariff_vulnerability(snap, {"status": "activated", "pct": 13.9})
        self.assertFalse(out["product_sensitive"])   # 收入性质产品，无钢材关键词
        self.assertTrue(out["industry_sensitive"])    # 钢铁 ∈ 制裁表
        self.assertEqual(out["level"], "partial")


# ============================================================
# ⑥ _compute_product_industry_alignment（4 象限 + underivable）
# ============================================================
class ProductIndustryAlignmentTest(unittest.TestCase):

    def _snap(self, margin, change_pct):
        return _snap_seg(product=[{"name": "P1", "revenue": 100, "gross_margin": margin}]) \
            | {"s55_industry": {"data": {"momentum": {"change_pct": change_pct}}}}

    def test_extendable(self):
        """高毛利(40) × 上行(+5) → extendable（可外推）。"""
        out = runner._compute_product_industry_alignment(self._snap(40, 5))
        self.assertEqual(out["quadrant"], "extendable")
        self.assertEqual(out["status"], "ok")

    def test_margin_erosion(self):
        """高毛利(40) × 下行(-5) → margin_erosion（毛利侵蚀）。"""
        self.assertEqual(runner._compute_product_industry_alignment(self._snap(40, -5))["quadrant"],
                         "margin_erosion")

    def test_volume_compensates(self):
        """低毛利(20) × 上行(+5) → volume_compensates（量补价）。"""
        self.assertEqual(runner._compute_product_industry_alignment(self._snap(20, 5))["quadrant"],
                         "volume_compensates")

    def test_double_pressure(self):
        """低毛利(20) × 下行(-5) → double_pressure（双重承压，高危）。"""
        self.assertEqual(runner._compute_product_industry_alignment(self._snap(20, -5))["quadrant"],
                         "double_pressure")

    def test_underivable_missing_margin(self):
        """缺毛利率 → underivable（不臆测象限）。"""
        snap = _snap_seg(product=[{"name": "P1", "revenue": 100}]) \
            | {"s55_industry": {"data": {"momentum": {"change_pct": 5}}}}
        out = runner._compute_product_industry_alignment(snap)
        self.assertEqual(out["status"], "underivable")

    def test_underivable_missing_momentum(self):
        """缺行业动量 → underivable。"""
        snap = _snap_seg(product=[{"name": "P1", "revenue": 100, "gross_margin": 40}])
        self.assertEqual(runner._compute_product_industry_alignment(snap)["status"], "underivable")


# ============================================================
# ⑦ _cr1_from_revenue
# ============================================================
class CR1Test(unittest.TestCase):

    def test_basic(self):
        self.assertAlmostEqual(runner._cr1_from_revenue([{"revenue": 80}, {"revenue": 20}]), 0.8, places=3)

    def test_empty_none(self):
        self.assertIsNone(runner._cr1_from_revenue([]))
        self.assertIsNone(runner._cr1_from_revenue([{"revenue": "N/A"}]))

    def test_ignores_nonpositive(self):
        self.assertAlmostEqual(runner._cr1_from_revenue([{"revenue": 60}, {"revenue": 0}, {"revenue": -5}]),
                               1.0, places=3)


# ============================================================
# ⑧ gate G34/G35/G36（三维对称）+ G17（tariff）+ G22（segment）
# ============================================================
class DimensionGateTest(unittest.TestCase):

    def _snap_qm(self, status):
        return {"_quality_markers": {"segment_product": {"status": status},
                                     "segment_industry": {"status": status},
                                     "segment_geo": {"status": status}}}

    def test_g34_36_pass_valid_states(self):
        for st in ("disclosed_ok", "not_disclosed", "stale_disclosure", "partial"):
            s = self._snap_qm(st)
            self.assertTrue(g.check_g34("", s), f"G34 {st} 应 PASS")
            self.assertTrue(g.check_g35("", s), f"G35 {st} 应 PASS")
            self.assertTrue(g.check_g36("", s), f"G36 {st} 应 PASS")

    def test_g34_36_fail_failed_states(self):
        for st in ("fetch_failed", "degraded"):
            s = self._snap_qm(st)
            self.assertFalse(g.check_g34("", s))
            self.assertFalse(g.check_g35("", s))
            self.assertFalse(g.check_g36("", s))

    def test_g34_36_fail_missing_marker(self):
        s = {"_quality_markers": {}}
        self.assertFalse(g.check_g34("", s))

    def test_g17_no_vulnerability_pass(self):
        """tariff_vulnerability level∈{low,none} → 放行（空报告也 PASS）。"""
        for lvl in ("low", "none"):
            s = {"computed_metrics": {"tariff_vulnerability": {"level": lvl}}}
            self.assertTrue(g.check_g17("", s), f"level={lvl} 应放行")

    def test_g17_fatal_requires_risk_and_haircut(self):
        """fatal + 空报告 → FAIL；fatal + 风险行+折让 → PASS。"""
        s = {"computed_metrics": {"tariff_vulnerability": {"level": "fatal"}}}
        self.assertFalse(g.check_g17("", s))
        rep = "关税风险：海外40%。估值折让 -15%~-25%。"
        self.assertTrue(g.check_g17(rep, s))

    def test_g22_no_disclosed_dim_pass(self):
        """无 disclosed 维（招行无行业）→ 放行（不强制脑补）。"""
        s = {"s1_financial": {"data": {"segment_composition": {"dimension_status": {
            "product": {"status": "not_disclosed"},
            "industry": {"status": "fetch_failed"}}}}}}
        self.assertTrue(g.check_g22("", s))

    def test_g22_disclosed_requires_src(self):
        """disclosed 维须含 segment_composition [src:]（防橡皮章）。"""
        s = {"s1_financial": {"data": {"segment_composition": {"dimension_status": {
            "product": {"status": "disclosed_ok"}}}}}}
        self.assertFalse(g.check_g22("分业务表（无溯源）", s))
        rep = "分产品表 [src: snapshot.s1_financial.data.segment_composition.product]"
        self.assertTrue(g.check_g22(rep, s))


if __name__ == "__main__":
    unittest.main(verbosity=2)
