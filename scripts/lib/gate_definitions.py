#!/usr/bin/env python3
"""
gate_definitions.py — Gate 积木定义 + Profile + 自评分（单一引擎）

仓库内唯一的 Gate 定义源（G1, G6–G29, G30, G31–G61；活跃 gate 数 = len(ALL_GATES)，勿硬编码）。第二套引擎（gate_checker.py 等）已删除（归档于父仓库 git 历史）。
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

from latest_extract import days_old  # noqa: E402  G32/G33 freshness 维度（plan Step 5.5）
from capstone_panorama import panorama as _cap_panorama  # noqa: E402
from capstone_panorama import QUAL_KW as _CAP_QUAL_KW  # noqa: E402
from capstone_panorama import QUANT_KW as _CAP_QUANT_KW  # noqa: E402

# ============================================================
# Gate 定义
# ============================================================

GATE_DESCS = {
    "G1": "技术面完整性（s4_technical 落盘+量价消费；四段：拉取/存放/读取/消费）",
    "G6": "季报连续性（≥6个连续季度数据）",
    "G7": "扣非对比（净利润/扣非/差额%三列已展示）",
    "G8": "现金流三件套（CFO/CFI/CFF/FCF/FCF净利润比）",
    "G9": "利润归因闭合（ΔNetProfit四项分解闭合）",
    "G10": "事件扫描完成（高优8类+低优10类，每类有状态标记）",
    "G11": "数据时效性声明（报告开头声明数据截止时间；表格仅在数据来源不同时标注日期）",
    "G12": "局限性披露（≥3条具体局限）",
    "G13": "持仓↔决策一致（若用户提供持仓信息，操作建议应考虑持仓语境）",
    "G14": "TD序列数据驱动（s4.td 驱动 setup 信号）+ 报告逐根展示",
    "G15": "同业对比（snapshot.s11_peer 核心6计数≥2家齐全+src溯源；金融股豁免毛利率/必PB；missing反编造）",
    "G16": "订单Layer6核对（合同负债核对偏差≤15%；销量/海外收入核对已跳过）",
    "G17": "关税/地缘风险完整（m7 责任；tariff_vulnerability fatal∪partial_* 时须有地缘/关税风险行+估值折让区间）",
    "G18": "竞品对标（已并入 G15；本 gate 恒 PASS 占位，强制力收归 G15）",
    "G19": "营收预测区间（Layer8给区间或标注'无法量化'）",
    "G20": "口径一致（Layer0口径=Layer8输出）",
    "G21": "SOURCE溯源（报告[src:]标记→snapshot路径验证）",
    "G22": "分业务数据完整性（m2§2.2 数据驱动；segment_composition 已披露维须有 [src:segment_composition]+分业务表）",
    "G23": "年报数据完整性（D3-D6覆盖率+segment维度）",
    "G25": "新闻分析流程完整性验证",
    "G26": "资金流向完整性（四档资金分布数据可用+报告已消费）",
    "G27": "财务指标+同比预计算一致性（financial_indicators 最新期有ROE；income 最新期有预计算同比键）",
    "G28": "杜邦数据存在+三因子闭合（dupont.status=ok + 残差<0.25pp；金融股豁免；硬校验）",
    "G29": "资产安全完整性（computed_metrics.asset_safety 可用+报告已消费；缺失不许编造）",
    "G30": "综合研判完整性（证据全景全维+反方诚实+概率闭合+情景-动作一致）",
    "G31": "估值数据有效性（quote.peTtm/pbRatio/totalMarketCap 覆盖率≥2/3；负值计'有数据'）",
    "G32": "龙虎榜信号完整性（lhb.data.processed 存在且 status=ok；真·空 never_listed 仍 PASS）",
    "G33": "北向资金信号完整性（northbound.data.processed 存在且 status=ok；真·非标的 no_northbound_data 仍 PASS）",
    "G34": "分产品维完整性（_quality_markers.segment_product.status 有效态；fetch_failed/degraded=FAIL）",
    "G35": "分行业维完整性（_quality_markers.segment_industry.status 有效态；fetch_failed/degraded=FAIL）",
    "G36": "分地区维完整性（_quality_markers.segment_geo.status 有效态；fetch_failed/degraded=FAIL）",
    "G37": "宏观数据有效性（s_macro PMI/PPI/M2 presence≥2/3；stale-value 误引=FAIL）",
    "G38": "分红有效性（每股股利；有分红历史引旧值=FAIL；不分红真空豁免）",
    "G39": "分类单源执法 report-layer（类型词/估值框架/宏观引用三查；classification 真空豁免）",
    "G40": "技术信号信封消费（m3/m6/m7；signals ok→须含 state 结论词、fibonacci→须渲染、support_resistance→止损禁 xx元空位、degraded→禁编造 DIF 数值）",
    "G41": "筹码成本位消费（m6/m7/m3；chipAvgCost 非空→须含成本位词、cost_pressure=True→须 surface 套牢、无 chip 编造成本=FAIL）",
    "G42": "融资融券杠杆情绪消费（m4/m7；s_margin ok→须含融资余额/两融词、无数据编造具体亿数=FAIL）",
    "G43": "财报披露日历消费（m4；s5_events.disclosure ok→须含披露/财报词、无数据编造具体预计披露日=FAIL）",
    "G44": "ESG 评级治理维度消费（m9.2/m7；s_esg ok→须含 ESG/评级词(不含裸治理)、无数据编造 ESG 评级=FAIL）",
    "G45": "目标价口径溯源（m5；目标价数字须 [src:] 溯源或不确定性标注；websearch vs API-grade 混用无 src=FAIL）",
    "G46": "占位（事件层重建：severity/M-code 体系退役并入大事提醒时间线；致命事件 surface 由 G30#1 timeline.fatal_events 负责；checker 恒 PASS，保留以维持 gate 计数分母）",
    "G47": "股东行为综合研判消费（m9.2/m7；ST3 shareholder_dynamics 融合 意图×内部人×前十大，有材料级方向须 surface 内部人/董监高/前十大/增持/减持/净买/净卖/港资/言行合一；空/中性/failed 豁免；反编造 FAIL）",
    "G48": "待执行/进行中增减持计划消费（m9.2/m7/m1；ST5 programs[] forward 信封，有 planned/ongoing 须 surface 待执行/进行中/拟减持/拟增持/窗口/计划；无活跃/failed 豁免；反编造 FAIL）",
    "G49": "买卖力量 verdict 消费（m9.2/m7/m6/m1/capstone；ST6 buy_sell_pressure 信封，verdict∈{buy_dominant,sell_dominant,balanced} 须 surface 买卖力量/买方/卖方/回购/增持/减持/解禁/质押/平仓；unclear/failed/空 豁免；反编造 FAIL）",
    "G50": "占位（事件层重建：severity 体系退役，时间线用官方 EVENT_TYPE_CODE 分类，无三档 severity 可校验一致性；数字/编造由 G16/G29 兜底；checker 恒 PASS，保留以维持 gate 计数分母）",
    "G51": "m2 §2.13 SGR 全链路（computed_metrics.sgr；ok+适用→须消费+三件套(ROE/派息率/留存率)+进度条+数值对齐；不适用→写不适用禁编值；assumed_no_dividend→⚠️/上限脚注；无 sgr→禁编 SGR 值）",
    "G52": "m3 ATR 波动/破位全链路（s4_technical.data.atr；ok+atr14→须消费+止损/破位段+数值对齐；缺→禁编 ATR 值；never_traded 豁免）",
    "G53": "m3 换手率自身分位全链路（s4_technical.data.turnover.pct_250；高换手↔pct≥70/低换手↔pct≤30 enforcement；报告分位数须==snapshot；never_traded 豁免）",
    "G54": "m3 技术环境+正交信号(ADX/BIAS/OBV)全链路（s4_technical.data.signals.state.adx_state/bias_state/obv_trend；ADX 值须==snapshot technical.dmi.ADX；须有环境判定段；never_traded 豁免）",
    "G55": "m3 golden 结构+边界+VWAP（六维读数≥4维+综合诊断段；禁仓位%/盈亏比/打分→m6；VWAP 值须==snapshot realtime_quote.vwap；never_traded 豁免）",
    "G56": "m1 golden 收敛+边界+反捏造（五块结构齐全；类型词/占主营占比==snapshot；禁 ST5/ST6 独立段量化/新接线标记；资金筹码须≤1句指向 m9/m7）",
    "G57": "m4 growth_tier 消费一致性+反编造（§4.1.1 P4；data growth_tier=high/moderate 须 surface 对应高/中成长词；None 须豁免且禁在业绩语境编造成长强度；company_guidance 缺→None 豁免）",
    "G58": "m5 估值分位必写+反编造（§5.1/§5.3；valuation_percentile pe_ttm/pb/ev_ebitda applicable=true 须 surface 分位[pct×0.01对齐或src]；applicable=false/无数据豁免；无数据却写分位%=FAIL）",
    "G59": "m5 §5.3 估值结论 verdict presence（必含偏贵/偏贱/高估/低估/估值合理/估值适中/估值偏低/估值偏高 判定词；无 §5.3 豁免）",
    "G60": "m6 定性三行结构化锚点+反捏造（Layer1 ⑪护城河/⑫治理战略/⑬前瞻催化 各须含 ≥1 [src:] 锚点或标「无源」；研发强度X%须≈snapshot；裸奔或捏造=FAIL；限证据全景子节防投资建议叙事误伤）",
    "G61": "千股千评结论一等公民完整性（四段闭环仿G1，根治「只拉不用」：①status三态 failed→FAIL禁编造/missing→PASS真空豁免 ②conclusions非空+四键(dimension/text/severity/source_api)+latest_period信封 ③双兜底data/data_full读取 ④每ok结论维度报告须surface词+反编造须[src:]锚；旧snapshot无s_stock_evaluation→PASS向后兼容）",
}

GATE_WEIGHTS = {
    "G1": 2,
    "G6": 2, "G7": 2, "G8": 2, "G9": 2, "G10": 2,
    "G11": 1, "G12": 2, "G13": 2, "G14": 2, "G15": 3,
    "G16": 2, "G17": 3, "G18": 2, "G19": 3,     "G20": 2,
    "G21": 3,  # PR 8: 高权重
    "G22": 3,  # 分业务数据完整性
    "G23": 3,  # 年报数据完整性
    "G25": 2,  # 新闻分析流程完整性
    "G26": 2,  # 资金流向完整性
    "G27": 1,  # 财务指标+同比预计算一致性（Soft，单独不阻塞）
    "G28": 1,  # 杜邦三因子闭合（Soft，单独不阻塞；硬校验失败=真FAIL）
    "G29": 2,  # 资产安全完整性（Soft，单独不阻塞；有数据漏写/无数据编造=FAIL）
    "G30": 4,  # 综合研判完整性（capstone 硬关卡，weight≥3 → FAIL 阻塞输出）
    "G31": 1,  # 估值数据有效性（Soft，单独不阻塞；覆盖率<2/3 仅扣 gate_pass 分）
    "G32": 1,  # 龙虎榜信号完整性（Soft，单独不阻塞；failed/缺失=真FAIL）
    "G33": 1,  # 北向资金信号完整性（Soft，单独不阻塞；failed/缺失=真FAIL）
    "G34": 1,  # 分产品维完整性（Soft；三维对称，fetch_failed/degraded=FAIL）
    "G35": 1,  # 分行业维完整性（Soft；三维对称，fetch_failed/degraded=FAIL）
    "G36": 1,  # 分地区维完整性（Soft；三维对称，fetch_failed/degraded=FAIL）
    "G37": 1,  # 宏观数据有效性 PMI/PPI/M2（Soft；presence<2/3 或 PMI stale-value=FAIL）
    "G38": 1,  # 分红有效性 每股股利（Soft；有分红历史且引旧值=FAIL；不分红真空豁免）
    "G39": 1,  # 分类单源执法 report-layer（Soft；类型词/估值框架/宏观引用三查；classification 真空豁免）
    "G40": 1,  # 技术信号信封消费（Soft；signals ok→须含 state 词、fib→须渲染、support_resistance→止损禁 xx元空位、degraded→禁编造 DIF）
    "G41": 1,  # 筹码成本位消费（Soft；chipAvgCost 非空→须含成本位词、cost_pressure→须 surface 套牢、无 chip 编造成本=FAIL）
    "G42": 1,  # 融资融券杠杆情绪消费（Soft；s_margin ok→须含两融词、无数据编造亿数=FAIL）
    "G43": 1,  # 财报披露日历消费（Soft；disclosure ok→须含披露词、无数据编造日期=FAIL）
    "G44": 1,  # ESG 评级治理维度消费（Soft；s_esg ok→须含 ESG 词、无数据编造评级=FAIL）
    "G45": 1,  # 目标价口径溯源（Soft；目标价数字须 src 或不确定性标注；websearch vs API-grade 混用=FAIL）
    "G46": 2,  # 占位（Soft；severity/M-code 退役，恒 PASS，保留 gate 计数分母）
    "G47": 1,  # 股东行为综合研判消费（Soft；ST3 shareholder_dynamics 有方向须 surface presence 词）
    "G48": 1,  # 待执行/进行中增减持计划消费（Soft；ST5 programs[] 有 active 须 surface presence 词）
    "G49": 1,  # 买卖力量 verdict 消费（Soft；ST6 buy_sell_pressure 有 verdict 须 surface 阵营词）
    "G50": 1,  # 占位（Soft；severity 退役，恒 PASS，保留 gate 计数分母）
    "G51": 2,  # m2 §2.13 SGR 全链路（Soft；ok→须消费+数值对齐，不适用→禁编值，assumed→⚠️上限脚注）
    "G52": 2,  # m3 ATR 波动/破位全链路（Soft；ok→须消费+止损段+数值对齐，缺→禁编值）
    "G53": 2,  # m3 换手率自身分位（Soft；自身分位法 enforcement+反捏造分位数）
    "G54": 2,  # m3 技术环境正交信号 ADX/BIAS/OBV（Soft；ADX 数值对齐+环境段）
    "G55": 2,  # m3 golden 结构+边界+VWAP（Soft；六维读数+诊断段+禁打分/仓位+VWAP 对齐）
    "G56": 2,  # m1 golden 收敛+边界+反捏造（Soft；五块结构+类型词/占比对齐+禁 ST5/ST6 量化越界）
    "G57": 1,  # m4 growth_tier 消费一致性+反编造（Soft；growth_tier=high/moderate 须 surface；None 豁免+禁编造；info/利好不 HARD 强制）
    "G58": 1,  # m5 估值分位必写+反编造（Soft；applicable 分位须 surface+对齐；无数据禁编造）
    "G59": 1,  # m5 §5.3 估值结论 verdict presence（Soft；必含贵贱判定词）
    "G60": 1,  # m6 定性三行结构化锚点+反捏造（Soft；⑪⑫⑬ 各须 [src:] 锚点或标无源；研发强度对齐）
    "G61": 1,  # 千股千评结论一等公民完整性（Soft；四段闭环仿G1，根治只拉不用；每ok结论维度强制surface+反编造）
}

# 综合研判 capstone = G30；活跃 gate = G1, G6–G29（不含G24）, G30, G31–G61
ALL_GATES = ["G1"] + [f"G{i}" for i in range(6, 30) if i != 24] + ["G30", "G31", "G32", "G33", "G34", "G35", "G36", "G37", "G38", "G39", "G40", "G41", "G42", "G43", "G44", "G45", "G46", "G47", "G48", "G49", "G50", "G51", "G52", "G53", "G54", "G55", "G56", "G57", "G58", "G59", "G60", "G61"]

# ============================================================
# Gate 分层 (PR 10: Tier 1 Hard = Python-enforced, Tier 2 Soft = LLM self-assessment)
# ============================================================

# Tier 1: Hard Gates — 数据完整性, Python 可验证, FAIL 阻塞输出
HARD_GATES = ["G6", "G7", "G8", "G9", "G11", "G16", "G21", "G22", "G23", "G25", "G26", "G30"]

# Tier 2: Soft Gates — 内容质量, 仅 LLM 可评估, 正则只能检查格式
# 这些 Gate 在 profile_full 中 auto_pass (不阻塞输出), LLM 在 Phase 4 自评 1-5 分
SOFT_GATES = ["G1", "G10", "G12", "G13", "G14", "G15", "G17", "G18", "G19", "G20", "G27", "G28", "G29", "G31", "G32", "G33", "G34", "G35", "G36", "G37", "G38", "G39", "G40", "G41", "G42", "G43", "G44", "G45", "G46", "G47", "G48", "G49", "G50", "G51", "G52", "G53", "G54", "G55", "G56", "G57", "G58", "G59", "G60", "G61"]

# ============================================================
# Gate Profiles（与 m11-gates.md Layer 2 严格对齐）
# ============================================================

PROFILES = {
    "profile_full": {
        "name": "full",
        "description": "深度分析/整体分析/买不买/估值 → 全部活跃 Gate 实跑（= ALL_GATES，见本文件；勿硬编码计数）",
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
    """G1: 技术面完整性（四段：拉取/存放/读取/消费，仿 G26/G29；2026-07 重构）。

    覆盖拉取→存放→读取→消费全流程（用户钦定，根治 603663 换手率漏消费）：
    ① 拉取：s4_technical.status（ok/failed/never_traded）+ realtime_quote._turnover_status
    ② 存放：s4.data.technical 或 s4.data.td 非空（真落盘，非 stub）
    ③ 读取：_snapshot_get 双兜底（内置保证）
    ④ 消费：报告含技术词任一；tq=ok 须含"换手/量比/成交额"（量价消费）
    三态放行（仿 G28）：never_traded → 结构性 PASS；failed → FAIL（禁编造）。
    向后兼容：旧 snapshot 无 s4 键 → 退化原信号矩阵检查（保 fixture 漏报=0）。
    """
    s4 = _snapshot_get(data, "s4_technical")
    if not isinstance(s4, dict) or not s4:
        return _g1_legacy(report)

    status = s4.get("status", "")
    signal_type = s4.get("signal_type", "")
    # 三态放行：never_traded（北交/港股/指标全None）→ 结构性 PASS（禁编造：见下）
    if status == "never_traded" or signal_type == "never_traded":
        # 禁编造：never_traded 却报告出现具体技术数值 → FAIL（数据不可得不应有数值）
        return not _has_specific_tech_numbers(report)
    # fetch_failed → FAIL（禁编造：failed 却报告出现具体技术数值同样 FAIL）
    if status == "failed" or signal_type == "fetch_failed":
        return False

    # ② 存放：technical 或 td 非空（数据真落盘）
    s4_data = s4.get("data", {}) or {}
    if not (s4_data.get("technical") or s4_data.get("td")):
        return False

    # ④ 消费：技术词任一
    tech_words = ["MACD", "KDJ", "RSI", "均线", "金叉", "死叉", "多头", "空头",
                  "TD", "布林", "BOLL", "MA5", "MA20", "量价"]
    if not any(w in report for w in tech_words):
        return False

    # ④ 量价消费：tq=ok 须含换手/量比/成交额（603663 漏消费根因修复）
    tq = _snapshot_get(data, "s2_quote_kline.data.realtime_quote") or {}
    tq_status = tq.get("_turnover_status", "ok")  # 旧 snapshot 无此键默认 ok
    if tq_status == "ok":
        if not any(w in report for w in ("换手", "量比", "成交额")):
            return False
    return True


def _g1_legacy(report: str) -> bool:
    """旧 snapshot（无 s4_technical）退化：原信号矩阵行数检查，保 fixture 漏报=0。"""
    if "信号" not in report and "矩阵" not in report:
        return False
    if not (_has_keywords(report, ["短", "中", "长"]) or _has_keywords(report, ["短期", "中期", "长期"])):
        return False
    matrix_rows = _count_pattern(report, r'[│|].*[│|].*[│|]')      # 表格行
    table_rows = _count_pattern(report, r'^\s*\|.*\|.*\|')         # markdown 表格行
    return matrix_rows >= 8 or table_rows >= 8


def _has_specific_tech_numbers(report: str) -> bool:
    """检测报告是否含具体技术指标数值（MACD/KDJ/RSI/MA + 数字）。

    用于 never_traded 禁编造判定：数据结构性不可得时，报告不应出现具体指标数值。
    仅匹配「指标名+数字」组合，避免「RSI 超买」等定性词误判。
    """
    patterns = [
        r'(?:MACD|DIF|DEA)\s*[：:=\-]?\s*-?\d',
        r'(?:KDJ|RSI|CCI|WR|VR)\s*[：:=\-]?\s*-?\d',
        r'MA[_\s]?\d+\s*[：:=\-]?\s*-?\d',
    ]
    return any(re.search(p, report) for p in patterns)


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
    # 双兜底 data/data_full（CLAUDE.md 硬规则：THS/EM 填 .data、Sina 填 .data_full；
    # 单读任一键 = 静默 never-match。镜像 G8 cf_section 范式）。
    fa_section = _snapshot_get(data, "s1_financial.data.financial_abstract")
    fa = fa_section.get("data", fa_section.get("data_full", [])) if isinstance(fa_section, dict) else None
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
    """G10: 事件扫描完成（已退役，恒 PASS 占位）。事件完整性 surface 已由 G30#1
    timeline.fatal_events + present_signals 接管（数据驱动读 s5_events.processed.timeline）；
    内容质量密度（quant/src/detail 计数）属报告作者 LLM 责任（同 G1/G8/G9，不在 gate 层强制）。
    保留注册以维持 gate 计数分母（mirror check_g46/check_g50）。"""
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
    """G14: TD 序列数据驱动 + 报告逐根展示（仿 G26；2026-07 重构）。

    ① 拉取+存放：s4.td 已固化（td_analyzer 从 s2 close 算，零网络，覆盖 setup/countdown/tdst）
    ② 消费：报告含 TD；有信号（summary.stage≠无信号）→ 须有计数/Setup/Countdown 展示
    三态放行（仿 G28）：never_traded → PASS。
    向后兼容：旧 snapshot 无 s4.td → 退化原检查（TD + ≥9 计数行）。
    """
    s4 = _snapshot_get(data, "s4_technical")
    if isinstance(s4, dict) and (s4.get("status") == "never_traded"
                                  or s4.get("signal_type") == "never_traded"):
        return True
    td = _snapshot_get(data, "s4_technical.data.td")
    if not isinstance(td, dict) or "summary" not in td:
        return _g14_legacy(report)

    # 消费：报告须含 TD
    if "TD" not in report:
        return False
    stage = (td.get("summary", {}) or {}).get("stage", "")
    # 有信号（stage≠无信号，如"买Setup N/9"/"Countdown M/13"/"TD13完成"）→ 须有计数展示
    if stage and stage != "无信号":
        return _count_pattern(report, r'(?:TD|计数|Setup|Countdown|序列)\s*\d+') >= 1
    # 无信号 → 提及 TD 即可（标注"无 TD 信号"等）
    return True


def _g14_legacy(report: str) -> bool:
    """旧 snapshot（无 s4.td）退化：TD + ≥9 计数行，保 fixture 漏报=0。"""
    if "TD" not in report:
        return False
    return _count_pattern(report, r'(?:TD|计数|Setup)\s*\d+') >= 9


# G15 核心 6 字段（gate 计数对象 = API 层真实数据，非正文词频）。
# 金融股豁免 gross_margin（真无营业成本，数据现实——非假设；check_g15 动态裁为 5）。
_G15_CORE_FIELDS = ("rev_yoy", "np_yoy", "pe", "pb", "roe", "gross_margin")


def check_g15(report: str, data: dict) -> bool:
    """G15: 同业对比（核心 6 计数 + src 溯源 + stock_type 适配 + 三态 + 反编造）。SOFT(weight 2)。

    v3 数据层重设计（F3 端到端；根治旧"正文 ≥4 指标词"橡皮章——只验词出现，不验数据真/是
    API/是 peer）。计数对象 = snapshot.s11_peer.items[].metrics 核心 6（东财 F10 5 维度 + sina 毛利率补全）：
      1. 三态：status∈{ok,degraded} 且 ≥2 家 peer 核心 6 齐全（金融股 5）→ 进入溯源检查；
              status==missing（全限流/独家/次新/未拉取）→ 豁免，但反编造（见 4）。
      2. 核心 6 计数：遍历 items 实际长度（不硬编码下标），每 peer metrics 核心 6 non-null。
         <2 家齐全：degraded 宽容 PASS；ok 但 <2 → FAIL。
      3. src 溯源（F3 根因闭环）：报告须带 [src: ...s11_peer] 或同业对比措辞（底线）。
      4. 反编造（仿 G29）：missing 时报告含同业措辞 + peer 财务数字 却无 s11_peer 溯源 → FAIL。
      5. stock_type 适配：金融股豁免 gross_margin（真无营业成本，数据现实），且必校验 PB（金融第一指标）。
    富字段（research_notes/eps/绝对值/资产负债率）消费但不阻断（仿 G26）。
    """
    stock_type = data.get("stock_type", "") or ""
    is_financial = any(kw in stock_type for kw in ("金融", "银行", "保险", "券商"))
    core = [k for k in _G15_CORE_FIELDS if not (is_financial and k == "gross_margin")]

    peer = _snapshot_get(data, "s11_peer.data") or {}
    status = peer.get("status")
    items = peer.get("items") or []

    def _has_core(metrics):
        return isinstance(metrics, dict) and all(metrics.get(k) is not None for k in core)

    # 1+4. missing（未拉取/全限流/独家/次新）→ 豁免；F2 溯源链 + 反编造
    if status not in ("ok", "degraded") or not items:
        # 完整性矛盾：status=ok 却无 items（声明有数据实际没有）
        if status == "ok" and not items:
            return False
        discovered_codes = peer.get("discovered_peer_codes")
        # L0（600584 bug 根治）：占位 missing 且无 discovered_peer_codes 键（→ None）=
        # 从未跑（em 恒回填此键；None 是防御性 never-run 信号）。须诚实披露「无适用同业」
        # （独家/垄断/次新/无可比/行业唯一），否则 = 零数据假 PASS → FAIL。
        # None（占位无键）与 []/非空 list（跑了）严格可区分：runner.fetch_peer_comparison_em 总回填此键。
        if discovered_codes is None:
            disclosed = any(kw in report for kw in (
                "无适用同业", "无可比", "独家", "垄断", "次新", "无同业",
                "尚无可比", "行业唯一", "无可比标的"))
            return bool(disclosed)
        has_peer_phrasing = any(kw in report for kw in ("同业", "可比公司", "对比", "竞品", "同行", "对标"))
        has_peer_number = bool(re.search(r"(毛利率|PE|PB|ROE)\s*[:：]\s*[\d.]+", report))
        # F2: 回填了 discovered_peer_codes 却仍 missing/空 items → 拉取失败/全限流；
        #     须诚实披露限流（限流/不可得/失败/缺失），否则 FAIL（根治「空 stub 假 PASS」）
        if discovered_codes:
            honest = any(kw in report for kw in ("限流", "不可得", "未能获取", "拉取失败", "数据缺失", "未获取"))
            if not honest:
                return False
        # F2: 删旧 "s11_peer" not in report 逃生口——无 peer 数据时报告同业措辞+peer 财务数字 = 编造
        #     （即使有 discovered_codes 限流披露，也不能编造具体 peer 财务数字）
        if has_peer_phrasing and has_peer_number:
            return False
        return True

    # 2. 核心 6 计数（遍历 items 实际长度）
    valid = [it for it in items if _has_core(it.get("metrics", {}))]
    if len(valid) < 2:
        return status == "degraded"   # degraded(部分缺)宽容 PASS；ok 但 <2 家齐全 → FAIL

    # 3. src 溯源：报告须带 s11_peer 溯源（首选）或同业对比措辞（底线）
    if "s11_peer" not in report and not any(
        kw in report for kw in ("同业", "可比", "对比", "同行", "竞品", "对标")
    ):
        return False

    # 5. stock_type 适配：金融股必校验 PB（金融第一指标）
    if is_financial and "PB" not in report:
        return False

    return True


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
      c. 合同负债行带 [src: snapshot/websearch] 溯源 → 计为 grounded（精确值交 G21）
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
            continue  # 该行已溯源，精确值交给 G21，不在此判冲突
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


# ============================================================
# 共享 freshness helper（plan Step 5.1）—— G37/G38/G30#1 数值对齐公共地基
# 复刻 G16 多精度范式，泛化为任意 latest_period 字段。纯函数，gate 运行时层 fixtures
# 不在时由 test_freshness_helper.py 单测兜底（户数 128685 vs 10.12万 bug case 必含）。
# ============================================================

def _extract_latest_value(data: dict, envelope_path: str, value_key=None):
    """从 latest_period 信封取标量 value（G37/G38/G30#1 共用）。

    envelope_path: 指向含 ``latest_period`` 的 dict（如 ``s8_a_share.data.shareholder_count``、
      ``valuation_snapshot.data.quote``（dividend 兄弟键 dividend_latest_period））。
    value_key: None→latest_period.value 须为标量（close/holder_count）；str→从 value(dict) 取子键
      （如 balance_sheet 的 "合同负债"、macro 的 "制造业-指数"）。

    返回 float 或 None。真空（latest_period None/缺失/value None/非数值）→ None（gate 走豁免）。
    """
    env = _snapshot_get(data, envelope_path)
    if not isinstance(env, dict):
        return None
    # dividend 用兄弟键 dividend_latest_period（dividend_history 保持 list 不破坏 m5 消费）：
    # quote 本身无 latest_period，但内含 dividend_latest_period 信封。
    lp = env.get("latest_period")
    if not isinstance(lp, dict) and envelope_path.endswith(".quote"):
        sib = env.get("dividend_latest_period")
        if isinstance(sib, dict):
            lp = sib   # 兄弟键本身就是信封（{raw_date, value, ...}）
    if not isinstance(lp, dict):
        return None
    val = lp.get("value")
    if value_key is not None and isinstance(val, dict):
        val = val.get(value_key)
    try:
        if val is None:
            return None
        f = float(val)
        return f if f == f else None   # NaN→None
    except (TypeError, ValueError):
        return None


def _check_value_freshness(report: str, snap_value, metric_kws,
                           scales=(1.0, 1e4, 1e8), tol=0.15):
    """报告是否 grounded snap_value（plan Step 5.1，复刻 G16 多精度数值对齐）。

    判定逻辑（找含任一 metric_kw 的行）：
      - 行带 ``[src:]`` 溯源 → grounded（精确值交 G21，不在此判冲突）
      - 行内数值 × ``scales`` 多精度换算（report"12.87万"→12.87×1e4=128700 ≈ snap 128685），
        任一与 snap 偏差 ≤ tol → grounded
      - 所有相关行均不 grounded → 报告未消费或用了 stale 值 → 返回 False

    ``scales`` = 报告数值可能所处的单位乘数（1=原值/1e4=万/1e8=亿），×report_num 对齐 snap 单位。
    snap_value=None → True（真空豁免）；metric_kws 无匹配行 → False（有数据但报告未提该字段）。
    """
    if snap_value is None:
        return True   # 真空豁免
    try:
        snap = float(snap_value)
    except (TypeError, ValueError):
        return True
    if snap != snap or snap == 0:   # NaN 或 0（难判对齐，仅认 src）
        snap = None

    rel_lines = [ln for ln in report.split('\n') if any(kw in ln for kw in metric_kws)]
    if not rel_lines:
        return False   # 有数据但报告完全没提该字段

    for ln in rel_lines:
        if '[src:' in ln:
            return True   # 该行已溯源 → grounded
        if snap is None:
            continue
        # 剥千分位逗号（"128,685"→"128685"），再抽数值
        for m in re.finditer(r'\d[\d,]*\.?\d*', ln):
            try:
                rv = float(m.group(0).replace(",", ""))
            except ValueError:
                continue
            if rv <= 0:
                continue
            for sc in scales:
                scaled = rv * sc   # 报告值×单位乘数（"12.87"万→128700）
                if scaled <= 0:
                    continue
                if max(scaled, snap) / min(scaled, snap) <= (1 + tol):
                    return True   # 偏差≤tol → grounded
    return False


def check_g17(report: str, data: dict) -> bool:
    """G17: 关税/地缘风险完整（m7 责任；tariff_vulnerability fatal∪partial* 触发）。SOFT（weight 3）。

    F3 升级（海外毛利率判别，2026-07-23）：level 集扩展为
      fatal / partial_low_margin_export / partial_mixed / partial_unverified → 须有 m7 §7.1
      地缘/关税风险行（关税/地缘/制裁/贸易摩擦/双反/出口管制/实体清单/倾销 任一）
      AND §7.1.1 估值折让（-% 区间[兼容全角－/～] 或 折让/折价/估值传导 词）。
      none（domestic_only/underivable_*）→ 放行。partial_unverified 与 fatal 对称要求
      （诚实：声称「有待核实风险」仍须列风险行+折让，禁只说"待核实"敷衍）。
    校验对象 = m7（§7.1 风险行 + §7.1.1 折让）。
    """
    cm = data.get("computed_metrics") or {}
    tv = cm.get("tariff_vulnerability") or {}
    lvl = str(tv.get("level") or "")
    if not (lvl == "fatal" or lvl.startswith("partial")):
        return True  # none / 空 → 放行（无脆弱性不强制关税分析）
    # m7 §7.1 地缘/关税风险行（关键词底线）
    risk_kws = ("关税", "地缘", "制裁", "贸易摩擦", "双反", "出口管制", "实体清单", "倾销")
    has_risk_row = any(kw in report for kw in risk_kws)
    # m7 §7.1.1 估值折让区间（负百分比区间[兼容全角－/～] 或 折让/折价/估值传导 词）
    has_haircut = bool(re.search(r'[－-]?\s*\d+\s*[%％]\s*[~～\-–—至到]\s*[－-]?\s*\d+\s*[%％]', report)) \
                  or "折让" in report or "折价" in report or "估值传导" in report
    return has_risk_row and has_haircut


def check_g18(report: str, data: dict) -> bool:
    """G18: 竞品对标（已并入 G15，本 checker 保留为占位以维持 gate 计数）。

    v3 合并：G18 原"≥3 家可比公司"机械计数（公司名形态多变不可靠）已被 G15 核心 6 计数
    （snapshot.s11_peer.items[].metrics 真实 API 数据）取代。同业对比措辞底线亦由 G15
    src 溯源分支覆盖。故 G18 不再独立强制——恒 PASS，强制力全部收归 G15（详见 G15 docstring）。
    删除原因见 financial-data-routing/REFACTOR_LOG.md。GATE_REGISTRY 保留条目维持 self_score 分母。
    """
    return True


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
    3. 模块级检测：m5（估值模块）须 >=2 个 verified [src:] 标记（F-G3 实现 docstring 承诺）。
       仿 G56 m1 段定位：定位「模块五」段，计 snapshot./bare-scene src（路径已验证）<2→FAIL；
       无 m5 段不执法（report-only / 非估值报告）。
    """
    snapshot = data
    snapshot_pattern = r'\[src:\s*snapshot\.([^\]]+)\]'
    websearch_pattern = r'\[src:\s*websearch\s+([^\]]+)\]'
    # 容错：无 snapshot. 前缀但匹配合法 scene 命名的 [src:]（旧文档/作者笔误），计入不报错
    bare_scene_pattern = r'\[src:\s*((?:s\d+_\w+|valuation_\w+|consensus_forecast|computed_metrics|s36_\w+|s55_\w+|web_research_findings)\.[^\]]+)\]'

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

    # F-G3: m5（估值模块）verified [src:] 计数（实现 docstring 承诺）。
    # 定位「模块五」段，计 snapshot./bare-scene src（上述已通过路径验证，非 None），<2→FAIL。
    m5m = re.search(r'^#{1,4}\s.*模块五', report, re.MULTILINE)
    if m5m:
        _rest = report[m5m.end():]
        _nxt = re.search(r'^#{1,4}\s', _rest, re.MULTILINE)
        _m5sec = _rest[:(_nxt.start() if _nxt else len(_rest))]
        _m5_verified = re.findall(r'\[src:\s*snapshot\.[^\]]+\]', _m5sec) + \
                       re.findall(r'\[src:\s*(?:s\d+_\w+|valuation_\w+|consensus_forecast|computed_metrics|s36_\w+|s55_\w+|web_research_findings)\.[^\]]+\]', _m5sec)
        if len(_m5_verified) < 2:
            return False   # m5 段 verified src 不足 2 个（橡皮章估值，无数据锚点）

    return True


def check_g22(report: str, data: dict) -> bool:
    """G22: 分业务数据完整性（m2 §2.2 数据驱动；防橡皮章脑补分业务表）。HARD（weight 3）。

    Phase 3 升级（从纯 grep 关键词 → 读 segment_composition，对齐 m2 §2.2 数据驱动）：
      - product/industry 任一维 disclosed_ok → 报告须含 (分业务/分产品/分行业/主营构成 表)
        AND [src: ...segment_composition...] 溯源（证明用真数据非脑补）。
      - 全部 not_disclosed/stale/fetch_failed（如招行无行业维）→ 放行（不强制脑补，防空公司误伤）。
    """
    seg = ((((data.get("s1_financial") or {}).get("data")) or {}).get("segment_composition")) or {}
    dim_status = seg.get("dimension_status") or {}
    product_ok = (dim_status.get("product") or {}).get("status") == "disclosed_ok"
    industry_ok = (dim_status.get("industry") or {}).get("status") == "disclosed_ok"
    if not (product_ok or industry_ok):
        return True  # 无 disclosed 维度 → 不要求分业务表（招行无行业即此态）
    has_segment = any(kw in report for kw in ["分业务", "分产品", "分行业", "业务分拆", "主营构成"])
    has_src = "segment_composition" in report   # [src: snapshot.s1_financial.data.segment_composition.{product,industry}]
    return has_segment and has_src


def check_g23(report: str, data: dict) -> bool:
    """G23: 年报数据完整性。(c) _critical_failure 管道硬止损 → (a) {D3,D4,D5=segment_product,D6=segment_geo} 达阈值 → (b) segment 维度不全 fetch_failed。"""
    # (c) 管道硬止损（优先判）：snapshot 自标 _critical_failure（finalize 判核心场景 s1_financial/s2_quote_kline/s5_events ≥2 全失败）→ FAIL
    if data.get("_critical_failure"):
        return False

    quality = data.get("_quality_markers", {})

    def _ok(m):
        # 词表统一：D3/D4 标 ok/partial，segment marker 标 disclosed_ok
        return (m or {}).get("status") in ("ok", "partial", "disclosed_ok")

    # segment 维度状态（segment_composition 的维度级判定）
    seg = ((((data.get("s1_financial") or {}).get("data")) or {}).get("segment_composition")) or {}
    dim_status = seg.get("dimension_status") or {}
    prod_ok = (dim_status.get("product") or {}).get("status") == "disclosed_ok"
    ind_ok = (dim_status.get("industry") or {}).get("status") == "disclosed_ok"

    # (a) {D3, D4, D5=segment_product, D6=segment_geo} 成功数达阈值
    #     金融股无分业务（product+industry 均非 disclosed_ok）→ 阈值降级，镜像 G22
    dims = [
        quality.get("D3_dividend", {}),
        quality.get("D4_holders", {}),
        quality.get("segment_product", {}),   # D5：分产品收入构成
        quality.get("segment_geo", {}),        # D6：分地区收入构成
    ]
    ok_count = sum(1 for m in dims if _ok(m))
    threshold = 3 if (prod_ok or ind_ok) else 2
    if ok_count < threshold:
        return False

    # (b) segment dimension_status.{product,industry,geo} 不全 fetch_failed，镜像 G22 路径
    statuses = [(dim_status.get(d) or {}).get("status") for d in ("product", "industry", "geo")]
    if statuses and all(s == "fetch_failed" for s in statuses):
        return False

    # governance 实控人 presence（软：status==ok 且有实控人 → 报告须消费；failed/never_empty 豁免）
    gov = data.get("governance") or {}
    if gov.get("status") == "ok" and gov.get("real_controler"):
        if not any(k in report for k in ("实控人", "实际控制人", "控股股东", "控制人")):
            return False

    return True


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
    ② income_statement 最新期行含至少一个 *_同比% 键且非 None；
    ③ mainfinadata（东财 MAINFINADATA 指标层）status==ok 且最新期含资产负债率(ZCFZL)/流动(LD)/速动(SD)比率之一非 None；
       never_empty（真无指标，极少）放行，failed（限流/网络）判 FAIL。
    金融股天然豁免：不校验总资产周转率（数据语义 N/A），ROE/BVPS/EPS 金融股全有，ZCFZL 必有。
    """
    fi = _snapshot_get(data, "s1_financial.data.financial_indicators")
    # 双兜底 data/data_full（CLAUDE.md 硬规则：THS/EM 填 .data、Sina 填 .data_full；
    # 单读 data_full → 主路径 fi_rows=None → ROE 检查恒 false-fail）。
    fi_rows = fi.get("data", fi.get("data_full")) if isinstance(fi, dict) else None

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
    if not any(latest.get(k) is not None for k in latest if str(k).endswith("_同比%")):
        return False

    # ③ mainfinadata 指标层（东财 MAINFINADATA）：status==ok 且最新期有偿债能力指标
    mf = _snapshot_get(data, "s1_financial.data.mainfinadata")
    if not isinstance(mf, dict):
        return False
    mf_status = mf.get("status")
    if mf_status == "failed":
        return False
    if mf_status == "ok":
        mf_rows = mf.get("data") or []
        latest_mf = mf_rows[0] if isinstance(mf_rows, list) and mf_rows else {}
        if not any(latest_mf.get(k) not in (None, "", "nan") for k in ("ZCFZL", "LD", "SD")):
            return False
    # never_empty（真无指标，极少）→ 放行
    return True


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
# 行首散文情景标签 + %（Layer2 每情景标题：### 乐观 42% / **乐观** 45%）。
# 字符类 [#*\-] 故意不含 |——表格行 | 乐观 | 交 _G30_SCENARIO_TABLE_RE，避免与本正则
# 职责混淆（否则裸 label 表格行被本正则误匹配，与 TABLE_RE 加粗 label 口径冲突，
# find_scenarios 在混合 label 表格里漏识别→#3 假 FAIL；2026-07-19 宁德实测配套修，与 TABLE_RE 同步）。
_G30_SCENARIO_HEADER_RE = re.compile(
    r"^[ \t]*[#*\-]*[ \t]*(乐观|基准|中性|悲观)[^%\n]{0,15}?(\d+(?:\.\d+)?)\s*%",
    re.MULTILINE)
# 表格行回退（Layer3 矩阵：| 乐观 | ... |，概率取行内首个 %）
# label 两侧容忍 markdown 强调符(**/*/`)——向 _g30_parse_matrix_table(cells+in)口径对齐。
# 否则 | **中性** | 这种正常加粗会让 find_scenarios→_g30_scenario_probs 漏识别→#3 概率闭合 FAIL，
# 而同 gate 的 #2/#4(走 parse_matrix，用 in) 却 PASS，口径自相矛盾（2026-07-19 修，宁德时代实测暴露）。
_G30_SCENARIO_TABLE_RE = re.compile(r"^[ \t]*\|\s*[*`]*\s*(乐观|基准|中性|悲观)[^|]*\|[^\n]*", re.MULTILINE)
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
# 前瞻事件时间维度标记词（Fix I）：timeline.future/active 非空 → 报告时间线段须含其一，禁单表混排未来与历史
_G30_FWD_MARKERS = ("未来", "前瞻", "预计", "将至", "待执行", "进行中", "计划", "窗口", "拟", "即将", "将要")


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


def _module_section(report, head_pattern, *, full_report_fallback=True):
    """统一 level-aware markdown 章节切片器（克隆 _g30_find_capstone 算法·根治 ^#{1,4}\\s 截断 bug）。
    head_pattern: 编译正则或裸 pattern 串（按 re.MULTILINE）。返回 (found, body)。
    body 含标题行到下一同级/更高级标题或 '\\n---\\n'（不截断 #### 子标题）。未找到 → (False, report 或 '')。"""
    pat = head_pattern if hasattr(head_pattern, "search") else re.compile(head_pattern, re.MULTILINE)
    m = pat.search(report)
    if not m:
        return (False, report if full_report_fallback else "")
    start = m.start()
    hm = re.match(r"^(#+)", report[m.start():m.end()])
    head_level = len(hm.group(1)) if hm else 4
    rest = report[m.end():]
    stop = len(rest)
    for h in re.finditer(r"^(#{1,4})\s+\S", rest, re.MULTILINE):
        if len(h.group(1)) <= head_level:
            stop = h.start()
            break
    dm = re.search(r"\n---\s*\n", rest[:stop])
    if dm:
        stop = min(stop, dm.start())
    return (True, report[start:m.end() + stop])


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


def _g30_group_tables(capstone: str):
    """连续 | 行 = 一张表；非 | 行分隔。返回 [[lines], ...]。"""
    tables, cur = [], []
    for l in capstone.splitlines():
        if l.strip().startswith("|"):
            cur.append(l)
        elif cur:
            tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    return tables


def _g30_parse_block(tbl):
    """单张情景矩阵表 → (rows, col_idx)；否则 None。列映射+行提取（表内逻辑）。"""
    if len(tbl) < 4:  # 表头 + 分隔 + ≥3 数据行
        return None

    def cells(l):
        return [c.strip() for c in l.strip().strip("|").split("|")]

    header = cells(tbl[0])
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
    for l in tbl[2:]:  # 跳表头 + |---| 分隔行
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


def _g30_parse_matrix_table(capstone: str):
    """情景矩阵表 → (rows, col_idx)；否则 None。

    多表共存时（全景表/财务表在前）按**表头签名选表**，不再无条件取 lines[0]
    （旧实现致列映射全错→#2/#4 假 FAIL）。表内列映射/行提取逻辑见 _g30_parse_block。
      pass1: 表头同时含「情景/方案」+「应对/动作/操作」的块（最精确）；
      pass2: 兜底——数据行 col0 含 ≥2 个{乐观,基准,中性,悲观}的块（无应对列的情景表）。
    """
    tables = _g30_group_tables(capstone)
    # pass1: 表头签名（情景 + 应对）
    for tbl in tables:
        if len(tbl) < 4:
            continue
        header = [c.strip() for c in tbl[0].strip().strip("|").split("|")]
        has_scen = any(any(k in h for k in ["情景", "方案"]) for h in header)
        has_act = any(any(k in h for k in ["应对", "动作", "操作"]) for h in header)
        if has_scen and has_act:
            r = _g30_parse_block(tbl)
            if r:
                return r
    # pass2: 兜底（数据行 col0 ≥2 情景词）
    for tbl in tables:
        scens = set()
        for l in tbl[2:]:
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if c:
                for x in ("乐观", "基准", "中性", "悲观"):
                    if x in c[0]:
                        scens.add(x)
        if len(scens) >= 2:
            r = _g30_parse_block(tbl)
            if r:
                return r
    return None


def _g30_panorama_section(capstone: str) -> str:
    """#1 覆盖判定范围：'证据全景'小节；找不到回退全文。
    限定到该小节，避免情景块里'cash_to_debt'等顺带提及被误判为'已全景覆盖'。"""
    return _module_section(capstone, r"^#{1,4}\s.*(?:证据全景|证据盘点|全景)")[1]


def _g30_announcement_registry_section(report: str) -> str:
    """v3：m4 §4.1.1「重大事件与公告一览/公告重要性一览/重要公告/公告登记」小节文本；找不到返回 ''。

    锚定该小节（照 _g30_panorama_section 模式）——避 capstone 误切，且防散文/capstone
    顺带提及「减持」冒充登记表条目（登记表须是有结构的小节）。扫全 report（m4 在 capstone 外）。"""
    return _module_section(report, r"^#{1,4}\s.*(?:公告重要性|重要公告一览|公告一览|公告登记表|重要公告清单|大事提醒|重大事件|重要事项|时间线)", full_report_fallback=False)[1]


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
        if re.search(r"投资建议|主推荐|综合主建议|主建议|综合建议|操作建议|结论", line):
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


# #1 数值新鲜度字段注册（plan Step 5.2 G30#1 升级）。
# 只校验「报告提及该字段词但值 stale/未 grounded」——catches 户数 stale-value bug；
# 不提及 ≠ FAIL（覆盖遗漏另由 miss_quant 管；户数非每份报告必提，强提会误伤）。
# close：报告引用最频繁的数字，stale 风险高（引旧收盘价）；daily_kline latest_period.value=收盘价标量。
_G30_VALUE_FIELDS = [
    ("股东户数", "s8_a_share.data.shareholder_count", ["股东户数", "户数"]),
    ("现价/收盘价", "s2_quote_kline.data.daily_kline", ["现价", "收盘价", "最新价"]),
]


def _g30_value_freshness_findings(data: dict, cov: str):
    """#1 数值新鲜度：报告提及某字段词但 latest_period 值未 grounded → 记 finding。

    复用 _check_value_freshness（多精度 + [src:] 豁免 + 真空豁免）。
    户数 stale-value bug 兜底：snapshot=128685 vs 报告"10.12万"→ 记 finding → #1 FAIL。
    """
    def _fmt(x):
        return f"{x:,.0f}" if x == int(x) else f"{x:,.2f}"   # 户数"128,685" / close"54.07"
    findings = []
    for label, path, kws in _G30_VALUE_FIELDS:
        v = _extract_latest_value(data, path)
        if v is None:
            continue                       # 真空（snapshot 无 latest_period）→ 豁免
        if not any(kw in cov for kw in kws):
            continue                       # 报告未提及该字段 → 非 stale-value（覆盖遗漏另管）
        if not _check_value_freshness(cov, v, kws):
            findings.append(f"{label} stale/未对齐(snapshot={_fmt(v)})")
    return findings


def _g30_signal_coverage_findings(data: dict, cov: str) -> list:
    """#1 信号覆盖：遍历 panorama.present_signals（源自大事提醒 timeline 风险码关键词），
    对每个信号断言证据全景含其**精确词**（拒 K线/换手冒充）。

    三态：timeline 无风险事件 → present_signals 空 → 豁免（真空票不误伤）；
    有信号但证据全景缺精确词 → FAIL（漏 surface 严重风险）。利好不进
    present_signals 强制列 → 门禁分级（漏报利好不致命，不 FAIL）。"""
    pan = _cap_panorama(data)
    findings = []
    for s in (pan.get("present_signals") or []):
        if not _g30_theme_covered(cov, s.get("kws") or []):
            findings.append(f"严重信号 {s.get('code')}({s.get('name')}) 未 surface"
                            f"（证据全景须含 {'/'.join((s.get('kws') or [])[:2])}，技术词不算）")
    findings += _signal_pipeline_consistency_findings(data)
    return findings


def _signal_pipeline_consistency_findings(data: dict) -> list:
    """raw∩processed 防御纵深（独立于管道自觉）：大事提醒 remind 有记录 → processed.timeline
    必须产 events；raw 有 remind 但 timeline 空 → 管道断裂。抓引擎 bug，防静默漏码。"""
    out = []
    rs = _snapshot_get(data, "s5_events.data.risk_signals") or {}
    if not isinstance(rs, dict):
        return out
    remind = rs.get("remind_records") or []
    tl = (rs.get("processed") or {}).get("timeline") or {}
    if (remind and isinstance(tl, dict) and tl.get("status") != "failed"
            and not (tl.get("events") or tl.get("future"))):
        out.append("事件管道断裂：remind 有大事提醒记录但 processed.timeline 无 events")
    return out


def _g30_announcement_registry_findings(data: dict, report: str) -> list:
    """#1 致命事件 surface（HARD）+ 前瞻事件时间维度标记（Fix I, HARD）。

    三态（mirror 信号覆盖）：
    - 无 fatal_events / 无 future+active → 豁免（真空票不误伤）；
    - processed.status==failed → 豁免（拉取失败非漏报）；
    - 有 fatal 但时间线小节缺失 / 缺该事件 → FAIL（漏 surface 致命风险，计入 fail_threshold）；
    - 有 future/active 前瞻事件但时间线段无时态标记词 → FAIL（扁平表混排未来与历史，误导读者）。
    surface 词：event_type 首段 + LV1 关键词（ST/*ST/退市/破产/重整/审计/违规/立案/处罚/保留意见/无法表示）。
    """
    rs = _snapshot_get(data, "s5_events.data.risk_signals") or {}
    proc = rs.get("processed") if isinstance(rs, dict) else None
    if not isinstance(proc, dict) or proc.get("status") == "failed":
        return []
    tl = proc.get("timeline") or {}
    if not isinstance(tl, dict) or tl.get("status") == "failed":
        return []
    reg = _g30_announcement_registry_section(report)
    findings = []
    # Fix I：前瞻事件（future/active）须标时间维度，禁单表混排未来与历史
    fwd_ev = (tl.get("future") or []) + (tl.get("active") or [])
    if fwd_ev:
        scope = reg if reg else report
        if not any(mk in scope for mk in _G30_FWD_MARKERS):
            findings.append(f"前瞻事件({len(fwd_ev)}条)未标时间维度（须 未来/前瞻/预计/待执行/进行中/计划 等；禁单表混排未来与历史）")
    fatal_ev = tl.get("fatal_events") or []
    if not fatal_ev:
        return findings                 # 无致命事件 → 真空豁免（保留前瞻 finding 若有）
    if not reg:
        findings.append(f"大事提醒时间线小节缺失（m4 §4.1.1 须渲染 {len(fatal_ev)} 条致命事件）")
        return findings
    for e in fatal_ev:
        if not isinstance(e, dict):
            continue
        et = (e.get("event_type") or "").strip()
        lv1 = e.get("level1_content") or ""
        kws = []
        if et:
            kws.append(et.replace("/", "、").split("、")[0].strip())
        for w in ("ST", "*ST", "退市", "破产", "重整", "审计", "违规", "立案", "处罚",
                  "保留意见", "无法表示"):
            if w in lv1 and w not in kws:
                kws.append(w)
        kws = [k for k in kws if len(k) >= 2]
        if not kws:
            continue
        if not any(k in reg for k in kws):
            findings.append(f"致命事件 {e.get('event_type_code')}({et}) 未在时间线 surface")
    return findings


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

    # ---- #1 数值新鲜度（plan Step 5.2 升级，反 stale-value）----
    # 报告提及户数词但 latest_period 值未 grounded（多精度/src 豁免）→ #1 FAIL。
    # catches 户数 stale-value bug（128685 vs 报告 10.12万）。
    vf_findings = _g30_value_freshness_findings(data, cov)
    if vf_findings:
        failed.append(1)
        reasons.append("#1 数值新鲜度 FAIL — " + "; ".join(vf_findings))

    # ---- #1 信号覆盖（capstone present_signals，源自大事提醒 timeline）----
    # present_signals 数据驱动（真空票豁免）；精确词校验（K线/换手不冒充）；timeline 派生的风险信号须在证据全景 surface。
    # 防御纵深：_signal_pipeline_consistency_findings 抓 remind 有记录但 timeline 无 events 的管道断裂。
    sig_findings = _g30_signal_coverage_findings(data, cov)
    if sig_findings:
        failed.append(1)
        reasons.append("#1 信号覆盖 FAIL — " + "; ".join(sig_findings))

    # ---- #1 致命事件 surface（HARD）：timeline.fatal_events 须在 m4 §4.1.1 大事提醒时间线 surface ----
    # 数据驱动（无 fatal_events→真空豁免；processed.status==failed→豁免）；锚定 m4 §4.1.1 大事提醒时间线小节。
    # surface 词：event_type 首段 + LV1 关键词（ST/*ST/退市/破产/重整/审计/违规/立案/处罚）。
    reg_findings = _g30_announcement_registry_findings(data, report)
    if reg_findings:
        failed.append(1)
        reasons.append("#1 致命事件 surface FAIL — " + "; ".join(reg_findings))

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


def check_g30(report: str, data: dict):
    """G30: 综合研判 capstone 完整性+诚实性。
    #1–6 硬检查（完整/诚实/概率闭合/矩阵结构/主情景一致/矛盾观望）。
    #7 软一致性提示由 capstone_panorama 写作期给出，不计入 verdict。
    返回富结构 {passed, failed, reasons}——verify_gates 引擎识别 dict 返回并上浮 reasons
    到 sidecar detail/action_required（让报告作者看到具体 FAIL 项，如「股东户数 stale/未对齐」，
    否则只看到泛化 desc 不知是哪个值 stale）。其他返 bool 的 gate 不受影响（引擎兼容 bool 与 dict）。"""
    return _g30_run(report, data)


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


def check_g32(report: str, data: dict) -> bool:
    """G32: 龙虎榜信号完整性（processed 存在且 status=ok）。SOFT（weight 1，单独不阻塞）。

    区分「真·无数据」与「拉取失败」——gate 职责是前者 PASS、后者 FAIL，不检查「数据非零」：
    - 真·从不上榜 → `processed.status="ok"`, `signal_type="never_listed"` → **PASS**（有效信号）
    - 拉取失败（东财限流+同花顺全挂） → `processed.status="failed"` 或 processed 缺失 → **FAIL**
    消费（报告是否提及）由 G30 #1 覆盖检查负责，本 gate 只校验数据层完整性。
    返回 bool 或富结构 {passed, reasons}（engine 识别 dict 取 passed）。
    plan Step 5.5 freshness 维度：真空(never_listed)→PASS；非真空但 latest_period.sort_key
    距今>90d（fetch_lhb 90 天窗）→ SOFT warning（passed=True 不阻塞，reason 上浮让 m6/m7
    不据此调仓位）；近期→PASS。
    """
    p = _snapshot_get(data, "lhb.data.processed")
    if not isinstance(p, dict) or p.get("status") != "ok":
        return False  # 拉取失败（processed 缺失 / status≠ok）
    lp = p.get("latest_period")
    if not isinstance(lp, dict) or lp.get("sort_key") is None:
        return True  # 真空（never_listed，90天未上榜）PASS
    d_old = days_old(lp.get("sort_key"), lp.get("as_of"))
    if d_old is not None and d_old > 90:
        return {"passed": True,
                "reasons": [f"龙虎榜最近上榜 {d_old} 天前·历史数据非近期，m6/m7 不得据此调仓位（SOFT warning）"]}
    return True  # 近期活跃 PASS


def check_g33(report: str, data: dict) -> bool:
    """G33: 北向资金信号完整性（processed 存在且 status=ok）。SOFT（weight 1，单独不阻塞）。

    区分「真·非北向标的」与「拉取失败」：
    - 真·非北向标的 → `processed.status="ok"`, `signal_type="no_northbound_data"` → **PASS**（有效信号）
    - 拉取失败（westock 异常+TOP10 全空） → `processed.status="failed"` 或 processed 缺失 → **FAIL**
    区分靠 Layer 1 `_process_northbound_signals`（not_in_pool 空表 vs WestockError），gate 事后校验。
    plan Step 5.5 freshness 维度：真空(no_northbound_data)→PASS；非真空但 latest_period.sort_key
    距今>180d → SOFT warning（passed=True，reason 上浮）；近期→PASS。（2026-08-09 统一 180d 口径，原 120）
    """
    p = _snapshot_get(data, "northbound.data.processed")
    if not isinstance(p, dict) or p.get("status") != "ok":
        return False  # 拉取失败
    lp = p.get("latest_period")
    if not isinstance(lp, dict) or lp.get("sort_key") is None:
        return True  # 真空（no_northbound_data）PASS
    d_old = days_old(lp.get("sort_key"), lp.get("as_of"))
    if d_old is not None and d_old > 180:
        return {"passed": True,
                "reasons": [f"北向持仓最近披露 {d_old} 天前·历史数据，仅作参考（SOFT warning）"]}
    return True  # 近期 PASS


def _check_segment_dim(data: dict, dim: str) -> bool:
    """三维对称 SOFT gate 共用：校验 _quality_markers.segment_<dim> 数据完整性（5 态）。

    镜像 G32/G33「真空 vs 失败」范式（逐字相同，硬对称）：
      - disclosed_ok / not_disclosed / stale_disclosure / partial → PASS
        （有效状态：真披露 / 真·空 / 历史停披 / 行数过少——均非失败）
      - fetch_failed / degraded / marker 缺失 → FAIL（拉取失败 / 脏数据 / 数据层未产 marker）
    消费（报告是否渲染）由 G30 #1 / G22 覆盖，本 gate 只校验数据层完整性。
    """
    quality = data.get("_quality_markers", {})
    marker = quality.get(f"segment_{dim}") or {}
    status = marker.get("status")
    return status in ("disclosed_ok", "not_disclosed", "stale_disclosure", "partial")


def check_g34(report: str, data: dict) -> bool:
    """G34: 分产品维完整性（_quality_markers.segment_product.status 有效态）。SOFT（weight 1）。"""
    return _check_segment_dim(data, "product")


def check_g35(report: str, data: dict) -> bool:
    """G35: 分行业维完整性（_quality_markers.segment_industry.status 有效态）。SOFT（weight 1）。"""
    return _check_segment_dim(data, "industry")


def check_g36(report: str, data: dict) -> bool:
    """G36: 分地区维完整性（_quality_markers.segment_geo.status 有效态）。SOFT（weight 1）。"""
    return _check_segment_dim(data, "geo")


# G37 宏观三字段（PMI/PPI/M2）。实测三字段均**不适合数值新鲜度校验**：
#   - PPI/M2 报告多引「同比%」派生指标（akshare 另列 `当月同比增长`/`-同比增长`，非
#     latest_period.value 的指数/绝对量），强数值校验必误判；
#   - PMI 报告虽直引指数，但窄带波动（49–52），stale vs fresh 值偏差常 <5% 落 tol 内，
#     靠数值判不了 stale（50.3 当月 vs 50.1 上月数值无法区分）。
# 故 G37 = presence 覆盖（镜像 G31）——宏观是市场级数据、同日全量刷新，presence 即新鲜度。
# stale 宏观值靠报告引「月份/季度」标注（m35 已要求），非 gate 数值层职责。
_G37_MACRO_FIELDS = ("pmi", "ppi", "m2")


def check_g37(report: str, data: dict) -> bool:
    """G37: 宏观数据有效性（PMI/PPI/M2 latest_period 覆盖率）。SOFT（weight 1，单独不阻塞）。

    数据层（镜像 G31 覆盖率）：``s6_macro.data.{pmi,ppi,m2}.latest_period.value`` non-None ≥ 2/3。
    宏观是市场级数据（非个股），同日全量刷新；本 gate 兜底 akshare 限流全挂（< 2/3 → FAIL）。
    不做数值新鲜度：PPI/M2 派生口径不一致、PMI 窄带判不了 stale（见上方注册表注释）。
    真空豁免：latest_period=None（fetch_failed）不计 presence；全缺失则覆盖率 0 → FAIL。
    """
    present = 0
    for k in _G37_MACRO_FIELDS:
        lp = _snapshot_get(data, f"s6_macro.data.{k}.latest_period")
        if isinstance(lp, dict) and lp.get("value") is not None:
            present += 1
    return present >= 2


def check_g38(report: str, data: dict) -> bool:
    """G38: 分红有效性（每股股利数值新鲜度）。SOFT（weight 1，单独不阻塞）。

    数据层：``quote.dividend_latest_period`` non-None（有分红历史）。不分红公司（成长股）无
    dividend_latest_period → 真空豁免 PASS（非每公司必分红，与 G31 负值是有效信号同理）。
    消费层：报告提及 分红/派息/每股股利 → 每股股利数值须与最新期对齐（scales 1.0=每股 / 0.1=每10股
    换算到每股）OR [src:] 溯源。"股息率"是派生 % 指标（≠ 每股股利绝对值），不纳入数值口径（用"股息率"
    关键词排除，避免误判）。镜像 G31 覆盖率 + G16 数值对齐范式。
    """
    snap_val = _extract_latest_value(data, "valuation_snapshot.data.quote", "每股股利")
    if snap_val is None:
        return True   # 真空豁免（无分红历史）
    div_kws = ("分红", "派息", "每股股利", "每股派息")   # 不含"股息"（股息率派生%口径不同）
    if any(kw in report for kw in div_kws):
        # 否定=有效「无分红」结论（如「几乎不分红」），非 stale 旧值 → 放行（mirror G31 负值是有效信号）
        if re.search(r"(?:不|无|暂无|未|几乎不|暂未|尚无)\s*(?:分红|派息|派现|股利)", report):
            return True
        # scales: report"0.12元"(每股)×1.0 / "每10股派1.2元"×0.1 → 都对齐 snap 每股股利 0.12
        if not _check_value_freshness(report, snap_val, list(div_kws), scales=(1.0, 0.1)):
            return False
    return True


# G39 分类单源执法（report-layer，读 snapshot.classification 单一真相源）。
# 与 G37（数据层 macro presence）正交：G37 兜 s6_macro fetch 全挂，G39 兜报告口径与反片面。
# 补 m0「周期禁 PE 做主要 / 成长禁 PB 做主要」从未有 gate 执法的真缺口（C6，2026-07-22）。
_G39_TYPE_CORE = {
    "周期股": "周期", "成长股": "成长", "消费股": "消费",
    "金融股": "金融", "防御股": "防御", "多元化控股": "多元化",
}
# valuation_framework 推荐词（forbidden_metric 间接执法：不引推荐框架 ≈ 误用 forbidden 指标做主要）
_G39_FW_KW = {
    "周期股": ("PB", "EV/EBITDA", "EV-EBITDA", "股息率", "市净率"),
    "成长股": ("PS", "PEG", "DCF", "市销率"),
    "金融股": ("PB", "不良率", "ROE", "市净率"),
    "多元化控股": ("NAV", "RNAV", "分部估值"),
}
_G39_FW_KW_MIXED = ("PS", "PEG", "远期PE", "远期市盈率", "市销率")
_G39_MACRO_KW = ("PPI", "M2", "PMI", "CPI", "生产者价格", "货币供应", "采购经理")


def check_g39(report: str, data: dict) -> bool:
    """G39: 分类单源执法（report-layer，读 snapshot.classification）。SOFT（weight 1，单独不阻塞）。

    三查（任一 fail → False），全部基于 classification 单一真相源（C1-C5+C2.5 产物）：
      #1 报告含类型词：primary_type 核心词（周期/成长/消费/金融/防御/多元化）在 report 出现
         （m1 要求开篇"标的属 {primary_type}{is_mixed 则补+secondary}"）。
      #2 估值框架一致（forbidden_metric 执法）：forbidden_metric 非空（周期/成长/金融/混合）时，
         报告须引 valuation_framework 推荐词——间接执法 m0「周期禁 PE / 成长禁 PB 做主要」：
         不引推荐框架 ≈ 用 forbidden 指标做主要估值。消费/防御 forbidden=None → 跳过（无硬禁）。
      #3 反片面宏观引用：macro_sensitivity==high（周期/金融/混合）→ 报告须引 ≥1 宏观（PPI/M2/PMI/CPI）。
         preferred_macro（周期/混合→PPI 优先，金融→M2 优先）是写作用法提示，gate 查 ≥1 即可；
         触发器是稳定的 classification（board 派生），非 flaky s55.momentum。

    真空豁免：classification 缺失 / primary_type=None（数据不可得 LLM 兜底）→ PASS（不强执法）。
    """
    cls = (data or {}).get("classification") or {}
    primary = cls.get("primary_type")
    if not primary:
        return True   # 分类不可得（LLM 兜底），不强执法

    # #1 类型词
    core = _G39_TYPE_CORE.get(primary)
    if core and core not in report:
        return False

    # #2 估值框架（forbidden_metric 间接执法）
    forbidden = cls.get("forbidden_metric")
    if forbidden:
        fw_kws = _G39_FW_KW_MIXED if cls.get("is_mixed") else _G39_FW_KW.get(primary)
        if fw_kws and not any(k in report for k in fw_kws):
            return False

    # #3 反片面宏观引用（macro_sensitivity==high）
    if cls.get("macro_sensitivity") == "high" and not any(k in report for k in _G39_MACRO_KW):
        return False

    return True


def check_g40(report: str, data: dict) -> bool:
    """G40: 技术信号信封消费（m3/m6/m7 责任；s4_technical.data.signals + fibonacci + support_resistance）。
    SOFT(weight1)。三态 mirror G29/G32/G33：ok→须消费；degraded→可跳过不许编造 DIF 数值；
    failed→FAIL；never_traded→PASS。

    校验对象：s4_technical.data.{signals, fibonacci, support_resistance}。
    五路径：
    (1) signals.status==ok → 报告须含 ≥1 state 结论词（金叉/死叉/多头/空头/MACD/KDJ/RSI/布林/多空排列/上中下轨）。
    (2) fibonacci populated → 须含「斐波那契/fib/回撤」（plan 实测 bug：算好却 0 渲染）。
    (3) support_resistance.layers populated + 报告含「止损/支撑/压力」+「xx元」空位 → FAIL（止损必须具体价位）。
    (4) degraded + 报告编造 `DIF ±数字`/`MACD±数字` → FAIL（反编造，mirror G29）。
    (5) never_traded/缺块 → PASS。
    """
    s4 = _snapshot_get(data, "s4_technical") or {}
    s4_data = s4.get("data", {}) if isinstance(s4, dict) else {}
    s4_status = s4.get("status") if isinstance(s4, dict) else None
    # never_traded（北交/港股）→ 结构性豁免
    if s4_status == "never_traded":
        return True

    signals = s4_data.get("signals") if isinstance(s4_data, dict) else None
    sig_ok = isinstance(signals, dict) and signals.get("status") == "ok"
    fib = s4_data.get("fibonacci") if isinstance(s4_data, dict) else None
    fib_ok = isinstance(fib, dict) and bool(fib)
    sr = s4_data.get("support_resistance") if isinstance(s4_data, dict) else None
    sr_layers = (sr.get("layers") if isinstance(sr, dict) else None) or []
    sr_ok = bool(sr_layers)

    # (1) signals ok → 须含 state 结论词
    if sig_ok:
        if not re.search(r"(金叉|死叉|多头|空头|MACD|KDJ|RSI|布林|多空排列|上轨|中轨|下轨|触轨|缩口)", report):
            return False
    # (2) fibonacci populated → 须渲染 fib
    if fib_ok:
        if not re.search(r"(斐波那契|fib|回撤|0\.(236|382|5|618|786))", report):
            return False
    # (3) support_resistance populated + 止损/支撑/压力空位「xx元」→ FAIL（必须具体价位）
    if sr_ok and re.search(r"(止损|支撑|压力)[^\n]{0,10}(xx|XX)[^\n]{0,3}元", report):
        return False
    # (4) degraded + 编造 DIF/MACD 数值 → FAIL
    sig_degraded = isinstance(signals, dict) and signals.get("status") == "degraded"
    if sig_degraded and re.search(r"(DIF|MACD)\s*[+\-]?\s*\d", report):
        return False
    return True


def check_g41(report: str, data: dict) -> bool:
    """G41: 筹码成本位消费（m6/m7/m3 责任；s4_technical.data.chip 升级一等）。SOFT(weight1)。
    三态 mirror G29/G40：chip 齐全(chipAvgCost 非空)→须消费成本位；chip 缺(chipAvgCost None/缺块)→豁免；
    never_traded→PASS。

    校验对象：s4_technical.data.chip（含 latest_period 信封 + cost_pressure/underwater_pct 派生）。
    四路径：
    (1) chipAvgCost 非空 → 报告须含成本位关键词（均成本/成本位/套牢/筹码/chipAvgCost/获利盘/浮盈亏）。
    (2) cost_pressure=True（chipAvgCost>现价）→ 须 surface 套牢/承压/浮亏（成本压力位 = 止损决策输入）。
    (3) 无 chip（旧票/港股）却写具体成本数值 → FAIL（反编造，mirror G29）。
    (4) never_traded / chip 缺块 → PASS。
    """
    s4 = _snapshot_get(data, "s4_technical") or {}
    s4_status = s4.get("status") if isinstance(s4, dict) else None
    if s4_status == "never_traded":
        return True
    s4_data = s4.get("data", {}) if isinstance(s4, dict) else {}
    chip = s4_data.get("chip") if isinstance(s4_data, dict) else None
    has_chip = isinstance(chip, dict)
    avg = chip.get("chipAvgCost") if has_chip else None
    cost_pressure = chip.get("cost_pressure") if has_chip else None

    if has_chip and avg is not None:
        # (1) 须消费成本位关键词（chip 专属，排除 m2 营业成本的裸"成本"）
        if not re.search(r"(均成本|平均成本|成本位|成本压力|套牢|筹码|chipAvgCost|获利盘|浮盈|浮亏|筹码集中)", report):
            return False
        # (2) cost_pressure=True → 须 surface 套牢/承压
        if cost_pressure and not re.search(r"(套牢|承压|浮亏|压力位|阻力)", report):
            return False
    # (3) 反编造：无 chip 却写具体成本数值
    if not has_chip and re.search(r"(均成本|平均成本|成本位|筹码)\s*(?:为|约|达|[：:])\s*[\d.]+\s*元", report):
        return False
    return True


def check_g42(report: str, data: dict) -> bool:
    """G42: 融资融券杠杆情绪消费（m4/m7 责任；s_margin 新 scene）。SOFT(weight1)。
    三态 mirror G40/G41：status=ok（有融资余额数据）→须消费；missing/failed（次新/无两融/拉取失败）→豁免，
    但反编造（无数据却写具体融资余额亿数）→ FAIL。
    """
    mg = _snapshot_get(data, "s_margin") or {}
    mg_data = mg.get("data", {}) if isinstance(mg, dict) else {}
    status = mg_data.get("status") if isinstance(mg_data, dict) else None
    has_value = (mg_data.get("latest_period") or {}).get("value") is not None if isinstance(mg_data, dict) else False

    if status == "ok" and has_value:
        if not re.search(r"(融资余额|融资融券|融券|两融|杠杆|margin|FinanceValue|融资买入)", report):
            return False
    # 反编造：非 ok 却写具体融资余额亿数
    if status != "ok" and re.search(r"融资余额\s*(?:为|约|达|[：:])\s*[\d.]+\s*亿", report):
        return False
    return True


def check_g43(report: str, data: dict) -> bool:
    """G43: 财报披露日历消费（m4 责任；s5_events.data.disclosure 并入）。SOFT(weight1)。
    三态：status=ok（有未来披露日）→须消费；missing/failed（无披露日/拉取失败）→豁免，
    但反编造（无数据却写具体预计披露日期）→ FAIL。
    """
    s5 = _snapshot_get(data, "s5_events") or {}
    s5d = s5.get("data", {}) if isinstance(s5, dict) else {}
    dc = s5d.get("disclosure") if isinstance(s5d, dict) else None
    status = dc.get("status") if isinstance(dc, dict) else None
    has_date = bool(dc.get("disclosure_date")) if isinstance(dc, dict) else False

    if status == "ok" and has_date:
        if not re.search(r"(披露|财报|季报|年报|中报|三季报|预约|disclosure|报告期|中期报告|年度报告)", report):
            return False
    # 反编造：非 ok 却写具体「预计 YYYY-MM-DD 披露」
    if status != "ok" and re.search(r"预计\s*\d{4}[-年]\d{1,2}[-月]?\d{0,2}[日号]?\s*披露", report):
        return False
    return True


def check_g44(report: str, data: dict) -> bool:
    """G44: ESG 评级治理维度消费（m9.2/m7 责任；s_esg 新 scene）。SOFT(weight1)。
    三态：status=ok（有 ESG 评级）→须消费；missing/failed（无 ESG/拉取失败）→豁免，
    但反编造（无数据却写具体 ESG 评级）→ FAIL。
    注意：consume 词不含裸「治理」（太宽，泛治理讨论不算消费 ESG 评级）。
    """
    es = _snapshot_get(data, "s_esg") or {}
    es_data = es.get("data", {}) if isinstance(es, dict) else {}
    status = es_data.get("status") if isinstance(es_data, dict) else None
    has_value = (es_data.get("latest_period") or {}).get("value") is not None if isinstance(es_data, dict) else False

    if status == "ok" and has_value:
        if not re.search(r"(ESG|中证|聚源|可持续发展|AAA|AA|BBB|BB|CCC|CC)", report):
            return False
    # 反编造：非 ok 却写具体「ESG 评级为 X」
    if status != "ok" and re.search(r"ESG\s*评级\s*(?:为|约|是|[：:])\s*[A-F]", report):
        return False
    return True


# 注册所有 Gate 验证函数
def check_g45(report: str, data: dict) -> bool:
    """G45: 目标价口径溯源（m5 责任；防 websearch 目标价与 API-grade 混用无 src）。SOFT(weight1)。

    F4：报告含「目标价/目标位/合理估值/合理价」+ 价格数字（N元）时，须有 [src:] 溯源 OR
    不确定性标注（数据不足/无法量化/区间/粗略/预估/仅供参考/存在不确定性/待核实）。裸目标价
    数字无 src（如 websearch 50.8 与 API 87.9 混用）→ FAIL。无目标价提及 → PASS
    （压力位/支撑位非目标价不触发）。校验对象 = m5 目标价表述（对照 valuation_snapshot API-grade）。
    """
    has_target = any(kw in report for kw in ("目标价", "目标位", "合理估值", "合理价"))
    has_price = bool(re.search(r'\d+(\.\d+)?\s*元', report))
    if not (has_target and has_price):
        return True
    # F-G4 收紧：旧版 `"[src:" in report`（任意位置）→ websearch 冒充 API 时 src 可在他处漂过。
    # 改为按行（markdown bullet 一行）切：每个「目标价语境 + N元」行自身须带 [src:] 或不确定性标注。
    # 旧版 `has_src anywhere` 被替换；src 与目标价同行（m5 模板 [src:] 置 bullet 末，同行命中）。
    _UNC = ("数据不足", "无法量化", "区间", "粗略", "预估", "仅供参考", "存在不确定性", "待核实", "未核实")
    for ln in report.split('\n'):
        if any(kw in ln for kw in ("目标价", "目标位", "合理估值", "合理价")) and \
                re.search(r'\d+(\.\d+)?\s*元', ln):
            if "[src:" not in ln and not any(kw in ln for kw in _UNC):
                return False   # 目标价 N元 行无 src/不确定性标注 → FAIL（防 websearch 冒充 API-grade）
    return True


def check_g46(report: str, data: dict) -> bool:
    """G46: 公告登记表 machine_field 消费（已并入大事提醒时间线，本 checker 保留为占位以维持 gate 计数）。

    事件层重建：机器字段（主体/金额/股数/窗口）现由 m4 时间线 LEVEL1_CONTENT 原样 surface，
    致命事件 surface 由 G30#1 timeline.fatal_events 检查负责。故 G46 不再独立强制——恒 PASS。
    GATE_REGISTRY 保留条目维持 self_score 分母。
    """
    return True


def check_g47(report: str, data: dict) -> bool:
    """G47: 股东行为综合研判消费（m9.2/m7 责任；ST3 shareholder_dynamics 融合 意图×内部人×前十大）。
    SOFT(weight1)。三态 mirror G40-44：shareholder_dynamics.status=ok 且有材料级方向
    → 报告须含 presence 词（内部人/董监高/前十大/增持/减持/净买/净卖/港资）；空/failed→豁免；
    反编造（无数据却写具名减持/增持）→ FAIL。

    触发判定「有材料级方向」= verdict∈{净减持,净增持,分歧} 或 top10.named 非空 或
    corroboration.double_bearish/bullish 或 insiders.trades>0；纯中性且无具名活动 → 豁免
    （「无材料级股东变动」是有效中性结论，不门禁强制）。
    """
    proc = _snapshot_get(data, "s5_events.data.risk_signals.processed") or {}
    sd = proc.get("shareholder_dynamics") if isinstance(proc, dict) else None
    if not isinstance(sd, dict):
        return True
    if sd.get("status") == "failed":
        return True
    # 判定是否有材料级方向
    by = sd.get("by_source") or {}
    top10 = by.get("top10") or {}
    has_named = isinstance(top10, dict) and bool(top10.get("named"))
    ins = by.get("insiders") or {}
    has_insider_trade = isinstance(ins, dict) and (
        (isinstance(ins.get("trades"), (int, float)) and ins.get("trades") > 0)
        or ins.get("net_shares") not in (None, 0))
    # ST7：季度信封活动（只看最新期 periods[0] 有新进/加仓/减仓）
    t10q = by.get("top10_quarterly") or {}
    _t10q_periods = t10q.get("periods") if isinstance(t10q, dict) else None
    has_quarterly = bool(_t10q_periods) and any(
        (p.get("new_entrants") or p.get("increasers") or p.get("decreasers"))
        for p in _t10q_periods[:1] if isinstance(p, dict))
    corr = sd.get("corroboration") or {}
    has_resonance = isinstance(corr, dict) and (
        corr.get("double_bearish") or corr.get("double_bullish"))
    verdict = sd.get("verdict")
    has_direction = (verdict in ("净减持", "净增持", "分歧")) or has_named or has_insider_trade or has_resonance or has_quarterly
    if not has_direction:
        return True  # 真空/纯中性：有效结论，豁免
    # presence：报告须含股东行为研判词
    presence_kws = ("内部人", "董监高", "前十大", "增持", "减持", "净买", "净卖", "港资", "言行合一",
                    "季度", "新进", "撤出", "加仓", "减仓")
    if not any(kw in report for kw in presence_kws):
        return False
    # 反编造：status != ok 却写具名「前十大N名减持/增持」
    if sd.get("status") != "ok" and re.search(r"前十大.{0,6}[增减]持", report):
        return False
    return True


def check_g48(report: str, data: dict) -> bool:
    """G48: 待执行/进行中增减持计划消费（m9.2/m7/m1 责任；ST5 programs[] forward 信封）。
    SOFT(weight1)。三态 mirror G40-47：processed.programs 有 status∈{planned,ongoing}
    → 报告须含 presence 词（待执行/进行中/拟减持/拟增持/窗口/计划/增持/减持）；无活跃 program→豁免
    （已完成/无计划是有效结论，不门禁强制）；反编造（无活跃计划却写「待执行X%」）→ FAIL。

    用户核心意图：现在/未来有无增持/减持悬顶/支撑，决定操作——有活跃计划须 surface。
    """
    proc = _snapshot_get(data, "s5_events.data.risk_signals.processed") or {}
    if not isinstance(proc, dict):
        return True
    progs = proc.get("programs")
    if not isinstance(progs, list):
        return True
    active = [p for p in progs if isinstance(p, dict) and p.get("status") in ("planned", "ongoing")]
    if not active:
        # 反编造：无活跃计划却声称「待执行/进行中」+ 具体比例（窄口径：待执行+%，避免「回购进行中」等误伤）
        if re.search(r"待执行", report) and re.search(r"\d+(?:\.\d+)?\s*%", report):
            return False
        return True   # 无待执行/进行中计划：豁免
    # presence：报告须含待执行/进行中/计划类词
    presence_kws = ("待执行", "进行中", "拟减持", "拟增持", "窗口", "计划", "增持", "减持")
    if not any(kw in report for kw in presence_kws):
        return False
    return True


def check_g49(report: str, data: dict) -> bool:
    """G49: 买卖力量 verdict 消费（m9.2/m7/m6/m1/capstone 责任；ST6 buy_sell_pressure 信封）。
    SOFT(weight1)。三态 mirror G40-48：processed.buy_sell_pressure.status==ok 且 verdict∈
    {buy_dominant,sell_dominant,balanced}（有材料级活动）→ 报告须含 presence 词
    （买卖力量/买方/卖方/回购/增持/减持/解禁/质押/平仓）；unclear/failed/空→豁免（近一季无活动是有效结论）；
    反编造（无 verdict 却写「买卖力量」+ 阵营词）→ FAIL。

    用户核心意图：合并所有公告/资金面信号成买卖阵营对决——有对决结论须 surface。
    """
    proc = _snapshot_get(data, "s5_events.data.risk_signals.processed") or {}
    if not isinstance(proc, dict):
        return True
    bsp = proc.get("buy_sell_pressure")
    if not isinstance(bsp, dict) or bsp.get("status") != "ok":
        # 反编造：无 BSP（或 failed）却声称「买卖力量」+ 阵营结论词
        if "买卖力量" in report and re.search(r"买方|卖方|买方占优|卖方占优", report):
            return False
        return True
    verdict = bsp.get("verdict")
    if verdict in (None, "unclear"):
        return True   # 无材料级活动：豁免（不门禁强制干净票/真空票）
    # presence：有 verdict（buy/sell/balanced）→ 报告须含阵营/分量词之一
    presence_kws = ("买卖力量", "买方", "卖方", "回购", "增持", "减持", "解禁", "质押", "平仓")
    if not any(kw in report for kw in presence_kws):
        return False
    return True


def check_g50(report: str, data: dict) -> bool:
    """G50: 公告登记表 severity 一致性（已并入大事提醒时间线，本 checker 保留为占位以维持 gate 计数）。

    事件层重建：severity 体系退役，时间线用官方 EVENT_TYPE_CODE 分类（无三档 severity 可校验一致性）。
    致命事件 surface 由 G30#1 timeline.fatal_events 检查负责；数字/编造由 G16/G29 兜底。故 G50 恒 PASS。
    GATE_REGISTRY 保留条目维持 self_score 分母。
    """
    return True


def _sgr_numeric_claim(report):
    """报告是否给出了具体 SGR 数值（反捏造用）。
    含「SGR / 可持续增长」的行若同时带「数字%」即视为报值（覆盖「SGR=27.40%」「SGR 可持续增长率 30%」
    等多种写法）；纯公式行（SGR = ROE×b/(1−ROE×b)，无百分数）不算。"""
    for ln in report.split('\n'):
        if ('SGR' in ln or '可持续增长' in ln) and re.search(r'\d[\d.]*\s*%', ln):
            return True
    return False


def check_g51(report: str, data: dict) -> bool:
    """G51: m2 §2.13 SGR 全链路（fetch+save+read+golden）。SOFT(weight2)，mirror G29(三态+反捏造)。
    snapshot 路径 computed_metrics.sgr（runner _compute_sgr 派生，扁平 dict，value 存百分数 27.40）。
    三态：ok+value+适用 → 须消费 + 三件套结构 + 进度条 + 数值对齐(scales=1.0)；
    applicability 含「不适用」→ 报告写「不适用」且禁编 SGR 值；
    payout_source=assumed_no_dividend → 报告须 ⚠️/「上限」诚实脚注；无 sgr 信封 → 禁编 SGR 值。
    """
    sgr = _snapshot_get(data, "computed_metrics.sgr")
    # ① 未拉到：禁编造（无数据却报 SGR 数值 → FAIL）
    if not isinstance(sgr, dict):
        if _sgr_numeric_claim(report):
            return False
        return True
    status = sgr.get("status")
    applic = str(sgr.get("applicability") or "")
    val = sgr.get("value")
    has_sgr_line = bool(re.search(r'SGR|可持续增长', report))
    # ok + 有值 + 适用 → 须消费 + 三件套结构 + 进度条 + 数值对齐
    if status == "ok" and val is not None and "不适用" not in applic:
        if not has_sgr_line:
            return False   # 有数据报告没提
        if not any(k in report for k in ("ROE", "派息率", "留存率")):
            return False   # 三件套缺
        if "进度" not in report and "█" not in report:
            return False   # 进度条对比缺
        # 反捏造：报告 SGR 值须 == snapshot（scales=(1.0,) 禁万/亿误配）
        if not _check_value_freshness(report, val, ["SGR", "可持续增长"], scales=(1.0,), tol=0.05):
            return False
    # 不适用 → 报告写「不适用」且禁编值
    if "不适用" in applic:
        if "不适用" not in report:
            return False
        if _sgr_numeric_claim(report):
            return False
    # payout 缺失 assumed → 须 ⚠️/「上限」诚实脚注（防误导）
    if sgr.get("payout_source") == "assumed_no_dividend":
        if "⚠" not in report and "上限" not in report:
            return False
    return True


# ============================================================
# m3 技术面六维重构 gate（G52-G55）· _g56_section 段定位 helper
# ============================================================

def _m3_section(report: str) -> str:
    """定位 m3 技术面段（首个匹配 header 到下一同级/更高级 header 之间文本，含标题行）。G52-G55 共用。
    匹配「模块三/技术分析/技术面」header；无 m3 段 → ''（report-only / 非 m3 报告不执法）。
    level-aware（克隆 _g30_find_capstone）：不在 #### 子标题截断，让 G52-55 消费校验真正读到技术正文。"""
    return _module_section(report, r'^#{1,4}\s.*(?:模块三|技术分析|技术面)', full_report_fallback=False)[1]


def check_g52(report: str, data: dict) -> bool:
    """G52: m3 ATR 波动/破位全链路（fetch+save+read+golden）。SOFT(weight2)。
    snapshot 路径 s4_technical.data.atr（runner _compute_atr 派生，flat-dict：atr14/atr_pct/
    stop_ref_price/break_threshold/interpretation）。三态：never_traded→豁免；ok+atr14→须消费+止损/
    破位段+数值对齐(scales=1.0)；缺 atr→禁编 ATR 值。
    """
    s4 = _snapshot_get(data, "s4_technical") or {}
    if s4.get("status") == "never_traded":
        return True
    atr = _snapshot_get(data, "s4_technical.data.atr")
    sec = _m3_section(report)
    if not isinstance(atr, dict):
        if sec and re.search(r'ATR\s*(?:=|为|约|：)?\s*[\d.]+\s*元?', sec):
            return False   # 反捏造：无数据却报 ATR 值
        return True
    atr14 = atr.get("atr14")
    if atr14 is None:
        return True
    if s4.get("status") == "ok" and sec:
        # 反捏造：报告 ATR 值须 == snapshot atr14
        if not _check_value_freshness(sec, atr14, ["ATR", "真实波幅", "波幅"], scales=(1.0,), tol=0.05):
            return False
        # read：止损参考价/破位段
        if not any(k in sec for k in ("止损", "破位", "支撑")):
            return False
    return True


def check_g53(report: str, data: dict) -> bool:
    """G53: m3 换手率自身分位全链路（fetch+save+read+golden）。SOFT(weight2)·核心创新。
    snapshot 路径 s4_technical.data.turnover（_compute_turnover_analysis，pct_250=自身250天分布百分位）。
    自身分位法 enforcement：高换手↔pct≥70 / 低换手↔pct≤30（防用绝对阈值跨股误判）；
    反捏造：报告分位数须 == snapshot pct_250（tol 5 分位）。
    """
    s4 = _snapshot_get(data, "s4_technical") or {}
    if s4.get("status") == "never_traded":
        return True
    to = _snapshot_get(data, "s4_technical.data.turnover")
    sec = _m3_section(report)
    if not isinstance(to, dict) or not sec:
        return True
    pct = to.get("pct_250")
    if pct is None:
        return True
    # 反捏造：报告分位数须 == snapshot（提取首个"NN分位"/"第NN百分位"）
    mm = re.search(r'(?:第?\s*)(\d{1,3})\s*(?:分位|百分位)', sec)
    if mm and abs(int(mm.group(1)) - pct) > 5:
        return False   # 分位数捏造
    # 自身分位法 enforcement：结论词须与分位一致（防绝对值误判）
    if re.search(r'(高换手|换手偏高|成交活跃|放量)', sec) and pct < 70:
        return False
    if re.search(r'(低换手|换手偏低|缩量|成交清淡)', sec) and pct > 30:
        return False
    # 提了换手须有档位表述（不能只给绝对值不判断）
    if "换手" in sec and not re.search(r'分位|偏高|偏低|正常|活跃|清淡', sec):
        return False
    return True


def check_g54(report: str, data: dict) -> bool:
    """G54: m3 技术环境+正交信号(ADX/BIAS/OBV)全链路（fetch+save+read+golden）。SOFT(weight2)。
    snapshot 路径 s4_technical.data.signals.state（_compute_indicator_trends 加 adx_state/bias_state/
    obv_trend）。三键渐进（部分缺失不硬 FAIL）；ADX 值须 == snapshot technical.dmi.ADX（反捏造）；
    报告须有环境判定段（震荡/趋势/环境）。
    """
    s4 = _snapshot_get(data, "s4_technical") or {}
    if s4.get("status") == "never_traded":
        return True
    state = _snapshot_get(data, "s4_technical.data.signals.state")
    sec = _m3_section(report)
    if not isinstance(state, dict) or not sec:
        return True
    # 三键存在性（渐进：任一 None 不硬 FAIL；存在则须是字符串）
    present = [k for k in ("adx_state", "bias_state", "obv_trend") if state.get(k) is not None]
    for k in present:
        if not isinstance(state.get(k), str):
            return False
    # 反捏造：ADX 数值须 == snapshot technical.dmi.ADX
    dmi = _snapshot_get(data, "s4_technical.data.technical.dmi") or {}
    adx = dmi.get("ADX")
    if adx is not None and "adx_state" in present:
        if not _check_value_freshness(sec, adx, ["ADX"], scales=(1.0,), tol=0.05):
            return False
    # read：环境判定段（震荡/趋势/环境）
    if present and not re.search(r'(震荡|趋势|环境)', sec):
        return False
    return True


def check_g55(report: str, data: dict) -> bool:
    """G55: m3 golden 结构+边界+VWAP（fetch+save+read+golden）。SOFT(weight2)。
    golden = 六维读数（环境/量能/位置/筹码/趋势 至少覆盖4维）+ 综合一致性诊断段（非打分）；
    边界禁区：仓位%/盈亏比/重仓/打分 → m6/m7（m3 只读数诊断）；VWAP 值须 == snapshot（反捏造）。
    """
    s4 = _snapshot_get(data, "s4_technical") or {}
    if s4.get("status") == "never_traded":
        return True
    sec = _m3_section(report)
    if not sec:
        return True   # 非 m3 报告不执法
    # ③ golden：六维读数维度词（至少覆盖 4/5 维 + 诊断段）
    dims = [(r'ADX|震荡|趋势', "环境"), (r'换手|分位|量能|OBV', "量能"),
            (r'VWAP|乖离|BIAS|支撑|压力|斐波', "位置"), (r'筹码|获利盘|成本', "筹码"),
            (r'MACD|KDJ|均线|TD|RSI', "趋势")]
    hit = sum(1 for pat, _ in dims if re.search(pat, sec))
    if hit < 4:
        return False
    if not re.search(r'(诊断|共振|分歧|阶段)', sec):
        return False   # 缺综合诊断段
    # ④ 边界禁区：仓位/盈亏比/重仓/买卖建议/打分（m3 只读数诊断，决策→m6）
    if re.search(r'(仓位|盈亏比|重仓|建议买入|建议卖出)', sec):
        return False
    if re.search(r'得分|评分|综合\s*\d+\s*分', sec):
        return False
    # ②③ VWAP 反捏造（s2_quote_kline.data.realtime_quote.vwap 零成本消费）
    vwap = _snapshot_get(data, "s2_quote_kline.data.realtime_quote.vwap")
    if vwap is not None and "VWAP" in sec:
        if not _check_value_freshness(sec, vwap, ["VWAP"], scales=(1.0,), tol=0.01):
            return False
    return True


def check_g56(report: str, data: dict) -> bool:
    """G56: m1 golden 收敛+边界+反捏造。SOFT(weight2)。
    m1 收敛后 = 五块定性叙事（类型/身份主营/历史阶段/当前阶段定位/同行差异化）+ 资金筹码一句话指向 home。
    禁：ST5/ST6 独立段量化、新接线标记、%/金额/窗口/逐笔（→m9 §9.2 / m7 §7.5.2）。
    反捏造：报告类型词 == classification.primary_type；占主营 Y% == snapshot dominant_business.revenue_ratio。
    """
    # 定位 m1 段（首个「标的概况」header 到下一同级 header）
    m = re.search(r'^#{1,4}\s.*标的概况', report, re.MULTILINE)
    if not m:
        return True   # 无 m1 段不执法（report-only / 非 m1 报告）
    rest = report[m.end():]
    nxt = re.search(r'^#{1,4}\s', rest, re.MULTILINE)
    sec = rest[:(nxt.start() if nxt else len(rest))]

    cls = _snapshot_get(data, "classification") or {}
    primary = cls.get("primary_type")

    # ① 反捏造：类型词缺失即越界/捏造
    _TYPE_KW = {"成长": ("成长",), "价值": ("价值",), "防御": ("防御", "公用"),
                "周期": ("周期",), "金融": ("金融", "银行", "券商", "保险")}
    if primary:
        stem = next((k for k in _TYPE_KW if k in str(primary)), None)
        syns = _TYPE_KW.get(stem, (str(primary),))
        if not any(s in sec for s in syns):
            return False   # 类型词缺失（可能捏造了别的类型）
        # dominant_business 占比数值对齐（report"占主营Y%" == snapshot）
        dom = cls.get("dominant_business") or {}
        ratio = dom.get("revenue_ratio")
        if ratio is not None and any(k in sec for k in ("占主营", "主营")):
            if not _check_value_freshness(sec, ratio, ["占主营", "主营"], scales=(1.0, 0.01), tol=0.05):
                return False   # 占比数捏造

    # ③ golden 结构：五块标志词（任一同义即可）
    _MUST = [("类型", "估值框架"), ("主营", "业务", "产品"), ("历史", "上市", "阶段"),
             ("当前", "阶段定位", "所处"), ("同行", "差异化", "vs", "对比")]
    for grp in _MUST:
        if not any(k in sec for k in grp):
            return False   # 五块不全

    # ④ 边界禁区（收敛核心）：禁新接线标记 + ST5/ST6 量化独立段
    if "🆕" in sec:
        return False
    if re.search(r'(减持|增持|回购)\s*(?:计划|悬顶|在途).{0,20}[\d.]+\s*[%亿]', sec):
        return False   # ST5/ST6 量化越界（→m9 §9.2）
    if re.search(r'(verdict|买卖阵营|买卖力量).{0,15}[\d.]+\s*亿', sec):
        return False   # ST6 verdict 量化越界
    # 资金/筹码方向须指向 home（≤1 句，不可独立成段重渲染）
    if any(k in sec for k in ("资金", "筹码", "回购", "减持", "增持")) and \
            not re.search(r'(详见|见)\s*m[79]', sec, re.IGNORECASE):
        return False   # 资金筹码未指向 m9/m7 = 越界重渲染
    return True


def check_g57(report: str, data: dict) -> bool:
    """G57: m4 growth_tier 消费一致性 + 反编造（m4 §4.1.1 P4 责任）。SOFT(weight1)，mirror G50 三态+反编造。
    snapshot 路径 consensus_forecast.data.company_guidance.latest_period.value.growth_tier
    （runner _fetch_company_guidance:6638 派生；仅 predict_type=='预增' 按 INCREASE_JZ 分档：
    >50%→high / 20-50%→moderate / 其余·非预增·缺字段→None）。
      · 漏报：data growth_tier=high/moderate，报告须含对应成长强度词；缺 → FAIL
      · 反编造：data growth_tier=None（非预增/略增/缺），报告却在业绩预告语境写高/中成长 → FAIL
      · 三态豁免：company_guidance/latest_period 缺失或拉取失败 → growth_tier 视为 None（空豁免），
        但反编造仍生效（禁无中生有）。
    解析保守：成长强度词 = 高成长|高增长|高速增(high) / 中成长|中增长(moderate)；反编造须与
    业绩语境（预增/业绩预告/业绩上修/上修）同行，避免行业「高成长」误伤。
    """
    gt = _snapshot_get(data, "consensus_forecast.data.company_guidance.latest_period.value.growth_tier")
    _HIGH = re.compile(r"高成长|高增长|高速增")
    _MOD = re.compile(r"中成长|中增长")
    if gt in ("high", "moderate"):
        if gt == "high" and not _HIGH.search(report):
            return False   # 漏报：数据 high 报告无高成长词
        if gt == "moderate" and not _MOD.search(report):
            return False   # 漏报：数据 moderate 报告无中成长词
    else:
        # None/缺 → 禁在业绩语境编造成长强度（反编造，scope 业绩行避免行业「高成长」误伤）
        for ln in report.splitlines():
            if ("预增" in ln or "业绩预告" in ln or "业绩上修" in ln or "上修" in ln) and \
                    (_HIGH.search(ln) or _MOD.search(ln)):
                return False
    return True


def check_g58(report: str, data: dict) -> bool:
    """G58: m5 估值分位必写+反编造（F-G1）。SOFT(weight1)，mirror G57/G50 三态+反编造。
    valuation_snapshot.data.valuation_percentile.{pe_ttm,pb,ev_ebitda}：每项 applicable=true 且有 pct_5y 时，
    m5 段须 surface 分位（_check_value_freshness 判 grounded——行带 [src:] 或 pct 值×0.01 对齐 snapshot）。
    applicable=false（亏损 EV-EBITDA≤0）/无分位数据→PASS（三态豁免）。
    反编造：valuation_percentile 整体缺失，m5 却写具体「NN% 分位」→ FAIL（无中生有）。
    3 态：m5 段缺失 + 有 applicable 分位 = FAIL（漏报；修复前 `模块五` 关键词太窄 + `if not m: return True`
    逃逸致永远 PASS）；m5 段缺失 + 无 applicable 数据 = PASS。关键词拓宽至 估值分析/估值 兜住折叠标题。"""
    vp = _snapshot_get(data, "valuation_snapshot.data.valuation_percentile")
    vp = vp if isinstance(vp, dict) else {}
    found, sec = _module_section(report, r'^#{1,4}\s.*(?:模块五|估值分析|估值)')
    if not found:
        sec = ""
    # ① 漏报：applicable 分位须 surface（grounded via [src:] 或 pct 值对齐）；章节缺失 + applicable = FAIL
    for key in ("pe_ttm", "pb", "ev_ebitda"):
        blk = vp.get(key) or {}
        if blk.get("applicable") and blk.get("pct_5y") is not None:
            if not _check_value_freshness(sec, blk.get("pct_5y"), ["分位", "百分位"],
                                          scales=(0.01,), tol=0.15):
                return False   # applicable 但 m5 未 surface 分位（漏报 / 数值不对齐 / 章节缺失）
    # ② 反编造：无分位数据（vp 整体空）却写具体分位百分比 → 编造
    if not vp:
        if "分位" in sec and re.search(r'[\d.]+\s*%', sec):
            return False
    return True


def check_g59(report: str, data: dict) -> bool:
    """G59: m5 §5.3 估值结论 verdict presence（F-G2）。SOFT(weight1)。
    m5 §5.3 估值结论必含判定词（偏贵/偏贱/高估/低估/估值合理/估值适中/估值偏低/估值偏高）。
    纯 presence——定性结论无法验正确性，但确保 m5 给读者明确贵贱判定（无 verdict → FAIL）。
    无 §5.3 段→PASS（report-only / 非估值报告）。
    """
    m = re.search(r'^#{1,4}\s.*5\.3', report, re.MULTILINE)
    if not m:
        return True
    rest = report[m.end():]
    nxt = re.search(r'^#{1,4}\s', rest, re.MULTILINE)
    sec = rest[:(nxt.start() if nxt else len(rest))]
    return any(k in sec for k in ("偏贵", "偏贱", "高估", "低估", "估值合理",
                                   "估值适中", "估值偏低", "估值偏高"))


def check_g60(report: str, data: dict) -> bool:
    """G60: m6 定性三行结构化锚点+反捏造（G-G2）。SOFT(weight1)，mirror G56/G58 三态+反编造。
    Layer1 ⑪护城河/⑫治理战略/⑬前瞻催化 三定性维度行各须含 ≥1 结构化锚点 [src:]（研发强度/P-codes/
    segment）；纯定性补充显式标「无源/定性补充」可豁免（真空/干净票），但既无 [src:] 又无「无源」标注 =
    定性裸奔 FAIL。反捏造：「研发强度X%」须≈snapshot（研发费用÷营业总收入，targeted regex 避免「研发费
    113亿」绝对值误伤）。
    三态：有锚/标无源 PASS / 无 m6 段豁免 / 裸奔或研发强度%捏造 FAIL。
    覆盖范围限定 Layer1「证据全景」子节——投资建议/观察清单的定性叙事（如「护城河深厚」）合法无 src，不误伤。
    """
    m = re.search(r'^#{1,4}\s.*综合研判', report, re.MULTILINE)
    if not m:
        return True   # 无 m6 段不执法（report-only / 非 m6 报告）
    rest = report[m.end():]
    # ⚠️ sec 边界用 ^#{1,3}（停在下一个 ### 模块），让 sec 跨越整个 m6 模块**含其 #### 子节**。
    # 若用 ^#{1,4} 会立即在 m6 第一个子节「#### Layer 1 — 证据全景」截断 → sec 仅剩标题尾，
    # Layer1 全部内容被排除 → 定性行永不命中 → gate 恒 PASS（m6 版 G30 同款同级标题截断 bug）。
    nxt = re.search(r'^#{1,3}\s', rest, re.MULTILINE)
    sec = rest[:(nxt.start() if nxt else len(rest))]
    # 定位 Layer1「证据全景」子节（投资建议叙事不含 src 合法，须隔离；pnxt 仍用 ^#{1,4} 停于下一 #### 子节）
    pm = re.search(r'^#{1,4}\s.*(?:证据全景|证据盘点|证据矩阵|全景)', sec, re.MULTILINE)
    if pm:
        psec = sec[pm.end():]
        pnxt = re.search(r'^#{1,4}\s', psec, re.MULTILINE)
        layer1 = psec[:(pnxt.start() if pnxt else len(psec))]
    else:
        layer1 = sec
    _SKIP = ("你须", "你判", "helper", "解读提示", "代码释义见", "定性锚点（helper",
             "定性（你", "机械格式", "self-check", "tally 是")
    _DIM_KWS = ("护城河", "治理战略", "前瞻催化")
    _PURE = ("无源", "定性补充")
    # ① 三定性维度数据行各须含 ≥1 [src:]（既无 src 又无「无源」标注 = 裸奔 FAIL）
    for ln in layer1.splitlines():
        if not any(k in ln for k in _DIM_KWS):
            continue
        if any(s in ln for s in _SKIP):
            continue
        if "[src:" not in ln and not any(p in ln for p in _PURE):
            return False
    # ② 反捏造：研发强度X% 须≈snapshot（targeted regex「研发强度」后跟 %，避免「研发费N亿」绝对值误伤）
    rd_val = None
    inc = _snapshot_get(data, "s1_financial.data.income_statement") or {}
    rows_inc = inc.get("data") or inc.get("data_full") or []
    if rows_inc and isinstance(rows_inc[0], dict):
        _rd = rows_inc[0].get("研发费用")
        _rev = rows_inc[0].get("营业总收入")
        if isinstance(_rd, (int, float)) and isinstance(_rev, (int, float)) and _rev:
            rd_val = _rd / _rev
    if rd_val is not None:
        _rd_pct = rd_val * 100
        for mm in re.finditer(r'研发强度\s*([\d.]+)\s*%', sec):
            try:
                _x = float(mm.group(1))
            except ValueError:
                continue
            if _x > 0 and max(_x, _rd_pct) / min(_x, _rd_pct) > 1.3:
                return False   # 研发强度% 捏造（与 snapshot 研发费÷营收 不对齐）
    return True


def check_g61(report: str, data: dict) -> bool:
    """G61: 千股千评结论一等公民完整性（四段闭环仿 G1，根治「只拉不用」）。SOFT(weight1)。

    守护 fetch→store→read→consume 全链（用户钦定「结论一等公民·不用只拉不用」）：
    ① 拉取：s_stock_evaluation.data.status 三态——failed→FAIL(禁编造)；missing(金融股/次新无千股千评,
       真空)→PASS 豁免；ok→继续。
    ② 保存：conclusions 非空 + 每条四键(dimension/text/severity/source_api) + latest_period 信封非 None。
    ③ 读取：_snapshot_get 双兜底 data/data_full 能读出 processed.conclusions（防 never-match，读三表范式硬规则）。
    ④ 消费：每个 ok 结论维度报告须 surface 对应词（severity 无关——结论即一等公民，拉了就须消费）；
       反编造：报告含结论词却无 s_stock_evaluation [src:] 锚 → FAIL。
    向后兼容：旧 snapshot 无 s_stock_evaluation 键 → PASS（get_evaluation status=None 走①豁免，保 fixture 漏报=0）。
    """
    from latest_extract import get_evaluation
    ev = get_evaluation(data)
    status = ev.get("status")
    # ① 拉取三态
    if status == "failed":
        return False                          # 拉取失败禁编造结论
    if status in ("missing", "never_evaluated", None):
        return True                           # 真空豁免（金融股/次新/非标的/旧 snapshot 无此 scene）
    if status != "ok":
        return True
    conclusions = ev.get("conclusions") or []
    # ② 保存格式正确
    if not conclusions:
        return False                          # ok 却无结论 = 管道断裂（只拉不用）
    REQ = ("dimension", "text", "severity", "source_api")
    if not all(all(k in c for k in REQ) for c in conclusions):
        return False                          # 字段缺 = 格式不正确
    if not ev.get("latest_period"):
        return False                          # 黄金范式信封缺
    # ③ 读取统一（双兜底，防 never-match）
    if not (_snapshot_get(data, "s_stock_evaluation.data.processed.conclusions")
            or _snapshot_get(data, "s_stock_evaluation.data_full.processed.conclusions")):
        return False
    # ④ 消费完整（不用只拉不用）：每个 ok 结论维度报告须 surface 对应词
    DIM_WORDS = {
        "控盘程度": ("完全控盘", "高度控盘", "中度控盘", "轻度控盘", "低度控盘", "控盘"),
        "综合结论": ("主力资金", "消息面", "上涨趋势", "上升趋势", "震荡趋势", "下跌趋势",
                    "市场关注", "关注意愿", "介入迹象", "资金流出"),
        "趋势量能": ("支撑位", "压力位", "强势上涨", "震荡上行", "弱势", "量能", "缩量", "放量"),
        "融资杠杆": ("融资余额", "融资", "杠杆", "两融", "保证金", "冲抵"),
    }
    for c in conclusions:
        words = DIM_WORDS.get(c.get("dimension"))
        if not words:
            continue                          # 未登记维度不强制（向前兼容新维度）
        if not any(w in report for w in words):
            return False                      # 只拉不用：ok 结论维度未 surface
    # 反编造：报告含结论词却无数据源锚 = 编造
    _HAS_CONCL = ("控盘", "主力资金介入", "主力资金流出", "支撑位", "压力位", "两融标的")
    if any(w in report for w in _HAS_CONCL) and "s_stock_evaluation" not in report:
        return False
    return True


GATE_CHECKERS = {
    "G1": check_g1, "G6": check_g6, "G7": check_g7, "G8": check_g8,
    "G9": check_g9, "G10": check_g10, "G11": check_g11, "G12": check_g12,
    "G13": check_g13, "G14": check_g14, "G15": check_g15, "G16": check_g16,
    "G17": check_g17, "G18": check_g18, "G19": check_g19, "G20": check_g20,
    "G21": check_g21, "G22": check_g22, "G23": check_g23,
    "G25": check_g25, "G26": check_g26, "G27": check_g27, "G28": check_g28,
    "G29": check_g29, "G30": check_g30, "G31": check_g31,
    "G32": check_g32, "G33": check_g33,
    "G34": check_g34, "G35": check_g35, "G36": check_g36,
    "G37": check_g37, "G38": check_g38, "G39": check_g39,
    "G40": check_g40, "G41": check_g41,
    "G42": check_g42, "G43": check_g43, "G44": check_g44,
    "G45": check_g45, "G46": check_g46,
    "G47": check_g47,
    "G48": check_g48,
    "G49": check_g49,
    "G50": check_g50,
    "G51": check_g51,
    "G52": check_g52,
    "G53": check_g53,
    "G54": check_g54,
    "G55": check_g55,
    "G56": check_g56,
    "G57": check_g57,
    "G58": check_g58,
    "G59": check_g59,
    "G60": check_g60,
    "G61": check_g61,
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
    # F5/F12（plan Step 2.4.3/2.4.5）：一致预期/业绩预告参与完整性自评（反片面·前瞻维度）。
    # envelope 级——annual={} 真空（如 300444 无机构覆盖）不误扣（status 仍 ok/partial）；
    # 整个 consensus_forecast 失败/缺失才扣分。
    ("consensus_forecast", "一致预期/业绩预告"),
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
