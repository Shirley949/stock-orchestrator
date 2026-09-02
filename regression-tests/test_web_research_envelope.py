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
