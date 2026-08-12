#!/usr/bin/env python3
"""事件层（东财大事提醒 timeline）回归测试：dedup 保真 + timeline 格式/KEEP/投影。

覆盖 plan 的 V1（dedup 类 bug：事件被静默吃掉）+ V2（格式/KEEP/投影类 bug）两类风险，
固化为契约。零网络、纯离线（构造 remind 行喂纯函数 `_dedup_remind_rows` / `_build_timeline`）。

V1 dedup：同一 INFO_CODE 可派生不同 EVENT_TYPE_CODE / NOTICE_DATE 的多个事件，去重键必须是
  (INFO_CODE,EVENT_TYPE_CODE,NOTICE_DATE) 三元组——只按 INFO_CODE 会吃掉「一份增发公告同时挂
  增发+解禁」的多事件（002230 实证）。
V2 timeline：KEEP 截断（NOTICE_DATE≤180d ∨ fatal 年龄豁免）/ 三桶 validity_state /
  fatal_events / by_code 闭合（Σlen(by_code[c])==len(events)，抓投影 bug）/ meta.counts /
  event 11 字段 / directional（002/003 LV1 关键词定方向）。

运行：python3 test_event_fetch.py（或经 run_regression.sh 串联）。
"""
import os, sys, unittest
from datetime import date

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', 'scripts')
sys.path.insert(0, os.path.join(SCRIPTS, 'lib'))
ROUTING = os.path.join(os.path.dirname(__file__), '..', '..', 'financial-data-routing')
sys.path.insert(0, ROUTING)

import runner
from runner import _dedup_remind_rows, _build_timeline

EVENT_FIELDS = ("notice_date", "event_type", "event_type_code", "specific", "belong_classif",
                "level1_content", "info_code", "flavor", "effective_date", "validity_state")
FATAL_CODES = {"330", "360", "430"}  # 代码级 fatal（条件升级 230/240/270 由 LV1/SPECIFIC 决定）


def _row(code, nd, lv1="", spec="", info_code="AN%d", etype="", belong=None, n=[0]):
    """构造一条 remind 原始行。info_code 默认每行唯一（同 INFO_CODE 多事件测试显式传同值）；
    传 None 表示市场事件无 INFO_CODE；传固定字符串表示同源公告。"""
    n[0] += 1
    if info_code and "%d" in info_code:
        info_code = info_code % n[0]
    return {"EVENT_TYPE_CODE": str(code), "NOTICE_DATE": nd, "LEVEL1_CONTENT": lv1,
            "SPECIFIC_EVENTTYPE": spec, "EVENT_TYPE": etype, "BELONG_CLASSIF": belong,
            "INFO_CODE": info_code}


class DedupPreservesTuples(unittest.TestCase):
    """V1：dedup 必须保住每个 distinct (INFO_CODE,EVENT_TYPE_CODE,NOTICE_DATE) tuple。"""

    def test_same_infocode_multiple_events_all_kept(self):
        """002230 实证：一份增发公告 (AN1) 派生增发180 + 解禁080×2，须全保留。"""
        AN1 = "AN1"
        rows = [
            _row("180", "2026-04-21", lv1="非公开发行9023万股", info_code=AN1),
            _row("080", "2026-10-26", lv1="解禁3.47%", info_code=AN1),
            _row("080", "2027-10-25", lv1="解禁0.28%", info_code=AN1),
        ]
        out = _dedup_remind_rows(rows)
        self.assertEqual(len(out), 3, "同一 INFO_CODE 的不同事件须全保留")
        tuples = {(r["INFO_CODE"], r["EVENT_TYPE_CODE"], str(r["NOTICE_DATE"])[:10]) for r in out}
        self.assertEqual(tuples, {(AN1, "180", "2026-04-21"),
                                  (AN1, "080", "2026-10-26"),
                                  (AN1, "080", "2027-10-25")})

    def test_identical_tuple_dropped(self):
        """完全相同的 (INFO_CODE,EVENT_TYPE_CODE,NOTICE_DATE) → 只留一条（fatal 补拉 vs 主拉取重叠）。"""
        AN1 = "AN1"
        rows = [
            _row("330", "2024-04-30", lv1="保留意见", info_code=AN1),
            _row("330", "2024-04-30", lv1="保留意见", info_code=AN1),
        ]
        self.assertEqual(len(_dedup_remind_rows(rows)), 1)

    def test_market_events_no_infocode_datecode_key(self):
        """市场事件（006/280/290/300/400 无 INFO_CODE）→ (None,code,date) 兜底去重。"""
        rows = [
            _row("006", "2026-05-01", info_code=None),
            _row("006", "2026-05-01", info_code=None),   # 同日同码 → drop
            _row("006", "2026-05-02", info_code=None),   # 异日 → 保留
        ]
        self.assertEqual(len(_dedup_remind_rows(rows)), 2)

    def test_no_infocode_collision_with_announcement(self):
        """无 INFO_CODE 的事件不得与有 INFO_CODE 的事件互相误并。"""
        rows = [
            _row("006", "2026-05-01", info_code=None),
            _row("180", "2026-05-01", info_code="AN1"),   # 同日不同码 + 一有一无 INFO_CODE
        ]
        self.assertEqual(len(_dedup_remind_rows(rows)), 2)


class TimelineFormatAndKeep(unittest.TestCase):
    """V2：_build_timeline 格式 / KEEP 截断 / 投影闭合。固定 today 使断言确定。"""

    TODAY = date(2026, 8, 10)
    CUTOFF = date(2026, 2, 11)  # today-180d

    @classmethod
    def _fixture(cls):
        """构造 6 行：1 旧非 fatal（应被 KEEP 丢）+ 1 旧 fatal（年龄豁免留）+ 4 近/未来。"""
        return [
            _row("004", "2026-06-09", lv1="2025年度分配10派4.4元", etype="分红送转"),        # catalyst, historical
            _row("280", "2025-12-01", lv1="股东户数41726户", etype="股东户数"),                # 旧非 fatal → 丢
            _row("330", "2024-04-30", lv1="保留意见", etype="非标审计意见"),                   # 旧 fatal → 留
            _row("080", "2026-09-11", lv1="解禁占总股本24.59%", etype="限售解禁"),             # risk, future
            _row("320", "2026-06-13", lv1="计划自2026-07-07起至2026-10-07减持", etype="增减持计划"),  # forward, active
            _row("003", "2026-07-15", lv1="预计业绩预增同比上升50%", etype="业绩预告"),        # directional→catalyst
        ]

    def test_keep_filters_old_nonfatal_keeps_old_fatal(self):
        tl = _build_timeline(self._fixture(), today=self.TODAY)
        codes = sorted(e["event_type_code"] for e in tl["events"])
        self.assertEqual(codes, ["003", "004", "080", "320", "330"], "旧非fatal须丢、旧fatal须留")
        # 280 被 KEEP 丢弃
        self.assertNotIn("280", {e["event_type_code"] for e in tl["events"]})

    def test_event_fields_present(self):
        tl = _build_timeline(self._fixture(), today=self.TODAY)
        self.assertGreater(len(tl["events"]), 0)
        for e in tl["events"]:
            for f in EVENT_FIELDS:
                self.assertIn(f, e, f"event 缺字段 {f}")
            self.assertIn(e["validity_state"], ("future", "active", "historical"))
            self.assertIn(e["flavor"], ("risk", "catalyst", "forward", "neutral"))

    def test_no_kept_event_over_180d_unless_fatal(self):
        tl = _build_timeline(self._fixture(), today=self.TODAY)
        cutoff_s = self.CUTOFF.isoformat()
        for e in tl["events"]:
            nd = e["notice_date"]
            if nd and nd < cutoff_s:
                self.assertTrue(e.get("fatal") or e["event_type_code"] in FATAL_CODES,
                                f"非 fatal 旧事件漏过 KEEP：{e['notice_date']} 码{e['event_type_code']}")

    def test_by_code_closure(self):
        """Σlen(by_code[c]) == len(events)：每事件恰落一桶，抓投影 bug。"""
        tl = _build_timeline(self._fixture(), today=self.TODAY)
        total = sum(len(v) for v in tl["by_code"].values())
        self.assertEqual(total, len(tl["events"]))

    def test_buckets_and_counts(self):
        tl = _build_timeline(self._fixture(), today=self.TODAY)
        c = tl["meta"]["counts"]
        self.assertEqual(c["events"], len(tl["events"]))
        self.assertEqual(c["future"] + c["historical"], c["events"])  # future(active∪future) ∪ historical
        self.assertEqual(len(tl["risk"]), c["risk"])
        self.assertEqual(len(tl["catalyst"]), c["catalyst"])
        self.assertEqual(len(tl["fatal_events"]), c["fatal"])
        # 330 fatal 必入 fatal_events + risk
        fatal_codes = {e["event_type_code"] for e in tl["fatal_events"]}
        self.assertIn("330", fatal_codes)
        risk_codes = {e["event_type_code"] for e in tl["risk"]}
        self.assertEqual(risk_codes, {"330", "080"})  # 330(旧fatal留) + 080(future)

    def test_directional_flavor_from_lv1(self):
        """003 业绩预告 LV1「预增/上升」→ catalyst（LV1 关键词定方向，非静态查表）。"""
        tl = _build_timeline(self._fixture(), today=self.TODAY)
        p003 = [e for e in tl["events"] if e["event_type_code"] == "003"]
        self.assertEqual(len(p003), 1)
        self.assertEqual(p003[0]["flavor"], "catalyst")

    def test_forward_window_validity_state(self):
        """320 增减持计划窗口 [2026-07-07, 2026-10-07] 含 today → active。"""
        tl = _build_timeline(self._fixture(), today=self.TODAY)
        p320 = [e for e in tl["events"] if e["event_type_code"] == "320"]
        self.assertEqual(len(p320), 1)
        self.assertEqual(p320[0]["validity_state"], "active")
        self.assertIn(p320[0], tl["active"])

    def test_future_event_validity(self):
        """080 解禁 NOTICE_DATE=2026-09-11 > today → future 桶。"""
        tl = _build_timeline(self._fixture(), today=self.TODAY)
        p080 = [e for e in tl["events"] if e["event_type_code"] == "080"]
        self.assertEqual(p080[0]["validity_state"], "future")
        self.assertIn(p080[0], tl["future"])

    def test_three_state_status_envelope(self):
        tl = _build_timeline(self._fixture(), today=self.TODAY)
        self.assertEqual(tl["status"], "ok")
        self.assertIn("latest_period", tl)
        self.assertIn(tl["latest_period"]["status"], ("ok", "failed"))
        self.assertEqual(tl["meta"]["body_fetch_count"], 0)  # 零 body fetch（默认）


class TimelineEmptyAndUnknown(unittest.TestCase):
    """边界：空 remind（真空 ok）/ 未知码（不崩，默认 neutral）/ P9 接入。"""

    def test_empty_remind_status_ok(self):
        """真空（0 remind）= 有效结论，status=ok 非 failed（与 fetch_failed 区分）。"""
        tl = _build_timeline([], today=date(2026, 8, 10))
        self.assertEqual(tl["status"], "ok")
        self.assertEqual(len(tl["events"]), 0)
        self.assertEqual(tl["meta"]["counts"]["events"], 0)
        self.assertIsNone(tl["latest_period"]["date"])

    def test_unknown_code_default_neutral_not_crash(self):
        """EVENT_TYPE_CODE 不在 45 码表 → flavor=neutral，事件原样进 timeline，未知码入 meta。"""
        rows = [_row("999", "2026-07-01", lv1="未知码事件", etype="X")]
        tl = _build_timeline(rows, today=date(2026, 8, 10))
        self.assertEqual(len(tl["events"]), 1)
        self.assertEqual(tl["events"][0]["flavor"], "neutral")
        self.assertIn("999", tl["meta"]["unknown_codes"])
        self.assertEqual(tl["events"][0], tl["by_code"]["999"][0])

    def test_p9_periods_injected_as_catalyst(self):
        """P9 月度经营（公告大全窄源）emit 为 catalyst pseudo-code P9。"""
        p9 = [{"公告日期": "2026-07-07", "公告标题": "2026年6月主要运营数据", "公告类型": "月度经营情况"},
              {"公告日期": "2026-06-08", "公告标题": "2026年5月主要运营数据", "公告类型": "月度经营情况"}]
        tl = _build_timeline([], p9_records=p9, today=date(2026, 8, 10))
        p9ev = [e for e in tl["events"] if e["event_type_code"] == "P9"]
        # ok 状态下最多 2 期入 timeline
        self.assertEqual(tl["p9_latest"]["status"], "ok")
        self.assertEqual(len(p9ev), 2)
        self.assertTrue(all(e["flavor"] == "catalyst" for e in p9ev))


if __name__ == "__main__":
    unittest.main(verbosity=2)
