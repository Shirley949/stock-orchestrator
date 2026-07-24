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


def _scene_has_data(val) -> bool:
    """判断 scene 值是否真有数据（envelope status / data·data_full / 空数组）。与 gate_definitions 同语义。"""
    if val is None:
        return False
    if isinstance(val, str):
        return val.strip() != ""
    if isinstance(val, dict):
        if val.get("status") in ("failed", "error", "throttled"):
            return False
        dd = val.get("data", val.get("data_full"))
        if isinstance(dd, dict):
            if dd.get("status") in ("failed", "error", "throttled"):
                return False
            return bool(dd)
        if isinstance(dd, list):
            return len(dd) > 0
        if val.get("status") in ("ok", "partial"):
            return True
        if "error" in val and "status" not in val and "data" not in val:
            return False
        return bool(val)
    if isinstance(val, list):
        return len(val) > 0
    return bool(val)


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

QUANT_KW = {t: kw for t, _, kw in QUANT_THEMES}
QUAL_KW = {t: kw for t, kw in QUAL_THEMES}


# 信号覆盖维度（G30#1 信号驱动覆盖的数据源）：读各 signal-envelope scene 的 processed，
# 收集 critical 码 → present_signals（数据驱动，真空票自动豁免）。每码配**精确词**（拒 K线/换手冒充）。
# (processed 路径, 取码子键, critical 码集, {code: (name, precise_kws)})
_SIGNAL_SOURCES = [
    ("s5_events.data.risk_signals.processed", "risk",
     ("M1", "M4", "M5", "M8"),
     {"M1": ("股东减持", ("减持", "股东减持")),
      "M4": ("违规/诉讼", ("违规", "处罚", "立案调查", "监管处罚")),
      "M5": ("ST/退市", ("ST", "退市", "*ST")),
      "M8": ("业绩下修", ("预减", "预亏", "首亏", "续亏", "计损", "减值"))}),
    ("s8_a_share.data.shareholder_count.processed", "signals",
     ("S2", "S7"),
     {"S2": ("高位派发", ("派发", "高位派发")),
      "S7": ("筹码急剧分散", ("筹码分散", "急剧分散", "筹码松动"))}),
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


def panorama(data: dict) -> dict:
    """读 snapshot → 证据全景结构（只抽值，不映射概率/方向）。"""
    out = {
        "present_quant": [], "gap_quant": [],
        "qual_required": [t for t, _ in QUAL_THEMES],
        "values": {}, "interpretation_flags": [], "draft_lines": [],
        "present_signals": [],
        "stock_type": _snapshot_get(data, "classification.primary_type") or _snapshot_get(data, "stock_type"),
    }

    for theme, paths, _ in QUANT_THEMES:
        present = any(_scene_has_data(_snapshot_get(data, p)) for p in paths)
        (out["present_quant"] if present else out["gap_quant"]).append(theme)

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

    # §2.2 主营构成三维 + 跨维派生信号（m6 Layer1「主营构成」行 + m6/m7 risk_register 解耦）
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

    rr = _snapshot_get(data, "computed_metrics.risk_register") or []
    if isinstance(rr, list) and rr:
        out["values"]["risk_register"] = rr   # severity 排序；m6 悲观情景挑 top，m7 §7.1 叙事

    # 重大事件（M 风险 / P 利好 双桶）——G30#1 信号覆盖数据层 + capstone 悲观/乐观打分素材。
    mat = _snapshot_get(data, "s5_events.data.risk_signals.processed")
    if isinstance(mat, dict) and mat.get("status") == "ok" and (mat.get("risk") or mat.get("catalyst")):
        risk_sigs = mat.get("risk") or []
        cat_sigs = mat.get("catalyst") or []
        crit_codes = (mat.get("aggregates") or {}).get("critical_codes") or []
        out["values"]["material_events"] = {
            "summary": mat.get("summary"), "signal_type": mat.get("signal_type"),
            "risk": risk_sigs, "catalyst": cat_sigs, "critical_codes": crit_codes,
            "latest_period": mat.get("latest_period"),
        }
        # critical 风险（M1/M4/M5/M8…）→ 前置「⚠️关键风险信号」段（经 _CRITICAL_KW 命中）
        for s in risk_sigs:
            if s.get("severity") == "critical":
                out["interpretation_flags"].append(
                    f"关键风险信号·{s.get('name')}：{s.get('evidence')} → 悲观情景核心驱动，须高亮")

    # present_signals（G30#1 信号驱动覆盖）：遍历 _SIGNAL_SOURCES，收集实际存在的 critical 码。
    for path, subkey, crit_codes, code_map in _SIGNAL_SOURCES:
        proc = _snapshot_get(data, path)
        if not isinstance(proc, dict):
            continue
        sigs = proc.get(subkey) or proc.get("signals") or []
        present = {s.get("code") for s in sigs if isinstance(s, dict)}
        for code in crit_codes:
            if code in present:
                name, kws = code_map[code]
                out["present_signals"].append(
                    {"source": path, "code": code, "name": name, "kws": list(kws)})

    vs = _snapshot_get(data, "valuation_snapshot.data") or {}
    if isinstance(vs, dict):
        tp = vs.get("targetPrice")
        ar = vs.get("analystRating")
        if isinstance(tp, dict) and tp.get("average"):
            out["values"]["targetPrice"] = tp.get("average")
        if isinstance(ar, dict) and ar.get("institutionCnt"):
            out["values"]["analystRating"] = f"买入{ar.get('buy_ratio', 0):.0f}%/机构{ar.get('institutionCnt')}家"

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
    if not (v.get("targetPrice") or v.get("analystRating")):
        return
    L.append(f"- 估值/前瞻：目标价 {v.get('targetPrice','—')}，评级 {v.get('analystRating','—')}。")


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


def _render_material_events(L, v):
    """重大事件（M 风险 / P 利好 双桶）——G30#1 信号覆盖数据层 + capstone 悲观/乐观打分素材。

    数据驱动：悲观情景读风险桶（减持/违规/ST/下修…），乐观情景读利好桶（增持/回购/分红/上修…），
    取代散文脑补。严重风险经 interpretation_flags→_CRITICAL_KW 前置「⚠️关键风险信号」段。
    """
    m = v.get("material_events")
    if not m:
        return
    risk = m.get("risk") or []
    cat = m.get("catalyst") or []
    parts = []
    if risk:
        crit = [f"{s.get('name')}({(s.get('evidence') or '')[:14]})" for s in risk
                if s.get("severity") == "critical"]
        parts.append(f"风险{len(risk)}类" + (f"，高危：{'、'.join(crit[:3])}" if crit else ""))
    if cat:
        parts.append(f"利好{len(cat)}类：{'、'.join(s.get('name', '') for s in cat[:4])}")
    if parts:
        L.append("- 重大事件：" + "；".join(parts) + "。（悲观读风险桶、乐观读利好桶）")


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
    """同业对比（s11_peer：target + ≤3 peer 核心6）——G30#1 反片面硬维度·同业对比。

    横截面·各股取各自最新报告期（jiankuang date，如 '2026一季报'）；peer 由独立
    `runner.py peer` 模式拉取后合并，A 模式快照常缺 → status=missing 时提示先跑 peer 模式。
    """
    p = v.get("peer")
    if not p:
        return
    st = p.get("status")
    if st == "missing":
        L.append("- 同业对比：未拉取（status=missing）。⚠️ 须先 websearch 定 peer 码、跑 "
                 "`runner.py peer` 模式合并，再写本维度（防 G30#1 反片面遗漏）。")
        return
    rp = p.get("target_report_period")
    L.append(f"- 同业对比（status={st}，{p.get('peers_count', 0)} 家）{f'（{rp}）' if rp else ''}：")
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
    "asset_safety": _render_asset_safety,
    "valuation": _render_valuation,
    "segment": _render_segment,
    "peer": _render_peer,
    "outlook": _render_outlook,
    "lhb": _render_lhb,
    "northbound": _render_northbound,
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
    L.append("- 定性（你须从 m1–m9 叙事提炼，机械模型丢失的关键）：护城河 / 治理战略 / 前瞻催化。")
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
    m = re.search(r"^#{1,4}\s.*(?:综合研判|情景|三档|概率|研判)", report, re.MULTILINE)
    if not m:
        return report
    return report[m.start():]


def _top_scenario(cap: str):
    """最高概率情景 (label, prob)，锚定行首情景声明。"""
    hdrs = list(re.finditer(
        r"^[ \t]*[#*|\-]*[ \t]*(乐观|基准|中性|悲观)[^%\n]{0,15}?(\d+(?:\.\d+)?)\s*%", cap, re.MULTILINE))
    if not hdrs:
        return None
    return max(((m.group(1), float(m.group(2))) for m in hdrs), key=lambda x: x[1])


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
          f"定性须覆盖: {pan['qual_required']}]")
    if args.report:
        rpt = Path(args.report).read_text(encoding="utf-8")
        adv = panorama_advisory(rpt, data)
        print("\n--- #7 软一致性提示（不计入 gate，仅请复核）---")
        print("\n".join(adv) if adv else "（无）")


if __name__ == "__main__":
    main()
