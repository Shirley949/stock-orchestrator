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


    # —— v4-1 单位正则修复（F15/F20：大小写+刻度等价；无 %附属容差 S7）——

    def test_v41_billion_case_equivalence(self):
        """v4-1①: value 写 $68.1 Billion、报告写 $68.1B（等价缩写）→ 修前 FAIL（F15 复现红）修后 PASS"""
        rep = "$68.1B [src: web_research_findings 市场规模]"
        snap = {"web_research_findings": _scene(
            [{"topic": "市场规模", "value": "市场 2026 年 $68.1 Billion（GII）", "provider": "exa",
              "url": "u", "query": "q", "_url_only": False}],
            accounting={"raw_n_total": 10, "kept": 1, "discarded": 9, "caliber_flags": []})}
        self.assertTrue(GD.check_g81(rep, snap))

    def test_v41_fabrication_still_fails(self):
        """v4-1②: 编造 $99.9B 恒 FAIL（执法力零回退）"""
        rep = "$99.9B [src: web_research_findings 市场规模]"
        snap = {"web_research_findings": _scene(
            [{"topic": "市场规模", "value": "市场 2026 年 $68.1 Billion（GII）", "provider": "exa",
              "url": "u", "query": "q", "_url_only": False}],
            accounting={"raw_n_total": 10, "kept": 1, "discarded": 9, "caliber_flags": []})}
        self.assertFalse(bool(GD.check_g81(rep, snap)))

    def test_v41_no_percent_attachment_tolerance(self):
        """v4-1③(S7): 4.63%(增长率) vs value 4.63(份额) 恒 FAIL——附属容差不引入（防假阴）"""
        rep = "增长 4.63% [src: web_research_findings 2026中报业绩]"
        snap = {"web_research_findings": _scene(
            [{"topic": "2026中报业绩", "value": "份额 4.63", "provider": "doubao",
              "url": "u", "query": "q", "_url_only": False}])}
        self.assertFalse(bool(GD.check_g81(rep, snap)))

    # —— v4-2 段落级对拍 + 家族等价 + entry_id 锚（转载家族/多源段落 实证批）——

    def test_v42_segment_scoping_mixed_line_passes(self):
        """v4-2①: 同行混排 snapshot 段数字 + wf 段数字——修前整行对拍必 FAIL（假阳），修后各段各拍 PASS"""
        rep = ("公司 ROE 5.24% 垫底 [src: snapshot.s11_peer]"
               "；产能 8 万吨 [src: web_research_findings HF供给格局]")
        snap = {"web_research_findings": _scene(
            [{"entry_id": "exa_a#q1e1", "topic": "HF供给格局", "value": "无水HF约8万吨/年",
              "provider": "exa", "url": "u", "query": "q", "_url_only": False}],
            accounting={"raw_n_total": 1, "kept": 1, "discarded_total": 0, "caliber_flags": [],
                        "kept_detail": [{"id": "exa_a#q1e1", "topic": "HF供给格局", "merged_into": ""}]})}
        self.assertTrue(GD.check_g81(rep, snap))

    def test_v42_fabrication_in_wf_segment_still_fails(self):
        """v4-2②: 编造数字落在 wf 段恒 FAIL（执法力零回退）"""
        rep = ("公司 ROE 5.24% 垫底 [src: snapshot.s11_peer]"
               "；产能 9.9 万吨 [src: web_research_findings HF供给格局]")
        snap = {"web_research_findings": _scene(
            [{"entry_id": "exa_a#q1e1", "topic": "HF供给格局", "value": "无水HF约8万吨/年",
              "provider": "exa", "url": "u", "query": "q", "_url_only": False}],
            accounting={"raw_n_total": 1, "kept": 1, "discarded_total": 0, "caliber_flags": []})}
        self.assertFalse(bool(GD.check_g81(rep, snap)))

    def test_v42_entry_id_anchor_matches(self):
        """v4-2③: entry_id 作引用锚（稳定主键恢复合法地位）——命中与未命中双向"""
        snap = {"web_research_findings": _scene(
            [{"entry_id": "exa_a#q1e1", "topic": "HF供给格局", "value": "无水HF约8万吨/年",
              "provider": "exa", "url": "u", "query": "q", "_url_only": False}],
            accounting={"raw_n_total": 1, "kept": 1, "discarded_total": 0, "caliber_flags": []})}
        rep_ok = "产能约 8 万吨/年 [src: web_research_findings exa_a#q1e1]"
        self.assertTrue(GD.check_g81(rep_ok, snap))
        rep_bad = "产能约 9.9 万吨/年 [src: web_research_findings exa_b#q1e9]"
        self.assertFalse(bool(GD.check_g81(rep_bad, snap)))

    def test_v42_merged_into_family_satisfies_reverse_arm(self):
        """v4-2④: 转载家族 merged_into——canonical 被引用即全族满足反向臂；无 detail 时仍逐条 FAIL"""
        items = [
            {"entry_id": "exa_a#q1e1", "topic": "研报全文版", "value": "缺口 2.31 万吨",
             "provider": "exa", "url": "u1", "query": "q", "_url_only": False},
            {"entry_id": "exa_a#q1e2", "topic": "研报摘要版", "value": "缺口 2.31 万吨",
             "provider": "exa", "url": "u2", "query": "q", "_url_only": False},
        ]
        acc = {"raw_n_total": 2, "kept": 2, "discarded_total": 0, "caliber_flags": [],
               "kept_detail": [{"id": "exa_a#q1e1", "topic": "研报全文版", "merged_into": ""},
                               {"id": "exa_a#q1e2", "topic": "研报摘要版", "merged_into": "exa_a#q1e1"}]}
        rep = "内需缺口 2.31 万吨 [src: web_research_findings 研报全文版]"
        self.assertTrue(GD.check_g81(rep, {"web_research_findings": _scene(items, acc)}))
        # 同场景无 kept_detail（旧账本）→ 摘要版未消费仍 FAIL（执法力零回退）
        acc_legacy = {"raw_n_total": 2, "kept": 2, "discarded_total": 0, "caliber_flags": []}
        self.assertFalse(bool(GD.check_g81(rep, {"web_research_findings": _scene(items, acc_legacy)})))

    def test_v42_b_bad_message_shows_failing_line(self):
        """v4-2⑤: b 臂消息引用失败行本身（治循环残留变量 stale-ln 诊断 bug）"""
        rep = ("无关首行 [src: web_research_findings 食品级CO2全球规模]\n"
               "营收9.99亿元 [src: web_research_findings 2026中报业绩]")
        r = GD.check_g81(rep, {"web_research_findings": _scene(ITEMS, ACC)})
        self.assertFalse(bool(r))
        self.assertIn("营收9.99亿元", str(r))


if __name__ == "__main__":
    unittest.main(verbosity=1)
