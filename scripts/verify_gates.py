#!/usr/bin/env python3
"""
verify_gates.py — Gate 硬关卡校验脚本（单一引擎，单一报告出口）

仓库内唯一的 Gate 引擎（+ lib/gate_definitions.py，G1, G6–G29, G30, G31, G32, G33，共 29）。第二套引擎（gate_checker.py
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
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# 添加 lib 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from gate_definitions import (
    ALL_GATES, GATE_CHECKERS, GATE_DESCS, GATE_HINTS, GATE_WEIGHTS, GATE_REGISTRY,
    PROFILES, compute_score, get_profile, compute_self_score
)
from trap_ledger import load_acceptance  # noqa: E402  C-4 warn→硬断言翻转位

# C-4：翻转位缓存（mtime 感知——簿记文件低频写，热路径零 IO 放大）
_ACC_STATE = {"path": None, "mtime": None, "flipped": False}
_ACC_OVERRIDE_PATH = None   # 测试注入点（test_field_acceptance 指向临时状态文件）


def _acceptance_flipped() -> bool:
    p = Path(_ACC_OVERRIDE_PATH) if _ACC_OVERRIDE_PATH else Path(SCRIPT_DIR).parent / "references" / "trap_ledger_acceptance.yaml"
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return False
    if _ACC_STATE["path"] == p and _ACC_STATE["mtime"] == mtime:
        return _ACC_STATE["flipped"]
    flipped = bool(((load_acceptance(p) or {}).get("warn_upgrade") or {}).get("flipped"))
    _ACC_STATE.update(path=p, mtime=mtime, flipped=flipped)
    return flipped


def _engine_receipt():
    """sidecar 并行环境完整性回执（E批 pending #14）：engine_commit + gate 文件指纹。
    取证字段非执法闸——非 git 树/文件缺失容忍为 None，零异常零阻断。"""
    receipt = {"engine_commit": None, "gate_sha256": None}
    try:
        r = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"],
                           cwd=Path(SCRIPT_DIR).parent, capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            receipt["engine_commit"] = r.stdout.strip()
    except Exception:
        pass
    try:
        receipt["gate_sha256"] = hashlib.sha256(
            (SCRIPT_DIR / "lib" / "gate_definitions.py").read_bytes()).hexdigest()[:16]
    except Exception:
        pass
    return receipt


def load_report(report_path: str) -> str:
    """加载报告内容"""
    path = Path(report_path)
    if not path.exists():
        print(f"❌ 报告文件不存在: {report_path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def load_data_snapshot(data_path: str) -> dict:
    """加载数据快照（可选）。

    failure-family R8 机制档：区分「未传快照」（合法 report-only 模式，返回 {}）
    与「传了读不到」（配置错误——静默降级 report-only 会让三态豁免吞掉大半执法面，
    产出假 PASS）。后者 exit 1 拒跑。
    """
    if not data_path:
        return {}
    path = Path(data_path)
    if not path.exists():
        print(f"❌ 已传 --data-snapshot 但文件不存在: {data_path}——拒静默降级 report-only"
              "（未传才是 report-only），exit 1", file=sys.stderr)
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ --data-snapshot 解析失败: {e}——exit 1（同上，拒静默降级）", file=sys.stderr)
        sys.exit(1)


def _build_action_required(failed_gates: list, details: list) -> list:
    """构建 action_required：失败 gate 的 desc + 具体原因（gate 返 dict 时上浮 reasons）+ GATE_HINTS 修法。

    有 reasons 的 gate（如 G30 返 {passed,failed,reasons}）逐条展开，让作者看到具体 FAIL 项
    （如「G30: ... → #1 数值新鲜度 FAIL — 股东户数 stale」），而非泛化 desc。
    GATE_HINTS（gate_definitions.py）注入高频 gate 的修法速查——FAIL 即自解释，
    免 Read 178K 源码排障；hint 不足再读 m11-gates.md 对应节。
    """
    detail_by_gate = {d["gate"]: d for d in details}
    lines = []
    for g in failed_gates:
        base = f"{g}: {GATE_DESCS.get(g, '未知')}"
        d = detail_by_gate.get(g) or {}
        reasons = d.get("reasons") or []
        if reasons:
            for r in reasons:
                lines.append(f"{base} → {r}")
        else:
            lines.append(base)
        # E9（2026-08-31）：diag 真值行——expected/found/src 三键（degraded 合成的不
        # 渲染，expected/found=None 无信息量，fix 已有 fail_hint 兜底行）。
        diag = d.get("diag")
        if isinstance(diag, dict) and not diag.get("degraded"):
            parts = [f"{k}: {diag[k]}" for k in ("expected", "found", "src")
                     if diag.get(k) is not None]
            if parts:
                lines.append(f"  ⚙️ {' | '.join(parts)}")
        hint = GATE_HINTS.get(g)
        if hint:
            lines.append(f"  💡 {g} 修法: {hint}")
    return lines


# E9-L2：diag.fix 话术 lint——「绕过/规避」类话术把 gate 当对手而非质检，警告不 FAIL。
_BYPASS_RE = re.compile(r"绕过|规避|换词避开|改成不含")


def _lint_diag_fix(details: list) -> list:
    """扫描 FAIL 项 diag.fix 的绕过话术 → 警告行列表（L2，不改变 verdict）。"""
    warns = []
    for d in details:
        diag = d.get("diag")
        fix = diag.get("fix") if isinstance(diag, dict) else None
        if isinstance(fix, str) and _BYPASS_RE.search(fix):
            warns.append(f"{d['gate']}: diag.fix 含绕过话术（应修数据/措辞事实，非绕检）: {fix}")
    return warns


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
    # 运行时第二防线（v2.1）：checker 返回裸 bool（含 `return <布尔表达式>` 形态——
    # 字面 regex 抓不到）→ reason 丢失风险，warn 上浮 sidecar。静态 lint（test_diag_contract
    # 审计 v2）管字面、本 warn 管语义。升级条件：一轮 cron（全票全门）零命中后升硬断言。
    bool_return_gates = []

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
            ret = checker(report, data)
            # 兼容 bool 与 dict 返回：dict 含 {passed, reasons} 时上浮具体 FAIL 原因到
            # sidecar/action_required（如 G30 「股东户数 stale」），让作者知是哪个值 stale。
            gate_diag = None
            if isinstance(ret, dict):
                ok = bool(ret.get("passed", False))
                gate_reasons = ret.get("reasons") or []
                gate_diag = ret.get("diag")
            else:
                ok = bool(ret)
                # 薄壳兜底（B1）：bool 门 FAIL 无原生 reasons → 上浮注册表 fail_hint
                #（比裸 desc 可执行；原生 reasons 的门如 G30 不受影响）
                if not ok:
                    # 运行时第二防线：仅 FAIL 的 bool 返回才算 reason 丢失（PASS 返回 bool 无害）
                    bool_return_gates.append(gate)
                    print(f"⚠️ [bool-return] {gate} 返回裸 bool FAIL（reason 丢失，降级 "
                          "fail_hint）——应返回 GateResult(passed, reasons, diag)", file=sys.stderr)
                    gate_reasons = [GATE_REGISTRY[gate]["fail_hint"]]
                else:
                    gate_reasons = []
            if ok:
                passed.append(gate)
                detail = {"gate": gate, "status": "pass", "desc": desc, "weight": weight}
            else:
                failed.append(gate)
                detail = {"gate": gate, "status": "fail", "desc": desc, "weight": weight}
                # E9（2026-08-31 诊断契约 v2）：FAIL 项 100% 带 diag——checker 未发射
                #（bool 返回 / 收集化前的裸 FAIL）→ 框架合成 degraded=True 兜底
                #（expected/found 留 None = 诚实标注「引擎未预计算真值」，fix=fail_hint）。
                if not isinstance(gate_diag, dict):
                    gate_diag = {"expected": None, "found": None,
                                 "fix": GATE_REGISTRY[gate]["fail_hint"], "degraded": True}
            if gate_reasons:
                detail["reasons"] = gate_reasons
            if isinstance(gate_diag, dict):
                detail["diag"] = gate_diag
            details.append(detail)
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
        "action_required": _build_action_required(failed + errors, details),
    }

    # A2: 脚本化三维自评分（数据覆盖 / Gate通过 / SOURCE溯源）—— 禁止手填
    base_result["self_score"] = compute_self_score(report, data, base_result)

    # E9-L2：diag.fix 绕过话术 lint（警告不 FAIL）
    lint = _lint_diag_fix(details)
    if lint:
        base_result["diag_lint"] = lint

    # 运行时第二防线：bool 返回门清单（零命中一轮 cron 后升硬断言，见 :150 注释）。
    # C-4（2026-09-01）：翻转位由 trap_ledger_scan --field-acceptance 自动置（一轮 cron
    # 零命中）——翻转后按硬断言执法：**verdict 中性**（bool 门本就 FAIL，恒 FAIL），
    # 只把 warn 升为 contract violation 进 action_required（禁静默降级 fail_hint）。
    if bool_return_gates:
        base_result["bool_return_warn"] = sorted(set(bool_return_gates))
        if _acceptance_flipped():
            base_result["bool_return_hard"] = True
            base_result.setdefault("action_required", []).insert(
                0, "❌ [硬断言已激活] bool 返回门违规：" + "、".join(sorted(set(bool_return_gates)))
                   + "——reason 丢失面零容忍（trap_ledger_acceptance.warn_upgrade.flipped）")

    return base_result


def _banner_line(verdict: str, n_fail: int, threshold: int) -> str:
    """横幅前缀三分（P0 2026-09-03）：✅ 当且仅当 verdict=PASS 且失败+错误=0。

    软过（verdict=PASS 但残留未过 gate）打 ⚠️——✅ 前缀会中和紧随的未过清单，
    致会话只计硬 FAIL（retrospective_audit_20260902 批2「只有 G71」误报根因）。
    仅改前缀渲染；verdict/exit code/sidecar 字段语义不动（发布链消费 verdict）。"""
    if verdict == "PASS":
        if n_fail == 0:
            return f"✅ 校验通过（失败 0，阈值 {threshold}）"
        return (f"⚠️ 校验软过：verdict=PASS 但残留 {n_fail} 个未过 gate"
                f"（阈值 {threshold}，硬阻断=权重≥3）——须在『分析局限性』标注")
    return f"🔴 校验失败（失败 {n_fail}，超出阈值 {threshold}）"


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
        for r in (d.get("reasons") or []):
            print(f"      ↳ {r}")

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

    print(_banner_line(result["verdict"],
                       result["failed"] + result["errors"], result["threshold"]))
    if result["verdict"] == "PASS":
        if result["failed_gates"]:
            print("⚠️  以下 Gate 未通过，请在'分析局限性'中标注：")
            for action in result["action_required"]:
                print(f"  - {action}")
    else:
        print("报告必须重做或补全以下项后再输出：")
        for action in result["action_required"]:
            print(f"  - {action}")

    print("-" * 60)


def _preflight_value_preview(data: dict, dim: str) -> str:
    """preflight 真值预览：按注册表 data_dim 路径解析 snapshot 值，渲染 ≤1 行紧凑预览。

    dict → 最多 4 个标量键值对；list → 长度+首行摘要；标量 → 原值。解析不到 → ''（豁免提示由调用方渲染）。
    """
    cur = data
    for part in dim.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return ""
    if cur is None:
        return ""
    if isinstance(cur, dict):
        scal = {k: v for k, v in list(cur.items())
                if isinstance(v, (int, float, str, bool)) and not str(k).startswith("_")}
        if not scal:
            return f"{{{len(cur)} 键}}"
        return "{" + ", ".join(f"{k}={v}" for k, v in list(scal.items())[:4]) + \
               (f" …(+{len(scal)-4})" if len(scal) > 4 else "") + "}"
    if isinstance(cur, list):
        return f"[{len(cur)} 行]"
    return str(cur)[:90]


def run_preflight(data: dict, profile_name: str) -> None:
    """B4 preflight 模式：写作前从 GATE_REGISTRY + 活 snapshot 生成逐门写作要求清单。

    与执法同源零漂移（三消费方单一真相源）：清单的 requires/fail_hint/weight 直接读注册表，
    真值预览按 data_dim 路径解析活 snapshot——LLM 写报告**前**读它，round-1「要求不明」类
    FAIL（603986 六败/600703 结构败）结构性消失。写作后 verify 不变。
    """
    profile = get_profile(profile_name)
    active = profile["gates"]
    print("=" * 72)
    print(f"Gate Preflight 写作要求清单 | Profile: {profile_name}（写报告前读，与执法同源）")
    print("=" * 72)
    with_data = without_data = 0
    for gate in ALL_GATES:
        if gate not in active:
            continue
        row = GATE_REGISTRY[gate]
        preview = _preflight_value_preview(data, row.get("data_dim") or "")
        mark = "🟢" if preview else "⚪"
        if preview:
            with_data += 1
        else:
            without_data += 1
        owners = "/".join(row.get("owner") or [])
        print(f"{mark} {gate} [{owners}] w{row['weight']}: {row['requires']}")
        if preview:
            print(f"      真值 {row.get('data_dim')} = {preview}")
        else:
            print(f"      （snapshot 无 {row.get('data_dim')} → 三态豁免路径，禁编造该维数值）")
        # preview_dims：执法真值在别处叶子（如 G54 的 ADX 在 dmi、G55 的 VWAP 在 s2）→ 一并渲染
        for extra in row.get("preview_dims") or []:
            pv = _preflight_value_preview(data, extra)
            if pv:
                print(f"      真值 {extra} = {pv}")
    print("-" * 72)
    print(f"共 {with_data + without_data} 门：{with_data} 门有数据（须消费/对齐真值），"
          f"{without_data} 门无数据（三态豁免，禁编造）")
    print("写作完成后运行 verify_gates.py（不带 --preflight）执法校验。")


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
    parser.add_argument("--report", required=False, help="报告文件路径（.md；--preflight 模式免填）")
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
    parser.add_argument("--preflight", action="store_true",
                        help="写作前模式：不跑 Gate，从 GATE_REGISTRY + 活 snapshot 生成"
                             "逐门写作要求清单（要求与执法同源，LLM 写报告前读它）。"
                             "须配 --data-snapshot，免 --report。")
    parser.add_argument("--no-sidecar", action="store_true",
                        help="禁用 sidecar 自动写入（默认写 <report>.verified.json）")
    args = parser.parse_args()

    # preflight 模式：写作前要求清单，独立分支（先例 --check-pointer），不跑 Gate 不写 sidecar
    if args.preflight:
        if not args.data_snapshot:
            parser.error("--preflight 须配 --data-snapshot（要求清单要解析活 snapshot 真值）")
        data = load_data_snapshot(args.data_snapshot)
        if not data:
            print("❌ 数据快照不存在或为空，preflight 无法生成真值要求")
            sys.exit(1)
        run_preflight(data, f"profile_{args.profile}")
        sys.exit(0)

    # 非 preflight 模式 --report 必填（手动校验维持原 required=True 行为，向后兼容）
    if not args.report:
        parser.error("以下参数是必需的: --report（或改用 --preflight 模式免 report）")

    # 指针校验模式：只读，独立分支，不重跑 Gate
    if args.check_pointer:
        check_pointer(args.report)

    # 加载输入
    report = load_report(args.report)
    data = load_data_snapshot(args.data_snapshot)
    # F3 mtime 校验（2026-09-01，CLI 层——库函数不校验，archive 重放 import 库函数不受影响）：
    # 报告 mtime 必须 ≥ 快照 mtime，报告早于快照 = 写错文件/陈旧拷贝（/tmp 固定路径被并行
    # 会话互覆的形态）。仅在快照可解析后执法——坏 JSON 走上方 exit 1 硬闸，不劫持其语义。
    if data and args.report and not args.report_only:
        from pathlib import Path as _P

        _rep, _snap = _P(args.report), _P(args.data_snapshot).expanduser()
        if _rep.exists() and _snap.exists() and _rep.stat().st_mtime < _snap.stat().st_mtime:
            print(f"❌ 报告 mtime 早于数据快照 mtime（report={_rep} < snapshot={_snap}）——"
                  "报告不是从该快照写出的（错文件/陈旧拷贝，F3）。修法：核对 --report 路径是否"
                  "run-scoped（/tmp/analysis_report_<code>.md）；确认无误后从正确快照重写报告。")
            sys.exit(2)
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
        result["engine_receipt"] = _engine_receipt()
        sidecar_path = Path(args.report).with_suffix(".verified.json")
        sidecar_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.quiet:
            print(f"\n📝 sidecar 已写入: {sidecar_path}")
            er = result["engine_receipt"]
            print(f"🔧 engine_receipt: commit={er['engine_commit']} "
                  f"gate_sha256={er['gate_sha256']}")
            # E：指针行直接可复制——消除「为格式提前读 m11-gates.md」的预读，
            # 用 args.profile（="full"）非 profile_name，与 SKILL 模板及 check_pointer 双匹配
            if result["verdict"] == "PASS":
                ss = result.get("self_score", {})
                print(f"📌 指针行（复制进 m11 区，粘贴后重跑 verify 刷新 sidecar）："
                      f"[verified: self_score={ss.get('score')} profile={args.profile} "
                      f"| see {sidecar_path.name}]")

    # 退出码
    if result["verdict"] == "FAIL":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
