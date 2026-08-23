#!/usr/bin/env python3
"""snapshot_view --field 外科投影 + footer/截断指针 实现验收（Fix C，2026-08-23）。

为什么存在：--field 是「单字段直出」白名单 flag（非 DSL），其六条语义此后由本脚本
判定，不再 LLM 手跑重验——①字段缺失显式报错+前10可用字段（杀静默 None 假阳）；
②行表→全期单列「日期: 值」（data/data_full 双键兜底=家规）；③长列表双帽
（_any_render 10条帽 + FIELD_CAP 4000c 硬截断，remind_records x97 裸 dump 70K）；
④dict 字段值过 capped renderer；⑤空列表三态「0 行（真空）」；⑥.N 含点拒绝。
另锁 C1 footer（balance 8期合同负债 + 仅前4期指针）/ _print_period_table 截断指针 /
C2 timeline 子层指针。

跑：python3 test_snapshot_view_field.py（离线合成快照，<2s）
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SV = os.path.join(HERE, "..", "scripts", "snapshot_view.py")


def _mk_dates(n):
    """n 期 desc 日期（2026-03-31 起逐季倒退）。"""
    out, y, q = [], 2026, 1
    for _ in range(n):
        out.append(f"{y}-{q * 3:02d}-30")
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out


def _mk_snap():
    dates12 = _mk_dates(12)
    bs_rows = [{"报告日": d, "合同负债": 1_000_000.0 + i * 50_000, "资产合计": 9.9}
               for i, d in enumerate(dates12)]
    # 炸弹字段：97 条 × 26 键 × 长标量 → 裸 dump ≫ 10条帽 7K ≫ 4000c 硬截断
    bomb = [{"k" + str(j).zfill(2): "x" * 250 for j in range(26)} for _ in range(97)]
    return {
        "s1_financial": {"data": {
            "balance_sheet": {
                "status": "ok", "data": bs_rows,
                "report_view": {
                    "view": "balance_sheet", "status": "ok",
                    "dates": dates12[:4], "unit": "亿元（原始元值已换算）",
                    "matrix": {"货币资金": [1.0, 2.0, 3.0, 4.0],
                               "合同负债": [0.10, 0.15, 0.12, 0.11]},
                    "missing_fields": [], "latest_period": {},
                }},
            "only_full": {"status": "ok",
                          "data_full": [{"报告日": "2026-03-30", "X": 1.5}]},  # 仅 data_full
            "income_statement": {
                "status": "ok",
                "report_view": {
                    "view": "income_statement", "status": "ok", "periods": 15,
                    "data": [{"报告日": d, "revenue": 100.0 + i} for i, d in enumerate(_mk_dates(15))],
                    "missing_fields": [],
                }},
        }},
        "s5_events": {"data": {"risk_signals": {
            "status": "ok", "remind_records": bomb,
            "processed": {"status": "ok", "programs": [],
                          "report_view": {"status": "ok", "summary": "s",
                                          "buy_sell_pressure": {}, "shareholder_dynamics": {}}},
        }}},
        "s3_fund_flow": {"data": {"fund_flow": {
            "items": [{"name": "特大单", "in": 0.7}, {"name": "大单", "in": 0.1}]}}},
        "classification": {"primary_type": "成长股"},
    }


def _run(snap_path, *args):
    return subprocess.run([sys.executable, SV, snap_path] + list(args),
                          capture_output=True, text=True, timeout=30)


class FieldProjectionTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.snap = os.path.join(self.td.name, "snap.json")
        with open(self.snap, "w", encoding="utf-8") as fh:
            json.dump(_mk_snap(), fh, ensure_ascii=False)

    def tearDown(self):
        self.td.cleanup()

    def test_rowtable_full_column(self):
        """②行表 → 全期单列 desc（12 行，首行=最新期）。"""
        r = _run(self.snap, "--raw", "s1_financial.data.balance_sheet", "--field", "合同负债")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(len(lines), 13)                       # header + 12 期
        self.assertIn("2026-03-30: 1,000,000", lines[1])       # rows[0]=最新
        self.assertIn("2023-06-30", lines[-1])                 # 12 期到底

    def test_missing_field_explicit_error(self):
        """①字段缺失 → exit 1 + 前10可用字段（杀静默 None）。"""
        r = _run(self.snap, "--raw", "s1_financial.data.balance_sheet", "--field", "不存在字段")
        self.assertEqual(r.returncode, 1)
        self.assertIn("可用字段（前10）", r.stderr)
        self.assertIn("报告日", r.stderr)
        self.assertNotIn("--raw", r.stdout)                    # 报错路径不打印 header

    def test_data_full_fallback(self):
        """⑤data_full 兜底：仅含 data_full 的 section 照常投影（家规双键）。"""
        r = _run(self.snap, "--raw", "s1_financial.data.only_full", "--field", "X")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2026-03-30: 1.5", r.stdout)

    def test_empty_list_three_state(self):
        """⑥空列表三态：dict 字段空 → 0 行（真空）；section data 空 → 真空(data)。"""
        r = _run(self.snap, "--raw", "s5_events.data.risk_signals.processed", "--field", "programs")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 行（真空）", r.stdout)
        snap = json.load(open(self.snap, encoding="utf-8"))
        snap["s5_events"]["data"]["risk_signals"]["processed"]["empty_sec"] = {"data": []}
        with open(self.snap, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False)
        r2 = _run(self.snap, "--raw", "s5_events.data.risk_signals.processed.empty_sec", "--field", "X")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("0 行（真空：data/data_full 为空）", r2.stdout)

    def test_dict_value_capped_render(self):
        """④dict/列表字段值过 _any_render capped renderer（items → [0]… 键树）。"""
        r = _run(self.snap, "--raw", "s3_fund_flow.data.fund_flow", "--field", "items")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[0] (dict", r.stdout)
        self.assertIn("name = 特大单", r.stdout)

    def test_bomb_double_cap(self):
        """③长列表双帽：97×26 键炸弹（裸 dump ~54K）→ 10条帽 + ≤4200c 硬截断 + .N 指路。"""
        r = _run(self.snap, "--raw", "s5_events.data.risk_signals", "--field", "remind_records")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLessEqual(len(r.stdout), 4200)              # FIELD_CAP 4000 + header/提示行
        self.assertIn("截断；单条 → --raw s5_events.data.risk_signals.remind_records.N", r.stdout)
        self.assertNotIn("[10]", r.stdout)                     # 10 条帽生效（只到 [9]）

    def test_dot_n_rejected(self):
        """⑥补.N 含点拒绝：--field 不接受嵌套/索引，指路 --raw <path>.N。"""
        r = _run(self.snap, "--raw", "s5_events.data.risk_signals", "--field", "remind_records.N")
        self.assertEqual(r.returncode, 1)
        self.assertIn("不支持", r.stderr)
        self.assertIn("--raw s5_events.data.risk_signals.remind_records.N", r.stderr)

    def test_scalar_direct(self):
        """标量直印（classification.primary_type）。"""
        r = _run(self.snap, "--raw", "classification", "--field", "primary_type")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("成长股", r.stdout)


class FooterPointerTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.snap = os.path.join(self.td.name, "snap.json")
        with open(self.snap, "w", encoding="utf-8") as fh:
            json.dump(_mk_snap(), fh, ensure_ascii=False)

    def tearDown(self):
        self.td.cleanup()

    def test_balance_footer_and_pointer(self):
        """C1：balance 尾部 8 期合同负债 footer + 仅前4期 --field 指针。"""
        r = _run(self.snap, "balance")
        self.assertEqual(r.returncode, 0, r.stderr)
        tail = "\n".join(r.stdout.strip().splitlines()[-2:])
        self.assertIn("合同负债 8期(万):", tail)
        self.assertIn("26-03-30:100", tail)                    # 元→万换算（_fmt 去尾零）+ YY 压缩日期
        self.assertIn("⚠️ 仅前4期（共12期）", tail)
        self.assertIn("--raw s1_financial.data.balance_sheet --field 合同负债", tail)

    def test_period_table_truncation_pointer(self):
        """C1：_print_period_table 截断指针（15 期视图只显 12 → 指针指 --field）。"""
        r = _run(self.snap, "income")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("⚠️ 仅前12期（共15期）；单字段全期 → --raw s1_financial.data.income_statement --field <字段名>",
                      r.stdout)

    def test_timeline_sublayer_pointer(self):
        """C2：timeline 尾部 programs 子层指针。"""
        r = _run(self.snap, "timeline")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--raw s5_events.data.risk_signals.processed --field programs",
                      r.stdout.strip().splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
