#!/usr/bin/env python3
"""gate_fixture_test.py —— P6-D3 surfacing fixture 总闸（漏报=0）。

机制（phase-6 D3 设计）：
  · fixture 源 = P5 合一 parity 冻结池（scene 键 runner 输出，`../parity/corpus/*_processed_golden.json.gz`，
    glob 自维护，票数勿硬编码）——喂 gate 顶层（gate 按 scene 名键走 path）。
  · 空报告探针：report=""（= 什么都不 surface 的极端报告）。
    - 信号在场/结构性要求的 gate 必须 FAIL（抓住省略 = 漏报=0 的证明）；
    - 三态豁免 / 快照侧完整性 / 条件无段 no-op / 退役占位 的 gate 必须 PASS（无误伤）。
  · 裁决解释镜像 verify_gates.py:146-153（G30 等返 dict {passed,reasons}——bool(dict) 恒 True，
    必须取 ret["passed"]，见「Capstone G30」违例史）。
  · EXPECTED 清单 = 2026-08-15 逐门策展（docstring 定性 + 引擎口径实测冻结）。gate 集 =
    gate_definitions.py 的 check_g*（新增 gate 未策展 → 本测试 FAIL，强制补策展）。
  · Level C：段内省略探针（G59/G60 段存在但缺 verdict/[src:] → 必 FAIL；条件 no-op 的执法面）。

出口：stdout 末行「漏报=N 共M门」；N>0 或任何 crash/误伤 → exit 1（对接 run_regression grep）。
"""
import glob
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts", "lib"))
from gate_definitions import GATE_CHECKERS  # noqa: E402

CORPUS_GLOB = os.path.join(HERE, "..", "parity", "corpus", "*_processed_golden.json.gz")

# ── 策展清单（空报告 × 冻结票 期望裁决；引擎口径）──────────────────────────
# 三类 PASS 语义：
#   豁免/占位  : G13 无持仓条件；G20/G45/G56/G59/G60 无对应段 no-op
#   快照完整性 : G6/G27/G28/G31/G32/G33/G34-G38/G52-G55 数据健康即 PASS（空报告无关）
#   条件 no-op : G15 同业段缺席豁免
# FAIL = 该门在空报告上执法（信号在场或结构性必需内容缺席 → 抓住省略）。
# MIX = 数据依赖真触发（G39 分类执法仅 002008 豁免；G48 前瞻增减持仅 002008 在场；
#       G57 growth_tier 一致性仅 300394 豁免）。
# B3 2026-08-17 退役门 G10/G18/G46/G50 已移出枚举（gate_definitions.RETIRED_GATES 留档）。
EXPECTED = {
    "G1":  {"000988": False, "002008": False, "300394": False},
    "G6":  {"000988": True,  "002008": True,  "300394": True},
    "G7":  {"000988": False, "002008": False, "300394": False},
    "G8":  {"000988": False, "002008": False, "300394": False},
    "G9":  {"000988": False, "002008": False, "300394": False},
    "G11": {"000988": False, "002008": False, "300394": False},
    "G12": {"000988": False, "002008": False, "300394": False},
    "G13": {"000988": True,  "002008": True,  "300394": True},
    "G14": {"000988": False, "002008": False, "300394": False},
    "G15": {"000988": True,  "002008": True,  "300394": True},
    "G16": {"000988": False, "002008": False, "300394": False},
    "G17": {"000988": False, "002008": False, "300394": False},
    "G19": {"000988": False, "002008": False, "300394": False},
    "G20": {"000988": True,  "002008": True,  "300394": True},
    "G21": {"000988": False, "002008": False, "300394": False},
    "G22": {"000988": False, "002008": False, "300394": False},
    "G23": {"000988": False, "002008": False, "300394": False},
    "G25": {"000988": False, "002008": False, "300394": False},
    "G26": {"000988": False, "002008": False, "300394": False},
    "G27": {"000988": True,  "002008": True,  "300394": True},
    "G28": {"000988": True,  "002008": True,  "300394": True},
    "G29": {"000988": False, "002008": False, "300394": False},
    "G30": {"000988": False, "002008": False, "300394": False},
    "G31": {"000988": True,  "002008": True,  "300394": True},
    "G32": {"000988": True,  "002008": True,  "300394": True},
    "G33": {"000988": True,  "002008": True,  "300394": True},
    "G34": {"000988": True,  "002008": True,  "300394": True},
    "G35": {"000988": True,  "002008": True,  "300394": True},
    "G36": {"000988": True,  "002008": True,  "300394": True},
    "G37": {"000988": True,  "002008": True,  "300394": True},
    "G38": {"000988": True,  "002008": True,  "300394": True},
    "G39": {"000988": False, "002008": True,  "300394": False},
    "G40": {"000988": False, "002008": False, "300394": False},
    "G41": {"000988": False, "002008": False, "300394": False},
    "G42": {"000988": False, "002008": False, "300394": False},
    "G43": {"000988": False, "002008": False, "300394": False},
    "G44": {"000988": False, "002008": False, "300394": False},
    "G45": {"000988": True,  "002008": True,  "300394": True},
    "G47": {"000988": False, "002008": False, "300394": False},
    "G48": {"000988": True,  "002008": False, "300394": True},
    "G49": {"000988": False, "002008": False, "300394": False},
    "G51": {"000988": False, "002008": False, "300394": False},
    "G52": {"000988": True,  "002008": True,  "300394": True},
    "G53": {"000988": True,  "002008": True,  "300394": True},
    "G54": {"000988": True,  "002008": True,  "300394": True},
    "G55": {"000988": True,  "002008": True,  "300394": True},
    "G56": {"000988": True,  "002008": True,  "300394": True},
    "G57": {"000988": False, "002008": False, "300394": True},
    "G58": {"000988": False, "002008": False, "300394": False},
    "G59": {"000988": True,  "002008": True,  "300394": True},
    "G60": {"000988": True,  "002008": True,  "300394": True},
    "G61": {"000988": False, "002008": False, "300394": False},
    # B5 盲区新门（2026-08-17）：空报告三态 no-op（无自称句/无 m3 段/无大单提及）；
    # 抓错能力由 /tmp/test_g62_64.py 单测覆盖（含 301377 真实 tally 失配复现）
    "G62": {"000988": True,  "002008": True,  "300394": True},
    "G63": {"000988": True,  "002008": True,  "300394": True},
    "G64": {"000988": True,  "002008": True,  "300394": True},
    # 模式B专用门（2026-08-26 B v2）：三票全 A 快照，mode 短路结构性 True；
    # 抓错能力由两极单测覆盖（反例方向/概率/置信/周期/共振/量价/止损/ATR/凯利/锚/regime）
    "G65": {"000988": True,  "002008": True,  "300394": True},
    "G66": {"000988": True,  "002008": True,  "300394": True},
    "G67": {"000988": True,  "002008": True,  "300394": True},
    "G68": {"000988": True,  "002008": True,  "300394": True},
    "G69": {"000988": True,  "002008": True,  "300394": True},
    "G70": {"000988": True,  "002008": True,  "300394": True},
}

# Level C：段内省略探针（段存在但内容缺席 → 必 FAIL；内容合规 → PASS）
SECTION_PROBES = [
    (
        "G59",
        "### 5.3 估值结论\n当前估值处于合理区间，与同业中枢接近。\n",
        False,  # 无 verdict 判定词（偏贵/偏贱/高估/低估/估值合理/…）
    ),
    (
        "G59",
        "### 5.3 估值结论\n综合来看估值偏低。\n",
        True,
    ),
    (
        "G59",
        # C 修复（2026-08-27）：m4 章号劫持形态——无词 5.3 在前不再遮蔽真估值节（旧 FAIL/新 PASS）
        "### 5.3 机构动向\n调研频繁。\n\n#### 5.3 估值结论\n估值偏低。\n",
        True,
    ),
    (
        "G60",
        "## 综合研判\n#### Layer 1 — 证据全景\n"
        "- 护城河：品牌与渠道优势明显\n"
        "- 治理战略：管理层稳定\n"
        "- 前瞻催化：新品周期临近\n",
        False,  # 三定性行既无 [src:] 也无「无源」标注 = 裸奔
    ),
    (
        "G60",
        "## 综合研判\n#### Layer 1 — 证据全景\n"
        "- 护城河：品牌与渠道优势明显 [src: snapshot.s11_peer.data.target_metrics]\n"
        "- 治理战略：无源（定性补充）\n"
        "- 前瞻催化：分红计划落地 [src: snapshot.s5_events.data.risk_signals.processed.timeline]\n",
        True,
    ),
]


def engine_verdict(fn, report, snap):
    """镜像 verify_gates.py:146-153：dict 返回取 ret['passed']，bool 原样。"""
    ret = fn(report, snap)
    if isinstance(ret, dict):
        return bool(ret.get("passed", False)), ret.get("reasons") or []
    return bool(ret), []


def load_stocks():
    stocks = {}
    for p in sorted(glob.glob(CORPUS_GLOB)):
        code = os.path.basename(p).split("_")[0]
        stocks[code] = json.load(gzip.open(p))
    return stocks


def main():
    stocks = load_stocks()
    if not stocks:
        print("❌ 冻结池为空：", CORPUS_GLOB)
        sys.exit(1)

    miss_reports = []   # 漏报（期望 FAIL 实 PASS：省略被抓漏）
    over_reports = []   # 误伤（期望 PASS 实 FAIL）
    crashes = []

    # Level A+B：全 gate × 全票，空报告
    for gname in sorted(GATE_CHECKERS, key=lambda g: int(g[1:])):
        fn = GATE_CHECKERS[gname]
        exp_map = EXPECTED.get(gname)
        if exp_map is None:
            miss_reports.append(f"{gname}: 未策展（新增 gate 须补 EXPECTED）")
            continue
        for code, snap in stocks.items():
            exp = exp_map.get(code)
            if exp is None:
                over_reports.append(f"{gname}/{code}: 票未登记（新增语料票须补 EXPECTED 列）")
                continue
            try:
                got, _ = engine_verdict(fn, "", snap)
            except Exception as e:  # noqa: BLE001
                crashes.append(f"{gname}/{code}: {type(e).__name__}: {e}")
                continue
            if got != exp:
                (miss_reports if exp and not got else over_reports).append(
                    f"{gname}/{code}: 期望{'FAIL' if exp else 'PASS'} 实际{'PASS' if got else 'FAIL'}"
                )

    # Level C：段内省略探针
    for gname, report, exp in SECTION_PROBES:
        try:
            got, reasons = engine_verdict(GATE_CHECKERS[gname], report, stocks["000988"])
        except Exception as e:  # noqa: BLE001
            crashes.append(f"{gname}/probe: {type(e).__name__}: {e}")
            continue
        if got != exp:
            (miss_reports if exp and not got else over_reports).append(
                f"{gname}/probe: 期望{'PASS' if exp else 'FAIL'} 实际{'FAIL' if exp else 'PASS'}"
                + (f" reasons={reasons[:1]}" if reasons else "")
            )

    total = len(GATE_CHECKERS)
    n_bad = len(miss_reports) + len(over_reports) + len(crashes)
    if miss_reports:
        print("❌ 漏报（省略未抓住）:")
        for m in miss_reports:
            print("   ", m)
    if over_reports:
        print("❌ 误伤（豁免票被 FAIL）:")
        for m in over_reports:
            print("   ", m)
    if crashes:
        print("❌ crash:")
        for m in crashes:
            print("   ", m)
    print(
        f"{'✅' if n_bad == 0 else '❌'} 漏报={len(miss_reports)} 共{total}门"
        f"（×{len(stocks)}票 + {len(SECTION_PROBES)} 段探针；误伤={len(over_reports)} crash={len(crashes)}）"
    )
    sys.exit(0 if n_bad == 0 else 1)


if __name__ == "__main__":
    main()
