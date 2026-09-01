# -*- coding: utf-8 -*-
"""G28 杜邦链路完整性 + 东财 fallback 测试（2026-08-30 重设计配套）。

覆盖三层（mirror test_g48 范式，零网络 monkeypatch）：
1. check_g28 纯快照完整性两极：ok+四字段→PASS（Sina/EM 信封同构、金融股字段在场即 PASS）；
   缺字段/failed/整段缺失/ok+data空→FAIL。闭合校验已废弃（口径实证见 REFACTOR_LOG），
   旧 _closure_check 残留字段不读。
2. 编排两极（fetch_financial_unified 的 fallback 分支）：sina ok→EM 零调用；
   sina failed/空→EM 恰好 1 次（单次不重试）且结果落 result["dupont"]；双败→终态 failed。
3. _em_dupont_envelope reshape：EM rows[0]→中文 schema 四因子（归母占比×法含>100）、
   _profile 金融检测、latest_period 信封四因子；call(max_retries=0) 单次语义。
4. 轨2 mixed_caliber（裁决 D）：_dupont_caliber_probe 五态状态机 + 前置短路
   （Q1/EM fallback/无指纹）× G28 第三臂两极（confirmed 沉默 FAIL 照抄 note /
   已披露 PASS / 未确认三态现状 PASS）；边界语料另见 trap_corpus g28_caliber_*。

跑：python3 test_g28_dupont.py   接入 run_regression.sh 契约层。
"""
import sys, unittest
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
sys.path.insert(0, str(_LIB))
_ROUTING = Path(__file__).resolve().parents[2] / "financial-data-routing"
sys.path.insert(0, str(_ROUTING))

from gate_definitions import check_g28  # noqa: E402
import runner  # noqa: E402  (runner 自身 bootstraps scripts/lib)

CORE4 = {"净资产收益率": 7.29, "归属母公司股东的销售净利率": 4.76,
         "资产周转率(次)": 0.76, "权益乘数": 1.94}


def _snap(dup):
    return {"s1_financial": {"data": {"dupont": dup}}}


def _sina_ok(data=None):
    return {"status": "ok", "source": "curl_sina_dupont", "_grade": "A", "_warnings": [],
            "data": dict(data if data is not None else CORE4, period="2026-06-30"),
            "latest_period": {"value": dict(CORE4)}}


SINA_FAILED = {"status": "failed", "source": "curl_sina_dupont",
               "error": "sina_dupont 返回空", "_grade": "A", "_warnings": []}


class CheckG28PureSnapshot(unittest.TestCase):
    def test_ok_four_fields_pass(self):
        self.assertTrue(check_g28("", _snap(_sina_ok())))                       # Sina 主源

    def test_ok_em_envelope_pass(self):
        em = {"status": "ok", "source": "RPT_F10_FINANCE_DUPONT(东财)", "_grade": "A",
              "_warnings": ["降级东财"],
              "data": dict(CORE4, period="2026-06-30", _profile="normal"),
              "latest_period": {"value": dict(CORE4)}}
        self.assertTrue(check_g28("", _snap(em)))                              # 东财 fallback

    def test_financial_stock_fields_present_pass(self):
        fin = {"净资产收益率": 6.71, "归属母公司股东的销售净利率": 42.9,
               "资产周转率(次)": 0.013, "权益乘数": 10.19}
        self.assertTrue(check_g28("", _snap(_sina_ok(fin))))                    # 字段在场即 PASS

    def test_missing_field_fail(self):
        broken = dict(CORE4, **{"资产周转率(次)": None})
        self.assertFalse(check_g28("", _snap(_sina_ok(broken))))

    def test_failed_fail(self):
        self.assertFalse(check_g28("", _snap(SINA_FAILED)))

    def test_no_section_fail(self):
        self.assertFalse(check_g28("", {}))                                     # report-only 语义

    def test_ok_empty_data_fail(self):
        self.assertFalse(check_g28("", _snap({"status": "ok", "data": {}})))

    def test_stale_closure_check_ignored(self):
        # 旧快照 _closure_check 残留（closed=False 大残差）不影响新 gate——字段在场即 PASS
        legacy = _sina_ok(dict(CORE4, _closure_check={"applicable": True, "closed": False,
                                                     "residual_pp": 18.87}))
        self.assertTrue(check_g28("", _snap(legacy)))


class RunnerSourceContract(unittest.TestCase):
    """源码级契约：fallback 编排分支必须真实存在于 fetch_financial_unified（防上节复刻与
    实际代码漂移——复刻测试过而真实编排缺失 = 假绿）。"""

    def test_branch_present_in_runner(self):
        src = (_ROUTING / "runner.py").read_text(encoding="utf-8")
        self.assertIn("if _dupont_is_empty(dup):", src)
        self.assertIn("result[\"dupont\"] = _em_dupont_envelope(stock_code, dup)", src)
        # else 分支保主路径（Sina ok → EM 零调用）
        self.assertIn("result[\"dupont\"] = dup", src)


class FallbackOrchestration(unittest.TestCase):
    """monkeypatch _fetch_sina_dupont / runner._em_dupont_envelope，锁定分支与调用计数。"""

    def _run(self, sina_env):
        with mock.patch.object(runner, "_fetch_sina_dupont", return_value=sina_env), \
             mock.patch.object(runner, "_em_dupont_envelope",
                               side_effect=lambda code, env: {"status": "ok",
                                    "source": "RPT_F10_FINANCE_DUPONT(东财)",
                                    "data": dict(CORE4, period="2026-06-30"),
                                    "_warnings": ["降级东财"]}) as em_mock:
            # 复刻 fetch_financial_unified 内联编排（:655 区域，5 行分支）
            dup = runner._fetch_sina_dupont("000960")
            result = {}
            if runner._dupont_is_empty(dup):
                result["dupont"] = runner._em_dupont_envelope("000960", dup)
            else:
                result["dupont"] = dup
        return result, em_mock

    def test_sina_ok_no_em_call(self):
        result, em = self._run(_sina_ok())
        self.assertEqual(em.call_count, 0)                                      # EM 零调用零存储
        self.assertEqual(result["dupont"]["source"], "curl_sina_dupont")

    def test_sina_failed_em_once(self):
        result, em = self._run(SINA_FAILED)
        self.assertEqual(em.call_count, 1)                                      # 恰好 1 次
        self.assertEqual(result["dupont"]["source"], "RPT_F10_FINANCE_DUPONT(东财)")

    def test_sina_empty_fields_triggers_em(self):
        blank = {"status": "ok", "source": "curl_sina_dupont", "_grade": "A",
                 "_warnings": [], "data": {k: None for k in CORE4}, "latest_period": None}
        result, em = self._run(blank)
        self.assertEqual(em.call_count, 1)                                      # 拉回来等于空→触发
        self.assertEqual(result["dupont"]["source"], "RPT_F10_FINANCE_DUPONT(东财)")


class EmDupontReshape(unittest.TestCase):
    """_em_dupont_envelope：mock EM rows[0]（688209 真实形态，归母占比>100）。"""

    ROW = {"REPORT_DATE": "2026-06-30T00:00:00", "ROE": 4.63, "SALE_NPR": 12.7307878,
           "PARENT_NETPROFIT_RATIO": 100.88213643, "TOTAL_ASSETS_TR": 0.3233799,
           "EQUITY_MULTIPLIER": 1.092790374}
    FIN_ROW = {"REPORT_DATE": "2026-06-30T00:00:00", "ROE": 6.71, "SALE_NPR": 43.1690,
               "PARENT_NETPROFIT_RATIO": 99.3837673, "TOTAL_ASSETS_TR": 0.0132694,
               "EQUITY_MULTIPLIER": 10.1864108}

    def _fetch(self, rows, status="ok"):
        fake = {"status": status, "rows": rows, "report_name": "RPT_F10_FINANCE_DUPONT",
                "error": "mock"}
        import dongcai_client as dc
        with mock.patch.object(dc, "fetch_em_dupont", return_value=fake):
            return runner._em_dupont_envelope("000960", dict(SINA_FAILED))

    def test_reshape_fields_and_envelope(self):
        em = self._fetch([self.ROW])
        d = em["data"]
        self.assertEqual(em["status"], "ok")
        self.assertEqual(em["source"], "RPT_F10_FINANCE_DUPONT(东财)")
        self.assertEqual(d["period"], "2026-06-30")                             # REPORT_DATE 截日期
        self.assertEqual(d["净资产收益率"], 4.63)
        self.assertEqual(d["归属母公司股东的销售净利率"], round(12.7307878 * 100.88213643 / 100, 2))
        self.assertGreater(d["归属母公司股东的销售净利率"], d["销售净利率"])        # 占比>100 勿截断
        self.assertEqual(d["_profile"], "normal")
        self.assertEqual(sorted(em["latest_period"]["value"]),
                         ["净资产收益率", "权益乘数", "资产周转率(次)", "销售净利率"])  # 信封同 Sina
        self.assertTrue(any("期末口径" in w for w in em["_warnings"]))           # 口径标注在场

    def test_reshape_financial_profile(self):
        em = self._fetch([self.FIN_ROW])
        self.assertEqual(em["data"]["_profile"], "financial")                    # 周转<0.05 & 乘数>8

    def test_em_fail_terminal(self):
        em = self._fetch([], status="failed")
        self.assertEqual(em["status"], "failed")                                 # 终态，不重试
        self.assertIn("EM fallback 亦失败", em["error"])
        self.assertIn("sina_dupont 返回空", em["error"])                          # 双源 error 合并

    def test_max_retries_zero_single_attempt(self):
        import dongcai_client as dc
        from pathlib import Path
        import tempfile
        dc._THROTTLE_MIN_GAP = 0
        dc._DC_CACHE_DIR = Path(tempfile.mkdtemp())
        calls = []
        with mock.patch.object(dc, "_http_get", side_effect=lambda u, t: calls.append(u) or "HTTP_ERROR"):
            env = dc.call("RPT_F10_FINANCE_DUPONT", filter_col="SECUCODE",
                          filter_val="000960.SZ", max_retries=0)
        self.assertEqual(len(calls), 1)                                          # 单次不重试
        self.assertEqual(env["status"], "failed")


# ---------------------------------------------------------------------------
# 轨2 mixed_caliber（2026-09-02 裁决 D）：探针状态机 × G28 第三臂 两极
# 边界值取 001309 德明利 20260830 真面板（残差 rel 7.03% 触发侧；000960 无害侧
# 见 trap_corpus g28_caliber_*）；EM 全 monkeypatch，零网络。
# ---------------------------------------------------------------------------
_CAL_DATA = {"period": "2026-06-30", "净资产收益率": 92.24,
             "归属母公司股东的销售净利率": 35.58, "资产周转率(次)": 0.77, "权益乘数": 3.13}


def _cal_env(data=None, source="curl_sina_dupont"):
    return {"status": "ok", "source": source, "_grade": "A", "_warnings": [],
            "data": dict(data if data is not None else _CAL_DATA),
            "latest_period": {"value": dict(CORE4)}}


def _em_ok(roe=89.37, npr=14.0, pnr=100.0, tr=0.77, mult=8.3, date="2026-06-30"):
    # 默认形态=001309 实测：自洽 0.11% ∧ 追随 Sina 92.24 rel 3.11%（abs 2.87pp——
    # rel 单值判追随，abs 0.25pp 会误判不追随=裁决④ abs 必错案）
    return {"status": "ok", "rows": [{"REPORT_DATE": date, "ROE": roe, "SALE_NPR": npr,
                                      "PARENT_NETPROFIT_RATIO": pnr, "TOTAL_ASSETS_TR": tr,
                                      "EQUITY_MULTIPLIER": mult}]}


def _probe(state, **kw):
    base = {"state": state, "sina_roe": 92.24, "factor_product": 85.75,
            "residual_pp": 6.49, "residual_rel": 0.0703, "em_roe": 89.37,
            "em_selfcheck_rel": 0.0011, "em_track_rel": 0.0311,
            "em_period": "2026-06-30", "sina_period": "2026-06-30",
            "thresholds": {"residual_rel": 0.05, "tol_rel": 0.05}}
    base.update(kw)
    return base


_CAL_NOTE = ("⚠️ 杜邦口径说明：ROE 92.24% 为披露加权口径（东财交叉验证 89.37%，rel 偏差 3.11%），"
             "与三因子乘积 85.75%（均值口径因子）残差 6.49pp=源端混装（非提取错误）；"
             "ROE 直接引用、三因子分解单独解读，禁跨口径反算闭合 "
             "[src: snapshot.s1_financial.data.dupont]")
_DISCLOSE = "杜邦口径说明：ROE 为披露加权口径，与三因子乘积残差为源端混装，禁跨口径反算闭合。"


def _ok(ret):
    return ret if isinstance(ret, bool) else ret.get("passed", True)


class CaliberProbeStateMachine(unittest.TestCase):
    """runner._dupont_caliber_probe：五态状态机 + 前置短路（EM 全 mock）。"""

    def _probe(self, env, em=None):
        import dongcai_client as dc
        with mock.patch.object(dc, "fetch_em_dupont",
                               return_value=em if em is not None
                               else {"status": "failed", "rows": []}) as fem:
            runner._dupont_caliber_probe("001309", env)
        return env, fem

    def test_no_fingerprint_no_em_call(self):
        env, fem = self._probe(_cal_env(dict(CORE4, period="2026-06-30")))  # 000960 型 rel 3.73%
        self.assertNotIn("caliber_probe", env)
        self.assertEqual(fem.call_count, 0)                      # 无指纹零 EM 调用

    def test_confirmed_writes_note(self):
        env, fem = self._probe(_cal_env(), _em_ok())
        self.assertEqual(env["caliber_probe"]["state"], "confirmed")
        self.assertIn("禁跨口径反算闭合", env["caliber_note"])   # m2 §2.12 模板句
        self.assertEqual(fem.call_count, 1)

    def test_em_fetch_failed_state(self):
        env, _ = self._probe(_cal_env())                          # 默认 failed 信封
        self.assertEqual(env["caliber_probe"]["state"], "em_fetch_failed")
        self.assertNotIn("caliber_note", env)                     # 现状 PASS：不挂 note

    def test_em_self_broken_state(self):
        # 000960 EM 面板实测形态：EQUITY_MULTIPLIER 期末口径 vs ROE 加权 → 三因子积 6.4
        # ≠ ROE 11.34（rel 43%）→ referee 失格（裁决③A 认证失败，非重跑可修）
        env, _ = self._probe(_cal_env(), _em_ok(roe=11.34, npr=4.0, pnr=100.0,
                                                tr=0.2, mult=8.0))
        self.assertEqual(env["caliber_probe"]["state"], "em_self_broken")
        self.assertNotIn("caliber_note", env)

    def test_em_not_tracking_state(self):
        # 自洽（10×100/100×0.77×7.8=60.06≈ROE 60）但不追随 Sina 92.24（rel 35%）
        # → 提取错嫌疑形态（裁决②A：现状+注记，真实样本=重开触发器 #3 素材）
        env, _ = self._probe(_cal_env(), _em_ok(roe=60.0, npr=10.0, mult=7.8))
        self.assertEqual(env["caliber_probe"]["state"], "em_not_tracking")
        self.assertNotIn("caliber_note", env)

    def test_em_period_mismatch_state(self):
        env, _ = self._probe(_cal_env(), _em_ok(date="2026-03-31"))
        self.assertEqual(env["caliber_probe"]["state"], "em_period_mismatch")
        self.assertNotIn("caliber_note", env)

    def test_q1_period_shortcircuit(self):
        # Q1=Sina 自算简单平均（自闭合且与 EM 加权天然不追随）→ 探针不跑，防假阳性
        env, fem = self._probe(_cal_env(dict(_CAL_DATA, period="2026-03-31")), _em_ok())
        self.assertNotIn("caliber_probe", env)
        self.assertEqual(fem.call_count, 0)

    def test_em_fallback_source_shortcircuit(self):
        # EM fallback 面板无独立 referee → 探针不跑
        env, fem = self._probe(_cal_env(source="RPT_F10_FINANCE_DUPONT(东财)"), _em_ok())
        self.assertNotIn("caliber_probe", env)
        self.assertEqual(fem.call_count, 0)

    def test_wiring_in_fetch_financial_unified(self):
        # 源码契约（mirror RunnerSourceContract）：探针真实挂在 Sina 主路径 else 分支
        src = (_ROUTING / "runner.py").read_text(encoding="utf-8")
        self.assertIn("_dupont_caliber_probe(stock_code, dup)", src)


class CaliberGateThirdArm(unittest.TestCase):
    """check_g28 第三臂：confirmed→强制披露（禁荣誉制）；未确认三态→现状 PASS。"""

    def _dup(self, state, note=_CAL_NOTE, **kw):
        d = _cal_env()
        d["caliber_probe"] = _probe(state, **kw)
        if note:
            d["caliber_note"] = note
        return d

    def test_confirmed_silent_fails_with_verbatim_note(self):
        ret = check_g28("## 三、财务分析\nROE 92.24% 引领行业，盈利能力极强。\n",
                        _snap(self._dup("confirmed")))
        self.assertIsInstance(ret, dict)                          # 禁裸 bool（诊断契约 v2.1）
        self.assertFalse(ret["passed"])
        self.assertIn(_CAL_NOTE, ret["reasons"][0])               # reason 照抄 note 原句
        diag = ret["diag"]
        self.assertEqual(diag["subcheck"], "dupont_caliber_disclosure")
        for k in ("expected", "found", "fix", "src", "degraded"):
            self.assertIn(k, diag)
        self.assertFalse(diag["degraded"])
        self.assertIn("照抄", diag["fix"])                        # 报告侧修法（非 [数据层]）
        self.assertNotIn("[数据层]", ret["reasons"][0])

    def test_confirmed_with_disclosure_passes(self):
        self.assertTrue(_ok(check_g28("## 三、财务分析\n" + _DISCLOSE + "\n",
                                      _snap(self._dup("confirmed")))))

    def test_unconfirmed_states_pass_silent(self):
        # 裁决③A/②A：四未确认态一律现状 PASS（报告沉默也不 FAIL——FAIL 的是认证不是 verdict）
        rpt = "## 三、财务分析\nROE 92.24% 引领行业。\n"
        for state in ("em_fetch_failed", "em_self_broken", "em_not_tracking",
                      "em_period_mismatch"):
            self.assertTrue(_ok(check_g28(rpt, _snap(self._dup(state, note=None)))),
                            f"{state} 须现状 PASS")

    def test_no_probe_passes(self):
        # 旧快照（无 caliber_probe 键）结构零翻转
        self.assertTrue(_ok(check_g28("## 三、财务分析\nROE 92.24%。\n", _snap(_cal_env()))))

    def test_confirmed_note_missing_still_fails_when_silent(self):
        # 荣誉制防御：runner 写入异常（note 缺失）+ 报告沉默 → 仍 FAIL，reason 落
        # m2 §2.12 兜底模板（不静默放行）；报告已披露则照常 PASS（披露满足即合规）
        ret = check_g28("## 三、财务分析\nROE 92.24% 引领行业。\n",
                        _snap(self._dup("confirmed", note=None)))
        self.assertFalse(_ok(ret))
        self.assertIn("m2 §2.12", ret["reasons"][0])
        self.assertTrue(_ok(check_g28("## 三、财务分析\n" + _DISCLOSE + "\n",
                                      _snap(self._dup("confirmed", note=None)))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
