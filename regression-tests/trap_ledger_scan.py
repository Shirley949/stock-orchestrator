#!/usr/bin/env python3
"""trap_ledger_scan — 陷阱台账扫描器（E10）：sidecar FAIL 按 signature 分类计数 + 现场验收簿记（C-4）。

用法：
  python3 trap_ledger_scan.py                       # 报告模式：线上语料计数 + delta + 验收只读状态
  python3 trap_ledger_scan.py --strict              # 增量拦截：任一 entry cur>count 基线 → exit 1
  python3 trap_ledger_scan.py --field-acceptance    # 簿记模式（cron 收尾跑）：窗口/暴露/关闭/warn翻转 自动落账
  python3 trap_ledger_scan.py --root <dir> [--ledger <yaml>] [--acceptance <yaml>]
                                                    # 扫沙箱（回归接线用，沙箱自带 ledger）

strict 语义（P12 裁定，勿改回直拦）：72 份存量 sidecar 中 10 份含历史 failed_gates
——历史 FAIL 是预期存在，count 基线即冻结时的实测量；仅**新增**（cur > count）才 exit 1。
回归（run_regression.sh）接线的是沙箱 fixtures，线上语料走非 strict 报告模式。

匹配：sidecar details[] 中 status==fail 的项，gate 相等且 reasons 拼接串命中 entry.match
正则（无 match=gate 级兜底）。旧 sidecar 无 reasons 时按 gate 兜底计。
未命中任何 entry 的 FAIL = unclassified（只报告，不拦——台账未登记非回归）。

现场验收簿记（C-4 裁决 2026-09-01，暴露度调整验收——「等零复发」不成立：零暴露时
零复发空洞）：簿记模式对**当窗新 sidecar** 跑三个暴露探针（报告正文 grep 触发形态），
输出 暴露N/阈值T·复现M·窗剩W；达标自动关闭、暴露不足自动展期一次（+2 cron）、仍不足
降级关闭「单元已证现场未证」转永久计数；warn→硬断言 同一 tracker（一轮 cron 零命中自动
翻转，verify_gates 读翻转位）。方向局限：现场只证假阳性方向，假阴性由 corpus+归档重放守。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
from trap_ledger import load_ledger, engine_pending, load_acceptance, save_acceptance  # noqa: E402

DEFAULT_ROOT = Path("~/analysis_report").expanduser()

# 暴露探针（C-4）：对当窗报告正文 grep 触发形态——形态出现=暴露（修复若失效会在同一
# 报告上产出 FAIL=复现/假阳性）。regex 与引擎语义同源（分位族=E1 全形态；否定=紧邻+窗内；
# 定增=同义词归一的落笔侧）。
_EXPOSURE_PROBES = {
    "percentile": re.compile(r"\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*(?:百分位|分位数|分位)"),
    "negation": re.compile(
        r"(?:没有|难以|不再|放弃|拒绝)[^，。；、！？]{0,2}"
        r"(?:加仓|增持|买入|建仓|减仓|减持|卖出|清仓|止损|空仓)"
        r"|(?:不支持|不宜|不建议|不急于|暂不|勿|避免|无加仓)[^。；！？]{0,12}?"
        r"(?:加仓|增持|买入|建仓|减仓|减持|卖出|清仓|止损|空仓)"),
    "dingzeng": re.compile(r"定增"),
}


def _iter_sidecars(root: Path):
    for sc in sorted(root.glob("**/*.verified.json")):
        try:
            doc = json.loads(sc.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        yield sc, doc


def _report_text(sc: Path) -> str:
    """sidecar 的兄弟报告正文（暴露探针作用面）。"""
    rp = sc.with_name(sc.name[: -len(".verified.json")] + ".md")
    try:
        return rp.read_text(encoding="utf-8")
    except OSError:
        return ""


def _window_key(doc: dict) -> str:
    """窗口键 = sidecar timestamp 的日期段（一日一窗，cron 颗粒度足够）。"""
    ts = str(doc.get("timestamp") or "")
    return ts[:10]


def _by_gate_index(ledger: list) -> dict:
    idx = {}
    for e in ledger:
        idx.setdefault(e.get("gate"), []).append(e)
    return idx


def _match_signature(by_gate: dict, gate, reasons: str):
    """单条 FAIL → 命中的 signature（无 match=gate 级兜底）；未命中返 None。
    scan 分类与 field_acceptance 复现计数共用（同一语义只允许一个实现）。"""
    for e in by_gate.get(gate, []):
        m = e.get("match")
        if not m or re.search(m, reasons):
            return e["signature"]
    return None


def scan(root: Path, ledger: list) -> tuple:
    """返回 (per_signature 计数, unclassified 清单)。"""
    counts = {e["signature"]: 0 for e in ledger}
    by_gate = _by_gate_index(ledger)
    unclassified = []
    for sc, doc in _iter_sidecars(root):
        for d in doc.get("details") or []:
            if d.get("status") != "fail":
                continue
            reasons = "".join(d.get("reasons") or [])
            hit = _match_signature(by_gate, d.get("gate"), reasons)
            if hit:
                counts[hit] += 1
            else:
                unclassified.append(f"{d.get('gate')}@{sc.name}")
    return counts, unclassified


def propose(root: Path, ledger: list) -> int:
    """unclassified 半自动化入账（pending #5）：按 gate×reasons 首例聚簇出签名提案草稿。

    人判流程：本输出 → 判「陷阱 vs 真错/环境态」→ 填 status/root_cause → 粘入
    trap_ledger.yaml entries → 重跑 scan 验证 unclassified=0。聚簇键=gate+reasons 原文
    （历史 sidecar 无 diag.subcheck 时靠原文分桶；新 sidecar 有 diag 时 reason 自带
    [数据层]/真值前缀，天然分桶）。
    """
    by_gate = _by_gate_index(ledger)
    clusters = {}   # (gate, reasons原文[:80]) -> count
    for sc, doc in _iter_sidecars(root):
        for d in doc.get("details") or []:
            if d.get("status") != "fail":
                continue
            reasons = "".join(d.get("reasons") or [])
            if _match_signature(by_gate, d.get("gate"), reasons):
                continue
            key = (d.get("gate"), reasons[:80])
            clusters[key] = clusters.get(key, 0) + 1
    if not clusters:
        print("✅ 无 unclassified，无需提案")
        return 0
    print(f"🔧 unclassified 聚簇提案（{len(clusters)} 簇）——人判后粘入 ledger entries：\n")
    for (gate, reasons), cnt in sorted(clusters.items(), key=lambda x: -x[1]):
        print(f"  - signature: {gate}#<subcheck>:<reason_class>   # {cnt} 处")
        print(f"    gate: {gate}")
        print(f"    match: {json.dumps(reasons[:24], ensure_ascii=False)}   # ← 首例前缀，人判改稳定子串")
        print(f"    count: {cnt}")
        print(f"    status: <landed|inflight|pending>   # 人判：陷阱=landed/inflight；环境态/真错=pending")
        print(f"    fix: \"<根因与修法一句话>\"")
        print(f"    # reasons 首例: {reasons[:110]}")
        print()
    return len(clusters)


def field_acceptance(root: Path, ledger: list, state: dict) -> list:
    """C-4 簿记核心：当窗新 sidecar → 暴露探针/复现计数 + 窗口递减 + 关闭/展期/降级
    + warn 翻转。state 原地更新（调用方 save_acceptance 落盘）；返回输出行。

    窗口 = sidecar timestamp 日期；「新窗」= 窗口键 > state.seen_through。无新
    sidecar → 窗口不递减（同窗重复跑幂等安全：exposure/recurred 只累计当窗新件）。"""
    lines = []
    sigs = state.get("signatures") or {}
    open_sigs = {s: v for s, v in sigs.items() if v.get("status") == "open"}
    seen_through = str(state.get("seen_through") or "")
    fresh = [(sc, doc) for sc, doc in _iter_sidecars(root) if _window_key(doc) > seen_through]
    if not fresh:
        return [f"📐 field_acceptance: 无新 sidecar（窗口不递减，seen_through={seen_through or '—'}）"]
    new_through = max(_window_key(doc) for _, doc in fresh)
    by_gate = _by_gate_index(ledger)
    exposure = {k: 0 for k in _EXPOSURE_PROBES}
    recur = {s: 0 for s in open_sigs}
    warn_hit = 0
    for sc, doc in fresh:
        text = _report_text(sc)
        for k, rx in _EXPOSURE_PROBES.items():
            exposure[k] += len(rx.findall(text))
        if doc.get("bool_return_warn"):
            warn_hit += 1
        for d in doc.get("details") or []:
            if d.get("status") != "fail":
                continue
            hit = _match_signature(by_gate, d.get("gate"), "".join(d.get("reasons") or []))
            if hit in recur:
                recur[hit] += 1
    lines.append(f"📐 field_acceptance（窗 {new_through}，{len(fresh)} 份新 sidecar，warn命中{warn_hit}）：")
    for s, v in open_sigs.items():
        v["exposed"] = int(v.get("exposed") or 0) + exposure.get(v.get("probe"), 0)
        v["recurred"] = int(v.get("recurred") or 0) + recur.get(s, 0)
        v["window_left"] = int(v.get("window_left") or 0) - 1
        thr = int(v.get("threshold") or 0)
        if v["recurred"] > 0:
            lines.append(f"  🔴 {s}: 暴露{v['exposed']}/{thr}·复现{v['recurred']}·窗剩{v['window_left']}"
                         " —— 复现=已 landed 引擎的回归，按晋级条文处置（禁报告级修补）")
        elif v["exposed"] >= thr:
            v["status"] = "closed_pass"
            lines.append(f"  ✅ {s}: 暴露{v['exposed']}≥{thr}·零复现 → closed_pass"
                         "（现场假阳性方向已证；假阴性方向由 corpus+归档重放守）")
        elif v["window_left"] <= 0:
            if not v.get("extended"):
                v["extended"] = True
                v["window_left"] += 2
                lines.append(f"  ⏳ {s}: 窗口耗尽·暴露{v['exposed']}<{thr} → 展期一次（+2 cron）")
            else:
                v["status"] = "closed_downgraded"
                lines.append(f"  📉 {s}: 展期后仍暴露{v['exposed']}<{thr} → closed_downgraded"
                             "（单元已证·现场未证；转永久计数兜底，复发照样触发 strict/晋级）")
        else:
            lines.append(f"  … {s}: 暴露{v['exposed']}/{thr}·复现0·窗剩{v['window_left']}")
    warn = state.setdefault("warn_upgrade", {})
    if warn_hit == 0:
        warn["zero_hit_windows"] = int(warn.get("zero_hit_windows") or 0) + 1
        if not warn.get("flipped"):
            warn["flipped"] = True
            lines.append("  🔔 warn_upgrade: 当窗 bool_return_warn 零命中 → flipped=true"
                         "（verify_gates 下轮起按硬断言执法，verdict 中性）")
        else:
            lines.append(f"  🔔 warn_upgrade: zero_hit_windows={warn['zero_hit_windows']}（已 flipped）")
    else:
        lines.append(f"  🔔 warn_upgrade: 当窗 {warn_hit} 份有 bool_return_warn，不翻转"
                     f"（zero_hit_windows={warn.get('zero_hit_windows') or 0}）")
    state["seen_through"] = new_through
    return lines


def acceptance_status(state: dict) -> list:
    """只读状态行（报告模式首行区，与 engine_pending 并排）。"""
    sigs = state.get("signatures") or {}
    if not sigs:
        return []
    parts = []
    for s, v in sigs.items():
        st = v.get("status")
        tag = {"closed_pass": "✅已关闭", "closed_downgraded": "📉降级关闭"}.get(st, f"窗剩{v.get('window_left')}")
        parts.append(f"{s.rsplit(':', 1)[0]} 暴露{v.get('exposed')}/{v.get('threshold')}·复现{v.get('recurred')}·{tag}")
    lines = ["📐 field_acceptance: " + " | ".join(parts)]
    warn = state.get("warn_upgrade") or {}
    if warn:
        lines.append(f"🔔 warn_upgrade: zero_hit_windows={warn.get('zero_hit_windows') or 0}"
                     f"·flipped={bool(warn.get('flipped'))}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="TRAP_LEDGER 扫描（报告/增量拦截/现场验收簿记）")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="sidecar 扫描根目录（默认 ~/analysis_report）")
    ap.add_argument("--ledger", help="ledger yaml 路径（默认 repo references/trap_ledger.yaml）")
    ap.add_argument("--acceptance", help="验收簿记 yaml 路径（默认 repo references/trap_ledger_acceptance.yaml）")
    ap.add_argument("--strict", action="store_true",
                    help="增量拦截：任一 signature 当前计数 > ledger count 基线 → exit 1")
    ap.add_argument("--field-acceptance", action="store_true",
                    help="现场验收簿记（cron 收尾跑）：窗口/暴露/关闭/warn 翻转自动落账并写回")
    ap.add_argument("--propose", action="store_true",
                    help="半自动化入账（pending #5）：unclassified 按 gate×reasons 聚簇出签名提案草稿，人判后入 ledger")
    ap.add_argument("--inspect", action="store_true",
                    help="只读模式（审计专用）：--field-acceptance 只打印不写回——簿记写回仅限 cron 运行态")
    args = ap.parse_args()

    # 晋级欠账（裁决⑤ 2026-08-31）：root_cause=engine 未修存量——与扫哪个 root 无关，
    # 恒打一行（run_regression 尾部 echo 同源）。
    pending = engine_pending(args.ledger)
    print(f"⚙️ engine_pending（root_cause=engine 且未 landed）: {len(pending)} 条"
          + (f"——{'、'.join(e['signature'] for e in pending)}" if pending else ""))

    ledger = load_ledger(args.ledger)
    root = Path(args.root).expanduser()
    state = load_acceptance(args.acceptance)
    if args.propose:
        return 1 if propose(root, ledger) else 0
    for ln in acceptance_status(state):
        print(ln)
    if not ledger:
        print("⚠️  ledger 为空/未建——无执法面（报告模式 no-op）")
        return 0
    counts, unclassified = scan(root, ledger)
    if args.field_acceptance:
        for ln in field_acceptance(root, ledger, state):
            print(ln)
        if args.inspect:
            print("🔍 --inspect 只读：簿记未写回（写回仅限 cron 运行态，审计跑数一律带 --inspect）")
        else:
            save_acceptance(state, args.acceptance)
            print(f"📝 验收簿记已写回: {args.acceptance or 'repo references/trap_ledger_acceptance.yaml'}")

    print(f"扫描 {root}（{len(list(root.glob('**/*.verified.json')))} 份 sidecar，"
          f"{len(ledger)} 条 ledger）")
    regressions = []
    for e in ledger:
        sig = e["signature"]
        cur, base = counts.get(sig, 0), int(e.get("count") or 0)
        delta = cur - base
        flag = "🔴 新增" if delta > 0 else ("🟢" if cur == 0 else "  ")
        print(f"  {flag} {sig}: cur={cur} base={base} delta={delta:+d}"
              f" status={e.get('status')}{' blocked' if e.get('blocked') else ''}")
        if delta > 0:
            regressions.append(sig)
    if regressions:
        print(f"⚠️ 晋级条文（SKILL.md 约束3）：{len(regressions)} 条复发——第 2 次复发必须落引擎"
              f"（ledger 置 root_cause=engine + status=inflight→修后 landed），禁第 3 次报告级修补")
    if unclassified:
        print(f"  ⚪ unclassified FAIL {len(unclassified)} 处（台账未登记，只报告）：")
        for u in unclassified[:10]:
            print(f"     · {u}")
    if args.strict:
        if regressions:
            print(f"❌ strict 增量拦截：{len(regressions)} 条 signature 超基线（回归/复发）："
                  f"{regressions}")
            return 1
        print("✅ strict 通过：全 signature 计数 ≤ ledger 基线（无新增 FAIL）")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
