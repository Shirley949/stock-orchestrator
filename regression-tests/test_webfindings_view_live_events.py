#!/usr/bin/env python3
"""webfindings 直读视图 + trade_sheet 事件日历读侧活算 契约测试（2026-10-06）。

背景（002222 实证）：web_research_findings 为写回期顶层 scene（标准信封 data.items），
fetch 期物化视图聚合它恒 stale，且物化层读 wr.items 裸键与信封错位 → 事件日历恒
「未拉取：0 条」，同会话无解（写回侧重物化被 §3 字节隔离 test_03 正确拦截）。
修复（雪球同构）：物化层不再聚合 webfindings（report_views 删块）；读取面
snapshot_view._webfindings_events 活算（§4 权威度分级唯一实现地）+ webfindings 直读视图。

两极：data.items 标准信封 → 事件出；旧裸键 items 信封 → 兼容等价；空 scene → 未拉取 label。
离线纯函数，零网络。
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import snapshot_view as sv  # noqa: E402


def _mk_snap(items_at="data"):
    items = [
        {"topic": "t_act", "entry_id": "e1", "url": "https://www.cninfo.com.cn/x",
         "value": "某公告全文含业绩说明"},
        {"topic": "t_ir", "entry_id": "e2", "url": "https://media.example.com/x",
         "value": "2026年9月1日召开业绩说明会、上半年营收7.24亿元"},
        {"topic": "t_plain", "entry_id": "e3", "url": "https://media.example.com/y",
         "value": "9月28日融资余额13.98亿元、超历史90%分位"},
    ]
    wr = {"scene": "web_research_findings", "_warnings": []}
    if items_at == "data":
        wr["data"] = {"status": "ok", "substantive": 3, "items": items}
    else:
        wr["items"] = items
    return {"web_research_findings": wr,
            "s4_technical": {"data": {"trade_sheet": {"view": "trade_sheet", "status": "ok",
                                                      "rows": [{"side": "卖", "type": "止损档（daily_ma20）",
                                                                "price": "65.107", "confirm_rule": "收盘跌破执行",
                                                                "action": "离场", "invalidation": "收回上方 2 日则取消"}]}}}}


class TestLiveEvents(unittest.TestCase):
    def test_01_standard_envelope_events_out(self):
        """正例：data.items 标准信封 → 实锤/待证分级出件（cninfo url=实锤；纯融资条目不入）。"""
        events, src = sv._webfindings_events(_mk_snap("data"))
        self.assertEqual(src, "web_research_findings")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["grade"], "实锤")
        self.assertEqual(events[1]["grade"], "待证")

    def test_02_bare_key_envelope_equivalent(self):
        """兼容极：旧裸键 items 信封 → 与标准信封逐字段等价。"""
        e1, s1 = sv._webfindings_events(_mk_snap("data"))
        e2, s2 = sv._webfindings_events(_mk_snap("bare"))
        self.assertEqual((e1, s1), (e2, s2))

    def test_03_empty_scene_not_pulled_label(self):
        """反例：无 scene → 0 条 + 未拉取 label（两极之反，豁免披露语义）。"""
        events, src = sv._webfindings_events({"s4_technical": {"data": {}}})
        self.assertEqual((events, src), ([], "未拉取（websearch 可选增强）"))

    def test_04_cap_five(self):
        """日历 cap 5 条（与原物化层 [:5] 语义一致）。"""
        snap = _mk_snap("data")
        snap["web_research_findings"]["data"]["items"] = [
            {"topic": f"t{i}", "entry_id": f"e{i}", "url": "https://x.example.com",
             "value": f"公告{i}"} for i in range(8)]
        events, _ = sv._webfindings_events(snap)
        self.assertEqual(len(events), 5)

    def test_05_trade_sheet_printer_live_overrides_stale_copy(self):
        """核心性质：物化副本里的 stale 事件被忽略，printer 只出 snap 活算结果。"""
        snap = _mk_snap("data")
        view = snap["s4_technical"]["data"]["trade_sheet"]
        view["event_calendar"] = [{"grade": "实锤", "text": "STALE-物化副本残留"}]
        view["event_calendar_source"] = "stale"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sv._print_trade_sheet(view, snap)
        out = buf.getvalue()
        self.assertIn("事件日历（web_research_findings）：2 条", out)
        self.assertIn("[实锤]", out)
        self.assertIn("[待证]", out)
        self.assertNotIn("STALE", out)

    def test_06_webfindings_view_printer(self):
        """webfindings 直读视图：status/items 计数 + topic/entry_id/url 清单形态冻结。"""
        v = _mk_snap("data")["web_research_findings"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sv._print_webfindings(v)
        out = buf.getvalue()
        self.assertIn("## webfindings status=ok items=3", out)
        self.assertIn("[t_act] e1", out)
        self.assertIn("url: https://www.cninfo.com.cn/x", out)

    def test_07_view_registered(self):
        """视图注册：webfindings 进 VIEW_PATHS 与 PRINTERS（--list 可见、直调可达）。"""
        self.assertIn("webfindings", sv.VIEW_PATHS)
        self.assertEqual(sv.VIEW_PATHS["webfindings"], ("web_research_findings",))
        self.assertIn("webfindings", sv.PRINTERS)


if __name__ == "__main__":
    unittest.main()
