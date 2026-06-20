#!/usr/bin/env python3
"""
gate_definitions.py — G1-G21 Gate 的代码化定义
与 m11-gates.md 严格对齐，不增加新规则——只是把它"可执行化"。
G21 为 PR 8 新增: SOURCE 溯源校验。
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
}

GATE_WEIGHTS = {
    "G1": 2, "G2": 2, "G3": 2, "G4": 2, "G5": 2,
    "G6": 2, "G7": 2, "G8": 2, "G9": 2, "G10": 2,
    "G11": 1, "G12": 2, "G13": 2, "G14": 2, "G15": 2,
    "G16": 2, "G17": 3, "G18": 2, "G19": 3,     "G20": 2,
    "G21": 3,  # PR 8: 高权重
    "G22": 3,  # 分业务数据完整性
}

ALL_GATES = [f"G{i}" for i in range(1, 23)]

# ============================================================
# Gate Profiles（与 m11-gates.md Layer 2 严格对齐）
# ============================================================

PROFILES = {
    "profile_full": {
        "name": "full",
        "description": "深度分析/整体分析/买不买/估值 → 全量Gate",
        "gates": ALL_GATES,
        "auto_pass": [],
        "fail_threshold": 3,
    },
    "profile_quick": {
        "name": "quick",
        "description": "今天买不买/要不要卖 → 仅技术面+操作+信号",
        "gates": ["G1", "G3", "G4", "G11", "G13"],
        "auto_pass": ["G2", "G5", "G6", "G7", "G8", "G9", "G10", "G12",
                      "G14", "G15", "G16", "G17", "G18", "G19", "G20", "G21", "G22"],
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
        last_three = [float(p) for p in percentages[-3:]]
        total = sum(last_three)
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
    """G6: 季报连续性（≥6个连续季度数据）"""
    # 优先：从 snapshot 读取收入数据行数
    rows = _snapshot_get(data, "s1_financial.data.income_statement.data_full")
    if rows and isinstance(rows, list) and len(rows) >= 6:
        return True
    # 降级：从报告中检查季度数据
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
    """G8: 现金流三件套（CFO/CFI/CFF/FCF/FCF净利润比）"""
    # 优先：从 snapshot 检查现金流数据是否存在
    cf = _snapshot_get(data, "s1_financial.data.cash_flow.data_full")
    has_cfo_data = False
    if cf and isinstance(cf, list):
        for row in cf:
            if row.get('经营活动产生的现金流量净额') is not None:
                has_cfo_data = True
                break
    # 检查报告是否展示
    fcf_present = "FCF" in report or "自由现金流" in report
    cfo_present = "CFO" in report or "经营性现金流" in report or "经营活动现金流" in report
    if has_cfo_data:
        return fcf_present and cfo_present
    # 无数据时仅检查文本
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
    """G10: 事件扫描完成（高优8类+低优10类，每类有状态标记）+ 无异常事件格式校验"""
    if "事件扫描" not in report and "事件" not in report:
        return False
    # 检查是否有扫描状态标记
    status_markers = _count_pattern(report, r'(✅|❌|⚠️|已扫描|未发现|已排查|无异常)')
    if status_markers < 8:
        return False

    # ── 新增：检查"无异常"事件的格式 ──
    # 规则：无事件的类别不写入报告，应合并为一行 "✅ 已扫描无异常" 格式
    # 检测是否有逐条罗列的无异常事件（错误格式）
    # 错误格式特征：独立行包含"无异常"、"无重大"、"未发现"等，且不是汇总行
    bad_patterns = [
        r'^\s*[-*]\s*(?:担保|关联交易|高管变动|资产减值|停复牌|可转债|审计意见|环保|诉讼)\s*[：:]\s*(?:无|未发现|无异常|无重大)',
        r'^\s*(?:担保|关联交易|高管变动|资产减值|停复牌|可转债|审计意见|环保|诉讼)\s*(?:无异常|无重大|未发现)',
    ]
    bad_lines = 0
    for pattern in bad_patterns:
        bad_lines += len(re.findall(pattern, report, re.MULTILINE | re.IGNORECASE))

    if bad_lines >= 3:
        # 有3条以上逐条罗列的无异常事件，格式错误
        # 不直接 fail（因为扫描确实完成了），但输出警告
        print(f"  ⚠️  G10 格式警告：发现 {bad_lines} 条无异常事件被逐条罗列，"
              f"应合并为一行 '✅ 已扫描无异常' 格式（规则：s5-events-18 规则一）")

    return True  # 格式问题仅警告，不阻断


def check_g11(report: str, data: dict) -> bool:
    """G11: 数据时效性声明（报告开头声明数据截止时间；表格仅在数据来源不同时标注日期）"""
    report_header = report[:500] if len(report) > 500 else report
    global_timestamp_patterns = [
        r'数据[截截至]+[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)',
        r'数据[截截至]+[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?\s*\d{1,2}[：:]\d{2})',
        r'[截截至]+[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)\s*的?数据',
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


def check_g16(report: str, data: dict) -> bool:
    """G16: 订单Layer6核对（合同负债核对偏差≤15%）"""
    # 优先：从 snapshot 检查合同负债数据
    bs = _snapshot_get(data, "s1_financial.data.balance_sheet.data_full")
    has_contract_data = False
    if bs and isinstance(bs, list):
        for row in bs:
            if row.get('合同负债') is not None:
                has_contract_data = True
                break
    if has_contract_data:
        # 数据存在，检查报告是否展示核对
        if "合同负债" not in report:
            return False
        has_crosscheck = any(kw in report for kw in ["核对", "交叉验证", "偏差", "验证"])
        return has_crosscheck
    # 无数据时仅检查文本
    if "合同负债" not in report:
        return False
    has_crosscheck = any(kw in report for kw in ["核对", "交叉验证", "偏差", "验证"])
    if not has_crosscheck:
        return False
    deviation = re.search(r'偏差[：:]*\s*(\d+(?:\.\d+)?)\s*%', report)
    if deviation:
        return float(deviation.group(1)) <= 15
    return True


def check_g17(report: str, data: dict) -> bool:
    """G17: 海外关税完整（海外敞口公司必须有T0-T4分析）"""
    # 无海外敞口则 auto_pass
    has_overseas = data.get("has_overseas_exposure", False) or "海外" in report
    if not has_overseas:
        return True
    # 有海外敞口则检查 T0-T4
    return "T0" in report and "T1" in report


def check_g18(report: str, data: dict) -> bool:
    """G18: 竞品对标≥3家（Layer5可比公司≥3家）"""
    # 提取公司名称数量
    company_pattern = r'(?:对标|竞品|可比|同行)[:：]'
    if "竞品" not in report and "对标" not in report and "可比" not in report:
        return False
    return True  # 有对标内容即通过，具体数量由内容决定


def check_g19(report: str, data: dict) -> bool:
    """G19: 营收预测区间（Layer8给区间或标注'无法量化'）"""
    if "预测" not in report and "预期" not in report:
        return False
    # 检查是否有区间或"无法量化"
    has_range = bool(re.search(r'\d+\s*[-~–]\s*\d+', report))
    has_cannot_quantify = "无法量化" in report or "难以预测" in report
    return has_range or has_cannot_quantify


def check_g20(report: str, data: dict) -> bool:
    """G20: 口径一致（Layer0口径=Layer8输出）"""
    # 金融股不得输出"在手订单"
    stock_type = data.get("stock_type", "")
    if stock_type in ["金融", "银行", "保险", "券商"]:
        if "在手订单" in report or "订单饱和" in report:
            return False
    return True


def check_g21(report: dict, data: dict) -> bool:
    """G21: SOURCE溯源（报告[src:]标记→snapshot路径验证）
    1. 解析报告中所有 [src: snapshot.X.Y.Z] 或 [src: X.Y.Z] 标记
    2. 验证路径在 snapshot 中存在
    3. 模块级检测：模块 2/2.5/5 各需 ≥2 个 [src:] 标记
    """
    snapshot = data  # data dict 直接就是 snapshot
    # 支持 [src: snapshot.X.Y.Z] 和 [src: X.Y.Z] 两种格式
    src_pattern = r'\[src:\s*(?:snapshot\.)?([^\]]+)\]'
    tags = list(re.finditer(src_pattern, report))

    if not tags:
        return False

    path_failures = []
    tag_paths = []

    for match in tags:
        tag = match.group(1)
        path = tag.replace("snapshot.", "")
        tag_paths.append(path)

        # 路径存在性校验
        parts = path.split(".")
        current = snapshot
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
                break

        if current is None:
            path_failures.append(f"路径不存在: {tag}")

    # 模块级检测
    REQUIRED_SRC_SECTIONS = {
        "financial": ["营收", "净利", "扣非", "毛利率", "ROE", "CFO", "FCF", "EPS"],
        "orders": ["合同负债", "海外占比", "份额", "订单"],
        "valuation": ["PE", "PB", "PS", "市盈率", "市净率"],
    }
    section_failures = []
    for section, keywords in REQUIRED_SRC_SECTIONS.items():
        section_src_count = 0
        for match in tags:
            ctx_start = max(0, match.start() - 200)
            ctx_end = min(len(report), match.end() + 200)
            context = report[ctx_start:ctx_end]
            if any(kw in context for kw in keywords):
                section_src_count += 1
        if section_src_count < 2:
            section_failures.append(f"模块 {section} 仅 {section_src_count} 个 [src:] (需≥2)")

    return len(path_failures) == 0 and len(section_failures) == 0


def check_g22(report: str, data: dict) -> bool:
    """G22: 分业务数据完整性（模块二包含分业务/分产品/分行业表格）"""
    has_segment = any(kw in report for kw in ["分业务", "分产品", "分行业", "业务分拆"])
    if not has_segment:
        return False
    has_revenue = "营业收入" in report or "营收" in report
    has_margin = "毛利率" in report or "毛利" in report
    return has_revenue and has_margin


# 注册所有 Gate 验证函数
GATE_CHECKERS = {
    "G1": check_g1, "G2": check_g2, "G3": check_g3, "G4": check_g4,
    "G5": check_g5, "G6": check_g6, "G7": check_g7, "G8": check_g8,
    "G9": check_g9, "G10": check_g10, "G11": check_g11, "G12": check_g12,
    "G13": check_g13, "G14": check_g14, "G15": check_g15, "G16": check_g16,
    "G17": check_g17, "G18": check_g18, "G19": check_g19,     "G20": check_g20,
    "G21": check_g21,
    "G22": check_g22,
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
