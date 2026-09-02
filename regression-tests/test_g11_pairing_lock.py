#!/usr/bin/env python3
"""test_g11_pairing_lock.py — G11 字面锚配对锁（P1a 2026-09-03，病类 B 双源漂移）。

锁对象：模板文档（m38/m12/m8）教给写作侧的声明行 ⇄ check_g11 正则，两侧锁死。
病灶：m38/m12 只用名词短语「数据截止声明（G11）」从未给字面行，模式 B 又不加载
m8 → 写作侧自造形态（`**数据截止声明**：`+冒号后接散文）→ 正则三重不匹配
（名词插入/加粗/日期不相邻）→ 2026-09-02 双批 G11×2 复发，终稿 workaround 两种
形态 = 漂移实证。修法：三文档统一字面锚 `📅 数据截止：YYYY-MM-DD`。

活文档投影：运行时读 m38/m12/m8 原文提取 backtick 字面锚喂真 check_g11——
禁第三份拷贝（文档改了测试自动跟随；文档丢锚 = 本测试红）。
锁法 = rot-one-when-it-rots：只锁烂过的锚，不预锁未烂的。

跑：python3 test_g11_pairing_lock.py
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from gate_definitions import check_g11  # noqa: E402

# 活文档（运行时读原文，禁拷贝进本文件）
_MODULES = Path(__file__).resolve().parent.parent.parent / "stock-analysis-quality" / "references" / "modules"
_DOCS = {
    "m38": _MODULES / "m38-b-conclusion-head.md",
    "m12": _MODULES / "m12-summary.md",
    "m8": _MODULES / "m8-disclaimer.md",
}
_CANON = "📅 数据截止：YYYY-MM-DD"   # 统一字面锚（三文档 backtick 内）
_DATE = "2026-09-02"

# 冻结红极：2026-09-02 双批首写 verbatim + 终裁令点名名词形态——防正则放宽到「什么都吃」
_BROKEN_FORMS = [
    "📅 **数据截止声明**：实时行情为 2026-09-02 11:30 午间快照（当日盘中，非收盘）；日K线序列截至 2026-09-01 收盘。",
    "📅 **数据截止声明（G11）**：实时行情/分时为 2026-09-02 11:30 上午收盘快照（午间休市，非全日收盘）。",
    "数据截止声明：2026-09-02",
]

# 双批终稿 workaround 形态（含合规子串）——归档报告不回溯翻红
_LEGACY_FINALS = [
    "📅 **数据时效声明｜数据截止：2026-09-02**（实时行情为当日 11:30 午间快照，非收盘）",
    "📅 **数据截止声明（G11）**：数据截止：2026-09-02。实时行情/分时为 2026-09-02 11:30 快照",
]


def _res(report):
    out = check_g11(report, {})
    return (True, []) if out is True else (bool(out), out.get("reasons", []))


def _pad(line):
    """声明行 → 前 500 字检查窗内的最小报告（正文填充不触发表格臂）。"""
    return line + "\n" + "正文填充。" * 100


def _doc_spans(text):
    """提取文档 backtick 内含「数据截/至」的字面锚（fenced 块外的行内 code span）。"""
    return re.findall(r"`([^`\n]*数据[截止至][^`\n]*)`", text)


class TestG11PairingLock(unittest.TestCase):
    def test_canonical_form_passes(self):
        ok, _ = _res(_pad(_CANON.replace("YYYY-MM-DD", _DATE)))
        self.assertTrue(ok)

    def test_broken_forms_still_fail(self):
        """冻结红极：名词插入形态必须 FAIL——正则放宽会在此响铃（锁的放宽方向）。"""
        for form in _BROKEN_FORMS:
            with self.subTest(form=form[:30]):
                ok, reasons = _res(_pad(form))
                self.assertFalse(ok, reasons)
                self.assertIn("G11", reasons[0])

    def test_legacy_final_forms_keep_passing(self):
        """双批终稿（含合规子串的 workaround 形态）不回溯翻红——归档兼容不变式。"""
        for form in _LEGACY_FINALS:
            with self.subTest(form=form[:30]):
                ok, _ = _res(_pad(form))
                self.assertTrue(ok)

    def test_live_docs_feed_real_gate(self):
        """活文档投影：m38/m12/m8 各须含 ≥1 个 backtick 字面锚，填日期喂真 check_g11 必 PASS。

        文档丢锚（有人把字面行改回名词短语/删掉）→ spans 为空 → 本测试红。
        文档改锚为不匹配形态 → check_g11 FAIL → 本测试红。两侧都锁。
        """
        for name, path in _DOCS.items():
            with self.subTest(doc=name):
                self.assertTrue(path.exists(), f"{name} 不存在: {path}")
                spans = _doc_spans(path.read_text(encoding="utf-8"))
                self.assertGreaterEqual(
                    len(spans), 1,
                    f"{name} 无 backtick 字面声明锚——写作侧无可抄合规行（2026-09-02 双批 G11 复发病根）")
                for span in spans:
                    filled = span.replace("YYYY-MM-DD", _DATE).replace("YYYY-MM-DD HH:MM", f"{_DATE} 15:30")
                    ok, reasons = _res(_pad(filled))
                    self.assertTrue(ok, f"{name} 锚不匹配 G11 正则: {span!r} → {reasons[:1]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
