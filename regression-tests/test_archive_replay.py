#!/usr/bin/env python3
"""test_archive_replay — 归档(报告↔快照) gate verdict 回放：基线冻结 + 零翻转比较。

零翻转锚点（诊断契约 v2 plan S0/S8）：引擎改动（G55/G56 收集化、G62 表头签名、
G63 分位剥离、G30#5 否定窗、21+ 门 reason 补线、diag 管线）不得改变任何归档对的
gate verdict——EXPECTED_FLIPS 白名单外逐 gate 相等；白名单 = 有意语义变更逐条裁决。

用法：
  python3 test_archive_replay.py --write-baseline      # S0b：引擎改动前冻结
  python3 test_archive_replay.py --compare <baseline>  # S2 每步后 / S8 总闸
  python3 test_archive_replay.py                       # 冒烟：配对统计 + 当前向量自洽

配对规则（P2 钉死，勿放宽——宽松配对会数出 149 对）：
  主报告 = <dir>/analysis_report*.md 且排除 *_publish.md / token_audit*
  快照   = 报告名日期(20\\d{6}) → sidecar timestamp 日期 → 同代码最新档
  profile = snapshot.mode=="B" → profile_quick，否则 profile_full

实现合同：
  - import verify_gates.verify_gates 函数直调——禁走 CLI（CLI 会把 sidecar 覆写
    到归档报告旁，污染语料）
  - gate_vector 只含本次执行的活跃门（status∈pass/fail/error；auto_pass 不记）
  - 语料缺失 → SKIP exit 0（仿 test_b_head_g71）；<30 对 stderr 告警
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "scripts"))
sys.path.insert(0, str(_HERE.parent / "scripts" / "lib"))

from verify_gates import verify_gates  # noqa: E402  函数直调，禁 CLI

CORPUS_DIR = Path(os.path.expanduser("~/.cache/skill-snapshots/full"))
REPORT_ROOT = Path(os.path.expanduser("~/analysis_report"))
BASELINE_PATH = _HERE / "fixtures" / "archive_replay_baseline.json"
MIN_PAIRS = 30          # <30 对 = 语料意外缩水，stderr 告警（仍继续）

# 有意语义变更白名单：{(gate, pair_id): "old→new 裁决理由（记 REFACTOR_LOG）"}。
# S2 各步出现预期翻转时逐条登记；未登记的翻转 = 回归 bug，--compare exit 1。
EXPECTED_FLIPS = {}


def _pair_candidates():
    """严格配对（P2 规则）。返回 [(pair_id, report_path, snapshot_path, profile)]。"""
    snaps = {}
    for p in sorted(CORPUS_DIR.glob("*.json")):
        code, date = p.stem.split("_")[0], p.stem.split("_")[1]
        snaps.setdefault(code, []).append((date, p))
    for c in snaps:
        snaps[c].sort()

    pairs = []
    for d in sorted(REPORT_ROOT.iterdir()):
        if not d.is_dir():
            continue
        m = re.search(r"(\d{6})", d.name)
        if not m or m.group(1) not in snaps:
            continue
        mains = sorted(f for f in d.glob("analysis_report*.md")
                       if not f.name.endswith("_publish.md") and "token_audit" not in f.name)
        for rpt in mains:
            code = m.group(1)
            # 快照定位：报告名日期 → sidecar timestamp 日期 → 同代码最新档
            dm = re.search(r"(20\d{6})", rpt.name)
            cand = [s for dt, s in snaps[code] if dm and dt == dm.group(1)]
            if not cand:
                sc = rpt.with_suffix(".verified.json")
                if sc.exists():
                    ts = json.loads(sc.read_text(encoding="utf-8")).get("timestamp", "")
                    dd = re.search(r"20\d{6}", ts.replace("-", ""))
                    if dd:
                        cand = [s for dt, s in snaps[code] if dt == dd.group(0)]
            snap = cand[0] if cand else snaps[code][-1][1]
            profile = "profile_quick" if json.loads(
                snap.read_text(encoding="utf-8")).get("mode") == "B" else "profile_full"
            pairs.append((f"{code}:{d.name}:{rpt.name}", rpt, snap, profile))
    return pairs


def _gate_vector(report_path: Path, snapshot_path: Path, profile: str) -> dict:
    """单对回放 → {profile, verdict, failed_gates, gate_vector}。"""
    report = report_path.read_text(encoding="utf-8")
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    res = verify_gates(report, data, profile)
    vec = {d["gate"]: d["status"] for d in res["details"] if d["status"] != "auto_pass"}
    return {"profile": res["profile"], "verdict": res["verdict"],
            "failed_gates": sorted(res["failed_gates"]), "gate_vector": vec}


def _collect() -> dict:
    out = {}
    for pid, rpt, snap, prof in _pair_candidates():
        try:
            out[pid] = _gate_vector(rpt, snap, prof)
        except Exception as e:  # 单对崩不拖垮整轮（error 也进向量，compare 可见）
            out[pid] = {"profile": prof, "verdict": "REPLAY_ERROR",
                        "failed_gates": [], "gate_vector": {}, "error": str(e)}
    return out


def _write_baseline():
    vec = _collect()
    if len(vec) < MIN_PAIRS:
        print(f"⚠️  配对仅 {len(vec)} 对（<{MIN_PAIRS}），先核对语料再冻结", file=sys.stderr)
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(vec, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    modes = {}
    for v in vec.values():
        modes[v["verdict"]] = modes.get(v["verdict"], 0) + 1
    print(f"✅ 基线冻结：{len(vec)} 对 → {BASELINE_PATH}")
    print(f"   verdict 分布：{modes}｜失败门合计 "
          f"{sum(len(v['failed_gates']) for v in vec.values())} 门次")


def _compare(baseline_path: Path) -> int:
    base = json.loads(baseline_path.read_text(encoding="utf-8"))
    cur = _collect()
    only_base, only_cur = set(base) - set(cur), set(cur) - set(base)
    for pid in sorted(only_base):
        print(f"⚠️  基线有、当前无（语料变动）：{pid}")
    flips, allowed = [], []
    for pid in sorted(set(base) & set(cur)):
        b, c = base[pid], cur[pid]
        for gate in sorted(set(b["gate_vector"]) | set(c["gate_vector"])):
            old, new = b["gate_vector"].get(gate, "absent"), c["gate_vector"].get(gate, "absent")
            if old == new:
                continue
            key = (gate, pid)
            if key in EXPECTED_FLIPS:
                allowed.append((pid, gate, old, new, EXPECTED_FLIPS[key]))
            else:
                flips.append((pid, gate, old, new))
        if b["verdict"] != c["verdict"] and not any(
                f[0] == pid for f in flips) and not any(a[0] == pid for a in allowed):
            flips.append((pid, "VERDICT", b["verdict"], c["verdict"]))
    print(f"回放 {len(set(base) & set(cur))} 对：白名单翻转 {len(allowed)}，意外翻转 {len(flips)}")
    for pid, gate, old, new, why in allowed:
        print(f"  ⚠️ allowed {gate} {old}→{new} @ {pid}（{why}）")
    for pid, gate, old, new in flips:
        print(f"  ❌ FLIP {gate} {old}→{new} @ {pid}")
    if flips:
        print("❌ 零翻转校验失败：存在白名单外的 verdict 变化")
        return 1
    print("✅ 零翻转校验通过（白名单外逐 gate 相等）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="归档 gate verdict 回放（零翻转锚点）")
    ap.add_argument("--write-baseline", action="store_true", help="冻结当前 verdict 向量")
    ap.add_argument("--compare", metavar="BASELINE", help="与基线逐 gate 比较")
    args = ap.parse_args()

    if not CORPUS_DIR.exists() or not REPORT_ROOT.exists():
        print("SKIP：语料缺席（~/.cache/skill-snapshots/full 或 ~/analysis_report）")
        return 0
    pairs = _pair_candidates()
    print(f"配对 {len(pairs)} 对（严格规则；< {MIN_PAIRS} 对将告警）")
    if len(pairs) < MIN_PAIRS:
        print(f"⚠️  配对 {len(pairs)} 对 < {MIN_PAIRS}，语料可能缩水", file=sys.stderr)

    if args.write_baseline:
        _write_baseline()
        return 0
    if args.compare:
        return _compare(Path(args.compare))
    # 冒烟：当前向量可产 + 统计
    vec = _collect()
    err = [k for k, v in vec.items() if v["verdict"] == "REPLAY_ERROR"]
    print(f"冒烟：{len(vec)} 对回放完成，REPLAY_ERROR {len(err)} 对")
    for k in err[:5]:
        print(f"  ⚠️  {k}: {vec[k].get('error')}")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
