#!/usr/bin/env python3
"""
capstone_panorama.py — 综合研判 capstone 的「证据全景」helper（LLM 写作期工具）

设计哲学（lucky-petting-rabbit.md C）：LLM 负责权衡+裁决，结构负责完整+诚实。
本 helper 只做两件事，绝不替 LLM 算答案：
  1. panorama(snapshot) —— 从 snapshot 抽各量化维度的【值】+ 适用性 flag + gap 标注，
     渲染成"证据全景"草稿表，供 LLM 写 Layer1。只抽值，不打分、不映射概率、不预填方向。
  2. panorama_advisory(report, snapshot) —— #7 软一致性提示：自列证据明显倾向 X、
     裁决却 Y → 标记"请明示理由"。不计入 gate verdict（engine 无 warning 通道，故为写作期）。

自包含（自带 _snapshot_get / _scene_has_data），不依赖 gate_definitions，避免循环 import。
读三表/derived 双兜底（CLAUDE.md 硬规则）。

CLI:
  python capstone_panorama.py --snapshot S.json                # 输出证据全景草稿
  python capstone_panorama.py --snapshot S.json --report R.md  # 草稿 + #7 软提示
"""
import argparse
import json
import re
import sys
from pathlib import Path

from latest_extract import days_old  # freshness stale 标记（叶工具，无循环依赖）
from announcement_materiality import derive_horizon  # v3：present_signals 附 horizon（按码派生，无循环依赖）


# ============================================================
# 自包含 snapshot 读取（与 gate_definitions 同语义，避免循环 import）
# ============================================================

def _snapshot_get(data: dict, path: str):
    parts = path.split(".")
    cur = data
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list) and p.isdigit():
            cur = cur[int(p)] if int(p) < len(cur) else None
        else:
            return None
    return cur


def _scene_bucket(val) -> str:
    """三桶判定（P1b 2026-09-03，retrospective_audit_20260902 处置④）：
    present（有数据→G30#1 覆盖义务）/ gap（到场未出货→披露义务）/ failed（拉取失败→
    披露义务+点名源）；"absent"（None/空 str/list：模式作用域外结构性缺席）不承担
    披露义务（mode B 不拉 s1 属设计非数据洞），显示层并入 gap。

    旧 `_scene_has_data` 黑名单语义的病：status=degraded/missing 的非空信封
    （002202 实证：asset_safety={status:'degraded'} 无 data 键、segment 富 dict
    status='missing'）落到 `bool(val)` 兜底 → 判 present → gate 把从未到货的
    维度当 present 强制覆盖（「真片面」假 FAIL）。改判独立桶后豁免覆盖但
    强制披露——防 Goodhart 回流（豁免≠静默免单）。"""
    if val is None:
        return "absent"
    if isinstance(val, str):
        return "present" if val.strip() else "absent"
    if isinstance(val, list):
        return "present" if val else "absent"
    if isinstance(val, dict):
        dd = val.get("data", val.get("data_full"))
        for env in (val, dd if isinstance(dd, dict) else {}):
            if env.get("status") in ("failed", "error", "throttled"):
                return "failed"
        if (isinstance(dd, (dict, list)) and dd):
            return "present"
        if val.get("status") is not None:
            return "gap"               # 有信封无数据 → 到场未出货
        return "present" if val else "absent"
    return "present" if val else "absent"


def _envelope_status(val) -> str:
    """读信封 status（顶层优先，嵌套 data.status 兜底；缺席返回 ''）。"""
    if isinstance(val, dict):
        st = val.get("status")
        if st is None:
            dd = val.get("data", val.get("data_full"))
            if isinstance(dd, dict):
                st = dd.get("status")
        return str(st) if st else ""
    return ""


def _rows(section):
    """三表/derived 双兜底取行（CLAUDE.md 硬规则）。"""
    if not isinstance(section, dict):
        return []
    return section.get("data", section.get("data_full", [])) or []


# ============================================================
# 维度注册表（plan Layer1）—— 单一真相源：量化维度→snapshot 路径 + 报告关键词
# ⚠️ gate_definitions.check_g30 的 CAPSTONE_DIM_PATHS 须与本表路径保持一致
# ============================================================

QUANT_THEMES = [
    ("财务质量", ["s1_financial.data.financial_indicators", "s1_financial.data.dupont"],
     ["ROE", "净资产收益率", "净利率", "毛利率", "杜邦", "周转率", "权益乘数", "扣非", "盈利能力"]),
    ("成长性", ["s1_financial.data.income_statement", "s1_financial.data.balance_sheet"],
     ["营收", "收入", "扣非", "合同负债", "增速", "增长", "拐点", "同比"]),
    ("估值", ["valuation_snapshot.data.quote", "valuation_snapshot.data.targetPrice",
            "valuation_snapshot.data.analystRating"],
     ["PE", "PB", "估值", "分位", "目标价", "贵", "便宜", "市盈", "市净"]),
    ("资产安全", ["computed_metrics.asset_safety"],
     ["货币资金", "有息负债", "商誉", "负债率", "资产负债", "cash_to_debt", "资金链", "现金"]),
    ("技术资金筹码", ["s3_fund_flow.data.fund_flow", "s2_quote_kline", "s8_a_share"],
     ["信号", "资金流", "资金", "筹码", "股东户数", "K线", "均线", "支撑", "阻力", "换手"]),
    ("前瞻预期", ["consensus_forecast", "valuation_snapshot.data.analystRating",
                "s55_industry", "s6_macro.data.pmi"],
     ["一致预期", "评级", "催化", "景气", "预期", "预测", "研报", "目标", "展望"]),
    ("龙虎榜资金", ["lhb.data.processed"],
     ["龙虎榜", "上榜", "机构席位", "游资", "营业部", "席位"]),
    ("北向资金", ["northbound.data.processed"],
     ["北向", "外资", "沪深港通", "陆股通", "持股比例"]),
    # §2.2 主营构成三维（产品/行业/地区同等量级）——G30 #1 反片面经 QUANT_KW 自动同步
    ("主营构成", ["s1_financial.data.segment_composition"],
     ["分产品", "分行业", "分地区", "主营构成", "收入占比", "毛利率",
      "海外", "境外", "外销", "敞口", "集中度", "关税"]),
    # F3 同业对比（target + ≤3 peer 核心6；s11_peer 为 first-class scene，capstone 须 surface）
    ("同业对比", ["s11_peer.data"],
     ["同业", "可比", "竞品", "peer", "营收增速", "净利增速", "毛利率", "PE", "PB", "ROE"]),
]

QUAL_THEMES = [
    ("护城河", ["护城河", "壁垒", "龙头", "垄断", "品牌", "网络效应", "转换成本",
              "规模优势", "技术优势", "市占率", "定价权", "专利", "客户粘性"]),
    ("治理战略", ["治理", "管理层", "股权", "战略", "激励", "质押", "控股",
                "执行力", "国企", "民企", "股东结构", "董监高"]),
    ("前瞻催化", ["前瞻", "预期", "催化", "景气", "趋势", "展望", "未来",
                "成长空间", "渗透率", "国产替代", "新产品", "扩产"]),
]

# 模式B定性维度（B 报告的叙事面：技术结构解读而非基本面主题，2026-08-26 B v2）
QUAL_THEMES_B = [
    ("多周期共振解读", ["月线", "周线", "日线", "60分钟", "60分钟", "共振", "多周期",
                       "MA20", "排列", "上升趋势", "下降趋势"]),
    ("大盘环境", ["大盘", "上证", "指数", "regime", "trend_up", "trend_down",
                "创业板", "板块", "市场环境"]),
    ("量价与背离结构", ["放量", "缩量", "量比", "成交额", "换手", "背离", "顶背离",
                       "底背离", "MACD", "量价配合", "尾盘"]),
]

QUANT_KW = {t: kw for t, _, kw in QUANT_THEMES}
QUAL_KW = {t: kw for t, kw in QUAL_THEMES}
QUAL_KW_B = {t: kw for t, kw in QUAL_THEMES_B}  # B 主题→关键词（gate G30 合并查找，2026-08-26 B v2）


# M-code presence 关键词表（G30#1 信号覆盖用·精确词拒 K线/换手冒充；path-agnostic，timeline/M-code 共用）。
_M_SIGNAL_KW = {
    "M1": ("股东减持", ("减持", "股东减持")),
    "M2": ("股权质押", ("质押", "质押平仓", "股权质押")),
    "M3": ("限售解禁", ("解禁", "限售解禁", "解禁压力")),
    "M4": ("违规/处罚", ("违规", "处罚", "立案调查", "监管处罚", "会计差错")),
    "M5": ("ST/退市", ("ST", "退市", "*ST")),
    "M6": ("增发稀释", ("增发", "增发稀释")),
    "M7": ("监管函", ("监管函", "问询函", "警示函")),
    "M8": ("业绩下修", ("预减", "预亏", "首亏", "续亏", "计损", "减值")),
    "M9": ("对外担保", ("担保", "对外担保", "连带责任")),
    "M10": ("交易异动", ("异动", "交易异常", "波动")),
    "M11": ("人员变动/立案", ("被立案", "立案调查", "人员变动", "高管变动", "离任", "辞职")),
}

# 大事提醒 EVENT_TYPE_CODE → M-code（timeline 已分桶 risk/forward/fatal，故投影 M-code 无需 severity 过滤）。
# forward 减持码(320/090/100) 仅 LV1 含减持/转让 才算 M1（增持=catalyst）；directional(002/003) 仅 risk-flavor 才算 M8。
_TIMELINE_CODE_TO_M = {
    "320": "M1", "090": "M1", "100": "M1",   # 股东/高管增减持
    "160": "M2", "080": "M3",                # 质押 / 解禁
    "270": "M4", "330": "M4",                 # 违规处罚 / 非标审计
    "230": "M5", "240": "M5", "430": "M5",    # ST / 退市 / 风险警示
    "180": "M6", "190": "M6",                 # 增发 / 配股
    "340": "M7",                              # 监管问询
    "002": "M8", "003": "M8",                 # 业绩快报/预告（减向）
    "250": "M9", "220": "M10",                # 对外担保 / 停复牌异动
    "380": "M11", "390": "M11", "370": "M11", # 董事长/总经理/法定代表人变更
}


def _is_phantom_m5(e):
    """code 230=上市状态变动 涵盖新股上市(benign)与 ST/退市 变动；specific/内容为新股上市的
    事件不构成 M5 风险信号（次新股 G30#1 假阳性根因，301682 实证）。"""
    if str(e.get("event_type_code")) != "230":
        return False
    return (e.get("specific") == "新股上市"
            or "新股上市" in str(e.get("level1_content") or ""))

# 信号覆盖维度（G30#1）：S2/S7 筹码码（severity 阈值·股东户数信号族）；M-code 由 timeline 投影（见下）。
# (processed 路径, 取码子键, {code: (name, precise_kws)}, 收集的 severity 集)
_SIGNAL_SOURCES = [
    ("s8_a_share.data.shareholder_count.processed", "signals",
     {"S2": ("高位派发", ("派发", "高位派发")),
      "S7": ("筹码急剧分散", ("筹码分散", "急剧分散", "筹码松动"))},
     ("critical", "warning")),   # 筹码码 warning 亦是实质风险（高位派发/散户涌入），非例行噪声
]


# ============================================================
# panorama —— 抽值（不打分）+ gap + 适用性 flag
# ============================================================

def _yi(v):
    try:
        return f"{float(v) / 1e8:.2f}亿"
    except (TypeError, ValueError):
        return None


def _stale_marker(lp: dict, threshold_days: int) -> str:
    """latest_period 信封的 stale 标记：days_old > threshold → ' ⚠️历史数据·非近期(距今N天)'。

    信号族（lhb/northbound）/ company_guidance 是稀疏·时序敏感数据，越远越不重要——
    渲染时须让 LLM 一眼看到「这是旧信号，别当近期活跃据此调仓位」（plan §4.1 改动 F）。
    """
    if not isinstance(lp, dict) or lp.get("sort_key") is None:
        return ""
    d_old = days_old(lp.get("sort_key"), lp.get("as_of"))
    if d_old is not None and d_old > threshold_days:
        return f" ⚠️历史数据·非近期(距今{d_old}天)"
    return ""


def _latest_annual_roe(data: dict, roe_key: str = "加权净资产收益率(%)"):
    """从 financial_indicators 取最近【年报】（日期末 12-31）ROE，供 ①财务质量 dim 用年化基准。

    为什么需要：tally 财务质量阈值 ≥10/<5 按【全年盈利能力】标定，但 snapshot 最新期常为
    Q1/H1 的 YTD 值（600036 招行：2026Q1=3.37 而 2025年报=13.44）。用 YTD 套年化阈值会把
    高质量股误判成偏空。优先取最近年报 ROE；无年报（次新/缺数据）返 None 由调用方退回最新期值
    （m6 解读提示已警示「非年化」）。双键兜底 data/data_full（读三表范式硬规则）。

    顺序：raw cache 行可能是 asc（未排序），故遍历全部取 max 日期的年报行，不信 rows[0]。
    ISO 日期串（YYYY-MM-DD）字典序比较正确。
    """
    fi = _snapshot_get(data, "s1_financial.data.financial_indicators") or {}
    rows = fi.get("data") or fi.get("data_full") or []
    best_date, best_roe = None, None
    for r in rows:
        if not isinstance(r, dict):
            continue
        dv = r.get("日期") or r.get("报告日") or r.get("截止日期")
        if not (isinstance(dv, str) and dv.replace("-", "").endswith("1231")):
            continue
        if best_date is None or dv > best_date:
            best_date = dv
            try:
                best_roe = float(r.get(roe_key))
            except (TypeError, ValueError):
                best_roe = None
    return best_roe


def _signal_direction_tally(values: dict, data: dict, fatal_events: list) -> dict:
    """Part G G-D1 —— 13 维信号方向 tally（概率判断的【参考锚】，非映射公式）。

    读 panorama values（+少数 raw snapshot 字段 peg/volume_state）定每维方向（偏多/偏空/中性/无数据）；
    fatal 风险单独标注（1 fatal > N 一般利好，由 LLM 权衡非线性权重）。阈值启发式——提供参考锚，
    LLM 仍自主判断概率，tally 绝不映射成概率分数（m6 哲学：数据是锚点，结论是权衡）。

    断空纠偏（写入前已实测 300750 真 panorama 结构）：原型 plan 脚本② 只对 synthetic flat-key demo
    验过；真 values 是嵌套结构（quality.indicators.value.加权净资产收益率），peg/volume_state 不在 values
    须读 raw data。ROE 取【最近年报】（_latest_annual_roe）作年化基准——阈值 ≥10/<5 按全年盈利能力标定，
    最新期常为 Q1/H1 YTD（600036 招行 2026Q1=3.37 vs 2025年报=13.44；300750 年报 ROE 亦 ≥10 偏多）；
    无年报退回最新期值，m6 解读提示警示非年化。
    """
    from collections import Counter

    def _num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    def dim(name, val, bull_fn, bear_fn):
        if val is None:
            return (name, "无数据")
        if bull_fn(val):
            return (name, "偏多")
        if bear_fn(val):
            return (name, "偏空")
        return (name, "中性")

    # ①财务质量：ROE 优先取【最近年报】（阈值 ≥10/<5 按全年盈利能力标定；最新期常为 Q1/H1 YTD，
    # 如 600036 招行 2026Q1=3.37 而 2025年报=13.44 → 用 YTD 套年化阈值误判偏空）。无年报退回最新期值。
    ind = _snapshot_get(values, "quality.indicators.value") or {}
    du = _snapshot_get(values, "quality.dupont.value") or {}
    roe_latest = _num(ind.get("加权净资产收益率(%)") or du.get("净资产收益率"))
    roe = _latest_annual_roe(data) or roe_latest
    # ②成长性：营收增速（peer target_metrics.rev_yoy）
    rev_yoy = _num(_snapshot_get(values, "peer.target_metrics.rev_yoy"))
    # ③估值：PEG（computed_metrics.peg_forward，raw 不在 values）
    peg = _num(_snapshot_get(data, "computed_metrics.peg_forward.value"))
    # ④资产安全：cash_to_debt
    cash_to_debt = _num(_snapshot_get(values, "asset_safety.cash_to_debt"))
    # ⑤技术资金筹码：量价（raw s4_technical）——量价须结合价位，恒中性
    volume_state = _snapshot_get(data, "s4_technical.data.volume_price.volume_state")
    # ⑥前瞻预期：consensus 近年净利增速（annual_near.netProfitYoy；空→无数据，诚实）
    consensus_growth = _num(_snapshot_get(values, "outlook.annual_near.netProfitYoy"))
    # ⑦龙虎榜：signal_type（never_listed/event_only → 非 L1/L2/L3 → 中性）
    lhb_signal = _snapshot_get(values, "lhb.signal_type")
    # ⑧北向：持股比例
    north_holding = _num(_snapshot_get(values, "northbound.holding_ratio_latest"))
    # ⑨主营构成：产品 top1 占比（有数据即偏多）
    seg_top1 = _snapshot_get(values, "segment.产品.top1_ratio")
    # ⑩同业对比：target ROE 在 target+peers 中的排名
    tm_roe = _num(_snapshot_get(values, "peer.target_metrics.roe"))
    peer_items = _snapshot_get(values, "peer.items") or []
    peer_roes = [_num(_snapshot_get(it, "metrics.roe")) for it in peer_items if isinstance(it, dict)]
    peer_roes = [r for r in peer_roes if r is not None]
    if tm_roe is not None and peer_roes:
        peer_roe_rank = sorted([tm_roe] + peer_roes, reverse=True).index(tm_roe) + 1
    else:
        peer_roe_rank = None
    # ⑪⑫⑬ G-D2 定性锚
    rd_intensity = _snapshot_get(values, "rd_intensity")
    pledge_pct = _num(_snapshot_get(values, "pledge_pct"))
    seg_growth_dim = _snapshot_get(values, "seg_growth_dim")

    out = [
        dim("财务质量", roe, lambda x: x >= 10, lambda x: x < 5),
        dim("成长性", rev_yoy, lambda x: x > 20, lambda x: x < 0),
        dim("估值", peg, lambda x: 0 < x < 1, lambda x: x > 2),
        dim("资产安全", cash_to_debt, lambda x: x > 1.5, lambda x: x < 0.8),
        dim("技术资金筹码", volume_state, lambda x: False, lambda x: False),  # 量价须结合价位，恒中性
        dim("前瞻预期", consensus_growth, lambda x: x > 20, lambda x: x < 0),
        dim("龙虎榜资金", lhb_signal, lambda x: x in ("L1",), lambda x: x in ("L2", "L3")),
        dim("北向资金", north_holding, lambda x: x > 10, lambda x: x < 0.5),
        dim("主营构成", seg_top1, lambda x: x is not None, lambda x: False),
        dim("同业对比", peer_roe_rank, lambda x: x == 1, lambda x: x > 3),
        dim("护城河", rd_intensity, lambda x: x is not None, lambda x: False),
        dim("治理战略", pledge_pct, lambda x: x is not None and x < 5, lambda x: x is not None and x > 30),
        dim("前瞻催化", seg_growth_dim, lambda x: x is not None, lambda x: False),
    ]
    cnt = Counter(d for _, d in out)
    # 致命风险 = timeline.fatal_events（公告型：330非标/360破产/430风险警示/ST/退市/重大违法）
    # ＋ tariff_vulnerability.level=="fatal"（m7 自有关税致命，非公告派生，保留不退役）
    _tariff_fatal = _snapshot_get(data, "computed_metrics.tariff_vulnerability.level") == "fatal"
    fatal = bool(fatal_events) or _tariff_fatal
    bull, neutral, bear, no_data = (cnt.get("偏多", 0), cnt.get("中性", 0),
                                    cnt.get("偏空", 0), cnt.get("无数据", 0))
    advisory = f"{bull}偏多/{neutral}中性/{bear}偏空"
    if no_data:
        advisory += f"/{no_data}无数据"
    if fatal:
        advisory += "；⚠️存在致命风险→压低乐观权重"
    return {"per_dim": out, "bull": bull, "neutral": neutral, "bear": bear,
            "no_data": no_data, "fatal_risk": fatal, "advisory": advisory}


def panorama(data: dict) -> dict:
    """读 snapshot → 证据全景结构（只抽值，不映射概率/方向）。
    模式感知（B v2）：snapshot.mode=="B" 时定性维度换短期叙事清单（共振/大盘/量价），
    量化维度照抽（B 缺 s1/s5 场景自然落 gap，gap 不 gate）。"""
    _is_b = isinstance(data, dict) and data.get("mode") == "B"
    _themes = QUAL_THEMES_B if _is_b else QUAL_THEMES
    out = {
        "present_quant": [], "gap_quant": [],
        "failed_quant": [], "disclose_quant": [],
        "qual_required": [t for t, _ in _themes],
        "values": {}, "interpretation_flags": [], "draft_lines": [],
        "present_signals": [],
        "stock_type": _snapshot_get(data, "classification.primary_type") or _snapshot_get(data, "stock_type"),
    }
    if _is_b:
        out["mode"] = "B"   # 消费方可读（m6 B 收口叙事锚）

    for theme, paths, _ in QUANT_THEMES:
        probes = [(p, _snapshot_get(data, p)) for p in paths]
        if any(_scene_bucket(v) == "present" for _, v in probes):
            out["present_quant"].append(theme)
            continue
        out["gap_quant"].append(theme)
        # 披露义务集（P1b 三桶）：failed 或 degraded/missing 信封——到场未出货≠静默豁免
        for p, v in probes:
            st = _envelope_status(v)
            if _scene_bucket(v) == "failed" or st in ("degraded", "missing"):
                out["disclose_quant"].append({"theme": theme, "path": p, "status": st or "failed"})
        if any(_scene_bucket(v) == "failed" for _, v in probes):
            out["failed_quant"].append(theme)

    # ---- 抽关键值 + 适用性/解读 flag（供 LLM 正确解读，非打分）----
    inc = _snapshot_get(data, "s1_financial.data.income_statement")
    r0 = (_rows(inc)[0] if _rows(inc) else {}) or {}
    if r0:
        out["values"]["income"] = {
            "报告期": r0.get("报告日"),
            "营业总收入": _yi(r0.get("营业总收入")),
            "归母净利润": _yi(r0.get("归属于母公司所有者的净利润")),
            "扣非净利润": _yi(r0.get("扣非净利润")),
        }
        # 🆕 Part G G-D2 ⑪护城河锚：研发强度 = 研发费用÷营业总收入（fraction，喂 Layer1 ⑪ + tally）
        _rd = r0.get("研发费用")
        _rev = r0.get("营业总收入")
        if isinstance(_rd, (int, float)) and isinstance(_rev, (int, float)) and _rev:
            out["values"]["rd_intensity"] = _rd / _rev

    fi = _snapshot_get(data, "s1_financial.data.financial_indicators")
    # 财务质量三源 latest_period 信封（indicators/abstract/dupont，period 显式驱动 freshness）。
    # 旧 cols[0] dict-order 已废弃——改读 latest_period（runner 已 desc 排序 + 信封）。
    quality = {}
    fi_lp = (fi or {}).get("latest_period") if isinstance(fi, dict) else None
    if isinstance(fi_lp, dict) and fi_lp.get("value"):
        quality["indicators"] = fi_lp
        # 单季 ROE flag：Q1（0331）非年报，勿直接当全年盈利能力
        v = fi_lp.get("value") or {}
        roe = v.get("加权净资产收益率(%)") or v.get("净资产收益率(%)")
        if roe is not None and str(fi_lp.get("raw_date", "")).endswith("0331"):
            try:
                if float(roe) < 5:
                    out["interpretation_flags"].append(
                        f"ROE={roe}% 取自 {fi_lp.get('period_label')}（单季非年化，解读时勿直接当全年盈利能力低）")
            except (TypeError, ValueError):
                pass
    ab = _snapshot_get(data, "s1_financial.data.financial_abstract")
    ab_lp = (ab or {}).get("latest_period") if isinstance(ab, dict) else None
    if isinstance(ab_lp, dict) and ab_lp.get("value"):
        quality["abstract"] = ab_lp
    du = _snapshot_get(data, "s1_financial.data.dupont")
    du_lp = (du or {}).get("latest_period") if isinstance(du, dict) else None
    if isinstance(du_lp, dict) and du_lp.get("value"):
        quality["dupont"] = du_lp
    if quality:
        out["values"]["quality"] = quality

    # 同业对比（s11_peer：target + ≤3 peer 核心6，横截面·各股取各自最新报告期；独立 peer 模式拉取后合并）
    peer = _snapshot_get(data, "s11_peer.data") or {}
    if isinstance(peer, dict) and peer.get("status") in ("ok", "degraded", "missing"):
        out["values"]["peer"] = {
            "status": peer.get("status"),
            "target_metrics": peer.get("target_metrics"),
            "target_report_period": peer.get("target_report_period"),
            "items": peer.get("items") or [],
            "peers_count": peer.get("peers_count", 0),
            "latest_period": peer.get("latest_period"),
            # 东财同业 5 维度富字段（一等公民）
            "target_rank": peer.get("target_rank"),
            "industry_median": peer.get("industry_median"),
            "industry_count": peer.get("industry_count"),
            "market_performance": peer.get("market_performance"),
        }

    am = _snapshot_get(data, "computed_metrics.asset_safety")
    if isinstance(am, dict) and am.get("status") == "ok":
        out["values"]["asset_safety"] = {
            "level": am.get("level"), "cash_to_debt": am.get("cash_to_debt"),
            "applicable": am.get("cash_to_debt_applicable"),
            "equity_multiplier": am.get("equity_multiplier"),
            "flags": am.get("flags"),
        }
        # 类型解读 flag：高杠杆须按 stock_type 解读（金融股常态，非利空）
        try:
            if am.get("equity_multiplier") and float(am["equity_multiplier"]) > 6:
                out["interpretation_flags"].append(
                    f"权益乘数={am.get('equity_multiplier')} 偏高，须按 stock_type 解读"
                    f"（金融股高杠杆为常态，非利空）")
        except (TypeError, ValueError):
            pass

    # §2.2 主营构成三维 + 跨维派生信号（m6 Layer1「主营构成」行 + m6/m7 经 timeline 解耦）
    seg = _snapshot_get(data, "s1_financial.data.segment_composition") or {}
    if isinstance(seg, dict):
        dim_st = seg.get("dimension_status") or {}
        seg_vals = {}
        for dim, label in (("product", "产品"), ("industry", "行业"), ("geo", "地区")):
            d = dim_st.get(dim) or {}
            rows = seg.get(dim, []) or []
            seg_vals[label] = {
                "status": d.get("status"), "top1": d.get("top1_name"),
                "top1_ratio": d.get("top1_ratio"), "row_count": d.get("row_count"),
                "report_date": d.get("report_date"),
                "has_margin": any(isinstance(r, dict)
                                  and _snapshot_get(r, "gross_margin") not in (None, "", 0)
                                  for r in rows),
            }
        if seg_vals:
            out["values"]["segment"] = seg_vals
            # 缺维提示（cross_ref_hints）直达 LLM，防编造海外%
            hints = seg.get("cross_ref_hints") or []
            if hints:
                out["interpretation_flags"].append(
                    "主营构成缺维：" + " | ".join(h.get("template", "") for h in hints))
        # 🆕 Part G G-D2 ⑬前瞻催化锚：第二曲线 = 产品第 2 大占比（fraction，喂 Layer1 ⑬ + tally）
        _prod_rows = seg.get("product") if isinstance(seg, dict) else None
        if isinstance(_prod_rows, list) and len(_prod_rows) >= 2 and isinstance(_prod_rows[1], dict):
            _r2 = _prod_rows[1].get("revenue_ratio")
            if isinstance(_r2, (int, float)):
                out["values"]["seg_growth_dim"] = _r2

    ov = _snapshot_get(data, "computed_metrics.overseas") or {}
    if isinstance(ov, dict) and ov.get("status"):
        out["values"]["overseas"] = ov
        if ov.get("status") == "underivable_but_historical":
            out["interpretation_flags"].append(
                f"海外占比 {ov.get('pct')}% 为 {ov.get('as_of')} 历史值（本期停披），引用须标注「停披/历史」")

    cc = _snapshot_get(data, "computed_metrics.concentration_composite") or {}
    if isinstance(cc, dict) and cc.get("region_cr1") is not None:
        out["values"]["concentration"] = cc
        if cc.get("composite_severe"):
            out["interpretation_flags"].append(
                f"营收双集中（地区CR1={cc.get('region_cr1')}×产品CR1={cc.get('product_cr1')}）→ 单点失败风险，悲观情景须引")

    tv = _snapshot_get(data, "computed_metrics.tariff_vulnerability") or {}
    _tv_lvl = tv.get("level") if isinstance(tv, dict) else None
    if _tv_lvl and (_tv_lvl == "fatal" or str(_tv_lvl).startswith("partial")):
        out["values"]["tariff_vulnerability"] = tv
        _tv_margin = tv.get("overseas_margin")
        _margin_str = f"、海外毛利率{round(_tv_margin * 100, 1)}%" if isinstance(_tv_margin, (int, float)) else ""
        out["interpretation_flags"].append(
            f"关税脆弱性={_tv_lvl}（海外{tv.get('overseas_pct')}%{_margin_str} + 产品「{tv.get('top1_product')}」+ 行业「{tv.get('industry')}」）→ m7 §7.1 须列地缘/关税风险行 + §7.1.1 估值折让")

    # product_industry_alignment 已退役（2026-07-22）：margin/momentum 并入 classification
    # 单一真相源（dominant_business.gross_margin + industry_momentum），m2/m6/m7 改读 snapshot.classification。

    # 重大事件 = 大事提醒时间线（单一交接结构 processed.timeline）：G30#1 信号覆盖数据层 + capstone 打分素材。
    mat = _snapshot_get(data, "s5_events.data.risk_signals.processed")
    _tl = mat.get("timeline") if isinstance(mat, dict) else None
    if isinstance(_tl, dict) and _tl.get("status") == "ok" and (_tl.get("events") or _tl.get("future")):
        out["values"]["material_events"] = {
            "summary": _tl.get("summary"),
            "timeline": _tl,
            "latest_period": _tl.get("latest_period"),
        }
        # 致命事件（fatal_events：330非标/360破产/430风险警示/ST/退市/重大违法）→ 前置「⚠️关键风险信号」
        for e in (_tl.get("fatal_events") or []):
            _nd = (e.get("notice_date") or "")[:10]
            out["interpretation_flags"].append(
                f"关键风险信号·致命事件·{e.get('event_type')}（{_nd}）：{(e.get('level1_content') or '')[:40]}"
                f" → 不可投/悲观核心驱动，须高亮")
        # 🆕 ST3 股东行为综合研判（融合意图×内部人×前十大；G47 presence 数据层 + Layer1 起草素材）
        sd = mat.get("shareholder_dynamics")
        if isinstance(sd, dict) and sd.get("status") == "ok":
            out["values"]["shareholder_dynamics"] = sd
            if sd.get("summary"):
                out["interpretation_flags"].append(f"股东行为研判·{sd.get('summary')}")
        # 🆕 ST5 待执行/进行中 增减持计划（forward，cap%/窗口/执行/剩余 + provenance；G48 presence 数据层）
        # 用户核心意图：现在/未来有无增持/减持悬顶/支撑 → 前置「⚠️关键风险信号」（_CRITICAL_KW 含减持）。
        progs = mat.get("programs")
        if isinstance(progs, list) and progs:
            out["values"]["programs"] = progs
            for p in progs:
                if isinstance(p, dict) and p.get("status") in ("planned", "ongoing"):
                    _act = "、".join(p.get("actor_names") or []) or "股东"
                    out["interpretation_flags"].append(
                        f"待执行计划·{_act}{p.get('direction', '')}（{p.get('status')}）→ 决策驱动，须显眼")
                    break

    # present_signals（G30#1 信号驱动覆盖）。
    # ① S2/S7 筹码码（severity 阈值·股东户数信号族）：遍历 _SIGNAL_SOURCES。
    for path, subkey, code_map, sev_set in _SIGNAL_SOURCES:
        proc = _snapshot_get(data, path)
        if not isinstance(proc, dict):
            continue
        sigs = proc.get(subkey) or proc.get("signals") or []
        _seen = set()
        for s in sigs:
            if not isinstance(s, dict) or s.get("severity") not in sev_set:
                continue
            code = s.get("code")
            if code in _seen or code not in code_map:
                continue
            _seen.add(code)
            name, kws = code_map[code]
            hz = s.get("structured_horizon") if isinstance(s.get("structured_horizon"), dict) else None
            out["present_signals"].append(
                {"source": path, "code": code, "name": name, "kws": list(kws),
                 "structured_horizon": hz or derive_horizon(code)})
    # ② 大事提醒 timeline → M-code presence（timeline 已分桶，无 severity 过滤；severity 体系已退役）。
    # 候选 = fatal_events（致命红牌必 surface）∪ risk（risk-flavor 事件）∪ active（forward 减持计划·决策驱动）。
    # forward 减持码(320/090/100) 仅 LV1 含减持/转让 才算 M1（增持=catalyst）；directional(002/003) 仅 risk-flavor 才算 M8。
    _tl = _snapshot_get(data, "s5_events.data.risk_signals.processed.timeline")
    if isinstance(_tl, dict) and _tl.get("status") == "ok":
        _seen_m = set()
        _cands = list(_tl.get("fatal_events") or []) + list(_tl.get("risk") or []) + list(_tl.get("active") or [])
        for e in _cands:
            if not isinstance(e, dict):
                continue
            code = e.get("event_type_code")
            mcode = _TIMELINE_CODE_TO_M.get(code)
            if not mcode or mcode in _seen_m:
                continue
            if code in ("320", "090", "100") and not any(
                    w in (e.get("level1_content") or "") for w in ("减持", "转让")):
                continue
            if code in ("002", "003") and e.get("flavor") != "risk":
                continue
            if _is_phantom_m5(e):
                continue
            _seen_m.add(mcode)
            name, kws = _M_SIGNAL_KW[mcode]
            out["present_signals"].append(
                {"source": "timeline", "code": mcode, "name": name, "kws": list(kws),
                 "structured_horizon": derive_horizon(mcode)})

    vs = _snapshot_get(data, "valuation_snapshot.data") or {}
    if isinstance(vs, dict):
        tp = vs.get("targetPrice")
        ar = vs.get("analystRating")
        if isinstance(tp, dict) and tp.get("average"):
            out["values"]["targetPrice"] = tp.get("average")
        if isinstance(ar, dict) and ar.get("institutionCnt"):
            out["values"]["analystRating"] = f"买入{ar.get('buy_ratio', 0):.0f}%/机构{ar.get('institutionCnt')}家"
        # 🆕 ST2 估值分位（PE-TTM/PB 双窗口 pct_5y/pct_all + 适用性 flag）
        vp = vs.get("valuation_percentile")
        if isinstance(vp, dict) and (vp.get("pe_ttm") or vp.get("pb")):
            out["values"]["valuation_percentile"] = vp

    # 龙虎榜资金（90 天窗·编码信号范式：signals[]/aggregates/trend）
    lp = _snapshot_get(data, "lhb.data.processed")
    if isinstance(lp, dict) and lp.get("status") == "ok":
        out["values"]["lhb"] = {
            "signal_type": lp.get("signal_type"),
            "severity": lp.get("severity"),
            "summary": lp.get("summary"),
            "total_count": lp.get("total_count"),            # 90 天内上榜次数
            "recent_count_30d": lp.get("recent_count_30d"),
            "signals": lp.get("signals") or [],
            "trend": lp.get("trend"),
            "aggregates": lp.get("aggregates") or {},
            "latest_period": lp.get("latest_period"),   # 信号族 freshness 信封（period_label+sort_key+summary）
        }

    # 北向资金（1 季度·仅水平信号；change_qoq/trend_direction 1Q 恒 null，不抽）
    nb = _snapshot_get(data, "northbound.data.processed")
    if isinstance(nb, dict) and nb.get("status") == "ok":
        out["values"]["northbound"] = {
            "signal_type": nb.get("signal_type"),
            "severity": nb.get("severity"),
            "summary": nb.get("summary"),
            "data_source": nb.get("data_source"),
            "holding_ratio_latest": nb.get("holding_ratio_latest"),
            "signals": nb.get("signals") or [],
            "latest_period": nb.get("latest_period"),   # 信号族 freshness 信封（period_label+sort_key+summary）
        }

    # 股东户数（latest_period 信封——★ bug 原案：写作期须见最新值，防引旧值如"10.12万"）
    sc_lp = _snapshot_get(data, "s8_a_share.data.shareholder_count.latest_period")
    if isinstance(sc_lp, dict) and sc_lp.get("value") is not None:
        out["values"]["shareholder_count"] = sc_lp

    # 前瞻预期（company_guidance 业绩预告·forecast 一等公民 + consensus annual[最近预测年]）
    cf = _snapshot_get(data, "consensus_forecast.data") or {}
    if isinstance(cf, dict):
        outlook = {}
        cg = cf.get("company_guidance") or {}
        if isinstance(cg, dict) and isinstance(cg.get("latest_period"), dict):
            outlook["guidance"] = cg["latest_period"]
            outlook["guidance_status"] = cg.get("status")
        annual = cf.get("annual") or {}
        if isinstance(annual, dict) and annual:
            try:
                yrs = sorted(int(y) for y in annual.keys())
                asof = (cf.get("latest_period") or {}).get("as_of") or ""
                asof_y = int(asof[:4]) if asof[:4].isdigit() else yrs[0]
                near = min((y for y in yrs if y >= asof_y), default=yrs[0])  # 最近预测年
                outlook["annual_near"] = {"year": near, **(annual.get(str(near)) or {})}
            except (ValueError, TypeError):
                pass
        if outlook:
            out["values"]["outlook"] = outlook

    # 🆕 ST6 买卖力量 verdict + 公司级回购（gate 外独立读·镜像 lhb/northbound）：
    # BSP 聚合跨 scene 数据（lhb/northbound/fund_flow），独立于公告——干净票（大单流入+北向增持但零公告）
    # 在 mat.status==ok and (risk or catalyst) gate 内会变孤儿 → gate 外填（同 lhb/northbound/shareholder_count）。
    bsp = _snapshot_get(data, "s5_events.data.risk_signals.processed.buy_sell_pressure")
    if isinstance(bsp, dict) and bsp.get("status") == "ok":
        out["values"]["buy_sell_pressure"] = bsp
        if bsp.get("summary"):
            out["interpretation_flags"].append(bsp.get("summary"))   # summary 已含「买卖力量：」前缀，勿再叠
    # 🆕 Part G G-D2 ⑫治理战略锚：质押比例（bsp.sell.pledge.pledge_ratio；无质押→0=干净治理）
    _pl = _snapshot_get(bsp, "sell.pledge.pledge_ratio")
    if isinstance(_pl, (int, float)):
        out["values"]["pledge_pct"] = _pl
    elif isinstance(bsp, dict) and bsp.get("status") == "ok":
        out["values"]["pledge_pct"] = 0.0   # bsp ok 但无 pledge 子键 = 无质押（干净）
    repos = _snapshot_get(data, "s5_events.data.risk_signals.processed.repurchase_programs")
    if isinstance(repos, list) and repos:
        out["values"]["repurchase_programs"] = repos

    # 🆕 Part G G-D1：信号方向 tally（概率判断的参考锚，非映射公式；fatal 风险单独标注）。
    # fatal 取自 timeline.fatal_events（公告型 330/360/430/ST/退市/重大违法）。
    _fe = _snapshot_get(data, "s5_events.data.risk_signals.processed.timeline.fatal_events") or []
    out["tally"] = _signal_direction_tally(out["values"], data, _fe)

    # ---- 渲染证据全景草稿表（Layer1）----
    _render_draft(out, data)
    return out


def _render_income(L, v):
    if not v.get("income"):
        return
    L.append(f"- 成长性：{v['income'].get('报告期','')} 营收 {v['income'].get('营业总收入')}，"
             f"归母 {v['income'].get('归母净利润')}，扣非 {v['income'].get('扣非净利润')}。"
             f"（ROE/盈利能力见下「财务质量」行）")


def _render_asset_safety(L, v):
    if not v.get("asset_safety"):
        return
    a = v["asset_safety"]
    L.append(f"- 资产安全：cash_to_debt {a.get('cash_to_debt')}（{a.get('level')}，"
             f"applicable={a.get('applicable')}）权益乘数 {a.get('equity_multiplier')}。")


def _render_valuation(L, v):
    # ST2 估值分位（双窗口 pct_5y/pct_all + 适用性 flag）
    vp = v.get("valuation_percentile") or {}
    pct_parts = []
    for key, label in (("pe_ttm", "PE(TTM)"), ("pb", "PB")):
        seg = vp.get(key)
        if not isinstance(seg, dict):
            continue
        if seg.get("applicable") is False:
            pct_parts.append(f"{label}分位：不适用")
            continue
        p5 = seg.get("pct_5y")
        pa = seg.get("pct_all")
        note = ""
        if seg.get("history_sufficient") is False:
            note = "（次新·仅参考）"
        if isinstance(p5, (int, float)):
            line = f"{label}分位 近五年{p5:.0%}"
            if isinstance(pa, (int, float)):
                line += f"/全部{pa:.0%}"
            pct_parts.append(line + note)
    has_target = v.get("targetPrice") or v.get("analystRating")
    if not (has_target or pct_parts):
        return
    pieces = []
    if has_target:
        pieces.append(f"目标价 {v.get('targetPrice','—')}，评级 {v.get('analystRating','—')}")
    if pct_parts:
        pieces.append("；".join(pct_parts) + "（[src: valuation_snapshot.data.valuation_percentile]）")
    L.append("- 估值/前瞻：" + "；".join(pieces) + "。")


def _render_lhb(L, v):
    """龙虎榜聚合渲染（不渲 seats 明细——m7 职责，避免叙事重复）。"""
    l = v.get("lhb")
    if not l:
        return
    parts = [str(l.get("summary") or "")]
    warn_sigs = [s.get("name") for s in (l.get("signals") or [])
                 if s.get("severity") == "warning"][:2]
    if warn_sigs:
        parts.append("警示：" + "/".join(warn_sigs))
    agg = l.get("aggregates") or {}
    if agg.get("inst_buy_seats"):
        parts.append(f"机构净买入{agg['inst_buy_seats']}席")
    if agg.get("hot_money_seats"):
        parts.append(f"游资{agg['hot_money_seats']}席/净额{agg.get('hot_money_net_amount_元', 0):.0f}元")
    dist = agg.get("reason_cat_dist") or {}
    if dist:
        parts.append("席位分布：" + ",".join(f"{k}{w}" for k, w in dist.items()))
    trend = l.get("trend")
    if isinstance(trend, dict) and trend.get("direction"):
        parts.append(f"趋势={trend.get('direction')}")
    lp_env = l.get("latest_period") or {}
    stale = _stale_marker(lp_env, 90)
    pl = f"（{lp_env.get('period_label')}）" if lp_env.get("period_label") else ""
    L.append(f"- 龙虎榜资金（90天窗）{pl}：{'；'.join(parts)}（signal={l.get('signal_type')}，"
             f"90天内{l.get('total_count')}次/近30天{l.get('recent_count_30d')}次）{stale}。")


def _render_northbound(L, v):
    """北向资金水平渲染（1 季度，无加仓/减仓动作）。"""
    n = v.get("northbound")
    if not n:
        return
    ds_label = {"westock": "westock季度持仓", "top10_deal": "TOP10成交活跃度",
                "none": "—"}.get(n.get("data_source"), n.get("data_source"))
    ratio = n.get("holding_ratio_latest")
    ratio_txt = f"{ratio:.2f}%" if ratio is not None else "—"
    sigs = [s.get("name") for s in (n.get("signals") or [])][:2]
    lp_env = n.get("latest_period") or {}
    stale = _stale_marker(lp_env, 120)
    pl = f"（{lp_env.get('period_label')}）" if lp_env.get("period_label") else ""
    L.append(f"- 北向资金（1季度·仅水平，无加仓减仓）{pl}：{n.get('summary')}（源={ds_label}，"
             f"持股{ratio_txt}，signal={n.get('signal_type')}，信号={'/'.join(sigs) if sigs else '—'}）{stale}。")


def _render_buy_sell_pressure(L, v):
    """ST6 买卖力量 verdict 渲染（Option 2.5 反双渲染：只吐 verdict + rollup 量级 + 回购新数字一行）。

    明确禁止重述 insider/top10 具名持有人、lhb 席位、北向 ratio——那些仍由 _render_shareholder_behavior/
    _render_lhb/_render_northbound 单渲染。此处只汇总阵营对决结论 + 各分量量级（net_pct/已执行额/计数）。
    """
    b = v.get("buy_sell_pressure")
    if not b:
        return
    verdict = b.get("verdict")
    buy, sell = b.get("buy") or {}, b.get("sell") or {}
    parts = []
    # 买方 rollup
    rp = buy.get("repurchase") or {}
    if rp.get("active_count"):
        seg = f"在途回购{rp['active_count']}项"
        if rp.get("executed_amount_yi"):
            seg += f"/已执行{rp['executed_amount_yi']:.2f}亿"
        if rp.get("progress_avg_pct") is not None:
            seg += f"(进度{rp['progress_avg_pct']:.0%})"
        if rp.get("cancel_type_count"):
            seg += "(注销型)"
        parts.append(("买", seg))
    ff = buy.get("fund_flow")
    if ff:
        parts.append(("买", f"大单净流入{ff.get('main_net_yi'):.1f}亿"))
    ib = buy.get("insider_buy") or {}
    if ib.get("controlling_365d_net_shares") or ib.get("insider_365d_net_shares"):
        parts.append(("买", "内部人增持" + ("(含控股股东)" if ib.get("controlling_365d_net_shares") else "")))
    # 卖方 rollup
    isl = sell.get("insider_sell") or {}
    if isl.get("forward_reduction_count"):
        seg = f"减持悬顶{isl['forward_reduction_count']}项"
        if isl.get("forward_overhang_cap_pct") is not None:
            seg += f"(上限{isl['forward_overhang_cap_pct']:.2%})"
        parts.append(("卖", seg))
    elif isl.get("controlling_365d_net_shares") or isl.get("insider_365d_net_shares"):
        parts.append(("卖", "减持" + ("(控股股东)" if isl.get("controlling_365d_net_shares") else "")))
    un = sell.get("unlock")
    if un:
        parts.append(("卖", f"解禁{un.get('upcoming_count')}笔"))
    pg = sell.get("pledge")
    if pg:
        d = pg.get("distance_pct")
        near = "（邻近强平）" if (d is not None and d < 1.2) else ""
        parts.append(("卖", f"质押比例{pg.get('pledge_ratio')}{near}"))
    ffo = sell.get("fund_flow_out")
    if ffo:
        parts.append(("卖", f"大单净流出{abs(ffo.get('main_net_yi')):.1f}亿"))
    _buy_txt = "、".join(s for side, s in parts if side == "买")
    _sell_txt = "、".join(s for side, s in parts if side == "卖")
    if not _buy_txt and not _sell_txt:
        L.append(f"- 买卖力量：近一季无材料级买卖力量异动（verdict={verdict}）。")
        return
    corr = b.get("corroboration") or {}
    corr_txt = ""
    if corr.get("multi_source_buy") or corr.get("multi_source_sell"):
        corr_txt = f"（多源共振：买{corr.get('buy_source_count')}源/卖{corr.get('sell_source_count')}源）"
    duel = f"买方({_buy_txt}) vs 卖方({_sell_txt})" if (_buy_txt and _sell_txt) \
        else (f"买方({_buy_txt})" if _buy_txt else f"卖方({_sell_txt})")
    L.append(f"- 买卖力量：{duel} → **{verdict}**{corr_txt}。")


def _render_material_events(L, v):
    """重大事件 = 大事提醒时间线（risk/catalyst/fatal/active 投影）——G30#1 信号覆盖数据层 + capstone 打分素材。

    风险事件投影到 M-code name（presence 词与 present_signals 一致，G30#1 覆盖闭环）；
    致命事件计入「致命N（不可投）」并经 interpretation_flags 前置「⚠️关键风险信号」段。
    """
    m = v.get("material_events")
    if not m:
        return
    tl = m.get("timeline") or {}
    # 风险 M-code（risk ∪ active-forward减持 ∪ fatal），保留首次出现顺序
    risk_mcodes = []
    def _add_mc(e):
        code = e.get("event_type_code")
        if code in ("320", "090", "100") and not any(
                w in (e.get("level1_content") or "") for w in ("减持", "转让")):
            return
        if code in ("002", "003") and e.get("flavor") != "risk":
            return
        if _is_phantom_m5(e):
            return
        mc = _TIMELINE_CODE_TO_M.get(code)
        if mc and mc not in risk_mcodes:
            risk_mcodes.append(mc)
    for e in (tl.get("risk") or []):
        _add_mc(e)
    for e in (tl.get("active") or []):
        _add_mc(e)
    for e in (tl.get("fatal_events") or []):
        _add_mc(e)
    fatal_ev = tl.get("fatal_events") or []
    parts = []
    if risk_mcodes:
        names = [_M_SIGNAL_KW[mc][0] for mc in risk_mcodes if mc in _M_SIGNAL_KW]
        fatal_txt = f"，致命{len(fatal_ev)}（不可投）" if fatal_ev else ""
        parts.append(f"风险{len(risk_mcodes)}类：{'、'.join(names)}{fatal_txt}")
    cat = tl.get("catalyst") or []
    if cat:
        cat_names = []
        for e in cat:
            nm = (e.get("event_type") or "").strip()
            if nm and nm not in cat_names:
                cat_names.append(nm)
        if cat_names:
            parts.append(f"利好{len(cat)}类：{'、'.join(cat_names[:4])}")
    if parts:
        L.append("- 重大事件：" + "；".join(parts) + "。（悲观读风险、乐观读利好）")


def _render_shareholder_count(L, v):
    """股东户数（latest_period 信封）——★ bug 原案：写作期直见最新值+环比，防引旧值如"10.12万"。"""
    lp = v.get("shareholder_count")
    if not lp:
        return
    val = lp.get("value")
    try:
        val_txt = f"{int(val):,} 户"
    except (TypeError, ValueError):
        val_txt = f"{val} 户"
    chg = lp.get("change_pct")
    chg_txt = f"（环比{chg:+.1f}%）" if isinstance(chg, (int, float)) else ""
    summ = (lp.get("summary") or "").strip()
    L.append(f"- 股东户数（最新期 {lp.get('period_label','')}）：{val_txt}{chg_txt}。{summ}".rstrip())


def _render_shareholder_behavior(L, v):
    """🆕 ST3+ST5 股东行为研判：待执行/进行中增减持计划 FIRST（决策驱动）+ 已完成融合（内部人×前十大）。

    待执行段（forward）：programs[] status∈{planned,ongoing} → cap%/窗口/已执行%/剩余%，每字段按
      provenance(REAL/MISSING) 诚实降级（缺→「需查正文」，绝不编造）。用户核心意图：现在/未来有无
      增持/减持悬顶/支撑，决定操作。已完成段：shareholder_dynamics（insiders/top10 占总股本%）。
    所有 `:.2%` 前均 None guard（早调/缺 total_shares → pct=None，f-string 会崩）。
    """
    src_sd = "[src: snapshot.s5_events.data.risk_signals.processed.shareholder_dynamics]"
    src_pg = "[src: snapshot.s5_events.data.risk_signals.processed.programs]"

    # ---- 待执行/进行中 FIRST（forward 计划，决策驱动；每数字带 provenance 诚实降级）----
    progs = v.get("programs")
    if isinstance(progs, list):
        for p in progs:
            if not isinstance(p, dict) or p.get("status") not in ("planned", "ongoing"):
                continue
            d = p.get("direction") or "增减持"
            tier = p.get("tier") or "股东"
            actors = "、".join(p.get("actor_names") or []) or "未具名"
            st = {"planned": "待执行", "ongoing": "进行中"}.get(p.get("status"), p.get("status"))
            prov = p.get("provenance") or {}
            seg = [f"{actors}{d}（{tier}，{st}）"]
            cap = p.get("announced_pct_cap")
            if cap is not None:
                seg.append(f"拟{d}不超{cap:.2%}总股本")
            elif prov.get("cap") == "MISSING":
                seg.append(f"拟{d}比例需查公告正文")
            ws, we = p.get("window_start"), p.get("window_end")
            if ws and we:
                seg.append(f"窗口{ws}~{we}")
            ep = p.get("executed_pct")
            if ep is not None:
                seg.append(f"已执行{ep:.2%}")
            rp = p.get("remaining_pct")
            if rp is not None:
                seg.append(f"剩余{rp:.2%}")
            elif cap is not None and ep is None:
                seg.append("已执行数需查正文")
            L.append(f"- ⏳待执行计划：{'；'.join(seg)}。 {src_pg}".rstrip())

    # ---- 近期已完成（completed，≤1yr；直接写结果：谁×方向×%，窗口，已执行完毕）----
    for p in (progs or []):
        if not isinstance(p, dict) or p.get("status") != "completed":
            continue
        d = p.get("direction") or "增减持"
        tier = p.get("tier") or "股东"
        actors = "、".join(p.get("actor_names") or []) or "未具名"
        seg = [f"{actors}{d}（{tier}）"]
        ep = p.get("executed_pct")
        cap = p.get("announced_pct_cap")
        if ep is not None:
            seg.append(f"实际{d}{ep:.2%}总股本")
        elif cap is not None:
            seg.append(f"计划不超{cap:.2%}总股本")
        we = p.get("window_end")
        wsrc = p.get("window_source")
        if we:
            tag = "" if wsrc == "REAL" else "（反算）"
            seg.append(f"窗口截至{we}{tag}")
        seg.append("已执行完毕，影响已释放")
        L.append(f"- ✅近期已完成：{'；'.join(seg)}。 {src_pg}".rstrip())

    # ---- 已完成融合（backward，内部人×前十大，占总股本%）----
    sd = v.get("shareholder_dynamics")
    if not isinstance(sd, dict) or not sd.get("verdict"):
        return
    verdict = sd.get("verdict")
    summary = (sd.get("summary") or "").strip()
    parts = [f"verdict={verdict}"]
    by = sd.get("by_source") or {}
    ins = by.get("insiders") or {}
    if isinstance(ins, dict) and (ins.get("trades") or ins.get("net_shares")):
        _s = f"内部人{ins.get('trades', 0)}笔"
        _np = ins.get("net_pct")
        if _np is not None:
            _s += f"({ins.get('net_direction', '')}{_np:.2%}总股本)"
        _gc = ins.get("grant_count")
        if _gc:
            _s += f"，{_gc}笔疑股权激励授予"
        parts.append(_s)
    top10 = by.get("top10") or {}
    if isinstance(top10, dict):
        named = top10.get("named") or []
        if isinstance(named, list) and named:
            _ns = []
            for n in named[:3]:
                if not isinstance(n, dict):
                    continue
                _t = f"{n.get('name', '')}{'增持' if (n.get('direction') or '').startswith('增') else '减持'}"
                _dp = n.get("delta_pct")
                if _dp is not None:
                    _t += f"{_dp:.2%}"
                _ns.append(_t)
            if _ns:
                parts.append(f"前十大[{'、'.join(_ns)}，资金面]")
    # ---- ST7 前十大流通股东季度信封（一行：季度+净/加权净+tone+强资金）----
    t10q = by.get("top10_quarterly") or {}
    t10q_periods = t10q.get("periods") if isinstance(t10q, dict) else None
    if isinstance(t10q_periods, list) and t10q_periods and isinstance(t10q_periods[0], dict):
        q0 = t10q_periods[0]
        if q0.get("quarter") and (q0.get("tone") or q0.get("weighted_net") is not None):
            def _qm(s):
                return ("%.1f万" % (s / 10000.0)) if isinstance(s, (int, float)) and abs(s) >= 1 else ("%.0f股" % (s or 0))
            _seg = [q0.get("quarter")]
            _ns = q0.get("net_shares")
            _wn = q0.get("weighted_net")
            if _ns is not None:
                _seg.append("净%s%s" % ("+" if _ns >= 0 else "", _qm(_ns)))
            if _wn is not None:
                _seg.append("加权%s%s" % ("+" if _wn >= 0 else "", _qm(_wn)))
            if q0.get("tone"):
                _seg.append("→ %s" % q0.get("tone"))
            sin, sout = q0.get("strong_in"), q0.get("strong_out")
            if sin is not None and sout is not None:
                _seg.append("强资金 进%s/出%s" % (sin, sout))
            src_t10q = "[src: snapshot.s5_events.data.risk_signals.processed.shareholder_dynamics.by_source.top10_quarterly]"
            L.append(("- 前十大流通股东季度：%s。 %s" % ("；".join(_seg), src_t10q)).rstrip())
    corr = sd.get("corroboration") or {}
    if isinstance(corr, dict):
        if corr.get("double_bearish"):
            parts.append("内部人∧前十大共振减持(最强看空)")
        elif corr.get("double_bullish"):
            parts.append("内部人∧前十大共振增持(最强看多)")
    vi = sd.get("vs_intent") or {}
    if isinstance(vi, dict) and vi.get("intent_executed") is not None:
        parts.append("言行合一" if vi.get("intent_executed") else "公告未执行")
    lp_env = sd.get("latest_period") or {}
    pl = f"（最新{lp_env.get('period_label')}）" if lp_env.get("period_label") else ""
    summ = f" {summary}" if summary else ""
    L.append(f"- 已完成股东行为{pl}：{'；'.join(parts)}。{summ} {src_sd}".rstrip())


def _render_outlook(L, v):
    """前瞻预期：company_guidance（业绩预告·forecast 一等公民）+ consensus annual[最近预测年]。

    company_guidance stale（is_forward_looking=False / 覆盖期已实际化）→ 标「无前瞻增量，参考实际财报」，
    防 LLM 把过期预告当 forward earnings 锚（plan §2.4.5）。
    """
    o = v.get("outlook")
    if not o:
        return
    parts = []
    g = o.get("guidance")
    if isinstance(g, dict):
        stale = ""
        if o.get("guidance_status") == "stale" or g.get("is_forward_looking") is False:
            stale = " ⚠️最近预告覆盖期已实际化，无前瞻增量，引用须参考实际财报"
        parts.append(f"业绩预告（{g.get('period_label','')}）：{g.get('summary','')}{stale}")
    an = o.get("annual_near")
    if isinstance(an, dict) and an.get("eps") is not None:
        parts.append(f"一致预期{an.get('year')}：EPS {an.get('eps')}，净利 {an.get('netProfit')}亿(同比{an.get('netProfitYoy')}%)")
    if parts:
        L.append("- 前瞻预期：" + "；".join(parts) + "。")


def _render_segment(L, v):
    """主营构成三维（产品/行业/地区 top1 + 占比）——G30#1 反片面硬维度 + G34/35/36 数据层。

    数据已在 panorama values['segment']（dimension_status.<dim>.top1_name，runner 已算好 max）。
    三维对称渲染，让 LLM 写作期直见集中度，不必回翻 snapshot segment_composition。
    """
    seg = v.get("segment")
    if not seg:
        return
    parts = []
    for dim in ("产品", "行业", "地区"):
        d = seg.get(dim) or {}
        if not d.get("top1"):
            continue
        ratio = d.get("top1_ratio")
        ratio_txt = f"({ratio*100:.1f}%)" if isinstance(ratio, (int, float)) else ""
        parts.append(f"{dim}top1={d['top1']}{ratio_txt}")
    if parts:
        rd = (seg.get("产品") or {}).get("report_date") or ""
        L.append(f"- 主营构成{f'（{rd}）' if rd else ''}：" + "；".join(parts) + "。")


def _q_caveat(raw_date) -> str:
    """季末日期（0331/0630/0930）→ 单季·未年化提示；年报(1231)无提示。"""
    s = str(raw_date or "").replace("-", "")
    return "（单季·未年化）" if len(s) >= 8 and s[4:8] in ("0331", "0630", "0930") else ""


def _render_quality(L, v):
    """财务质量（ROE/净利率/杜邦三因子）——G30#1 反片面硬维度·财务质量。

    三源 latest_period 信封各带期次（indicators 加权ROE+周转 / abstract 毛利率+净利率 /
    dupont 三因子分解）。Q1/中报/三季 ROE 标「单季·未年化」（防 LLM 把单季 ROE 当全年盈利能力）。
    """
    q = v.get("quality")
    if not q:
        return
    ind = q.get("indicators")
    if ind:
        iv = ind.get("value") or {}
        roe = iv.get("加权净资产收益率(%)") or iv.get("净资产收益率(%)")
        to = iv.get("总资产周转率(次)")
        parts = []
        if roe is not None:
            parts.append(f"加权ROE {roe}%")
        if to is not None:
            parts.append(f"总资产周转 {to}次")
        if parts:
            L.append(f"- 财务质量（{ind.get('period_label')}）{_q_caveat(ind.get('raw_date'))}："
                     + "，".join(parts) + "。")
    du = q.get("dupont")
    if du:
        dv = du.get("value") or {}
        roe, npm, to, em = (dv.get("净资产收益率"), dv.get("销售净利率"),
                            dv.get("资产周转率(次)"), dv.get("权益乘数"))
        if roe is not None:
            decomp = "×".join(x for x in (
                f"净利率{npm}%" if npm is not None else None,
                f"周转{to}" if to is not None else None,
                f"权益乘数{em}" if em is not None else None) if x)
            L.append(f"  杜邦分解（{du.get('period_label')}）：ROE {roe}%"
                     + (f" = {decomp}" if decomp else "") + "。")
    ab = q.get("abstract")
    if ab:
        av = ab.get("value") or {}
        parts = [f"毛利率 {av['毛利率']}%" for k in ("毛利率",) if av.get(k) is not None]
        if av.get("销售净利率") is not None:
            parts.append(f"净利率 {av['销售净利率']}%")
        if parts:
            L.append(f"  盈利能力（{ab.get('period_label')}）{_q_caveat(ab.get('raw_date'))}："
                     + "，".join(parts) + "。")


def _render_peer(L, v):
    """同业对比（s11_peer：东财 F10 行业自动，target + 同业核心6）——G30#1 反片面硬维度。

    em 路径恒 ok/degraded（东财 5 维度 + sina 毛利率补全）；status/peers_count/target_report_period
    取自 s11_peer 信封。富字段 target_rank/industry_median/market_performance 为东财同业一等公民。
    """
    p = v.get("peer")
    if not p:
        return
    st = p.get("status")
    rp = p.get("target_report_period")
    L.append(f"- 同业对比（status={st}，{p.get('peers_count', 0)} 家）{f'（{rp}）' if rp else ''}：")
    # 东财 F10 同业 5 维度一等公民（target_rank/industry_median/market_performance）。
    rank = p.get("target_rank") or {}
    med = p.get("industry_median") or {}
    ic = p.get("industry_count")
    if rank or med:
        rank_parts = []
        for k, lbl in (("dupont", "ROE"), ("growth", "成长"), ("valuation", "估值")):
            r = rank.get(k)
            if r is not None:
                rank_parts.append(f"{lbl}第{r}/{ic}" if ic else f"{lbl}第{r}")
        med_parts = []
        for k, lbl in (("pe", "PE中值"), ("pb", "PB中值"), ("roe", "ROE中值")):
            mv = med.get(k)
            if mv is not None:
                try:
                    med_parts.append(f"{lbl} {float(mv):.2f}{'%' if k == 'roe' else ''}")
                except (TypeError, ValueError):
                    med_parts.append(f"{lbl} {mv}")
        _pos = ""
        if rank_parts:
            _pos = "行业排名：" + "｜".join(rank_parts)
        if med_parts:
            _pos += ("；行业基准：" if _pos else "行业基准：") + "｜".join(med_parts)
        if _pos:
            L.append(f"  ⭐ 行业位置（东财同业，样本{ic or '?'}家）：{_pos}。")
    mp = p.get("market_performance") or {}
    mp_wins = mp.get("windows") or {}
    if mp_wins:
        board = mp.get("board_name") or "板块"
        _mparts = []
        for _lbl in ("近1月", "近3月", "近6月", "YTD"):
            w = mp_wins.get(_lbl) or {}
            ch, hs = w.get("change"), w.get("hs300")
            if ch is not None and hs is not None:
                try:
                    _exc = float(ch) - float(hs)
                    _mparts.append(f"{_lbl} 个股{float(ch):+.1f}%/沪深300{float(hs):+.1f}%("
                                   f"{'跑赢' if _exc > 0 else '跑输'}{abs(_exc):.1f}pct)")
                except (TypeError, ValueError):
                    pass
        if _mparts:
            L.append(f"  📈 市场表现（vs 沪深300，{board}）：{'；'.join(_mparts)}。")
    for it in [{"name": "目标", "metrics": p.get("target_metrics")}] + list(p.get("items") or []):
        m = it.get("metrics") or {}
        if not m:
            continue
        parts = []
        for k, lbl in (("pe", "PE"), ("pb", "PB"), ("roe", "ROE"),
                       ("rev_yoy", "营收增速"), ("np_yoy", "净利增速"), ("gross_margin", "毛利率")):
            val = m.get(k)
            if val is not None:
                parts.append(f"{lbl} {val}{'%' if k in ('roe','rev_yoy','np_yoy','gross_margin') else ''}")
        if parts:
            name = it.get("name") or it.get("code")
            L.append(f"  - {name}：" + "｜".join(parts) + "。")


# 证据全景草稿渲染器注册表（决策D：新增主题=加一项，不动 _render_draft）
THEME_RENDERERS = {
    "income": _render_income,
    "quality": _render_quality,
    "material_events": _render_material_events,
    "shareholder_count": _render_shareholder_count,
    "shareholder_behavior": _render_shareholder_behavior,
    "asset_safety": _render_asset_safety,
    "valuation": _render_valuation,
    "segment": _render_segment,
    "peer": _render_peer,
    "outlook": _render_outlook,
    "lhb": _render_lhb,
    "northbound": _render_northbound,
    "buy_sell_pressure": _render_buy_sell_pressure,
}


def _render_draft(out: dict, data: dict) -> None:
    """生成 Layer1 证据全景草稿 markdown 行（通用化：遍历 THEME_RENDERERS，新增主题=加 dict 项）。"""
    L = out["draft_lines"]
    # 关键风险信号前置（plan §4.1 改动D）：关税/集中度/派发/停披等决策信号不被量化数据淹没，
    # 单列「⚠️ 关键风险信号」子节置首（证据全景 heading 仍存，G30 #1 定位不受影响）。
    _CRITICAL_KW = ("关税", "集中度", "双集中", "致命", "fatal", "派发", "过热", "停披", "stale",
                    "关键风险信号", "减持", "违规", "处罚", "退市", "ST", "计损", "减值", "预减", "预亏")
    critical = [f for f in out["interpretation_flags"] if any(k in f for k in _CRITICAL_KW)]
    normal = [f for f in out["interpretation_flags"] if f not in critical]
    if critical:
        L.append("#### ⚠️ 关键风险信号（写作期须显眼，直接影响悲观情景与仓位裁决）")
        for f in critical:
            L.append(f"- ⚠️ {f}")
    L.append("#### 证据全景（helper 抽值草稿——只列值与 gap，方向/权重由你判断）")
    v = out["values"]
    for _theme, renderer in THEME_RENDERERS.items():
        renderer(L, v)
    if out["gap_quant"]:
        L.append(f"- ⚠️ 数据 gap（m8 须披露；反片面 gate 豁免）：{out['gap_quant']} 无 snapshot 数据。")
    if out.get("disclose_quant"):
        ds = "、".join(f"{d['theme']}[{d['status']}]" for d in out["disclose_quant"])
        L.append(f"- ⚠️ 到场未出货/拉取失败（G30#1 披露义务，各维须一行〈维度名+降级/缺失/失败〉，"
                 f"照抄 002202 §4.0 维表形态）：{ds}。")
    # 🆕 Part G G-D2：定性锚点（helper 抽值，Layer1 ⑪⑫⑬ 行挂 🔒锚点用）
    _rd, _pl, _sg = v.get("rd_intensity"), v.get("pledge_pct"), v.get("seg_growth_dim")
    _anchors = []
    if isinstance(_rd, (int, float)):
        _anchors.append(f"研发强度{_rd:.1%}（护城河⑪锚）")
    if isinstance(_pl, (int, float)):
        _anchors.append(f"质押{_pl:.2f}%（治理⑫锚）")
    if isinstance(_sg, (int, float)):
        _anchors.append(f"第二曲线占比{_sg:.1%}（前瞻催化⑬锚）")
    if _anchors:
        L.append("- 定性锚点（helper 抽值，Layer1 ⑪⑫⑬ 行挂 🔒 结构化锚点）："
                 + "；".join(_anchors) + "。定性补充须显式标「无源」。")
    L.append("- 定性（你须从 m1–m9 叙事提炼，机械模型丢失的关键）：护城河 / 治理战略 / 前瞻催化。")
    # 🆕 Part G G-D1：信号方向 tally（参考锚，非映射公式；Layer1 末尾一行收口）
    _tally = out.get("tally")
    if isinstance(_tally, dict) and _tally.get("advisory"):
        L.append(f"- 📊 信号方向 tally（13 维参考锚，非概率映射）：{_tally['advisory']}。"
                 "tally 是参考——致命风险非线性压低乐观权重，LLM 仍自主判断概率。")
    for f in normal:
        L.append(f"- 🔎 解读提示：{f}")


# ============================================================
# #7 软一致性提示（写作期，不计入 gate verdict）
# ============================================================

def panorama_advisory(report: str, data: dict) -> list:
    """#7：自列证据明显倾向 X、裁决却 Y → 仅标记请复核。engine 无 warning 通道，故为写作期建议。"""
    adv = []
    if not report:
        return adv
    # 定位综合研判章节
    cap = _find_capstone(report)
    bull = sum(cap.count(w) for w in ["拐点", "增长", "突破", "景气", "放量", "超预期", "龙头", "壁垒"])
    bear = sum(cap.count(w) for w in ["下滑", "下降", "萎缩", "亏损", "紧张", "高估", "跌破", "疲软"])
    top = _top_scenario(cap)
    if top:
        top_label, top_p = top
        if bull - bear >= 6 and "悲观" in top_label:
            adv.append(f"#7[软] 证据明显偏多(看多词{bull}>>看空词{bear}) 但最高概率情景={top_label}({top_p}%)，"
                       f"请明示偏谨慎裁决的理由（如估值已贵/前瞻催化不确定）。")
        elif bear - bull >= 6 and "乐观" in top_label:
            adv.append(f"#7[软] 证据明显偏空(看空词{bear}>>看多词{bull}) 但最高概率情景={top_label}({top_p}%)，"
                       f"请明示偏乐观裁决的理由。")
    return adv


def _find_capstone(report: str) -> str:
    """capstone 定位（#7 advisory 用）。统一走 section_locator（单一实现；
    旧副本正则取首+切到文末，劫持面更大）。"""
    from section_locator import locate
    return locate(report)[0]


def _top_scenario(cap: str):
    """最高概率情景 (label, prob)。共享 gate_definitions._g30_find_scenarios（表优先，
    与 G30#3 同源），消除孪生内联正则漂移。lazy import：gate_definitions 模块级已反向
    import capstone_panorama，此处模块级 import 会循环。"""
    from gate_definitions import _g30_find_scenarios
    scens = _g30_find_scenarios(cap)
    return max(((lbl, p) for lbl, p, _ in scens), key=lambda x: x[1], default=None)


# ============================================================
# CLI
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="综合研判 capstone 证据全景 helper（写作期工具）")
    ap.add_argument("--snapshot", required=True, help="snapshot.json 路径")
    ap.add_argument("--report", help="报告 .md（提供则额外给 #7 软提示）")
    args = ap.parse_args()

    data = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    pan = panorama(data)
    print("\n".join(pan["draft_lines"]))
    print(f"\n[present 维度须全覆盖: {pan['present_quant']}; gap 已豁免: {pan['gap_quant']}; "
          f"披露义务: {[(d['theme'], d['status']) for d in pan.get('disclose_quant', [])] or '无'}; "
          f"定性须覆盖: {pan['qual_required']}]")
    _tl = pan.get("tally")
    if isinstance(_tl, dict):
        print(f"\n[信号方向 tally：{_tl.get('advisory')} | fatal={_tl.get('fatal_risk')}]")
        print("  逐维：" + "；".join(f"{n}={d}" for n, d in _tl.get("per_dim", [])))
    if args.report:
        rpt = Path(args.report).read_text(encoding="utf-8")
        adv = panorama_advisory(rpt, data)
        print("\n--- #7 软一致性提示（不计入 gate，仅请复核）---")
        print("\n".join(adv) if adv else "（无）")


if __name__ == "__main__":
    main()
