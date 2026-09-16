#!/usr/bin/env python3
"""atomic_step_probe.py — D5 章级三动作探针（流水架构批3，plan 3b）。

判定粒度 = 章（钉死，视图级不判——m4 五件套先拉 news 写一段再拉 timeline = 合法）：
  每写作步 = 首动作 Read modules/<m>.md → 中间任意次视图拉取 → 末动作 update_checklist 勾选。
  章与章之间动作交错（下章 Read 先于上章勾选）= 拆窗 = 批读回潮信号 → 逐处列出。

合法面（不判）：
  - 同章模块复读（compact 后重读将写章节合法，台账=读过≠在context）
  - 章内任意次视图拉取（原子步②投影 + 按需 any/--field 重取）
  - 非模块 Read（SKILL/scenarios/CLAUDE 等）不构成章边界

用法：
  python3 atomic_step_probe.py <session.jsonl> [--fail-on-interleave]
  exit 0 = 报告完成（拆窗与否看报告）；--fail-on-interleave 时拆窗 → exit 1（CI 用）。
"""
import argparse
import json
import re
import sys

MODULE_RE = re.compile(r"modules/(m\d[\w-]*)\.md")
CHECK_RE = re.compile(r"--check\s+(\S+)")
LOOP_RE = re.compile(r"for\s+\w+\s+in\s+([^;\n]+)")   # 旧路径批量勾选：for c in c04 c05; do --check $c
VIEW_RE = re.compile(r"snapshot_view\.py|xq_voice\.py")


def _check_ids(cmd):
    """命令中的勾选 cid 列表（--check 字面形 + for-in 循环形展开；--uncheck 不计）。"""
    if "update_checklist" not in cmd or "--uncheck" in cmd:
        return []
    mc = CHECK_RE.search(cmd)
    if mc and not mc.group(1).startswith("$"):
        return [mc.group(1)]
    lp = LOOP_RE.search(cmd)          # --check $c 变量形 → 展开 for-in 清单
    if lp:
        return [t for t in lp.group(1).split() if re.fullmatch(r"c[\w-]+", t)]
    return mc.group(1) if mc else []


def events_in_order(path):
    """按轮序展开 (turn, kind, detail)：mod_read / check / view。"""
    events = []
    turn = -1
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                l = json.loads(line)
            except json.JSONDecodeError:
                continue
            if l.get("type") != "assistant":
                continue
            turn += 1
            for b in l.get("message", {}).get("content", []):
                if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                    continue
                n = b.get("name")
                inp = b.get("input") or {}
                c = str(inp.get("command", ""))
                fp = str(inp.get("file_path", ""))
                if n == "Read":
                    m = MODULE_RE.search(fp)
                    if m:
                        events.append((turn, "mod_read", m.group(1)))
                elif n == "Bash":
                    for cid in _check_ids(c):
                        events.append((turn, "check", cid))
                    if VIEW_RE.search(c) and not _check_ids(c):
                        events.append((turn, "view", c[:50].replace("\n", " ")))
    return events


def probe(path):
    events = events_in_order(path)
    chapters = []          # [dict(mod, read_turn, check_turn|None, views)]
    interleaves = []       # 拆窗事件
    cur = None
    for turn, kind, detail in events:
        if kind == "mod_read":
            if cur and detail == cur["mod"]:
                continue                      # 同章复读 = 合法（compact 恢复）
            if cur and cur["check_turn"] is None:
                interleaves.append(dict(prev=cur["mod"], prev_read=cur["read_turn"],
                                        nxt=detail, at=turn,
                                        note=f"Read {detail} 先于 {cur['mod']} 勾选（下章读先于上章勾）"))
                chapters.append({**cur, "views": cur["views"]})   # 上章未闭合先入账
                cur = None
            cur = dict(mod=detail, read_turn=turn, check_turn=None, views=0)
        elif kind == "view" and cur is not None:
            cur["views"] += 1
        elif kind == "check":
            if cur is not None and cur["check_turn"] is None:
                cur["check_turn"] = turn
                chapters.append(cur)
                cur = None
            else:
                # 勾选迟到（旧路径批量勾在写作后）→ 回闭最早的未闭合章；
                # 拆窗已在上面的 mod_read 分支逐处记账，此处只修闭合态
                for ch in chapters:
                    if ch["check_turn"] is None:
                        ch["check_turn"] = turn
                        break
    if cur:
        chapters.append(cur)                  # 末章未闭合（写作中/断头）→ 报告为未闭合

    return chapters, interleaves


def main():
    ap = argparse.ArgumentParser(description="D5 章级三动作探针（拆窗=批读回潮信号）")
    ap.add_argument("session", help="会话 JSONL 路径")
    ap.add_argument("--fail-on-interleave", action="store_true",
                    help="检出拆窗时 exit 1（默认仅报告）")
    args = ap.parse_args()

    chapters, interleaves = probe(args.session)
    print(f"[atomic_step_probe] {args.session}")
    print(f"  章（模块级写作步）：{len(chapters)} 个｜拆窗：{len(interleaves)} 处")
    for ch in chapters:
        ok = ch["check_turn"] is not None
        print(f"  - {ch['mod']:<16} Read@轮{ch['read_turn']} → "
              f"{'勾@轮' + str(ch['check_turn']) if ok else '未闭合'}"
              f"（章内视图拉取 {ch['views']} 次）")
    for iv in interleaves:
        print(f"  ⚠️ 拆窗：{iv['note']}（上章 Read@轮{iv['prev_read']}，"
              f"下章 Read@轮{iv['at']}）")
    if interleaves and args.fail_on_interleave:
        sys.exit(1)
    print("  判定：拆窗=下章 Read 先于上章勾选；同章复读/章内视图拉取均合法（视图级不判）")


if __name__ == "__main__":
    main()
