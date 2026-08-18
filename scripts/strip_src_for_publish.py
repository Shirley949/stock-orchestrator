#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strip_src_for_publish —— 报告发布层剥离器：本地 md → 外部文档（腾讯文档等）发布版。

用法：
    python3 strip_src_for_publish.py /tmp/analysis_report.md /tmp/analysis_report_publish.md

做什么：剥除全部溯源标记（gate 执法用，读者不需要）：
  · 明文形式  `[src: snapshot.x.y]` / `[src: websearch x]`
  · 注释形式  `<!-- [src: snapshot.x.y] -->`（历史速览块写法，一并兼容）

不做什么（保留原样）：
  · `[verified: self_score=N ...]` 指针行（发布版仍可回查 sidecar）
  · `[m6 §10.3]` 等非 src 括号引用
  · 行数 / 表格结构（剥离只发生在行内，管道行首尾不动）

⚠️ 只用于发布副本，**原报告 md 永不剥离**——verify_gates 扫的就是带 [src:] 的原文
（load_report 原样读入，禁剥 <!-- -->；剥离后的发布版不再过 gate）。
"""
import re
import sys

# 注释式优先剥（更长的模式先匹配），再剥明文式；含前置空白防剥后留双空格
_HIDDEN_SRC_RE = re.compile(r'[ \t]*<!--[ \t]*\[src:[^\]\n]*\][ \t]*-->')
_PLAIN_SRC_RE = re.compile(r'[ \t]*\[src:[^\]\n]*\]')


def strip_for_publish(text: str) -> str:
    """剥除全部 src 溯源标记（明文 + 注释两式），其余原样。"""
    out = _HIDDEN_SRC_RE.sub('', text)
    out = _PLAIN_SRC_RE.sub('', out)
    return out


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    src_path, dst_path = sys.argv[1], sys.argv[2]
    text = open(src_path, encoding='utf-8').read()
    out = strip_for_publish(text)
    # 出口断言：残留 = 剥离器漏模式（发布版带漏网标记 = 阅读噪音逃逸）
    residual = len(re.findall(r'\[src:', out))
    assert residual == 0, f'{residual} 个 [src: 残留——剥离模式有漏'
    assert out.count('\n') == text.count('\n'), '行数改变——剥离误伤换行'
    open(dst_path, 'w', encoding='utf-8').write(out)
    print(f'OK: 剥离 {text.count("[src:") - out.count("[src:")} 个 src 标记 '
          f'（{len(text)} → {len(out)} chars）→ {dst_path}')


if __name__ == '__main__':
    main()
