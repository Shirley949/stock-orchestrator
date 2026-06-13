#!/usr/bin/env python3
"""
generate_checklist.py — 执行清单生成器（机制 1）
Phase 0 第一步必须调用，输出本次任务的完整执行清单。

功能：
1. 解析用户问题 → 两段式映射（映射表 80% + LLM 兜底 20%）
2. 匹配模式 + 展开 Phase
3. 解析 Skill 依赖图 → 输出必须加载文件清单
4. 生成可勾选 Markdown → 每步前面有 [ ]，后面有 <!--check_id:X--> 标记

用法:
  python generate_checklist.py \
    --user-prompt "深度分析沃尔核材002130，重点看期货成本和订单" \
    --stock-codes "002130" \
    --mode A \
    --output /tmp/analysis_checklist_20260612.md
"""

import argparse
import json
import os
import sys
import re
from datetime import datetime
from pathlib import Path

# 添加 lib 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from skill_dep_graph import resolve_required_files, get_mode_profile
from parse_user_question import parse_user_question


# ============================================================
# 模式判定（从 orchestrator SKILL.md 提取的规则）
# ============================================================

def detect_mode(user_prompt: str) -> str:
    """根据用户 prompt 自动判定分析模式。长匹配优先，避免子串误判。"""
    # 按长度降序排列，优先匹配更长的触发词
    mode_b_triggers = sorted([
        "今天买不买", "要不要卖", "当日操作", "盘中建议",
        "现在能买吗", "现在能加仓吗", "要不要减仓", "盘中", "能加仓"
    ], key=len, reverse=True)
    mode_c_triggers = sorted([
        "有没有风险", "最近有什么公告", "事件扫描", "有没有雷", "风险", "事件"
    ], key=len, reverse=True)
    mode_d_triggers = sorted([
        "估值多少", "贵不贵", "值不值得买", "PE多少"
    ], key=len, reverse=True)
    mode_a_triggers = sorted([
        "深度分析", "整体分析", "财报分析", "全面分析",
        "值不值得买", "分析一下", "帮我看看", "怎么样",
        "买不买", "估值", "分析", "看看"
    ], key=len, reverse=True)

    # 先检查 B（更具体的短操作词）——如果 B 命中且 A 也命中，取 A
    for trigger in mode_b_triggers:
        if trigger in user_prompt:
            # 检查是否同时命中 A 的更具体触发词
            for a_trigger in ["深度分析", "整体分析", "财报分析", "全面分析", "帮我看看"]:
                if a_trigger in user_prompt:
                    return "A"
            return "B"

    # 再检查 D
    for trigger in mode_d_triggers:
        if trigger in user_prompt:
            return "D"

    # 再检查 C
    for trigger in mode_c_triggers:
        if trigger in user_prompt:
            return "C"

    # 最后检查 A
    for trigger in mode_a_triggers:
        if trigger in user_prompt:
            return "A"

    return "A"  # 默认模式 A（宁多勿少）


def extract_stock_codes(user_prompt: str) -> list[str]:
    """从用户 prompt 中提取股票代码"""
    # 6 位数字代码（支持中文紧邻、空格、标点等多种边界）
    codes = re.findall(r'(?:^|[^\d])(\d{6})(?:[^\d]|$)', user_prompt)
    # 也支持中文名+代码紧邻的情况（如"沃尔核材002130"）
    codes2 = re.findall(r'[一-鿿](\d{6})', user_prompt)
    # SH/SZ 前缀
    prefixed = re.findall(r'(?:SH|SZ|sh|sz)[.\s]?(\d{6})', user_prompt)
    # .SS/.SZ 后缀
    suffixed = re.findall(r'(\d{6})\.(?:SS|SZ|ss|sz)', user_prompt)
    all_codes = list(set(codes + codes2 + prefixed + suffixed))
    return all_codes


# ============================================================
# Phase 步骤定义
# ============================================================

PHASE_STEPS = {
    "A": {
        "phase_0": [
            {"id": "c01", "desc": "Skills 全部加载（orchestrator + routing + registry + quality + order-intelligence）"},
            {"id": "c02", "desc": "用户问题映射表已生成（见下方）"},
            {"id": "c03", "desc": "必须加载文件清单已确认"},
            {"id": "c04", "desc": "运行 routing/runner.py A <stock_code> → 拉取全量数据 snapshot"},
            {"id": "c05", "desc": "运行 order-intelligence/runner.py <stock_code> <stock_type> → 订单数据"},
            {"id": "c06", "desc": "检查 runner._warnings → 处理降级/失败项"},
        ],
        "phase_1": [
            {"id": "c10", "desc": "runner 返回的实时行情数据确认", "agent": 1},
            {"id": "c11", "desc": "runner 返回的资金流向数据确认", "agent": 1},
            {"id": "c12", "desc": "降级链验证：检查 runner._warnings 中的降级项", "agent": 1},
            {"id": "c13", "desc": "runner 返回的财务三表数据确认（8季度）", "agent": 2},
            {"id": "c14", "desc": "runner 返回的合同负债趋势确认", "agent": 2},
            {"id": "c15", "desc": "提取扣非净利润（从 runner snapshot）", "agent": 2},
            {"id": "c16", "desc": "runner 返回的新闻 → Claude 执行 18 类事件语义分类", "agent": 3},
            {"id": "c17", "desc": "runner 返回的公告标题 → Claude 筛选中标/重大合同", "agent": 3},
            {"id": "c18", "desc": "runner Layer 0-3 数据确认 + Claude 判断间接出海", "agent": 4},
            {"id": "c19", "desc": "Claude 选择可比公司（runner 返回候选池）", "agent": 4},
            {"id": "c19b", "desc": "Claude 判断期货品种（如用户提到期货）", "agent": 4},
        ],
        "phase_1_skipped": [
            {"id": "c_skip_irm", "desc": "❌ Layer 1 互动易（永久跳过，不可程序化）"},
            {"id": "c_skip_dev", "desc": "❌ Layer 2 设备/产能（永久跳过，需人工）"},
            {"id": "c_skip_demand", "desc": "❌ Layer 4-B 步骤1 全球需求基数（永久跳过）"},
        ],
        "phase_2": [
            {"id": "c50", "desc": "收单清单 12 项全部勾选（来自 runner s10_checklist）"},
            {"id": "c51", "desc": "缺失项已在'分析局限性'标注"},
        ],
        "phase_3": [
            {"id": "c60", "desc": "m0 分类"},
            {"id": "c61", "desc": "m2 财务（含扣非诊断 + 利润归因 + 现金流三件套）"},
            {"id": "c62", "desc": "m25 订单诊断（来自 order-intelligence runner）"},
            {"id": "c63", "desc": "m3 技术（TD 4 步 + 多指标交叉）"},
            {"id": "c64", "desc": "m4.1.1 事件扫描结果"},
            {"id": "c65", "desc": "m5 估值（含历史分位 + 同业对比）"},
            {"id": "c66", "desc": "m6 决策树 + m9 信号矩阵 + m10 三档情景"},
            {"id": "c67", "desc": "m7 风险 + 反转假设"},
            {"id": "c68", "desc": "m8 局限性 ≥ 3 条"},
        ],
        "phase_4": [
            {"id": "c70", "desc": "运行 verify_gates.py（机制 3）"},
            {"id": "c71", "desc": "自评分 ≥ 80"},
        ],
        "phase_5": [
            {"id": "c80", "desc": "报告写入腾讯文档"},
        ],
    },
    "B": {
        "phase_0": [
            {"id": "c01", "desc": "Skills 加载（orchestrator + routing + registry）"},
            {"id": "c02", "desc": "用户问题映射表已生成"},
            {"id": "c04", "desc": "运行 routing/runner.py B <stock_code> → 拉取行情+K线"},
            {"id": "c06", "desc": "检查 runner._warnings → 处理降级/失败项"},
        ],
        "phase_1": [
            {"id": "c10", "desc": "runner 返回的实时行情数据确认", "agent": 1},
            {"id": "c11", "desc": "runner 返回的 K 线数据确认", "agent": 1},
            {"id": "c12", "desc": "技术指标自算（MACD/KDJ/RSI/TD）", "agent": 1},
            {"id": "c13", "desc": "分时数据与盘口解读", "agent": 1},
        ],
        "phase_2": [
            {"id": "c50", "desc": "数据收单完成（来自 runner s10_checklist）"},
        ],
        "phase_3": [
            {"id": "c60", "desc": "m3 技术面"},
            {"id": "c61", "desc": "m6 操作建议"},
            {"id": "c62", "desc": "m9 信号矩阵"},
        ],
        "phase_4": [
            {"id": "c70", "desc": "运行 verify_gates.py（profile_quick）"},
        ],
        "phase_5": [
            {"id": "c80", "desc": "报告输出"},
        ],
    },
    "C": {
        "phase_0": [
            {"id": "c01", "desc": "Skills 加载（orchestrator + routing + registry）"},
            {"id": "c02", "desc": "用户问题映射表已生成"},
        ],
        "phase_1": [
            {"id": "c10", "desc": "事件扫描 18 类"},
        ],
        "phase_2": [
            {"id": "c50", "desc": "事件收单完成"},
        ],
        "phase_3": [
            {"id": "c60", "desc": "m4 事件/情绪"},
        ],
        "phase_4": [
            {"id": "c70", "desc": "运行 verify_gates.py（profile_event_scan）"},
        ],
        "phase_5": [
            {"id": "c80", "desc": "报告输出"},
        ],
    },
    "D": {
        "phase_0": [
            {"id": "c01", "desc": "Skills 加载（orchestrator + routing + registry + quality）"},
            {"id": "c02", "desc": "用户问题映射表已生成"},
        ],
        "phase_1": [
            {"id": "c10", "desc": "s9 情景概率 + s11 可比公司"},
            {"id": "c11", "desc": "s4 机构评级/目标价"},
        ],
        "phase_2": [
            {"id": "c50", "desc": "数据收单完成"},
        ],
        "phase_3": [
            {"id": "c60", "desc": "m5 估值"},
        ],
        "phase_4": [
            {"id": "c70", "desc": "运行 verify_gates.py（profile_valuation）"},
        ],
        "phase_5": [
            {"id": "c80", "desc": "报告输出"},
        ],
    },
}


# ============================================================
# 清单生成
# ============================================================

def get_phase_name(phase_key: str) -> str:
    """Phase key → 中文名"""
    names = {
        "phase_0": "Phase 0: 准入校验",
        "phase_1": "Phase 1: 数据拉取（并行 4 路 Agent）",
        "phase_2": "Phase 2: 数据收单",
        "phase_3": "Phase 3: 报告生成",
        "phase_4": "Phase 4: Gate 校验",
        "phase_5": "Phase 5: 输出",
    }
    return names.get(phase_key, phase_key)


def generate_agent_steps(mode: str, question_result: dict) -> list[str]:
    """为 Phase 1 生成 Agent 分组描述（仅模式 A，v3 runner 模型）"""
    if mode != "A":
        return []

    # 根据用户问题动态调整 Agent 4 的内容
    has_futures = any(kw in str(question_result) for kw in ["期货", "商品", "铜价", "LME"])
    has_orders = any(kw in str(question_result) for kw in ["订单", "在手", "饱和", "合同负债"])

    extra_items = []
    if has_futures:
        extra_items.append("Claude 判断期货品种 → futures_main_sina(CU0)")
        extra_items.append("Claude 解读 LME 库存数据")
    if has_orders:
        extra_items.append("Claude 判断间接出海（runner 返回 reported_overseas_pct）")
        extra_items.append("Claude 筛选中标公告（runner 返回标题列表）")

    lines = [
        "### Agent 1: 行情 + 资金流（runner 已拉取，Claude 验证）",
        "  - runner 返回实时行情 + 资金流向 → Claude 确认数据完整性",
        "  - runner._warnings 中的降级项 → Claude 标注到报告",
        "",
        "### Agent 2: 财务三表（runner 已拉取，Claude 分析）",
        "  - runner 返回利润表/资产负债表/现金流 → Claude 做扣非诊断 + 利润归因",
        "  - runner 返回合同负债趋势 → Claude 确认数据",
        "",
        "### Agent 3: 事件扫描（runner 返回新闻，Claude 分类）",
        "  - runner 返回新闻标题 → Claude 执行 18 类事件语义分类",
        "  - runner 返回公告标题 → Claude 筛选中标/重大合同",
        "",
        "### Agent 4: 订单 + 期货 + 同业（runner 返回数据，Claude 判断）",
        "  - runner Layer 0-3 数据 → Claude 判断间接出海 + 供需轴",
        "  - Claude 选择可比公司（runner 返回候选池）",
    ]
    for item in extra_items:
        lines.append(f"  - {item}")

    return lines


def generate_checklist(user_prompt: str, stock_codes: str = None,
                       mode: str = None, output: str = None) -> str:
    """
    生成完整执行清单的主函数。

    参数:
        user_prompt: 用户原始分析请求
        stock_codes: 股票代码（逗号分隔），None 则自动提取
        mode: 分析模式（A/B/C/D），None 则自动判定
        output: 输出文件路径，None 则返回字符串

    返回: 清单 Markdown 内容
    """
    # 自动提取/判定
    if not stock_codes:
        codes = extract_stock_codes(user_prompt)
        stock_codes = ",".join(codes) if codes else "未知"
    if not mode:
        mode = detect_mode(user_prompt)

    stock_code_list = [c.strip() for c in stock_codes.split(",") if c.strip()]

    # Stage 1: 两段式问题映射
    question_result = parse_user_question(user_prompt)

    # Stage 2: Skill 依赖图
    required_files = resolve_required_files(mode, user_prompt)
    profile_name = get_mode_profile(mode)

    # 获取 Phase 步骤
    mode_steps = PHASE_STEPS.get(mode, PHASE_STEPS["A"])

    # 生成时间戳
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_file = output or f"/tmp/analysis_checklist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    # 统计总步骤数
    total_steps = sum(len(steps) for steps in mode_steps.values())
    # 加上用户问题映射行数
    mapping_rows = len(question_result["matched"]) + len(question_result["unmapped"])
    total_steps += mapping_rows

    # 构建清单
    lines = []
    lines.append(f"# 执行清单 — {'、'.join(stock_code_list)} 分析（mode={mode}）")
    lines.append(f"生成时间：{timestamp}")
    lines.append(f"用户问题：{user_prompt}")
    lines.append("")

    # Phase 0
    lines.append(f"## {get_phase_name('phase_0')}")
    for step in mode_steps["phase_0"]:
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
    lines.append("")

    # Runner 调用命令（v3 机制 6）
    if mode in ("A", "B") and stock_code_list:
        sc = stock_code_list[0]
        lines.append("### 🔧 Runner 调用命令（机械化部分）")
        lines.append("```bash")
        if mode == "A":
            lines.append(f"# Step 1: 数据拉取（routing runner）")
            lines.append(f"python ~/.hermes/skills/stock-analysis/financial-data-routing/runner.py A {sc}")
            lines.append(f"")
            lines.append(f"# Step 2: 订单数据（order-intelligence runner）")
            lines.append(f"python ~/.hermes/skills/stock-analysis/order-intelligence/runner.py {sc} <stock_type>")
        elif mode == "B":
            lines.append(f"# 数据拉取（routing runner）")
            lines.append(f"python ~/.hermes/skills/stock-analysis/financial-data-routing/runner.py B {sc}")
        lines.append("```")
        lines.append("")

    # 用户问题 → 数据需求映射
    lines.append("## 用户问题 → 数据需求映射")
    lines.append("| 用户问题 | 需要数据 | API/源 | 来源 | 状态 |")
    lines.append("|---------|---------|-------|------|------|")

    for match in question_result["matched"]:
        source_label = "映射表"
        apis = ", ".join(match["api_sources"][:2])  # 最多显示2个API
        lines.append(f"| {match['segment'][:20]} | {match['data_needs'][:30]} | {apis} | {source_label} | [ ] |")

    for unmapped in question_result["unmapped"]:
        lines.append(f"| {unmapped['segment'][:20]} | ⚠️ 待LLM判断 | — | [LLM兜底] | [ ] |")

    lines.append("")

    # Phase 1
    lines.append(f"## {get_phase_name('phase_1')}")
    agent_lines = generate_agent_steps(mode, question_result)
    if agent_lines:
        lines.extend(agent_lines)
        lines.append("")
    for step in mode_steps["phase_1"]:
        agent_tag = f"（Agent {step.get('agent', '?')}）" if "agent" in step else ""
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}{agent_tag}")
    lines.append("")

    # 永久跳过项（v3：显式标记不可达步骤）
    if "phase_1_skipped" in mode_steps:
        lines.append("### ❌ 永久跳过的步骤（runner 内部已硬跳）")
        for step in mode_steps["phase_1_skipped"]:
            lines.append(f"- {step['desc']}")
        lines.append("")

    # Phase 2
    lines.append(f"## {get_phase_name('phase_2')}")
    for step in mode_steps["phase_2"]:
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
    lines.append("")

    # Phase 3
    lines.append(f"## {get_phase_name('phase_3')}")
    for step in mode_steps["phase_3"]:
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
    lines.append("")

    # Phase 4
    lines.append(f"## {get_phase_name('phase_4')}")
    lines.append(f"Profile: `{profile_name}`")
    for step in mode_steps["phase_4"]:
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
    lines.append("")

    # Phase 5
    lines.append(f"## {get_phase_name('phase_5')}")
    for step in mode_steps["phase_5"]:
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
    lines.append("")

    # 必须加载的文件清单
    lines.append("---")
    lines.append("")
    lines.append("## 🔴 必须加载的文件（Phase 0 完成前不许进 Phase 1）")
    lines.append("")
    lines.append("| 优先级 | 文件 | 状态 | 原因 |")
    lines.append("|-------|------|------|------|")

    for f in required_files:
        priority = f["priority"]
        path = f["path"]
        reason = f["reason"]
        # orchestrator 和 data-source-registry 视为已加载
        if "orchestrator" in path or "data-source-registry" in path:
            status = "✅ 已加载"
        else:
            status = "[ ] 未加载"
        bold = "**" if priority == "P0" else ""
        lines.append(f"| {bold}{priority}{bold} | {bold}{path}{bold} | {status} | {reason} |")

    lines.append("")

    # LLM 兜底提示（如果有未匹配的问题）
    if question_result["unmapped"]:
        lines.append("---")
        lines.append("")
        lines.append("## ⚠️ LLM 兜底任务（以下子问题需要 Claude 判断数据需求）")
        lines.append("")
        lines.append("```")
        lines.append(question_result["llm_fallback_prompt"] or "无")
        lines.append("```")
        lines.append("")
        lines.append("请在主线程中解析上述未匹配问题，将结果回写到清单的映射表中。")
        lines.append("")

    # 完成进度
    lines.append("---")
    lines.append(f"**完成进度：0/{total_steps}**")
    lines.append(f"**下一步**：开始执行 Phase 0")
    lines.append("")

    content = "\n".join(lines)

    # 写入文件
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        print(f"✅ 执行清单已生成: {output}")
        print(f"   模式: {mode} | 股票: {stock_codes} | 步骤: {total_steps}")
        if question_result["unmapped"]:
            print(f"   ⚠️  {len(question_result['unmapped'])} 条问题需要 LLM 兜底")
    else:
        print(content)

    return content


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="执行清单生成器（机制 1）")
    parser.add_argument("--user-prompt", required=True, help="用户的原始分析请求")
    parser.add_argument("--stock-codes", help="股票代码（逗号分隔），不传则自动提取")
    parser.add_argument("--mode", choices=["A", "B", "C", "D"], help="分析模式，不传则自动判定")
    parser.add_argument("--output", help="输出清单文件路径")
    args = parser.parse_args()

    generate_checklist(
        user_prompt=args.user_prompt,
        stock_codes=args.stock_codes,
        mode=args.mode,
        output=args.output,
    )


if __name__ == "__main__":
    main()
