#!/usr/bin/env python3
"""
gate_definitions.py — Gate 积木定义 + Profile + 自评分（单一引擎）

仓库内唯一的 Gate 定义源（G1, G6–G29, G30, G31，共 27）。第二套引擎（gate_checker.py 等）已删除（归档于父仓库 git 历史）。
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

from capstone_panorama import panorama as _cap_panorama  # noqa: E402
from capstone_panorama import QUAL_KW as _CAP_QUAL_KW  # noqa: E402
from capstone_panorama import QUANT_KW as _CAP_QUANT_KW  # noqa: E402

# ============================================================
# Gate 定义
# ============================================================

GATE_DESCS = {
    "G1": "信号矩阵完整性（≥8行×3列：短/中/长）",
    "G6": "季报连续性（≥6个连续季度数据）",
    "G7": "扣非对比（净利润/扣非/差额%三列已展示）",
    "G8": "现金流三件套（CFO/CFI/CFF/FCF/FCF净利润比）",
    "G9": "利润归因闭合（ΔNetProfit四项分解闭合）",
    "G10": "事件扫描完成（高优8类+低优10类，每类有状态标记）",
    "G11": "数据时效性声明（报告开头声明数据截止时间；表格仅在数据来源不同时标注日期）",
    "G12": "局限性披露（≥3条具体局限）",
    "G13": "持仓↔决策一致（若用户提供持仓信息，操作建议应考虑持仓语境）",
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
    "G30": "综合研判完整性（证据全景全维+反方诚实+概率闭合+情景-动作一致）",
    "G31": "估值数据有效性（quote.peTtm/pbRatio/totalMarketCap 覆盖率≥2/3；负值计'有数据'）",
}

GATE_WEIGHTS = {
    "G1": 2,
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
    "G30": 4,  # 综合研判完整性（capstone 硬关卡，weight≥3 → FAIL 阻塞输出）
    "G31": 1,  # 估值数据有效性（Soft，单独不阻塞；覆盖率<2/3 仅扣 gate_pass 分）
}

# 综合研判 capstone = G30；活跃 gate = G1, G6–G29, G30, G31（共 27）
ALL_GATES = ["G1"] + [f"G{i}" for i in range(6, 30)] + ["G30", "G31"]

# ============================================================
# Gate 分层 (PR 10: Tier 1 Hard = Python-enforced, Tier 2 Soft = LLM self-assessment)
# ============================================================

# Tier 1: Hard Gates — 数据完整性, Python 可验证, FAIL 阻塞输出
HARD_GATES = ["G6", "G7", "G8", "G9", "G11", "G16", "G21", "G23", "G24", "G25", "G26", "G30"]

# Tier 2: Soft Gates — 内容质量, 仅 LLM 可评估, 正则只能检查格式
# 这些 Gate 在 profile_full 中 auto_pass (不阻塞输出), LLM 在 Phase 4 自评 1-5 分
SOFT_GATES = ["G1", "G10", "G12", "G13", "G14", "G15", "G17", "G18", "G19", "G20", "G22", "G27", "G28", "G29", "G31"]

# ============================================================
# Gate Profiles（与 m11-gates.md Layer 2 严格对齐）
# ============================================================

PROFILES = {
    "profile_full": {
        "name": "full",
        "description": "深度分析/整体分析/买不买/估值 → 全部 27 Gate 实跑",
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
        "gates": ["G1", "G30", "G11", "G13"],
        "auto_pass": ["G6", "G7", "G8", "G9", "G10", "G12",
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
    # 优先：从 snapshot 检查收入数据（需要≥2期）。读路径范式：data 优先 + data_full 兜底
    # （三表因源不同填不同键：THS/EM 主路径只填 .data，Sina 只填 .data_full；单读 data_full → 永不命中）。
    inc = _snapshot_get(data, "s1_financial.data.income_statement")
    rows = inc.get("data", inc.get("data_full", [])) if isinstance(inc, dict) else []
    if isinstance(rows, list) and len(rows) >= 2:
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
    """G13: 持仓↔决策一致（若用户提供持仓信息，操作建议应考虑持仓语境）"""
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
    """G29: 资产安全完整性 + 危险 surface（computed_metrics.asset_safety）。

    双层校验：
    (1) 完整性：snapshot 有 asset_safety(status=ok) → 报告必须消费关键数值/比率；
        snapshot 缺失(status=degraded) → 报告可跳过但不许编造具体数值。
    (2) 实质：level==🚨（cash_to_debt<0.5 / goodwill 占比超阈值）→ 报告必须 surface 危险词，
        否则 FAIL（补商誉爆雷/资金链断裂的机器兜底——全代码库唯一）。
    五路径：🚨+surface=PASS；🚨+未surface=FAIL；有数据漏写字段=FAIL；degraded+编造数值=FAIL；
    degraded+不编造=PASS；其余=PASS。weight 2, SOFT, auto_pass（quick 模式跳过）。
    """
    am = _snapshot_get(data, "computed_metrics.asset_safety")
    has_data = isinstance(am, dict) and am.get("status") == "ok"
    level = am.get("level") if isinstance(am, dict) else None

    if has_data:
        if level == "🚨":
            # 实质：危险判定已下沉，报告必须 surface 危险词（任一即满足；危险词天然覆盖资金链/商誉两端）
            if not re.search(r"(🚨|危险|紧张|风险|爆雷|减值|资金链)", report):
                return False
        else:
            # 消费：非危险档，报告须提具体字段词（去掉漏判词 资产负债率/资产负债结构，商誉占比?→商誉）
            if not re.search(r"(货币资金|有息负债|商誉|cash_to_debt)", report):
                return False

    # 无数据不许编造具体数值（拓宽正则：为|约|达|： + 数字+亿）
    if not has_data and re.search(r"(货币资金|有息负债)\s*(?:为|约|达|[：:])\s*[\d.]+\s*亿", report):
        return False
    return True


# ============================================================
# G30 综合研判 capstone（lucky-petting-rabbit.md C/D）
# 设计哲学：LLM 负责权衡+裁决；结构只强制【完整+诚实】，绝不替 LLM 算答案。
# #1–6 硬检查；#7 软一致性提示下沉为 capstone_panorama 写作期建议（engine 无 warning 通道）。
# 证据全景维度/关键词以 capstone_panorama 为单一真相源（_cap_panorama / _CAP_*_KW）。
# 章节定位锚定结构（行首情景标签+概率），不锚裸词——防散文污染（情景词出现在非情景上下文）。
# ============================================================

_G30_CAPSTONE_HEAD_RE = re.compile(r"^#{1,4}\s.*(?:综合研判|情景|三档|概率|研判)", re.MULTILINE)
# 行首情景标签 + %（防"主情景(基准)概率40%"/"基准偏乐观"等散文污染）
_G30_SCENARIO_HEADER_RE = re.compile(
    r"^[ \t]*[#*|\-]*[ \t]*(乐观|基准|中性|悲观)[^%\n]{0,15}?(\d+(?:\.\d+)?)\s*%",
    re.MULTILINE)
# 表格行回退（Layer3 矩阵：| 乐观 | ... |，概率取行内首个 %）
_G30_SCENARIO_TABLE_RE = re.compile(r"^[ \t]*\|\s*(乐观|基准|中性|悲观)\s*\|[^\n]*", re.MULTILINE)
# 反方证据标记（#2 诚实硬要求）—— 覆盖真实研报常见表述
_G30_COUNTER_MARKERS = ["须克服", "反方", "相反", "利空", "不利", "风险", "然而", "但是",
                        "尽管", "不过", "隐患", "压制", "拖累", "担忧", "脆弱", "质疑",
                        "逆风", "承压", "挑战", "压力", "不足", "偏弱", "受限", "掣肘"]
_G30_ACTION_VERBS = ["加仓", "增持", "买入", "建仓", "减仓", "减持", "卖出", "清仓",
                     "止损", "止盈", "持有", "观望", "不操作", "波段", "趋势持有", "空仓"]
_G30_HOLD_VERBS = ["持有", "观望", "不操作", "波段", "趋势持有"]
_G30_BEARISH_VERBS = ["减仓", "减持", "卖出", "清仓", "止损", "空仓"]
_G30_BULLISH_VERBS = ["加仓", "增持", "买入", "建仓"]
_G30_CONDITION_MARKERS = ["成立条件", "前提", "若", "触发", "假设", "一旦", "假如", "条件", "需满足"]


def _g30_find_capstone(report: str) -> str:
    """定位综合研判章节：从匹配标题到下一个同级/更高级标题/分隔符。找不到回退全文。"""
    m = _G30_CAPSTONE_HEAD_RE.search(report)
    if not m:
        return report
    start = m.start()
    head_match = re.match(r"^(#+)", report[m.start():m.end()])
    head_level = len(head_match.group(1)) if head_match else 4
    rest = report[m.end():]
    stop = len(rest)
    for hm in re.finditer(r"^(#{1,4})\s+\S", rest, re.MULTILINE):
        if len(hm.group(1)) <= head_level:
            stop = hm.start()
            break
    dm = re.search(r"\n---\s*\n", rest[:stop])
    if dm:
        stop = min(stop, dm.start())
    return report[start:m.end() + stop]


def _g30_next_section_end(capstone: str, start: int) -> int:
    """从 start 找下一个同级/更高级标题或硬分隔作为块尾（情景块不被后续章节污染）。"""
    rest = capstone[start:]
    m = re.search(r"\n#{1,4}\s|\n---\s*\n", rest)
    return start + m.start() if m else len(capstone)


def _g30_find_scenarios(capstone: str) -> list:
    """结构化情景声明 → [(label, prob, block_text), ...]。优先行首情景标签，回退表格行。"""
    hdrs = list(_G30_SCENARIO_HEADER_RE.finditer(capstone))
    out = []
    for i, m in enumerate(hdrs):
        start = m.start()
        end = hdrs[i + 1].start() if i + 1 < len(hdrs) else _g30_next_section_end(capstone, start)
        out.append((m.group(1), float(m.group(2)), capstone[start:end]))
    if out:
        return out
    for m in _G30_SCENARIO_TABLE_RE.finditer(capstone):
        pm = re.search(r"(\d+(?:\.\d+)?)\s*%", m.group(0))
        prob = float(pm.group(1)) if pm else 0.0
        out.append((m.group(1), prob, m.group(0)))
    return out


def _g30_split_scenarios(capstone: str) -> list:
    return [(lbl, blk) for lbl, _, blk in _g30_find_scenarios(capstone)]


def _g30_scenario_probs(capstone: str) -> list:
    return [p for _, p, _ in _g30_find_scenarios(capstone)]


def _g30_theme_covered(text: str, kws: list) -> bool:
    return any(k in text for k in kws)


def _g30_first_action(scope: str):
    """按文本位置取首个动作动词（非按列表序）——修"持有/逢低加仓"误取加仓。"""
    found = [(scope.index(v), v) for v in _G30_ACTION_VERBS if v in scope]
    return min(found)[1] if found else None


def _g30_parse_matrix_table(capstone: str):
    """情景矩阵表 → (rows, col_idx)；否则 None。列感知：标签在表头、内容在单元格。"""
    lines = [l for l in capstone.splitlines() if l.strip().startswith("|")]
    if len(lines) < 4:  # 表头 + 分隔 + ≥3 数据行
        return None

    def cells(l):
        return [c.strip() for c in l.strip().strip("|").split("|")]

    header = cells(lines[0])
    col_idx = {}
    for i, h in enumerate(header):
        if any(k in h for k in ["情景", "方案"]) and "scenario" not in col_idx:
            col_idx["scenario"] = i
        elif any(k in h for k in ["成立条件", "前提"]) and "condition" not in col_idx:
            col_idx["condition"] = i
        elif "概率" in h and "prob" not in col_idx:
            col_idx["prob"] = i
        elif any(k in h for k in ["目标价", "价位"]) and "price" not in col_idx:
            col_idx["price"] = i
        elif any(k in h for k in ["应对", "动作", "操作"]) and "action" not in col_idx:
            col_idx["action"] = i
        elif any(k in h for k in ["反方", "风险", "须克服", "对立", "反驳", "利空", "隐忧", "逆风"]) and "counter" not in col_idx:
            col_idx["counter"] = i
    if "scenario" not in col_idx:
        col_idx["scenario"] = 0

    rows = []
    for l in lines[2:]:  # 跳表头 + |---| 分隔行
        c = cells(l)
        if not c or all(not x for x in c):
            continue
        si = col_idx["scenario"]
        label = c[si] if si < len(c) else c[0]
        lab = next((x for x in ("乐观", "基准", "中性", "悲观") if x in label), None)
        if not lab:
            continue
        row = {"_label": lab}
        for key, i in col_idx.items():
            if key == "scenario":
                continue
            row[key] = c[i].strip() if i < len(c) else ""
        rows.append(row)
    return (rows, col_idx) if len(rows) >= 3 else None


def _g30_panorama_section(capstone: str) -> str:
    """#1 覆盖判定范围：'证据全景'小节；找不到回退全文。
    限定到该小节，避免情景块里'cash_to_debt'等顺带提及被误判为'已全景覆盖'。"""
    m = re.search(r"^#{1,4}\s.*(?:证据全景|证据盘点|全景)", capstone, re.MULTILINE)
    if not m:
        return capstone
    rest = capstone[m.end():]
    nxt = re.search(r"^#{1,4}\s", rest, re.MULTILINE)
    return capstone[m.start():m.end() + (nxt.start() if nxt else len(rest))]


def _g30_action_class(v):
    if v in _G30_BULLISH_VERBS:
        return "bull"
    if v in _G30_BEARISH_VERBS:
        return "bear"
    if v in _G30_HOLD_VERBS:
        return "hold"
    return None


def _g30_extract_main_rec_action(capstone: str):
    """从'投资建议/主推荐'行首句抽动作（隔离'评级 买入(N家)'等噪声）。"""
    for line in capstone.splitlines():
        if re.search(r"投资建议|主推荐|综合建议|操作建议|结论", line):
            a = _g30_first_action(line.split("。")[0])
            if a:
                return a
    return None


def _g30_extract_top_scenario_action(capstone: str):
    """最高概率情景的应对动作（主情景=最高概率情景）。表格从 action 列；散文从'应对'句。"""
    tbl = _g30_parse_matrix_table(capstone)
    scens = _g30_find_scenarios(capstone)
    if not scens:
        return None
    top_label = max(scens, key=lambda x: x[1])[0]
    if tbl:
        rows, col_idx = tbl
        if "action" in col_idx:
            for r in rows:
                if r["_label"] == top_label and r.get("action"):
                    return _g30_first_action(r["action"]) or None
        return None
    top = next((b for lbl, _, b in scens if lbl == top_label), None)
    if not top:
        return None
    m = re.search(r"应对[:：][^。]*", top)
    return _g30_first_action(m.group(0) if m else top)


def _g30_run(report: str, data: dict) -> dict:
    """G30 内核：#1–6 硬检查，富返回 {passed, failed, reasons}。check_g30 取 passed(bool)。"""
    failed = []
    reasons = []
    pan = _cap_panorama(data)
    cap = _g30_find_capstone(report)

    # ---- #1 完整性（反片面核心）—— 覆盖判定限定在'证据全景'小节 ----
    cov = _g30_panorama_section(cap)
    miss_quant = [t for t in pan["present_quant"]
                  if not _g30_theme_covered(cov, _CAP_QUANT_KW[t])]
    miss_qual = [t for t in pan["qual_required"]
                 if not _g30_theme_covered(cov, _CAP_QUAL_KW[t])]
    if miss_quant or miss_qual:
        failed.append(1)
        parts = []
        if miss_quant:
            parts.append(f"有数据未纳入(真片面): {miss_quant}")
        if miss_qual:
            parts.append(f"定性主题未覆盖: {miss_qual}")
        reasons.append("#1 完整性 FAIL — " + "; ".join(parts)
                       + (f"  [已豁免 gap 维度: {pan['gap_quant']}]" if pan["gap_quant"] else ""))

    # ---- #2 诚实性（每情景须列反方证据）----
    tbl = _g30_parse_matrix_table(cap)
    blocks = _g30_split_scenarios(cap)
    if tbl:  # 表格：列感知（查 counter 列存在 + 单元格非空）
        rows_t, col_idx_t = tbl
        if "counter" not in col_idx_t:
            failed.append(2)
            reasons.append("#2 诚实性 FAIL — 矩阵表缺'反方证据/风险'列")
        else:
            lacking = [r["_label"] for r in rows_t if not r.get("counter", "").strip()]
            if lacking:
                failed.append(2)
                reasons.append(f"#2 诚实性 FAIL — 反方证据列单元格为空: {lacking}")
    else:  # 散文：每情景块须含反方标记词
        if len(blocks) < 3:
            failed.append(2)
            reasons.append(f"#2 诚实性 FAIL — 情景块不足 3 个（{len(blocks)}），无法逐情景校验")
        else:
            lacking = [lbl for lbl, blk in blocks
                       if not any(m in blk for m in _G30_COUNTER_MARKERS)]
            if lacking:
                failed.append(2)
                reasons.append(f"#2 诚实性 FAIL — 以下情景缺'须克服的反方证据': {lacking}")

    # ---- #3 概率闭合（结构化情景概率，非 section 前 3 个 %）----
    probs = _g30_scenario_probs(cap)
    if len(probs) < 3:
        failed.append(3)
        reasons.append(f"#3 概率闭合 FAIL — 概率数不足 3 个（{probs}）")
    else:
        total = sum(probs[:3])
        if not (99 <= total <= 101):
            failed.append(3)
            reasons.append(f"#3 概率闭合 FAIL — 前 3 概率和={total}（{probs[:3]}），不在 99–101")

    # ---- #4 矩阵结构（每情景: 目标价+动作+成立条件; capstone≥2 证据引用）----
    struct_fail = []
    field_name = {"price": "目标价", "action": "应对动作", "condition": "成立条件"}
    if tbl:
        rows_t, col_idx_t = tbl
        for r in rows_t:
            miss = [field_name[k] for k in ("price", "action", "condition")
                    if k not in col_idx_t or not r.get(k, "").strip()]
            if miss:
                struct_fail.append(f"{r['_label']}缺({'+'.join(miss)})")
    else:
        if len(blocks) < 3:
            struct_fail.append("情景块不足3")
        else:
            for lbl, blk in blocks:
                has_price = bool(re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块|万亿|亿|千万|%|倍)", blk))
                has_action = any(v in blk for v in _G30_ACTION_VERBS)
                has_cond = any(c in blk for c in _G30_CONDITION_MARKERS)
                miss = []
                if not has_price:
                    miss.append("目标价/数值")
                if not has_action:
                    miss.append("应对动作")
                if not has_cond:
                    miss.append("成立条件")
                if miss:
                    struct_fail.append(f"{lbl}缺({'+'.join(miss)})")
    refs = len(re.findall(r"\[src:", cap)) + len(
        re.findall(r"见\s*模块|见\s*m\d|前述|上述|如前所述|参见", cap))
    if refs < 2:
        struct_fail.append(f"证据引用不足2(仅{refs})")
    if struct_fail:
        failed.append(4)
        reasons.append("#4 矩阵结构 FAIL — " + "; ".join(struct_fail))

    # ---- #5 主情景(最高概率情景)动作 = 报告主推荐（动作分类须一致）----
    main_action = _g30_extract_main_rec_action(cap)
    top_action = _g30_extract_top_scenario_action(cap)
    mc, tc = _g30_action_class(main_action), _g30_action_class(top_action)
    if mc and tc and mc != tc:
        failed.append(5)
        reasons.append(f"#5 主情景一致 FAIL — 主推荐='{main_action}'({mc}) 与 "
                       f"最高概率情景='{top_action}'({tc}) 动作分类不一致")

    # ---- #6 信号矛盾 → 主推荐动作 = 持有/观望类 ----
    if re.search(r"信号.{0,4}(矛盾|冲突)|(矛盾|冲突).{0,4}信号", cap) or "信号矛盾" in cap:
        if mc != "hold":
            failed.append(6)
            reasons.append(f"#6 矛盾观望 FAIL — 报告称信号矛盾，但主推荐='{main_action}'({mc})"
                           f" 非'持有/观望'类")

    return {"passed": len(failed) == 0, "failed": failed, "reasons": reasons}


def check_g30(report: str, data: dict) -> bool:
    """G30: 综合研判 capstone 完整性+诚实性。
    #1–6 硬检查（完整/诚实/概率闭合/矩阵结构/主情景一致/矛盾观望）。
    #7 软一致性提示由 capstone_panorama 写作期给出，不计入 verdict。
    返回 bool（engine verify_gates 以 `if ok:` 判定——返回非空 dict 会被当 truthy 永远 PASS）。"""
    return _g30_run(report, data)["passed"]


def check_g31(report: str, data: dict) -> bool:
    """G31: 估值数据有效性（valuation_snapshot.data.quote 关键 L1 字段覆盖率）。

    SOFT gate（weight 1，不在 HARD_GATES / 不进 fail_threshold 硬门）：失败仅拉低 gate_pass 分
    （= self_score 扣分），不阻塞输出。与 P1 runner 层 `_validate_quote` 双闸——runner 在入 snapshot
    前挡脏数据（第一道最有效闸），本 gate 在报告侧复核"数据有没有"，防御 cached/旧 snapshot 绕过自检。

    检查 peTtm/pbRatio/totalMarketCap 三项关键 L1 字段非 None 覆盖率 ≥ 2/3。
    ⚠️ 负值是有效信号非脏数据：亏损股负 PE（pe_is_loss）/破净 PB<1/资不抵债 PB<0 均 `_validate_quote`
       保留原值，故 non-None 即计"有数据"——覆盖率衡量"拉到数据没"，不是"公司盈不盈利"。
    valuation_snapshot 整体缺失或 quote 非 dict → FAIL（数据层硬缺失，非报告问题，但仍扣分提示重拉）。
    """
    quote = _snapshot_get(data, "valuation_snapshot.data.quote")
    if not isinstance(quote, dict):
        return False
    fields = ["peTtm", "pbRatio", "totalMarketCap"]
    present = sum(1 for f in fields if quote.get(f) is not None)
    return present >= 2   # ≥ 2/3


# 注册所有 Gate 验证函数
GATE_CHECKERS = {
    "G1": check_g1, "G6": check_g6, "G7": check_g7, "G8": check_g8,
    "G9": check_g9, "G10": check_g10, "G11": check_g11, "G12": check_g12,
    "G13": check_g13, "G14": check_g14, "G15": check_g15, "G16": check_g16,
    "G17": check_g17, "G18": check_g18, "G19": check_g19, "G20": check_g20,
    "G21": check_g21, "G22": check_g22, "G23": check_g23, "G24": check_g24,
    "G25": check_g25, "G26": check_g26, "G27": check_g27, "G28": check_g28,
    "G29": check_g29, "G30": check_g30, "G31": check_g31,
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
