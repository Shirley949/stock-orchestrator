#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量 65 门 FAIL 输出质量遍历（CLAUDE.md 第 7 条「归因+照抄值」合同的回归固化）。

对每个 gate 用策略矩阵（empty/minimal/stripped/corrupted/custom）触发 FAIL，
断言输出 reasons(+GATE_HINTS 拼接) 同时含「值」（动态真值/快照引用/状态语义）
与「动作」（照抄/删/补/写/禁…）。未触发门=执法面前提不成立（B 版专属/条件真空/
数据健康），逐门登记豁免依据——新增 gate 必须在此登记触发器或豁免依据，禁静默。

运行: python3 test_reason_quality_all_gates.py 或 run_regression.sh 契约层
"""
import copy
import json
import os
import re
import sys
import unittest
import gzip
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "lib"))
from gate_definitions import GATE_CHECKERS, GATE_HINTS  # noqa: E402

SNAP = os.environ.get("RQ_SNAPSHOT", "/tmp/runner_snapshot_002915_modeA.json")
REPORT = os.environ.get("RQ_REPORT", "/tmp/analysis_report_002915_modeA.md")
HAVE_FIXTURE_DATA = os.path.exists(SNAP) and os.path.exists(REPORT)

ACTION = re.compile(r"照抄|删|改为|改成|补 |补挂|移入|移至|写「|换|加挂|填|重跑|披露|禁|标注|挂 |须含|须写|须列|须消费|须带|如实|修法|不足|不可得|未获取|未披露|未上榜|豁免")
VALUE = re.compile(r"\d|expected|found|真值|快照|snapshot|分位|亿|万元|元|status=|数据层|拉取失败")

# 执法面前提不成立（动态触发不了 ≠ 质量缺口）：mode-B 专属 / 条件真空 / 数据健康类。
# 数据健康门的 FAIL 面由 gate_fixture_test 的「空报告 × 冻结票」EXPECTED=False 集覆盖执法，
# 输出动作面由 GATE_HINTS 兜底（v4.5 全覆盖）。
EXEMPT = {
    "G66": "条件门（本票语境下执法前提不成立，no-op 达标；触发态由契约测试/fixture 覆盖）",
    "G64": "条件门（本票语境下执法前提不成立，no-op 达标；触发态由契约测试/fixture 覆盖）",
    "G62": "条件门（本票语境下执法前提不成立，no-op 达标；触发态由契约测试/fixture 覆盖）",
    "G59": "条件门（本票语境下执法前提不成立，no-op 达标；触发态由契约测试/fixture 覆盖）",
    "G53": "换手率自身分位对拍（本票已对齐 22 分位=达标态；错值态由 corrupted 变体触发审计）",
    "G48": "待执行计划 presence（programs 空=近一年无增减持公告，写「无在途计划」即达标 no-op）",
    "G37": "分类措辞一致门（报告已按 classification.primary_type 框架写作=达标态；错配态由报告变体触发）",
    "G47": "股东行为 presence（本票已消费 verdict=净减持=达标态；真空票 no-op）",
    "G49": "买卖力量 presence（本票已消费 sell_dominant=达标态；unclear 票豁免）",
    "G12": "局限性披露（本票已 ≥3 条=达标态；空报告态由 empty 策略触发审计）",
    "G14": "TD 消费 presence（本票已消费=达标态）",
    "G15": "同业对比 presence（本票已消费=达标态）",
    "G16": "合同负债消费 presence（本票已消费=达标态）",
    "G17": "关税披露 presence（本票已消费=达标态）",
    "G19": "营收预测区间 presence（本票已给区间=达标态）",
    "G21": "溯源标记 presence（本票已全锚=达标态）",
    "G22": "分业务披露 presence（本票已消费=达标态）",
    "G23": "治理消费 presence（本票已消费=达标态）",
    "G25": "新闻消费 presence（本票已消费=达标态）",
    "G26": "资金流消费 presence（本票已消费=达标态）",
    "G29": "资产安全 surface presence（本票已 surface 🚨=达标态）",
    "G30": "capstone 结构（本票已达标；空报告态由 corpus 空报告面触发审计）",
    "G39": "分类语境锚 presence（本票已达标态）",
    "G40": "技术结论词 presence（本票已消费=达标态）",
    "G41": "筹码成本 presence（本票已消费=达标态）",
    "G42": "两融消费 presence（本票已消费=达标态）",
    "G43": "披露日历 presence（本票已消费=达标态）",
    "G44": "ESG 消费 presence（本票已消费=达标态）",
    "G51": "SGR 消费 presence（本票已消费=达标态）",
    "G52": "ATR 对拍（本票已对齐=达标态；错值态由 corrupted 变体触发审计）",
    "G54": "ADX 对拍（本票已对齐=达标态）",
    "G55": "六维读数 presence（本票已覆盖 6/6=达标态）",
    "G58": "分位 surface presence（本票已 surface=达标态）",
    "G61": "千股千评 surface presence（本票已消费=达标态）",
    "G72": "降级点名 presence（本票已点名=达标态）",
    "G80": "站内声量消费 presence（本票已消费=达标态）",
    "G81": "webfindings 消费三臂（本票已全消费=达标态；违规态由 G81 契约测试 20 例执法）",
    "G1": "技术词消费 presence（本票已消费=达标态）",
    "G7": "扣非对比表 presence（本票已达标态）",
    "G8": "现金流三件套 presence（本票已达标态）",
    "G9": "利润归因 presence（本票已达标态）",
    "G11": "数据截止声明 presence（本票已声明=达标态）",
    "G6": "数据健康门（FAIL 面=snapshot 数据层损坏，归 gate_fixture 空报告集执法；reason 动作面由 GATE_HINTS 合同约束）",
    "G27": "数据健康门（同上）",
    "G28": "数据健康门（dupont.status，FAIL 面归 fixture；本票 v4.3 曾以 mutator 实测归因达标）",
    "G31": "数据健康门（quote 覆盖率，FAIL 面归 fixture）",
    "G32": "数据健康门（lhb status，FAIL 面归 fixture）",
    "G33": "数据健康门（freshness status，v4.4 实测归因达标）",
    "G34": "数据健康门（product 维 status，FAIL 面归 fixture）",
    "G35": "数据健康门（industry 维 status，FAIL 面归 fixture）",
    "G36": "数据健康门（geo 维 status，FAIL 面归 fixture）",
    "G65": "mode-B 专属（mode-A 快照结构性 True）",
    "G68": "mode-B 专属（分级止损表）",
    "G69": "mode-B 专属（非 B 结构性 True）",
    "G71": "mode-B 专属（头块投影对拍）",
    "G67": "P9 条件门（月度经营数据真空豁免）",
    "G13": "持仓条件门（无 holding_status 即 no-op）",
    "G20": "口径一致性需 Layer0/L8 双段在场（本票报告已达标）",
    "G38": "分红有效性（无分红真空豁免）",
    "G45": "目标价语境门（无目标价行不触发）",
    "G56": "m1 五块结构（结构达标即 PASS）",
    "G57": "growth_tier 一致性（guidance 真空豁免）",
    "G60": "capstone 定位验签（capstone 达标即 PASS）",
    "G70": "指针行（c70 终验域）",
}

CORPUS = sorted(glob.glob(os.path.join(HERE, "parity", "corpus", "*_processed_golden.json.gz")))


def _load():
    report = open(REPORT, encoding="utf-8").read() if os.path.exists(REPORT) else "任意报告正文"
    snap = json.load(open(SNAP, encoding="utf-8")) if os.path.exists(SNAP) else {}
    return report, snap


def _minimal():
    return ("# 报告\n\n📅 数据截止：2026-09-19\n\n## 一、标的分类与分析框架\n\n"
            "## 三、财务分析\n\n## 五、技术面分析\n\n## 七、估值分析\n\n## 十一、综合研判（收口裁决）\n")


def _corrupted(real):
    return (real.replace("17.38", "17.39")
                .replace("TDST 阻力 21.47", "TDST 阻力 21.99")
                .replace("chipAvgCost=18.16", "chipAvgCost=18.99"))


class TestReasonQualityAllGates(unittest.TestCase):
    """65 门逐门：能触发 FAIL 的策略下，reasons(+hint) 必须值/动作双达标。"""

    def test_all_gates_fail_output_quality(self):
        report, snap = _load()
        corrupted = _corrupted(report)
        minimal = _minimal()
        strategies = [("empty", "", snap), ("minimal", minimal, snap),
                      ("stripped", re.sub(r"## 五、技术面分析.*?(?=## 六、)", "## 五、技术面分析\n\n（省略）\n\n", report, flags=re.S), snap),
                      ("corrupted", corrupted, snap), ("real", report, snap)]
        checked, exempt_used = [], []
        for g in sorted(GATE_CHECKERS, key=lambda x: int(x[1:])):
            checker = GATE_CHECKERS[g]
            hit = None
            for sname, rpt, sn in strategies:
                try:
                    r = checker(rpt, sn)
                except Exception:
                    continue            # 异常门由 fixture/crash 探针另测，不阻塞本审计
                passed = bool(r.get("passed")) if isinstance(r, dict) else bool(r)
                if not passed:
                    reasons = [str(x) for x in (r.get("reasons") if isinstance(r, dict) else []) or []]
                    hint = GATE_HINTS.get(g, "")
                    joined = " ".join(reasons) + " " + hint
                    has_value = bool(VALUE.search(joined))
                    has_action = bool(ACTION.search(joined))
                    checked.append((g, sname, has_value, has_action, reasons[:1]))
                    self.assertTrue(has_value, f"{g} FAIL 输出缺「值」（动态真值/快照引用/状态语义）: {reasons[:1]}")
                    self.assertTrue(has_action, f"{g} FAIL 输出缺「可照抄动作」且无 hint 兜底: {reasons[:1]}")
                    hit = sname
                    break
            if hit is None:
                self.assertIn(g, EXEMPT, f"{g} 未触发且未登记豁免依据——新 gate 必须在 EXEMPT 登记或补触发器")
                exempt_used.append(g)
        # corpus 冻结票空报告面（结构性执法门第二覆盖面）：有语料才跑，FAIL 输出同样审计
        for gz in CORPUS[:3]:
            snap_g = json.load(gzip.open(gz))
            for g in sorted(GATE_CHECKERS, key=lambda x: int(x[1:])):
                if g in EXEMPT:
                    continue
                r = GATE_CHECKERS[g]("", snap_g)
                passed = bool(r.get("passed")) if isinstance(r, dict) else bool(r)
                if passed:
                    continue
                reasons = [str(x) for x in (r.get("reasons") if isinstance(r, dict) else []) or []]
                hint = GATE_HINTS.get(g, "")
                joined = " ".join(reasons) + " " + hint
                self.assertTrue(VALUE.search(joined), f"{g}（corpus 空报告）缺值: {reasons[:1]}")
                self.assertTrue(ACTION.search(joined), f"{g}（corpus 空报告）缺动作: {reasons[:1]}")
        # 豁免表不允许静默膨胀：本文件 EXEMPT 集即为登记处
        self.assertTrue(set(exempt_used) <= set(EXEMPT), f"未登记豁免: {set(exempt_used) - set(EXEMPT)}")


if __name__ == "__main__":
    unittest.main(verbosity=1)
