#!/usr/bin/env python3
"""diff_engine —— 双引擎 gate verdict 差分（WP 批零翻转证明的命名工具，2026-09-01 升格）。

用途（reason-only 批的权威验证器）：改 gate reason 面后，证明 **verdict 零翻转**。
两个引擎副本（旧=HEAD 原样 / 新=已改）对同一批（报告, 快照）输入对逐门求值，
diff verdict 向量——任何 FLIP（True↔False、正常↔CRASH）即退出码 1。

用法：
  # 造旧引擎副本（子进程求值，避免 sys.modules 缓存串味）：
  #   cp -r scripts /tmp/old_eng && git show HEAD:scripts/lib/gate_definitions.py \
  #     > /tmp/old_eng/lib/gate_definitions.py && find /tmp/old_eng -name __pycache__ -exec rm -rf {} +
  python3 scripts/diff_engine.py /tmp/old_eng scripts --gates g7,g8,g9
  python3 scripts/diff_engine.py /tmp/old_eng scripts --gates all        # 全 check_g*

配对（输入对构造，忠实性优先）：
  归档目录（默认 /home/ubuntu/analysis_report/analysis_report-*）×
  ① 目录内 runner_snapshot*.json（与报告**同期**，首选——cache 快照会被轮转清除，
    2026-09-01 实测：cache-only 配对 30 对 vs 目录内优先 49 对，后者超批2 基线 44）
  ② 兜底 live cache 该代码最新快照。
  报告 = sidecar（*.verified.json）的同名 .md；目录名尾 6 位数字 = 代码。

输出：per-pair verdict 分布 + flips 清单 + reason 升级计数（旧 n_reasons=0 → 新>0）。
exit 0 = 零翻转；exit 1 = 有翻转（阻断落码）；exit 2 = 用法错。
"""
import glob
import json
import os
import re
import subprocess
import sys

_EVAL = r'''
import json, sys, glob, os, re
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
import gate_definitions as gd
gates = sys.argv[2].split(",")
root = sys.argv[3]
out = {}
for d in sorted(glob.glob(os.path.join(root, "analysis_report-*"))):
    m = re.search(r"-(\d{6})(?:-mode\w+-\d+)?$", d)
    if not m: continue
    sides = glob.glob(os.path.join(d, "*.verified.json"))
    if not sides: continue
    stem = sides[0][:-len(".verified.json")]
    rpt_path = stem if stem.endswith(".md") else stem + ".md"
    if not os.path.exists(rpt_path): continue
    indir = sorted(glob.glob(os.path.join(d, "runner_snapshot*.json")))
    cands = indir or sorted(glob.glob(
        "/home/ubuntu/.cache/skill-snapshots/full/%s_*.json" % m.group(1)))
    if not cands: continue
    rpt = open(rpt_path, encoding="utf-8").read()
    try: snap = json.load(open(cands[-1]))
    except Exception: continue
    vec = {}
    for g in gates:
        fn = getattr(gd, "check_" + g, None)
        if fn is None: vec[g] = {"v": "NOFN"}; continue
        try:
            ret = fn(rpt, snap)
            vec[g] = {"v": bool(ret.get("passed")) if isinstance(ret, dict) else bool(ret),
                      "n": len(ret.get("reasons") or []) if isinstance(ret, dict) else 0}
        except Exception as e:
            vec[g] = {"v": "CRASH:" + type(e).__name__}
    out[os.path.basename(d)] = vec
print(json.dumps(out, ensure_ascii=False, sort_keys=True))
'''


def _dump(engine_dir: str, gates: str, root: str) -> dict:
    """子进程跑一份引擎（进程隔离 = 双 import 不串 sys.modules 缓存）。"""
    p = subprocess.run([sys.executable, "-c", _EVAL, engine_dir, gates, root],
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr[-2000:])
        sys.exit(2)
    return json.loads(p.stdout)


def _resolve_gates(new_dir: str, spec: str) -> str:
    if spec != "all":
        return spec
    # 全 check_g* 门清单以「新引擎」为准（新增门在旧引擎无实现 → 记 NOFN，不算翻转）
    names = []
    for f in glob.glob(os.path.join(new_dir, "lib", "gate_definitions.py")):
        src = open(f, encoding="utf-8").read()
        names = sorted(set(re.findall(r"^def (check_g\w+)\(", src, re.M)))
    return ",".join(n[len("check_"):] for n in names)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        sys.stderr.write(__doc__)
        return 2
    old_dir, new_dir = args[0], args[1]
    gates_spec = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--gates=")), "all")
    root = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--root=")),
                "/home/ubuntu/analysis_report")
    gates = _resolve_gates(new_dir, gates_spec)
    old, new = _dump(old_dir, gates, root), _dump(new_dir, gates, root)
    if old.keys() != new.keys():
        sys.stderr.write(f"配对集不一致: old={len(old)} new={len(new)}（引擎炸在枚举期）\n")
        return 2
    flips, crashes, upgrades, dist = [], 0, 0, {}
    for pair in old:
        for g in old[pair]:
            vo, vn = old[pair][g]["v"], new[pair][g]["v"]
            dist[(g, vo)] = dist.get((g, vo), 0) + 1
            if vo != vn:
                flips.append((pair, g, vo, vn))
            if isinstance(vo, str) or isinstance(vn, str):
                crashes += 1
            if old[pair][g].get("n") == 0 < new[pair][g].get("n", 0):
                upgrades += 1
    print(f"pairs={len(old)} gates={len(gates.split(','))} "
          f"evals={len(old) * len(gates.split(','))} flips={len(flips)} "
          f"crash-states={crashes} reason_upgrades={upgrades}")
    for pair, g, vo, vn in flips:
        print(f"  FLIP {pair} {g}: {vo} -> {vn}")
    dist_s = " ".join(f"{g}:{v}×{c}" for (g, v), c in sorted(dist.items()))
    print(f"  dist: {dist_s}")
    return 1 if flips else 0


if __name__ == "__main__":
    sys.exit(main())
