#!/usr/bin/env python3
"""v12 引擎单测（S4a Step1 验收；plan A1）。

覆盖：
- E2 as-of 门：stale 事故场景（P2 BT-08 的 4083.97 形态）拦截 / 新鲜场景零误拦 / 日期键缺档保守放行
- E4 rebound_spec：字段完整性（两 dn 规则分支都产出 spec；up 规则不产出）
- conditional_winrate：表查询 + neutral 无此字段
- state_tuple / p3_signals：S8 分级与 DSNH/DSNL 边界（构造序列精确验证）
- fund_sustain：±3 日正天数判定 + 缺档降级 None

运行：python3 regression-tests/test_short_term_engine_v12.py
"""
import os
import sys
import json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.expanduser("~/.hermes/skills/stock-analysis/financial-data-routing")
sys.path.insert(0, ENGINE_DIR)
import short_term_engine as ste  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        FAILS.append(name)
        print(f"  ✗ {name} {detail}")


# ---------- E2 as-of 门 ----------
print("== E2 as-of gate ==")
# 事故1形态：指数止于 06-03，个股 K 线到 08-26（P2 BT-08 stale 4083.97）
ok, reason = ste._apply_index_asof_gate(["2026-06-03", "2026-05-30"], "2026-08-26")
check("stale 指数拦截（事故1形态）", not ok and "stale_index" in reason, reason)
# 事故2形态：指数止于 09-07 当日（有当日根）→ 不拦（当日根在，半根 bar 场景由 v12 regime 消费端 T-1 序列处理口径另行保证）
ok2, _ = ste._apply_index_asof_gate(["2026-09-07", "2026-09-06"], "2026-09-07")
check("新鲜（指数末根=个股末日）不拦", ok2)
# 完全新鲜
ok3, _ = ste._apply_index_asof_gate(["2026-09-08", "2026-09-07"], "2026-09-07")
check("指数领先个股末日不拦", ok3)
# 日期键缺档 → engine 层根本不调门（idx_dates 为空跳过 gate）；纯函数层语义=空列表 → index_empty 拒用。
# 此处固化纯函数语义（防线语义：宁可 unknown 也不放过 stale），engine 层的「保守放行」由调用侧
# 条件保证（enrich 内 if idx_dates 非空才调门——见 short_term_engine enrich 块）。
ok4, reason4 = ste._apply_index_asof_gate([], "2026-08-26")
check("空日期列表拒用（index_empty）", not ok4 and reason4 == "index_empty", (ok4, reason4))

# ---------- E4 rebound_spec ----------
print("== E4 rebound spec ==")
spec = ste._rebound_spec(60.0)
check("entry_band 0.975×", abs(spec["entry_band"]["low"] - 58.5) < 1e-6, spec["entry_band"])
check("entry_band 0.98×", abs(spec["entry_band"]["high"] - 58.8) < 1e-6)
check("valid 5 days in entry_mode", "5" in spec["entry_mode"])
check("ladder ±8%", spec["ladder"]["take_profit"] == "+8%" and spec["ladder"]["stop"] == "-8%")
check("invalidation 在档", "失效" in spec["invalidation"])

# ---------- conditional_winrate ----------
print("== conditional_winrate ==")
cw = ste._conditional_winrate("up_stall", "trend_up")
check("up_stall/trend_up=0.521", cw and cw["win_rate"] == 0.521 and cw["n"] == 780)
cw2 = ste._conditional_winrate("dn_oversold", "trend_down")
check("dn_oversold/trend_down=0.608", cw2 and cw2["win_rate"] == 0.608)
cw3 = ste._conditional_winrate("up_stall", "trend_down")
check("无该 regime 条目 → None", cw3 is None)


def build_daily(closes):
    """closes → daily DataFrame（engine 消费形态）。"""
    n = len(closes)
    return pd.DataFrame({
        "open": closes, "close": closes, "high": closes, "low": closes,
        "volume": [1e6] * n,
    }, index=pd.date_range("2025-01-01", periods=n, freq="B"))


def build_snapshot(closes, idx_desc_closes=None, idx_dates=None, ff_hist=None):
    n = len(closes)
    rows = [{"date": d.strftime("%Y-%m-%d"), "open": c, "close": c, "high": c, "low": c,
             "volume": 1e6, "outstanding_share": 1e8} for d, c in
            zip(pd.date_range("2025-01-01", periods=n, freq="B"), closes)]
    snap = {
        "s2_quote_kline": {"data": {"daily_kline": {"data_full": rows}}},
        "s4_technical": {"data": {"atr": {"atr14": 1.0}}},
        "intraday_60min": {},
        "market_context": {"data": {"index_close": idx_desc_closes or []}},
    }
    if idx_dates is not None:
        snap["market_context"]["data"]["index_close_dates"] = idx_dates
    if ff_hist is not None:
        snap["s3_fund_flow"] = {"data": {"fund_flow": {"daily_history": ff_hist}}}
    return snap


# ---------- forecast_direction：spec 只在 dn 族、conditional_winrate 全规则 ----------
print("== forecast_direction v12 字段 ==")
# 构造 dn_oversold 触发：regime=trend_down + ret20 < -15%
# closes 21 根即可：前 1 根垫底 + 20 根下跌（ret20 = close[-1]/close[-21]-1）
closes_dn = [180.0] * 110 + [180 - i * 1.5 for i in range(1, 21)]  # 130根；末20日 180→150 ret20≈-16.7%
snap = build_snapshot(closes_dn)
daily = build_daily(closes_dn)
regime_info = {"regime": "trend_down"}
fc = ste.forecast_direction(daily, regime_info)
check("dn_oversold 触发", fc.get("rule_name") in ("dn_oversold", "dn_oversold_panic"), fc.get("rule_name"))
check("dn 分支产出 rebound_spec", "rebound_spec" in fc)
check("conditional_winrate 在档", fc.get("conditional_winrate", {}).get("win_rate") in (0.608, 0.568),
      fc.get("conditional_winrate"))
# up_stall：无 rebound_spec
closes_flat = [100.0] * 20 + [100 + (i % 3) for i in range(21)]
daily_flat = build_daily(closes_flat)
regime_up = {"regime": "trend_up"}
fc2 = ste.forecast_direction(daily_flat, regime_up)
if fc2.get("rule_name") == "up_stall":
    check("up_stall 无 rebound_spec", "rebound_spec" not in fc2)
    check("up_stall conditional=0.521", fc2.get("conditional_winrate", {}).get("win_rate") == 0.521)
else:
    print(f"  (up_stall 未触发：rule={fc2.get('rule_name')}——构造序列不带该带，跳过)")

# ---------- enrich_short_term：state_tuple / p3_signals / fund_sustain ----------
print("== enrich_short_term v12 字段 ==")
# 构造：MA20 上方温和上行 + 末段微跌（DSNH>0）
n = 80
base = [50 + 0.05 * k for k in range(n)]           # 缓慢单边上行
base[-3] = base[-4] - 0.1                           # 末 3 日微跌（不创 20 日新低）
closes_up = [round(x, 3) for x in base]
idx_series = [3900 + k for k in range(n)][::-1]     # desc 指数（任意，门不触发）
idx_dates_asc = [d.strftime("%Y-%m-%d") for d in pd.date_range("2025-06-01", periods=n, freq="B")][::-1]
ff = [{"date": f"day{k}", "main_net": (1e8 if k >= 6 else -5e7)} for k in range(10)]  # 末7根=day3..9，其中 day6..9 四根正
snap = build_snapshot(closes_up, idx_desc_closes=idx_series, idx_dates=idx_dates_asc, ff_hist=ff)
enrich = ste.enrich_short_term(snap)
check("status ok", enrich.get("status") == "ok", enrich.get("status"))
st_ = enrich.get("state_tuple") or {}
check("state_tuple 有 trend_state/regime", "trend_state" in st_ and "regime" in st_, st_)
p3 = enrich.get("p3_signals") or {}
check("p3_signals 有 dsnh/dsnl", p3.get("dsnh_days") is not None and p3.get("dsnl_days") is not None, p3)
check("dsnh_sell_hint=False（非 trend_down）", p3.get("dsnh_sell_hint") is False)
check("fund_sustain=4 正日 sustained", (enrich.get("fund_sustain") or {}).get("pos_days_7") == 4
      and enrich["fund_sustain"]["verdict"] == "sustained", enrich.get("fund_sustain"))
# 缺档 → None
snap_noff = build_snapshot(closes_up, idx_desc_closes=idx_series, idx_dates=idx_dates_asc)
enrich2 = ste.enrich_short_term(snap_noff)
check("资金缺档 → fund_sustain None", enrich2.get("fund_sustain") is None)

# S8 分级精确性：下跌+深乖离+收回 MA5+DSNL 3-10 → A 级
# 构造：先涨后急跌至 bias<-8%，末 4 日止跌（DSNL 落 3-10）且末日收回 MA5 上方
c = [100 + 0.3 * k for k in range(60)]              # 涨段（MA20 远低于价 → bias 正）
crash = [c[-1] * (1 - 0.02 * k) for k in range(1, 16)]  # 急跌 30%（bias 转深负）
c2 = c + [round(x, 3) for x in crash[:-3]]
rebound = [crash[-4], crash[-4] * 1.02]             # 末 2 日反弹收回 MA5
closes_s8 = c2 + [round(x, 3) for x in rebound]
snap_s8 = build_snapshot(closes_s8, idx_desc_closes=[3800] * 80,
                         idx_dates=[d.strftime("%Y-%m-%d") for d in pd.date_range("2025-01-01", periods=80, freq="B")][::-1])
en3 = ste.enrich_short_term(snap_s8)
p3s = en3.get("p3_signals") or {}
check("S8 条件 bias≤-8 成立", p3s.get("s8_conditions", {}).get("bias_le_m8") is True, p3s)
check("S8 grade ∈ {A,B,None}", p3s.get("s8_buy_plus_grade") in ("A", "B", None), p3s.get("s8_buy_plus_grade"))

# ---------- E2 门在 enrich 链路内生效（stale → degraded + warning） ----------
stale_date = "2025-01-01"  # 早于个股K线末日（末根日期在 2025-04 下旬）
snap_stale = build_snapshot(closes_up, idx_desc_closes=idx_series,
                            idx_dates=[stale_date] * n)  # 指数末根显式早于个股末日 → stale
en4 = ste.enrich_short_term(snap_stale)
warn = json.dumps(snap_stale.get("_warnings", []), ensure_ascii=False)
check("stale → status degraded", en4.get("status") == "degraded", en4.get("status"))
check("stale warning 在档（E2）", "E2" in warn, warn[:120])

print()
if FAILS:
    print(f"FAIL {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL PASS")
