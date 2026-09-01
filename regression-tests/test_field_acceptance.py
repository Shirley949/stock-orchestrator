#!/usr/bin/env python3
"""test_field_acceptance — C-4 现场验收簿记测试（裁决A，2026-09-01）。

四极：
  1. closed_pass —— 暴露达标 + 零复现 → 自动关闭
  2. 展期一次 → 降级关闭 —— 窗口耗尽暴露不足：先 +2 展期，再耗尽 → closed_downgraded
  3. 复现阻断 —— FAIL reasons 命中 match → recurred>0 不关闭（🔴 回归提示）
  4. warn 翻转 + 硬断言执法 —— 当窗零 bool_return_warn → flipped=true；
     verify_gates 见翻转位 → bool_return_hard + action_required 置顶（verdict 中性）

方向局限（验收语义）：现场只证假阳性方向；假阴性由 corpus+归档重放守（见簿记文件头）。
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "scripts"))
sys.path.insert(0, str(_HERE.parent / "scripts" / "lib"))

import trap_ledger_scan as tls  # noqa: E402
from trap_ledger import load_acceptance, save_acceptance  # noqa: E402

_LEDGER = [
    {"signature": "G63#percentile_variant:bai_percentile_leak", "gate": "G63",
     "match": "百分位", "count": 0},
    {"signature": "G30#5:negation_context_v2", "gate": "G30", "match": "主推荐", "count": 0},
    {"signature": "G30#1:synonym_dingzeng", "gate": "G30", "match": "定增", "count": 0},
]


def _state(windows=2, thresholds=(3, 2, 1)):
    sigs = {
        "G63#percentile_variant:bai_percentile_leak": _sig("percentile", windows, thresholds[0]),
        "G30#5:negation_context_v2": _sig("negation", windows, thresholds[1]),
        "G30#1:synonym_dingzeng": _sig("dingzeng", windows, thresholds[2]),
    }
    return {"seen_through": None, "signatures": sigs,
            "warn_upgrade": {"zero_hit_windows": 0, "flipped": False}}


def _sig(probe, window_left, threshold):
    return {"probe": probe, "window_left": window_left, "threshold": threshold,
            "exposed": 0, "recurred": 0, "extended": False, "status": "open"}


def _mk_window(root: Path, date: str, report: str, fails=(), warn=None):
    """造 1 份 sidecar + 兄弟报告。fails=[(gate, reasons_str)]；warn=bool_return_warn 值。"""
    d = root / date
    d.mkdir(parents=True, exist_ok=True)
    (d / "r.md").write_text(report, encoding="utf-8")
    doc = {"timestamp": f"{date}T09:00:00+00:00",
           "details": [{"gate": g, "status": "fail", "reasons": [rs]} for g, rs in fails]}
    if warn is not None:
        doc["bool_return_warn"] = warn
    (d / "r.verified.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


class TestFieldAcceptance(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "corpus"
        self.root.mkdir()
        self.state_path = Path(self.tmp.name) / "acc.yaml"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, state):
        lines = tls.field_acceptance(self.root, _LEDGER, state)
        return lines, state

    def test_pole1_closed_pass(self):
        """暴露达标+零复现 → closed_pass；同窗幂等（重复跑不重复计）。"""
        rpt = "换手率 94 百分位历史低位，估值分位 20 分位；另处 3 分位。"
        _mk_window(self.root, "2026-09-02", rpt)
        st = _state()
        lines, st = self._run(copy.deepcopy(st))
        g63 = st["signatures"]["G63#percentile_variant:bai_percentile_leak"]
        self.assertEqual(g63["status"], "closed_pass")
        self.assertGreaterEqual(g63["exposed"], 3)          # 3 处分位形态 ≥ 阈值 3
        self.assertEqual(g63["recurred"], 0)
        self.assertTrue(any("closed_pass" in ln for ln in lines))
        # 幂等：同窗再跑（seen_through 已推进）不新增
        lines2, st2 = self._run(st)
        self.assertTrue(any("无新 sidecar" in ln for ln in lines2))
        self.assertEqual(st2["signatures"]["G63#percentile_variant:bai_percentile_leak"]["exposed"],
                         g63["exposed"])

    def test_pole2_extend_then_downgrade(self):
        """窗口耗尽暴露不足 → 展期一次(+2)；再耗尽 → closed_downgraded。"""
        _mk_window(self.root, "2026-09-02", "全文无任何触发形态。")
        st = _state()
        lines, st = self._run(st)                            # 窗1（无暴露）
        dz = st["signatures"]["G30#1:synonym_dingzeng"]
        self.assertEqual(dz["status"], "open")
        self.assertEqual(dz["window_left"], 1)
        _mk_window(self.root, "2026-09-03", "仍无形态。")
        _, st = self._run(st)                                # 窗2 → 耗尽 → 展期
        dz = st["signatures"]["G30#1:synonym_dingzeng"]
        self.assertTrue(dz["extended"])
        self.assertEqual(dz["window_left"], 2)               # 0 + 2
        _mk_window(self.root, "2026-09-04", "仍无。")
        _, st = self._run(st)                                # 窗3
        _mk_window(self.root, "2026-09-05", "仍无。")
        _, st = self._run(st)                                # 窗4 → 再耗尽 → 降级
        dz = st["signatures"]["G30#1:synonym_dingzeng"]
        self.assertEqual(dz["status"], "closed_downgraded")

    def test_pole3_recurrence_blocks_close(self):
        """FAIL reasons 命中 match → recurred>0、不关闭、🔴 提示（引擎已 landed=回归）。"""
        _mk_window(self.root, "2026-09-02", "报告正文有定增措辞一次。",
                   fails=[("G30", "致命事件 233(增发) 未在时间线 surface——含定增措辞")])
        st = _state()
        lines, st = self._run(st)
        dz = st["signatures"]["G30#1:synonym_dingzeng"]
        self.assertGreaterEqual(dz["exposed"], 1)
        self.assertGreaterEqual(dz["recurred"], 1)
        self.assertEqual(dz["status"], "open")               # 复现不关闭
        self.assertTrue(any("🔴" in ln and "回归" in ln for ln in lines))

    def test_pole4_warn_flip_and_hard_enforcement(self):
        """当窗零 bool_return_warn → flipped=true；verify_gates 读翻转位 → 硬断言行
        （verdict 中性：bool 门 FAIL 恒 FAIL，只升 action_required）。"""
        import verify_gates as vg
        _mk_window(self.root, "2026-09-02", "正文无形态", warn=[])
        st = _state()
        lines, st = self._run(st)
        self.assertTrue(st["warn_upgrade"]["flipped"])       # 一轮 cron 零命中即翻
        self.assertTrue(any("flipped=true" in ln for ln in lines))
        # 硬断言执法（隔离注入点，不碰仓库真实状态文件）。
        # 2026-09-01 起 WP1a+WP1b 22 门 lossy 全 GateResult 化，真实夹具（24 门 FAIL）
        # 已无裸 bool-FAIL 火种——机制证明改为注入裸 bool checker（同 test_diag_contract
        # test_bool_return_warn_fires 注入式）；触发器语义不变：bool 门 FAIL 恒 FAIL 只升 action。
        save_acceptance(st, self.state_path)
        old = vg._ACC_OVERRIDE_PATH
        import gate_definitions as gd
        orig_g6 = gd.GATE_CHECKERS.get("G6")
        gd.GATE_CHECKERS["G6"] = lambda r, d: False      # 注入裸 bool FAIL
        vg._ACC_OVERRIDE_PATH = str(self.state_path)
        try:
            res = vg.verify_gates("## 五、估值\n缩量无词表命中", {"s1_financial": {"data": {}}},
                                  "profile_full")
            self.assertTrue(res.get("bool_return_hard"))
            self.assertTrue(any("硬断言" in a for a in res.get("action_required") or []))
        finally:
            vg._ACC_OVERRIDE_PATH = old
            gd.GATE_CHECKERS["G6"] = orig_g6
        # 反极：warn 非空窗不翻转
        _mk_window(self.root, "2026-09-03", "x", warn=["G22"])
        st2 = _state()
        _, st2 = self._run(st2)
        self.assertFalse(st2["warn_upgrade"]["flipped"])
        self.assertEqual(st2["warn_upgrade"]["zero_hit_windows"], 0)

    def test_status_lines_readonly(self):
        """报告模式只读状态行（不落盘不递减）。"""
        st = _state()
        lines = tls.acceptance_status(st)
        self.assertTrue(any("field_acceptance" in ln for ln in lines))
        self.assertTrue(any("warn_upgrade" in ln for ln in lines))
        self.assertEqual(st["signatures"]["G30#1:synonym_dingzeng"]["window_left"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
