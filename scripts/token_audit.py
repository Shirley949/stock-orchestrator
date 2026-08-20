#!/usr/bin/env python3
"""token_audit.py — 股票分析会话 token 事后审计（零 LLM 成本，复盘时一条命令）。

用法：
  python3 token_audit.py <session.jsonl> [--stock 002859] [-o out.md]
  python3 token_audit.py --latest                 # 审计最新会话
  python3 token_audit.py --latest --stock 002859  # 最新会话 + 标注股票

设计（2026-08-20）：记录的活交给引擎——分析会话零改动零负担，本脚本从 Claude Code
会话 JSONL 提取 per-request 真实 usage（input/cache_read/output）+ 内容块静态加权
归因（chars × 存活轮数 = context 压力），输出一张 md 审计表。

两个口径（互补，不是重复）：
  真实口径  per-turn usage 累计 —— 总量权威，钱和窗口消耗
  归因口径  chars×存活轮数      —— 哪个内容块在吃 context（定位浪费）

维度（正交双轴）：
  Phase   流程段（P0加载/P2拉取/P3写作/P4gate/P5发布），由工具调用序列确定性推断
  类别     内容性质（模块文件mXX/视图view/Skill加载/runner/websearch/LLM输出/系统）

新管线检查项（自动判定，基线=瑞丰 300243 旧路径审计 2026-08-20）：
  1. 模块 JIT：m*.md Read 轮次跨度（全量加载=集中 1-3 轮；JIT=跨度大且穿插写作）
  2. m11 延迟：m11-gates.md Read 应在首次 verify_gates 之后（或不出现）
  3. 视图直读：snapshot_view.py 调用计数；禁手写提取（json.load+runner_snapshot 且
     非 verify/token_audit 自身）
  4. 模块文件加权占比 vs 基线 32.3%
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

# ---------- 类别/Phase 推断规则（确定性，勿靠 LLM 自觉） ----------

MODULE_RE = re.compile(r"modules/(m\d[\w-]*)\.md")

VIEW_NAMES = ["kline", "cash_flow", "income", "mainfina", "news", "events", "holder"]
# 视图 → 消费模块（报告归因用；events 双消费取 m4）
VIEW_TO_MODULE = {"kline": "m3", "cash_flow": "m2", "income": "m2", "mainfina": "m2",
                  "news": "m4", "events": "m4", "holder": "m4"}

WEBSEARCH_PAT = re.compile(r"feedcoopapi|mcp\.exa\.ai|api\.tavily|firecrawl|websearch|WebSearch", re.I)
HANDWRITE_PAT = re.compile(r"json\.load|json\.loads", re.I)
SNAPSHOT_FILE_PAT = re.compile(r"runner_snapshot|/tmp/snapshot")


def classify_block(kind, detail):
    """给内容块打 (category, module) 标签。kind: tool_result/tool_use/text。

    detail：text→None；tool_use→(name, input)；tool_result→(来源工具 name, input)。
    """
    if kind == "text":
        return "LLM输出(写作)", None
    n, i2 = detail
    c = str(i2.get("command", "")) if isinstance(i2, dict) else ""
    fp = str(i2.get("file_path", "")) if isinstance(i2, dict) else ""

    if n == "Read":
        m = MODULE_RE.search(fp)
        if m:
            mid = re.match(r"m\d+", m.group(1)).group()
            return f"模块文件{mid}", mid
        if "SKILL" in fp or "/references/" in fp or "skills/" in fp:
            return "Skill加载", None
        return "Read其它", None
    if "snapshot_view.py" in c:
        for v in VIEW_NAMES:
            if re.search(rf"\b{v}\b", c):
                return f"视图:{v}", VIEW_TO_MODULE[v]
        return "视图:list/raw", None
    if HANDWRITE_PAT.search(c) and SNAPSHOT_FILE_PAT.search(c):
        return "手写提取stdout", None
    if "runner.py" in c:
        return "runner拉取", None
    if "verify_gates" in c or "update_checklist" in c:
        return "gate校验", None
    if "strip_src" in c or "md_to_smartcanvas" in c or "mcporter" in c:
        return "发布管线", None
    if WEBSEARCH_PAT.search(c) or n in ("WebSearch", "mcp__websearch__web_search_exa"):
        return "websearch", None
    if n in ("Write", "Edit"):
        return "LLM输出(写文件)", None
    if n == "Bash":
        return "bash其它", None
    if n and n.startswith("mcp__"):
        return "MCP工具", None
    return "其它工具", None


PHASE_MARKS = [
    ("P2拉取", lambda n, c, fp: "runner.py" in c),
    ("P3写作", lambda n, c, fp: bool(MODULE_RE.search(fp)) or "snapshot_view.py" in c),
    ("P4gate", lambda n, c, fp: "verify_gates" in c),
    ("P5发布", lambda n, c, fp: "strip_src" in c or "md_to_smartcanvas" in c or "mcporter" in c),
]


def main():
    ap = argparse.ArgumentParser(description="会话 token 事后审计")
    ap.add_argument("session", nargs="?", help="会话 JSONL 路径")
    ap.add_argument("--latest", action="store_true", help="取最新会话")
    ap.add_argument("--stock", default="", help="股票代码（仅用于标注/文件名）")
    ap.add_argument("-o", "--out", default="", help="输出 md 路径（默认 ~/analysis_report/token_audits/）")
    args = ap.parse_args()

    path = args.session
    if args.latest or not path:
        cands = sorted(glob.glob(os.path.expanduser(
            "~/.claude/projects/*/*.jsonl")), key=os.path.getmtime)
        if not cands:
            sys.exit("❌ 未找到会话 JSONL")
        path = cands[-1]

    lines = []
    with open(path, encoding="utf-8") as fh:
        for l in fh:
            l = l.strip()
            if l:
                try:
                    lines.append(json.loads(l))
                except json.JSONDecodeError:
                    pass

    # ---- 第一遍：建轮次序列（assistant 消息 = 一轮 API 调用），记录工具调用参数 ----
    turns = []          # [{usage, tool_uses:[(id,name,input)], text_chars, thinking_chars}]
    tooluse_by_id = {}  # tool_use_id -> (name, input) 供 tool_result 归因
    for l in lines:
        if l.get("type") != "assistant":
            continue
        msg = l.get("message", {})
        t = {"usage": msg.get("usage") or {}, "tool_uses": [], "text": 0, "thinking": 0}
        for b in msg.get("content", []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                t["tool_uses"].append((b.get("id"), b.get("name"), b.get("input") or {}))
                tooluse_by_id[b.get("id")] = (b.get("name"), b.get("input") or {})
            elif b.get("type") == "text":
                t["text"] += len(b.get("text") or "")
            elif b.get("type") == "thinking":
                t["thinking"] += len(b.get("thinking") or "")
        turns.append(t)

    T = len(turns)
    if T == 0:
        sys.exit("❌ 会话无 assistant 轮次")

    # ---- Phase 边界：首个命中各 phase 标志的轮次 ----
    phase_start = {}
    for i, t in enumerate(turns):
        for _, name, inp in t["tool_uses"]:
            c = str(inp.get("command", "")) if isinstance(inp, dict) else ""
            fp = str(inp.get("file_path", "")) if isinstance(inp, dict) else ""
            for ph, pat in PHASE_MARKS:
                if ph not in phase_start and pat(name or "", c, fp):
                    phase_start[ph] = i
    order = ["P2拉取", "P3写作", "P4gate", "P5发布"]
    starts = [phase_start[p] for p in order if p in phase_start]

    def phase_of(i):
        cur = "P0加载/其它"
        for ph in order:
            if ph in phase_start and i >= phase_start[ph]:
                cur = ph
        return cur

    # ---- 第二遍：内容块归因（user 消息里的 tool_result + assistant 自产） ----
    # cost = chars × 存活轮数(T - i)；归一化后即「context 压力占比」
    blocks = []  # [{turn, phase, cat, module, chars, desc}]
    turn_no = -1
    for l in lines:
        if l.get("type") == "assistant":
            turn_no += 1
            t = turns[turn_no]
            ph = phase_of(turn_no)
            if t["text"]:
                cat, mod = classify_block("text", None)
                blocks.append(dict(turn=turn_no, phase=ph, cat=cat, module=mod,
                                   chars=t["text"], desc="assistant 正文"))
            if t["thinking"]:
                blocks.append(dict(turn=turn_no, phase=ph, cat="LLM输出(thinking)",
                                   module=None, chars=t["thinking"], desc="thinking"))
            for _, name, inp in t["tool_uses"]:
                cat, mod = classify_block("tool_use", (name, inp))
                c = str(inp.get("command", "")) if isinstance(inp, dict) else ""
                fp = str(inp.get("file_path", "")) if isinstance(inp, dict) else ""
                desc = (c[:70] or fp[-70:]).replace("\n", " ")
                blocks.append(dict(turn=turn_no, phase=ph, cat=cat, module=mod,
                                   chars=len(desc) + 20, desc=f"调用:{name} {desc}"))
        elif l.get("type") == "user":
            msg = l.get("message", {})
            content = msg.get("content")
            if isinstance(content, str):
                # 用户纯文本输入也是 context
                blocks.append(dict(turn=max(turn_no, 0), phase=phase_of(max(turn_no, 0)),
                                   cat="用户输入", module=None,
                                   chars=len(content), desc="user 消息"))
                continue
            for b in content or []:
                if not isinstance(b, dict) or b.get("type") != "tool_result":
                    continue
                src = tooluse_by_id.get(b.get("tool_use_id"), ("?", {}))
                txt = b.get("content")
                if isinstance(txt, list):
                    txt = " ".join(x.get("text", "") for x in txt if isinstance(x, dict))
                chars = len(str(txt or ""))
                cat, mod = classify_block("tool_result", src)
                n, i2 = src
                c = str(i2.get("command", "")) if isinstance(i2, dict) else ""
                fp = str(i2.get("file_path", "")) if isinstance(i2, dict) else ""
                desc = (c[:60] or fp[-60:]).replace("\n", " ")
                tno = max(turn_no, 0)
                blocks.append(dict(turn=tno, phase=phase_of(tno), cat=cat, module=mod,
                                   chars=chars, desc=f"{n}: {desc}"))

    for b in blocks:
        b["cost"] = b["chars"] * max(T - b["turn"], 1)
    total_cost = sum(b["cost"] for b in blocks) or 1

    # ---- 真实 usage 累计 ----
    tot_in = sum(t["usage"].get("input_tokens", 0) for t in turns)
    tot_cache = sum(t["usage"].get("cache_read_input_tokens", 0) for t in turns)
    tot_cc = sum(t["usage"].get("cache_creation_input_tokens", 0) for t in turns)
    tot_out = sum(t["usage"].get("output_tokens", 0) for t in turns)

    # ---- 汇总 ----
    by_phase = defaultdict(lambda: Counter())
    by_cat = defaultdict(Counter)   # phase -> cat -> cost
    for b in blocks:
        by_phase[b["phase"]][b["cat"]] += b["cost"]
        by_cat[b["cat"]][b["phase"]] += b["cost"]

    module_reads = defaultdict(list)   # mXX -> [turn]
    snapshot_calls, handwrite_hits = [], []
    for l in lines:
        if l.get("type") != "assistant":
            continue
        for b in l.get("message", {}).get("content", []):
            if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                continue
            n, inp = b.get("name"), b.get("input") or {}
            c = str(inp.get("command", "")) if isinstance(inp, dict) else ""
            fp = str(inp.get("file_path", "")) if isinstance(inp, dict) else ""
            if "snapshot_view.py" in c:
                snapshot_calls.append(c)
            if HANDWRITE_PAT.search(c) and SNAPSHOT_FILE_PAT.search(c) \
                    and "verify_gates" not in c and "token_audit" not in c:
                handwrite_hits.append(c[:90].replace("\n", " "))

    # 模块 Read 轮次（精确）
    module_reads = defaultdict(list)
    ti = -1
    for l in lines:
        if l.get("type") == "assistant":
            ti += 1
            for b in l.get("message", {}).get("content", []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    fp = str((b.get("input") or {}).get("file_path", ""))
                    m = MODULE_RE.search(fp)
                    if m:
                        module_reads[m.group(1)[:3]].append(ti)

    read_turns = sorted(t for ts in module_reads.values() for t in ts)
    jit_span = (read_turns[-1] - read_turns[0]) if len(read_turns) > 1 else 0
    m11_turns = module_reads.get("m11", [])
    vg_turn = phase_start.get("P4gate")
    m11_delayed = (not m11_turns) or (vg_turn is not None and m11_turns[0] > vg_turn)

    mod_file_cost = sum(b["cost"] for b in blocks if b["cat"].startswith("模块文件"))
    mod_file_pct = 100 * mod_file_cost / total_cost
    view_cost = sum(b["cost"] for b in blocks if b["cat"].startswith("视图:"))
    view_chars = sum(b["chars"] for b in blocks if b["cat"].startswith("视图:"))
    hw_cost = sum(b["cost"] for b in blocks if b["cat"] == "手写提取stdout")
    hw_chars = sum(b["chars"] for b in blocks if b["cat"] == "手写提取stdout")
    BASE_MOD_PCT = 32.3   # 瑞丰 300243 旧路径基线（2026-08-20 审计）

    # ---- 输出 ----
    stock = args.stock or "?"
    out_path = args.out or os.path.expanduser(
        f"~/analysis_report/token_audits/{stock}-{datetime.now():%Y%m%d-%H%M}.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    L = []
    L.append(f"# Token 审计 — {stock}（{datetime.now():%Y-%m-%d %H:%M}）")
    L.append(f"\n- 会话：`{os.path.basename(path)}`（{T} 轮 API 调用，{len(blocks)} 内容块）")
    L.append(f"- 真实口径（per-request usage 累计）："
             f"input **{tot_in:,}**（cache_read {tot_cache:,} / cache_write {tot_cc:,}）"
             f"+ output **{tot_out:,}**")
    L.append(f"- 归因口径：Σ chars×存活轮数 = {total_cost/1e6:.1f}M char·turn"
             f"（定位浪费用，非计费单位）")

    L.append("\n## ① Phase × 类别矩阵（归因占比 %）\n")
    cats = sorted(by_cat, key=lambda c: -sum(by_cat[c].values()))
    phases = ["P0加载/其它", "P2拉取", "P3写作", "P4gate", "P5发布"]
    L.append("| 类别 | " + " | ".join(phases) + " | 合计 |")
    L.append("|------|" + "------|" * (len(phases) + 1))
    for c in cats:
        row = [f"{100*by_cat[c].get(p,0)/total_cost:.1f}" if by_cat[c].get(p) else "—" for p in phases]
        tot = f"**{100*sum(by_cat[c].values())/total_cost:.1f}**"
        L.append(f"| {c} | " + " | ".join(row) + f" | {tot} |")
    L.append("| **合计** | " + " | ".join(
        f"**{100*sum(by_phase[p].values())/total_cost:.0f}**"
        if sum(by_phase[p].values()) else "—" for p in phases) + " | **100** |")

    L.append("\n## ② 模块维度（Phase 3 内）\n")
    L.append("| 模块 | 文件Read轮次 | 首读轮 | 视图取数（chars） |")
    L.append("|------|------------|-------|-----------------|")
    for m in sorted(module_reads):
        L.append(f"| {m} | {len(module_reads[m])} | {module_reads[m][0]} | — |")
    L.append(f"\n- 模块 Read 轮次跨度：**{jit_span} 轮**（JIT 生效=跨度大且穿插写作；旧全量加载=集中 1-3 轮）")
    L.append(f"- snapshot_view 调用 **{len(snapshot_calls)} 次**，结果合计 {view_chars:,} chars")
    if handwrite_hits:
        L.append(f"- ⚠️ 疑似手写提取 {len(handwrite_hits)} 处：")
        for h in handwrite_hits[:5]:
            L.append(f"  - `{h}`")

    L.append("\n## ③ 新管线检查项（基线=瑞丰 300243 旧路径，2026-08-20）\n")
    checks = [
        ("模块 JIT 加载", jit_span >= 10, f"跨度 {jit_span} 轮（旧：Phase3 开头集中全量 Read）"),
        ("m11 延迟加载", m11_delayed,
         "未提前读" if not m11_turns else f"首读轮 {m11_turns[0]} vs verify 轮 {vg_turn}"),
        ("视图直读", len(snapshot_calls) >= 3,
         f"{len(snapshot_calls)} 次调用 / {view_chars:,} chars（旧 kline 单项 146K）"),
        ("无手写提取", not handwrite_hits,
         f"{len(handwrite_hits)} 处 / stdout {hw_chars:,} chars（加权压力 "
         f"{100*hw_cost/total_cost:.1f}%）——视图覆盖字段禁 json.load 直读" if handwrite_hits
         else f"0 处（stdout 节省基线 ~20%）"),
        ("模块文件占比较基线下降", mod_file_pct < BASE_MOD_PCT,
         f"当前 {mod_file_pct:.1f}% vs 基线 {BASE_MOD_PCT}%（健康线 20%）"),
    ]
    for name, ok, detail in checks:
        L.append(f"- {'✅' if ok else '❌'} **{name}**：{detail}")

    L.append("\n## ④ Top-15 最贵内容块（context 压力）\n")
    L.append("| 轮 | Phase | 类别 | chars | 压力% | 内容 |")
    L.append("|----|-------|------|-------|------|------|")
    for b in sorted(blocks, key=lambda x: -x["cost"])[:15]:
        L.append(f"| {b['turn']} | {b['phase']} | {b['cat']} | {b['chars']:,} | "
                 f"{100*b['cost']/total_cost:.1f} | {b['desc'][:60]} |")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"✅ 审计已写入 {out_path}")
    print(f"   轮次={T} | input={tot_in:,}(+cache {tot_cache:,}/{tot_cc:,}) "
          f"output={tot_out:,} | 检查项: "
          + " ".join(f"{'✅' if ok else '❌'}{n}" for n, ok, _ in checks))


if __name__ == "__main__":
    main()
