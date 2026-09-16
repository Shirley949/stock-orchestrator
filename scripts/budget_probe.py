#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批 1（流水架构 v1.1）预算表 v2 干跑探针（plan M-8）。

入参 snapshot 路径 → 跑预算表 v2 全部 baked 命令 → 输出「步×命令×实测 chars×预算」对拍表。
exit 1 当任一命令 rc≠0 或实测 > 预算 ×2（超线信号，禁现场放宽——回查投影命令是否手写膨胀）。

探针域边界（不入表、不算超线）：
  · exa/websearch 分量（c64 行 0~4.4K）= P2 检索期协变量，不在 snapshot 视图域；
  · c66 盘上结论段 = 报告文件域（非 snapshot）；panorama 实拉 3.4K 入表可测。
用法：
  python3 budget_probe.py /tmp/runner_snapshot_601208_modeA.json
"""
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SV = str(SCRIPT_DIR / "snapshot_view.py")
PANO = str(SCRIPT_DIR / "lib" / "capstone_panorama.py")

# 预算表 v2（plan 批 1b baked；chars=stdout 字节级长度）
# 行 = (步id, 说明, 命令列表, 预算 chars)；命令 = [snapshot_view 参数...] 或 ["PANO"]（panorama）
BUDGET_TABLE = [
    ("c60", "m0 分类投影", [["any", "classification", "--depth", "1"]], 900),
    ("c_m1", "m1 叙事辅证（可选）", [["--raw", "xq_market_voice.data.answers.d1_intel"]], 700),
    ("c61", "m2 财务四视图", [["cash_flow"], ["income"], ["balance"], ["mainfina"]], 9600),
    ("c62", "m25 对撞（可选）", [["--raw", "xq_market_voice.data.answers.d1_intel"]], 700),
    ("c63", "m3 技术投影", [
        ["kline"], ["technical"],
        ["any", "s3_fund_flow.data.fund_flow", "--depth", "1"],
        ["--raw", "xq_market_voice.data.answers.d5_moves"]], 6300),
    ("c64", "m4 消息面（exa 分量不在本探针域）", [
        ["news"], ["timeline"], ["xqvoice"],
        ["--raw", "s35_research_reports.data.layer1.em_reports_count"],
        ["any", "northbound.data.processed"]], 11200),
    ("c65", "m5 估值投影", [["valuation"], ["consensus"], ["peer"]], 5000),
    ("c66", "m6 capstone（盘上结论段不在本探针域）", [
        ["PANO"],
        ["--raw", "xq_conclusion_check.processed"],
        ["--raw", "xq_market_voice.data.answers.d3_bullbear"]], 10700),
    ("c_d4", "m9blk 股东回报+治理（c_d4+c_d5 两步合计）", [
        ["timeline"], ["annual"], ["holder"],
        ["any", "s_esg.data"], ["any", "governance"]], 5000),
    ("c67", "m7 风险投影（对冲注记可选项未含）", [
        ["any", "classification"], ["any", "s6_macro.data"],
        ["any", "s_margin.data"], ["any", "lhb"],
        ["--raw", "s_stock_evaluation.data.processed.conclusions"],
        ["--raw", "computed_metrics.tariff_vulnerability"],
        ["--raw", "computed_metrics.concentration_composite"],
        ["--raw", "xq_market_voice.data.answers.d6_risk"]], 6100),
    ("c68", "m8 局限（纯文本零拉取）", [], 0),
    ("c_m10", "m10 机构观点（白名单 --raw 小件按票增补）", [
        ["--raw", "xq_market_voice.data.answers.d2_analyst"]], 1600),
    ("c68b", "m12 速览聚合（status=ok 时）", [
        ["--raw", "xq_market_voice.processed.summary"]], 200),
]


def main():
    ap = argparse.ArgumentParser(description="预算表 v2 干跑探针（原子步②命令×实测×预算对拍）")
    ap.add_argument("snapshot", help="runner snapshot 路径（.json）")
    ap.add_argument("--max-factor", type=float, default=2.0,
                    help="超线倍数阈值（默认 2×预算；禁现场放宽，改投影命令才是修法）")
    args = ap.parse_args()
    snap = Path(args.snapshot).expanduser()
    if not snap.exists():
        print(f"❌ snapshot 不存在: {snap}")
        sys.exit(1)

    total, budget_sum = 0, 0
    bad = []
    print(f"{'步':<12} {'命令':<58} {'实测':>8} {'预算':>7}  判")
    print("-" * 96)
    for sid, note, cmds, budget in BUDGET_TABLE:
        step_chars = 0
        for cmd in cmds:
            if cmd == ["PANO"]:
                argv = [sys.executable, PANO, "--snapshot", str(snap)]
            else:
                argv = [sys.executable, SV, str(snap)] + cmd
            p = subprocess.run(argv, capture_output=True, text=True)
            out_len = len(p.stdout or "")
            step_chars += out_len
            disp = "capstone_panorama --snapshot" if cmd == ["PANO"] else "$SV " + " ".join(cmd)
            flag = "✅" if p.returncode == 0 else "❌rc"
            print(f"{sid:<12} {disp:<58} {out_len:>8} {'':>7}  {flag}")
            if p.returncode != 0:
                bad.append((sid, disp, f"rc={p.returncode}: {(p.stderr or '')[:120]}"))
        total += step_chars
        budget_sum += budget
        over = budget * args.max_factor
        if step_chars > over:
            flag = "❌超线"
            bad.append((sid, "STEP-TOTAL", f"{step_chars} > {over:.0f}（{args.max_factor}×预算 {budget}）"))
        elif cmds:
            print(f"{sid:<12} {'└ 步合计':<58} {step_chars:>8} {budget:>7}  {'⚠️近线' if step_chars > budget else '✅'}")
    print("-" * 96)
    print(f"合计（探针域）: 实测 {total} / 预算 {budget_sum}（exa 分量、盘上结论段不在域）")
    if bad:
        print(f"\n❌ {len(bad)} 项超线/rc 失败：")
        for sid, what, detail in bad:
            print(f"  [{sid}] {what}: {detail}")
        sys.exit(1)
    print("✅ 预算表 v2 全部命令 rc=0 且 ≤2× 预算")
    sys.exit(0)


if __name__ == "__main__":
    main()
