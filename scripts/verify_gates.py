#!/usr/bin/env python3
"""
verify_gates.py — Gate 硬关卡校验脚本
把 m11-gates.md 的 Gate 体系从"文档级"升级为"执行级"。

用法:
  python verify_gates.py --report /tmp/analysis_report.md --data-snapshot /tmp/analysis_data.json --profile full
  python verify_gates.py --report /tmp/analysis_report.md --profile quick

退出码:
  0 = 全部通过（或失败数在阈值内）
  1 = 失败 Gate 超出阈值，报告必须重做
"""

import argparse
import json
import sys
from pathlib import Path

# 添加 lib 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from gate_definitions import (
    ALL_GATES, GATE_CHECKERS, GATE_DESCS, GATE_WEIGHTS,
    PROFILES, compute_score, get_profile
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
    verdict = "PASS" if fail_count <= profile["fail_threshold"] else "FAIL"

    return {
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


def main():
    parser = argparse.ArgumentParser(description="Gate 硬关卡校验脚本")
    parser.add_argument("--report", required=True, help="报告文件路径（.md）")
    parser.add_argument("--data-snapshot", help="数据快照文件路径（.json，可选）")
    parser.add_argument("--profile", default="full",
                        choices=["full", "quick", "event_scan", "valuation"],
                        help="Gate Profile（默认 full）")
    parser.add_argument("--output", help="输出 JSON 结果文件路径（可选）")
    parser.add_argument("--quiet", action="store_true", help="静默模式，仅输出 JSON")
    args = parser.parse_args()

    # 加载输入
    report = load_report(args.report)
    data = load_data_snapshot(args.data_snapshot)

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

    # 退出码
    if result["verdict"] == "FAIL":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
