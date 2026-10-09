#!/usr/bin/env python3
"""exec_shell 视图 user_position 渲染契约测试（2026-10-08）。

背景（300502 实证，同族第 3 例）：execution_shell 子树 v3.3+T11 批加入 user_position
（personal overlay，execution_shell.py:522），b-trade-sheet §1/§7 写明「你的持仓」行
消费合同，但 _print_exec_shell 漏同步渲染行 → 视图缺口，写作侧被迫 --raw 绕过；
且持仓行无 gate 执法，漏渲染=报告静默缺失。同族前例：webfindings_stale /
webfindings_key_contract（均 2026-10-06 landed）。

执法面：视图渲染两极断言（引擎修后防族复发）。
两极：有仓态 5 字段全出 / 空仓态（execution_shell.py 无 --position 形状）+ 无键旧快照兜底。
离线纯函数，零网络。
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import snapshot_view as sv  # noqa: E402


def _mk_shell(user_position=None, drop_key=False):
    v = {"status": "ok", "rules_id": "v3.3+T11 2026-10-06",
         "today": {"action": "NONE", "end_position": "空仓", "trigger": "t"},
         "orders": [], "pfd": {"ratio_5d": -0.37, "as_of_date": "2026-09-30",
                               "th": -0.1, "status": "ok"},
         "comparison": {"v33_t11": {"net_pnl": 0, "trades_n": 0, "end_position": "空仓"},
                        "v31_ref": {"net_pnl": 0, "end_position": "空仓"}},
         "fold": {"ledger_rows": 1, "kline_start_v33_t11": "ledger首日"},
         "context_panel": {"news_n": 0, "announcements_n": 0, "xq_voice_n": 0}}
    if not drop_key:
        v["user_position"] = user_position
    return v


def _render(v):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sv._print_exec_shell(v)
    return buf.getvalue()


class TestExecShellUserPosition(unittest.TestCase):
    def test_01_held_position_full_fields(self):
        """正例：有仓态 → position/action/reason/ladder/atr_stop 全字段照抄渲染。"""
        up = {"weight": "personal_overlay", "not_in_state_machine": True,
              "last_close": 389.0, "position": "100股 @成本393.1", "cost": 393.1,
              "shares": 100, "pnl_pct": -1.04, "ladder": 361.652, "atr_stop": 346.54,
              "action": "HOLD", "reason": "现价 389.00 在你的梯子 361.65 与 ATR 止损 346.54 上方 → 持有",
              "watch_spec": None}
        out = _render(_mk_shell(up))
        self.assertIn("你的持仓（personal overlay，不进状态机）", out)
        self.assertIn("100股 @成本393.1", out)
        self.assertIn("动作 HOLD", out)
        self.assertIn("你的梯子 361.65 / ATR止损 346.54", out)
        self.assertIn("持有", out)

    def test_02_no_position_watch_spec_band(self):
        """反例极：空仓态（execution_shell.py 无 --position 形状）→ 空仓 + WAIT + spec_band。"""
        up = {"weight": "personal_overlay", "not_in_state_machine": True,
              "last_close": 389.0, "position": "空仓（未提供持仓）",
              "watch": {"spec_band": "等回踩 361.65 带", "atr_stop": 346.54},
              "action": "WAIT"}
        out = _render(_mk_shell(up))
        self.assertIn("空仓（未提供持仓）", out)
        self.assertIn("动作 WAIT", out)
        self.assertIn("等回踩 361.65 带", out)

    def test_03_missing_key_fallback(self):
        """反例极：旧快照无 user_position 键 → 兜底行，不崩。"""
        out = _render(_mk_shell(drop_key=True))
        self.assertIn("未提供仓位", out)

    def test_04_invalid_position_no_crash(self):
        """反例极：position='invalid'（成本解析失败形状）→ 渲染不崩。"""
        up = {"weight": "personal_overlay", "not_in_state_machine": True,
              "last_close": 389.0, "position": "invalid", "action": "WAIT"}
        out = _render(_mk_shell(up))
        self.assertIn("invalid", out)
        self.assertIn("动作 WAIT", out)

    def test_05_view_registered(self):
        """视图注册仍在：exec_shell 挂 s4_technical.data.execution_shell。"""
        self.assertEqual(sv.VIEW_PATHS["exec_shell"], ("s4_technical", "data", "execution_shell"))


if __name__ == "__main__":
    unittest.main()
