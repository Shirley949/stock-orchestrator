#!/usr/bin/env python3
"""
data_contracts.py —— stock-analysis snapshot 的数据契约注册表（单一真相源）

把「获取层 runner fetcher」与「消费层 module/gate/computed_metrics」用一份声明式
契约绑死，消除三处真相源分裂（snapshot_schema.md / _EXPECTED_SCENES /
CHECKID_TO_SNAPSHOT_PATH）的手工 drift。

每个 scene 声明六维：
  produces   —— 产出字段路径 + confidence（confirmed/assumed/unverified）
  consumers  —— 字段级消费者（module:行号 / Gxx / 派生 scene）
  priority   —— P0(gate-critical) / P1(report-important) / P2(nice-to-have)
  cost       —— 网络 calls + latency + throttle_prone
  depends_on —— 顺序敏感的 backfill 依赖（CI 校验调度顺序）
  fallback   —— 限流/失败降级链（S4 收入）

confidence 语义（驱动 CI 严格度，用户决策「分级标注 + 逐步硬化」）：
  confirmed  —— 字段路径形状已验证（mock / 单股真连 / fetcher 硬编码确认）→ CI hard fail
  assumed    —— 路径依赖隐式约定（如中文键名），fetcher 代码支持但未单独验证 → CI warn
  unverified —— 路径形状未确认（依赖 API 原字段名，runner 不 reshape）→ CI warn

证据来源：3 个 Explore agent 一手调研（2026-07-05），file:line 见各 scene 注释。
本文件 S1 阶段为纯增量声明，不进入运行时热路径（runner/gate 不 import 它运行时逻辑）。
"""

# ============================================================
# 常量
# ============================================================

P0, P1, P2 = "P0", "P1", "P2"                                  # 优先级
CONFIRMED, ASSUMED, UNVERIFIED = "confirmed", "assumed", "unverified"  # 置信度

# ============================================================
# Scene 契约（Mode A 全量 20 个 + Mode B 占位）
# ============================================================

SCENES = {

    # ───────────── P0：gate-critical（缺失直接 gate FAIL）─────────────

    "s1_financial": {
        "fetcher": "fetch_financial_unified",   # runner.py:587
        "mode": ["A"],
        "produces": [
            {"path": "data.income_statement",    "confidence": CONFIRMED},
            {"path": "data.balance_sheet",       "confidence": CONFIRMED},
            {"path": "data.cash_flow",           "confidence": CONFIRMED},
            {"path": "data.financial_abstract",  "confidence": CONFIRMED},
            {"path": "data.financial_indicators","confidence": CONFIRMED},
            {"path": "data.segment_composition", "confidence": CONFIRMED},
        ],
        "consumers": {
            "data.income_statement":     ["m2", "m25:67", "G6", "G9", "G27", "computed_metrics"],
            "data.balance_sheet":        ["m2", "m25:12", "G16", "computed_metrics"],
            "data.cash_flow":            ["m2", "G8"],
            "data.financial_abstract":   ["m2", "G7"],
            "data.financial_indicators": ["m2", "G27"],
            "data.segment_composition":  ["m2", "m25:13"],
        },
        "priority": P0,   # G6/G7/G8/G9/G16/G27 均读它
        "cost": {"calls": 12, "calls_worst": 33, "latency": "medium"},
        "depends_on": [],
        "fallback": ["THS三表 → 东财datacenter → Sina三表 → all_failed"],  # runner.py:657-706
        "cacheable": True,
    },

    "s3_fund_flow": {
        "fetcher": "fetch_fund_flow",            # runner.py:924
        "mode": ["A", "B"],
        "produces": [
            {"path": "data.fund_flow", "confidence": CONFIRMED},
            {"path": "data.fund_flow.items[].name", "confidence": ASSUMED,
             "note": "fetcher 硬编码中文{特大单,大单,中单,小单}(runner.py:979-989)；G26 严格依赖此集合，错则 FAIL"},
        ],
        "consumers": {
            "data.fund_flow":              ["G26", "m10:10A.4"],
            "data.fund_flow.items[].name": ["G26"],
        },
        "priority": P0,   # G26 依赖
        "cost": {"calls": 1, "calls_worst": 3, "latency": "high", "throttle_prone": True},
        "depends_on": [],
        "fallback": {"data.fund_flow": "akshare:stock_fund_flow_individual"},  # 同花顺源
        "cacheable": True,
    },

    "s3_cninfo_pdf": {
        "fetcher": "fetch_cninfo_reports",       # runner.py:1553
        "mode": ["A"],
        "produces": [
            {"path": "data.audit_opinion",  "confidence": CONFIRMED},
            {"path": "data.dividend",       "confidence": CONFIRMED},
            {"path": "data.biz_breakdown",  "confidence": CONFIRMED},
            {"path": "data.geo_revenue",    "confidence": CONFIRMED},
            {"path": "data.top10_holders",  "confidence": CONFIRMED},
        ],
        "consumers": {
            "data.audit_opinion":  ["s36_annual_analysis"],
            "data.dividend":       ["s36_annual_analysis"],
            "data.biz_breakdown":  ["s36_annual_analysis"],
            "data.geo_revenue":    ["s36_annual_analysis"],
            "data.top10_holders":  ["s36_annual_analysis"],
        },
        "priority": P0,   # s36→G23 链路源头；D2_audit.status==ok 经 s36 间接必需
        "cost": {"calls": 4, "latency": "very_high"},   # ~300s，SIGALRM 锁
        "depends_on": [],
        "fallback": [],   # PDF 独家，无替代
        "cacheable": False,
    },

    # ───────────── P1：report-important（核心分析维度）─────────────

    "s2_quote_kline": {
        "fetcher": "fetch_quote_and_kline",      # runner.py:871
        "mode": ["A", "B"],
        "produces": [
            {"path": "data.daily_kline",    "confidence": CONFIRMED},
            {"path": "data.realtime_quote", "confidence": CONFIRMED},
        ],
        "consumers": {
            "data.daily_kline":   ["m3-technical", "computed_metrics", "R6_holder_distribution", "G14", "_EXPECTED_SCENES"],
            "data.realtime_quote": ["m3-technical", "computed_metrics"],
        },
        "priority": P1,
        "cost": {"calls": 2, "calls_worst": 9, "latency": "medium"},
        "depends_on": [],
        "fallback": {
            "data.daily_kline":   "stock_zh_a_daily → curl_eastmoney_kline → stock_zh_a_hist",
            "data.realtime_quote": "curl_sina_hq → _derive_quote_from_daily",
        },
        "cacheable": True,
    },

    "futu_overview": {
        "fetcher": "fetch_futu_overview",        # runner.py:1794
        "mode": ["A"],
        "produces": [
            {"path": "data.quote.price",          "confidence": CONFIRMED},
            {"path": "data.quote.peTtm",          "confidence": CONFIRMED},
            {"path": "data.quote.peLyr",          "confidence": CONFIRMED},
            {"path": "data.quote.pbRatio",        "confidence": CONFIRMED},
            {"path": "data.quote.epsTtm",         "confidence": CONFIRMED},
            {"path": "data.quote.dividendRatio",  "confidence": CONFIRMED},
            {"path": "data.analystRating",        "confidence": CONFIRMED},
            {"path": "data.targetPrice",          "confidence": CONFIRMED},
            # ★断链#1：runner 不 reshape，子路径依赖富途 API 原字段名 targetInfo
            {"path": "data.targetPrice.targetInfo.average", "confidence": UNVERIFIED,
             "note": "runner.py:1828 直接透传 API data，未产出 targetInfo 子键；m4:113 引用，依赖 API 原字段名"},
            {"path": "data.targetPrice.targetInfo.highest", "confidence": UNVERIFIED},
            {"path": "data.targetPrice.targetInfo.lowest",  "confidence": UNVERIFIED},
            # 无消费者候选砍除（log.md:696）
            {"path": "data.quote.priceHighest_52week", "confidence": CONFIRMED, "consumed": False,
             "note": "无消费者（log.md:696 标可砍），候选 S5 移除；consumed=False 显式豁免孤儿校验"},
            {"path": "data.quote.priceLowest_52week",  "confidence": CONFIRMED, "consumed": False,
             "note": "无消费者，候选 S5 移除；consumed=False 显式豁免孤儿校验"},
        ],
        "consumers": {
            "data.quote.price":          ["computed_metrics"],
            "data.quote.peTtm":          ["m5:13", "m6:79", "computed_metrics"],
            "data.quote.peLyr":          ["m5:14", "m6:79"],
            "data.quote.pbRatio":        ["m5:15", "m6:79", "computed_metrics"],
            "data.quote.epsTtm":         ["m5:16", "m6:81", "m10:10"],
            "data.quote.dividendRatio":  ["m5:17"],
            "data.analystRating":        ["m10:10A.1", "s4_rating_backfill", "_EXPECTED_SCENES"],
            "data.targetPrice":          ["m4:113", "m6:83", "m10:55"],
            "data.targetPrice.targetInfo.average": ["m4:113"],
            "data.targetPrice.targetInfo.highest": ["m4:114"],
            "data.targetPrice.targetInfo.lowest":  ["m4:114"],
        },
        "priority": P1,
        "cost": {"calls": 3, "calls_worst": 9, "latency": "high", "throttle_prone": True},
        "depends_on": [],
        "fallback": {},   # Futu 独家，限流→status:throttled 标注
        "cacheable": True,
    },

    "futu_forecast": {
        "fetcher": "fetch_futu_forecast",        # runner.py:1848
        "mode": ["A"],
        "produces": [
            {"path": "data.eps",       "confidence": CONFIRMED},
            {"path": "data.revenue",   "confidence": CONFIRMED},   # S0 m10 显式化
            {"path": "data.netProfit", "confidence": CONFIRMED},
            {"path": "data.ebit",      "confidence": CONFIRMED},
        ],
        "consumers": {
            "data.eps":       ["m10:10A.3", "m6:81", "m5:35", "computed_metrics:eps_fy_consensus", "s73_forecast_backfill"],
            "data.revenue":   ["m10:10A.3"],
            "data.netProfit": ["m10:10A.3"],
            "data.ebit":      ["m10:10A.3"],
        },
        "priority": P1,
        "cost": {"calls": 4, "calls_worst": 12, "latency": "high", "throttle_prone": True},
        "depends_on": [],
        "fallback": {"data.eps": "akshare:stock_profit_forecast_ths"},   # revenue/ebit/netProfit 富途独家无替代
        "cacheable": True,
    },

    "s5_events": {
        "fetcher": "fetch_events",               # runner.py:1114
        "mode": ["A"],
        "produces": [
            {"path": "data.news", "confidence": CONFIRMED},
            # ★断链#3：中文键名依赖 news_analyzer 输出
            {"path": "data.news.data_full[].新闻内容", "confidence": ASSUMED,
             "note": "中文键名依赖 news_analyzer 输出；m4:166 引用，G21 [src:] 路径验证依赖此键"},
            {"path": "data.risk_signals", "confidence": CONFIRMED},
            # ★断链#4：细粒度子键，runner 不强制 schema
            {"path": "data.risk_signals.unlock.has_forward_pressure", "confidence": UNVERIFIED,
             "note": "runner.py:1034 默认 {unlock:None,...}，子键依赖填充代码；m7:19 引用"},
        ],
        "consumers": {
            "data.news":                                  ["m4", "G25", "_EXPECTED_SCENES", "m25:14"],
            "data.news.data_full[].新闻内容":             ["m4:166"],
            "data.risk_signals":                          ["m7"],
            "data.risk_signals.unlock.has_forward_pressure": ["m7:19"],
        },
        "priority": P1,
        "cost": {"calls": 4, "calls_worst": 7, "latency": "medium"},
        "depends_on": [],
        "fallback": {
            "data.news":              "news_analyzer(eastmoney search-api) → stock_news_em",
            "data.risk_signals.pledge": "stock_gpzy_pledge_ratio_em 季度回退(20260331→51231→50930)",
        },
        "cacheable": True,
    },

    "s6_macro": {
        "fetcher": "fetch_macro",                 # runner.py:1226
        "mode": ["A"],
        "produces": [
            {"path": "data.pmi", "confidence": CONFIRMED},
            {"path": "data.ppi", "confidence": CONFIRMED},
            {"path": "data.m2",  "confidence": CONFIRMED},
        ],
        "consumers": {
            "data.pmi": ["_EXPECTED_SCENES", "m35"],
            "data.ppi": ["m35:7"],
            "data.m2":  ["m5:66"],
        },
        "priority": P1,
        "cost": {"calls": 3, "latency": "low"},
        "depends_on": [],
        "fallback": {},
        "cacheable": False,
    },

    "s8_a_share": {
        "fetcher": "fetch_a_share",               # runner.py:1282
        "mode": ["A"],
        "produces": [
            {"path": "data.shareholder_count.processed", "confidence": CONFIRMED},
        ],
        "consumers": {
            "data.shareholder_count.processed": ["m25:15", "m4:55", "m6:43", "_EXPECTED_SCENES"],
        },
        "priority": P1,
        "cost": {"calls": 1, "calls_worst": 4, "latency": "low"},
        "depends_on": [],   # R6 后处理读 s2，但发生在 fetch 内部 (runner.py:2444)
        "fallback": {},
        "cacheable": True,
    },

    "s35_research_reports": {
        "fetcher": "fetch_research_reports",      # runner.py:2149
        "mode": ["A"],
        "produces": [
            {"path": "data.layer1.em_reports_count",        "confidence": CONFIRMED},
            {"path": "data.layer1.em_rating_distribution",  "confidence": CONFIRMED},
            {"path": "data.layer1.eps_consensus",           "confidence": CONFIRMED},
            # ★断链#5：.current.mean 子路径形状未在 runner 显式确认
            {"path": "data.layer1.eps_consensus.current.mean", "confidence": UNVERIFIED,
             "note": "_compute_eps_consensus(runner.py:1946) 返回结构未确认含 .current.mean；m5:33/m6:83/m10:11 引用"},
        ],
        "consumers": {
            "data.layer1.em_reports_count":                   ["m10:105"],
            "data.layer1.em_rating_distribution":             ["m4:112", "s4_rating_backfill"],
            "data.layer1.eps_consensus":                      ["m5:33", "m6:83", "m10:11", "s4_rating_backfill"],
            "data.layer1.eps_consensus.current.mean":         ["m5:33", "m6:83", "m10:11"],
        },
        "priority": P1,
        "cost": {"calls": 2, "latency": "medium"},
        "depends_on": [],
        "fallback": {},
        "cacheable": True,
    },

    # ───────────── P2：nice-to-have / coverage-only ─────────────

    "s55_industry": {
        "fetcher": "fetch_industry_data",         # runner.py:1168
        "mode": ["A"],
        "produces": [{"path": "data", "confidence": CONFIRMED}],
        "consumers": {},   # ★零 module/gate 正文消费（Agent2 全扫实证），仅 _EXPECTED_SCENES 占席
        "priority": P2,
        "cost": {"calls": 2, "latency": "low"},
        "depends_on": [],
        "fallback": {},
        "cacheable": False,
        "coverage_only": True,   # CI 校验1 对此 scene 降级为 warn（待 S5 按「消费才覆盖」处置）
        "note": "拉了数据但 14 个 module 正文零引用，仅 _EXPECTED_SCENES 消费（'拉到即覆盖'掩盖）。S5 处置：补进 module 或从清单移除。",
    },

    "s7_cyclical": {
        "fetcher": "fetch_cyclical",              # runner.py:1259
        "mode": ["A"],
        "produces": [{"path": "data", "confidence": CONFIRMED}],
        "consumers": {"data": ["m35-cyclical"]},
        "priority": P2,
        "cost": {"calls": 0, "latency": "low"},   # 非周期股直接 return
        "depends_on": [],
        "fallback": {},
        "cacheable": False,
    },

    # ───────────── 派生/backfill scene（无独立 fetcher，读其他 scene）─────────────

    "s4_rating": {
        "fetcher": None,   # 回填 runner.py:2392-2428
        "mode": ["A"],
        "produces": [{"path": "data.rating", "confidence": CONFIRMED}],
        "consumers": {"data.rating": ["m4", "m6"]},
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": ["s35_research_reports", "futu_overview"],   # ★顺序敏感
        "fallback": {},
        "cacheable": False,
        "derived": True,
    },

    "s73_forecast": {
        "fetcher": None,   # 回填 runner.py:2380
        "mode": ["A"],
        "produces": [{"path": "data", "confidence": CONFIRMED}],
        "consumers": {"data": ["m10"]},
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": ["futu_forecast"],   # ★顺序敏感
        "fallback": {},
        "cacheable": False,
        "derived": True,
    },

    "s36_annual_analysis": {
        "fetcher": None,   # 回填 runner.py:2356
        "mode": ["A"],
        "produces": [
            {"path": "data.D2_audit_opinion", "confidence": CONFIRMED},
            {"path": "data.D3_dividend",      "confidence": CONFIRMED},
            {"path": "data.D4_top10_holders", "confidence": CONFIRMED},
            {"path": "data.D5_biz_breakdown", "confidence": CONFIRMED},
            {"path": "data.D6_geo_revenue",   "confidence": CONFIRMED},
        ],
        "consumers": {
            "data.D2_audit_opinion": ["G23", "m9"],
            "data.D3_dividend":      ["m9"],
            "data.D4_top10_holders": ["m9"],
            "data.D5_biz_breakdown": ["m2", "m9"],
            "data.D6_geo_revenue":   ["m2", "m9"],
        },
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": ["s3_cninfo_pdf"],   # ★顺序敏感
        "fallback": {},
        "cacheable": False,
        "derived": True,
    },

    "computed_metrics": {
        "fetcher": "_build_computed_metrics",    # runner.py:1659
        "mode": ["A"],
        "produces": [
            {"path": "data.pe_ttm",          "confidence": CONFIRMED},
            {"path": "data.pb",              "confidence": CONFIRMED},
            {"path": "data.eps_fy_consensus","confidence": CONFIRMED},
            {"path": "data.gross_margin_calc","confidence": CONFIRMED},
            {"path": "data.has_overseas_exposure",  "confidence": CONFIRMED},   # G17 标记（D6 派生）
            {"path": "data.reported_overseas_pct", "confidence": CONFIRMED},   # m25 关税影响引用
        ],
        "consumers": {
            "data.pe_ttm": ["m5"], "data.pb": ["m5"],
            "data.eps_fy_consensus": ["m5", "m6"],
            "data.gross_margin_calc": ["m2"],
            "data.has_overseas_exposure": ["G17"],
            "data.reported_overseas_pct": ["m25"],
        },
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": ["s1_financial", "futu_overview", "futu_forecast", "s36_annual_analysis"],   # ★顺序敏感（s36=D6 源）
        "fallback": {},
        "cacheable": False,
        "derived": True,
    },

    "s4_technical": {
        # Mode B 占位（runner.py:2435，"由 Claude 用 K线数据自算"，零网络）
        "fetcher": None,
        "mode": ["B"],
        "produces": [{"path": "data", "confidence": CONFIRMED}],
        "consumers": {"data": ["m3-technical"]},
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": ["s2_quote_kline"],
        "fallback": {},
        "cacheable": False,
        "derived": True,
    },
}


# ============================================================
# 派生视图（供 S3 调度 / S5 覆盖率派生 / CI 校验使用，不进运行时热路径）
# ============================================================

def get_consumed_scenes():
    """consumers 非空的 scene 名集合。

    S5 _EXPECTED_SCENES 派生用——语义=「消费才覆盖」（用户决策）：
    只有被 module/gate 实际消费的 scene 才计入 data_coverage。
    注意：s55_industry 因 consumers={} 会被排除（待 S5 处置）。
    """
    return {name for name, c in SCENES.items() if c.get("consumers")}


def get_by_priority(mode):
    """按 priority 分组的 scene 名（S3 fetch_for_mode 调度用）。

    返回 {P0:[...], P1:[...], P2:[...]}，同组内保留 SCENES 声明顺序（tie-breaker）。
    """
    groups = {P0: [], P1: [], P2: []}
    for name, c in SCENES.items():
        if mode in c.get("mode", []):
            groups[c["priority"]].append(name)
    return groups


def all_produces():
    """全 scene produces 扁平化：path → [(scene, confidence, note), ...]。

    CI 校验2「无断链消费」用：consumer 引用的 path 必须在此出现（或为其前缀）。
    """
    out = {}
    for sname, c in SCENES.items():
        for p in c.get("produces", []):
            out.setdefault(p["path"], []).append((sname, p["confidence"], p.get("note", "")))
    return out


def all_consumer_refs():
    """全 scene consumers 扁平化：(scene, path) 列表。CI 校验1/2 用。"""
    out = []
    for sname, c in SCENES.items():
        for path, cons in c.get("consumers", {}).items():
            out.append((sname, path, cons))
    return out


if __name__ == "__main__":
    # 自检：打印契约概览（不校验，校验在 verify_data_contracts.py）
    print(f"scenes: {len(SCENES)} | consumed: {len(get_consumed_scenes())} | "
          f"produces paths: {len(all_produces())}")
    for prio in (P0, P1, P2):
        names = get_by_priority("A")[prio]
        print(f"  {prio} (Mode A): {names}")
