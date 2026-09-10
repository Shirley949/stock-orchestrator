#!/usr/bin/env python3
"""load_skeleton.py — C0 台账回写副作用化（批4.3）

出内容 + 翻台账 = 同一命令（禁依赖 LLM 自发 Edit——002008 的 1/5 回写率、600105 的
31 读零回写即「记性不可靠」现行复现）。动作：扫会话 transcript 的 Read 事件 →
把骨架台账中对应条目 状态:未读→已读（幂等）→ stdout 打印翻页后的骨架全文。

用法：
  python3 load_skeleton.py <skeleton.md> [--transcript <session.jsonl>]
  # --transcript 缺省取 mtime 最新 jsonl——本命令在会话内跑时最新即自身会话；
  # 事后审计等跨会话场景必须显式传（mtime 挑选的已知陷阱，同 token_audit --latest）

B 侧：无骨架（A-only），本命令自然无对象；B 台账行为挂 token_audit 加载集 diff 字段
观察（观察态，禁以「自发行为」为据转正）。
"""
import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

LEDGER_RE = re.compile(r"^- ▸ (\S+\.md) \| 状态:(未读|已读)")


def read_file_paths(transcript: str) -> set:
    """收集 transcript 中全部 Read tool_use 的 file_path（去重）。"""
    fps = set()
    with open(transcript, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = (d.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for b in content:
                if (isinstance(b, dict) and b.get("type") == "tool_use"
                        and b.get("name") == "Read"):
                    fps.add(str((b.get("input") or {}).get("file_path", "")))
    return fps


def main():
    ap = argparse.ArgumentParser(description="骨架台账翻页（出内容+翻台账同一副作用）")
    ap.add_argument("skeleton", help="generate_checklist --skeleton-out 产出的骨架路径")
    ap.add_argument("--transcript", default="",
                    help="会话 jsonl；缺省取 mtime 最新（会话内跑=自身；事后审计须显式传）")
    args = ap.parse_args()

    path = Path(args.skeleton)
    if not path.exists():
        sys.exit(f"❌ 骨架不存在: {path}")
    tp = args.transcript
    if not tp:
        cands = sorted(glob.glob(os.path.expanduser(
            "~/.claude/projects/*/*.jsonl")), key=os.path.getmtime)
        if not cands:
            sys.exit("❌ 未找到会话 jsonl——事后审计场景须 --transcript 显式传")
        tp = cands[-1]

    fps = read_file_paths(tp)
    lines = path.read_text(encoding="utf-8").splitlines()
    flipped = []
    for i, l in enumerate(lines):
        m = LEDGER_RE.match(l)
        if not m or m.group(2) != "未读":
            continue
        if any(fp.endswith(m.group(1)) for fp in fps):
            lines[i] = l.replace("状态:未读", "状态:已读", 1)
            flipped.append(m.group(1).split("/")[-1])

    content = "\n".join(lines)
    path.write_text(content + "\n", encoding="utf-8")
    print(content)                       # 出内容：翻页后的骨架全文（LLM 经 Bash result 直读）
    print(f"\n[翻页 {len(flipped)} 项：{', '.join(flipped) or '无'} | transcript={tp}]",
          file=sys.stderr)


if __name__ == "__main__":
    main()
