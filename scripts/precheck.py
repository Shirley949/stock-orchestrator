#!/usr/bin/env python3
"""
precheck.py — 数据拉取完成后的停机检查（PR 7）

在 runner 跑完后、报告生成前调用。
检查 snapshot 中的 _critical_failure 字段，决定是否允许继续。

用法:
  python precheck.py <snapshot_path>

退出码:
  0 = 数据充足，可以继续
  1 = 数据大面积失败，禁止生成报告
  2 = snapshot 文件不存在或格式错误
"""

import json
import sys


def precheck_critical_failure(snapshot_path: str) -> bool:
    """
    检查 snapshot 是否标记了 critical_failure。
    返回 True 表示"数据充足，可以继续"。
    返回 False 表示"数据不足，必须停机"。
    """
    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
    except FileNotFoundError:
        print(f"🔴 snapshot 文件不存在: {snapshot_path}", file=sys.stderr)
        return False
    except json.JSONDecodeError as e:
        print(f"🔴 snapshot 格式错误: {e}", file=sys.stderr)
        return False

    # 检查 _critical_failure 标记
    if snapshot.get("_critical_failure"):
        failure_summary = snapshot.get("_failure_summary", [])
        failed_scenes = []
        for scene in ["s1_financial", "s2_quote_kline", "s5_events"]:
            scene_data = snapshot.get(scene, {}).get("data", {})
            if scene_data and all(
                v.get("status") not in ("ok", "cached")
                for v in scene_data.values()
                if isinstance(v, dict)
            ):
                failed_scenes.append(scene)

        print("🔴 数据拉取大面积失败，禁止生成报告", file=sys.stderr)
        print(f"   失败场景: {failed_scenes}", file=sys.stderr)
        print(f"   失败摘要 ({len(failure_summary)} 条):", file=sys.stderr)
        for w in failure_summary[:5]:
            print(f"     - {w[:100]}", file=sys.stderr)
        if len(failure_summary) > 5:
            print(f"     ... 还有 {len(failure_summary) - 5} 条", file=sys.stderr)
        return False

    # 检查核心场景是否有至少一个成功
    core_scenes = ["s1_financial", "s2_quote_kline", "s5_events"]
    has_any_data = False
    for scene in core_scenes:
        scene_data = snapshot.get(scene, {}).get("data", {})
        for val in scene_data.values():
            if isinstance(val, dict) and val.get("status") in ("ok", "cached"):
                has_any_data = True
                break
        if has_any_data:
            break

    if not has_any_data:
        print("🔴 核心场景无任何有效数据，禁止生成报告", file=sys.stderr)
        return False

    # 检查数据收单
    checklist = snapshot.get("s10_checklist", {})
    completed = checklist.get("completed", 0)
    total = checklist.get("total", 12)
    missing = checklist.get("missing", [])

    if completed < 4:
        print(f"⚠️ 数据收单不足: {completed}/{total} 项完成", file=sys.stderr)
        print(f"   缺失: {missing}", file=sys.stderr)
        # 不阻塞，但发出警告

    print(f"✅ 数据预检通过 ({completed}/{total} 项完成)", file=sys.stderr)
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python precheck.py <snapshot_path>", file=sys.stderr)
        sys.exit(2)

    snapshot_path = sys.argv[1]
    if precheck_critical_failure(snapshot_path):
        sys.exit(0)
    else:
        sys.exit(1)
