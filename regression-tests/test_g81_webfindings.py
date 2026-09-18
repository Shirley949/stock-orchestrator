#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G81 契约测试（读侧协议 v3-S6）——webfindings 消费三臂：反例必 FAIL 先证，正例后证。

a 引用完整性（含反向消费臂）/ b 数字一致性（D2 换算 万=1e4 亿=1e8 M=1e6 B=1e9）/ c 口径披露 presence。
豁免语义：scene 缺且无引用=PASS；scene 缺但引用=a FAIL；accounting 缺=反向臂+c 臂豁免（复刻 G80 status≠ok）。
运行: python3 test_g81_webfindings.py 或 run_regression.sh 契约层
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
import gate_definitions as GD  # noqa: E402


def _scene(items, accounting=None):
    data = {"items": items, "status": "ok", "substantive": sum(1 for i in items if not i.get("_url_only"))}
    if accounting is not None:
        data["accounting"] = accounting
    return {"data": data, "status": "ok", "_warnings": []}


ITEMS = [
    {"topic": "食品级CO2全球规模@FMI@2026", "value": "2026年$88亿，2036年$146亿，CAGR 5.2%",
     "provider": "exa", "url": "https://fmi", "query": "q1", "_url_only": False},
    {"topic": "2026中报业绩", "value": "营收3.16亿(+1.67%)，归母净利2192.14万(-60.75%)",
     "provider": "doubao", "url": "https://eeo", "query": "q2", "_url_only": False},
]
ACC = {"raw_n_total": 20, "kept": 2, "discarded_total": 18,
       "caliber_flags": [{"file": "exa_a", "q": 1, "unit": "B", "min": 3.23, "max": 14.6, "n_values": 4}]}


class TestG81(unittest.TestCase):

    # —— 反例（必 FAIL）——

    def test_cite_but_scene_missing_fails(self):
        """a 反例：报告引用 webfindings 但 snapshot 无 scene → FAIL"""
        r = GD.check_g81("xx [src: snapshot.web_research_findings] yy", {"other": 1})
        self.assertFalse(bool(r))
        self.assertIn("web_research_findings", str(r))

    def test_topic_anchor_unknown_fails(self):
        """a 反例：topic 锚不存在于 items → FAIL（带锚真值）"""
        rep = "市场规模巨大 [src: web_research_findings 不存在的锚词] "
        r = GD.check_g81(rep, {"web_research_findings": _scene(ITEMS, ACC)})
        self.assertFalse(bool(r))

    def test_number_not_in_value_fails(self):
        """b 反例：同行数字不在命中条目 value 集（同单位不同值 3.16亿→9.99亿）"""
        rep = "营收9.99亿元增长良好 [src: web_research_findings 2026中报业绩]"
        r = GD.check_g81(rep, {"web_research_findings": _scene(ITEMS, ACC)})
        self.assertFalse(bool(r))

    def test_caliber_flag_without_disclosure_fails(self):
        """c 反例：caliber_flags 非空但引用段无披露 token → FAIL"""
        rep = "食品级CO2全球规模88亿美元 [src: web_research_findings 食品级CO2全球规模]"
        r = GD.check_g81(rep, {"web_research_findings": _scene(ITEMS, ACC)})
        self.assertFalse(bool(r))

    def test_unconsumed_kept_fails(self):
        """a 反向臂反例：accounting 在场，kept topic 未被引用/未弃用 → FAIL 列清单"""
        rep = "本节无 webfindings 内容 [src: snapshot.s11_peer]"
        r = GD.check_g81(rep, {"web_research_findings": _scene(ITEMS, ACC)})
        self.assertFalse(bool(r))
        self.assertIn("食品级CO2", str(r))

    # —— 正例（PASS）——

    def test_no_scene_no_cite_pass(self):
        self.assertTrue(GD.check_g81("普通报告 [src: snapshot.s11_peer]", {"other": 1}))

    def test_anchor_match_numbers_match_pass(self):
        rep = ("食品级CO2 全球规模 2026 年 $88亿（机构间口径分歧 $3.23Bn~$14.6Bn，本文采 FMI 口径）"
               " [src: web_research_findings 食品级CO2全球规模]"
               "；2026中报业绩条目以 runner 财务为准（web 版弃用）。")
        self.assertTrue(GD.check_g81(rep, {"web_research_findings": _scene(ITEMS, ACC)}))

    def test_disclosure_token_passes_c_arm(self):
        rep = ("食品级CO2 全球规模 $88亿，机构间口径分歧区间 $3.23Bn~$14.6Bn，本文采 FMI 口径 "
               "[src: web_research_findings 食品级CO2全球规模]"
               "；2026中报业绩条目以 runner 财务为准（web 版弃用）。")
        self.assertTrue(GD.check_g81(rep, {"web_research_findings": _scene(ITEMS, ACC)}))

    def test_legacy_snapshot_without_accounting_c_arm_exempt(self):
        """accounting 缺 → c 臂豁免（旧快照），b 臂仍执法"""
        rep = "营收3.16亿元 [src: web_research_findings 2026中报业绩]"
        self.assertTrue(GD.check_g81(rep, {"web_research_findings": _scene(ITEMS)}))

    def test_reverse_arm_exempt_without_accounting(self):
        """accounting 缺 → 反向消费臂豁免（旧快照无账可查）"""
        rep = "无 webfindings 段落"
        self.assertTrue(GD.check_g81(rep, {"web_research_findings": _scene(ITEMS)}))

    def test_discard_marker_satisfies_reverse_arm(self):
        """弃用标注满足反向臂"""
        rep = ("食品级CO2 全球规模 $88亿 [src: web_research_findings 食品级CO2全球规模]"
               "；2026中报业绩条目：口径以 runner 财务为准，web 版弃用（dup）。"
               " [src: snapshot.s1_financial]")
        self.assertTrue(GD.check_g81(rep, {"web_research_findings": _scene(ITEMS, ACC)}))


if __name__ == "__main__":
    unittest.main(verbosity=1)
