#!/usr/bin/env python3
"""trade_sheet 视图单测（S4a Step3 验收；plan A3）。

覆盖：
- 行集结构：卖出（减仓带 LLM 位 + 止损链 + ATR）/ 买（rebound_spec 直通 + S8 分级）/
  参考（DSNH/DSNL）/ 缺档降级
- 价位照抄断言：行价位与 S&R layers/stops 完全一致（禁改禁四舍五入）
- 事件日历权威度分级（实锤/待证/不入）
- b_head v3 渲染：4 行状态头 + 无三情景表 + conditional_winrate 注入
- 空快照降级（status=empty / missing 不炸）

运行：python3 regression-tests/test_trade_sheet_view.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/.hermes/skills/stock-analysis/financial-data-routing"))
import report_views as rv  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        FAILS.append(name)
        print(f"  ✗ {name} {detail}")


def fixture_snapshot():
    """构造最小 B 快照（字段形态对齐真实 runner 产出）。"""
    return {
        "mode": "B",
        "s2_quote_kline": {"data": {
            "realtime_quote": {"current": 24.4, "change_pct": 3.79, "turnover": 6.4},
            "daily_kline": {"data_full": [
                {"date": f"2026-09-{d:02d}", "close": 24.0 + d * 0.01, "open": 24.0,
                 "high": 24.5 + d * 0.01, "low": 23.8, "amount": 5e8, "turnover": 0.02}
                for d in range(1, 31)
            ]},
        }},
        "s4_technical": {"data": {
            "atr": {"atr14": 1.0, "atr_stop": 22.4},
            "short_term_enrich": {
                "direction_forecast": {
                    "direction": "neutral", "confidence": "NEUTRAL", "rule_name": None,
                    "horizon_days": 15,
                    "expected_range": {"low": 21.983, "high": 26.817},
                },
                "risk_control": {
                    "kelly": {"kelly_fraction": 0.0, "capped_at": 0.25},
                    "stops": [
                        {"level": "h60_ma60", "price": 24.898, "rule": "60m MA60 得失"},
                        {"level": "daily_ma20", "price": 24.508, "rule": "日MA20-2%×2日"},
                    ],
                    "atr": {"atr_stop": 22.4},
                },
                "state_tuple": {"trend_state": "down", "regime": "trend_down",
                                 "strength": "divergent", "structure": "amplified",
                                 "structure_tier": "mid"},
                "p3_signals": {"dsnh_days": 7, "dsnl_days": 4,
                                "s8_buy_plus_grade": None,
                                "dsnh_sell_hint": True, "dsnl_bottom_hint": False},
                "fund_sustain": {"pos_days_7": 5, "verdict": "sustained"},
            },
            "support_resistance": {"layers": [
                {"name": "压力2", "price": 25.01, "direction": "up"},
                {"name": "压力1", "price": 24.62, "direction": "up"},
                {"name": "强支撑", "price": 23.33, "direction": "down"},
            ]},
        }},
        "s3_fund_flow": {"data": {"fund_flow": {"net_flow": 3.45, "daily_history": [
            {"date": f"2026-09-{d:02d}", "main_net": 1e8 if d % 2 else -5e7} for d in range(1, 11)
        ]}}},
        "web_research_findings": {"items": [
            {"topic": "公告", "value": "公司公告披露减持计划，深交所 szse.cn 见",
             "url": "http://www.szse.cn/x"},
            {"topic": "传闻", "value": "球友称订单传闻待证实", "url": "https://xueqiu.com/x"},
        ]},
    }


print("== trade_sheet 行集 ==")
snap = fixture_snapshot()
v = rv.build_trade_sheet_view(snap)
check("status=ok", v.get("status") == "ok")
sides = [r["side"] for r in v["rows"]]
check("有卖行", "卖" in sides)
check("无买行（neutral 无 rebound_spec）", "买" not in sides or
      all("提示" in r["type"] for r in v["rows"] if r["side"] == "买"))
# 价位照抄：减仓带价 = S&R up 层价
band_prices = [r["price"] for r in v["rows"] if "减仓带" in r["type"]]
check("减仓带价照抄 layers", band_prices == [25.01, 24.62], band_prices)
stop_prices = [r["price"] for r in v["rows"] if "止损档" in r["type"]]
check("止损档价照抄 stops", stop_prices == [24.898, 24.508], stop_prices)
check("每行有失效条件", all(r.get("invalidation") for r in v["rows"]))
check("每行有确认规则", all(r.get("confirm_rule") for r in v["rows"]))
# DSNH 提示行
check("DSNH 卖区提示行在档", any("DSNH" in (r["type"] or "") for r in v["rows"]))
# 资金持续性
check("fund_sustain 透传", v.get("fund_sustain", {}).get("verdict") == "sustained")

print("== 事件日历权威度分级 ==")
ec = v.get("event_calendar") or []
check("日历 1 条（仅公告级）", len(ec) == 1, ec)
check("实锤分级", ec and ec[0].get("grade") == "实锤", ec)
check("传闻不入日历", all("传闻" not in (e.get("text") or "") for e in ec))

print("== rebound_spec 买行（dn 触发态） ==")
snap["s4_technical"]["data"]["short_term_enrich"]["direction_forecast"] = {
    "direction": "bull", "confidence": "MED", "rule_name": "dn_oversold",
    "probability": 0.64, "horizon_days": 15,
    "conditional_winrate": {"win_rate": 0.608, "n": 102, "as_of": "2026-10-03"},
    "rebound_spec": {
        "entry_band": {"low": 23.5, "high": 23.6}, "entry_mode": "回踩限价（触发后 5 个交易日内触及有效）",
        "ladder": {"take_profit": "+8%", "stop": "-8%"},
        "invalidation": "收盘跌破强支撑或 ATR 止损则 spec 失效",
        "confirmator": "触发后 5 日内收盘站上压力带 → 反弹升级确认"},
}
v2 = rv.build_trade_sheet_view(snap)
buy_rows = [r for r in v2["rows"] if r["side"] == "买" and "入场带" in (r["type"] or "")]
check("买行在档（rebound_spec 直通）", len(buy_rows) == 1)
check("买行价位 = entry_band", buy_rows and buy_rows[0]["price"] == "23.5~23.6")
check("买行带条件胜率", buy_rows and buy_rows[0].get("conditional_winrate", {}).get("win_rate") == 0.608)

print("== 空快照降级 ==")
v3 = rv.build_trade_sheet_view({"mode": "B", "s2_quote_kline": {"data": {}}})
check("空快照 status 不炸（empty/ok）", v3.get("status") in ("ok", "empty"), v3.get("status"))

print("== b_head v3 渲染 ==")
bh = rv.build_b_head_view(snap)
md = bh.get("head_draft_md") or ""
check("v3 标题=交易计划", "## 交易计划" in md, md[:60])
check("无三情景表", "| 情景 |" not in md)
check("条件胜率注入", ("条件胜率" in md) or ("无方向置信" in md))
check("数字禁改提示在档", "禁改禁四舍五入" in md)

print()
if FAILS:
    print(f"FAIL {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL PASS")
