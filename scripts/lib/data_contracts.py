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
# Scene 契约（Mode A 全量 + Mode B 占位 + 日内低吸引擎派生）
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
            {"path": "data.dupont",             "confidence": CONFIRMED},
        ],
        "consumers": {
            "data.income_statement":     ["m2", "m25:67", "G6", "G9", "G27", "computed_metrics"],
            "data.balance_sheet":        ["m2", "m25:12", "G16", "computed_metrics"],
            "data.cash_flow":            ["m2", "G8"],
            "data.financial_abstract":   ["m2", "G7"],
            "data.financial_indicators": ["m2", "G27"],
            "data.segment_composition":  ["m2", "m25:13"],
            "data.dupont":               ["m2:291", "G28"],
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
            {"path": "data.realtime_quote.turnover",   "confidence": CONFIRMED},  # 换手率%，腾讯 qt.gtimg.cn data[38]（sina/kline 无此字段，单开腾讯调用）
            {"path": "data.realtime_quote.change_pct", "confidence": CONFIRMED},  # 涨跌幅%，腾讯 data[32]，跨 scene 注入 valuation_snapshot.quote.changeRatio
        ],
        "consumers": {
            "data.daily_kline":   ["m3-technical", "computed_metrics", "R6_holder_distribution", "G14", "_EXPECTED_SCENES"],
            "data.realtime_quote": ["m3-technical", "computed_metrics"],
            "data.realtime_quote.turnover":   ["m3-technical"],   # m3 量比/换手率行（15% 权重）
            "data.realtime_quote.change_pct": ["valuation_snapshot.quote.changeRatio"],  # 跨 scene 单向注入
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

    # ───────────── P1：日内低吸定位器（stock-intraday-t-analyzer）核心输入 ─────────────
    "intraday_kline_5min": {
        "fetcher": "fetch_kline_sina",          # lib/data_sources.py
        "mode": ["A", "B"],
        "produces": [
            {"path": "data.kline_5min", "confidence": CONFIRMED,
             "note": "Sina getKLineData 分钟 OHLCV；stock-intraday-t-analyzer 引擎核心输入（纯函数派生低吸信号）"},
        ],
        "consumers": {
            "data.kline_5min": ["computed_metrics", "intraday_technical_derived"],   # 引擎：派生 MA55/ATR/MACD/VWAP/背离 + h60/m5 均线
        },
        "priority": P1,
        "cost": {"calls": 1, "latency": "fast"},
        "depends_on": [],
        "fallback": ["curl_sina_kline → all_failed"],
        "cacheable": True,
    },

    "intraday_daily_ohlcv": {
        "fetcher": "fetch_daily_akshare",        # lib/data_sources.py（保守双源：数值走 akshare qfq）
        "mode": ["A", "B"],
        "produces": [
            {"path": "data.daily", "confidence": CONFIRMED,
             "note": "akshare stock_zh_a_daily qfq 完整日线 OHLCV+amount+turnover+outstanding_share；"
                     "供日内引擎 ma_series/levels/weekly/gaps/daily_last 计算"},
        ],
        "consumers": {
            "data.daily": ["intraday_technical_derived"],
        },
        "priority": P1,
        "cost": {"calls": 1, "latency": "fast", "throttle_prone": True},   # akshare 重依赖，单股单次低频
        "depends_on": [],
        "fallback": ["fetch_kline_sina(scale=240) → all_failed"],   # 降级 OHLCV-only，缺 amount/turnover
        "cacheable": True,
    },

    "intraday_technical_derived": {
        "fetcher": None,   # engine 纯函数派生：compute_ma_series / _detect_gaps / compute_levels / compute_weekly / build_daily_last
        "mode": ["A", "B"],
        "produces": [
            {"path": "result.ma_series",  "confidence": CONFIRMED},
            {"path": "result.levels",     "confidence": CONFIRMED},
            {"path": "result.weekly",     "confidence": CONFIRMED},
            {"path": "result.gaps",       "confidence": CONFIRMED},
            {"path": "result.daily_last", "confidence": CONFIRMED},
        ],
        "consumers": {
            "result.ma_series":  ["format_text", "SKILL.md 输出白名单"],
            "result.levels":     ["format_text", "SKILL.md 输出白名单"],
            "result.weekly":     ["format_text", "SKILL.md 输出白名单"],
            "result.gaps":       ["format_text", "SKILL.md 输出白名单"],
            "result.daily_last": ["format_text", "SKILL.md 输出白名单"],
        },
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": ["intraday_kline_5min", "intraday_daily_ohlcv"],   # ★顺序敏感：5min(h60/m5) + 日线(daily)
        "fallback": {},
        "cacheable": False,
        "derived": True,
    },

    "valuation_snapshot": {
        "fetcher": "fetch_valuation_snapshot",        # runner.py（westock 腾讯源 + akshare baidu）
        "mode": ["A"],
        "produces": [
            {"path": "data.quote.price",          "confidence": CONFIRMED},
            {"path": "data.quote.peTtm",          "confidence": CONFIRMED},
            {"path": "data.quote.peLyr",          "confidence": CONFIRMED},   # baidu 市盈率(静)，指标名须精确"静"
            {"path": "data.quote.pbRatio",        "confidence": CONFIRMED},
            {"path": "data.quote.pcfRatio",       "confidence": CONFIRMED},   # baidu 市现率（新增）
            {"path": "data.quote.epsTtm",         "confidence": CONFIRMED},
            {"path": "data.quote.epsLyr",         "confidence": CONFIRMED},   # westock finance_periods 取年报(12-31)行
            {"path": "data.quote.totalMarketCap", "confidence": CONFIRMED},
            {"path": "data.quote.dividend_history","confidence": CONFIRMED},  # 原始分红方案序列（主，LLM 推理）
            {"path": "data.quote.dividend_ratio", "confidence": CONFIRMED},   # 派生股息率%（辅，cashDiviRMB÷10÷price）
            {"path": "data.quote.dividend_year",  "confidence": CONFIRMED},
            {"path": "data.quote.changeRatio",    "confidence": CONFIRMED},   # 跨 scene 注入：fetch_for_mode 从 s2.realtime_quote.change_pct（腾讯 qt.gtimg.cn data[32]）写入
            {"path": "data.quote.pe_is_loss",     "confidence": CONFIRMED},   # 亏损标记（负 PE 保留）
            {"path": "data.quote.pb_insolvent",   "confidence": CONFIRMED},   # 资不抵债标记（PB<0 保留）
            {"path": "data.analystRating",        "confidence": CONFIRMED},
            {"path": "data.targetPrice",          "confidence": CONFIRMED},
            {"path": "data.targetPrice.average",  "confidence": CONFIRMED},
            {"path": "data.targetPrice.highest",  "confidence": CONFIRMED},
            {"path": "data.targetPrice.lowest",   "confidence": CONFIRMED},
        ],
        "consumers": {
            "data.quote.price":          ["computed_metrics"],
            "data.quote.peTtm":          ["m5:13", "m6:79", "computed_metrics"],
            "data.quote.peLyr":          ["m5:14", "m6:79"],
            "data.quote.pbRatio":        ["m5:15", "m6:79", "computed_metrics"],
            "data.quote.pcfRatio":       ["m5"],                # 市现率（新增，m5 估值表）
            "data.quote.epsTtm":         ["m5:16", "m6:81", "m10:10"],
            "data.quote.epsLyr":         ["m5"],
            "data.quote.totalMarketCap": ["m5", "computed_metrics"],
            "data.quote.dividend_history":["m5"],               # 原始方案（主）
            "data.quote.dividend_ratio": ["m5:17"],             # 派生股息率（辅）
            "data.quote.dividend_year":  ["m5"],
            "data.quote.changeRatio":    ["m5", "m6"],
            "data.quote.pe_is_loss":     ["m5"],                # 负值语义标注
            "data.quote.pb_insolvent":   ["m5"],
            "data.analystRating":        ["m10:10A.1", "s4_rating_backfill", "_EXPECTED_SCENES"],
            "data.targetPrice":          ["m4:113", "m6:83", "m10:55"],
            "data.targetPrice.average":  ["m4:113"],
            "data.targetPrice.highest":  ["m4:114"],
            "data.targetPrice.lowest":   ["m4:114"],
        },
        "priority": P1,
        # westock(腾讯源)无限流；baidu stock_zh_valuation_baidu 稳定（PE-TTM/市净率/总市值）。
        # calls≈baidu 4 指标 + westock(fund_flow/rating/consensus 与他场景复用，当日缓存)。
        "cost": {"calls": 4, "calls_worst": 7, "latency": "medium", "throttle_prone": False},
        "depends_on": [],
        "fallback": {"data.quote.peTtm": "westock:finance", "data.quote.pbRatio": "westock:finance"},
        "cacheable": True,
    },

    "consensus_forecast": {
        "fetcher": "fetch_consensus_forecast",        # runner.py（westock consensus 年度 + finance 实际值）
        "mode": ["A"],
        "produces": [
            {"path": "data.eps",            "confidence": CONFIRMED},   # list[dict]，年度 reshape 供 computed_metrics PEG
            {"path": "data.revenue",        "confidence": CONFIRMED},
            {"path": "data.netProfit",      "confidence": CONFIRMED},
            {"path": "data.ebit",           "confidence": CONFIRMED},
            {"path": "data.annual",         "confidence": CONFIRMED},   # 年度富表 2026/27/28（eps/营收/净利/pe/pb/ps/yoy）
            {"path": "data.last_actual",    "confidence": CONFIRMED},   # 最新期实际值（含 EBIT）
            {"path": "data.paid_in_capital","confidence": CONFIRMED},   # 总股本（市值交叉校验）
        ],
        "consumers": {
            "data.eps":       ["m10:10A.3", "m6:81", "m5:35", "computed_metrics:eps_fy_consensus", "s73_forecast_backfill"],
            "data.revenue":   ["m10:10A.3"],
            "data.netProfit": ["m10:10A.3"],
            "data.ebit":      ["m10:10A.3"],
            "data.annual":    ["m10:10A.3"],
            "data.last_actual": ["m10:10A.3"],
            "data.paid_in_capital": ["m5"],   # 总股本×收盘价 与 baidu 总市值交叉校验
        },
        "priority": P1,
        # westock consensus + finance 各 1 次 npx（腾讯源无限流）。
        "cost": {"calls": 2, "calls_worst": 3, "latency": "medium", "throttle_prone": False},
        "depends_on": [],
        "fallback": {"data.eps": "s35:eps_consensus", "data.last_actual.revenue": "s1_financial:income_statement"},
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
        "depends_on": ["s35_research_reports", "valuation_snapshot"],   # ★顺序敏感
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
        "depends_on": ["consensus_forecast"],   # ★顺序敏感
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
            {"path": "data.peg_forward",     "confidence": CONFIRMED},   # consensus 同源 forward PE÷netProfitYoy（四档适用性）
            {"path": "data.gross_margin_calc","confidence": CONFIRMED},
            {"path": "data.has_overseas_exposure",  "confidence": CONFIRMED},   # G17 标记（D6 派生）
            {"path": "data.reported_overseas_pct", "confidence": CONFIRMED},   # m25 关税影响引用
            {"path": "data.asset_safety",           "confidence": CONFIRMED},   # m2 §2.10 防雷（balance_sheet 派生）；G29 校验
        ],
        "consumers": {
            "data.pe_ttm": ["m5"], "data.pb": ["m5"],
            "data.eps_fy_consensus": ["m5", "m6"],
            "data.peg_forward": ["m5"],        # m5 估值表 PEG 行（读 value/applicability）
            "data.gross_margin_calc": ["m2"],
            "data.has_overseas_exposure": ["G17"],
            "data.reported_overseas_pct": ["m25"],
            "data.asset_safety": ["m2:246", "G29"],
        },
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": ["s1_financial", "valuation_snapshot", "consensus_forecast", "s36_annual_analysis"],   # ★顺序敏感（s36=D6 源）
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
