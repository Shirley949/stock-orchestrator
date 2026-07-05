#!/usr/bin/env python3
"""
test_data_contracts.py —— 数据契约 CI 的反例测试（S1-C / pact 化）

断言两件事：
  1. **反例全检出**：构造伪注册表（orphan / broken-consumer / 豁免路径 / 前缀匹配 /
     confidence-gating / consumer-tag），每个 check 行为符合预期（error 该报则报、
     不该报则静默、warn 降级正确）。
  2. **真实注册表零 error**：run_all(data_contracts.SCENES) 必须 errors == []，
     且锁定已知 warn 暴露面（s55 coverage_only、priceHighest/lowest consumed=False、
     7 项 non_confirmed 断链候选）——防 regression 把该暴露的问题静默吞掉。

S1 边界（plan §3.2）：本文件覆盖校验 1（orphan）/ 2（broken）/ 6（non_confirmed）
+ consumer-tag。校验 3（schema drift，S2）与 4（_EXPECTED_SCENES drift，S5）尚未实现，
故对应反例以 skip + TODO 占位，待 S2/S5 实现后取消跳过。**不伪测不存在的 check。**

零网络、纯离线。pact 化（2026-07-05）：本文件迁入主 skill regression-tests/，
路径用 __file__ 相对定位，脱离 gate-audit 工作区。运行见同目录 run_regression.sh。

用法：
    python3 test_data_contracts.py            # 或经 run_regression.sh 串联
"""
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"              # stock-orchestrator/scripts/
sys.path.insert(0, str(_SCRIPTS / "lib"))        # data_contracts / gate_definitions
sys.path.insert(0, str(_SCRIPTS))                # verify_data_contracts

import data_contracts as dc
import verify_data_contracts as vdc


def _scene(produces=None, consumers=None, coverage_only=False):
    """构造最小合法 scene（与 dc.SCENES 同构），便于反例注入。"""
    return {
        "fetcher": "fake_fetch", "mode": ["A"],
        "produces": produces or [],
        "consumers": consumers or {},
        "priority": dc.P1, "cost": {}, "depends_on": [], "fallback": {}, "cacheable": False,
        "coverage_only": coverage_only,
    }


class CounterExamples(unittest.TestCase):
    """反例：每个 check 在受控伪注册表上行为正确。"""

    def test_orphan_produce_is_error(self):
        """confirmed 产出 + 无 consumer + 非 coverage_only + 非 consumed=False → error。"""
        scenes = {"fake": _scene(
            produces=[{"path": "data.x", "confidence": dc.CONFIRMED}],
            consumers={},
        )}
        errs, _ = vdc.run_all(scenes)
        self.assertTrue(
            any(f.check == "orphan_produces" and f.severity == "error" for f in errs),
            f"应报 orphan error，实得 errs={errs}",
        )

    def test_orphan_coverage_only_downgrades_to_warn(self):
        """coverage_only scene（s55 模式）的孤儿产出降级为 warn，不阻塞 CI。"""
        scenes = {"fake": _scene(
            produces=[{"path": "data.x", "confidence": dc.CONFIRMED}],
            consumers={},
            coverage_only=True,
        )}
        errs, warns = vdc.run_all(scenes)
        self.assertEqual(errs, [], "coverage_only 不应产生 error")
        self.assertTrue(any(f.check == "orphan_produces" and f.severity == "warn" for f in warns))

    def test_orphan_consumed_false_downgrades_to_warn(self):
        """consumed=False（priceHighest_52week 模式）显式豁免孤儿校验，降级 warn。"""
        scenes = {"fake": _scene(
            produces=[{"path": "data.x", "confidence": dc.CONFIRMED, "consumed": False}],
            consumers={},
        )}
        errs, warns = vdc.run_all(scenes)
        self.assertEqual(errs, [], "consumed=False 不应产生 error")
        self.assertTrue(any(f.check == "orphan_produces" and f.severity == "warn" for f in warns))

    def test_broken_consumer_is_error(self):
        """consumer 引用了本 scene 不产出的字段 → error。"""
        scenes = {"fake": _scene(
            produces=[{"path": "data.x", "confidence": dc.CONFIRMED}],
            consumers={"data.y": ["m1"]},   # y 未产出
        )}
        errs, _ = vdc.run_all(scenes)
        self.assertTrue(
            any(f.check == "broken_consumer" and f.severity == "error" for f in errs),
            f"应报 broken_consumer error，实得 errs={errs}",
        )

    def test_consumer_subpath_is_not_broken(self):
        """consumer 读 produce 的子字段（前缀匹配）→ 合法，不报断链。"""
        scenes = {"fake": _scene(
            produces=[{"path": "data.x", "confidence": dc.CONFIRMED}],
            consumers={"data.x.sub": ["m1"]},
        )}
        errs, _ = vdc.run_all(scenes)
        self.assertFalse(
            any(f.check == "broken_consumer" for f in errs),
            f"子字段消费不应报断链，实得 errs={errs}",
        )

    def test_assumed_produce_not_flagged_as_orphan(self):
        """confidence gating：assumed 产出无 consumer 不触发 orphan error，仅 non_confirmed warn。"""
        scenes = {"fake": _scene(
            produces=[{"path": "data.x", "confidence": dc.ASSUMED}],
            consumers={},
        )}
        errs, warns = vdc.run_all(scenes)
        self.assertEqual(errs, [], "assumed 不应触发 hard orphan")
        self.assertTrue(any(f.check == "non_confirmed" for f in warns))

    def test_unknown_consumer_tag_warns(self):
        """consumer tag 不匹配 m/G/R/s\\d+|computed_metrics|_EXPECTED → warn。"""
        scenes = {"fake": _scene(
            produces=[{"path": "data.x", "confidence": dc.CONFIRMED}],
            consumers={"data.x": ["zzz_unknown_tag"]},
        )}
        _, warns = vdc.run_all(scenes)
        self.assertTrue(any(f.check == "consumer_tag" for f in warns),
                        f"应 warn consumer_tag，实得 warns={warns}")


class RealRegistry(unittest.TestCase):
    """真实注册表：零 error + 锁定已知 warn 暴露面。"""

    def setUp(self):
        self.errs, self.warns = vdc.run_all(dc.SCENES)

    def test_zero_errors(self):
        """核心防线：真实注册表必须 0 error（否则契约自相矛盾）。"""
        self.assertEqual(self.errs, [],
                         f"真实注册表存在契约 error，应修正：{self.errs}")

    def test_known_exposure_present(self):
        """锁定已知 warn（防 regression 静默吞掉该暴露的问题）。"""
        keys = {(f.check, f.scene, f.path) for f in self.warns}
        must = [
            ("orphan_produces", "s55_industry", "data"),
            ("orphan_produces", "futu_overview", "data.quote.priceHighest_52week"),
            ("orphan_produces", "futu_overview", "data.quote.priceLowest_52week"),
            ("non_confirmed", "futu_overview", "data.targetPrice.targetInfo.average"),
            ("non_confirmed", "s3_fund_flow", "data.fund_flow.items[].name"),
            ("non_confirmed", "s5_events", "data.news.data_full[].新闻内容"),
            ("non_confirmed", "s35_research_reports", "data.layer1.eps_consensus.current.mean"),
        ]
        for triple in must:
            self.assertIn(triple, keys, f"已知暴露面消失（可能被 regression 吞掉）：{triple}")

    def test_consumed_scenes_excludes_s55(self):
        """get_consumed_scenes() 排除 consumers={} 的 scene（S5 '消费才覆盖' 前置语义）。"""
        consumed = dc.get_consumed_scenes()
        self.assertIn("futu_forecast", consumed)
        self.assertNotIn("s55_industry", consumed, "s55 无消费者，不应计入 consumed")


class DeferredChecks(unittest.TestCase):
    """S2/S5 检查占位：实现后取消跳过。"""

    def test_schema_drift_counterexample(self):
        """校验3 双向覆盖：注册表多出字段→undocumented warn；doc 多出字段→not contracted warn。"""
        scenes = {"fake": _scene(
            produces=[{"path": "data.x", "confidence": dc.CONFIRMED}],
            consumers={"data.x": ["m1"]},
        )}
        # (a) 空 doc → 注册表路径 undocumented
        warns = vdc.check_schema_coverage(scenes, doc_paths=set())
        self.assertTrue(any("undocumented" in f.msg for f in warns),
                        f"空 doc 应触发 undocumented warn，实得 {warns}")
        # (b) doc 多出 fake.data.undoced → not contracted（注意 doc 路径须含 .data. 才计入）
        warns2 = vdc.check_schema_coverage(scenes, doc_paths={"fake.data.x", "fake.data.undoced"})
        self.assertTrue(any("not contracted" in f.msg and f.path == "fake.data.undoced" for f in warns2),
                        f"应触发 not contracted warn，实得 {warns2}")

    @unittest.skip("S5：_EXPECTED_SCENES 派生实现后加 drift 反例")
    def test_expected_scenes_drift_counterexample(self):
        # TODO S5: 断言 derived _EXPECTED_SCENES == gate_definitions._EXPECTED_SCENES
        self.fail("待 S5 实现 _EXPECTED_SCENES 派生")


if __name__ == "__main__":
    unittest.main(verbosity=2)
