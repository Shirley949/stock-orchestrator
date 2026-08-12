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
            {"path": "data.income_statement.latest_period",  "confidence": CONFIRMED,
             "note": "利润表最新期信封（series-family，period_type=day，value={营业总收入,归母净利润,扣非净利润}；plan L2）"},
            {"path": "data.balance_sheet",       "confidence": CONFIRMED},
            {"path": "data.balance_sheet.latest_period",     "confidence": CONFIRMED,
             "note": "资产负债表最新期信封（value={合同负债,货币资金,短期借款,商誉}；plan L2）"},
            {"path": "data.cash_flow",           "confidence": CONFIRMED},
            {"path": "data.cash_flow.latest_period",         "confidence": CONFIRMED,
             "note": "现金流量表最新期信封（value=经营活动产生的现金流量净额；plan L2）"},
            {"path": "data.financial_abstract",  "confidence": CONFIRMED},
            {"path": "data.financial_indicators","confidence": CONFIRMED},
            {"path": "data.segment_composition", "confidence": CONFIRMED},
            {"path": "data.dupont",             "confidence": CONFIRMED},
            {"path": "data.mainfinadata",       "confidence": CONFIRMED,
             "note": "东财 MAINFINADATA 指标 165 字段（wide 族，rows[0]=最新期 desc）；ZCFZL/LD/SD 偿债能力 + ROEJQ/ROIC + 同比/DJD 单季；G27③/m2§2.3"},
            {"path": "data.rd_expense",         "confidence": CONFIRMED,
             "note": "东财 RDEXP 研发全子字段（序列族取最新年报期 12-31）；RESEARCH_EXPENSE/_CAPITALIZATION/_RATIO/_NUM/_NUM_RATIO；m2§2.3.1/§2.11"},
        ],
        "consumers": {
            "data.income_statement":     ["m2", "m25:67", "G6", "G9", "G27", "computed_metrics"],
            "data.balance_sheet":        ["m2", "m25:12", "G16", "computed_metrics"],
            "data.cash_flow":            ["m2", "G8"],
            "data.financial_abstract":   ["m2", "G7"],
            "data.financial_indicators": ["m2", "G27"],
            "data.segment_composition":  ["m2:§2.2", "m25:13", "m6:Layer1", "m7:7.1", "m0", "m1", "m5:§5.2"],   # 三维 canonical v2.0（product/industry/geo + dimension_status）；m0 分类/m1 叙事/m5 同业本公司行/m6 主营构成行/m7 地缘/关税+集中度/m2 分业务表
            "data.dupont":               ["m2:291", "G28"],
            "data.mainfinadata":         ["m2:§2.3", "G27"],   # 偿债能力 ZCFZL/LD/SD（m2§2.3 空白源）+ G27③ presence
            "data.rd_expense":           ["m2:§2.3.1", "m2:§2.11"],   # 研发资本化/人员（替 PDF rd_expense）
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

    # ───────────── P1：report-important（核心分析维度）─────────────

    "s2_quote_kline": {
        "fetcher": "fetch_quote_and_kline",      # runner.py:871
        "mode": ["A", "B"],
        "produces": [
            {"path": "data.daily_kline",    "confidence": CONFIRMED},
            {"path": "data.daily_kline.latest_period", "confidence": CONFIRMED,
             "note": "最新 bar 信封（series-family，value=close 标量；plan L2）。"
                     "G30#1 经 _G30_VALUE_FIELDS 读 close 做数值新鲜度（现价 stale 兜底）"},
            {"path": "data.realtime_quote", "confidence": CONFIRMED},
            {"path": "data.realtime_quote.turnover",       "confidence": CONFIRMED},  # 换手率%（=turnover_pct 归一，腾讯 d[38]，与 daily.turnover×100 统一口径）
            {"path": "data.realtime_quote.turnover_pct",   "confidence": CONFIRMED},  # 换手率% 归一字段（四态 ok 态填；兼容名 turnover）
            {"path": "data.realtime_quote.amount_yuan",    "confidence": CONFIRMED},  # 成交额 元（d[37]万×10000；兼容名 amount）
            {"path": "data.realtime_quote.volume_ratio",   "confidence": CONFIRMED},  # 量比 d[46]（量价领先镜头核心）
            {"path": "data.realtime_quote.change_pct",     "confidence": CONFIRMED},  # 涨跌幅% 腾讯 d[32]，跨 scene 注入 valuation_snapshot.quote.changeRatio
            {"path": "data.realtime_quote._turnover_status","confidence": CONFIRMED}, # 四态信封 not_applicable/no_trade/fetch_failed/ok（G1 判结构性豁免 vs 瞬态失败）
        ],
        "consumers": {
            "data.daily_kline":   ["m3-technical", "computed_metrics", "R6_holder_distribution", "G14", "_EXPECTED_SCENES"],
            "data.daily_kline.latest_period": ["G30"],   # #1 数值新鲜度（close stale 兜底）
            "data.realtime_quote": ["m3-technical", "computed_metrics"],
            # 换手率归一% 扩展到 7 模块 + G1（量价四镜头消费链；原仅 m3 → 603663 漏消费根因）
            "data.realtime_quote.turnover":      ["m3-technical", "m4-sentiment", "m5-valuation", "m6-decision", "m7-risk", "m9-governance", "m25-orders", "G1"],
            "data.realtime_quote.turnover_pct":  ["m3-technical", "m6-decision"],     # 归一字段同 turnover 语义
            "data.realtime_quote.amount_yuan":   ["m3-technical", "m6-decision", "m7-risk"],   # 成交额（流动性/量价）
            "data.realtime_quote.volume_ratio":  ["m3-technical", "m6-decision"],     # 量比（四镜头之量价领先）
            "data.realtime_quote.change_pct":    ["valuation_snapshot.quote.changeRatio"],     # 跨 scene 单向注入
            "data.realtime_quote._turnover_status": ["G1"],                          # G1 四段判结构性豁免
        },
        "priority": P1,
        "cost": {"calls": 2, "calls_worst": 9, "latency": "medium"},
        "depends_on": [],
        "fallback": {
            "data.daily_kline":   "stock_zh_a_daily（新浪单源；Tier2/Tier3 已删）",
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
            {"path": "data.quote.dividend_latest_period", "confidence": CONFIRMED,
             "note": "最新分红期信封（兄弟键，dividend_history 保持 list 不破坏 m5 消费；plan L2）。"
                     "value dict {每股股利(cashDiviRMB/10), 股利总额, dividendPlan}；G38 经 _extract_latest_value 兄弟键回退读 每股股利 做数值新鲜度"},
            {"path": "data.quote.changeRatio",    "confidence": CONFIRMED},   # 跨 scene 注入：fetch_for_mode 从 s2.realtime_quote.change_pct（腾讯 qt.gtimg.cn data[32]）写入
            {"path": "data.quote.pe_is_loss",     "confidence": CONFIRMED},   # 亏损标记（负 PE 保留）
            {"path": "data.quote.pb_insolvent",   "confidence": CONFIRMED},   # 资不抵债标记（PB<0 保留）
            {"path": "data.analystRating",        "confidence": CONFIRMED},
            {"path": "data.targetPrice",          "confidence": CONFIRMED},
            {"path": "data.targetPrice.average",  "confidence": CONFIRMED},
            {"path": "data.targetPrice.highest",  "confidence": CONFIRMED},
            {"path": "data.targetPrice.lowest",   "confidence": CONFIRMED},
            # ST2 估值分位（近五年 baidu 序列自算，零增量调用）：pe_ttm/pb 双窗口分位 + 适用性/history_sufficient
            {"path": "data.valuation_percentile", "confidence": CONFIRMED,
             "note": "ST2 估值分位 {pe_ttm,pb}，每项 {pct_5y,pct_all,current,median_5y,min_5y,max_5y,window_5y,window_all,applicable,history_sufficient,as_of}；"
                     "baidu 近五年日序列(914行)自算 pct=(vals<=current).mean()；亏损 PE→applicable=false；次新 5y<3y→history_sufficient=false。m5 §5.1/m6 Layer1 消费"},
            # F-D1/D2 lixinger EV/EBITDA（工业/周期股企业价值口径，填补免费源全缺）
            {"path": "data.ev_metrics", "confidence": CONFIRMED,
             "note": "lixinger fundamental/non_financial 快照 {ev_ebitda_r,ev_ebit_r,ey,source,as_of}；"
                     "金融股跳过（EBITDA 不适用）；best-effort 失败→键缺；m5 §5.x/m6 Layer1 企业价值锚消费"},
            {"path": "data.valuation_percentile.ev_ebitda", "confidence": CONFIRMED,
             "note": "lixinger ≤10y 序列本地算 box（同 pe_ttm 结构 + 适用性/history_sufficient）；EV-EBITDA≤0 不适用→键缺"},
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
            "data.quote.dividend_latest_period": ["G38"],   # 分红有效性（每股股利数值新鲜度，scales 1.0/0.1）
            "data.quote.changeRatio":    ["m5", "m6"],
            "data.quote.pe_is_loss":     ["m5"],                # 负值语义标注
            "data.quote.pb_insolvent":   ["m5"],
            "data.analystRating":        ["m10:10A.1", "_EXPECTED_SCENES"],   # m4 §4.3 收敛后评级→m10 §10A；删 ghost s4_rating_backfill
            "data.targetPrice":          ["m6:83", "m10:55"],   # m4 §4.3 收敛后目标价明细→m10 §10A，删 m4:113
            "data.targetPrice.average":  ["m10:55"],   # m10 §10A 渲染目标价（m4 收敛后不再读）
            "data.targetPrice.highest":  ["m10:55"],
            "data.targetPrice.lowest":   ["m10:55"],
            "data.valuation_percentile": ["m5", "m6", "capstone_panorama"],   # ST2 分位：m5 §5.1 行 + m6 Layer1 估值锚 + capstone L339 values pull（含 ev_ebitda 子键）
            "data.ev_metrics":           ["m5", "m6"],   # F-D1/D2 lixinger EV/EBITDA：m5 企业价值锚 + m6 Layer1 估值锚
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
            {"path": "data.company_guidance", "confidence": CONFIRMED,
             "note": "业绩预告（东财 RPT_PUBLIC_OP_NEWPREDICT，runner.py:6796 嵌套于 consensus_forecast.data）；company_guidance 非顶层 scene"},
            {"path": "data.company_guidance.latest_period.value.predict_type", "confidence": CONFIRMED,
             "note": "预增/预减/续盈/扭亏/略增...（M8 预减·首亏·续亏·预亏 / P4 预增·续盈·扭亏 分流；runner.py:3603）"},
            {"path": "data.company_guidance.latest_period.value.growth_tier", "confidence": CONFIRMED,
             "note": "高成长强度分档（仅预增按 INCREASE_JZ：>50%→high / 20-50%→moderate / 其余·非预增·缺→None；runner.py:6638 additive 加法式）；m4 G57 校验 presence"},
            {"path": "data.latest_period", "confidence": CONFIRMED,
             "note": "最新实绩锚点信封（period_type=year，value=actual；runner.py:6900）；G30#1 数值新鲜度（同 s1/s2/s8 latest_period 范式）"},
            {"path": "data.annual_latest_period", "confidence": CONFIRMED,
             "note": "最近预测年信封（period_type=year，value=forecast；runner.py:6901）；m10 §10A 年度预测表读最近预测年"},
        ],
        "consumers": {
            "data.eps":       ["m10:10A.3", "m6:81", "m5:35", "computed_metrics:eps_fy_consensus"],
            "data.revenue":   ["m10:10A.3"],
            "data.netProfit": ["m10:10A.3"],
            "data.ebit":      ["m10:10A.3"],
            "data.annual":    ["m10:10A.3"],
            "data.last_actual": ["m10:10A.3"],
            "data.paid_in_capital": ["m5", "_aggregate_shareholder_dynamics", "_assemble_programs"],   # 总股本×收盘价 与 baidu 总市值交叉校验 + ST5 占总股本% 派生分母（缺→%全 None 诚实降级）
            "data.company_guidance": ["_process_material_signals"],   # runner 内部 M8/P4 编码（业绩预告→风险/利好分流）
            "data.company_guidance.latest_period.value.predict_type": ["m4-sentiment", "m5-valuation"],
            "data.company_guidance.latest_period.value.growth_tier": ["m4-sentiment", "G57"],
            "data.latest_period": ["G30"],                # 数值新鲜度（_g30_value_freshness_findings，同 s1/s2/s8 范式）
            "data.annual_latest_period": ["m10"],         # m10 §10A 年度预测表（最近预测年）
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
            {"path": "data.news.latest_period", "confidence": CONFIRMED,
             "note": "最新新闻信封（period_type=datetime，raw_date=最新发布时间 max(data_full)，value=标题；plan L2）"},
            # ★断链#3：中文键名依赖 news_analyzer 输出
            {"path": "data.news.data_full[].新闻内容", "confidence": ASSUMED,
             "note": "中文键名依赖 news_analyzer 输出；m4:166 引用，G21 [src:] 路径验证依赖此键"},
            {"path": "data.risk_signals", "confidence": CONFIRMED},
            # ★断链#4：细粒度子键，runner 不强制 schema
            {"path": "data.risk_signals.unlock.has_forward_pressure", "confidence": UNVERIFIED,
             "note": "runner 默认 {unlock:None,...}，子键依赖填充代码；m7:19 引用"},
            {"path": "data.risk_signals.processed", "confidence": CONFIRMED,
             "note": "事件层信封 {status, latest_period, timeline, shareholder_dynamics, programs, repurchase_programs}（事件主源=东财大事提醒 timeline；severity/M-P/risk_register/announcements 体系已退役）"},
            {"path": "data.risk_signals.processed.timeline", "confidence": CONFIRMED,
             "note": "东财 F10 大事提醒 RPT_F10_REMIND 时间线信封 {events,future,historical,active,risk,catalyst,fatal_events,by_code{EVENT_TYPE_CODE:[events]},"
                     "meta{body_fetch_count,unknown_codes,counts},summary,latest_period,status}；45 类 EVENT_TYPE_CODE 官方分类（risk/catalyst/forward/directional/neutral flavor），"
                     "NOTICE_DATE≤180d 硬截断 ∨ fatal 年龄豁免（330非标/360破产/430风险警示/ST240/退市230/重大违法270）；"
                     "event={notice_date,event_type,event_type_code,specific,belong_classif,level1_content,info_code,flavor,effective_date,validity_state[,fatal]}；"
                     "P9 月度经营（公告大全窄源）emit 为 catalyst pseudo-code P9；m1/m4/m6/m7/m9/capstone 消费，G30#1 fatal_events surface；三态 ok(含 never_*/真空)/failed"},
            {"path": "data.risk_signals.latest_period", "confidence": CONFIRMED,
             "note": "最新事件日信封（period_type=event，date=max timeline event notice_date，value=None；真空→None→gate 自动 PASS）"},
            # ST3：减持增持融合（意图×内部人×前十大）—— executive_trade/shareholder 既有 raw 激活（前十大今日 orphan）
            {"path": "data.risk_signals.executive_trade", "confidence": CONFIRMED,
             "note": "westock 董监高/实控人个人增减持 list[dict]（managerName/managerSharesChange±/managerDealPrice/managerHoldChangeDeclareDate）；M1/P1 evidence + shareholder_dynamics.insiders"},
            {"path": "data.risk_signals.shareholder", "confidence": CONFIRMED,
             "note": "westock 十大股东 list[dict]（no/name/holdShares/holdPct/holdChange±；正=增持负=减持，最新一期）；"
                     "ST3 C1 解码层 fold 进 M1/P1 evidence + shareholder_dynamics.top10（具名大股东方向，今日 orphan 已激活）"},
            {"path": "data.risk_signals.processed.shareholder_dynamics", "confidence": CONFIRMED,
             "note": "ST3+ST5 股东行为融合信封 {status,by_source{insiders,top10,controlling_shareholders},vs_intent,windows,verdict,corroboration,latest_trade_date,latest_period,summary}；"
                     "三态 ok(含空)/failed；m9 §9.2 综合研判 home + m6/m7/m4/capstone 消费，G47 presence。"
                     "ST6 P4 加法式：by_source.controlling_shareholders（ths_executions fold·控股股东/一致行动人子桶，weight 高于董监高）+ "
                     "by_source.top10.source（westock|top10_multiperiod·gap-fill）+ named[].multi_period_direction（多期 qoq 趋势）。"
                     "ST5 加法式 %：total_shares/total_shares_source（=paid_in_capital，缺→None 全 % 降级）+ "
                     "by_source.insiders.{net_pct,increase_pct,reduce_pct,detail[].pct,detail[].is_grant,grant_count,increase_shares_total,reduce_shares_total}（gross-split，修 net-only 遗漏）+ "
                     "by_source.top10.{net_pct,named[].delta_pct}；0-1 ratio，消费方 inline {x:.2%}（同 unlock {r:.1%} 范式）。"
                     "ST7 加法式：by_source.top10_quarterly（券商级季度信封 periods[{period,quarter,new_entrants[],increasers[],decreasers[],exited[],flat[],net_shares,weighted_net,strong_in/strong_out,tone}] + latest_period(quarter)；源 RPT_F10_EH_FREEHOLDERS HOLDER_STATE_NEW/HOLDER_NEWTYPE/HOLD_NUM 官方结构化 PRIMARY；m9 §9.2 券商表 + G47 presence）"},
            # ST5：待执行/进行中 增减持计划（forward，决策驱动）—— cap%/窗口=正文 REAL，executed%=THS REAL÷总股本
            {"path": "data.risk_signals.processed.programs", "confidence": CONFIRMED,
             "note": "ST5 待执行-FIRST 计划信封 list[dict]：{direction,tier,status(planned|ongoing|completed|abandoned),"
                     "announce_date,window_start,window_end,window_source[REAL绝对|DERIVED反算|MISSING],announced_pct_cap[REAL正文],announced_shares_cap,"
                     "executed_shares[REAL THS],executed_pct[REAL÷总股本],remaining_pct(cap−exec),over_executed,avg_price,"
                     "source_art_codes[],provenance{cap,window,executed,remaining,price:REAL|DERIVED|MISSING}}；"
                     "预披露 body↔THS 执行 JOIN（actor名+窗口就近）；0/[]（无活跃计划，empty_is_ok）/None；m9 待执行段 + G48 presence"},
            # ST6 P0：公司级回购计划（与股东级 programs[] 平级·actor=公司；westock buyback 执行 PRIMARY + body 计划层）
            {"path": "data.risk_signals.processed.repurchase_programs", "confidence": CONFIRMED,
             "note": "ST6 公司级回购 list[dict]：{purpose[注销并减少注册资本|股权激励/员工持股|市值管理],announce_date,"
                     "status(planned|ongoing|completed|abandoned),plan_amount_cap_yi[REAL body 不超过/最高限额],"
                     "plan_amount_floor_yi[REAL body 不低于],plan_price_cap[REAL 调整后价],window_start/end/source,"
                     "executed_amount_yi[REAL westock sum(BuybackFunds)],executed_shares,avg_price,"
                     "progress_pct[=executed÷cap 两 REAL 比值],currency(RMB|HKD),source_art_codes[],"
                     "provenance{plan,executed,window,price:REAL|DERIVED|MISSING}}；"
                     "0/[]（无回购，empty_is_ok）/None；m9 回购段 + capstone _render_buy_sell_pressure"},
            # ST6 P2：买卖力量综合 verdict（read-only 聚合·Option 2.5 薄 verdict，跨 scene lhb/northbound/fund_flow + shareholder_dynamics）
            {"path": "data.risk_signals.processed.buy_sell_pressure", "confidence": CONFIRMED,
             "note": "ST6 买卖阵营对决 verdict {status,as_of,buy{repurchase,insider_buy,incentive,top10_accum,northbound,lhb_buy,fund_flow},"
                     "sell{insider_sell,unlock,pledge,placement,top10_dist,lhb_sell,fund_flow_out},verdict(buy_dominant|sell_dominant|balanced|unclear),"
                     "corroboration{multi_source_buy/sell,source_count,weight},summary,latest_period}；"
                     "read-only 读既有信封一次（反双渲染：DETAIL 不进 BSP，仍由 _render_shareholder_behavior/_render_lhb 单渲染）；"
                     "材料性闸（董监高/控股股东 <INSIDER_MIN_RATIO_PCT=1% 不计 force）；三态 ok(含 unclear 空活动)/failed；m9 §9.2 + G49 presence"},
            # ST5.1：执行/趋势/正文 三 raw 源（_fetch_risk_signals 内 env 兄弟键，processed 派生输入；非模块直读）
            {"path": "data.risk_signals.ths_executions", "confidence": CONFIRMED,
             "note": "ST5.1 同花顺 stock_shareholder_change_ths 结构化执行 list[dict]（date/actor/direction/shares/avg_price/remaining/window_start/end/channel）；"
                     "覆盖控股股东/一致行动人（executive_trade 仅董监高个人的 null gap 根治）；_assemble_programs/_aggregate 内部消费"},
            {"path": "data.risk_signals.top10_multiperiod", "confidence": CONFIRMED,
             "note": "ST5.1 东财 datacenter RPT_F10_EH_FREEHOLDERS 前十大流通股东多期趋势 list[{period,holders[{name,delta_shares,hold_pct,qoq_pct,is_new}]}]；"
                     "多期 QoQ=真趋势（beats westock 单期快照）；_aggregate top10 趋势消费"},
            {"path": "data.disclosure", "confidence": CONFIRMED,
             "note": "Westock W2: 财报披露日历并入（disclosure_date/desc + latest_period event）；无未来披露日=missing 真空"},
        ],
        "consumers": {
            "data.news":                                  ["m4", "G25", "_EXPECTED_SCENES", "m25:14"],
            "data.news.data_full[].新闻内容":             ["m4:166"],
            "data.risk_signals":                          ["m1", "m4", "m5", "m6", "m7", "m9"],
            "data.risk_signals.unlock.has_forward_pressure": ["m7:19"],
            "data.risk_signals.processed":                ["m6", "G30"],
            "data.risk_signals.processed.timeline":       ["m1", "m4", "m6", "m7", "m9", "capstone_panorama", "G30"],  # 大事提醒时间线：m1拐点锚/m4渲染/m6悲观top/m7风险行/m9 §9.2/capstone fatal+signals/G30#1 fatal surface
            "data.risk_signals.executive_trade":          ["m4", "m9", "capstone_panorama"],   # ST3 内部人执行层（既有 raw 补登 consumer）
            "data.risk_signals.shareholder":              ["m4", "m9", "capstone_panorama"],   # ST3 前十大执行层（今日 orphan 补登）
            "data.risk_signals.processed.shareholder_dynamics": ["m9", "m6", "m7", "m4", "capstone_panorama", "G47"],  # ST3+ST5 融合信封（含 %）：m9 §9.2 home + m6/m7/m4 消费 + G47 presence
            "data.risk_signals.processed.programs": ["m9", "m7", "m1", "m6", "capstone_panorama", "G48"],  # ST5 待执行-FIRST 计划：m9 待执行段 + m7 风险行 + m1 overhang + m6 timing + capstone render + G48 presence
            "data.risk_signals.processed.repurchase_programs": ["m9", "m7", "m1", "capstone_panorama", "_aggregate_buy_sell_pressure"],  # ST6 公司级回购：m9 回购段 + m7/m1 + capstone render + BSP 聚合输入
            "data.risk_signals.processed.buy_sell_pressure": ["m9", "m6", "m7", "m1", "capstone_panorama", "G49"],  # ST6 买卖阵营 verdict：m9 §9.2 home + m6 timing + m7 卖方 + m1 + capstone render + G49 presence
            "data.risk_signals.ths_executions": ["_assemble_programs", "_aggregate_shareholder_dynamics"],   # ST5.1 THS 执行（内部派生输入）
            "data.risk_signals.top10_multiperiod": ["_aggregate_shareholder_dynamics"],   # ST5.1 RPT 多期趋势（内部派生输入）
            "data.disclosure":                            ["m4", "G43"],   # m4 事件扫描（披露日临近=催化/风险）+ G43 消费校验
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
            {"path": "data.pmi.latest_period",  "confidence": CONFIRMED,
             "note": "PMI 最新期信封（period_type=month，value=制造业-指数 标量；plan L2）"},
            {"path": "data.ppi", "confidence": CONFIRMED},
            {"path": "data.ppi.latest_period",  "confidence": CONFIRMED,
             "note": "PPI 最新期信封（value=当月 指数；plan L2）"},
            {"path": "data.m2",  "confidence": CONFIRMED},
            {"path": "data.m2.latest_period",   "confidence": CONFIRMED,
             "note": "M2 最新期信封（value=货币和准货币(M2)-数量(亿元) 绝对量；plan L2）"},
        ],
        "consumers": {
            "data.pmi": ["_EXPECTED_SCENES", "m35"],
            "data.pmi.latest_period":  ["G37"],   # 宏观 presence（数值窄带/派生口径不做，见 gate 注释）
            "data.ppi": ["m35:7"],
            "data.ppi.latest_period":  ["G37"],
            "data.m2":  ["m5:66"],
            "data.m2.latest_period":   ["G37"],
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
            {"path": "data.shareholder_count.latest_period", "confidence": CONFIRMED,
             "note": "户数最新期信封（series-family，value=holder_count+change_pct 透传；plan L2）。"
                     "G30#1 经 _G30_VALUE_FIELDS 读 value 做数值新鲜度校验（★ 户数 stale-value bug 兜底）"},
        ],
        "consumers": {
            "data.shareholder_count.processed": ["m25:15", "m4:55", "m6:43", "_EXPECTED_SCENES"],
            "data.shareholder_count.latest_period": ["G30"],   # #1 数值新鲜度（_g30_value_freshness_findings）
        },
        "priority": P1,
        "cost": {"calls": 1, "calls_worst": 4, "latency": "low"},
        "depends_on": [],   # R6 后处理读 s2，但发生在 fetch 内部 (runner.py:2444)
        "fallback": {},
        "cacheable": True,
    },

    "lhb": {
        "fetcher": "fetch_lhb",                     # runner.py（东财个股席位 + 同花顺 daily 摘要）
        "mode": ["A"],
        "produces": [
            {"path": "data.processed", "confidence": CONFIRMED},
            {"path": "data.processed.latest_period", "confidence": CONFIRMED,
             "note": "龙虎榜最新上榜日信封（signal-family，processed.latest_date 升级为信封，标量向后兼容；plan L2 §2.3）。"
                     "value 按 signal_type 选（hot_money→游资净额/inst→机构净额），summary 头条必带。"
                     "freshness（lhb 90d 窗 sort_key 新旧）消费归 capstone Step 4 渲染「⚠️历史榜单·非近期」"},
            {"path": "data.seats", "confidence": CONFIRMED},     # 元·单席（东财）；m7 highlight 读 类型/_reason_cat
            {"path": "data.daily", "confidence": CONFIRMED},     # 万元·全榜（同花顺）；90d 窗
        ],
        "consumers": {
            "data.processed": ["m4", "m6", "m7", "capstone", "G32"],
            "data.seats": ["m7"],                                # §7.5.3 highlight
            "data.daily": ["m7"],
        },
        "priority": P1,
        "cost": {"calls": 8, "calls_worst": 41, "latency": "medium"},  # 90d 窗：典型 1日期+~3日×2 flag+1 THS；热股最多 1+20×2+1
        "depends_on": [],
        "fallback": {},
        "cacheable": True,
        "note": "个股机构/游资席位（东财 stock_lhb_stock_detail_em 主 + 同花顺 lhbgg HTML 补次日涨跌/原因→daily）。"
                "⚠️ 90 天窗：seats/daily/detail_dates 均过滤 90d，total_count=90d 内上榜次数。"
                "daily=万元·全榜前5 / seats=元·单席（单位进字段名）。三态靠 signal_type 编码："
                "never_listed(真·空,ok) / event_only_summary(东财降级,ok/L5) / fetch_failed(双源挂,failed)；G32 据此判完整性。"
                "有意不进 gate _EXPECTED_SCENES（self-score 分母不变，风险>收益）。",
    },

    "northbound": {
        "fetcher": "fetch_northbound",              # runner.py（westock 季度持仓 + 东财 TOP10 降级）
        "mode": ["A"],
        "produces": [
            {"path": "data.processed", "confidence": CONFIRMED},
            {"path": "data.processed.latest_period", "confidence": CONFIRMED,
             "note": "北向最新季度信封（signal-family，日期从 quarterly_holding[0].披露截止 提升到 processed；plan L2 §2.3）。"
                     "period_type=quarter，value=holding_ratio_latest(%)，summary 头条必带。"
                     "freshness（披露截止 sort_key 新旧）消费归 capstone Step 4 渲染；真空（no_northbound_data）→ latest_period=None"},
        ],
        "consumers": {
            "data.processed": ["m4", "m6", "m7", "capstone", "G33"],
        },
        "priority": P1,
        "cost": {"calls": 1, "calls_worst": 2, "latency": "low"},   # 1Q：1 westock 调用；失败 +1 TOP10
        "depends_on": [],
        "fallback": {},
        "cacheable": True,
        "note": "外资季度持仓（westock fund north-holding 主 + 东财 RPT_MUTUAL_TOP10DEAL 降级）。"
                "⚠️ 只拉 1 季度（最新季度，order={'最新季度':0}）·仅水平信号：holding_ratio_prev/change_qoq/"
                "trend_direction 恒 null，删 foreign_accumulating/reducing（流向需 2Q）。"
                "processed 区分 no_northbound_data(真·非标的, status=ok) vs failed(双源拉取失败)；G33 据此判完整性。"
                "有意不进 gate _EXPECTED_SCENES（同 lhb）。",
    },

    "s11_peer": {
        "fetcher": "fetch_peer_comparison",      # runner.py（target + ≤3 peer）
        "mode": ["A"],
        "produces": [
            # 伞路径 data（同 s55_industry/s36_annual_analysis 范式）：覆盖 status/target_metrics/
            # items[].metrics(核心6)/items[].gsjj_yw 等全部子字段（_path_matches 前缀匹配）。
            # 核心 6（gate 强制）vs 富字段（不计 gate）的区分见 schema.md 散文 + 下方 note。
            {"path": "data", "confidence": CONFIRMED},
        ],
        "consumers": {
            "data.status":           ["G15"],                  # 三态(ok/degraded/missing)判定
            "data.target_metrics":  ["m5", "G15"],             # m5 同业对比(§5.2) + G15 核心6计数
            "data.items[].metrics": ["m5", "G15", "m6"],       # m6 capstone 引用 peer 指标
            "data.items[].gsjj_yw": ["m1", "m5"],              # 主营相近度佐证
        },
        "priority": P1,
        "cost": {"calls": 8, "latency": "medium"},   # target(1 jiankuang+1 sina) + ≤3 peer×2 + 0.6s 节流
        "depends_on": [],                             # peer_codes 由 LLM websearch 外部给出，非 scene 依赖
        "fallback": {},
        "cacheable": True,                            # jiankuang(curl)+sina(akshare) 均经 DataSnapshot 缓存
        "note": "同业对比（F3 端到端重建）：target + ≤3 peer，核心 6 字段（rev_yoy/np_yoy/pe/pb/roe/gross_margin）"
                "经 腾讯 jiankuang(curl,[1,3,6]退火+fail_cache) + akshare sina 利润表(毛利率) 真实拉取。"
                "⚠️ peer 码由 LLM websearch 主营业务相近度给出（本环境无可靠'拉竞争对手'API：sina 无清单/"
                "东财限流/申万 SSL 封，实测）；runner 纯机械化拉取，全参数化，换码即跑。"
                "三态：ok(≥2家核心齐全)/degraded(部分缺)/missing(全限流或未拉取)；反编造（拉不到不填词）。"
                "金融股豁免 gross_margin（真无营业成本，数据现实——非假设；core_fields 动态裁为 5）。"
                "调用：① mode A 带 peer_codes 一次性拉取；② `python runner.py peer <target> <c1,c2,c3> [stock_type]`"
                "（LLM websearch 后单独拉取，LLM 合并入 snapshot.s11_peer）。"
                "research_notes（全球份额/认证等定性）为 LLM websearch 补充字段（_source:llm_web_research），"
                "非 runner 产出——gate 只校验 metrics（API 层），不校验 research_notes（仿 G26 富字段原则）。"
                "有意不进 gate _EXPECTED_SCENES（同 lhb/northbound；peer 非每票必有，进清单会误伤独家/次新）。",
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
            "data.layer1.em_reports_count":                   ["m10:105", "m4"],   # m4 §4.1 机构关注度代理（P1-9：研报覆盖数=机构关注度；P2-10 补登 m4 consumer）
            "data.layer1.em_rating_distribution":             ["m10:10A.1"],   # m4 §4.3 收敛后评级分布→m10 §10A.1；删 m4:112 + ghost s4_rating_backfill
            "data.layer1.eps_consensus":                      ["m5:33", "m6:83", "m10:11"],
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

    "web_research_findings": {
        "fetcher": "DataSnapshot.fetch_web_research",  # F4: LLM websearch 产出（非 runner 网络）；data_snapshot.py 封装信封
        "mode": ["A", "B"],
        "produces": [{"path": "data", "confidence": UNVERIFIED}],  # websearch 非一手 API → UNVERIFIED + items _verified=false
        "consumers": {"data.items": ["m5"]},   # F-D4：m5 目标价/API 缺失时引 web_research（[src: web_research_findings]，G21 路径验证 + G45 口径）
        "priority": P2,
        "cost": {"calls": 0, "latency": "low"},   # LLM websearch 成本不计入 runner
        "depends_on": [],
        "fallback": {},
        "cacheable": False,
        "coverage_only": True,   # 不进 _EXPECTED_SCENES（self-score 分母）；websearch 非每票必有
        "note": "F4: LLM websearch 数字（机构覆盖/目标价/评级/产能/份额）入 snapshot，标 _verified=false；"
                "报告引用须 [src: web_research_findings]，m5 目标价优先 API-grade valuation_snapshot。",
    },

    "s_margin": {
        # _attach_westock_extras（runner.py）：westock fund margin 融资融券单日快照
        "fetcher": "_attach_westock_extras",
        "mode": ["A"],
        "produces": [{"path": "data.finance_value_yi", "confidence": CONFIRMED,
                      "note": "融资余额(亿) + security_value_yi 融券 + finance_dod/security_dod 环比(DOD现成信号) + latest_period"}],
        "consumers": {"data.finance_value_yi": ["m7-risk", "G42"]},  # m7 踩踏风险 / G42 消费校验（m4 杠杆情绪已删→归 m7）
        "priority": P2,
        "cost": {"calls": 1, "latency": "low"},
        "depends_on": [],
        "fallback": {},
        "cacheable": True,
        "coverage_only": True,   # 不进 _EXPECTED_SCENES（次新/无两融标的 missing，进清单会误伤）
        "note": "Westock W1: 融资余额=杠杆拥挤度(高位+环比增=踩踏风险)，融券=空头；三态 ok/missing(次新)/failed。",
    },

    "s_esg": {
        # _attach_westock_extras（runner.py）：westock esg 中证/聚源 ESG 评级
        "fetcher": "_attach_westock_extras",
        "mode": ["A"],
        "produces": [{"path": "data.items", "confidence": CONFIRMED,
                      "note": "[{source(中证/聚源), rating, publish_date, change}] + latest_period(最新发布日+评级)"}],
        "consumers": {"data.items": ["m9-governance", "m7-risk", "G44"]},  # m9.2 治理 / m7 合规风险 / G44 消费校验
        "priority": P2,
        "cost": {"calls": 1, "latency": "low"},
        "depends_on": [],
        "fallback": {},
        "cacheable": True,
        "coverage_only": True,   # 不进 _EXPECTED_SCENES（无 ESG 数据标的 missing，进清单会误伤）
        "note": "Westock W3: ESG 评级(中证/聚源双源)，低 ESG=治理/合规风险，变动=趋势；三态 ok/missing/failed。",
    },

    # ───────────── 派生/backfill scene（无独立 fetcher，读其他 scene）─────────────

    "s36_annual_analysis": {
        "fetcher": None,   # 回填 runner.py:2356
        "mode": ["A"],
        "produces": [
            {"path": "data.D3_dividend",      "confidence": CONFIRMED},   # westock valuation_snapshot.dividend_history
            {"path": "data.D4_top10_holders", "confidence": CONFIRMED},   # 东财 EH_HOLDERS 前十大（off-PDF）
            {"path": "data.D7_custsupp",      "confidence": CONFIRMED},   # 东财 CUSTSUPP 前五客户/供应商（最新年报期，off-PDF）
            {"path": "data.D8_staff",         "confidence": CONFIRMED},   # 东财 STAFF 员工构成（最新年报期，off-PDF）
        ],
        "consumers": {
            "data.D3_dividend":      ["m9"],
            "data.D4_top10_holders": ["m9"],
            "data.D7_custsupp":      ["m9"],   # §9.4 客户/供应商集中度
            "data.D8_staff":         ["m9"],   # §9.5 员工构成与人均效能
        },
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": ["valuation_snapshot"],   # D3 分红 westock 源（D4/D7/D8 东财独立 fetch，无 scene 依赖）
        "fallback": {},
        "cacheable": False,
        "derived": True,
    },

    "computed_metrics": {
        "fetcher": "_build_computed_metrics",    # runner.py:1659
        "mode": ["A"],
        "produces": [
            {"path": "data.eps_fy_consensus","confidence": CONFIRMED},
            {"path": "data.peg_forward",     "confidence": CONFIRMED},   # consensus 同源 forward PE÷netProfitYoy（四档适用性）
            {"path": "data.gross_margin_calc","confidence": CONFIRMED},
            {"path": "data.has_overseas_exposure",  "confidence": CONFIRMED},   # 海外顶层镜像（geo 派生量，G17 旧读，现 computed_metrics 内部派生 overseas.status）
            {"path": "data.reported_overseas_pct", "confidence": CONFIRMED},   # 海外占比%（m25/m35 关税情景引用）
            {"path": "data.asset_safety",           "confidence": CONFIRMED},   # m2 §2.10 home（完整体检+level/flags）；m7 §7.1 反双渲染引用（读 level/cash_to_debt，不重渲染比率）；G29 校验
            # §1.5/§1.6 三维派生信号（zero 新 API，全从 segment_composition 派生）
            {"path": "data.overseas",                "confidence": CONFIRMED},   # §1.5 海外五态（geo 派生，降级信号）：activated/domestic_only/underivable_*；m7 §7.1 读 status/pct/as_of
            {"path": "data.concentration_composite","confidence": CONFIRMED},   # §1.6 营收复合集中度（region_cr1 × product_cr1，合取→composite_severe 单点失败跳级）
            {"path": "data.tariff_vulnerability",   "confidence": CONFIRMED},   # §1.6 关税脆弱性海外毛利率判别（fatal/partial_low_margin_export/partial_mixed/partial_unverified/none）；G17 Phase3 触发源
        ],
        "consumers": {
            "data.eps_fy_consensus": ["m5", "m6"],
            "data.peg_forward": ["m5"],        # m5 估值表 PEG 行（读 value/applicability）
            "data.gross_margin_calc": ["m2"],
            "data.has_overseas_exposure": ["computed_metrics"],   # _compute_overseas_status 内部读它派生 overseas.status（G17 Phase3 改读 tariff_vulnerability）
            "data.reported_overseas_pct": ["m25", "m35", "computed_metrics"],
            "data.asset_safety": ["m2:246", "m7", "G29"],   # m2 §2.10 home（完整比率体检）+ m7 §7.1 反双渲染引用（读 level/cash_to_debt 出风险行，不重渲染比率）+ G29 校验
            "data.overseas":                  ["m7", "computed_metrics"],                  # m7 §7.1；tariff_vulnerability 派生读它
            "data.concentration_composite":   ["m7", "m6"],                                # m7 识别（§7.1 集中度行）+ m6 悲观引用（单点失败）
            "data.tariff_vulnerability":      ["m7", "m6", "m25", "m35", "G17"],           # m7 识别（§7.1 地缘+§7.1.1 折让）+ m6 悲观引用 + m25 T0-T4 + m35 关税情景行 + G17 三维合取触发
        },
        "note": "computed_metrics 实存 snapshot['computed_metrics'][key]（无 .data. 中缀）；契约 path 用 data.X 仅为场景内符号一致，verify 不解析真实 snapshot 路径。",
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": ["s1_financial", "valuation_snapshot", "consensus_forecast", "s36_annual_analysis"],   # ★顺序敏感（s36=D6 源）
        "fallback": {},
        "cacheable": False,
        "derived": True,
    },

    "classification": {
        "fetcher": None,   # runner.py:7422 派生（C1 解码 + C2 静态派生 + C2.5 dominant_business + C3 is_mixed overlay），非 fetcher 产出
        "mode": ["A"],
        "produces": [
            {"path": "primary_type",        "confidence": CONFIRMED},   # 分类结果（周期/成长/消费/金融/防御/多元化控股）
            {"path": "is_mixed",            "confidence": CONFIRMED},   # 混合型 overlay（成长+周期材料，C3）
            {"path": "secondary_type",      "confidence": CONFIRMED},   # 混合时次类型，非混合缺省
            {"path": "valuation_framework", "confidence": CONFIRMED},   # 估值框架（C2；周期→PB/EV-EBITDA，成长→PS/PEG，金融→PB/ROE），约束下游 m5 口径
            {"path": "macro_sensitivity",   "confidence": CONFIRMED},   # 宏观敏感度 high/medium/low（C2）；G37 宏观条件触发器
            {"path": "forbidden_metric",    "confidence": CONFIRMED},   # 禁用主估值指标（C2；周期→"PE做主要"，成长→"PB做主要"），m0 执法依据
            {"path": "dominant_business",   "confidence": CONFIRMED,    # C2.5 主导业务锚 {product_name,revenue_ratio,gross_margin,report_date}
             "note": "top1 产品按营收占比最大取（修 segment 源序 latent bug）；非时间序列无 latest_period 信封；行业身份读 raw_facts.board_name_level 不在此（segment.industry 常是 CSRC 大类过宽）"},
            {"path": "raw_facts",           "confidence": CONFIRMED,    # 原始事实 {industry_csrc,board_name_level,main_business}
             "note": "board_name_level=具体产业链级（如'电力设备-电池-锂电池'），m1 行业身份一句话锚"},
        ],
        "consumers": {
            "primary_type":        ["m0", "m1", "G39"],   # m0 类型句单一真相源 + m1 身份句 + G39 类型词三查
            "is_mixed":            ["m0", "m1", "G39"],
            "secondary_type":      ["m1"],                # m1 混合时次类型联动
            "valuation_framework": ["m0", "m1"],          # m0 声明约束 + m1 类型句
            "macro_sensitivity":   ["m0", "G39"],         # G39 宏观引用三查
            "forbidden_metric":    ["m0", "m1", "G39"],   # m0 执法依据 + G39 禁用指标三查
            "dominant_business":   ["m0", "m1", "m2", "m7"],  # m0 home + m1 主营锚 + m2/m7 读 gross_margin
            "raw_facts":           ["m1"],                # m1 行业身份（board_name_level）
        },
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": [],
        "fallback": {},
        "cacheable": False,
        "derived": True,
        "note": "股票类型单一真相源（snapshot_schema.md:65，2026-07-22 约定）：所有模块读类型/估值框架/宏观敏感度/主导业务只读此处，"
                "不再散读 segment_composition/product_industry_alignment（已退役）。顶层独立扁平 slot（runner.py:7422 snapshot['classification']=classification，"
                "无 .data. 中缀、非时间序列、无 latest_period）。schema_coverage 方向(b) 因 classification 路径无 .data. 中缀而跳过（verify_data_contracts.py:185），"
                "故 preferred_macro/is_cyclic/is_financial/confidence/evidence 当前无 module/gate 直读——按 orphan_produces 语义不声明 produces（不声明则不查）。"
                "~~industry_momentum~~ 已移除（2026-07-22：s55.momentum 是日内板块涨跌幅≠景气趋势，景气改读 s6_macro 信封）。",
    },

    "governance": {
        "fetcher": None,   # runner.py:7715 派生（东财 ORG_BASICINFO 6 字段 + classifier raw_facts board/main_business 合并），非 fetcher 产出
        "mode": ["A"],
        "produces": [
            {"path": "status",              "confidence": CONFIRMED},   # 三态：ok/never_empty/failed（G23 软 presence 触发）
            {"path": "real_controler",      "confidence": CONFIRMED},   # 实际控制人
            {"path": "control_holder",      "confidence": CONFIRMED},   # 控股股东
            {"path": "control_direct_ratio","confidence": CONFIRMED},   # 控股直比%（>50% 强控制）
            {"path": "chairman",            "confidence": CONFIRMED},   # 董事长
            {"path": "legal_person",        "confidence": CONFIRMED},   # 法定代表人
            {"path": "area",                "confidence": CONFIRMED},   # 地区板块（如「山西板块」）
            {"path": "board_name_level",    "confidence": CONFIRMED,    # 行业合并串（如「电力设备-电网设备-线缆部件及其他」）
             "note": "自 classifier.raw_facts.board_name_level 复暴露（canonical produce=classification.raw_facts），m9 §9.2 单处读取"},
            {"path": "main_business",       "confidence": CONFIRMED,    # 主营业务一句话
             "note": "自 classifier.raw_facts.main_business 复暴露（canonical produce=classification.raw_facts），m9 §9.2 单处读取"},
        ],
        "consumers": {
            "status":              ["G23"],          # 软 presence（status==ok+实控人 → 报告须消费；failed/never_empty 豁免）
            "real_controler":      ["m9", "m1", "G23"],
            "control_holder":      ["m9", "m1"],
            "control_direct_ratio":["m9", "m1"],
            "chairman":            ["m9"],
            "legal_person":        ["m9"],
            "area":                ["m9"],
            "board_name_level":    ["m9"],           # §9.2 治理基本信息（复暴露自 classification.raw_facts）
            "main_business":       ["m9"],
        },
        "priority": P1,
        "cost": {"calls": 0, "latency": "low"},
        "depends_on": ["classification"],   # board_name_level/main_business 复暴露自 raw_facts
        "fallback": {},
        "cacheable": False,
        "derived": True,
        "note": "公司治理基本信息单一读取点（runner.py:7715 snapshot['governance']）：东财 RPT_F10_ORG_BASICINFO（实控人/控股/直比/董事长/法人/地区）"
                "+ classifier BASIC_ORGINFO（board/main_business，零重复抓取——BASIC_ORGINFO 已由 classifier 抓取）。顶层独立扁平 slot（无 .data. 中缀、非时间序列、无 latest_period）。"
                "schema_coverage 方向(b) 因无 .data. 中缀跳过（同 classification）。不入 _INFRA_TOP（向B 由 SCENES 登记覆盖）。",
    },

    "s4_technical": {
        # fetch_technical（runner.py:1407）：westock technical/chip + technical_signals + td_analyzer + 形态加工
        # 加工前置：fibonacci/支撑压力/量价/筹码判定 在拉取层算好，snapshot 存变量+值，报告只消费不算
        # signals 信封（technical_signals.py）：westock technical_series 历史序列 → 结构化 events/state
        # 三态信封（仿 lhb/northbound）：ok / never_traded（北交/港股/指标全None 豁免）/ failed
        "fetcher": "fetch_technical",
        "mode": ["A", "B"],
        "produces": [
            {"path": "data.technical",          "confidence": CONFIRMED, "note": "westock technical 9族（ma/macd/kdj/rsi/boll/bias/wr/dmi/other），腾讯源无限流"},
            {"path": "data.chip",               "confidence": CONFIRMED, "note": "westock chip 筹码（chipProfitRate/chipAvgCost/集中度 + latest_period 信封 + cost_pressure/underwater_pct 派生），北交/港股 None"},
            {"path": "data.td",                 "confidence": CONFIRMED, "note": "td_analyzer：Setup/Countdown/TDST/PriceFlip/Confluence/趋势过滤/回测/summary（零网络，从 s2 close 算）"},
            {"path": "data.fibonacci",          "confidence": CONFIRMED, "note": "加工前置：swing high/low + 6 回撤位 + 当前回撤位%"},
            {"path": "data.support_resistance", "confidence": CONFIRMED, "note": "加工前置：5层（压力1/2 + 第一/强/深度支撑）带价位区间+依据"},
            {"path": "data.volume_price",       "confidence": CONFIRMED, "note": "加工前置：双口径量价（realtime vr + daily v/ma20）+ 背离 + turnover MA"},
            {"path": "data.chip_behavior",      "confidence": CONFIRMED, "note": "加工前置：跨场景筹码判定（派发/吸筹/洗盘/中性）"},
            {"path": "data.signals",            "confidence": CONFIRMED, "note": "technical_signals：westock technical_series 历史序列→结构化 events(金叉/死叉/缺口/触轨)+state(macd/kdj/rsi/ma/boll态)+latest_period，三态 ok/degraded/never_traded"},
        ],
        "consumers": {
            "data.technical":          ["m3-technical", "m6-decision", "G1"],       # m3 §3.2/3.5 技术指标、m6 矩阵、G1 技术词消费
            "data.chip":               ["m3-technical", "m6-decision", "m7-risk", "G41"],  # 筹码分布（chipAvgCost=成本压力位→m6/m7止损、chipProfitRate/集中度、G41 消费校验）
            "data.td":                 ["m3-technical", "m6-decision", "G1", "G14"],  # m3 §3.1 TD、G14 数据驱动 setup≥9
            "data.fibonacci":          ["m3-technical", "G40"],                     # §3.4 斐波那契 + G40 渲染校验
            "data.support_resistance": ["m3-technical", "m6-decision", "m7-risk", "G40"],  # §3.3 五层支撑压力 + m6/m7 止损价位 + G40
            "data.volume_price":       ["m3-technical", "m6-decision"],             # 量价配合（四镜头之量价领先）
            "data.chip_behavior":      ["m6-decision"],                             # 主力行为四联判定
            "data.signals":            ["m3-technical", "m6-decision", "m7-risk", "G40"],  # m3 直读 state/events、m6/m7 止损收紧、G40 消费校验
        },
        "priority": P1,
        "cost": {"calls": 3, "latency": "medium"},   # westock technical/chip/technical_series 3次 CLI（td/fibonacci/支撑压力/量价/筹码判定 零网络从 s2 算）
        "depends_on": ["s2_quote_kline"],
        "fallback": {},
        "cacheable": True,
        "derived": True,
    },

    "s_stock_evaluation": {
        # fetch_stock_evaluation（runner.py）：4 东财 datacenter-web 端点 + akshare 序列 + s_margin
        # → processed.conclusions[]「结论一等公民」（券商原文一字不改，用户定调）。
        # 三态 ok/missing(金融股·次新·非标的无千股千评,真空)/failed；G61 四段守护 fetch→store→read→consume。
        "fetcher": "fetch_stock_evaluation",
        "mode": ["A"],
        "produces": [
            {"path": "data.processed.conclusions", "confidence": CONFIRMED,
             "note": "千股千评结论一等公民（券商原文）：控盘程度(STOCKEVALUATE.PARTICIPATE_TYPE_CN)/"
                     "综合结论(CUSTOM_PK.WORDS_EXPLAIN 主力资金动向·severity=warning if 流出/大幅)/"
                     "趋势量能(TRENDVOLUME.COMMENT_TXT 含支撑/压力位)/融资杠杆(s_margin+MARGIN_EXPLAIN 两融资格)。"
                     "字段 dimension/text/severity/source_api/evidence，G61 段④ force-surface 每条 ok 结论。"},
            {"path": "data.processed.metrics", "confidence": CONFIRMED,
             "note": "支撑数字：control_tier/org_participate(0-1 控盘度)/prime_cost_1d·20d/prime_inflow/"
                     "total_score/rise_prob/rank_ratio/support·resistance(券商位)/finance_value_yi/akshare(评分·关注·意愿,标延迟日期)"},
            {"path": "data.processed.latest_period", "confidence": CONFIRMED,
             "note": "千股千评最新交易日信封（period_type=day，value={control_tier}，summary 头条=控盘程度·主力资金动向）。"
                     "ok→信封 / missing·failed→None；G61 段② 据此判格式完整性。"},
            # data.raw（stockevaluate/custom_pk/trendvolume/margin_explain/s_margin 全行）加法式存储供审计追溯，
            # 非契约 produce（无消费者，按 lhb/s1 惯例不声明，避免 orphan 误报）。
        ],
        "consumers": {
            "data.processed.conclusions":   ["m4", "m6", "m7", "G61"],
            "data.processed.metrics":       ["m4", "m7"],
            "data.processed.latest_period": ["G61"],
        },
        "priority": P2,
        "cost": {"calls": 5, "calls_worst": 9, "latency": "medium", "throttle_prone": True},
        "depends_on": [],
        "fallback": {},
        "cacheable": True,
        "note": "千股千评·主力控盘「结论一等公民」。4 东财 datacenter-web 端点(STOCKEVALUATE/CUSTOM_PK/"
                "TRENDVOLUME 用 sort_columns=TRADE_DATE；MARGIN_EXPLAIN 用 sort_columns='')+akshare 序列+s_margin。"
                "三坑：filter_col=SECURITY_CODE+裸码 / sort_columns 差异 / 读 r['rows']。"
                "⚠️ 机构参与度口径冲突：STOCKEVALUATE.ORG_PARTICIPATE=0-1 控盘度 vs akshare zlkp=0-100 参与分值（同名不同物，metrics 区分标注）。"
                "有意不进 gate _EXPECTED_SCENES（同 lhb/northbound，self-score 分母不变）。",
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
