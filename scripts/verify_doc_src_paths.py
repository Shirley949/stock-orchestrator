#!/usr/bin/env python3
"""verify_doc_src_paths.py —— 文档 [src:] 路径机器校验器（failure-family R10 / F5+F6 机制层）。

职责：模块文档教作者写的每一条 `[src:]` 路径，必须在至少一份真实快照上 dot-split 可解析
（G21 同款语义）——「散文承载合同无校验器」的机制补位。手写路径 8 处硬 bug（F5）的拦新增闸。

语义（镜像 check_g21，单一实现原则：解析规则与 G21 逐字符一致，勿单方面演化）：
  · `[src: snapshot.<path>]` / 无前缀合法 scene（s\d+_\w+|valuation_\w+|consensus_forecast|
    computed_metrics|s36_\w+|s55_\w+|web_research_findings 开头）→ 按 `.` 切段逐层 dict.get；
  · `[src: websearch XXX]` 非快照路径，跳过；
  · `[]` 记法（items[]/data_full[N]）在 src 标签内 = 不解析（双轨制：[] 仅限契约键/散文）；
  · 行内含「仅当」= 条件性路径标注（R10 规范），两档不通降级 WARN 不算 error。

判定：一条路径在**全部**传入快照上都不通 = error（A/B 多快照任一可解析即通过）。
用法：
  python3 verify_doc_src_paths.py [--doc-root DIR] [--data-snapshot SNAP.json ...]
默认快照 = regression-tests/parity/corpus 冻结金票（确定性、仓库内）；B 专属路径用
--data-snapshot 传一份真实 B 快照补判。exit 0=零 error。
"""
import argparse
import glob
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DOC_ROOT = os.path.expanduser(
    "~/.hermes/skills/stock-analysis/stock-analysis-quality/references")
DEFAULT_SNAP_GLOB = os.path.join(HERE, "..", "regression-tests", "parity", "corpus",
                                 "*_processed_golden.json.gz")
B_GOLDEN_GLOB = os.path.join(HERE, "..", "regression-tests", "fixtures",
                             "*_modeB_golden.json.gz")
# 条件性路径标注（R10 规范「模板路径旁必标『仅当 X 存在』」）的等效标记词：
# 文档实测三式——「仅当…」「⚠️ 条件性：」「…时禁标此 src」任一出现即降级 WARN
CONDITIONAL_MARKERS = ("仅当", "条件性", "禁标")

# 与 check_g21 同款三式（勿单方面演化——解析合同见 m11 G21 ⑥ 双轨制）
SNAPSHOT_PAT = re.compile(r'\[src:\s*snapshot\.([^\]]+)\]')
BARE_SCENE_PAT = re.compile(
    r'\[src:\s*((?:s\d+_\w+|valuation_\w+|consensus_forecast|computed_metrics'
    r'|s36_\w+|s55_\w+|web_research_findings)\.[^\]]+)\]')


def resolve(snapshot, path):
    """G21 同款 dot-split：逐段 dict.get；list 段（'0' 等）仅在 dict 有该字面键时命中。"""
    current = snapshot
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def load_default_snapshots():
    snaps = []
    for p in sorted(glob.glob(DEFAULT_SNAP_GLOB)) + sorted(glob.glob(B_GOLDEN_GLOB)):
        snaps.append((os.path.basename(p), json.load(gzip.open(p))))
    return snaps


def scan_doc(path, snaps, errors, warns):
    """单文档扫描：收集 (行号, 路径) → 任一快照可解析即 ok；全不通→error（仅当→warn）。"""
    rel = os.path.relpath(path, os.path.expanduser("~"))
    text = open(path, encoding="utf-8").read()
    for i, ln in enumerate(text.splitlines(), 1):
        for pat in (SNAPSHOT_PAT, BARE_SCENE_PAT):
            for m in pat.finditer(ln):
                p = m.group(1)
                if "<" in p or ">" in p:
                    continue          # 散文占位符（snapshot.<路径>）非真实路径，非执法面
                if any(resolve(s, p) is not None for _, s in snaps):
                    continue
                entry = f"{rel}:{i}  [src: …{p}]  （{len(snaps)} 份快照全不通）"
                if any(k in ln for k in CONDITIONAL_MARKERS):
                    warns.append(entry + "  ← 行内已标条件性（R10 规范降级）")
                else:
                    errors.append(entry)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--doc-root", default=DEFAULT_DOC_ROOT)
    ap.add_argument("--data-snapshot", action="append", default=[],
                    help="额外真实快照 JSON 路径（可多次；B 专属路径需传 B 快照）")
    args = ap.parse_args()

    snaps = load_default_snapshots()
    for p in args.data_snapshot:
        snaps.append((os.path.basename(p), json.load(open(p))))
    if not snaps:
        print("❌ 无可用快照（冻结池空且未传 --data-snapshot）")
        sys.exit(1)

    docs = sorted(glob.glob(os.path.join(args.doc_root, "**", "*.md"), recursive=True))
    errors, warns = [], []
    n_tags = 0
    for d in docs:
        before = len(errors) + len(warns)
        scan_doc(d, snaps, errors, warns)
        # 统计该文档标记数（含 websearch——它跳过路径校验但计入覆盖面）
        n_tags += len(re.findall(r'\[src:[^\]]+\]', open(d, encoding="utf-8").read()))
        _ = before

    print(f"扫描 {len(docs)} 份文档 / {n_tags} 个 [src:] 标记 / {len(snaps)} 份快照")
    for w in warns:
        print(f"  ⚠️ {w}")
    if errors:
        print(f"❌ 坏路径 {len(errors)} 处（照抄必挂，修文档或标「仅当」）：")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    print(f"✅ 坏路径 0（warn={len(warns)}）")
    sys.exit(0)


if __name__ == "__main__":
    main()
