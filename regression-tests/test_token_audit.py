#!/usr/bin/env python3
"""token_audit v2 语义自检 fixture：合成微型会话 → 跑表计 → 断言处数/分层/写回/覆盖率。

为什么存在：表计是验收线（纯提取≤5 / 覆盖率>80% / 写回 0 / gate 源码 0）的尺，
尺的语义（去重 · result-only · 挂载前缀机械分层 · 写回目标同一）此后任何改动
都由本脚本判定，不再需要 LLM 手跑模拟重验（2026-08-21 688048 审计重放口径）。

跑：python3 test_token_audit.py（无网络，<2s）
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


def _build_fixture(path):
    with open(path, "w", encoding="utf-8") as fh:
        for tid, cmd, res_len in CALLS:
            fh.write(json.dumps({"type": "assistant", "message": {
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "content": [{"type": "tool_use", "id": tid, "name": "Bash",
                             "input": {"command": cmd}}]}}) + "\n")
            fh.write(json.dumps({"type": "user", "message": {
                "content": [{"type": "tool_result", "tool_use_id": tid,
                             "content": [{"type": "text", "text": "x" * res_len}]}]}}) + "\n")


class TokenAuditV2Test(unittest.TestCase):
    def test_v2_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            fx = os.path.join(td, "fixture.jsonl")
            out = os.path.join(td, "out.md")
            _build_fixture(fx)
            r = subprocess.run([sys.executable, AUDIT, fx, "--stock", "TEST", "-o", out],
                               capture_output=True, text=True, timeout=60)
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


if __name__ == "__main__":
    unittest.main()
