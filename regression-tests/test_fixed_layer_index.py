#!/usr/bin/env python3
"""
test_fixed_layer_index.py —— 固定层触发分册索引对拍（plan-compact-loop-fix-v4 批2 步2.2）

锁 CLAUDE.md 驻留层与外移分册的指针合同（驻留=索引+红线，分册=卷文件）：
  1. 索引表在位：≥4 条目，每条三要素齐全（触发词+路径+何时读，缺一=红）。
  2. 每条目路径 Path.exists()（防断链/改名逃逸——含 ~ 展开与目录形态）。
  3. 分册内容真实性：各卷含领域标记串（防空壳分册/只建文件不迁内容）。
  4. 驻留不回潮：已外移大块的特征串禁再出现在 CLAUDE.md（防内容悄悄搬回）。
  5. 红线行/测试集表/乙情景留守行在位（plan 6.1 三项驻留增量）。
  6. 触发词保留清单 token 在驻留层在场（指针可发现性合同）。

红极自证：schema 坏样例（删「何时读」列）必被 parser 报出；条目下限防空转绿。
反向覆盖（目录级「每文件被条目覆盖」）不实现——三个分册根目录均含合法非分册同目录
文件（_research/ 研究件、tdx-publish-v4/rules.md、docs/ 其它），目录 glob 会误伤；
孤儿分册风险由内容标记断言+条目下限+「新卷→加索引行→本测试转绿」扩展演练承接。
零网络纯离线。
"""
import re
import unittest
from pathlib import Path

CLAUDE_MD = Path.home() / "CLAUDE.md"
ORCH_ROOT = Path(__file__).resolve().parent.parent
VOL1 = ORCH_ROOT / "_research" / "engineering-paradigms.md"
VOL2 = Path.home() / "tdx-publish-v4" / "SOP.md"
VOL3 = Path.home() / ".claude" / "docs" / "tooling-playbook.md"

INDEX_HEADER = r"###\s*📚\s*触发分册索引"
ROW_RE = re.compile(r"^\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]*)\|")
PATH_RE = re.compile(r"`([^`]+)`")

# 已外移大块的特征串——驻留层零命中（回潮=红）
REGROWTH_MARKERS = [
    "Tavily — Bash 直连 REST",          # WebSearch 方法节（→卷3）
    "mcp__tavily__tavily_search",       # 同上
    "playwright.sync_api",              # 浏览器自动化节（→卷3）
    "feedcoopapi",                      # 豆包搜索节（→卷3）
    "push2his.eastmoney.com",           # 资金流 API 节（→s3-fund-flow.md）
    "stock_fund_flow_individual",       # 同上（全市场排行陷阱）
    "ensure_newest_first",              # 黄金范式节（→卷1）
    "make_latest_envelope",             # 信号信封/黄金范式节（→卷1）
    "_attach_series_latest_period",     # 黄金范式节（→卷1）
    "tdx_publish.py prepare",           # 发布 SOP 节（→卷2）
    "create_smartcanvas_by_mdx",        # 腾讯文档 SOP 节（→卷2）
]

# 分册领域标记——各卷 ≥ 全部命中（空壳卷=红）
VOLUME_MARKERS = {
    VOL1: ["ensure_newest_first", "make_latest_envelope", "双兜底", "latest_period"],
    VOL2: ["tdx_publish.py", "prepare", "verify"],
    VOL3: ["feedcoopapi", "Exa", "豆包", "playwright"],
}

# 触发词保留清单（plan 6.1）——驻留层全文含（缺=指针不可发现）
RESIDENT_TOKENS = [
    "websearch", "Exa", "豆包", "Tavily", "playwright", "chromium",
    "配额", "quota", "发布", "腾讯文档", "tdx", "pipeline", "scene",
    "gate", "信封", "季报测试集", "研报测试集", "龙虎榜", "北向",
    "股东户数", "资金流",
]


def index_section(text: str) -> str:
    m = re.search(INDEX_HEADER + r".*?(?=\n#{2,3} |\Z)", text, re.S)
    return m.group(0) if m else ""


def parse_index(section: str) -> list[dict]:
    """索引表段 → [{triggers, paths, when, summary}]；表头/分隔行跳过。
    三要素缺失的行记 {"_malformed": 原行}（红极用）。"""
    rows = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        if re.match(r"^\|\s*[-:| ]+\|", line) or ("触发词" in line and "何时读" in line):
            continue
        cells = line.split("|")
        cells = [c.strip() for c in cells[1:-1]] if len(cells) >= 3 else []
        if len(cells) != 4 or not all(cells[:3]):
            rows.append({"_malformed": line})
            continue
        rows.append({"triggers": cells[0], "paths": cells[1],
                     "when": cells[2], "summary": cells[3]})
    return rows


class TestFixedLayerIndex(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = CLAUDE_MD.read_text(encoding="utf-8")
        cls.section = index_section(cls.text)
        cls.rows = parse_index(cls.section)

    def test_index_section_present(self):
        self.assertTrue(self.section, "CLAUDE.md 缺「📚 触发分册索引」节（外移合同断裂）")

    def test_entry_count_floor(self):
        self.assertGreaterEqual(
            len([r for r in self.rows if "_malformed" not in r]), 4,
            f"索引条目 <4（空转绿风险）: {len(self.rows)}")

    def test_schema_three_essentials(self):
        bad = [r["_malformed"] for r in self.rows if "_malformed" in r]
        self.assertEqual(bad, [], f"三要素不齐的行（触发词|路径|何时读|摘要）: {bad}")

    def test_paths_exist(self):
        missing = []
        for r in self.rows:
            if "_malformed" in r:
                continue
            for p in PATH_RE.findall(r["paths"]):
                if not Path(p).expanduser().exists():
                    missing.append(p)
        self.assertEqual(missing, [], f"断链/改名逃逸的条目路径: {missing}")

    def test_volume_content_markers(self):
        for vol, markers in VOLUME_MARKERS.items():
            with self.subTest(vol=vol.name):
                self.assertTrue(vol.exists(), f"分册缺失: {vol}")
                content = vol.read_text(encoding="utf-8")
                absent = [m for m in markers if m not in content]
                self.assertEqual(absent, [], f"{vol.name} 空壳（缺领域标记）: {absent}")

    def test_resident_no_regrowth(self):
        regrown = [m for m in REGROWTH_MARKERS if m in self.text]
        self.assertEqual(regrown, [], f"已外移内容回潮驻留层: {regrown}")

    def test_redline_row_present(self):
        self.assertIn("工具红线", self.text, "红线行缺失")
        for token in ("豆包", "500", "Exa", "并发"):
            self.assertIn(token, self.text, f"红线要素缺失: {token}")

    def test_testset_table_present(self):
        for p in ("/home/ubuntu/regression-test-dataset/一季报测试集-DO-NOT-DELETE/",
                  "/home/ubuntu/regression-test-dataset/2026研报测试集-DO-NOT-DELETE/"):
            self.assertIn(p, self.text, f"测试集表路径缺失: {p}")

    def test_leftbehind_pointer(self):
        self.assertIn("engineering-paradigms", self.text,
                      "乙情景留守行（Gate 修复验证节尾）缺失")

    def test_trigger_tokens_resident(self):
        absent = [t for t in RESIDENT_TOKENS if t not in self.text]
        self.assertEqual(absent, [], f"触发词保留清单缺 token（指针不可发现）: {absent}")


class TestRedPoles(unittest.TestCase):
    """schema 红极：坏样例必被报，好样例必净——两极都见"""

    GOOD = """### 📚 触发分册索引（按需 Read，勿预载）

| 触发词 | 分册路径 | 何时读 | 摘要 |
|---|---|---|---|
| 改 pipeline；新 scene/gate/信封 | `~/.x/vol1.md` | 动码前 | 范式全文 |
| 发布/腾讯文档/tdx | `~/y/SOP.md` | 发布前 | 五步闸 |
"""

    def test_red_missing_when_cell(self):
        bad = self.GOOD.replace("| `~/.x/vol1.md` | 动码前 |", "| `~/.x/vol1.md` | |")
        rows = parse_index(index_section(bad))
        self.assertTrue(any("_malformed" in r for r in rows),
                        f"缺「何时读」的行未被报出: {rows}")

    def test_green_wellformed(self):
        rows = parse_index(index_section(self.GOOD))
        self.assertEqual([r for r in rows if "_malformed" in r], [])
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
