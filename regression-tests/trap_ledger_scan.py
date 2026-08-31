#!/usr/bin/env python3
"""trap_ledger_scan — 陷阱台账扫描器（E10）：sidecar FAIL 按 signature 分类计数。

用法：
  python3 trap_ledger_scan.py                       # 报告模式：线上语料计数 + delta
  python3 trap_ledger_scan.py --strict              # 增量拦截：任一 entry cur>count 基线 → exit 1
  python3 trap_ledger_scan.py --root <dir> [--ledger <yaml>]
                                                    # 扫沙箱（回归接线用，沙箱自带 ledger）

strict 语义（P12 裁定，勿改回直拦）：72 份存量 sidecar 中 10 份含历史 failed_gates
——历史 FAIL 是预期存在，count 基线即冻结时的实测量；仅**新增**（cur > count）才 exit 1。
回归（run_regression.sh）接线的是沙箱 fixtures，线上语料走非 strict 报告模式。

匹配：sidecar details[] 中 status==fail 的项，gate 相等且 reasons 拼接串命中 entry.match
正则（无 match=gate 级兜底）。旧 sidecar 无 reasons 时按 gate 兜底计。
未命中任何 entry 的 FAIL = unclassified（只报告，不拦——台账未登记非回归）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
from trap_ledger import load_ledger, engine_pending  # noqa: E402

DEFAULT_ROOT = Path("~/analysis_report").expanduser()


def scan(root: Path, ledger: list) -> tuple:
    """返回 (per_signature 计数, unclassified 清单)。"""
    counts = {e["signature"]: 0 for e in ledger}
    by_gate = {}
    for e in ledger:
        by_gate.setdefault(e.get("gate"), []).append(e)
    unclassified = []
    for sc in sorted(root.glob("**/*.verified.json")):
        try:
            doc = json.loads(sc.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for d in doc.get("details") or []:
            if d.get("status") != "fail":
                continue
            reasons = "".join(d.get("reasons") or [])
            hit = None
            for e in by_gate.get(d.get("gate"), []):
                m = e.get("match")
                if not m or re.search(m, reasons):
                    hit = e["signature"]
                    break
            if hit:
                counts[hit] += 1
            else:
                unclassified.append(f"{d.get('gate')}@{sc.name}")
    return counts, unclassified


def main() -> int:
    ap = argparse.ArgumentParser(description="TRAP_LEDGER 扫描（报告/增量拦截）")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="sidecar 扫描根目录（默认 ~/analysis_report）")
    ap.add_argument("--ledger", help="ledger yaml 路径（默认 repo references/trap_ledger.yaml）")
    ap.add_argument("--strict", action="store_true",
                    help="增量拦截：任一 signature 当前计数 > ledger count 基线 → exit 1")
    args = ap.parse_args()

    # 晋级欠账（裁决⑤ 2026-08-31）：root_cause=engine 未修存量——与扫哪个 root 无关，
    # 恒打一行（run_regression 尾部 echo 同源）。
    pending = engine_pending(args.ledger)
    print(f"⚙️ engine_pending（root_cause=engine 且未 landed）: {len(pending)} 条"
          + (f"——{'、'.join(e['signature'] for e in pending)}" if pending else ""))

    ledger = load_ledger(args.ledger)
    root = Path(args.root).expanduser()
    if not ledger:
        print("⚠️  ledger 为空/未建——无执法面（报告模式 no-op）")
        return 0
    counts, unclassified = scan(root, ledger)

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
