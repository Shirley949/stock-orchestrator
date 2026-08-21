#!/usr/bin/env python3
"""snapshot_view.py — snapshot 报告视图直出 CLI（写报告时的数据读取唯一入口）。

用法：
  python snapshot_view.py <snap.json> kline        # K线：recent30 desc + stats250d
  python snapshot_view.py <snap.json> cash_flow    # 现金流 12 期（FCF/CFO净利比已算）
  python snapshot_view.py <snap.json> income       # 利润表 12 期（毛利率/同比已算）
  python snapshot_view.py <snap.json> mainfina     # 主要指标 8 期（单季同比/ROIC/偿债）
  python snapshot_view.py <snap.json> news         # 新闻 high+medium 标题级
  python snapshot_view.py <snap.json> events       # 大事提醒投影（权威=processed.timeline）
  python snapshot_view.py <snap.json> holder       # 股东户数信号期
  python snapshot_view.py <snap.json> balance      # 资产负债表 4 期 × 关键科目（亿元）
  python snapshot_view.py <snap.json> timeline     # 事件时间线五桶 + 买卖压力 + 股东动态
  python snapshot_view.py <snap.json> technical    # 技术面全维度（MA/TD/支撑压力/fib/筹码/ATR）
  python snapshot_view.py <snap.json> valuation    # 估值锚 + 分位 + 评级/目标价 + EV
  python snapshot_view.py <snap.json> consensus    # 一致预期（annual/时序/实绩/指引）
  python snapshot_view.py <snap.json> peer         # 同业对比（items 指标表 + 排名 + 中值）
  python snapshot_view.py <snap.json> annual       # 年报维度（分红/前十大/客户供应商/员工）
  python snapshot_view.py <snap.json> --list       # 列出可用视图与状态
  python snapshot_view.py <snap.json> any <scene或路径> [--depth 2]  # 任意节键树探查（扁平小节首选）
  python snapshot_view.py <snap.json> --raw a.b.c  # 兜底：任意 raw 路径直读（视图缺数据时）

设计（2026-08-20）：视图由 runner 落盘时挂载（report_views.attach_report_views），
本 CLI 只做「格式化直出」——LLM 一条命令拿到已裁剪/已反转/已换算的紧凑表格，
禁止再手写提取脚本。输出对齐文本表（人读友好 + token 紧凑）。
"""
import argparse
import json
import sys

# 视图名 → snapshot 内路径（加法式挂载点，单一真相源=report_views.attach_report_views）
VIEW_PATHS = {
    "kline":     ("s2_quote_kline", "data", "daily_kline", "report_view"),
    "cash_flow": ("s1_financial", "data", "cash_flow", "report_view"),
    "income":    ("s1_financial", "data", "income_statement", "report_view"),
    "mainfina":  ("s1_financial", "data", "mainfinadata", "report_view"),
    "balance":   ("s1_financial", "data", "balance_sheet", "report_view"),
    "news":      ("s5_events", "data", "news", "report_view"),
    "events":    ("s5_events", "data", "risk_signals", "report_view"),
    "timeline":  ("s5_events", "data", "risk_signals", "processed", "report_view"),
    "technical": ("s4_technical", "data", "report_view"),
    "valuation": ("valuation_snapshot", "data", "report_view"),
    "consensus": ("consensus_forecast", "data", "report_view"),
    "peer":      ("s11_peer", "data", "report_view"),
    "annual":    ("s36_annual_analysis", "data", "report_view"),
    "holder":    ("s8_a_share", "data", "shareholder_count", "report_view"),
}

# 各视图表格列（列名, 取值键/取值函数）
def _fmt(v):
    if v is None or v is False:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 1e12 else f"{v:,.4g}"
    return str(v)


def _table(headers, rows):
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
              for i, h in enumerate(headers)]
    line = lambda cells: " | ".join(c.ljust(w) for c, w in zip(cells, widths))
    sep = "-+-".join("-" * w for w in widths)
    return [line(headers), sep] + [line(r) for r in rows]


def _print_kline(v):
    print(f"## K线视图 rows_total={v.get('rows_total')} window={v.get('window')} status={v.get('status')}")
    s = v.get("stats") or {}
    print("\n[stats]")
    for k in ("close_latest", "high_52w", "low_52w", "dist_52w_high_pct", "dist_52w_low_pct",
              "ytd_high", "ytd_low", "ytd_chg_pct", "avg_amount_20d_亿", "max_amount_60d_亿"):
        print(f"  {k:22s} = {_fmt(s.get(k))}")
    rec = v.get("recent") or []
    print(f"\n[recent desc rows[0]=最新 共{len(rec)}行]")
    for line in _table(["date", "open", "high", "low", "close", "chg%", "amount亿", "turnover%", "outstanding_share"],
                       [[_fmt(r.get(k2)) for k2 in ("date", "open", "high", "low", "close", "chg_pct",
                                                     "amount_亿", "turnover_pct", "outstanding_share")] for r in rec]):
        print(line)


def _print_period_table(v, cols, n=12):
    print(f"## {v.get('view')} status={v.get('status')} periods={v.get('periods')} "
          f"missing_fields={v.get('missing_fields') or '无'}")
    data = (v.get("data") or [])[:n]
    for line in _table(cols, [[_fmt(r.get(c)) for c in cols] for r in data]):
        print(line)


def _print_cash(v):
    _print_period_table(v, ["报告日", "CFO", "CFI", "CFF", "capex", "FCF",
                            "net_profit", "CFO_NP_ratio_pct", "FCF_NP_ratio_pct", "cash_end",
                            "dep", "amort", "wc_recv", "wc_inv", "wc_pay"])


def _print_income(v):
    _print_period_table(v, ["报告日", "revenue", "revenue_yoy_pct", "np_parent", "np_parent_yoy_pct",
                            "np_deducted", "np_deducted_yoy_pct", "gross_margin_pct",
                            "net_margin_pct", "three_exp", "rd_exp"])


def _print_mainfina(v):
    _print_period_table(v, ["REPORT_DATE", "DJD_TOI_YOY", "DJD_DPNP_YOY", "ROIC", "ROEJQ",
                            "ZCFZL", "LD", "SD", "XSMLL", "XSJLL"], n=8)


def _print_news(v):
    print(f"## news status={v.get('status')} counts={v.get('counts')}")
    items = v.get("items") or []
    for it in items:
        print(f"  {it.get('日期', '—')} [{_fmt(it.get('分类'))}] {_fmt(it.get('标题'))} ({_fmt(it.get('来源'))})")


def _print_events(v):
    print(f"## events(remind投影) count={v.get('count')} timeline_status={v.get('timeline_status')}")
    print(f"  ⚠️ 权威交接: {v.get('authoritative')}")
    for it in (v.get("items") or []):
        print(f"  {it.get('date', '—')} [{_fmt(it.get('code'))}|{_fmt(it.get('type'))}] {str(it.get('content') or '')[:80]}")


def _print_holder(v):
    print(f"## holder status={v.get('status')} signal_type={v.get('signal_type')} summary={v.get('summary')}")
    data = v.get("data") or []
    keys = list(data[0].keys()) if data else []
    for line in _table(keys, [[_fmt(r.get(k)) for k in keys] for r in data]):
        print(line)


# ---------------------------------------------------------------------------
# 7 新视图 printer（2026-08-20 终局版）
# ---------------------------------------------------------------------------

def _print_balance(v):
    print(f"## {v.get('view')} status={v.get('status')} dates={v.get('dates')} unit={v.get('unit')}")
    if v.get("missing_fields"):
        print(f"  missing_fields={v['missing_fields']}")
    m = v.get("matrix") or {}
    dates = v.get("dates") or []
    for line in _table(["科目"] + [str(d) for d in dates],
                       [[k] + [_fmt(x) for x in m.get(k, [])] for k in m]):
        print(line)


def _print_timeline(v):
    print(f"## timeline status={v.get('status')}")
    print(f"  summary: {v.get('summary')}")
    bsp = v.get("buy_sell_pressure") or {}
    sd = v.get("shareholder_dynamics") or {}
    print(f"  买卖压力 verdict={_fmt(bsp.get('verdict'))} | {bsp.get('summary')}")
    print(f"  股东动态 verdict={_fmt(sd.get('verdict'))} | {sd.get('summary')}")
    progs = v.get("programs") or []
    if progs:
        print(f"  programs: {len(progs)} 条")
    for bucket in ("fatal_events", "risk", "catalyst", "future", "historical"):
        rows = v.get(bucket) or []
        print(f"\n[{bucket}] {len(rows)} 条")
        for it in rows:
            print(f"  {it.get('notice_date', '—')} [{_fmt(it.get('event_type_code'))}|{_fmt(it.get('event_type'))}] {str(it.get('content') or '')[:70]}")
    bc = v.get("by_code_count") or {}
    if bc:
        print("\n[by_code 计数] " + " ".join(f"{c}×{n}" for c, n in
              sorted(bc.items(), key=lambda x: -x[1])))


def _print_technical(v):
    print(f"## technical status={v.get('status')}")
    state = v.get("signals_state") or {}
    if state:
        print("\n[信号态]")
        for k, val in state.items():
            print(f"  {k:18s} = {val}")
    t = v.get("technical") or {}
    if t:
        print(f"\n[行情] date={t.get('date')} close={_fmt(t.get('close'))}")
        ma = t.get("ma") or {}
        print("  MA: " + " ".join(f"{k}={_fmt(x)}" for k, x in ma.items()))
        for grp in ("macd", "kdj", "rsi", "boll", "dmi"):
            g = t.get(grp) or {}
            if g:
                print(f"  {grp.upper()}: " + " ".join(f"{k}={_fmt(x)}" for k, x in g.items()))
    for key, label in (("td_summary", "TD日线"), ("weekly_td_summary", "TD周线")):
        s = v.get(key) or {}
        if s:
            print(f"\n[{label}] {s.get('direction')} | {s.get('stage')}")
            kl = s.get("key_levels") or {}
            if kl:
                print("  key_levels: " + " ".join(f"{k}={_fmt(x)}" for k, x in kl.items()))
            if s.get("action_hint"):
                print(f"  hint: {s['action_hint']}")
    sr = v.get("support_resistance_layers") or []
    if sr:
        print("\n[支撑压力]")
        for lay in sr:
            print(f"  {lay.get('name', '—'):6s} {_fmt(lay.get('price'))} ({_fmt(lay.get('range_pct'))}%) ← {lay.get('basis')}")
    fib = v.get("fibonacci") or {}
    if fib.get("levels"):
        print(f"\n[斐波那契] 当前位%={_fmt(fib.get('current_position_pct'))} 最近位={_fmt(fib.get('nearest_level'))}")
        print("  " + " ".join(f"{k}={_fmt(x)}" for k, x in (fib.get("levels") or {}).items()))
    chip = v.get("chip") or {}
    if chip:
        print("\n[筹码] " + " ".join(f"{k}={_fmt(x)}" for k, x in chip.items()))
    for key in ("turnover", "volume_price", "relative_strength", "atr"):
        blk = v.get(key)
        if isinstance(blk, dict):
            print(f"\n[{key}] " + " ".join(f"{k}={_fmt(x)}" for k, x in blk.items()))


def _print_valuation(v):
    print(f"## valuation status={v.get('status')}")
    q = v.get("quote") or {}
    if q:
        print("\n[quote]")
        for k, val in q.items():
            print(f"  {k:18s} = {_fmt(val)}")
    vp = v.get("valuation_percentile") or {}
    for metric, blk in vp.items():
        if isinstance(blk, dict):
            print(f"\n[分位 {metric}]")
            for k, val in blk.items():
                if isinstance(val, dict):  # window_5y/window_all 压成单行
                    print(f"  {k:22s} = " + " ".join(f"{wk}={_fmt(wv)}" for wk, wv in val.items()))
                else:
                    print(f"  {k:22s} = {_fmt(val)}")
    for key in ("analystRating", "targetPrice", "ev_metrics"):
        blk = v.get(key)
        if isinstance(blk, dict):
            print(f"\n[{key}] " + " ".join(f"{k}={_fmt(x)}" for k, x in blk.items()))


def _print_consensus(v):
    print(f"## consensus status={v.get('status')} missing_fields={v.get('missing_fields') or '无'}")
    ann = v.get("annual") or {}
    if ann:
        years = sorted(ann)
        cols = ["指标"] + years
        keys = list(next(iter(ann.values()), {}).keys())
        rows = [[k] + [_fmt(ann[y].get(k)) for y in years] for k in keys]
        print("\n[annual（westock）]")
        for line in _table(cols, rows):
            print(line)
    em = v.get("em_annual") or {}
    if em:
        years = sorted(em)
        keys = list(next(iter(em.values()), {}).keys())
        print("\n[em_annual（东财）]")
        for line in _table(["指标"] + years,
                           [[k] + [_fmt(em[y].get(k)) for y in years] for k in keys]):
            print(line)
    series = v.get("series") or {}
    for name, rows in series.items():
        if rows:
            print(f"\n[{name} 时序]")
            for r in rows:
                print(f"  {r.get('periodStr', '—')} consensusMean={_fmt(r.get('consensusMean'))} analysts={_fmt(r.get('numAnalysts'))}")
    la = v.get("last_actual") or {}
    if la:
        print(f"\n[last_actual] {la.get('period')} " +
              " ".join(f"{k}={_fmt(la.get(k))}" for k in ("eps", "netProfit", "revenue", "ebit")))
    print(f"\n[target_price] {_fmt(v.get('target_price'))}")
    cg = v.get("company_guidance") or {}
    lp = cg.get("latest_period") or {}
    if lp:
        print(f"[company_guidance] status={cg.get('status')} latest={lp.get('period_label', '—')}")


def _print_peer(v):
    print(f"## peer status={v.get('status')} target={v.get('target_code')} "
          f"peers={v.get('peers_count')} valid={v.get('valid_count')} source={v.get('selection_source')}")
    note = v.get("selection_note")
    if note:
        print(f"  note: {note}")
    cols = ["code", "name", "rev_yoy", "np_yoy", "pe", "pb", "roe", "gross_margin"]
    rows = []
    tm = v.get("target_metrics") or {}
    rows.append([str(v.get("target_code") or "本股"), "(target)"] + [_fmt(tm.get(c)) for c in cols[2:]])
    for it in v.get("items") or []:
        m = it.get("metrics") or {}
        rows.append([str(it.get("code", "")), str(it.get("name", ""))] + [_fmt(m.get(c)) for c in cols[2:]])
    print("\n[核心 6 指标]")
    for line in _table(cols, rows):
        print(line)
    tr = v.get("target_rank") or {}
    im = v.get("industry_median") or {}
    if tr:
        print(f"\n[target_rank] growth={_fmt(tr.get('growth'))} valuation={_fmt(tr.get('valuation'))} dupont={_fmt(tr.get('dupont'))}")
    if im:
        print(f"[industry_median] " + " ".join(f"{k}={_fmt(x)}" for k, x in im.items()))
    mp = v.get("market_performance") or {}
    wins = mp.get("windows") or {}
    if wins:
        print(f"\n[相对大盘 {mp.get('board_name', '')} {mp.get('trade_date', '')}]")
        for w, blk in wins.items():
            if isinstance(blk, dict):
                print(f"  {w:4s} " + " ".join(f"{k}={_fmt(x)}" for k, x in blk.items()))


def _print_annual(v):
    print(f"## annual status={v.get('status')} missing_fields={v.get('missing_fields') or '无'}")
    d3 = v.get("D3_dividend") or []
    if d3:
        print(f"\n[D3 分红 {len(d3)} 期]")
        for r in d3:
            print(f"  {r.get('reportEndDate', '—')} {r.get('dividendFlag')}/{r.get('dividendType')} "
                  f"每股={_fmt(r.get('cashDiviRMB'))} 总额={_fmt(r.get('totalCashDiviComRMB'))} {r.get('dividendPlan') or ''}")
    d4 = v.get("D4_top10_holders") or []
    if d4:
        print(f"\n[D4 前十大股东 as-of {v.get('D4_holders_report_date', '—')}]")
        for r in d4:
            print(f"  #{_fmt(r.get('rank'))} {r.get('name', '—')} {_fmt(r.get('ratio'))} {_fmt(r.get('state'))} shares={_fmt(r.get('shares'))}")
    d7 = v.get("D7_custsupp") or {}
    if d7:
        print(f"\n[D7 客户/供应商 top3 as-of {d7.get('report_date', '—')}]")
        for c in d7.get("customers") or []:
            print(f"  客户#{_fmt(c.get('rank'))} 金额={_fmt(c.get('amount'))} 占比={_fmt(c.get('ratio'))}%")
        for s in d7.get("suppliers") or []:
            print(f"  供应商#{_fmt(s.get('rank'))} 金额={_fmt(s.get('amount'))} 占比={_fmt(s.get('ratio'))}%")
    d8 = v.get("D8_staff") or {}
    if d8:
        print(f"\n[D8 员工] total={_fmt(d8.get('total_num'))} 平均薪酬={_fmt(d8.get('avg_salary'))} as-of {d8.get('report_date', '—')}")


# ---------------------------------------------------------------------------
# any 两级探查：任意节键树（深度可调，扁平小节首选读取方式）
# ---------------------------------------------------------------------------

PRINTERS = {
    "kline": _print_kline, "cash_flow": _print_cash, "income": _print_income,
    "mainfina": _print_mainfina, "news": _print_news, "events": _print_events,
    "holder": _print_holder,
    "balance": _print_balance, "timeline": _print_timeline,
    "technical": _print_technical, "valuation": _print_valuation,
    "consensus": _print_consensus, "peer": _print_peer, "annual": _print_annual,
}


def _any_render(node, depth, indent=0, max_len=200):
    pad = "  " * indent
    if isinstance(node, dict):
        for k, val in node.items():
            if isinstance(val, (dict, list)) and depth > 0:
                size = f" x{len(val)}" if isinstance(val, list) else ""
                print(f"{pad}{k} ({type(val).__name__}{size}):")
                _any_render(val, depth - 1, indent + 1, max_len)
            elif isinstance(val, (dict, list)):
                size = f" x{len(val)}" if isinstance(val, list) else f" dict({len(val)}键)"
                print(f"{pad}{k}: {type(val).__name__}{size}")
            else:
                print(f"{pad}{k} = {str(val)[:max_len]}")
    elif isinstance(node, list):
        # 长列表展开上限：>10 项只展开前 10（remind_records x95 全展开实测 77K chars）
        shown = node[:10]
        for i, item in enumerate(shown):
            if isinstance(item, (dict, list)) and depth > 0:
                print(f"{pad}[{i}] ({type(item).__name__} x{len(item)}):")
                _any_render(item, depth - 1, indent + 1, max_len)
            elif isinstance(item, (dict, list)):
                print(f"{pad}[{i}] {type(item).__name__} x{len(item)}")
            else:
                print(f"{pad}[{i}] = {str(item)[:max_len]}")
        if len(node) > len(shown):
            print(f"{pad}… (+{len(node) - len(shown)} more; 用 .N 单条下钻)")


def _walk(obj, path):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def main():
    ap = argparse.ArgumentParser(description="snapshot 报告视图直出")
    ap.add_argument("snapshot", help="snapshot JSON 路径")
    ap.add_argument("view", nargs="?", choices=list(VIEW_PATHS) + ["any"], help="视图名")
    ap.add_argument("target", nargs="?", help="any 模式：scene 名或点分路径（如 s1_financial.data.segment_composition）")
    ap.add_argument("--depth", type=int, default=1, help="any 模式展开深度（默认 1，扁平小节建议 2）")
    ap.add_argument("--list", action="store_true", help="列出可用视图与状态")
    ap.add_argument("--raw", metavar="PATH", help="兜底：任意 raw 路径直读（如 s1_financial.data.cash_flow.data.0）")
    args = ap.parse_args()

    snap = json.load(open(args.snapshot))

    # 独立 --raw 形式（不带视图名）：任意 raw 路径直读（SKILL 文档形式，先于 --list 分支）
    if args.raw and not args.view and not args.list:
        val = _walk(snap, args.raw)
        print(f"--raw {args.raw} =")
        print(json.dumps(val, ensure_ascii=False, default=str)[:4000])
        return

    if args.list or not args.view:
        print(f"snapshot: {args.snapshot}  code={snap.get('stock_code')} ts={snap.get('timestamp')}")
        for name, path in VIEW_PATHS.items():
            v = _walk(snap, ".".join(path))
            st = v.get("status") if isinstance(v, dict) else "❌ 未挂载"
            print(f"  {name:10s} {st}")
        print("  any        <scene或路径> --depth N（任意节键树探查，扁平小节首选）")
        scenes = [k for k in snap if isinstance(snap[k], dict)]
        print("  scenes     " + " ".join(sorted(scenes)) + "  ← any 的目标空间")
        return

    if args.view == "any":
        if not args.target:
            print("❌ any 模式需指定 scene 名或点分路径（如 any computed_metrics / any s1_financial.data.segment_composition --depth 2）",
                  file=sys.stderr)
            sys.exit(1)
        node = _walk(snap, args.target)
        if node is None:
            print(f"❌ 路径不存在: {args.target}", file=sys.stderr)
            sys.exit(1)
        print(f"## any {args.target} --depth {args.depth}")
        _any_render(node, args.depth)
        return

    view = _walk(snap, ".".join(VIEW_PATHS[args.view]))
    if not isinstance(view, dict):
        print(f"❌ 视图未挂载（snapshot 可能是旧版 runner 产出）: {args.view}\n"
              f"   兜底：any {'.'.join(VIEW_PATHS[args.view][:-1])} --depth 2", file=sys.stderr)
        sys.exit(1)
    PRINTERS[args.view](view)

    if args.raw:
        val = _walk(snap, args.raw)
        print(f"\n--raw {args.raw} =")
        print(json.dumps(val, ensure_ascii=False, indent=1)[:4000])


if __name__ == "__main__":
    main()
