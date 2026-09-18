#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读侧协议契约测试（v3-S1/S3）——搜索工件解析器 search_artifact_parser.py 的六组断言。

验收锚点（全部为历史真实数据的冻结值）：
  002273 事故回放 92=74+18 + 三真漏信号 HIT 于 B 级读面
  002549 出样 59 条 + 口径对撞族召回（食品级CO2 极差族）
  合成 fixtures 15 用例（含限流伪装/空结果/截断写/批头/尾哨兵/双空 Tavily）
运行: python3 test_search_artifact_parser.py 或 run_regression.sh 契约层
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTING = HERE.parent.parent / "financial-data-routing"
sys.path.insert(0, str(ROUTING))
import search_artifact_parser as SAP  # noqa: E402

FIX = HERE / "fixtures" / "search_artifacts"
F2273 = sorted((FIX / "corpus/misc").glob("exa_*.json")) + \
    sorted((FIX / "corpus/misc").glob("doubao_[1-7]_*.json"))
F2549 = sorted((FIX / "corpus/exa_002549").glob("batch*.json")) + \
    sorted((FIX / "corpus/doubao_002549").glob("q*.json"))


def parse_all(paths, seen=None):
    reg, disp, seen = {}, {}, {} if seen is None else seen
    for p in paths:
        r = SAP.parse_file(str(p))
        d, seen = SAP.structural_disposition(r.entries, seen)
        disp.update(d)
        for e in r.entries:
            reg[e.id] = e
    return reg, disp


class TestParseMatrix(unittest.TestCase):
    """组1: 合成 fixtures 期望矩阵（fail-loud 五律 + 双空回退 + 批头/哨兵）"""

    EXP = {
        "f01_doubao_empty.json": "FAIL:0-entries",
        "f02_doubao_quota.json": "FAIL:doubao-api-error",
        "f03_exa_jsonrpc_error.jsonl": "FAIL:jsonrpc-error",
        "f04_exa_ratelimit.jsonl": "FAIL:exa-rate-limited",
        "f05_exa_single.jsonl": "RESULT_EXA:1",
        "f06_exa_emptytitle.jsonl": "RESULT_EXA:1",
        "f07_doubao_long.json": "RESULT_DOUBAO:1",
        "f08_garbage.bin": "NON_RESULT",
        "f09_script.sh": "NON_RESULT",
        "f10_initialize_only.jsonl": "FAIL:no-tools-call",
        "f11_batch_headers.txt": "RESULT_DOUBAO:5",
        "f12_truncated.jsonl": "FAIL:unparsable",
        "f13_doubao_empty_title.json": "RESULT_DOUBAO:2",
        "f14_doubao_content_embeds_title.json": "RESULT_DOUBAO:1",
        "f15_tavily_both_empty.json": "RESULT_TAVILY:1",
    }

    def test_matrix(self):
        bad = []
        for name, want in self.EXP.items():
            try:
                r = SAP.parse_file(str(FIX / "synthetic" / name))
                got = f"{r.kind}:{r.n}" if r.kind.startswith("RESULT") else r.kind
            except SAP.ParseError as e:
                got = "FAIL:" + str(e).split(":")[0].split("(")[0].strip()
            ok = got == want or (got.startswith("FAIL:") and want.startswith("FAIL:")
                                 and want[5:].split(":")[0] in got)
            if not ok:
                bad.append(f"{name}: want={want} got={got}")
        self.assertEqual(bad, [], f"解析矩阵偏差: {bad}")

    def test_tavily_raw_content_fallback(self):
        r = SAP.parse_file(str(FIX / "corpus/misc/tavily_empty_content.json"))
        self.assertEqual((r.kind, r.n), ("RESULT_TAVILY", 4))
        self.assertTrue(all(len(e.text) > 100 for e in r.entries), "content 空须回退 raw_content")
        r2 = SAP.parse_file(str(FIX / "synthetic/f15_tavily_both_empty.json"))
        self.assertTrue(any("empty-b-level" in w for w in r2.warnings), "双空须告警")

    def test_firecrawl_samples(self):
        r1 = SAP.parse_file(str(FIX / "corpus/misc/firecrawl_search_sample1.txt"))
        self.assertEqual((r1.kind, r1.n), ("RESULT_FIRECRAWL", 3))
        r2 = SAP.parse_file(str(FIX / "corpus/misc/firecrawl_scrape_sample.md"))
        self.assertEqual((r2.kind, r2.n), ("RESULT_FIRECRAWL", 1))

    def test_non_result_excluded(self):
        for name in ("f08_garbage.bin", "f09_script.sh"):
            r = SAP.parse_file(str(FIX / "synthetic" / name))
            self.assertEqual(r.kind, "NON_RESULT", f"{name} 不得入账")


class TestIncidentReplay(unittest.TestCase):
    """组2: 002273 事故回放（冻结真值 92=74+18 + 三信号 B 级面命中）"""

    def test_accounting_identity_and_signals(self):
        reg, disp = parse_all(F2273)
        N, K = len(reg), len(disp)
        self.assertEqual((N - K, K, N), (74, 18, 92))
        signals = {"筹码": r"融资融券差额占比|持仓比例变化",
                   "千万台口径": r"1000万台|超1000万|不带显示屏",
                   "康耐特合资": r"康耐特|光视"}
        for sig, pat in signals.items():
            hits = [e for eid, e in reg.items() if eid not in disp
                    and (re.search(pat, e.text) or re.search(pat, e.title))]
            self.assertTrue(hits, f"{sig} 信号须在已读集(M)的 B 级面命中")

    def test_out_of_sample_002549(self):
        reg, _ = parse_all(F2549)
        self.assertEqual(len(reg), 59)
        ents = []
        for p in (FIX / "corpus/exa_002549").glob("batch*.json"):
            ents += SAP.parse_file(str(p)).entries
        flags = SAP.collision_screen(ents)
        self.assertTrue(flags, "对撞预筛须召回食品级CO2极差族")
        units = {f["unit"] for f in flags}
        self.assertTrue(units & {"B", "billion"}, f"须含十亿量级族, 实得 {units}")


class TestAccount(unittest.TestCase):
    """组3: M+K==N 对账断言四态 + waive 通道 + 反偷懒"""

    def setUp(self):
        self.reg = {e.id: e for e in SAP.parse_file(str(FIX / "corpus/exa_002549/batch1.json")).entries}
        self.ids = list(self.reg)

    def _acc(self, cur, waivers=None):
        return SAP.run_account(self.reg, cur, waivers)

    def test_full_disposition_pass(self):
        acc, rc, errs = self._acc({"entries": [
            {"id": i, "disposition": "kept", "value": "样本 v1 2026", "topic": "t"} for i in self.ids]})
        self.assertEqual((rc, errs), (0, []))
        self.assertEqual(acc["raw_n"], len(self.ids))

    def test_missing_block(self):
        cur = {"entries": [{"id": i, "disposition": "kept", "value": "x 1", "topic": "t"}
                           for i in self.ids[:-1]]}
        acc, rc, errs = self._acc(cur)
        self.assertEqual(rc, 1)
        self.assertTrue(any("M+K!=N" in e for e in errs))

    def test_unknown_id_block(self):
        acc, rc, errs = self._acc({"entries": [{"id": "no#such", "disposition": "kept", "value": "1"}]})
        self.assertEqual(rc, 1)
        self.assertTrue(any("unknown-entry-id" in e for e in errs))

    def test_anti_lazy_warn_not_block(self):
        acc, rc, errs = self._acc({"entries": [
            {"id": i, "disposition": "kept", "value": "无数字描述", "topic": "t"} for i in self.ids]})
        self.assertEqual(rc, 0)
        self.assertTrue(acc["warnings"], "反偷懒须 WARN")

    def test_waiver_channel(self):
        acc, rc, errs = self._acc({"entries": [
            {"id": i, "disposition": "kept", "value": "x 1", "topic": "t"} for i in self.ids]},
            waivers={"exa_fail.json": "exa-rate-limited 已重拉替代"})
        self.assertEqual(rc, 0)
        self.assertEqual(acc["waivers"][0]["file"], "exa_fail.json")


class TestCollisionScreen(unittest.TestCase):
    """组4: 口径对撞预筛（V5 修正法回测）"""

    def test_food_grade_family(self):
        ents = []
        for p in (FIX / "corpus/exa_002549").glob("batch*.json"):
            ents += SAP.parse_file(str(p)).entries
        flags = SAP.collision_screen(ents)
        self.assertTrue(any(f["max"] / f["min"] >= 3 for f in flags))
        contributors = [c for f in flags for c in f["contributors"]]
        self.assertTrue(any("CO2" in c["title"] or "Carbon Dioxide" in c["title"] for c in contributors),
                        "须含 CO2 市场规模族")


class TestFollowupAndManifest(unittest.TestCase):
    """组5: 追读登记闭环"""

    def test_followup_increments(self):
        with tempfile.TemporaryDirectory() as td:
            mf = f"{td}/manifest.json"
            a = SAP.run_followup("002549", "b1", "exa", "url a", "对撞裁决", mf)
            b = SAP.run_followup("002549", "b1", "web_reader", "url b", "全文核验", mf)
            self.assertEqual((a["id"], b["id"]), ("f001", "f002"))
            man = json.load(open(mf))
            self.assertEqual(len(man["followups"]), 2)
            self.assertIn("/tmp/002549/followup_", a["path"])


    def test_parse_json_accumulates_across_calls(self):
        """S8b 首票实战(688716)缺陷修: 多批 parse --json 同路径须累积合并, 末批禁覆盖前批"""
        import json as _json, subprocess, sys, tempfile
        with tempfile.TemporaryDirectory() as td:
            out = f"{td}/entries.json"
            cli = str(ROUTING / "search_artifact_parser.py")
            for name in ("f05_exa_single.jsonl", "f06_exa_emptytitle.jsonl"):
                r = subprocess.run([sys.executable, cli, "parse",
                                    "--files", str(FIX / "synthetic" / name),
                                    "--json", out], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
            d = _json.load(open(out))
            self.assertEqual(len(d["entries"]), 2, f"两批须累积=2, 实得 {len(d['entries'])}")
            self.assertEqual(len({e["file"] for e in d["entries"].values()}), 2)

if __name__ == "__main__":
    unittest.main(verbosity=1)
