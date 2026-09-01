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
  · Level D：真实正文探针（R12，failure-family 2026-08-30）——「诚实否定句 + 他处触发词」
    形态。语料 = 龙磁 300835 初稿真实片段（G48 事故行 / G57 Q4 行 / G49 观点层）+ 归档
    快照（parity 冻结池 000988 + 600183 模式B金票）+ 策展构造快照（degraded 中间态 /
    千股千评 ok / 空 growth_tier——冻结票覆盖不到的三态分支）。三桶：
    REAL_HONEST 诚实写法必须 PASS（回归红线：R5 片段级收窄等修复冻结在此，重引入即红）；
    REAL_TWIN   反编造反例必须 FAIL（两极验证执法臂仍活）；
    REAL_WATCH  疑似误伤/漏洞形态，冻结当前判决（观察档 R7：判决漂移即红，禁静默变化）。

出口：stdout 末行「漏报=N 共M门」；N>0 或任何 crash/误伤/watch漂移 → exit 1（对接 run_regression grep）。
"""
import copy
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
    # 核心结论头块门（2026-08-31 m38 配套）：三票全 A 快照，mode 短路结构性 True；
    # 抓错能力由 test_b_head_g71.py 两极单测覆盖（存在性/槽位/纪律位标签/概率投影/pess 分支）
    "G71": {"000988": True,  "002008": True,  "300394": True},
    # 降级源点名披露门（2026-09-01 收官批 F1）：池票快照 ts=2026-08-14（生效前）→
    # legacy 豁免恒 True；两极执法由 SECTION_PROBES 带构造快照（第 4 元素）的 G72 探针覆盖
    "G72": {"000988": True,  "002008": True,  "300394": True},
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
        "G16",
        # D′ 修复（2026-08-27）：他主体数字（订单 8 亿）前方归因豁免（旧 FAIL/新 PASS；000988 golden CL=4.93 亿）
        "### 模块二\n合同负债核对：在手订单破 8 亿，合同负债 4.93 亿元，与快照一致。\n",
        True,
    ),
    (
        "G16",
        # D′ 反极：编造照抓——CL 归因的 12 亿（ratio 2.43>1.5）两代皆 FAIL（保守执法保持）
        "### 模块二\n合同负债核对：最新期 12 亿元，与快照一致。\n",
        False,
    ),
    (
        "G63",
        # 反极（2026-08-28 批量/剥离/真值集补全修复）：双编造价（113.0 距 111.68=1.2%、
        # 109.0 距 weekly sell_tdst 107.602=1.3%）——宽松化后照抓，且 reasons 须为全量（≥2 条）
        "### 模块三 技术面\n第一支撑 113.0 元附近有承接，第二支撑 109.0 亦有买盘。\n",
        False,
    ),
    (
        "G63",
        # 反极：TDST 真值入手抄错（110 vs weekly sell_tdst 107.602=2.2%）——加真值≠豁免
        "### 模块三 技术面\n周线 TDST 压力参考 110 元，未突破。\n",
        False,
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
    # —— G72 降级源点名披露（2026-09-01 收官批 F1）两极 + legacy 豁免，第 4 元素 = 构造快照 ——
    (
        "G72",
        "## 14. 数据时效与局限\n本报告数据存在降级，已在相应章节如实披露。\n",
        False,  # 样板话（无源名）必抓——真值携带式：逐条点名才算披露
        {"_warnings": ["[akshare] K线使用 stock_zh_a_daily"], "timestamp": "2026-09-01T09:00:00"},
    ),
    (
        "G72",
        "## 14. 数据时效与局限\nK线源降级为 akshare stock_zh_a_daily（新浪源）。\n",
        True,  # 点名 API 名即达标
        {"_warnings": ["[akshare] K线使用 stock_zh_a_daily"], "timestamp": "2026-09-01T09:00:00"},
    ),
    (
        "G72",
        "",
        True,  # legacy 豁免极：ts<2026-09-01 空报告亦 PASS（G61 旧快照同款向后兼容）
        {"_warnings": ["[akshare] K线使用 stock_zh_a_daily"], "timestamp": "2026-08-14T18:00:00"},
    ),
]


# ── Level D：真实正文探针（R12）────────────────────────────────────────────
# 快照键（load_level_d_snaps 构造）：
#   A000988    = parity 冻结票原样；degraded_sd = sd.status→degraded（G47 反编造臂仅对
#               ≠ok/≠failed 的中间态生效，failed 在 :2147 早退豁免）；no_bsp = 删
#               buy_sell_pressure（G49 反编造臂执法态）；eval_ok = 千股千评 ok 最小构造
#               （三张冻结 A 票均无 s_stock_evaluation，真空豁免盖不住 ①-④ 执法面）；
#   empty      = {}（growth_tier None 分支）；B600183 = 模式B金票（G69 四维全在场）。
# 依赖声明：degraded_sd 保留 000988 的 sd.verdict=净增持（has_direction=True 前提）——
# 与 EXPECTED 表同级的冻结票依赖，corpus 刷新须同步复核。
REAL_HONEST = [
    ("G48", "A000988",
     "| **股东层面风险** | 股东户数单季 +74.32%，散户化；无待执行增减持计划 |",
     "龙磁事故行原样：R5 片段级收窄（|。；;\\n 切分）后否定句+同行他格 % 不再误伤"),
    ("G48", "A000988",
     "无待执行计划。\n当前 PE 分位 15%。",
     "否定句 + 他处 %（R5 立项原始形态，两代正交验证均须 PASS）"),
    ("G47", "degraded_sd",
     "股东数据降级（部分源失败），内部人动向本季无从核实。",
     "降级如实披露 + presence 词（内部人）+ 无具名动作 → 合法"),
    ("G49", "A000988",
     "买卖力量：近一季无材料级活动（unclear），观点层近乎空白。",
     "unclear 豁免 + 诚实否定；presence 词（买卖力量）在场不触发反编造（无阵营词）"),
    ("G57", "empty",
     "Q4：2026 年中报预增吗？\n答：公司处于高成长赛道（行业景气叙事）。",
     "业绩触发词与成长强度词分行 → 反编造行级 scope 不误伤行业叙事"),
    ("G61", "eval_ok",
     "千股千评：轻度控盘 [src: snapshot.s_stock_evaluation.data.processed.conclusions]",
     "ok 结论 surface + 数据源锚 → 四段闭环（拉/存/读/消费）全通"),
    ("G29", "A000988",
     "资产安全：货币资金充裕、有息负债可控，整体风险一般。",
     "非🚨 档消费词（货币资金/有息负债）surface + 危险词同场 → 双臂皆满足"),
    ("G25", "A000988",
     "事件扫描：近 3 月新闻分桶（高价值 1 条 / 中价值 60 条）[src: snapshot.s5_events.data.news]",
     "python_layer=completed + src 锚 → 事件面消费合法"),
    ("G69", "B600183",
     "资金流 [src: snapshot.s3_fund_flow.data.fund_flow] 主力净流入明显；融资余额平稳 "
     "[src: snapshot.s_margin.data]；估值分位 50% "
     "[src: snapshot.valuation_snapshot.data.valuation_percentile]；获利盘接近成本 "
     "[src: snapshot.s4_technical.data.chip]",
     "B 门四维全消费（src 锚 + 维度词同行）→ 满配形态"),
]
REAL_TWIN = [
    ("G48", "A000988",
     "另有待执行减持计划，规模 2.5%",
     "无活跃计划却写「待执行+%」同片段 → 反编造照抓（执法臂活跃证明）"),
    ("G47", "degraded_sd",
     "前十大流通股东增持明显。",
     "status≠ok 却写具名「前十大…增持」→ 反编造 FAIL"),
    ("G61", "eval_ok",
     "轻度控盘，主力资金介入迹象明显",
     "结论词在场却无 s_stock_evaluation 锚 → 编造 FAIL"),
    ("G29", "empty",
     "货币资金约 35 亿",
     "无 asset_safety 数据却写具体数值 → 反编造 FAIL"),
]
# 观察档（R7）：冻结 2026-08-30 实测判决。漂移即 exit 1——改判须连注释一起更新（显性化）。
REAL_WATCH = [
    ("G49", "no_bsp", True,
     "买卖力量：无结论。\n观点层：卖方研报 0 覆盖、机构评级仅 1 家。",
     "F4a 已修（2026-09-01 片段级收窄）：「卖方研报」覆盖度语境与「买卖力量」跨行共现"
     "不再触发反编造——旧冻结 FAIL 为误伤态，现判 PASS；条目保留作回归锚防再漂移"),
    ("G57", "empty", False,
     "Q4：2026 年中报预增吗？\n答：公司处于高成长赛道（行业叙事，非业绩预告结论）。",
     "疑似误伤：诚实免责括号自身含「业绩预告」→ 同行与「高成长」共现触发反编造"
     "（纯文本 regex 无否定语境识别；写作规避=否定表述不复用触发词）"),
    ("G69", "B600183", True,
     "资金流数据降级如实披露 [src: snapshot.s3_fund_flow.data.fund_flow]（本维未消费）。\n"
     "融资 [src: snapshot.s_margin.data] 杠杆温和；估值分位 50% "
     "[src: snapshot.valuation_snapshot.data.valuation_percentile]；获利 "
     "[src: snapshot.s4_technical.data.chip] 筹码稳定。\n另注：主力动向中性（叙述语）。",
     "F4b① 已修（2026-09-01 同行+否定披露守卫）：降级披露行（挂 [src:] 但行内含"
     "未消费/降级）不再计入消费维度——判决仍 True 但理由已从「拼出来的」变为"
     "「真消费的」（融资/估值分位/获利 3 维同行真消费，need=3）；真实翻转形态="
     "2 真+1 假票（TestF4bG69Narrow.test_disclosure_line_not_counted_2true_1fake "
     "冻结）；条目保留作回归锚防再漂移"),
    ("G25", "A000988", True,
     "## 六、市场情绪与重大事件\n\n事件时间线（28 条事件）：\n"
     "| 日期 | 事件 | 意义 |\n|---|---|---|\n"
     "| 2026-08-29 | 披露中报 [src: snapshot.s5_events.data.risk_signals.processed.timeline] | 兑现日 |",
     "F4b② 已修（2026-09-01 同节锚）：节标题带事件词+src 挂节内明细行=合法消费"
     "（002130/300223 等 5 对归档实锤形态）——初申行级窗口被重放证伪，窗口修正为"
     "section（改锚表不改报告）；条目保留作回归锚防再漂移（回退行级即红）"),
    ("G25", "A000988", False,
     "## 五、技术面\n离散事件（缺口高频反复）：跳空缺口交替，非单边趋势结构。\n\n"
     "## 九、全景表\n| ⑫治理 | risk 2 条 [src: snapshot.s5_events.data.risk_signals.processed.timeline] | 中性 |",
     "F4b② 已修（2026-09-01 同节锚）：跨节拼不算消费——事件词散在技术面叙事"
     "（「离散事件」）+ s5_events src 挂全景表别节，旧全文两独立条件可拼出「消费」"
     "（000657 形态）；现判 FAIL 为正确执法，条目保留防松动回全文级（翻 True 即红）"),
]


def load_level_d_snaps(stocks):
    base = stocks["000988"]
    deg = copy.deepcopy(base)
    deg["s5_events"]["data"]["risk_signals"]["processed"]["shareholder_dynamics"]["status"] = "degraded"
    nobsp = copy.deepcopy(base)
    nobsp["s5_events"]["data"]["risk_signals"]["processed"].pop("buy_sell_pressure", None)
    ev = {"s_stock_evaluation": {"data": {"status": "ok", "processed": {
        "conclusions": [{"dimension": "控盘程度", "text": "轻度控盘",
                         "severity": "info", "source_api": "em"}],
        "latest_period": {"period": "2026-08-29", "value": "轻度控盘"}}}}}
    b_gold = os.path.join(HERE, "600183_modeB_golden.json.gz")
    snaps = {"A000988": base, "degraded_sd": deg, "no_bsp": nobsp,
             "eval_ok": ev, "empty": {},
             "B600183": json.load(gzip.open(b_gold)) if os.path.exists(b_gold) else None}
    return snaps


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

    # Level C：段内省略探针（元组可选第 4 元素 = 自定义快照，覆盖生效期/构造态两极）
    for probe in SECTION_PROBES:
        gname, report, exp = probe[0], probe[1], probe[2]
        snap = probe[3] if len(probe) > 3 else stocks["000988"]
        try:
            got, reasons = engine_verdict(GATE_CHECKERS[gname], report, snap)
        except Exception as e:  # noqa: BLE001
            crashes.append(f"{gname}/probe: {type(e).__name__}: {e}")
            continue
        if got != exp:
            (miss_reports if exp and not got else over_reports).append(
                f"{gname}/probe: 期望{'PASS' if exp else 'FAIL'} 实际{'FAIL' if exp else 'PASS'}"
                + (f" reasons={reasons[:1]}" if reasons else "")
            )

    # Level D：真实正文探针（R12）——诚实/孪生断言期望判决，观察档断言冻结判决
    watch_drifts = []
    snaps_d = load_level_d_snaps(stocks)
    for bucket, probes in (("honest", REAL_HONEST), ("twin", REAL_TWIN)):
        for gname, snap_key, report, _why in probes:
            snap = snaps_d.get(snap_key)
            if snap is None:
                crashes.append(f"{gname}/D-{bucket}: 快照 {snap_key} 缺失")
                continue
            try:
                got, reasons = engine_verdict(GATE_CHECKERS[gname], report, snap)
            except Exception as e:  # noqa: BLE001
                crashes.append(f"{gname}/D-{bucket}: {type(e).__name__}: {e}")
                continue
            exp = (bucket == "honest")   # honest 须 PASS；twin 须 FAIL
            if got != exp:
                (miss_reports if exp and not got else over_reports).append(
                    f"{gname}/D-{bucket}[{snap_key}]: 期望{'PASS' if exp else 'FAIL'}"
                    f" 实际{'PASS' if got else 'FAIL'}"
                    + (f" reasons={reasons[:1]}" if reasons else ""))
    for gname, snap_key, frozen, report, _why in REAL_WATCH:
        snap = snaps_d.get(snap_key)
        if snap is None:
            crashes.append(f"{gname}/D-watch: 快照 {snap_key} 缺失")
            continue
        try:
            got, _reasons = engine_verdict(GATE_CHECKERS[gname], report, snap)
        except Exception as e:  # noqa: BLE001
            crashes.append(f"{gname}/D-watch: {type(e).__name__}: {e}")
            continue
        if got != frozen:
            watch_drifts.append(
                f"{gname}/D-watch[{snap_key}]: 冻结={'PASS' if frozen else 'FAIL'}"
                f" 实际={'PASS' if got else 'FAIL'}（改判须连 REAL_WATCH 注释一起显性更新）")

    total = len(GATE_CHECKERS)
    n_bad = len(miss_reports) + len(over_reports) + len(crashes) + len(watch_drifts)
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
    if watch_drifts:
        print("❌ watch 漂移（观察档判决变化，须显性裁决）:")
        for m in watch_drifts:
            print("   ", m)
    print(
        f"{'✅' if n_bad == 0 else '❌'} 漏报={len(miss_reports)} 共{total}门"
        f"（×{len(stocks)}票 + {len(SECTION_PROBES)} 段探针"
        f" + {len(REAL_HONEST) + len(REAL_TWIN)} 真实正文探针/watch={len(REAL_WATCH)}；"
        f"误伤={len(over_reports)} crash={len(crashes)} drift={len(watch_drifts)}）"
    )
    sys.exit(0 if n_bad == 0 else 1)


if __name__ == "__main__":
    main()
