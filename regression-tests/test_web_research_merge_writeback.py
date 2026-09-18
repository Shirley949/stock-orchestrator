# -*- coding: utf-8 -*-
"""F4#web_writeback:multicall_overwrite 引擎修回归：web_research 多批 merge 写回。

病理（300179 实锤 2026-09-15）：runner web_research 每次调用直接赋值覆盖 scene——
同票三批拉取（12+4+4）后盘上仅存最后一批 4 条，前两批 16 条静默蒸发，
status=ok + stdout 成功面（「已合并写入」为谎言措辞）。

修复面（runner.py）：写回默认 merge-by-topic upsert（_merge_web_research_items 纯函数：
exact-topic strip 整行替换、空 topic 只追加不建键、无模糊匹配/大小写折叠）；
--replace 显式重建（保 S1 清警告语义）；stdout mode/existing/appended/updated 诚实计数；
--verify 写后读盘对拍（MISMATCH 臂）；告警=状态函数（URL-only/空场按合并后 items 现算，
跨批存活、修正后自清，白名单外键类只留本批）；覆盖旧行 _warnings 留痕旧值→新值
（fetch_log params 只存摘要 {topic_hint,items,url_only,substantive}，旧值无第二副本）。

fixture 保真度（如实记录，非冒充原始数据）：
- fixtures/web_research_merge_300179/ 三批文件 = 300179 生产会话三批 --items 载荷的
  transcript 提取，批切分 [12,4,4] 与生产 fetch_log params 计数吻合；
- 内容级保真实证（2026-09-16 对拍）：三批 union 与生产盘 20 条 5 键
  (topic/value/provider/url/query) 逐条全等（生产盘=覆盖病理后人工补救批的幸存真相）；
- 原始 @file 逐字节载荷不可考 → 保真标准=内容等价，非字节等价。
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTING = HERE.parent.parent / "financial-data-routing"
FIXTURES = HERE / "fixtures" / "web_research_merge_300179"

sys.path.insert(0, str(ROUTING))
from runner import _merge_web_research_items  # noqa: E402

RUNNER = ROUTING / "runner.py"

# 内容比对键集（5 白名单键；_verified/_url_only/_source 为引擎自有键，不参与内容比对）
CONTENT_KEYS = ["topic", "value", "provider", "url", "query"]


def _rows(snapshot_path):
    snap = json.load(open(snapshot_path, encoding="utf-8"))
    return snap["web_research_findings"]["data"]["items"]


def _content_md5(items):
    return hashlib.md5(json.dumps(items, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _fixture(name):
    return json.load(open(FIXTURES / name, encoding="utf-8"))


class TestMergeFunction(unittest.TestCase):
    """纯函数层：upsert 语义 + Q2 反误并 + 覆盖留痕 + G3 无损携带。"""

    def test_upsert_replaces_whole_row(self):
        prev = [{"topic": "A", "value": "旧值", "url": "http://old"}]
        merged, appended, updated, overwritten = _merge_web_research_items(
            prev, [{"topic": "A", "value": "新值", "url": "http://new"}])
        self.assertEqual((len(merged), appended, updated), (1, 0, 1))
        self.assertEqual(merged[0]["value"], "新值")      # 整行替换：新策展胜
        self.assertEqual(overwritten, [(prev[0], merged[0])])  # 旧行留痕（⑦）

    def test_empty_topic_append_only_never_upserts(self):
        prev = [{"topic": "", "url": "http://a1"}, {"topic": "", "url": "http://a2"}]
        merged, appended, updated, _ = _merge_web_research_items(
            prev, [{"topic": "", "url": "http://b1"}])
        self.assertEqual((len(merged), appended, updated), (3, 1, 0))  # 空 topic 只追加

    def test_no_fuzzy_match_conservative(self):
        """Q2：大小写/全角差异 = 不同键，宁重复不误并（错杀比重复糟）。"""
        prev = [{"topic": "GDP 占比", "value": "v1"},
                {"topic": "gdp 占比", "value": "v2"},
                {"topic": "GDP占比", "value": "v3"},
                {"topic": "  GDP 占比  ", "value": "strip 后同键"}]
        merged, _, updated, _ = _merge_web_research_items(
            prev, [{"topic": "GDP 占比", "value": "新"}])
        self.assertEqual(updated, 1)                       # 仅 strip 后精确命中的第 1 键被替换
        self.assertEqual(len(merged), 4)                   # 其余三变体原样保留
        self.assertEqual(merged[0]["value"], "新")
        self.assertEqual(merged[1]["value"], "v2")
        self.assertEqual(merged[2]["value"], "v3")

    def test_idempotent_resend_content_frozen(self):
        prev = _fixture("batch1_12.json") + _fixture("batch2_4.json") + _fixture("batch3_4.json")
        before = _content_md5(prev)
        merged, appended, updated, overwritten = _merge_web_research_items(prev, prev)
        self.assertEqual((appended, updated, overwritten), (0, 20, []))  # 同内容重发=零覆盖告警
        self.assertEqual(_content_md5(merged), before)     # 字节级不变

    def test_extra_keys_carried_lossless(self):
        """G3 schema 演化：白名单扩键时整行替换无损携带（merge 不做键级手术）。"""
        prev = [{"topic": "A", "value": "旧", "future_key": "x"}]
        merged, _, _, _ = _merge_web_research_items(
            prev, [{"topic": "A", "value": "新", "future_key": "y", "another": 1}])
        self.assertEqual(merged[0], {"topic": "A", "value": "新", "future_key": "y", "another": 1})

    def test_corrupt_prev_items_tolerated(self):
        self.assertEqual(_merge_web_research_items(None, [{"topic": "A", "value": "v"}])[0:3],
                         ([{"topic": "A", "value": "v"}], 1, 0))


class TestWritebackE2E(unittest.TestCase):
    """子进程端到端：真实 runner.py 三批重放 + D 系列不变式（隔离临时快照，禁污染在用 scene）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="wr_merge_e2e_")
        cls.snap = str(Path(cls.tmp) / "snap.json")
        # 基座含 API scene（s11_peer）——验证 web_research 写回对 API scene 字节级隔离
        base = {"stock_code": "300179", "stock_name": "四方达", "ts": "2026-09-16T00:00:00",
                "_warnings": [], "_data_summary": {"fetch_log": [], "total_fetches": 0},
                "s11_peer": {"data": {"items": [{"metric": "peer_margin", "value": "41.37%"}]},
                             "data_full": {}, "status": "ok", "_source": "em"}}
        json.dump(base, open(cls.snap, "w", encoding="utf-8"), ensure_ascii=False)
        cls._peer_md5 = cls._scene_md5()

    @classmethod
    def _scene_md5(cls):
        snap = json.load(open(cls.snap, encoding="utf-8"))
        return hashlib.md5(json.dumps(snap["s11_peer"], sort_keys=True).encode()).hexdigest()

    @classmethod
    def _run(cls, items_arg, *flags):
        return subprocess.run(
            [sys.executable, str(RUNNER), "web_research", "300179",
             "--snapshot", cls.snap, "--items", f"@{items_arg}", *flags],
            capture_output=True, text=True)

    def test_01_three_batches_twenty_no_loss(self):
        """病理序列重放：12+4+4 → 终态 20（修复前=4），union 内容零丢失（Q1）+ URL 保真（Q3）。"""
        for batch in ["batch1_12.json", "batch2_4.json", "batch3_4.json"]:
            r = self._run(FIXTURES / batch)
            self.assertEqual(r.returncode, 0, r.stderr)
        rows = _rows(self.snap)
        self.assertEqual(len(rows), 20)
        expect = {}
        for batch in ["batch1_12.json", "batch2_4.json", "batch3_4.json"]:
            for it in _fixture(batch):
                expect[it["topic"]] = it
        lost = [t for t in expect
                if not any(all(r.get(k) == expect[t].get(k) for k in CONTENT_KEYS) for r in rows)]
        self.assertEqual(lost, [])                          # Q1+Q3：5 键逐条全等
        self.assertEqual(len({r["topic"] for r in rows}), 20)  # 零重复行

    def test_02_union_resend_idempotent(self):
        """补救批（union 20 一次性重发）在 merge 语义下内容中性：零追加零覆盖告警、字节不变。"""
        union = str(FIXTURES / "batch1_12.json")  # 占位，下面拼 union 临时文件
        all_items = sum((_fixture(b) for b in
                         ["batch1_12.json", "batch2_4.json", "batch3_4.json"]), [])
        union = str(Path(self.tmp) / "union20.json")
        json.dump(all_items, open(union, "w", encoding="utf-8"), ensure_ascii=False)
        before = _content_md5(_rows(self.snap))
        r = self._run(union)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("appended=0, updated=20", r.stdout)
        self.assertEqual(_content_md5(_rows(self.snap)), before)

    def test_03_api_scene_byte_isolated(self):
        """web_research 写回不触碰 API scene（§3 盲区动态证明）。"""
        self.assertEqual(self._scene_md5(), self._peer_md5)

    def test_04_empty_batch_exit2_snapshot_frozen(self):
        """空批 exit 2 + 快照字节不变 + 既有 [web_research] 告警不丢（Q4）。"""
        empty = str(Path(self.tmp) / "empty.json")
        json.dump([], open(empty, "w", encoding="utf-8"))
        snap = json.load(open(self.snap, encoding="utf-8"))
        snap["_warnings"].append("[web_research] URL-only 1/20 条（测试哨兵）")
        json.dump(snap, open(self.snap, "w", encoding="utf-8"), ensure_ascii=False)
        before = hashlib.md5(open(self.snap, "rb").read()).hexdigest()  # 基线取点在哨兵注入后
        r = self._run(empty)
        self.assertEqual(r.returncode, 2)
        after = hashlib.md5(open(self.snap, "rb").read()).hexdigest()
        self.assertEqual(before, after)                     # 零写入
        self.assertTrue(any("测试哨兵" in w for w in
                            json.load(open(self.snap, encoding="utf-8"))["_warnings"]))

    def test_05_url_only_warning_survives_next_batch(self):
        """Q4：URL-only 告警=状态函数，跨批存活（修复前 S1 清警告=跨批丢失）。"""
        urlonly = str(Path(self.tmp) / "urlonly.json")
        json.dump([{"url": "https://example.com/a1"}, {"url": "https://example.com/a2"}],
                  open(urlonly, "w", encoding="utf-8"))
        r = self._run(urlonly)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("url_only=2", r.stdout)
        r2 = self._run(FIXTURES / "batch3_4.json")          # 后续干净批
        self.assertIn("url_only=2", r2.stdout)              # 计数跨批存活
        warns = json.load(open(self.snap, encoding="utf-8"))["_warnings"]
        self.assertEqual(sum("URL-only" in w for w in warns), 1)  # 恒一条（状态函数不累积）

    def test_06_correction_overwrites_and_warns(self):
        """修正批：同 topic 整行替换 + 计数不变 + ⑦覆盖留痕（旧值→新值进 _warnings）。"""
        corr = _fixture("batch3_4.json")[0]
        old_value = corr["value"]
        corr["value"] = "修正后的值-v2"
        corr_path = str(Path(self.tmp) / "corr.json")
        json.dump([corr], open(corr_path, "w", encoding="utf-8"), ensure_ascii=False)
        n_before = len(_rows(self.snap))
        r = self._run(corr_path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("appended=0, updated=1", r.stdout)
        rows = _rows(self.snap)
        self.assertEqual(len(rows), n_before)               # 计数不变
        hit = [x for x in rows if x["topic"] == corr["topic"]][0]
        self.assertEqual(hit["value"], "修正后的值-v2")
        self.assertEqual(len([x for x in rows if x["topic"] == corr["topic"]]), 1)
        warns = json.load(open(self.snap, encoding="utf-8"))["_warnings"]
        cov = [w for w in warns if "覆盖更新" in w]
        self.assertEqual(len(cov), 1)
        self.assertIn(old_value[:20], cov[0])               # 旧值留痕可溯（R1 缓解实证）

    def test_07_replace_rebuilds_with_s1_semantics(self):
        """--replace：整场重建（items=1）+ 旧 [web_research] 告警清空（S1 语义等价）。"""
        one = str(Path(self.tmp) / "one.json")
        json.dump([{"topic": "重建单条", "value": "v1", "provider": "p",
                    "url": "https://x/1", "query": "q"}],
                  open(one, "w", encoding="utf-8"))
        r = self._run(one, "--replace")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("mode=replace", r.stdout)
        rows = _rows(self.snap)
        self.assertEqual(len(rows), 1)
        warns = [w for w in json.load(open(self.snap, encoding="utf-8"))["_warnings"]
                 if "[web_research]" in w]
        self.assertEqual(warns, [])                         # URL-only 状态告警随状态消失（自清）


class TestAccountingCumulation(unittest.TestCase):
    """T12（S4·读侧协议）：--accounting 累积性——300179 防火。三批的账必须跨批累积，
    末批 accounting 不得覆盖前批（同型病理：批内快照直写=搜到没存的账本版）。"""

    def test_12_three_batches_ledger_cumulative(self):
        tmp = tempfile.mkdtemp(prefix="wr_acc_t12_")
        snap = str(Path(tmp) / "t12.json")
        json.dump({"stock_code": "300179", "stock_name": "四方达", "ts": "t",
                   "_warnings": [], "_data_summary": {"fetch_log": [], "total_fetches": 0}},
                  open(snap, "w", encoding="utf-8"), ensure_ascii=False)
        batches = [
            (10, {"raw_n": 40, "kept": 10, "discarded": 30, "retention": 0.25,
                  "discarded_detail": [{"id": "b1#q1e9", "rule": "dup_url", "reason": "首见 b1"}],
                  "caliber_flags": [{"file": "exa_b1", "unit": "B", "min": 3.23, "max": 14.6}],
                  "waivers": []}),
            (4, {"raw_n": 12, "kept": 4, "discarded": 8, "retention": 0.33,
                 "discarded_detail": [{"id": "b2#q1e2", "rule": "content", "reason": "弱相关"}],
                 "caliber_flags": [], "waivers": [{"file": "f.json", "reason": "限流"}]}),
            (4, {"raw_n": 8, "kept": 4, "discarded": 4, "retention": 0.5,
                 "discarded_detail": [{"id": "b3#q1e1", "rule": "dup_url", "reason": "首见 b1"}],
                 "caliber_flags": [], "waivers": []}),
        ]
        for bi, (n_items, acc) in enumerate(batches, 1):
            items = str(Path(tmp) / f"b{bi}.json")
            json.dump([{"topic": f"t{bi}-{k}", "value": f"v{bi}-{k}", "provider": "exa"} for k in range(n_items)],
                      open(items, "w", encoding="utf-8"), ensure_ascii=False)
            accf = str(Path(tmp) / f"acc{bi}.json")
            json.dump(acc, open(accf, "w", encoding="utf-8"), ensure_ascii=False)
            r = subprocess.run(
                [sys.executable, str(RUNNER), "web_research", "300179", "--snapshot", snap,
                 "--items", f"@{items}", "--accounting", f"@{accf}"],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        d = json.load(open(snap, encoding="utf-8"))["web_research_findings"]["data"]
        self.assertEqual(len(d["items"]), 18)
        acc = d.get("accounting") or {}
        self.assertEqual(acc.get("raw_n_total"), 60, f"三批 raw_n 须累积 40+12+8, 实得 {acc.get('raw_n_total')}")
        self.assertEqual(len(acc.get("per_batch") or []), 3, "per_batch 须三批留痕")
        b1_detail = [x for x in acc.get("discarded_detail", []) if x.get("id") == "b1#q1e9"]
        self.assertTrue(b1_detail, "批1 弃读明细须在批3 写回后存活(300179 防火)")
        self.assertTrue(acc.get("caliber_flags"), "批1 对撞 flag 须跨批存活")
        self.assertEqual(len(acc.get("waivers") or []), 1)
        fl = json.load(open(snap, encoding="utf-8")).get("_data_summary", {}).get("fetch_log", [])
        self.assertTrue(fl and "raw_n" in fl[-1].get("params", {}), "fetch_log.params 须增 raw_n 摘要")


if __name__ == "__main__":
    unittest.main()
