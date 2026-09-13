# -*- coding: utf-8 -*-
"""E批·pending #13：web_research_findings URL-only 拦截标记 两极 + 真实形态冻结。

裁决 f：scene 写入管道带实质 gate——URL-only（value/topic/provider 全空，仅存 URL 快照）
逐条 _url_only=True + substantive 计数剔除 + fetch_log url_only 记日志 + _warnings 规范化
WARN（经既有 G72 m8 点名 / precheck exit 3 披露通道执法）；不丢弃（URL 快照保 G21 溯源）。
真实极 = 688270 生产快照 14/14 URL-only 同构形态（2026-09-02 dump 实证：
keys=[_source,_verified,provider,query,topic,url,value]，非空仅 url/_source/_verified）。
零翻转锚：status 恒 ok/missing 恒等、items 计数恒等、结构化条目零 flag 零 WARN。
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS / "lib"))

from data_snapshot import DataSnapshot

# 真实形态冻结（688270 生产快照同构：LLM websearch 只回填 URL 的实际形状）
REAL_URL_ONLY_ITEM = {
    "topic": "", "value": None, "provider": "", "query": "",
    "url": "https://finance.example.com/research/688270",
    "_source": "llm_web_research", "_verified": False,
}
STRUCTURED_ITEM = {
    "topic": "全球供需预测", "value": "2027 全球需求 12 万片/年（Exa 摘要）",
    "provider": "exa", "url": "https://www.example.com/forecast",
    "query": "TaP substrate supply forecast 2027",
    "_source": "llm_web_research", "_verified": False,
}

URL_ONLY_WARN = ("[web_research] URL-only {n}/{tot} 条（value/topic/provider 全空，仅存 URL 快照）"
                 "——发现层产出未结构化，报告引用须标「未核实」")


def _bare_ds():
    ds = object.__new__(DataSnapshot)   # 免 IO：fetch_web_research 只用到 _fetch_log
    ds._fetch_log = []
    return ds


LEGACY_DOC_ITEM = {   # 2026-09-11 603256 首轮生产实锤：照 orchestrator SKILL.md 旧 schema 逐字传参
    "source": "财联社", "title": "宏和科技上半年电子布均价同比+147.61%",
    "url": "https://www.cls.cn/detail/2453864", "published": "2026-08-13",
    "content": "平均售价 11.91 元/米，同比+147.61%；原材料进价同比+229.21%",
}


class WebResearchKeyAliasContract(unittest.TestCase):
    """键名合同容错（F4 trap：入口文档旧 schema content/title/source 系 4 次生产复发）。

    别名键仅当目标键空时回填（防覆盖）；白名单外非空键不静默——命名 WARN + fetch_log 记账；
    引擎自有键（_ 前缀）豁免——scene 行重写回不产生假 WARN。
    """

    def test_legacy_doc_keys_aliased(self):
        """真实极：旧文档 schema 五键传入 → 自动映射 substantive=1，非 URL-only"""
        ds = _bare_ds()
        res = ds.fetch_web_research([dict(LEGACY_DOC_ITEM)])
        it = res["data"]["items"][0]
        self.assertEqual(it["topic"], "宏和科技上半年电子布均价同比+147.61%")
        self.assertIn("11.91", str(it["value"]))
        self.assertEqual(it["provider"], "财联社")
        self.assertFalse(it["_url_only"])
        self.assertEqual(res["data"]["substantive"], 1)
        self.assertNotIn("URL-only", str(res["_warnings"]))

    def test_unmapped_key_dropped_loud(self):
        """静默kill根因：白名单外非空键（published）必须命名 WARN + fetch_log 记账，禁无声丢"""
        ds = _bare_ds()
        res = ds.fetch_web_research([dict(LEGACY_DOC_ITEM)])
        self.assertTrue(any("published" in w for w in res["_warnings"]))
        self.assertEqual(ds._fetch_log[-1]["params"].get("dropped_keys"), ["published"])
        self.assertEqual(ds._fetch_log[-1]["params"].get("mapped"), 3)

    def test_alias_collision_prefers_canonical(self):
        """目标键已有值 → 别名值不覆盖、并入 dropped 命名（禁丢弃已持有信息）"""
        ds = _bare_ds()
        item = dict(STRUCTURED_ITEM, title="重复标题")
        res = ds.fetch_web_research([item])
        self.assertEqual(res["data"]["items"][0]["topic"], "全球供需预测")
        self.assertTrue(any("title" in w for w in res["_warnings"]))

    def test_engine_own_keys_exempt(self):
        """scene 行重写回（_ 前缀引擎自有键）→ 零假 WARN 零 dropped 记账"""
        ds = _bare_ds()
        first = ds.fetch_web_research([dict(STRUCTURED_ITEM)])
        rewrite = _bare_ds().fetch_web_research([dict(first["data"]["items"][0])])
        self.assertEqual(rewrite["_warnings"], [])
        params = ds._fetch_log[-1]["params"]
        self.assertNotIn("dropped_keys", params)
        self.assertNotIn("mapped", params)


class WebResearchUrlOnlyEnvelope(unittest.TestCase):
    def test_real_shape_url_only(self):
        """真实极：URL-only → flag True + WARN「URL-only 1/1」+ substantive=0；
        status 恒 ok（三态恒等：降级走 _warnings 记录，非 failed）"""
        ds = _bare_ds()
        res = ds.fetch_web_research([dict(REAL_URL_ONLY_ITEM)], topic_hint="t")
        it = res["data"]["items"][0]
        self.assertTrue(it["_url_only"])
        self.assertEqual(res["data"]["status"], "ok")
        self.assertEqual(res["data"]["substantive"], 0)
        self.assertEqual(len(res["data"]["items"]), 1)            # 不丢弃：items 计数恒等
        self.assertEqual([w for w in res["_warnings"] if "URL-only" in w],
                         [URL_ONLY_WARN.format(n=1, tot=1)])
        self.assertEqual(ds._fetch_log[-1]["params"]["url_only"], 1)
        self.assertEqual(ds._fetch_log[-1]["params"]["substantive"], 0)

    def test_structured_clean(self):
        """反极：结构化条目 → flag=False 零 WARN substantive=1（零翻转锚）"""
        ds = _bare_ds()
        res = ds.fetch_web_research([dict(STRUCTURED_ITEM)])
        self.assertFalse(res["data"]["items"][0]["_url_only"])
        self.assertEqual(res["_warnings"], [])
        self.assertEqual(res["data"]["substantive"], 1)
        self.assertEqual(ds._fetch_log[-1]["params"]["url_only"], 0)

    def test_mixed_count(self):
        """混合 1 实质 + 2 URL-only → flag 逐条正确 + WARN 计数 2/3"""
        res = _bare_ds().fetch_web_research(
            [dict(STRUCTURED_ITEM), dict(REAL_URL_ONLY_ITEM), dict(REAL_URL_ONLY_ITEM)])
        self.assertEqual([it["_url_only"] for it in res["data"]["items"]], [False, True, True])
        self.assertEqual(res["data"]["substantive"], 1)
        self.assertTrue(any("URL-only 2/3" in w for w in res["_warnings"]))

    def test_empty_missing_pinned(self):
        """空 → missing 恒等 + 空 items WARN（真空与降级可区分），无 URL-only WARN"""
        ds = _bare_ds()
        res = ds.fetch_web_research([])
        self.assertEqual(res["data"]["status"], "missing")
        self.assertEqual(res["_warnings"], ["[web_research] 空 items——LLM 未提供 websearch 发现"])
        self.assertEqual(ds._fetch_log[-1]["params"],
                         {"topic_hint": "", "items": 0, "url_only": 0, "substantive": 0})

    def test_dict_wrap_unwrap_pinned(self):
        """dict 包裹解包既有行为钉死（防回归）"""
        res = _bare_ds().fetch_web_research({"items": [dict(STRUCTURED_ITEM)]})
        self.assertEqual(len(res["data"]["items"]), 1)
        self.assertFalse(res["data"]["items"][0]["_url_only"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
