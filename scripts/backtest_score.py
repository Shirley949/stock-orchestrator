#!/usr/bin/env python3
"""盲测评分（plan §7）：读模式B报告 forecast block（LLM 转述层）→ 拉 T+1~今天日K
→ 5/10/15d 方向命中判定 → 汇总 JSON。

用法：
  python3 backtest_score.py <report.md> [--as-of 2026-08-05]
  python3 backtest_score.py --aggregate <score_json>...      # 汇总多票

判定规则（与引擎语义一致）：
  bull   → ret_H > 0 命中
  bear   → ret_H < 0 命中
  neutral → |ret_H| ≤ 预期区间半宽（expected_range 缺席时用 ±2%）命中
  insufficient_history / failed → 不计分母（产品行为测试，非方向错误）
验收线：HIGH 置信层 15d 方向命中 ≥70%（用户 2026-08-26 拍板）。
"""
import json
import re
import sys
import os

sys.path.insert(0, "/home/ubuntu/.hermes/skills/stock-analysis/stock-orchestrator/scripts/lib")
sys.path.insert(0, "/home/ubuntu/.hermes/skills/stock-analysis/financial-data-routing")


def parse_forecast_block(report_path: str) -> dict:
    """报告 md → forecast block dict（```json {direction_15d...} ``` 代码块）。"""
    text = open(report_path, encoding="utf-8").read()
    # forecast block：含 direction_15d 键的 json 代码块
    for m in re.finditer(r"```json\s*(\{.*?\})\s*```", text, re.S):
        try:
            blk = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if "direction_15d" in blk:
            return blk
    return {}


def fetch_future_closes(stock_code: str, as_of: str):
    """T+1~今天收盘序列（全史 stock_zh_a_daily → > as_of 切片）。返回 (dates, closes)。"""
    from runner import fetch_with_fallback, _format_daily_symbol
    env, _w = fetch_with_fallback("stock_zh_a_daily", {"symbol": _format_daily_symbol(stock_code)})
    if env.get("status") not in ("ok", "cached"):
        return [], []
    rows = env.get("data", env.get("data_full", []))
    fut = [(str(r.get("date", ""))[:10], float(r["close"]))
           for r in rows
           if isinstance(r, dict) and r.get("close") is not None
           and str(r.get("date", ""))[:10] > as_of]
    return [d for d, _ in fut], [c for _, c in fut]


def score_one(report_path: str, stock_code: str = None, as_of: str = None) -> dict:
    blk = parse_forecast_block(report_path)
    if not blk:
        return {"report": report_path, "error": "forecast block 未找到（报告缺 m6 收口 JSON）"}
    # stock_code/as_of 可从文件名或参数推；显式参数优先
    if not stock_code:
        m = re.search(r"(\d{6})", os.path.basename(report_path))
        stock_code = m.group(1) if m else None
    if not as_of:
        m = re.search(r"asof[_-](\d{8})", report_path)
        as_of = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else None
    if not stock_code or not as_of:
        return {"report": report_path, "error": f"stock_code/as_of 不可推 ({stock_code}, {as_of})，需显式传"}

    d15 = blk.get("direction_15d") or {}
    direction = d15.get("direction")
    confidence = d15.get("confidence")
    probability = d15.get("probability")
    status = d15.get("status")
    if status in ("insufficient_history", "failed") or direction is None:
        return {"stock": stock_code, "as_of": as_of, "direction": direction,
                "confidence": confidence, "scored": False,
                "reason": f"不计分母: status={status} direction={direction}"}

    dates, closes = fetch_future_closes(stock_code, as_of)
    base = closes[-1] if not dates else None  # placeholder, base 从 as_of 收盘取
    # base = as_of 当日收盘（future[0] 的前一根）；全史里再取一次
    from runner import fetch_with_fallback as _fw, _format_daily_symbol as _fs
    env, _ = _fw("stock_zh_a_daily", {"symbol": _fs(stock_code)})
    rows = env.get("data", env.get("data_full", []))
    base_rows = [float(r["close"]) for r in rows
                 if isinstance(r, dict) and r.get("close") is not None
                 and str(r.get("date", ""))[:10] <= as_of]
    if not base_rows or not closes:
        return {"stock": stock_code, "as_of": as_of, "error": "日K数据不足（base/future 空）"}
    base = base_rows[-1]

    out = {"stock": stock_code, "as_of": as_of, "direction": direction,
           "confidence": confidence, "probability": probability,
           "base_close": base, "scored": True}
    er = (blk.get("expected_range") or {}) or \
         (d15.get("expected_range") if isinstance(d15.get("expected_range"), dict) else {})
    half_width = None
    if isinstance(er, dict) and er.get("low") is not None and er.get("high") is not None:
        half_width = (er["high"] - er["low"]) / 2
    hits = {}
    for h in (5, 10, 15):
        if len(closes) >= h:
            ret = closes[h - 1] / base - 1
            if direction == "bull":
                hit = ret > 0
            elif direction == "bear":
                hit = ret < 0
            else:  # neutral：|ret| ≤ 半宽（缺席 ±2%）
                hw = half_width if half_width is not None else 0.02
                hit = abs(ret) <= hw
            hits[f"{h}d"] = {"ret": round(ret, 4), "hit": bool(hit),
                             "eval_date": dates[h - 1], "close": closes[h - 1]}
        else:
            hits[f"{h}d"] = {"hit": None, "reason": f"未来数据不足({len(closes)}<{h})"}
    out["hits"] = hits
    return out


def aggregate(scores: list) -> dict:
    """按置信层汇总命中率（None hit 不计；scored=False 不计分母）。"""
    agg = {}
    for layer in ("HIGH", "MED", "NEUTRAL"):
        rows = [s for s in scores if s.get("scored") and s.get("confidence") == layer]
        if not rows:
            continue
        for h in ("5d", "10d", "15d"):
            vals = [r["hits"][h]["hit"] for r in rows if r.get("hits", {}).get(h, {}).get("hit") is not None]
            if vals:
                agg[f"{layer}_{h}"] = {"n": len(vals), "hits": sum(vals),
                                       "rate": round(sum(vals) / len(vals), 4)}
    unscored = [{"stock": s.get("stock"), "reason": s.get("reason") or s.get("error")}
                for s in scores if not s.get("scored")]
    return {"per_layer": agg, "acceptance": "HIGH 15d ≥70%",
            "high_15d_pass": agg.get("HIGH_15d", {}).get("rate", 0) >= 0.70,
            "unscored": unscored, "n_total": len(scores)}


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    if args[0] == "--aggregate":
        scores = []
        for p in args[1:]:
            obj = json.load(open(p))
            scores.extend(obj if isinstance(obj, list) else [obj])
        print(json.dumps(aggregate(scores), ensure_ascii=False, indent=2))
        return
    report = args[0]
    stock = as_of = None
    if "--stock" in args:
        stock = args[args.index("--stock") + 1]
    if "--as-of" in args:
        as_of = args[args.index("--as-of") + 1]
    result = score_one(report, stock, as_of)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
