#!/usr/bin/env python3
"""token_audit.py — 股票分析会话 token 事后审计（零 LLM 成本，复盘时一条命令）。

用法（显式传路径优先——--latest 按 mtime 挑选，可能选中活跃会话自身或错目标）：
  python3 token_audit.py <session.jsonl> [--stock 002859] [-o out.md]   # ✅ 推荐
  python3 token_audit.py --latest --stock 002859                        # ⚠️ mtime 挑选，慎用

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
  3. 视图直读：snapshot_view.py 调用计数（含 any 两级探查；any 命中扁平小节=合规）
  4. 无视图内手写：手写提取（tool_use 去重）按命令内路径字面量 vs VIEW_MOUNT_PREFIXES
     机械分层——前缀互通=视图内❌违规，视图外=info（建议改 any）；含 .jsonl /
     token_audit / verify_gates 的命令不计（日志挖掘与自审计排除）
  5. gate 源码零读入：Read gate_definitions.py（178K）→ ❌（FAIL 修法看 verify hint）
  6. 视图覆盖率：CLI result chars /（CLI result + 手写 result）chars > 80%（v2 result-only）
  7. 模块文件加权占比 vs 基线 32.3%
  8. 无快照写回：以写模式 open 的文件参数命中快照路径（runner.py 除外）→ ❌
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

VIEW_NAMES = ["kline", "cash_flow", "income", "mainfina", "news", "events", "holder",
              "balance", "timeline", "technical", "valuation", "consensus", "peer", "annual"]
# 视图 → 消费模块（报告归因用；events 双消费取 m4）
VIEW_TO_MODULE = {"kline": "m3", "cash_flow": "m2", "income": "m2", "mainfina": "m2",
                  "news": "m4", "events": "m4", "holder": "m4",
                  "balance": "m2", "timeline": "m4", "technical": "m3",
                  "valuation": "m5", "consensus": "m4", "peer": "m5", "annual": "m9"}

# 14 视图挂载点前缀（手写分级用：路径落在挂载点内 = 视图已覆盖仍手写 → ❌）
VIEW_MOUNT_PREFIXES = [
    "s2_quote_kline.data.daily_kline", "s1_financial.data.cash_flow",
    "s1_financial.data.income_statement", "s1_financial.data.mainfinadata",
    "s1_financial.data.balance_sheet", "s5_events.data.news",
    "s5_events.data.risk_signals", "s8_a_share.data.shareholder_count",
    "s4_technical.data", "valuation_snapshot.data", "consensus_forecast.data",
    "s11_peer.data", "s36_annual_analysis.data",
]
# 扁平小节（≤4K，any --depth 2 一条命令即全量；V9 尺寸采样结论，视图化收益<维护成本）
FLAT_SECTIONS = ["segment_composition", "financial_indicators", "rd_expense",
                 "dupont", "financial_abstract", "computed_metrics", "classification"]

WEBSEARCH_PAT = re.compile(r"feedcoopapi|mcp\.exa\.ai|api\.tavily|firecrawl|websearch|WebSearch", re.I)
HANDWRITE_PAT = re.compile(r"json\.load|json\.loads", re.I)
SNAPSHOT_FILE_PAT = re.compile(r"runner_snapshot|/tmp/snapshot")
WRITEBACK_PAT = re.compile(r"""open\(\s*['"]([^'"]+)['"]\s*,\s*['"][wa]['"]""")

# 手写提取路径解析：链式 ['a']['b'] 与 .get('a' 两类字面量（转义引号归一）
_PATH_CHAIN_RE = re.compile(r"(\[\s*['\"]([\w.\-]+)['\"]\s*\])+")
_PATH_GET_RE = re.compile(r"\.get\(\s*['\"]([\w.\-]+)['\"]")


def _extract_paths(cmd):
    s = cmd.replace('\\"', '"').replace("\\'", "'")
    paths = set()
    for m in _PATH_CHAIN_RE.finditer(s):
        paths.add(".".join(re.findall(r"['\"]([\w.\-]+)['\"]", m.group(0))))
    paths.update(_PATH_GET_RE.findall(s))
    return paths


def _tier_in_view(cmd):
    """手写命令访问路径 vs 视图挂载前缀的机械分层：前缀互通（含相等）= 视图内。

    禁用尾分量匹配：data 是 4 个挂载点的尾分量，尾匹配会把 s35/computed_metrics
    等 .data 访问误判视图内（688048 重放实测 4 处假阳性）。解析不出保守归视图外。
    """
    for p in _extract_paths(cmd):
        for mnt in VIEW_MOUNT_PREFIXES:
            if mnt == p or mnt.startswith(p + ".") or p.startswith(mnt + "."):
                return True
    return False


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
        if "gate_definitions" in fp:
            return "gate源码读入", None
        if "SKILL" in fp or "/references/" in fp or "skills/" in fp:
            return "Skill加载", None
        return "Read其它", None
    if "snapshot_view.py" in c:
        if HANDWRITE_PAT.search(c) and SNAPSHOT_FILE_PAT.search(c):
            return "复合命令(view+提取)", None   # snapshot_view 为主 + 附带 json.load → 复合，不计手写
        if re.search(r"\bany\b", c):
            return "视图:any", None
        for v in VIEW_NAMES:
            if re.search(rf"\b{v}\b", c):
                return f"视图:{v}", VIEW_TO_MODULE[v]
        return "视图:list/raw", None
    if HANDWRITE_PAT.search(c) and SNAPSHOT_FILE_PAT.search(c):
        return "手写提取", None   # 处数/分层/覆盖率以 handwrite_hits 单一计数源为准（v2）
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
    used_latest = args.latest or not path
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

    # A1：会话内容自提股票码（扫前 5 条用户文本消息——首条常为 caveat/命令包装，单读首条必漏）
    detected_code = ""
    seen_user = 0
    for l in lines:
        if l.get("type") != "user" or seen_user >= 5:
            if l.get("type") == "user":
                break
            continue
        content = (l.get("message") or {}).get("content")
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            texts = [x.get("text", "") for x in content
                     if isinstance(x, dict) and x.get("type") == "text"]
        else:
            texts = []
        txt = " ".join(t for t in texts if t)
        if not txt.strip():
            continue
        seen_user += 1
        m = re.search(r"(?<!\d)\d{6}(?!\d)", txt)
        if m:
            detected_code = m.group(0)
            break
    code_mismatch = bool(args.stock and detected_code and args.stock != detected_code)

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
    blocks = []  # [{turn, phase, cat, module, chars, desc, kind(call/result)}]
    result_chars_by_id = {}   # tool_use_id -> result chars（handwrite_hits 记录用）
    vg_result_texts = []      # verify_gates.py 执行的 result（按时间序，末条=终态）
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
                                   chars=len(desc) + 20, desc=f"调用:{name} {desc}",
                                   kind="call"))
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
                result_chars_by_id[b.get("tool_use_id")] = chars
                cat, mod = classify_block("tool_result", src)
                n, i2 = src
                c = str(i2.get("command", "")) if isinstance(i2, dict) else ""
                fp = str(i2.get("file_path", "")) if isinstance(i2, dict) else ""
                if "verify_gates" in c and "python" in c:
                    vg_result_texts.append(str(txt or ""))
                desc = (c[:60] or fp[-60:]).replace("\n", " ")
                tno = max(turn_no, 0)
                blocks.append(dict(turn=tno, phase=phase_of(tno), cat=cat, module=mod,
                                   chars=chars, desc=f"{n}: {desc}", kind="result"))

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
    snapshot_calls, handwrite_hits, writeback_hits, gate_src_reads, any_calls = [], [], [], [], []
    field_calls, field_chars = 0, 0                    # A5：--field 外科投影分布
    gate_src_bash_n, gate_src_bash_chars = 0, 0        # A2：gate 源码 Bash 侧访问（透明度）
    hw_turn = -1
    for l in lines:
        if l.get("type") != "assistant":
            continue
        hw_turn += 1
        for b in l.get("message", {}).get("content", []):
            if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                continue
            n, inp = b.get("name"), b.get("input") or {}
            c = str(inp.get("command", "")) if isinstance(inp, dict) else ""
            fp = str(inp.get("file_path", "")) if isinstance(inp, dict) else ""
            if "snapshot_view.py" in c:
                snapshot_calls.append(c)
                if re.search(r"\bany\b", c):
                    any_calls.append(c)
                if "--field" in c:
                    field_calls += 1
                    field_chars += result_chars_by_id.get(b.get("id"), 0)
            # A2：sed/grep/cat/awk 撞 gate_definitions = 源码访问（verify_gates.py 执行不计；
            # 与手写并集的命令只计手写不重复计）
            if re.search(r"\b(sed|grep|cat|awk)\b", c) and "gate_definitions" in c \
                    and not (HANDWRITE_PAT.search(c) and SNAPSHOT_FILE_PAT.search(c)):
                gate_src_bash_n += 1
                gate_src_bash_chars += result_chars_by_id.get(b.get("id"), 0)
            if "gate_definitions" in fp and n == "Read":
                gate_src_reads.append(fp)
            # 写回检测：以写模式 open 的文件参数本身命中快照路径（目标同一，
            # 防「读快照+写报告 md」跨文件假阳——688048 轮212-246 曾 7 处误报）；
            # 合法生产者 runner.py 除外；Path.write_text(json.dumps) 形态为已知限制
            if "runner.py" not in c and any(
                    SNAPSHOT_FILE_PAT.search(fn) for fn in WRITEBACK_PAT.findall(c)):
                writeback_hits.append(c[:90].replace("\n", " "))
            # 手写提取：tool_use 去重单一计数源（处数/分层/覆盖率全由此出）；
            # .jsonl = 日志挖掘（snapshot 恒 .json），token_audit/verify_gates = 自审计
            if HANDWRITE_PAT.search(c) and SNAPSHOT_FILE_PAT.search(c) \
                    and "snapshot_view.py" not in c and ".jsonl" not in c \
                    and "verify_gates" not in c and "token_audit" not in c:
                handwrite_hits.append({
                    "turn": hw_turn, "chars": result_chars_by_id.get(b.get("id"), 0),
                    "in_view": _tier_in_view(c), "surgical": "# rule5-surgical" in c,
                    # v3 处数三分桶：gate 调试（读 gate 源码甄别 FAIL）> fetch 补救（重拉/注入运维）
                    # > extract（真提取，验收线 ≤5 只量此桶）。注入写标记用 re 匹配 json.dump(
                    # ——禁裸子串 'json.dump'，会误中 json.dumps 打印惯用法
                    "bucket": ("gate" if "gate_definitions" in c else
                               "fetch" if ("akshare" in c or "financial-data-routing" in c)
                               else "extract"),
                    "inj_write": bool(re.search(r"json\.dump\s*\(", c)
                                      and SNAPSHOT_FILE_PAT.search(c)),
                    "cmd": c[:90].replace("\n", " ")})

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
    # v2：覆盖率口径 result-only（剔 tool_use stub 幽灵 chars），两侧同口径
    view_chars = sum(b["chars"] for b in blocks
                     if b["cat"].startswith("视图:") and b.get("kind") == "result")
    hw_cost = sum(b["cost"] for b in blocks if b["cat"].startswith("手写提取"))
    # A3：外科豁免单列（# rule5-surgical 声明处不计违规，quota ≤2 超额打 ⚠️）
    hw_exempt = [h for h in handwrite_hits if h.get("surgical")]
    hw_violations = [h for h in handwrite_hits if not h.get("surgical")]
    hw_chars = sum(h["chars"] for h in hw_violations)
    hw_in_view = [h for h in hw_violations if h["in_view"]]
    hw_out_view = [h for h in hw_violations if not h["in_view"]]
    # v3 处数三分桶（chars 口径不变——hw_chars/覆盖率/总取数仍按非 surgical 全量）
    hw_extract = [h for h in handwrite_hits if h.get("bucket") == "extract"]
    hw_gate = [h for h in handwrite_hits if h.get("bucket") == "gate"]
    hw_fetch = [h for h in handwrite_hits if h.get("bucket") == "fetch"]
    ext_in_n = sum(1 for h in hw_extract if h["in_view"])
    ext_out_n = len(hw_extract) - ext_in_n
    fetch_inj_n = sum(1 for h in hw_fetch if h.get("inj_write"))
    # 视图覆盖率 = CLI result chars /（CLI result + 手写 result）chars
    cli_chars = view_chars
    view_cov_pct = 100 * cli_chars / (cli_chars + hw_chars) if (cli_chars + hw_chars) else 0
    any_flat_hits = sum(1 for c in any_calls if any(s in c for s in FLAT_SECTIONS))
    BASE_MOD_PCT = 32.3   # 瑞丰 300243 旧路径基线（2026-08-20 审计）

    # ---- A4：总账行 + 环比历史（TOKEN_AUDIT_NO_HISTORY=1 时回归测试防污染） ----
    total_pull = cli_chars + hw_chars
    gate_fails = -1
    if vg_result_texts:
        m = re.search(r"失败: (\d+)", vg_result_texts[-1])
        if m:
            gate_fails = int(m.group(1))
    p4_start = phase_start.get("P4gate")
    p4_dump_chars = sum(h["chars"] for h in handwrite_hits
                        if p4_start is not None and h["turn"] >= p4_start)
    stock = args.stock or detected_code or "?"
    hist_path = os.path.expanduser("~/.cache/token_audit_history.jsonl")
    hist_entry = dict(date=datetime.now().strftime("%Y-%m-%d %H:%M"), stock=stock,
                      cli=cli_chars, handwrite=hw_chars, total=total_pull,
                      coverage=round(view_cov_pct, 1), gate_fails=gate_fails,
                      p4_dump_chars=p4_dump_chars, session=os.path.basename(path),
                      hw_extract=len(hw_extract), hw_gate=len(hw_gate),
                      hw_fetch=len(hw_fetch))
    recent = []
    try:
        with open(hist_path, encoding="utf-8") as fh:
            recent = [json.loads(x) for x in fh if x.strip()][-3:]
    except (OSError, json.JSONDecodeError):
        recent = []
    if os.environ.get("TOKEN_AUDIT_NO_HISTORY") != "1":
        os.makedirs(os.path.dirname(hist_path), exist_ok=True)
        with open(hist_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(hist_entry, ensure_ascii=False) + "\n")

    # ---- 输出 ----
    # stock 已在 A4 段取 args.stock or detected_code or "?"
    # 默认落对应股票分析目录（analysis_report-*-{code}/）；无匹配目录再退 token_audits/
    if args.out:
        out_path = args.out
    else:
        base = os.path.expanduser("~/analysis_report")
        stock_dir = None
        if os.path.isdir(base):
            for d in sorted(os.listdir(base)):
                if d.startswith("analysis_report-") and d.endswith(f"-{stock}"):
                    stock_dir = os.path.join(base, d)
                    break
        if stock_dir:
            out_path = os.path.join(
                stock_dir, f"token_audit-{stock}-{datetime.now():%Y%m%d-%H%M}.md")
        else:
            out_path = os.path.join(
                base, "token_audits", f"{stock}-{datetime.now():%Y%m%d-%H%M}.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    L = []
    L.append(f"# Token 审计 — {stock}（{datetime.now():%Y-%m-%d %H:%M}）")
    L.append(f"- 语义口径：**semantics v3**（deduped · result-only · path-tiered · 3-bucket 处数）"
             "——处数口径与 v2 不可比（gate 调试/fetch 补救另计）；chars 口径可比")
    L.append(f"\n- 会话：`{os.path.basename(path)}`（{T} 轮 API 调用，{len(blocks)} 内容块）")
    L.append(f"- 被分析文件：`{path}`")
    if used_latest:
        L.append("- ⚠️ 本次经 `--latest` mtime 挑选会话——可能选中活跃会话自身或错目标，"
                 "建议显式传路径")
    if code_mismatch:
        L.append(f"- ⚠️ 内容自提股票码 **{detected_code}** ≠ --stock {args.stock}"
                 "——疑似错目标审计（张冠李戴）")
    elif detected_code:
        L.append(f"- 内容自提股票码：{detected_code}"
                 + ("（与 --stock 一致 ✓）" if args.stock else "（--stock 未传，自动采用）"))
    L.append(f"- 真实口径（per-request usage 累计）："
             f"input **{tot_in:,}**（cache_read {tot_cache:,} / cache_write {tot_cc:,}）"
             f"+ output **{tot_out:,}**")
    L.append(f"- 归因口径：Σ chars×存活轮数 = {total_cost/1e6:.1f}M char·turn"
             f"（定位浪费用，非计费单位）")
    L.append(f"- **总取数 = CLI {cli_chars:,} + 手写 {hw_chars:,} = {total_pull:,} chars**"
             f"（覆盖率 {view_cov_pct:.1f}%｜末次 gate FAIL {gate_fails if gate_fails >= 0 else '—'}"
             f"｜P4 dump {p4_dump_chars:,}c｜外科豁免 {len(hw_exempt)} 处）")
    if recent:
        L.append("- 环比（最近 3 次）：" + "；".join(
            f"{r.get('date','?')} {r.get('stock','?')}: {r.get('total',0):,}c" for r in recent))

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
    L.append(f"- snapshot_view 调用 **{len(snapshot_calls)} 次**（含 any {len(any_calls)} 次，"
             f"其中扁平小节命中 {any_flat_hits} 次），结果合计 {view_chars:,} chars")
    L.append(f"- --field 外科投影调用 **{field_calls} 次 / {field_chars:,} chars**"
             "（分布行——防散便宜调用刷覆盖率：3c/调使刷分子成本趋零，须与手写残余同读）")
    if hw_in_view:
        L.append(f"- ⚠️ 手写提取（视图内·违规）{len(hw_in_view)} 处：")
        for h in hw_in_view:
            L.append(f"  - 轮{h['turn']} ({h['chars']:,}c) `{h['cmd'][:90]}`")
    if hw_out_view:
        L.append(f"- ℹ️ 手写提取（视图外·建议 any/--field）{len(hw_out_view)} 处：")
        for h in hw_out_view:
            L.append(f"  - 轮{h['turn']} ({h['chars']:,}c) `{h['cmd'][:90]}`")
    if hw_exempt:
        over = " ⚠️ 超额（quota ≤2）" if len(hw_exempt) > 2 else ""
        L.append(f"- 🔬 外科豁免（# rule5-surgical 声明，quota ≤2）{len(hw_exempt)} 处{over}：")
        for h in hw_exempt:
            L.append(f"  - 轮{h['turn']} ({h['chars']:,}c) `{h['cmd'][:90]}`")
    if hw_gate:
        L.append(f"- 🔧 gate 调试（hint 数据核对优先，读 gate 源码属行为分诊非取数）{len(hw_gate)} 处：")
        for h in hw_gate:
            L.append(f"  - 轮{h['turn']} ({h['chars']:,}c) `{h['cmd'][:90]}`")
    if hw_fetch:
        inj = f"，其中 ⚠️ 注入写 {fetch_inj_n} 处（json.dump 直写快照，D4 变量间接盲区）" \
            if fetch_inj_n else ""
        L.append(f"- 🔄 fetch 补救（API 失败后重拉/注入运维）{len(hw_fetch)} 处{inj}：")
        for h in hw_fetch:
            mark = " ⚠️ 注入写" if h.get("inj_write") else ""
            L.append(f"  - 轮{h['turn']} ({h['chars']:,}c){mark} `{h['cmd'][:90]}`")

    L.append("\n## ③ 新管线检查项（基线=瑞丰 300243 旧路径，2026-08-20）\n")
    checks = [
        ("模块 JIT 加载", jit_span >= 10, f"跨度 {jit_span} 轮（旧：Phase3 开头集中全量 Read）"),
        ("m11 延迟加载", m11_delayed,
         "未提前读" if not m11_turns else f"首读轮 {m11_turns[0]} vs verify 轮 {vg_turn}"),
        ("视图直读", len(snapshot_calls) >= 3,
         f"{len(snapshot_calls)} 次调用 / {view_chars:,} chars（旧 kline 单项 146K）"),
        ("无视图内手写提取", not hw_in_view,
         f"手写 {len(handwrite_hits)} 处 = 真提取 {len(hw_extract)}"
         f"（视图内 {ext_in_n} / 视图外 {ext_out_n}）+ gate 调试 {len(hw_gate)} "
         f"+ fetch 补救 {len(hw_fetch)}；验收线 ≤5 量真提取桶"
         if handwrite_hits else "0 处（stdout 节省基线 ~20%）"),
        ("无快照写回", not writeback_hits,
         f"{len(writeback_hits)} 处 json.dump/open(w/a) 写快照（runner.py 除外）"
         if writeback_hits else "0 处（快照只读）"),
        ("gate 源码零读入", not gate_src_reads,
         f"{len(gate_src_reads)} 次 Read gate_definitions（178K）——FAIL 修法看 verify 输出 "
         f"💡 hint，不足再读 m11-gates.md" if gate_src_reads else "0 次"),
        ("视图覆盖率>80%", view_cov_pct > 80,
         f"CLI 直读 {cli_chars:,} / (CLI+手写) {cli_chars + hw_chars:,} chars = "
         f"{view_cov_pct:.0f}%（any 命中扁平小节计合规）"),
        ("模块文件占比较基线下降", mod_file_pct < BASE_MOD_PCT,
         f"当前 {mod_file_pct:.1f}% vs 基线 {BASE_MOD_PCT}%（健康线 20%）"),
    ]
    for name, ok, detail in checks:
        L.append(f"- {'✅' if ok else '❌'} **{name}**：{detail}")
    L.append(f"- ℹ️ gate 源码 Bash 侧访问（sed/grep/cat/awk 撞 gate_definitions，sanctioned "
             f"fallback 透明度）：**{gate_src_bash_n} 次 / {gate_src_bash_chars:,}c**"
             f"（vs Read 全文 178K）")

    L.append("\n## ④ Top-15 最贵内容块（context 压力）\n")
    L.append("| 轮 | Phase | 类别 | chars | 压力% | 内容 |")
    L.append("|----|-------|------|-------|------|------|")
    for b in sorted(blocks, key=lambda x: -x["cost"])[:15]:
        L.append(f"| {b['turn']} | {b['phase']} | {b['cat']} | {b['chars']:,} | "
                 f"{100*b['cost']/total_cost:.1f} | {b['desc'][:60]} |")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"✅ 审计已写入 {out_path}")
    print(f"   被分析文件: {path}")
    if used_latest:
        print("   ⚠️ --latest mtime 挑选——可能选中活跃会话自身或错目标，建议显式传路径")
    if code_mismatch:
        print(f"   ⚠️ 内容自提股票码 {detected_code} ≠ --stock {args.stock}——疑似错目标审计")
    print(f"   轮次={T} | input={tot_in:,}(+cache {tot_cache:,}/{tot_cc:,}) "
          f"output={tot_out:,} | 检查项: "
          + " ".join(f"{'✅' if ok else '❌'}{n}" for n, ok, _ in checks))
    print(f"   [v2] 手写提取 {len(handwrite_hits)} 处 = 真提取 {len(hw_extract)}"
          f"（视图内 {ext_in_n} / 视图外 {ext_out_n}）+ gate 调试 {len(hw_gate)} "
          f"+ fetch 补救 {len(hw_fetch)}（验收线 ≤5 量真提取桶）| 写回 {len(writeback_hits)} | "
          f"覆盖率 {view_cov_pct:.1f}%（CLI {cli_chars:,} / 手写 {hw_chars:,} result chars）")
    print(f"   [v3] 外科豁免 {len(hw_exempt)} 处（quota ≤2）"
          + ("⚠️ 超额 " if len(hw_exempt) > 2 else "")
          + f"| gate源码Bash侧 {gate_src_bash_n} 次/{gate_src_bash_chars:,}c | "
          f"--field {field_calls} 次/{field_chars:,}c"
          + (f" | fetch 注入写 {fetch_inj_n} 处" if fetch_inj_n else ""))
    print(f"   总取数 {total_pull:,} = CLI {cli_chars:,} + 手写 {hw_chars:,}"
          f"｜gate FAIL {gate_fails if gate_fails >= 0 else '—'}｜P4 dump {p4_dump_chars:,}c")


if __name__ == "__main__":
    main()
