#!/usr/bin/env python3
"""
update_checklist.py — 执行清单打勾工具（PR 7: 增加 --evidence-from 校验）

用法: python update_checklist.py --check c01 --file /tmp/analysis_checklist_xxx.md
      python update_checklist.py --check c01 --file /tmp/checklist.md --evidence-from /tmp/snapshot.json --evidence-path s1_financial
      python update_checklist.py --check c01,c02,c10 --file /tmp/analysis_checklist_xxx.md
      python update_checklist.py --uncheck c20 --file /tmp/analysis_checklist_xxx.md

PR 7 改动: --evidence-from 参数要求打勾前验证 snapshot 中对应路径有有效数据。
"""

import argparse
import json
import re
import sys
from pathlib import Path


# 清单项 → snapshot 路径的映射表
CHECKID_TO_SNAPSHOT_PATH = {
    "c04": "_top_level",  # 检查 _critical_failure 不存在
    "c05": "order_intelligence.layer0_caliber",
    "c10": "s2_quote_kline.data.realtime_quote",
    "c11": "s3_fund_flow.data.fund_flow",
    "c12": "_top_level",  # 检查 _warnings
    "c13": "s1_financial.data.income_statement",
    "c14": "s1_financial.data.balance_sheet",
    "c15": "s1_financial.data.income_statement",  # 扣非从利润表提取
    "c16": "s5_events.data.news",
    "c17": "s5_events.data.news",
    "c18": "s2_quote_kline.data.realtime_quote",
    "c19": "s2_quote_kline.data.daily_kline",
    "c_pdf_annual": "s3_cninfo_pdf.data",
    "c_pdf_research": "s35_research_reports.data",
    "c_analyst_forecast": "s73_forecast.data",
    "c_d2_safety": "s36_annual_analysis.data",
    "c_d3_growth": "s36_annual_analysis.data",
    "c_d4_dividend": "s36_annual_analysis.data",
    "c_d5_governance": "s36_annual_analysis.data",
    "c_d6_audit": "s36_annual_analysis.data",
}


def validate_evidence(snapshot_path: str, evidence_path: str) -> tuple:
    """
    验证 snapshot 中指定路径有有效数据。
    返回 (valid: bool, message: str)
    """
    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return False, f"snapshot 加载失败: {e}"

    # 特殊路径: _top_level 检查 _critical_failure
    if evidence_path == "_top_level":
        if snapshot.get("_critical_failure"):
            return False, "snapshot 标记了 _critical_failure"
        return True, "无 critical_failure"

    # 解析嵌套路径: "s1_financial.data.income_statement"
    parts = evidence_path.split(".")
    current = snapshot
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return False, f"路径 {evidence_path} 不存在"

    if current is None:
        return False, f"路径 {evidence_path} 值为 None"

    if isinstance(current, dict):
        status = current.get("status")
        if status in ("ok", "cached"):
            return True, f"status={status}"
        elif status == "all_failed":
            return False, f"status=all_failed"
        else:
            return False, f"status={status}"

    return True, f"值存在: {type(current).__name__}"


def validate_gate_result(sidecar_path: str) -> tuple:
    """验证 verify_gates sidecar（c70 专用，单一出口契约）。

    契约（与 verify_gates --check-pointer 一致）：
      ① verdict == "PASS"
      ② self_score.score >= 80
      ③ 新鲜度：sidecar mtime >= 报告 mtime（<name>.verified.json ↔ <name>.md）

    返回 (valid: bool, message: str)
    """
    try:
        result = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return False, f"sidecar 加载失败: {e}"

    if result.get("verdict") != "PASS":
        return False, f"verdict={result.get('verdict')}（需 PASS），失败 Gate：{result.get('failed_gates')}"

    ss = result.get("self_score", {})
    score = ss.get("score", 0)
    if score < 80:
        return False, f"self_score={score} < 80"

    # 尽力而为的新鲜度：从 sidecar 名反推同名报告（verify_gates 的派生规则）
    sidecar_p = Path(sidecar_path)
    report_p = sidecar_p.parent / sidecar_p.name.replace(".verified.json", ".md")
    if report_p.exists() and sidecar_p.stat().st_mtime < report_p.stat().st_mtime:
        return False, "sidecar 比报告旧（报告已改动但未重新校验）"

    return True, f"verdict=PASS self_score={score}"


def update_checklist(
    file_path: str,
    check_ids: list[str],
    uncheck_ids: list[str] = None,
    evidence_from: str = None,
    evidence_path: str = None,
):
    """
    更新清单文件中的 checkbox 状态。
    check_ids: 要打勾的 ID 列表 (如 ["c01", "c02"])
    uncheck_ids: 要取消打勾的 ID 列表
    evidence_from: snapshot JSON 路径（PR 7）
    evidence_path: snapshot 中的路径（PR 7，覆盖自动映射）
    """
    path = Path(file_path)
    if not path.exists():
        print(f"❌ 清单文件不存在: {file_path}")
        sys.exit(1)

    content = path.read_text(encoding="utf-8")
    original = content

    # 打勾: [ ] <!--c01--> → [x] <!--c01-->
    for cid in check_ids:
        # PR 7: evidence 校验
        if evidence_from:
            if cid == "c70":
                # c70 特例: evidence-from 是 verify_gates sidecar（单一出口契约，
                # 非 snapshot）。verdict==PASS + self_score>=80 + 新鲜度由代码强制。
                valid, msg = validate_gate_result(evidence_from)
                if not valid:
                    print(f"❌ {cid}: Gate sidecar 校验失败 — {msg}")
                    sys.exit(1)
                print(f"🔍 {cid}: Gate sidecar 校验通过 — {msg}")
            else:
                ep = evidence_path or CHECKID_TO_SNAPSHOT_PATH.get(cid)
                if ep:
                    valid, msg = validate_evidence(evidence_from, ep)
                    if not valid:
                        print(f"❌ {cid}: evidence 校验失败 — {msg}")
                        print(f"   路径: {ep}")
                        sys.exit(1)
                    else:
                        print(f"🔍 {cid}: evidence 校验通过 — {msg}")

        pattern = rf'\[ \] <!--{re.escape(cid)}-->'
        replacement = f'[x] <!--{cid}-->'
        new_content = re.sub(pattern, replacement, content)
        if new_content == content:
            print(f"⚠️  {cid}: 未找到对应的 [ ] 标记（可能已打勾或 ID 不存在）")
        else:
            print(f"✅ {cid}: 已打勾")
            content = new_content

    # 取消打勾
    if uncheck_ids:
        for cid in uncheck_ids:
            pattern = rf'\[x\] <!--{re.escape(cid)}-->'
            replacement = f'[ ] <!--{cid}-->'
            new_content = re.sub(pattern, replacement, content)
            if new_content == content:
                print(f"⚠️  {cid}: 未找到对应的 [x] 标记")
            else:
                print(f"↩️  {cid}: 已取消打勾")
                content = new_content

    # 更新完成进度
    total = len(re.findall(r'<!--c[\w]+-->', content))
    checked = len(re.findall(r'\[x\] <!--c[\w]+-->', content))
    progress_pattern = r'\*\*完成进度：\d+/\d+\*\*'
    new_progress = f'**完成进度：{checked}/{total}**'
    content = re.sub(progress_pattern, new_progress, content)

    # 更新下一步提示
    if checked == total:
        next_step = "**下一步**：所有步骤已完成，进入 Gate 校验"
    else:
        # 找到第一个未完成的 check_id
        remaining = re.findall(r'\[ \] <!--(c[\w]+)-->', content)
        if remaining:
            next_step = f"**下一步**：继续执行 {remaining[0]}"
        else:
            next_step = "**下一步**：继续执行"
    next_pattern = r'\*\*下一步\*\*：.*'
    content = re.sub(next_pattern, next_step, content)

    # 写回文件
    if content != original:
        path.write_text(content, encoding="utf-8")
        print(f"\n📝 清单已更新: {file_path}")
        print(f"   进度: {checked}/{total}")
    else:
        print(f"\n无变更")


def main():
    parser = argparse.ArgumentParser(description="执行清单打勾工具（PR 7: 增加 evidence 校验）")
    parser.add_argument("--check", required=True, help="要打勾的 check_id，逗号分隔（如 c01,c02,c10）")
    parser.add_argument("--uncheck", help="要取消打勾的 check_id，逗号分隔")
    parser.add_argument("--file", required=True, help="清单文件路径")
    parser.add_argument("--evidence-from", help="snapshot JSON 路径（PR 7: 打勾前校验数据）")
    parser.add_argument("--evidence-path", help="snapshot 中的路径（覆盖自动映射）")
    args = parser.parse_args()

    check_ids = [c.strip() for c in args.check.split(",") if c.strip()]
    uncheck_ids = [c.strip() for c in args.uncheck.split(",") if c.strip()] if args.uncheck else []

    if not check_ids and not uncheck_ids:
        print("❌ 必须指定 --check 或 --uncheck")
        sys.exit(1)

    update_checklist(
        args.file, check_ids, uncheck_ids,
        evidence_from=args.evidence_from,
        evidence_path=args.evidence_path,
    )


if __name__ == "__main__":
    main()
