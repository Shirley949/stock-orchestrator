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


if __name__ == "__main__":
    unittest.main(verbosity=2)
