#!/usr/bin/env python3
"""token_audit v2/v3 语义自检 fixture：合成微型会话 → 跑表计 → 断言处数/分层/写回/覆盖率。

为什么存在：表计是验收线（纯提取≤5 / 覆盖率>80% / 写回 0 / gate 源码 0）的尺，
尺的语义（去重 · result-only · 挂载前缀机械分层 · 写回目标同一 · v3 外科豁免/
--field 分布/总账行/Bash 侧透明度/错目标告警）此后任何改动都由本脚本判定，
不再需要 LLM 手跑模拟重验（2026-08-21 688048 审计重放口径；2026-08-23 v3 扩容）。

跑：python3 test_token_audit.py（无网络，<2s）
所有审计子进程统一带 TOKEN_AUDIT_NO_HISTORY=1 + 隔离 HOME（防污染真环比历史）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.join(HERE, "..", "scripts", "token_audit.py")

# (tool_use_id, command, result_chars)。覆盖 v2 全部分支语义：
CALLS = [
    # 1. CLI 视图调用（any）→ 视图: any，覆盖率分子
    ("t1", "python3 snapshot_view.py /tmp/runner_snapshot_688048.json any governance --depth 1", 500),
    # 2. 手写视图内：链式路径 == 挂载前缀 s1_financial.data.income_statement
    ("t2", 'python3 -c "import json;d=json.load(open(\'/tmp/runner_snapshot_688048.json\'));'
           "print(d['s1_financial']['data']['income_statement'])\"", 300),
    # 3. 手写视图外：computed_metrics（扁平小节，非挂载点）
    ("t3", 'python3 -c "import json;d=json.load(open(\'/tmp/runner_snapshot_688048.json\'));'
           "print(d['computed_metrics'])\"", 200),
    # 4. .jsonl 日志挖掘自匹配 → D2 排除（不计处数）
    ("t4", "python3 -c \"import json;ls=[json.loads(l) for l in open('session.jsonl')];"
           "print([l for l in ls if 'runner_snapshot' in str(l)])\"", 999),
    # 5. verify_gates 自审计命令（含 json.load）→ 既有排除（不计处数）
    ("t5", 'python3 -c "import json;print(len(json.load(open(\'/tmp/runner_snapshot_688048.json\'))))"'
           " && python3 verify_gates.py report.md", 999),
    # 6. 复合命令（view 为主 + 附带 json.load）→ 归「复合」不计手写、不入覆盖率
    ("t6", "python3 snapshot_view.py /tmp/runner_snapshot_688048.json kline "
           '&& python3 -c "import json;json.load(open(\'/tmp/runner_snapshot_688048.json\'))"', 999),
    # 7. 写回：写模式 open 的文件参数命中快照路径（不含 json.load → 不计手写）
    ("t7", 'python3 -c "import json;json.dump({\'a\':1},open(\'/tmp/runner_snapshot_fix.json\',\'w\'))"', 50),
    # 8. 合法生产者 runner（> 重定向非 open( → 不算写回）
    ("t8", "python3 runner.py 688048 A > /tmp/runner_snapshot_688048.json", 50),
    # 9. 跨文件假阳反例：读快照 + 写模式打开报告 md（不是快照）→ 不是写回
    ("t9", 'python3 -c "import json;d=json.load(open(\'/tmp/runner_snapshot_688048.json\'));'
           "open('/tmp/analysis_report.md','w').write(str(d)[:9])\"", 50),
]

# 预期：处数=3（#2 视图内 + #3/#9 视图外；#4/.jsonl、#5/verify_gates、#6/复合 排除）；
# #9 含 json.load+快照引用且无排除词 → 计手写（视图外，无路径字面量保守归外），
# 其写模式 open 的目标是报告 md → 不是写回。#7 只写回不提取。
# 覆盖率 = 500 / (500 + 300+200+50) = 47.6%。
EXPECTED_COUNT = 3
EXPECTED_IN = 1
EXPECTED_OUT = 2
EXPECTED_WRITEBACK = 1


def _build_fixture(path, calls=CALLS, user_text=None):
    with open(path, "w", encoding="utf-8") as fh:
        if user_text is not None:
            fh.write(json.dumps({"type": "user", "message": {
                "content": [{"type": "text", "text": user_text}]}}) + "\n")
        for tid, cmd, res_len in calls:
            fh.write(json.dumps({"type": "assistant", "message": {
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "content": [{"type": "tool_use", "id": tid, "name": "Bash",
                             "input": {"command": cmd}}]}}) + "\n")
            fh.write(json.dumps({"type": "user", "message": {
                "content": [{"type": "tool_result", "tool_use_id": tid,
                             "content": [{"type": "text", "text": "x" * res_len}]}]}}) + "\n")


def _run_audit(fx, out, stock="TEST", no_history=True, home=None):
    """跑审计子进程。默认 NO_HISTORY=1（防污染真环比历史）；home 隔离时另建 env。"""
    env = dict(os.environ)
    env["TOKEN_AUDIT_NO_HISTORY"] = "1" if no_history else "0"
    if home:
        env["HOME"] = home
    return subprocess.run([sys.executable, AUDIT, fx, "--stock", stock, "-o", out],
                          capture_output=True, text=True, timeout=60, env=env)


def _hw_cmd(path_key, surgical=False):
    """视图外手写命令模板（非挂载点路径）。surgical=True 加豁免声明注释。"""
    tag = "  # rule5-surgical" if surgical else ""
    return ('python3 -c "import json;d=json.load(open(\'/tmp/runner_snapshot_688048.json\'));'
            f"print(d['{path_key}'])\"{tag}")


class TokenAuditV2Test(unittest.TestCase):
    def test_v2_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            fx = os.path.join(td, "fixture.jsonl")
            out = os.path.join(td, "out.md")
            _build_fixture(fx)
            r = _run_audit(fx, out)
            self.assertEqual(r.returncode, 0, r.stderr)
            stdout, md = r.stdout, open(out, encoding="utf-8").read()

            # v2 摘要行：处数 / 视图内 / 视图外 / 写回 / 覆盖率（result-only）
            self.assertIn(f"手写提取 {EXPECTED_COUNT} 处（视图内 {EXPECTED_IN} / "
                          f"视图外 {EXPECTED_OUT}）| 写回 {EXPECTED_WRITEBACK} | "
                          f"覆盖率 47.6%", stdout)

            # 版本戳与检查项
            self.assertIn("semantics v2", md)
            self.assertIn("无快照写回", md)          # 期望行存在（此处 ❌，写回=1）
            self.assertIn("1 处 json.dump/open(w/a) 写快照", md)
            # .jsonl / verify_gates / 复合 不计手写：处数=3 已隐含；再钉 .jsonl 排除词
            self.assertNotIn("手写提取（视图内·违规）2 处", md)

            # 跨文件假阳反例（#9）：写回必须仍为 1（写报告 md 不算写快照）
            self.assertIn("| 写回 1 |", stdout)

            # ---- v3 新增行（A1/A2/A4/A5）：additive 断言 ----
            self.assertIn("被分析文件:", stdout)                      # A1 路径打印
            self.assertIn(f"- 被分析文件：`{fx}`", md)
            self.assertIn("gate 源码 Bash 侧访问", md)                # A2 透明度行
            self.assertIn("0 次 / 0c", md)                            #   fixture 无 sed 撞源码
            self.assertIn("- **总取数 = CLI 500 + 手写 550 = 1,050 chars**", md)  # A4 总账
            self.assertIn("--field 外科投影调用 **0 次 / 0 chars**", md)   # A5 分布行
            self.assertIn("外科豁免 0 处", md)                        # A3 豁免桶（空态）

    def test_a1_latest_and_code_mismatch(self):
        """错目标告警：内容自提码 ≠ --stock → stdout+md 双 ⚠️（T2 语义的合成版）。"""
        with tempfile.TemporaryDirectory() as td:
            fx = os.path.join(td, "fixture.jsonl")
            out = os.path.join(td, "out.md")
            # 首条用户文本（caveat 包装）无码 → 第 2 条才有码（v5.1：扫前 5 条）
            _build_fixture(fx, user_text="  # <local-command-caveat> local wrap\n"
                                         "/clear\n帮我分析 688048（第二句才有码）")
            r = _run_audit(fx, out, stock="688048")   # 一致 → 无 mismatch ⚠️
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("疑似错目标", r.stdout)
            md = open(out, encoding="utf-8").read()
            self.assertIn("内容自提股票码：688048（与 --stock 一致 ✓）", md)

            out2 = os.path.join(td, "out2.md")
            r2 = _run_audit(fx, out2, stock="688195")   # 688195 ≠ 内容码 688048
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertIn("内容自提股票码 688048", r2.stdout)
            self.assertIn("疑似错目标", r2.stdout)
            md2 = open(out2, encoding="utf-8").read()
            self.assertIn("疑似错目标审计", md2)

    def test_a3_full_list_and_surgical_exempt(self):
        """手写全列（[:5] 放开）+ 外科豁免正反例 + quota 超额 ⚠️。"""
        with tempfile.TemporaryDirectory() as td:
            # ① 7 处手写（全视图外）→ 全列 7 行（锁 [:5] 不回退）
            fx = os.path.join(td, "fx7.jsonl")
            calls = [(f"h{i}", _hw_cmd(f"section_{i}"), 100 + i) for i in range(7)]
            _build_fixture(fx, calls=calls)
            out = os.path.join(td, "out7.md")
            r = _run_audit(fx, out)
            self.assertEqual(r.returncode, 0, r.stderr)
            md = open(out, encoding="utf-8").read()
            self.assertIn("视图外·建议 any/--field）7 处", md)
            self.assertEqual(md.count("c) `python3 -c"), 7)   # 7 条明细全列

            # ② 2 处声明豁免 + 1 处普通手写 → 豁免桶 2 处、手写只计 1
            fx2 = os.path.join(td, "fxs.jsonl")
            calls2 = [
                ("s1", _hw_cmd("panorama_a", surgical=True), 400),
                ("s2", _hw_cmd("panorama_b", surgical=True), 300),
                ("n1", _hw_cmd("section_x"), 200),
                ("v1", "python3 snapshot_view.py /tmp/runner_snapshot_688048.json income", 500),
            ]
            _build_fixture(fx2, calls=calls2)
            out2 = os.path.join(td, "outs.md")
            r2 = _run_audit(fx2, out2)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            md2 = open(out2, encoding="utf-8").read()
            self.assertIn("外科豁免（# rule5-surgical 声明，quota ≤2）2 处", md2)
            self.assertNotIn("超额", md2)
            self.assertIn("手写提取（视图外·建议 any/--field）1 处", md2)
            # 豁免不计覆盖率分母：500/(500+200)=71.4%
            self.assertIn("覆盖率 71.4%", md2)

            # ③ 3 处声明豁免 → quota 超额 ⚠️
            fx3 = os.path.join(td, "fx3.jsonl")
            calls3 = [(f"s{i}", _hw_cmd(f"pan_{i}", surgical=True), 300) for i in range(3)]
            _build_fixture(fx3, calls=calls3)
            out3 = os.path.join(td, "out3.md")
            r3 = _run_audit(fx3, out3)
            self.assertEqual(r3.returncode, 0, r3.stderr)
            md3 = open(out3, encoding="utf-8").read()
            self.assertIn("3 处 ⚠️ 超额（quota ≤2）", md3)
            self.assertIn("⚠️ 超额", r3.stdout)

    def test_a5_field_distribution(self):
        """--field 调用分布行：含 --field 的 snapshot_view 调用计入、普通调用不计。"""
        with tempfile.TemporaryDirectory() as td:
            fx = os.path.join(td, "fxf.jsonl")
            calls = [
                ("f1", "python3 snapshot_view.py /tmp/runner_snapshot_688048.json "
                       "--raw s1_financial.data.balance_sheet --field 合同负债", 277),
                ("f2", "python3 snapshot_view.py /tmp/runner_snapshot_688048.json "
                       "--raw classification --field primary_type", 3),
                ("v1", "python3 snapshot_view.py /tmp/runner_snapshot_688048.json balance", 2400),
            ]
            _build_fixture(fx, calls=calls)
            out = os.path.join(td, "outf.md")
            r = _run_audit(fx, out)
            self.assertEqual(r.returncode, 0, r.stderr)
            md = open(out, encoding="utf-8").read()
            self.assertIn("--field 外科投影调用 **2 次 / 280 chars**", md)
            self.assertIn("--field 2 次/280c", r.stdout)
            # 普通视图调用不入分布行（快照调用总数 3 次 vs --field 2 次）
            self.assertIn("snapshot_view 调用 **3 次**", md)

    def test_a4_history_env_gate(self):
        """A4 防污染闸门：NO_HISTORY=1 不 append；未设时 append 到隔离 HOME。"""
        with tempfile.TemporaryDirectory() as td:
            fx = os.path.join(td, "fxh.jsonl")
            _build_fixture(fx)
            home = os.path.join(td, "home")
            os.makedirs(home, exist_ok=True)

            # 未设闸门（NO_HISTORY=0）+ 隔离 HOME → append 落盘
            out = os.path.join(td, "out_h.md")
            r = _run_audit(fx, out, no_history=False, home=home)
            self.assertEqual(r.returncode, 0, r.stderr)
            hist = os.path.join(home, ".cache", "token_audit_history.jsonl")
            self.assertTrue(os.path.exists(hist))
            entries = [json.loads(x) for x in open(hist, encoding="utf-8") if x.strip()]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["total"], 1050)
            self.assertIn("gate_fails", entries[0])

            # 闸门开启 → 不再 append（条数仍 1）
            out2 = os.path.join(td, "out_h2.md")
            r2 = _run_audit(fx, out2, no_history=True, home=home)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            entries2 = [json.loads(x) for x in open(hist, encoding="utf-8") if x.strip()]
            self.assertEqual(len(entries2), 1)


if __name__ == "__main__":
    unittest.main()
