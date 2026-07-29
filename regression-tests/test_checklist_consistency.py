#!/usr/bin/env python3
"""checklist 分母一致性回归测试（Bug 2）。

背景：generate_checklist 写 `0/47`（含 phase_1_skipped 3 项 + mapping 行 6 项无 c-tag），
update_checklist 只数 `<!--c[\\w]+-->`（38）→ 覆写 `X/38`。两分母数不同的东西，永不到 100%。

修复：generate:276 排除 phase_1_skipped；generate:316-322 给 mapping 行加 `c_map_N` c-tag
（c-tag 在 `[ ]` 之后，对齐 update:163 正则 `\[ ] <!--cid-->`）。两分母 → 同一 N。

本测试锁住：
  1. 分母一致：progress 行的 N == 文件 `<!--c[\\w]+-->` 计数；
  2. 100% 可达：全打勾后 checked==total；
  3. phase_1_skipped 不计入（❌ 永久跳过项无 c-tag、不被数）；
  4. mapping 行带 c_map_N c-tag 且可被 update_checklist 打勾；
  5. mode A / B 双模式均成立。
"""
import os, re, sys, tempfile, unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', 'scripts')
sys.path.insert(0, SCRIPTS)
import generate_checklist as gen
import update_checklist as upd

PROMPT_A = ("全量分析长电科技600584.SH 是否值得买？有技术壁垒吗？查看A股竞争对手，"
            "毛利率如何？查看2026年中报预增吗？目前全球市场供需如何？")

CTAG_RE = re.compile(r'<!--c[\w]+-->')
CHECKED_RE = re.compile(r'\[x\] <!--c[\w]+-->')


def _generate_to_file(prompt, mode, stock_codes=None):
    """生成清单写临时文件，返回 (path, content)。"""
    content = gen.generate_checklist(prompt, stock_codes=stock_codes, mode=mode)
    fd, path = tempfile.mkstemp(suffix='.md', prefix='checklist_test_')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path, content


def _progress_total(content):
    m = re.search(r'\*\*完成进度：\d+/(\d+)\*\*', content)
    return int(m.group(1)) if m else None


class ChecklistConsistencyTests(unittest.TestCase):

    def _assert_consistency(self, mode, stock_codes=None):
        path, content = _generate_to_file(PROMPT_A, mode, stock_codes)
        try:
            total = _progress_total(content)
            self.assertIsNotNone(total, "progress 行缺失")
            ctag_count = len(CTAG_RE.findall(content))

            # 1. 分母一致：progress N == c-tag 计数（Bug 2 核心）
            self.assertEqual(total, ctag_count,
                             f"[{mode}] 分母不一致：progress={total} vs c-tag 数={ctag_count}")

            # 3. phase_1_skipped 不计入：每个被数的 c-tag 都须是真实 checkbox 行
            #    （`[ ]` 或 `[x]` 紧邻 c-tag），❌ 跳过项无 c-tag
            checkbox_ctags = len(re.findall(r'\[[ x]\] <!--c[\w]+-->', content))
            self.assertEqual(checkbox_ctags, ctag_count,
                             f"[{mode}] 存在不带 checkbox 的 c-tag 或反之")

            # 4. mapping 行带 c_map_N c-tag（A 模式 prompt 必产 matched+unmapped）
            map_tags = re.findall(r'<!--(c_map_\d+)-->', content)
            self.assertGreaterEqual(len(map_tags), 1,
                                    f"[{mode}] mapping 行无 c_map_N c-tag")
            # c_map_N 唯一不撞现有 c01..c80 / c_d2_* / c_pdf_*
            non_map = re.findall(r'<!--(c(?!map_)(?:\w+))-->', content)
            self.assertFalse(any(t.startswith('map_') for t in []),
                             "正则兜底校验（不应命中）")

            # 4b. update_checklist 能打勾 mapping 行（c_map_1）
            first_map = map_tags[0]
            upd.update_checklist(path, check_ids=[first_map])
            with open(path, encoding='utf-8') as f:
                after = f.read()
            self.assertIn(f'[x] <!--{first_map}-->', after,
                          f"[{mode}] update_checklist 未能打勾 mapping c-tag {first_map}")

            # 2. 100% 可达：模拟全打勾（regex，不依赖 update 的 sys.exit 路径）
            all_ids = re.findall(r'\[ \] <!--(c[\w]+)-->', after)
            fully = re.sub(r'\[ \] <!--(c[\w]+)-->', r'[x] <!--\1-->', after)
            checked = len(CHECKED_RE.findall(fully))
            total_after = _progress_total(fully)
            self.assertEqual(checked, total_after,
                             f"[{mode}] 全打勾后 checked={checked} != total={total_after}（不可达 100%）")
        finally:
            os.unlink(path)

    def test_mode_a_consistency(self):
        self._assert_consistency("A", stock_codes="600584.SH")

    def test_mode_b_consistency(self):
        self._assert_consistency("B", stock_codes="600584.SH")


if __name__ == "__main__":
    unittest.main(verbosity=2)
