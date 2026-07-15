#!/usr/bin/env python3
"""
verify_gates.py — Gate 硬关卡校验脚本（单一引擎，单一报告出口）

仓库内唯一的 Gate 引擎（+ lib/gate_definitions.py，G1, G6–G29, G30, G31，共 27）。第二套引擎（gate_checker.py
等）已删除（归档于父仓库 git 历史）。本脚本既是校验器，也是分数的唯一生产者：默认产出 sidecar
（<report>.verified.json），m11 区放指针行引用它，禁止手填分数。

核心能力：
  - verify_gates(): 按 Profile 逐 Gate 校验；compute_self_score() 三维自评分
    （数据覆盖 40% + Gate 通过 40% + SOURCE 溯源 20%）注入 result。
  - 默认写 sidecar <report>.verified.json（分数/verdict/failed_gates 唯一真相源）。
  - --check-pointer: 只读复检出口契约（指针行 + sidecar 有效 + PASS + self_score≥80 + 新鲜）。
  - --report-only: 纯文本模式（data={}），开发用，不能作为最终输出校验。

用法:
  python verify_gates.py --report R.md --data-snapshot D.json --profile full
  python verify_gates.py --report R.md --check-pointer   # 只读复检出口契约

退出码:
  0 = verdict=PASS（失败数 ≤ fail_threshold）
  1 = verdict=FAIL（失败 Gate 超出阈值），报告必须重做
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# 添加 lib 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from gate_definitions import (
    ALL_GATES, GATE_CHECKERS, GATE_DESCS, GATE_WEIGHTS,
    PROFILES, compute_score, get_profile, compute_self_score
)


def load_report(report_path: str) -> str:
    """加载报告内容"""
    path = Path(report_path)
    if not path.exists():
        print(f"❌ 报告文件不存在: {report_path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def load_data_snapshot(data_path: str) -> dict:
    """加载数据快照（可选）"""
    if not data_path:
        return {}
    path = Path(data_path)
    if not path.exists():
        print(f"⚠️  数据快照文件不存在: {data_path}，仅基于报告内容校验")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_gates(report: str, data: dict, profile_name: str) -> dict:
    """
    执行 Gate 校验。

    返回:
    {
        "profile": "profile_full",
        "total_gates": 20,
        "active_gates": 20,
        "auto_passed": 0,
        "passed": 15,
        "failed": 3,
        "errors": 2,
        "score": 85,
        "threshold": 3,
        "verdict": "PASS" | "FAIL",
        "details": [
            {"gate": "G1", "status": "pass|fail|auto_pass|error", "desc": "...", "weight": 2},
            ...
        ],
        "failed_gates": ["G16", "G17", "G19"],
        "action_required": ["G16: 订单Layer6核对...", ...]
    }
    """
    profile = get_profile(profile_name)
    active_gates = profile["gates"]
    auto_pass_gates = set(profile["auto_pass"])

    details = []
    passed = []
    failed = []
    errors = []

    for gate in ALL_GATES:
        desc = GATE_DESCS.get(gate, "")
        weight = GATE_WEIGHTS.get(gate, 2)

        if gate not in active_gates:
            # 不在当前 Profile 的活跃 Gate 列表中
            continue

        if gate in auto_pass_gates:
            details.append({
                "gate": gate,
                "status": "auto_pass",
                "desc": desc,
                "weight": weight,
            })
            continue

        # 执行验证
        checker = GATE_CHECKERS.get(gate)
        if not checker:
            errors.append(gate)
            details.append({
                "gate": gate,
                "status": "error",
                "desc": desc,
                "weight": weight,
                "error": "无验证函数",
            })
            continue

        try:
            ok = checker(report, data)
            if ok:
                passed.append(gate)
                details.append({
                    "gate": gate,
                    "status": "pass",
                    "desc": desc,
                    "weight": weight,
                })
            else:
                failed.append(gate)
                details.append({
                    "gate": gate,
                    "status": "fail",
                    "desc": desc,
                    "weight": weight,
                })
        except Exception as e:
            errors.append(gate)
            details.append({
                "gate": gate,
                "status": "error",
                "desc": desc,
                "weight": weight,
                "error": str(e),
            })

    # 计算自评分
    score = compute_score(passed, failed, profile)

    # 判定
    fail_count = len(failed) + len(errors)
    
    # P0 fix: weight≥3 gates 硬阻断（不受 fail_threshold 影响）
    # GATE_WEIGHTS 用模块级 import（line 36-39），勿在此函数内再 import——
    # 函数内 `from .gate_definitions import GATE_WEIGHTS` 会让该名变局部变量，
    # 遮蔽模块级绑定，导致上方 line 98 `GATE_WEIGHTS.get(...)` UnboundLocalError。
    critical_failures = [g for g in failed + errors if GATE_WEIGHTS.get(g, 0) >= 3]
    
    if critical_failures:
        verdict = "FAIL"
    else:
        verdict = "PASS" if fail_count <= profile["fail_threshold"] else "FAIL"

    base_result = {
        "profile": profile_name,
        "profile_desc": profile["description"],
        "total_gates": len(ALL_GATES),
        "active_gates": len(active_gates),
        "auto_passed": len(auto_pass_gates),
        "passed": len(passed),
        "failed": len(failed),
        "errors": len(errors),
        "score": score,
        "threshold": profile["fail_threshold"],
        "verdict": verdict,
        "details": details,
        "failed_gates": failed + errors,
        "action_required": [
            f"{g}: {GATE_DESCS.get(g, '未知')}" for g in failed + errors
        ],
    }

    # A2: 脚本化三维自评分（数据覆盖 / Gate通过 / SOURCE溯源）—— 禁止手填
    base_result["self_score"] = compute_self_score(report, data, base_result)

    return base_result


def print_report(result: dict):
    """打印校验报告"""
    print("=" * 60)
    print(f"Gate 校验报告 | Profile: {result['profile']} ({result['profile_desc']})")
    print("=" * 60)
    print()

    # 逐 Gate 输出
    for d in result["details"]:
        status_icon = {
            "pass": "✅",
            "fail": "❌",
            "auto_pass": "⚪",
            "error": "⚠️",
        }.get(d["status"], "?")

        line = f"{status_icon} {d['gate']}: {d['desc']}"
        if d["status"] == "error":
            line += f" [ERROR: {d.get('error', '')}]"
        print(line)

    # 汇总
    print()
    print("-" * 60)
    print(f"通过: {result['passed']} | 失败: {result['failed']} | "
          f"错误: {result['errors']} | auto_pass: {result['auto_passed']}")
    print(f"自评分: {result['score']} / 100")
    print(f"失败阈值: {result['threshold']}")

    # A2: 三维脚本化自评分摘要（禁止手填）
    ss = result.get("self_score")
    if ss:
        cov = ss["dimensions"]["data_coverage"]
        src = ss["dimensions"]["source_traceability"]
        print(f"自评分(v2.1脚本): {ss['score']} / 100  "
              f"[数据覆盖 {cov['score']}% ({cov['hit']}/{cov['total']}) · "
              f"Gate {ss['dimensions']['gate_pass']['score']} · "
              f"溯源 {src['score']}% (snap={src['snapshot_tags']} web={src['websearch_tags']})]")
    print()

    if result["verdict"] == "PASS":
        print(f"✅ 校验通过（失败 {result['failed'] + result['errors']}，"
              f"阈值 {result['threshold']}）")
        if result["failed_gates"]:
            print("⚠️  以下 Gate 未通过，请在'分析局限性'中标注：")
            for action in result["action_required"]:
                print(f"  - {action}")
    else:
        print(f"🔴 校验失败（失败 {result['failed'] + result['errors']}，"
              f"超出阈值 {result['threshold']}）")
        print("报告必须重做或补全以下项后再输出：")
        for action in result["action_required"]:
            print(f"  - {action}")

    print("-" * 60)


def check_pointer(report_path: str):
    """只读校验模式：不重跑 Gate，只确认报告出口契约成立。

    契约（任一失败 sys.exit(1)）：
      1. 报告含指针行 [verified: ... | see <name>.verified.json]
      2. sidecar <report_stem>.verified.json 存在
      3. sidecar verdict == "PASS"
      4. sidecar self_score.score >= 80
      5. sidecar mtime >= report mtime（报告改动后必须重新校验，防过期）
    """
    report_text = load_report(report_path)
    report_p = Path(report_path)

    # 1. 指针行
    if not re.search(r"\[verified:.*see\s+\S+\.verified\.json\]", report_text):
        print("❌ 指针校验失败：报告缺少指针行 [verified: ... | see <name>.verified.json]")
        print("   m11 区必须放指针行，禁止手填分数。")
        sys.exit(1)

    # 2. sidecar 存在（派生路径：report.md → report.verified.json）
    sidecar = report_p.with_suffix(".verified.json")
    if not sidecar.exists():
        print(f"❌ 指针校验失败：sidecar 不存在 {sidecar}")
        print("   先运行 verify_gates.py（不带 --check-pointer）产出 sidecar。")
        sys.exit(1)

    result = json.loads(sidecar.read_text(encoding="utf-8"))

    # 3. verdict
    if result.get("verdict") != "PASS":
        print(f"❌ 指针校验失败：sidecar verdict={result.get('verdict')}（需 PASS）")
        print(f"   失败 Gate：{result.get('failed_gates')}")
        sys.exit(1)

    # 4. self_score >= 80
    ss = result.get("self_score", {})
    if ss.get("score", 0) < 80:
        print(f"❌ 指针校验失败：self_score={ss.get('score')} < 80")
        sys.exit(1)

    # 5. 新鲜度
    if sidecar.stat().st_mtime < report_p.stat().st_mtime:
        print("❌ 指针校验失败：sidecar 比报告旧（报告已改动但未重新校验）")
        sys.exit(1)

    print(f"✅ 指针校验通过：verdict=PASS self_score={ss.get('score')} "
          f"sidecar={sidecar.name}")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Gate 硬关卡校验脚本")
    parser.add_argument("--report", required=True, help="报告文件路径（.md）")
    parser.add_argument("--data-snapshot", help="数据快照文件路径（.json，可选）")
    parser.add_argument("--profile", default="full",
                         choices=["full", "quick"],
                        help="Gate Profile（默认 full）")
    parser.add_argument("--output", help="输出 JSON 结果文件路径（可选）")
    parser.add_argument("--report-only", action="store_true",
                        help="纯文本模式：忽略 snapshot，仅基于报告文本校验 "
                             "（吸收 quality/runner.py 的文本模式，消除双引擎）。"
                             "开发用，不能作为最终输出校验。")
    parser.add_argument("--quiet", action="store_true", help="静默模式，仅输出 JSON")
    parser.add_argument("--check-pointer", action="store_true",
                        help="只读校验模式：不重跑 Gate，只确认报告出口契约"
                             "（指针行 + sidecar 有效 + PASS + self_score≥80 + 新鲜）。"
                             "c70 打勾前的强制关卡。")
    parser.add_argument("--no-sidecar", action="store_true",
                        help="禁用 sidecar 自动写入（默认写 <report>.verified.json）")
    args = parser.parse_args()

    # 指针校验模式：只读，独立分支，不重跑 Gate
    if args.check_pointer:
        check_pointer(args.report)

    # 加载输入
    report = load_report(args.report)
    data = load_data_snapshot(args.data_snapshot)
    if args.report_only:
        data = {}  # 纯文本模式：禁用数据感知 Gate（等同旧 quality runner 行为）

    # 执行校验
    profile_name = f"profile_{args.profile}"
    result = verify_gates(report, data, profile_name)

    # 输出
    if not args.quiet:
        print_report(result)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        if not args.quiet:
            print(f"\n📝 详细结果已写入: {args.output}")

    # sidecar（默认写）：单一出口的核心产物，c70 打勾与 --check-pointer 都依赖它
    if not args.no_sidecar:
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        sidecar_path = Path(args.report).with_suffix(".verified.json")
        sidecar_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.quiet:
            print(f"\n📝 sidecar 已写入: {sidecar_path}")

    # 退出码
    if result["verdict"] == "FAIL":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
