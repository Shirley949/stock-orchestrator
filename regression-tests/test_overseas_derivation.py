#!/usr/bin/env python3
"""
test_overseas_derivation.py —— 海外敞口派生单测（G17 数据层标记）

直接喂 `_compute_overseas_exposure`（financial-data-routing/runner.py）各种 snapshot，
断言 has_overseas_exposure / reported_overseas_pct 的派生逻辑：
  - segment_composition.geo 单源（SEGMENTSV，name/revenue 字段）
  - 海外关键词：境外/海外/国外/出口
  - 阈值严格 >10% 才置 True
  - 缺数据/非数字/纯国内 → (None, None)，绝不抛错

pact 化：__file__ 相对定位 runner.py，零网络、零外部文件依赖（geo payload 内联）。
运行：python3 test_overseas_derivation.py  或经 run_regression.sh 串联。
"""
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROUTING = _HERE.parent.parent / "financial-data-routing"   # stock-analysis/financial-data-routing
import sys
sys.path.insert(0, str(_ROUTING))

from runner import _compute_overseas_exposure as _derive


def _snap_geo(rows):
    """构造 snapshot：geo 行放 s1_financial.data.segment_composition.geo（name/revenue 字段）。"""
    return {"s1_financial": {"data": {"segment_composition": {"geo": rows}}}}


class OverseasDerivationTest(unittest.TestCase):

    def test_002415_overseas_37pct_activates(self):
        """002415 海康：境内58.2B + 境外34.3B = 37.06% > 10% → (True, 37.06)。"""
        snap = _snap_geo([
            {"name": "境内", "revenue": "58221682972.42"},
            {"name": "境外", "revenue": "34286113097.52"},
        ])
        flag, pct = _derive(snap)
        self.assertIs(flag, True)
        self.assertAlmostEqual(pct, 37.06, places=2)

    def test_600519_overseas_2pct_not_activated(self):
        """600519 茅台：国内1639B + 国外4.85B = 2.87% < 10% → (None, None)（flag 不置）。"""
        snap = _snap_geo([
            {"name": "国内", "revenue": 163924442864.97},
            {"name": "国外", "revenue": 4850142322.68},
        ])
        flag, pct = _derive(snap)
        self.assertIsNone(flag)              # <10% 不激活
        self.assertAlmostEqual(pct, 2.87, places=2)   # pct 仍返回（透明，m25 可参考）

    def test_domestic_only_no_overseas_kw(self):
        """纯国内地区名（华东/华南/华北，无海外关键词）→ (None, None)。"""
        snap = _snap_geo([
            {"name": "华东地区", "revenue": "12737286793.3"},
            {"name": "华南地区", "revenue": "5044103118.72"},
        ])
        flag, pct = _derive(snap)
        self.assertIsNone(flag)
        self.assertIsNone(pct)

    def test_600893_overseas_subthreshold(self):
        """600893：境内销售/境外销售，境外 4.27% < 10% → (None, None)。"""
        snap = _snap_geo([
            {"name": "境内销售", "revenue": 43708267610.78},
            {"name": "境外销售", "revenue": 1950520200.78},
        ])
        flag, pct = _derive(snap)
        self.assertIsNone(flag)

    def test_garbage_safe_degradation(self):
        """601088 类垃圾（传统中文/资产负债字段混入 geo，无海外关键词）→ (None, None)。"""
        snap = _snap_geo([
            {"name": "分部資產總額分部負債總額", "revenue": "4.0"},
            {"name": "清遠電力 廣東福建立能源", "revenue": "1.0"},
        ])
        flag, pct = _derive(snap)
        self.assertIsNone(flag)
        self.assertIsNone(pct)

    def test_empty_snapshot(self):
        """空 snapshot（mode B 无 s1）→ (None, None)，不抛错。"""
        flag, pct = _derive({})
        self.assertIsNone(flag)
        self.assertIsNone(pct)

    def test_non_numeric_revenue_degrades(self):
        """境外行 revenue 非数字（'N/A'）→ 该行不计入 total，无其他有效数据 → (None, None)。"""
        snap = _snap_geo([{"name": "境外", "revenue": "N/A"}])
        flag, pct = _derive(snap)
        self.assertIsNone(flag)
        self.assertIsNone(pct)

    def test_boundary_exactly_10pct_not_activated(self):
        """边界：境外恰好 10.0%（境外=10/总=100）→ 严格 >10 不激活 → flag=None（pct=10.0 返回）。"""
        snap = _snap_geo([
            {"name": "境内", "revenue": 90},
            {"name": "境外", "revenue": 10},
        ])
        flag, pct = _derive(snap)
        self.assertIsNone(flag)              # 严格 >10，等于 10 不激活
        self.assertAlmostEqual(pct, 10.0, places=1)

    def test_seg_geo_primary(self):
        """segment_composition.geo 含境外行 → 按其占比派生（SEGMENTSV 单源）。"""
        snap = _snap_geo([
            {"name": "境内", "revenue": 60},
            {"name": "境外", "revenue": 40},
        ])
        flag, pct = _derive(snap)
        self.assertIs(flag, True)   # 40% > 10%
        self.assertAlmostEqual(pct, 40.0, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
