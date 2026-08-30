# -*- coding: utf-8 -*-
"""src 标记写法与发布层剥离回归（2026-08-18 视认修订后契约）。

三组断言：
1. gate 对注释包裹 `<!-- [src: ...] -->` 的等价性（历史写法兼容：引擎免疫，但规范已否决
   该写法——smartcanvas 前台原样显示注释文本，发布层改用 strip_src_for_publish.py）
   · G21 提取正则 / G45 行级豁免 / _check_value_freshness 行级豁免 / G60 Layer1 锚
   · tally 表第 2 列方向词格放注释 = G62 禁区（漏数，防误用）
2. strip_for_publish：明文+注释两式全剥、[verified:] 指针保留、行数/表格结构不变
3. 转换器口径：明文→注释包裹往返无损（负向环视防双包裹）

mirror test_m6_gates 范式：sys.path.insert lib + from gate_definitions import ...
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from gate_definitions import check_g45, check_g60, _tally_table_counts, _check_value_freshness
from strip_src_for_publish import strip_for_publish


def _ok(r):
    """GateResult 兼容判定：bool 直返；dict 看 'passed'（getattr(dict,'passed') 恒 None 是坑）."""
    if isinstance(r, bool):
        return r
    if isinstance(r, dict):
        return r.get("passed") is True
    return getattr(r, "passed", False) is True


_SNAP = {"s1_financial": {"data": {"income_statement": {"data": [{"营业总收入": 100.0}]}}}}


class GateImmunityPlainVsHidden(unittest.TestCase):
    """① 注释包裹对 gate 执法点等价（明文与隐藏同 verdict）。"""

    def test_g45_line_exemption(self):
        plain = "机构目标价 2000 元 [src: snapshot.valuation_snapshot.data.targetPrice]"
        hidden = "机构目标价 2000 元 <!-- [src: snapshot.valuation_snapshot.data.targetPrice] -->"
        nosrc = "机构目标价 2000 元"
        multiline = "机构目标价 2000 元 <!--\n[src: snapshot.valuation_snapshot.data.targetPrice]\n-->"
        self.assertTrue(_ok(check_g45(plain, _SNAP)))
        self.assertTrue(_ok(check_g45(hidden, _SNAP)))
        self.assertFalse(_ok(check_g45(nosrc, _SNAP)))       # 必FAIL反例：执法分支进入
        self.assertFalse(_ok(check_g45(multiline, _SNAP)))   # 跨行注释破同线豁免

    def test_value_freshness_line_exemption(self):
        # 控制组：数值刻意偏离 snap，隔离出 src 通道（数值对齐是另一 grounded 通道）
        val, kw = 21.37, ("每股分红",)
        hidden = "本年度每股分红 99.99 元 <!-- [src: snapshot.s1_financial.dividend] -->"
        plain = "本年度每股分红 99.99 元 [src: snapshot.s1_financial.dividend]"
        nosrc = "本年度每股分红 99.99 元"
        self.assertTrue(_check_value_freshness(plain, val, kw))
        self.assertTrue(_check_value_freshness(hidden, val, kw))
        self.assertFalse(_check_value_freshness(nosrc, val, kw))

    def test_g60_layer1_anchor(self):
        head = "### 模块六：综合研判 Capstone\n#### Layer 1 — 证据全景\n"
        self.assertTrue(_ok(check_g60(head + "- 护城河：国内唯一 [src: snapshot.segment_composition.data]", _SNAP)))
        self.assertTrue(_ok(check_g60(head + "- 护城河：国内唯一 <!-- [src: snapshot.segment_composition.data] -->", _SNAP)))
        self.assertFalse(_ok(check_g60(head + "- 护城河：国内唯一", _SNAP)))  # 必FAIL反例

    def test_tally_direction_cell_is_forbidden_zone(self):
        """tally 第 2 列方向词格 = G62 禁区：注释使 cells[1] 精确匹配漏数。"""
        base = _tally_table_counts("| 证据A | 偏多 | 1.2 |")
        self.assertEqual(base["多"], 1)
        with_comment = _tally_table_counts("| 证据A | 偏多 <!-- [src: snapshot.s2_quote_kline.data] --> | 1.2 |")
        self.assertEqual(with_comment["多"], 0)   # 漏数实锤 = 禁区存在
        # 非方向词格（第 3 列）放注释安全
        safe = _tally_table_counts("| 证据A | 偏多 | 1.2 <!-- [src: snapshot.s2_quote_kline.data] --> |")
        self.assertEqual(safe["多"], 1)


class StripForPublish(unittest.TestCase):
    """② 发布层剥离：两式全剥、指针保留、结构不变。"""

    def test_strips_both_forms_and_keeps_pointer(self):
        t = ("[verified: self_score=95 profile=full | see analysis_report.verified.json]\n"
             "现价 1590 [src: snapshot.s2_quote_kline.data.realtime_quote] 元\n"
             "PE <!-- [src: snapshot.valuation_snapshot.data.quote] --> TTM 558")
        out = strip_for_publish(t)
        self.assertNotIn("[src:", out)
        self.assertNotIn("<!--", out)
        self.assertIn("[verified:", out)          # 指针保留
        self.assertEqual(out.count("\n"), t.count("\n"))

    def test_fixture_structure_invariant(self):
        """固化语料剥离不变性：行数/表格行数不变，[src:] 两式零残留，指针保留。

        断言收窄说明（2026-08-27）：旧版曾全局断言零 `<!--` 并采样公共路径
        /tmp/analysis_report.md——该路径被任意会话复写后，非 src 的模板占位注释
        （如中科曙光样本的 `<!-- PART-B -->`）造成脆断。strip 职责只剥 src 隐藏
        注记，不属其职责面的注释不再纳入契约；语料改用仓库内 fixture（消除环境耦合）。
        """
        path = Path(__file__).resolve().parent / "fixtures" / "strip_publish_sample.md"
        t = path.read_text(encoding="utf-8")
        out = strip_for_publish(t)
        self.assertEqual(out.count("\n"), t.count("\n"))
        self.assertNotIn("[src:", out)
        # 模板类注释（无 src 标记）原样保留 = 职责边界自证
        self.assertIn("<!-- PART-B -->", out)
        pipes = lambda s: sum(1 for l in s.splitlines() if l.strip().startswith("|"))
        self.assertEqual(pipes(t), pipes(out))
        self.assertIn("[verified:", out)


class ConverterRoundtrip(unittest.TestCase):
    """③ 明文→注释包裹转换口径（历史工具 /tmp/convert_hidden.py 的契约钉死）。"""

    SRC_RE = re.compile(r"(?<!<!-- )\[src: ((?:snapshot\.|websearch|s\d+_)[^\]\n]+)\]")

    def test_roundtrip_and_no_double_wrap(self):
        t = "营收 2.46 [src: snapshot.s1_financial.income.revenue] 亿"
        hidden = self.SRC_RE.sub(lambda m: f"<!-- [src: {m.group(1)}] -->", t)
        self.assertEqual(len(self.SRC_RE.findall(hidden)), 0)          # 零未包裹残留
        self.assertEqual(hidden.count("[src:"), t.count("[src:"))      # 标记本体无损
        again = self.SRC_RE.sub(lambda m: f"<!-- [src: {m.group(1)}] -->", hidden)
        self.assertEqual(again, hidden)                                 # 幂等（防双包裹）
        # 非 src 括号不误伤
        t2 = "见 [m6 §10.3] 与 [verified: self_score=95]"
        self.assertEqual(self.SRC_RE.findall(t2), [])


if __name__ == "__main__":
    unittest.main()
