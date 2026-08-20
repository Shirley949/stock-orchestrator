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
  python snapshot_view.py <snap.json> --list       # 列出可用视图与状态
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
    "news":      ("s5_events", "data", "news", "report_view"),
    "events":    ("s5_events", "data", "risk_signals", "report_view"),
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


PRINTERS = {
    "kline": _print_kline, "cash_flow": _print_cash, "income": _print_income,
    "mainfina": _print_mainfina, "news": _print_news, "events": _print_events,
    "holder": _print_holder,
}


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
    ap.add_argument("view", nargs="?", choices=list(VIEW_PATHS), help="视图名")
    ap.add_argument("--list", action="store_true", help="列出可用视图与状态")
    ap.add_argument("--raw", metavar="PATH", help="兜底：任意 raw 路径直读（如 s1_financial.data.cash_flow.data.0）")
    args = ap.parse_args()

    snap = json.load(open(args.snapshot))

    if args.list or not args.view:
        print(f"snapshot: {args.snapshot}  code={snap.get('stock_code')} ts={snap.get('timestamp')}")
        for name, path in VIEW_PATHS.items():
            v = _walk(snap, ".".join(path))
            st = v.get("status") if isinstance(v, dict) else "❌ 未挂载"
            print(f"  {name:10s} {st}")
        return

    view = _walk(snap, ".".join(VIEW_PATHS[args.view]))
    if not isinstance(view, dict):
        print(f"❌ 视图未挂载（snapshot 可能是旧版 runner 产出）: {args.view}", file=sys.stderr)
        sys.exit(1)
    PRINTERS[args.view](view)

    if args.raw:
        val = _walk(snap, args.raw)
        print(f"\n--raw {args.raw} =")
        print(json.dumps(val, ensure_ascii=False, indent=1)[:4000])


if __name__ == "__main__":
    main()
