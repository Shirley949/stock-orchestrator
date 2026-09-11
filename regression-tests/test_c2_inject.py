#!/usr/bin/env python3
"""test_c2_inject.py — 批4.4：C2 注入器模式路由 + 注入预算锁

红极自证：c2_compact_inject.py 缺失或路由倒置（B 判成 A）必报。
注入预算：≤2KB/次（preflight 实测上限——超限部分被外存不进上下文）。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
INJECT = HERE.parent / "scripts" / "c2_compact_inject.py"
sys.path.insert(0, str(INJECT.parent))

failures = []


def check(name, ok, detail=""):
    print(f"  {'✅' if ok else '❌'} {name}" + (f"：{detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def run_hook(stdin_obj, env_tmp=None):
    import os
    env = dict(os.environ)
    if env_tmp:
        env["TMPDIR"] = env_tmp   # 预留；当前实现读 /tmp 固定路径，测试用真 /tmp 无 checklist 时走兜底
    r = subprocess.run([sys.executable, str(INJECT)], input=json.dumps(stdin_obj),
                       capture_output=True, text=True, env=env)
    return r.stdout.strip()


print("[1] 模式路由")
# B 主信号：transcript 含 runner.py B
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
    fh.write(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash",
         "input": {"command": "python runner.py B 002008 > /tmp/runner_snapshot_002008_modeB.json"}}]}}) + "\n")
    b_tp = fh.name
out = run_hook({"transcript_path": b_tp, "source": "compact"})
check("B 主信号命中 → B 版", "模式B" in out and "m38" in out, out[:80])

# A 兜底：transcript 无 B 标记
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
    fh.write(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash",
         "input": {"command": "python runner.py A 603920 > /tmp/runner_snapshot_603920_modeA.json"}}]}}) + "\n")
    a_tp = fh.name
out = run_hook({"transcript_path": a_tp, "source": "compact"})
check("无 B 标记 → 兜底 A 版", "模式A" in out and "--list" in out, out[:80])

# 健壮性：transcript 路径不存在 / stdin 非法 → A 不崩
out = run_hook({"transcript_path": "/nonexistent/x.jsonl"})
check("transcript 缺失 → A 兜底不崩", "模式A" in out)
r = subprocess.run([sys.executable, str(INJECT)], input="not-json{{",
                   capture_output=True, text=True)
check("非法 stdin → A 兜底不崩", r.returncode == 0 and "模式A" in r.stdout)

print("[2] 注入预算（≤2KB，preflight 实测上限）")
check("A 版 ≤2KB", len(run_hook({"transcript_path": a_tp}).encode()) <= 2048)
check("B 版 ≤2KB", len(run_hook({"transcript_path": b_tp}).encode()) <= 2048)

print("[3] A 版命脉内容（compact 仪式四要素）")
a_out = run_hook({"transcript_path": a_tp})
check("首取数 --list 纪律在场", "--list" in a_out)
check("12 模块 JIT 勿重读在场", "12 模块" in a_out and "勿重读" in a_out)
check("禁整段重读在场", "禁整段重读" in a_out)
check("m11 延迟语义在场", "m11" in a_out and "verify" in a_out)

import os
os.unlink(b_tp)
os.unlink(a_tp)
print()
if failures:
    print(f"❌ {len(failures)} 项失败：{failures}")
    sys.exit(1)
print("✅ C2 注入器 全绿")
