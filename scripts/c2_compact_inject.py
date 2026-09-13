#!/usr/bin/env python3
"""c2_compact_inject.py — C2 SessionStart(compact) hook 注入器（批4.4）

stdin: Claude Code hook JSON（含 transcript_path）；stdout = 注入上下文的注入文本。
预算：≤2KB/次（preflight 实测超限部分被外存、上下文只留 ~2KB 预览）。

模式路由（单一语义单实现，与 token_audit IS_B_SESSION 同签名）：
  主信号 = transcript 内 runner A/B 调用形态计数（多者胜，B>A→B、仅 A→A）；
  副信号 = /tmp 下 modeB 清单 mtime 新于 modeA（transcript 零痕迹时）；
  兜底默认 A（A 版注入是 B 的超集 = 安全侧）。
"""
import glob
import json
import os
import re
import sys

B_RE = re.compile(r"runner\.py[\"']?\s+B\s")


def detect_mode(transcript_path: str) -> str:
    # 主信号决胜：transcript 同时含 A/B 痕迹时（如 A 会话引用过 B 票命令文本），
    # runner 调用形态计数多者胜；只有 A 痕迹 = 直接 A，不落副信号
    b_n = a_n = 0
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if B_RE.search(line):
                    b_n += 1
                elif re.search(r"runner\.py[\"']?\s+A\s", line):
                    a_n += 1
    except OSError:
        pass
    if b_n > a_n:
        return "B"
    if a_n > 0:
        return "A"
    # 副信号：modeB 清单 mtime 新于 modeA（transcript 不可读/零痕迹时）
    b = sorted(glob.glob("/tmp/analysis_checklist_*_modeB_*.md"), key=os.path.getmtime)
    a = sorted(glob.glob("/tmp/analysis_checklist_*_modeA_*.md"), key=os.path.getmtime)
    if b and (not a or os.path.getmtime(b[-1]) > os.path.getmtime(a[-1])):
        return "B"
    return "A"   # 兜底默认 A


def _latest(paths):
    c = sorted((p for p in paths if os.path.exists(p)), key=os.path.getmtime)
    return c[-1] if c else None


def render(mode: str, transcript_path: str = "") -> str:
    cl = _latest(glob.glob(f"/tmp/analysis_checklist_*_mode{mode}_*.md"))
    if mode == "B":
        lines = [
            "[C2·compact续接·模式B] ①首个取数动作=snapshot_view.py <最新快照> --list（禁 json.load 探查）",
            f"②B 模块 6 个 JIT 勿整段重读（m38/m39/m3/m36/m37/m6）③清单：{cl or '未找到'}",
        ]
        return "\n".join(lines)
    sk = _latest(glob.glob("/tmp/analysis_skeleton_*.md"))
    # transcript_path 内联：load_skeleton 缺省 --latest 在并行会话下绑错（12:52 实证），
    # 显式传本会话 transcript 才能正确翻台账
    sk_cmd = (f"（翻页=load_skeleton.py {sk} --transcript {transcript_path or '<本会话jsonl>'}，已读项勿重读）"
              if sk else "")
    lines = [
        "[C2·compact续接·模式A] ①首个取数动作=snapshot_view.py <最新快照> --list（重建视图认知，禁 json.load 全树探查）",
        "②模块已读勿重读：12 模块 JIT（写哪章读哪章）；m11 仅首次 verify FAIL 才读",
        "③禁整段重读任何已 Read 过的文件（旧文按需 --list/any/--field 重取，不整段重读）",
        f"④清单：{cl or '未找到'}" + (f"｜骨架台账：{sk}{sk_cmd}" if sk else ""),
    ]
    return "\n".join(lines)


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    tp = d.get("transcript_path", "")
    mode = detect_mode(tp) if tp and os.path.exists(tp) else "A"
    print(render(mode, tp))


if __name__ == "__main__":
    main()
