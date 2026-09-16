#!/usr/bin/env python3
"""preflight_c2_sessionstart.py — 4a 诱导 compact 前置①（批3-3c，用后即焚）。

验证 SessionStart(compact) 的注入链路在本机可用：以 hook 真实 stdin 形态
（{"transcript_path":…, "source":"compact"}）直调 c2_compact_inject.py，
断言 stdout 首行 `[C2·` 开头且 ≤2KB。manual /compact 触发时 Claude Code 以同一
stdin 形态调本 hook——本脚本 PASS 即链路就绪，剩下的就是会话里敲 /compact。

用法：python3 preflight_c2_sessionstart.py <本会话jsonl> [--mode A|B]
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INJECT = HERE.parent / "scripts" / "c2_compact_inject.py"


def main():
    if len(sys.argv) < 2:
        sys.exit("用法：preflight_c2_sessionstart.py <本会话jsonl> [--mode A|B]")
    tp = sys.argv[1]
    mode = "A"
    if "--mode" in sys.argv:
        mode = sys.argv[sys.argv.index("--mode") + 1]
    if not Path(tp).exists():
        sys.exit(f"❌ transcript 不存在: {tp}")
    stdin = json.dumps({"transcript_path": tp, "source": "compact"})
    r = subprocess.run([sys.executable, str(INJECT)], input=stdin,
                       capture_output=True, text=True)
    out = r.stdout.strip()
    ok = r.returncode == 0 and out.startswith("[C2·")
    size = len(out.encode())
    mode_ok = f"模式{mode}" in out.split("\n")[0] if out else False
    print(f"{'✅' if ok else '❌'} hook 可执行且首行 [C2· 开头（{size}B ≤2048）")
    print(f"{'✅' if mode_ok else '❌'} 路由命中 模式{mode}（首行：{out.split(chr(10))[0][:60]}）")
    if not (ok and mode_ok):
        sys.exit(1)
    print("▶ 链路就绪。下一步（4a 诱导）：该会话内敲 /compact → SessionStart(compact) "
          "fire → 注入同款文本 → 观测恢复步数（≤3 工具调用）与恢复取数 chars。")


if __name__ == "__main__":
    main()
