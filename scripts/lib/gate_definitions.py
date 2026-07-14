#!/usr/bin/env python3
"""
gate_definitions.py — Gate 积木定义 + Profile + 自评分（单一引擎）

仓库内唯一的 Gate 定义源（G1-G27）。第二套引擎（gate_checker.py 等）已删除（归档于父仓库 git 历史）。
本模块提供：GATE_DESCS / GATE_WEIGHTS / GATE_CHECKERS（每 Gate 一行可验证）、
PROFILES（full/quick 组装）、compute_score（Gate 加权）、compute_self_score（三维自评分：
数据覆盖 40% + Gate 通过 40% + SOURCE 溯源 20%，注入 sidecar 作为 m11 唯一权威分数）。

关键 checker 说明：
  - check_g16：真实数值核对 —— snapshot 有合同负债时，报告必须不与 snapshot 冲突 +
    数值对齐或带 [src:] 溯源 + 含核对关键词（杜绝"橡皮章"）。修复 603929：
    报告 websearch 14.48亿 vs snapshot 5.39亿 → 原版误判 PASS。
  - check_g17/g18：Step 0 去"海外"词触发 + 补同业关键词，避免误阻塞。
"""

import re

# ============================================================
# Gate 定义
# ============================================================

GATE_DESCS = {
    "G1": "信号矩阵完整性（≥8行×3列：短/中/长）",
    "G2": "情景概率闭合（三档概率=100%，允许±1%）",
    "G3": "决策树结构（≥3分支+1默认，每分支带触发条件+仓位+止损位）",
    "G4": "决策↔信号一致（信号矛盾→决策树默认'不操作'）",
    "G5": "决策↔情景一致（主分支≥20%→乐观+基准≥60%）",
    "G6": "季报连续性（≥6个连续季度数据）",
    "G7": "扣非对比（净利润/扣非/差额%三列已展示）",
    "G8": "现金流三件套（CFO/CFI/CFF/FCF/FCF净利润比）",
    "G9": "利润归因闭合（ΔNetProfit四项分解闭合）",
    "G10": "事件扫描完成（高优8类+低优10类，每类有状态标记）",
    "G11": "数据时效性声明（报告开头声明数据截止时间；表格仅在数据来源不同时标注日期）",
    "G12": "局限性披露（≥3条具体局限）",
    "G13": "持仓↔决策一致（若用户提供持仓信息，决策树应考虑持仓语境）",
    "G14": "TD逐根展示（TD计数表≥9行+结论）",
    "G15": "同业对比（≥2家可比公司+≥4指标）",
    "G16": "订单Layer6核对（合同负债核对偏差≤15%；销量/海外收入核对已跳过）",
    "G17": "海外关税完整（海外敞口公司必须有T0-T4分析）",
    "G18": "竞品对标≥3家（Layer5可比公司≥3家）",
    "G19": "营收预测区间（Layer8给区间或标注'无法量化'）",
    "G20": "口径一致（Layer0口径=Layer8输出）",
    "G21": "SOURCE溯源（报告[src:]标记→snapshot路径验证）",
    "G22": "分业务数据完整性（模块二包含分业务/分产品/分行业表格）",
    "G23": "PDF数据完整性（D2-D6覆盖率+质量标记）",
    "G24": "数据交叉验证（PDF vs API 一致性）",
    "G25": "新闻分析流程完整性验证",
    "G26": "资金流向完整性（四档资金分布数据可用+报告已消费）",
    "G27": "财务指标+同比预计算一致性（financial_indicators 最新期有ROE；income 最新期有预计算同比键）",
    "G28": "杜邦数据存在+三因子闭合（dupont.status=ok + 残差<0.25pp；金融股豁免；硬校验）",
    "G29": "资产安全完整性（computed_metrics.asset_safety 可用+报告已消费；缺失不许编造）",
}

GATE_WEIGHTS = {
    "G1": 2, "G2": 2, "G3": 2, "G4": 2, "G5": 2,
    "G6": 2, "G7": 2, "G8": 2, "G9": 2, "G10": 2,
    "G11": 1, "G12": 2, "G13": 2, "G14": 2, "G15": 2,
    "G16": 2, "G17": 3, "G18": 2, "G19": 3,     "G20": 2,
    "G21": 3,  # PR 8: 高权重
    "G22": 3,  # 分业务数据完整性
    "G23": 3,  # PDF数据完整性
    "G24": 2,  # 数据交叉验证
    "G25": 2,  # 新闻分析流程完整性
    "G26": 2,  # 资金流向完整性
    "G27": 1,  # 财务指标+同比预计算一致性（Soft，单独不阻塞）
    "G28": 1,  # 杜邦三因子闭合（Soft，单独不阻塞；硬校验失败=真FAIL）
    "G29": 2,  # 资产安全完整性（Soft，单独不阻塞；有数据漏写/无数据编造=FAIL）
}

ALL_GATES = [f"G{i}" for i in range(1, 30)]

# ============================================================
# Gate 分层 (PR 10: Tier 1 Hard = Python-enforced, Tier 2 Soft = LLM self-assessment)
# ============================================================

# Tier 1: Hard Gates — 数据完整性, Python 可验证, FAIL 阻塞输出
HARD_GATES = ["G6", "G7", "G8", "G9", "G11", "G16", "G21", "G23", "G24", "G25", "G26"]

# Tier 2: Soft Gates — 内容质量, 仅 LLM 可评估, 正则只能检查格式
# 这些 Gate 在 profile_full 中 auto_pass (不阻塞输出), LLM 在 Phase 4 自评 1-5 分
SOFT_GATES = ["G1", "G2", "G3", "G4", "G5", "G10", "G12", "G13", "G14", "G15", "G17", "G18", "G19", "G20", "G22", "G27", "G28", "G29"]

# ============================================================
# Gate Profiles（与 m11-gates.md Layer 2 严格对齐）
# ============================================================

PROFILES = {
    "profile_full": {
        "name": "full",
        "description": "深度分析/整体分析/买不买/估值 → 全部 29 Gate 实跑",
        "gates": ALL_GATES,
        # Step 2 (2026-07-01): 翻 auto_pass=[] — Soft Gates 也实跑。
        # Step 0 已修 G17/G18 checker 误判（去"海外"词触发 + 同业关键词），
        # 故翻 [] 不再误阻塞。HARD_GATES/SOFT_GATES 仅作 Python-vs-LLM 分层文档保留，
        # 不再决定 auto_pass。LLM 自评分 = compute_self_score（三维，独立于 Gate 通过）。
        "auto_pass": [],
        "fail_threshold": 3,
    },
    "profile_quick": {
        "name": "quick",
        "description": "今天买不买/要不要卖 → 仅技术面+操作+信号",
        "gates": ["G1", "G3", "G4", "G11", "G13"],
        "auto_pass": ["G2", "G5", "G6", "G7", "G8", "G9", "G10", "G12",
                      "G14", "G15", "G16", "G17", "G18", "G19", "G20", "G21", "G22", "G25", "G26", "G27", "G28"],
        "fail_threshold": 2,
    },
}


# ============================================================
# Gate 验证函数
# ============================================================

def _count_pattern(text: str, pattern: str) -> int:
    """统计正则匹配次数"""
    return len(re.findall(pattern, text, re.IGNORECASE))


def _has_keywords(text: str, keywords: list[str]) -> bool:
    """检查是否包含所有关键词"""
    return all(kw in text for kw in keywords)


def _snapshot_get(data: dict, path: str):
    """从 data（即 snapshot）中按点分路径读取值"""
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current


def check_g1(report: str, data: dict) -> bool:
    """G1: 信号矩阵完整性（≥8行×3列：短/中/长）"""
    # 检查报告中是否有信号矩阵相关内容
    if "信号" not in report and "矩阵" not in report:
        return False
    # 检查是否有短/中/长三个维度
    has_dims = _has_keywords(report, ["短", "中", "长"]) or _has_keywords(report, ["短期", "中期", "长期"])
    if not has_dims:
        return False
    # 检查矩阵行数（至少8行数据行）
    matrix_rows = _count_pattern(report, r'[│|].*[│|].*[│|]')  # 表格行
    table_rows = _count_pattern(report, r'^\s*\|.*\|.*\|', )  # markdown 表格行
    return matrix_rows >= 8 or table_rows >= 8


def check_g2(report: str, data: dict) -> bool:
    """G2: 情景概率闭合（三档概率=100%，允许±1%）"""
    if "情景" not in report and "概率" not in report:
        return False
    has_scenarios = any(kw in report for kw in ["乐观", "悲观", "中性", "基准", "悲观情景", "乐观情景"])
    if not has_scenarios:
        return False
    # 只在"情景"章节内取百分比，避免后续章节的百分比污染
    # 找最后一个"情景"出现位置（跳过"模块九：情景概率"标题，取实际表格）
    idx = report.rfind('情景')
    remaining = report[idx:]
    lines = remaining.split('\n')
    section_lines = []
    for i, line in enumerate(lines):
        if i > 0 and (line.startswith('### ') or line.strip() == '---'):
            break
        section_lines.append(line)
    section = '\n'.join(section_lines)
    percentages = re.findall(r'(\d+(?:\.\d+)?)\s*%', section)
    if len(percentages) >= 3:
        # 取前3个百分比（乐观/基准/悲观），而不是最后3个
        first_three = [float(p) for p in percentages[:3]]
        total = sum(first_three)
        if 99 <= total <= 101:
            return True
        return False
    return len(percentages) >= 2


def check_g3(report: str, data: dict) -> bool:
    """G3: 决策树结构（≥3分支+1默认，每分支带触发条件+仓位+止损位）"""
    if "决策" not in report:
        return False
    # 放宽正则：支持多种决策树格式
    branch_patterns = [
        r'分支\s*\d', r'方案\s*\d', r'若触发', r'若回踩', r'若发生',
        r'├─\s*若', r'情景\s*\d', r'Branch\s*\d',
    ]
    branches = sum(_count_pattern(report, p) for p in branch_patterns)
    has_position = "仓位" in report or "持仓" in report
    has_stop = "止损" in report
    return branches >= 3 and has_position and has_stop


def check_g4(report: str, data: dict) -> bool:
    """G4: 决策↔信号一致（信号矛盾→决策树默认'不操作'）"""
    if "决策" not in report or "信号" not in report:
        return False
    # 如果有"信号矛盾"关键词，检查是否有"不操作"或"观望"
    if "矛盾" in report or "冲突" in report:
        return "不操作" in report or "观望" in report or "持有" in report
    return True  # 无矛盾信号则通过


def check_g5(report: str, data: dict) -> bool:
    """G5: 决策↔情景一致（主分支≥20%→乐观+基准≥60%）"""
    if "情景" not in report or "决策" not in report:
        return False
    # 检查是否有乐观+基准概率
    return "乐观" in report and ("基准" in report or "中性" in report)


def check_g6(report: str, data: dict) -> bool:
    """G6: 季报连续性（≥6个连续季度数据）
    P0-3 fix: 增加空数组假阳性检测 — status=ok/failed+data=[] → 明确失败
    """
    # 优先：从 snapshot 读取收入数据行数
    income = _snapshot_get(data, "s1_financial.data.income_statement")
    if isinstance(income, dict):
        snapshot_status = income.get("status", "")
        rows = income.get("data", income.get("data_full", []))
        if isinstance(rows, list):
            # P0-3 fix: 数据为空且状态异常 → 明确失败（无论 status 是 ok 还是 failed）
            if len(rows) == 0 and snapshot_status in ("ok", "failed", "empty"):
                return False
            # 有效数据 >= 6 行 → 通过
            if len(rows) >= 6:
                return True
            # 有数据但不足 → 退回文本检查
            if 0 < len(rows) < 6:
                quarter_pattern = r'20\d{2}[Qq][1-4]|20\d{2}年[第]?[一二三四1-4]季[度报]'
                return len(re.findall(quarter_pattern, report)) >= 6

    # snapshot 不存在 → 降级到报告文本检查（保留容错）
    quarter_pattern = r'20\d{2}[Qq][1-4]|20\d{2}年[第]?[一二三四1-4]季[度报]'
    quarters = re.findall(quarter_pattern, report)
    if len(quarters) >= 6:
        return True
    date_pattern = r'20\d{2}[-/](?:0[1-9]|1[0-2])[-/](?:0[1-9]|[12]\d|3[01])'
    dates = re.findall(date_pattern, report)
    return len(set(dates)) >= 6


def check_g7(report: str, data: dict) -> bool:
    """G7: 扣非对比（净利润/扣非/差额%三列已展示）"""
    # 优先：从 snapshot 检查 financial_abstract 是否有扣非数据
    fa = _snapshot_get(data, "s1_financial.data.financial_abstract.data_full")
    if fa and isinstance(fa, list):
        for row in fa:
            if '扣非' in str(row.get('指标', '')):
                return _has_keywords(report, ["扣非", "净利润"])
    # 降级：纯文本匹配
    return _has_keywords(report, ["扣非", "净利润"]) or _has_keywords(report, ["扣非净利润", "非经常性"])


def check_g8(report: str, data: dict) -> bool:
    """G8: 现金流三件套（CFO/CFI/CFF/FCF/FCF净利润比）
    P0-3 fix: 增加空数组假阳性检测 — status=ok/failed+data=[] → 明确失败
    """
    # P0-3: 检查 snapshot 结构完整性
    cf_section = _snapshot_get(data, "s1_financial.data.cash_flow")
    if isinstance(cf_section, dict):
        cf_status = cf_section.get("status", "")
        cf_data = cf_section.get("data", cf_section.get("data_full", []))
        if isinstance(cf_data, list):
            # P0-3 fix: 数据为空且状态异常 → 明确失败
            if len(cf_data) == 0 and cf_status in ("ok", "failed", "empty"):
                return False
            # 有数据 → 正常验证
            if len(cf_data) > 0:
                for row in cf_data:
                    if isinstance(row, dict) and row.get('经营活动产生的现金流量净额') is not None:
                        fcf_present = "FCF" in report or "自由现金流" in report
                        cfo_present = "CFO" in report or "经营性现金流" in report or "经营活动现金流" in report
                        return fcf_present and cfo_present

    # snapshot 不存在或无数据 → 降级到报告文本检查（保留容错）
    fcf_present = "FCF" in report or "自由现金流" in report
    cfo_present = "CFO" in report or "经营性现金流" in report or "经营活动现金流" in report
    return fcf_present and cfo_present


def check_g9(report: str, data: dict) -> bool:
    """G9: 利润归因闭合（ΔNetProfit四项分解闭合）"""
    # 优先：从 snapshot 检查收入数据（需要≥2期）
    rows = _snapshot_get(data, "s1_financial.data.income_statement.data_full")
    if rows and isinstance(rows, list) and len(rows) >= 2:
        return "利润归因" in report or ("归因" in report and "净利润" in report)
    # 降级：纯文本匹配
    return "利润归因" in report or ("归因" in report and "净利润" in report)


def check_g10(report: str, data: dict) -> bool:
    """G10: 事件扫描完成（高优8类+低优10类，每类有状态标记）+ 内容质量检查"""
    if "事件扫描" not in report and "事件" not in report:
        return False
    
    status_markers = _count_pattern(report, r'(✅|❌|⚠️|已扫描|未发现|已排查|无异常)')
    if status_markers < 8:
        return False

    bad_patterns = [
        r'^\s*[-*]\s*(?:担保|关联交易|高管变动|资产减值|停复牌|可转债|审计意见|环保|诉讼)\s*[：:]\s*(?:无|未发现|无异常|无重大)',
        r'^\s*(?:担保|关联交易|高管变动|资产减值|停复牌|可转债|审计意见|环保|诉讼)\s*(?:无异常|无重大|未发现)',
    ]
    bad_lines = 0
    for pattern in bad_patterns:
        bad_lines += len(re.findall(pattern, report, re.MULTILINE | re.IGNORECASE))

    if bad_lines >= 3:
        print(f"  ⚠️  G10 格式警告：发现 {bad_lines} 条无异常事件被逐条罗列，"
              f"应合并为一行 '✅ 已扫描无异常' 格式（规则：s5-events-18 规则一）")

    quant_patterns = [
        r'\d+\.?\d*(?:万元|亿元)',
        r'\d+\.?\d*%',
        r'\d{4}年\d{1,2}月\d{1,2}日',
    ]
    quant_count = sum(_count_pattern(report, p) for p in quant_patterns)
    
    src_count = _count_pattern(report, r'\[src:')
    event_details = _count_pattern(report, r'(?:公告|披露|表示|指出|称)')
    
    quality_score = 0
    if quant_count >= 3:
        quality_score += 30
    if src_count >= 2:
        quality_score += 30
    if event_details >= 2:
        quality_score += 20
    if status_markers >= 8:
        quality_score += 20
    
    if quality_score < 60:
        print(f"  ⚠️  G10 内容质量不足: {quality_score}/100 (需>=60)")
        return False
    
    return True


def check_g11(report: str, data: dict) -> bool:
    """G11: 数据时效性声明（报告开头声明数据截止时间；表格仅在数据来源不同时标注日期）"""
    report_header = report[:500] if len(report) > 500 else report
    global_timestamp_patterns = [
        r'数据[截止至]+[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)',
        r'数据[截止至]+[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?\s*\d{1,2}[：:]\d{2})',
        r'[截止至]+[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)\s*的?数据',
        r'报告[生成制作]+[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)',
    ]
    
    has_global_timestamp = any(re.search(p, report_header) for p in global_timestamp_patterns)
    if has_global_timestamp:
        return True
    
    table_lines = re.findall(r'^\s*\|.*\|.*$', report, re.MULTILINE)
    date_keywords = ["日期", "时间", "截止", "报告期", "数据日期", "截至", "公布日"]
    tables_with_date = sum(1 for t in table_lines if any(kw in t for kw in date_keywords))
    return tables_with_date > 0


def check_g12(report: str, data: dict) -> bool:
    """G12: 局限性披露（≥3条具体局限）"""
    if "局限" not in report and "局限性" not in report and "不足" not in report:
        return False
    # 统计局限性条目
    limitation_items = _count_pattern(report, r'(?:局限|不足|限制|风险提示|数据限制|⚠️)')
    return limitation_items >= 3


def check_g13(report: str, data: dict) -> bool:
    """G13: 持仓↔决策一致（若用户提供持仓信息，决策树应考虑持仓语境）"""
    # 无持仓信息时 auto_pass
    if data.get("holding_status") is None:
        return True
    return "决策" in report


def check_g14(report: str, data: dict) -> bool:
    """G14: TD逐根展示（TD计数表≥9行+结论）"""
    if "TD" not in report:
        return False
    # 检查是否有 TD 计数表
    td_rows = _count_pattern(report, r'(?:TD|计数|Setup)\s*\d+')
    return td_rows >= 9


def check_g15(report: str, data: dict) -> bool:
    """G15: 同业对比（≥2家可比公司+≥4指标）"""
    # 检查是否有同业对比表
    if "同业" not in report and "可比" not in report and "对比" not in report:
        return False
    # 检查指标关键词
    metrics = ["营收增速", "净利增速", "毛利率", "PE", "PB", "ROE", "PS", "PEG", "EV/EBITDA"]
    metric_count = sum(1 for m in metrics if m in report)
    # 检查是否有至少2家公司的数据
    peer_pattern = r'(?:公司|股票|简称)[:：]?\s*\S+'
    return metric_count >= 4


def _extract_contract_liab(data: dict):
    """从 snapshot 资产负债表提取最新合同负债值（元，float 或 None）。"""
    # data 优先 + data_full 兜底（对齐 G6/G8 范式；修正只读 data_full 导致 G16 从不命中）
    bs = (_snapshot_get(data, "s1_financial.data.balance_sheet.data")
          or _snapshot_get(data, "s1_financial.data.balance_sheet.data_full"))
    if not bs or not isinstance(bs, list):
        return None
    for row in bs:
        if not isinstance(row, dict):
            continue
        v = row.get('合同负债')
        if v is None:
            continue
        try:
            fv = float(v)
            if fv != 0:  # 跳过 0 / None 占位
                return fv
        except (TypeError, ValueError):
            continue
    return None


def check_g16(report: str, data: dict) -> bool:
    """G16: 订单Layer6核对（合同负债核对偏差≤15%）

    v2 真实核对（修复橡皮章）：
    - snapshot 有合同负债值 V（元）→ 归一化为亿，与报告"合同负债"行的数值比对：
      a. 冲突检测：报告合同负债行的 X亿 若与 V 偏离 >50% 且无 [src:] 溯源 → FAIL（疑似编造）
      b. 数值对齐：报告出现 V(亿) 字符串 → 计为 grounded
      c. 合同负债行带 [src: snapshot/websearch] 溯源 → 计为 grounded（精确值交 G21/G24）
      d. 至少一个 grounded + 含核对关键词 → PASS
    - snapshot 无合同负债（银行/缺失）→ 文本回退（保留原容错）。
    """
    snap_cl = _extract_contract_liab(data)
    has_crosscheck = any(kw in report for kw in ["核对", "交叉验证", "偏差", "验证"])

    if snap_cl is None:
        # 无数据 → 文本回退
        if "合同负债" not in report:
            return False
        if not has_crosscheck:
            return False
        deviation = re.search(r'偏差[：:]*\s*(\d+(?:\.\d+)?)\s*%', report)
        if deviation:
            return float(deviation.group(1)) <= 15
        return True

    # snapshot 有数据 → 报告必须消费
    if "合同负债" not in report:
        return False

    cl_yi = snap_cl / 1e8  # 元 → 亿
    # 报告中所有"合同负债"行
    cl_lines = [ln for ln in report.split('\n') if '合同负债' in ln]

    # (a) 冲突检测：合同负债行里 X亿 若与 snapshot 偏离 >50% 且无溯源 → FAIL
    for ln in cl_lines:
        if '[src:' in ln:
            continue  # 该行已溯源，精确值交给 G21/G24，不在此判冲突
        for m in re.finditer(r'(\d+\.?\d*)\s*亿', ln):
            try:
                rv = float(m.group(1))
            except ValueError:
                continue
            if rv > 0 and cl_yi > 0:
                ratio = max(rv, cl_yi) / min(rv, cl_yi)
                if ratio > 1.5:
                    return False  # 数值冲突，疑似编造

    # (b) 数值对齐
    aligned_candidates = {f"{cl_yi:.2f}", f"{round(cl_yi, 1):.1f}"}
    if cl_yi >= 1:
        aligned_candidates.add(f"{int(round(cl_yi))}")
    value_aligned = any(c in report for c in aligned_candidates)

    # (c) 合同负债行带溯源
    has_src_on_cl_line = any('[src:' in ln for ln in cl_lines)

    if not has_crosscheck:
        return False
    return value_aligned or has_src_on_cl_line


def check_g17(report: str, data: dict) -> bool:
    """G17: 海外关税完整（海外敞口公司必须有T0-T4分析）

    海外敞口只认 data 层显式标记 has_overseas_exposure，不再用 report 里"海外"
    一词触发（描述台资背景/海外讨论等文字会误判）。T0-T4 关税分析为 LLM+websearch
    手动项（数据层不生产），未声明海外敞口即放行。
    """
    if not data.get("has_overseas_exposure"):
        return True  # 未声明海外敞口 → 不要求 T0-T4
    return "T0" in report and "T1" in report


def check_g18(report: str, data: dict) -> bool:
    """G18: 竞品对标（Layer5可比公司，机械底线：报告含同业对比内容）

    "≥3家"无法可靠机械计数（公司名形态多变），本 checker 只做底线校验：报告必须
    含同业对比内容（同业/同行/相比/对比/对标/竞品/可比 任一）。精确数量由 LLM 自评
    与报告审阅把关。
    """
    peer_kws = ("同业", "同行", "相比", "对比", "对标", "竞品", "可比")
    return any(kw in report for kw in peer_kws)


def check_g19(report: str, data: dict) -> bool:
    """G19: 营收预测区间（Layer8给区间或标注'无法量化'）"""
    if "预测" not in report and "预期" not in report:
        return False
    # 检查是否有区间或"无法量化"
    has_range = bool(re.search(r'\d+\s*[-~–]\s*\d+', report))
    has_cannot_quantify = "无法量化" in report or "难以预测" in report
    return has_range or has_cannot_quantify


def check_g20(report: str, data: dict) -> bool:
    """G20: 口径一致（Layer0口径=Layer8输出）

    子串匹配：分类器统一输出 "X股" 格式（金融股/银行股...），旧 list `in` 精确
    匹配永不命中"金融股"。改子串匹配兼容 "银行"/"金融" 等出现在 stock_type
    任意位置，未来加"医药股"等新类不影响本 gate。
    """
    # 金融股不得输出"在手订单"（在手订单是订单型公司口径，金融股无此概念）
    stock_type = data.get("stock_type", "")
    if any(kw in stock_type for kw in ("金融", "银行", "保险", "券商")):
        if "在手订单" in report or "订单饱和" in report:
            return False
    return True


def check_g21(report: str, data: dict) -> bool:
    """G21: SOURCE溯源（报告[src:]标记→snapshot路径验证）
    P1-1 fix: 支持 snapshot + websearch 双格式降级
    1. 解析报告中所有 [src: snapshot.X.Y.Z] 或 [src: websearch XXX] 标记
    2. snapshot 存在时验证路径；snapshot 为空时接受 websearch 标记（>=2）
    3. 模块级检测：模块 2/2.5/5 各需 >=2 个 [src:] 标记
    """
    snapshot = data
    snapshot_pattern = r'\[src:\s*snapshot\.([^\]]+)\]'
    websearch_pattern = r'\[src:\s*websearch\s+([^\]]+)\]'
    # 容错：无 snapshot. 前缀但匹配合法 scene 命名的 [src:]（旧文档/作者笔误），计入不报错
    bare_scene_pattern = r'\[src:\s*((?:s\d+_\w+|valuation_\w+|consensus_forecast|computed_metrics|s36_\w+|s55_\w+)\.[^\]]+)\]'

    snapshot_tags = list(re.finditer(snapshot_pattern, report))
    websearch_tags = list(re.finditer(websearch_pattern, report))
    bare_tags = list(re.finditer(bare_scene_pattern, report))
    all_tags = snapshot_tags + websearch_tags + bare_tags

    if not all_tags:
        return False

    # P1-1 fix: snapshot 为空时降级 — 只接受 websearch 标记 >= 2 个
    # Gap-3 fix: 不接受 snapshot 标记（snapshot 为空时无法验证路径）
    if not snapshot or snapshot == {}:
        # 只接受 websearch 标记，不接受 snapshot/bare 标记
        websearch_only = [t for t in all_tags if t not in snapshot_tags and t not in bare_tags]
        return len(websearch_only) >= 2

    # 正常模式：snapshot. 标记 + bare scene 标记都按 snapshot 子路径验证
    path_failures = []
    verified_snapshot_like = snapshot_tags + bare_tags
    if verified_snapshot_like:
        for match in verified_snapshot_like:
            path = match.group(1)
            parts = path.split(".")
            current = snapshot
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = None
                    break
            if current is None:
                path_failures.append(f"路径不存在: {path}")
        if path_failures:
            return False
    elif len(websearch_tags) < 2:
        # 只有 websearch 标记且不足 2 个
        return False

    return True


def check_g22(report: str, data: dict) -> bool:
    """G22: 分业务数据完整性（模块二包含分业务/分产品/分行业表格）"""
    has_segment = any(kw in report for kw in ["分业务", "分产品", "分行业", "业务分拆"])
    if not has_segment:
        return False
    has_revenue = "营业收入" in report or "营收" in report
    has_margin = "毛利率" in report or "毛利" in report
    return has_revenue and has_margin


def check_g23(report: str, data: dict) -> bool:
    """G23: PDF数据完整性（D2-D6覆盖率+质量标记）"""
    quality = data.get("_quality_markers", {})

    # D2 审计意见必须存在
    if quality.get("D2_audit", {}).get("status") not in ("ok",):
        return False

    # D3/D4/D5 至少有 2 个成功
    required_fields = ["D3_dividend", "D4_holders", "D5_biz_breakdown"]
    ok_count = sum(1 for f in required_fields if quality.get(f, {}).get("status") == "ok")
    if ok_count < 2:
        # 检查是否有 LLM 兜底结果
        llm_tasks = data.get("_llm_fallback_tasks", [])
        if not llm_tasks:
            return False

    # D6 必须存在
    if quality.get("D6_geo_revenue", {}).get("status") not in ("ok", "partial"):
        return False

    return True


def check_g24(report: str, data: dict) -> bool:
    """G24: 数据交叉验证（PDF vs API 一致性）"""
    warnings = data.get("_cross_validation_warnings", [])
    severe = []
    for w in warnings:
        if "差异=" in w:
            try:
                pct_str = w.split("差异=")[1].split("%")[0]
                if float(pct_str) > 10:
                    severe.append(w)
            except (ValueError, IndexError):
                pass
    return len(severe) == 0


def check_g25(report: str, data: dict) -> bool:
    """G25: 新闻分析流程完整性验证"""
    s5_events = data.get("s5_events", {})
    news_data = s5_events.get("data", {}).get("news", {})
    
    high_count = len(news_data.get("high_value", []))
    medium_count = len(news_data.get("medium_value", []))
    
    if high_count == 0 and medium_count == 0:
        return True
    
    python_layer = news_data.get("_python_layer", "")
    if python_layer != "completed":
        return False
    
    if "事件扫描" not in report and "事件" not in report:
        return False
    
    src_count = _count_pattern(report, r'\[src:')
    if high_count > 0 and src_count == 0:
        return False
    
    return True


def check_g26(report: str, data: dict) -> bool:
    """G26: 资金流向完整性（四档资金分布数据可用+报告已消费）

    数据源：westock fund flow（腾讯源）。westock 给每档净额，runner 按正负拆分 in/out，
    故 items 4 档 + status=ok 自动满足（不再因外部限流而 FAIL）。
    富字段（trend_5d/10d/20d、rank_market/rank_industry、circ_rate）由 m10 报告消费，
    但**不计入本 gate**——缺富字段不阻断（避免新源偶发缺字段致 G26 更脆）。

    验证点：
    1. snapshot 中 s3_fund_flow.data.fund_flow.status == "ok"
    2. fund_flow.items 包含 4 档数据（特大单/大单/中单/小单）
    3. 报告中包含资金流向相关关键词
    """
    # 1. 检查 snapshot 中的资金流向数据
    fund_flow = _snapshot_get(data, "s3_fund_flow.data.fund_flow")
    if not fund_flow or fund_flow.get("status") != "ok":
        return False
    
    # 2. 检查四档数据完整性
    items = fund_flow.get("items", [])
    if len(items) < 4:
        return False
    
    # 验证四档标签
    expected_names = {"特大单", "大单", "中单", "小单"}
    actual_names = {item.get("name") for item in items}
    if not expected_names.issubset(actual_names):
        return False
    
    # 3. 检查报告是否消费了资金流向数据
    fund_keywords = ["资金流向", "主力资金", "大单", "小单", "特大单", "净流入", "净流出", "资金分布"]
    has_fund_data = any(kw in report for kw in fund_keywords)
    
    return has_fund_data


def check_g27(report: str, data: dict) -> bool:
    """G27: 财务指标 + 同比预计算一致性（Soft tier，weight 1，单独不阻塞阈值 3）。

    校验 Section 3 新增数据确实落进 snapshot 且非空，防止「拉了数据但 snapshot 空 / LLM 无键可读」
    的隐性浪费（红线①同类）。与 m2 §2.12 / §2.1-2.9 同一 snapshot 路径，单一真相源。
    ① financial_indicators.data_full 最新期含加权ROE 或 摊薄ROE（非 None）；
    ② income_statement 最新期行含至少一个 *_同比% 键且非 None。
    金融股天然豁免：不校验总资产周转率（数据语义 N/A），ROE/BVPS/EPS 金融股全有。
    """
    fi = _snapshot_get(data, "s1_financial.data.financial_indicators")
    fi_rows = fi.get("data_full") if isinstance(fi, dict) else None

    def _latest(name):
        if not isinstance(fi_rows, list):
            return None
        for r in fi_rows:
            if isinstance(r, dict) and str(r.get("指标", "")).startswith(name):
                for k, v in r.items():  # 首个非「指标」键 = 最新期（periods 新在前）
                    if k != "指标":
                        return v
        return None

    # ① 最新期含加权ROE 或 摊薄ROE
    if not any(_latest(n) not in (None, "", "nan") for n in ("加权净资产收益率", "净资产收益率")):
        return False

    # ② income 最新期行含至少一个预计算同比键且非 None
    inc = _snapshot_get(data, "s1_financial.data.income_statement")
    inc_rows = None
    if isinstance(inc, dict):
        inc_rows = inc.get("data", inc.get("data_full"))
    if not isinstance(inc_rows, list) or not inc_rows:
        return False
    latest = inc_rows[0] or {}
    return any(latest.get(k) is not None for k in latest if str(k).endswith("_同比%"))


def check_g28(report: str, data: dict) -> bool:
    """G28: 杜邦数据存在 + 三因子闭合（Soft tier，weight 1，硬校验：失败=真 FAIL）。

    新浪杜邦 vFD_DupontAnalysis 经 runner._fetch_sina_dupont 总拉入 snapshot，源端统一平均口径，
    残差<0.25pp。闭合判定在 fetcher 的 _dupont_check_closure 算好（绝对值反算
    归母净利润/平均归母权益×100 vs 实测 ROE），gate 只读结果。
    ① dupont.status == "ok"（拉取成功，否则硬 FAIL，真实反映数据缺失）；
    ② _closure_check.applicable=False 放行（金融股无总资产周转率，三因子不适用）；
    ③ applicable=True 时要求 closed=True 且残差<0.25pp。
    新 snapshot 经 runner 升级后自然含 dupont；历史旧 snapshot 无该字段则 FAIL（weight=1 不硬阻断）。
    """
    dupont = _snapshot_get(data, "s1_financial.data.dupont")
    if not isinstance(dupont, dict) or dupont.get("status") != "ok":
        return False
    cc = (dupont.get("data") or {}).get("_closure_check") or {}
    if not cc.get("applicable", True):  # 金融股（无总资产周转率）→ 放行
        return True
    try:
        return bool(cc.get("closed", False)) and float(cc.get("residual_pp", 99)) < 0.25
    except (TypeError, ValueError):
        return False


def check_g29(report: str, data: dict) -> bool:
    """G29: 资产安全完整性（computed_metrics.asset_safety 可用+报告已消费；缺失不许编造）。

    范式同 G26：snapshot 有 asset_safety(status=ok) → 报告必须消费关键数值/比率；
    snapshot 缺失(status=degraded) → 报告可跳过但不许编造具体数值。
    三路径：正确数据+消费=PASS；缺失+不编造=PASS；有数据漏写=FAIL；无数据编造数值=FAIL。
    weight 2, SOFT, auto_pass（quick 模式跳过）。
    """
    am = _snapshot_get(data, "computed_metrics.asset_safety")
    has_data = isinstance(am, dict) and am.get("status") == "ok"
    consumes = bool(re.search(r"(货币资金|有息负债|商誉占比?|cash_to_debt|资产负债率|资产负债结构)", report))
    if has_data and not consumes:
        return False
    # 无数据却编造具体数值（货币资金/有息负债：XX亿）→ FAIL
    if not has_data and re.search(r"(货币资金|有息负债)\s*[：:]\s*[\d.]+\s*亿", report):
        return False
    return True


# 注册所有 Gate 验证函数
GATE_CHECKERS = {
    "G1": check_g1, "G2": check_g2, "G3": check_g3, "G4": check_g4,
    "G5": check_g5, "G6": check_g6, "G7": check_g7, "G8": check_g8,
    "G9": check_g9, "G10": check_g10, "G11": check_g11, "G12": check_g12,
    "G13": check_g13, "G14": check_g14, "G15": check_g15, "G16": check_g16,
    "G17": check_g17, "G18": check_g18, "G19": check_g19, "G20": check_g20,
    "G21": check_g21, "G22": check_g22, "G23": check_g23, "G24": check_g24,
    "G25": check_g25, "G26": check_g26, "G27": check_g27, "G28": check_g28,
    "G29": check_g29,
}


def get_profile(profile_name: str) -> dict:
    """获取 Profile 配置"""
    if profile_name not in PROFILES:
        print(f"⚠️  未知 Profile: {profile_name}，使用 profile_full")
        return PROFILES["profile_full"]
    return PROFILES[profile_name]


def compute_score(passed_gates: list[str], failed_gates: list[str], profile: dict) -> int:
    """计算自评分（0-100）"""
    total_weight = 0
    earned_weight = 0
    for gate in profile["gates"]:
        if gate in profile["auto_pass"]:
            continue  # auto_pass 不计入评分
        w = GATE_WEIGHTS.get(gate, 2)
        total_weight += w
        if gate in passed_gates:
            earned_weight += w
    if total_weight == 0:
        return 100
    return round(earned_weight / total_weight * 100)


# ============================================================
# 自评分（脚本产出，A2 修复：禁止手填）
# ============================================================

# 预期核心 scene 路径 —— 模式A 数据消费链的关键节点
_EXPECTED_SCENES = [
    ("s1_financial.data.income_statement", "财报-收入"),
    ("s1_financial.data.balance_sheet", "财报-资产负债"),
    ("s1_financial.data.cash_flow", "财报-现金流"),
    ("s2_quote_kline", "行情K线"),
    ("s3_fund_flow.data.fund_flow", "资金流向"),
    ("valuation_snapshot.data.analystRating", "机构评级"),
    ("s55_industry", "行业"),
    ("s6_macro.data.pmi", "宏观"),
    ("s5_events.data.news", "事件新闻"),
    ("s8_a_share", "A股特征"),
]


def _scene_has_data(val) -> bool:
    """判断一个 scene 的值是否真的有数据（非空/非占位）。

    修复 Gap-1：递归检查 data 字段内部的 status，
    避免 scene envelope 在场但 data.status=failed 时误判为有数据。

    两种 scene 结构：
    1. 深路径（leaf node）: {status: "ok"/"failed", data: [...]}  → 直接检查 status
    2. 浅路径（envelope）: {scene: "s2", data: {status: "failed"}} → 需递归检查 data.status
    """
    if val is None:
        return False
    if isinstance(val, (str,)):
        return val.strip() != ""
    if isinstance(val, dict):
        envelope_status = val.get("status", "")
        if envelope_status in ("failed", "error", "throttled"):
            return False

        data = val.get("data", val.get("data_full"))

        if isinstance(data, dict):
            # Gap-1 fix: recursively check status inside data dict
            data_status = data.get("status", "")
            if data_status in ("failed", "error", "throttled"):
                return False
            return bool(data)

        if isinstance(data, list):
            return len(data) > 0

        # No data field or empty data: rely on envelope status
        if envelope_status in ("ok", "partial"):
            return True

        # Gap-1 fix: 裸 error 信封（无 status/data，仅含 error 键）→ 视为无数据
        # 例：valuation_snapshot.data.analystRating = {"error":"Expecting value..."}
        if "error" in val and "status" not in val and "data" not in val:
            return False

        return bool(val)

    if isinstance(val, list):
        return len(val) > 0
    return bool(val)


def compute_self_score(report: str, data: dict, gate_result: dict) -> dict:
    """三维脚本化自评分（替代 m11 手填分数）。

    维度：
      - data_coverage (40%): 10 个核心 scene 的数据命中率
      - gate_pass (40%): 复用 gate 引擎分数（compute_score）
      - source_traceability (20%): 报告 [src:] 标记中 snapshot 源占比（vs websearch）
    返回 {score, dimensions, weights, rubric_version}。
    """
    # Dim 1: 数据覆盖
    hit = sum(1 for path, _ in _EXPECTED_SCENES if _scene_has_data(_snapshot_get(data, path)))
    coverage_pct = round(hit / len(_EXPECTED_SCENES) * 100)

    # Dim 2: gate pass（复用引擎分数）
    gate_pct = gate_result.get("score", 0)

    # Dim 3: source traceability（snapshot. 严匹配 + bare scene 容错均计入分子）
    snap_tags = len(re.findall(r'\[src:\s*snapshot\.', report))
    bare_tags = len(re.findall(r'\[src:\s*(?:s\d+_\w+|valuation_\w+|consensus_forecast|computed_metrics|s36_\w+|s55_\w+)\.', report))
    web_tags = len(re.findall(r'\[src:\s*websearch', report))
    total_tags = snap_tags + bare_tags + web_tags
    src_pct = round((snap_tags + bare_tags) / total_tags * 100) if total_tags else 0

    score = round(coverage_pct * 0.4 + gate_pct * 0.4 + src_pct * 0.2)
    return {
        "score": score,
        "dimensions": {
            "data_coverage": {"score": coverage_pct, "hit": hit, "total": len(_EXPECTED_SCENES)},
            "gate_pass": {"score": gate_pct},
            "source_traceability": {"score": src_pct, "snapshot_tags": snap_tags,
                                    "bare_scene_tags": bare_tags, "websearch_tags": web_tags},
        },
        "weights": {"data_coverage": 0.4, "gate_pass": 0.4, "source_traceability": 0.2},
        "rubric_version": "v2.1-script",
    }
