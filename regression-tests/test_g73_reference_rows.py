#!/usr/bin/env python3
"""G73 参考行合同两极测试（2026-10-07 批：G73#dsnh_row:price_none_soft_fail landed 的执法者）。

合同：trade_sheet.rows 中 row_class=reference 的参考行（DSNH/DSNL 条件提示行）豁免
价位/确认词/买行cw 三臂，仍执法 side/type/confirm_rule/action/invalidation 五列完备；
机械行（无 row_class）六列合同不变——豁免不得泄漏到机械行。

背景：G73 六列循环遍历的是快照引擎行（非报告文本），DSNH/DSNL 参考行引擎侧
price=None 是设计语义（非机械执行），出生即对任意触发 DSNH 的 modeB 票恒 1 软 FAIL。
两极：参考行→PASS；机械行缺价→仍 FAIL；参考行缺 invalidation→仍 FAIL。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "lib"))
from gate_definitions import check_g73  # noqa: E402

REF_DSNH = {"side": "卖", "price": None, "row_class": "reference",
            "type": "DSNH 卖区提示（7 日不创新高）",
            "confirm_rule": "下跌态 ∧ 6-10 日不创新高（P3 三盲段 -3.1/-8.2/-1.1ppt）",
            "action": "减仓提示（非机械执行）", "invalidation": "收盘创 20 日新高等级上破"}
REF_DSNL = {"side": "买", "price": None, "row_class": "reference",
            "type": "DSNL 底部确认提示（8 日不创新低）",
            "confirm_rule": "下跌态 ∧ 6-10 日不创新低（半级置信：后验发现）",
            "action": "观察升级，不开仓（需反弹 spec 触发）", "invalidation": "再创新低"}
MECH_STOP = {"side": "卖", "price": 118.703, "type": "止损档（daily_ma20）· 反抽离场位",
             "confirm_rule": "日MA20-2%×2日 收盘跌破执行",
             "action": "已触发（现价在位下方）→ 反抽不过则离场",
             "invalidation": "收回该位上方 2 日则取消"}
REPORT_HEADER = "# 三环集团(300408) 交易计划\n\n| 方向 | 价位 | 类型 | 触发（收盘确认） | 动作 | 失效条件 |\n|---|---|---|---|---|---|\n"


def _snap(rows):
    return {"mode": "B",
            "s4_technical": {"data": {"trade_sheet": {"status": "ok", "rows": rows}}}}


def _run(name, rows, expect_pass, expect_substr=None):
    r = check_g73(REPORT_HEADER, _snap(rows))
    passed = (r is True) or (isinstance(r, dict) and r.get("passed"))
    ok = passed == expect_pass
    detail = ""
    if not ok and isinstance(r, dict):
        detail = " reasons=" + " | ".join(r.get("reasons") or [])
    if ok and expect_substr and isinstance(r, dict):
        ok = any(expect_substr in x for x in (r.get("reasons") or []))
        detail = f" reasons 缺 {expect_substr!r}"
    print(f"{'✅' if ok else '❌'} {name}（expect {'PASS' if expect_pass else 'FAIL'}）{detail}")
    return ok


def main():
    results = []
    # ① 正例：DSNH+DSNL 参考行与机械止损行共存 → PASS（原合同下恒 FAIL 的场景）
    results.append(_run("参考行×2+机械行共存", [REF_DSNH, REF_DSNL, MECH_STOP], True))
    # ② 反例：机械行缺价（无 row_class）→ 仍 FAIL（豁免不泄漏）
    mech_no_price = dict(MECH_STOP, price=None)
    results.append(_run("机械行缺价仍FAIL", [mech_no_price], False, "缺列/空列"))
    # ③ 反例：参考行缺 invalidation → 仍 FAIL（五列完备仍执法）
    ref_bad = {k: v for k, v in REF_DSNH.items() if k != "invalidation"}
    results.append(_run("参考行缺失效仍FAIL", [ref_bad], False, "缺列/空列"))
    # ④ 反例：机械行缺确认词 → [数据层] 臂仍在
    mech_no_confirm = dict(MECH_STOP, confirm_rule="日MA20-2%×2日")
    results.append(_run("机械行缺确认词仍[数据层]", [mech_no_confirm], False, "[数据层]"))
    # ⑤ 引擎接线：dsnh_sell_hint=True → 行带 row_class=reference；False → 全表无该键
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                    "financial-data-routing"))
    from report_views import build_trade_sheet_view
    import copy
    base = {"s4_technical": {"data": {"short_term_enrich": {"p3_signals": {}}}}}
    on = copy.deepcopy(base)
    on["s4_technical"]["data"]["short_term_enrich"]["p3_signals"] = {
        "dsnh_sell_hint": True, "dsnh_days": 7}
    rows_on = build_trade_sheet_view(on)["rows"]
    results.append(all(r.get("row_class") == "reference" for r in rows_on) and len(rows_on) == 1)
    print(f"{'✅' if results[-1] else '❌'} 引擎 dsnh=True → 参考行带 row_class")
    rows_off = build_trade_sheet_view(base)["rows"]
    results.append(all("row_class" not in r for r in rows_off))
    print(f"{'✅' if results[-1] else '❌'} 引擎 dsnh=False → 无 row_class 键")

    n_pass = sum(1 for x in results if x)
    print(f"\n{'OK' if n_pass == len(results) else 'FAILED'}  {n_pass}/{len(results)}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
