#!/usr/bin/env python3
"""G16 冲突扫描数字主体归因回归测试（D′ 修复 2026-08-27）。

背景：publish 稿剥 [src:] 后，合同负债核对行常混入他主体数字（在手订单 8 亿、净现金 35 亿、
经营现金流 3.2 亿），旧引擎对该行所有 X亿 一律与快照 CL 对比（ratio>1.5 即 FAIL）→ 6 份真实
publish 稿误伤（沃尔核材/瑞华泰/蓝特/长光华芯/凯盛/芯碁微装）。修复：数字归行内**前方最近**
主体 token（中文财务行文主体在数字前），前方无主体才看后方；最近者属 CL 族或无主体 → 保守执法。

每判例 = 待测行 + 统一 grounding 行（带 src + 核对词 + 真值 4.93），使 (b)(c) 腿恒满足，
verdict 完全由待测行的冲突扫描决定（单变量隔离）。
"""
import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts', 'lib'))
from gate_definitions import check_g16

SNAP = {"s1_financial": {"data": {"balance_sheet": {"data": [{"合同负债": 493000000.0}]}}}}  # 4.93 亿
GROUND = "合同负债核对：最新期 4.93 亿元，与快照一致 [src: snapshot.s1_financial.data.balance_sheet.data]。"


def _rep(line):
    return line + "\n" + GROUND


class CheckG16SubjectAttribution(unittest.TestCase):
    def test_order_and_netcash_exemp(self):
        """① 688630 实案形态：订单 8 亿 / 净现金 35 亿 与 CL 同行 → 前方归因豁免 PASS（旧 FAIL）。"""
        self.assertTrue(check_g16(_rep("合同负债核对：在手订单破 8 亿、净现金 35 亿，与快照一致。"), SNAP))

    def test_semicolon_netcash_exemp(self):
        """② 净现金 35 亿；合同负债 4.93 亿 → 35 归因净现金 PASS（旧 FAIL）。"""
        self.assertTrue(check_g16(_rep("净现金 35 亿；合同负债 4.93 亿。"), SNAP))

    def test_semicolon_cashflow_exemp(self):
        """③ 分号句：现金流量净额 3.2 亿；合同负债 4.93 亿 → 3.2 归因现金（前方优先，不吃后方 CL）PASS。"""
        self.assertTrue(check_g16(_rep("经营活动现金流量净额 3.2 亿；合同负债 4.93 亿。"), SNAP))

    def test_postposition_true_value_pass(self):
        """④ 后置形态：4.93 亿为合同负债（真值无冲突）→ PASS。"""
        self.assertTrue(check_g16(_rep("本期 4.93 亿为合同负债，另有订单 8 亿。"), SNAP))

    def test_cl_attributed_fabrication_fails(self):
        """⑤ 编造照抓：前方最近主体=合同负债 的 12 亿 → FAIL（保守执法保持）。"""
        self.assertFalse(check_g16(_rep("合同负债核对：最新期 12 亿元，与快照一致。"), SNAP))

    def test_postposition_fabrication_fails(self):
        """⑥ 后置编造照抓：12 亿为合同负债（后方兜底=cl）→ FAIL。"""
        self.assertFalse(check_g16(_rep("本期 12 亿为合同负债，另有订单 8 亿。"), SNAP))

    def test_dual_family_residual_fails(self):
        """⑦ 双族同现残余：订单是合同负债两倍达 12 亿——12 前方最近=合同负债 → FAIL（宁紧勿松，known-limit）。"""
        self.assertFalse(check_g16(_rep("订单金额是合同负债两倍，达 12 亿。"), SNAP))

    def test_src_line_skip_unchanged(self):
        """⑧ [src:] 行整行跳过（现有豁免不动）→ PASS。"""
        self.assertTrue(check_g16(
            _rep("合同负债核对：最新期 12 亿元，与快照一致 [src: snapshot.s1_financial]。"), SNAP))


if __name__ == "__main__":
    unittest.main()
