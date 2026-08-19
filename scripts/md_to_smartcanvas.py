#!/usr/bin/env python3
"""md_to_smartcanvas.py — 发布侧报告 UI 转换器（gate 报告 → 腾讯智能文档 MDX）

管线位置：report.md → strip_src_for_publish.py → 本脚本 → mcporter create_smartcanvas_by_mdx

实测依据（2026-08-20 ui-test-20260820 文档回读验证，勿凭记忆改）：
  ✅ markdown 标题/表格/有序无序列表/引用/分割线/emoji — 原生渲染
  ✅ <Mark bold> — 组件路径绕开 CommonMark 侧翼规则，恒定加粗
  ❌ **X：**汉字 — 全角标点收尾+后接汉字 → 字面星号（SGR 渲染不稳定根因）
  ❌ <Mark backgroundColor> — 静默丢弃（黄色荧光笔不可用）
  ✅ <Callout blockColor borderColor icon> — 黄色高亮块唯一正确载体
  ✅ <Paragraph blockColor> — 段落底色
  ❌ HTML 注释 — 前台可见；❌ ~~删除线~~ 存疑 — 均禁用
  ⚠️ borderColor 必须 Strict 白名单（light_orange 会静默回退 green）

用法：
  python3 md_to_smartcanvas.py <input.md> <output.mdx> [--title 文档标题] [--icon 📈]
"""

import argparse
import re
import sys

# ---- 白名单（mdx_references.md 附录，实测确认）----
BORDER_COLORS = {"default", "grey", "blue", "sky_blue", "green", "yellow",
                 "orange", "red", "rose_red", "purple"}

FULLWIDTH_PUNCT = "：）」，。；、！？》』】"

# 事件区块的 Callout 配置：(标记正则, icon, blockColor, borderColor)
# 正则匹配 fix_bold 之后的形态（<Mark bold>未来事件</Mark>）
SECTION_CALLOUTS = [
    (re.compile(r"^<Mark bold>未来事件</Mark>.*$"), "⏳", "light_blue", "blue"),
    (re.compile(r"^<Mark bold>历史事件.*</Mark>.*$"), "✅", "light_grey", "grey"),
]
# 行级浅黄底的关键词——只用于「短句决策行」（评级结论/操作动作）。
# ⚠️ 高亮密度预算（2026-08-20 用户反馈「整段黄底就没有意义了」）：
#   黄底仅命中 ≤120 字符的行，长分析段一律不加底色（重点靠加粗）；
#   全文黄底 ≤5 处。满屏高亮 = 没有高亮。
PARA_HIGHLIGHT_KEYS = ("综合评级", "主推荐动作")
PARA_HL_MAX_LEN = 120
# 行内红色强调关键词（风险/止损类）
RED_LINE_KEYS = ("止损", "破位", "致命", "fatal")


def fix_bold(text: str) -> str:
    """**X** → <Mark bold>X</Mark>（组件路径，免疫全角标点侧翼失效）。

    单行内成对处理；跨行加粗在报告中不存在（模块规范单行加粗）。
    表格单元格内同样适用（实测 TableCell 内 Mark 正常）。
    """
    out = []
    for line in text.split("\n"):
        # 跳过代码围栏（报告理论无代码块，防御性保留）
        if line.strip().startswith("```"):
            out.append(line)
            continue
        # 逐个成对替换：非贪婪匹配，内容不含 * 与换行
        line = re.sub(r"\*\*([^*\n]+)\*\*", r"<Mark bold>\1</Mark>", line)
        out.append(line)
    return "\n".join(out)


def wrap_callout(lines: list[str], icon: str, block: str, border: str) -> list[str]:
    """把一组行包成三段式 Callout（缩进 4 空格）。"""
    assert border in BORDER_COLORS  # 白名单硬校验，防静默回退
    indented = []
    for ln in lines:
        indented.append("    " + ln if ln.strip() else "")
    return [f'<Callout icon="{icon}" blockColor="{block}" borderColor="{border}">',
            *indented, "</Callout>"]


def transform(src: str, title: str, icon: str) -> str:
    lines = src.split("\n")

    # 1) 全量 **X** → <Mark bold>X</Mark>（在结构处理前做，后续匹配用 Mark 形态）
    lines = fix_bold("\n".join(lines)).split("\n")

    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # 2) 事件区块：**未来事件**/**历史事件** 标记行起，到下一个标题/空行后非列表行止
        matched = None
        for pat, icon_, block_, border_ in SECTION_CALLOUTS:
            if pat.match(line):
                matched = (icon_, block_, border_)
                break
        if matched:
            icon_, block_, border_ = matched
            # 收集本区块正文：标记行之后的列表/普通行，遇标题或连续空行+非列表终止
            j = i + 1
            body = [line]  # 标记行本身也进 Callout（<Mark bold>未来事件</Mark> 作为小标题）
            while j < n:
                nxt = lines[j]
                if nxt.startswith("#"):
                    break
                if nxt.strip() == "":
                    # 空行后若还是列表项则继续（列表间空行），否则终止
                    k = j + 1
                    while k < n and lines[k].strip() == "":
                        k += 1
                    if k < n and (lines[k].lstrip().startswith(("-", "•", "*")) or re.match(r"^\d+\.", lines[k].lstrip())):
                        body.append("")
                        j = k
                        continue
                    break
                body.append(nxt)
                j += 1
            out.extend(wrap_callout(body, icon_, block_, border_))
            i = j
            continue

        # 3) 行级增强（在标题/表格行之外的普通段落与列表行）
        stripped = line.strip()
        is_list_item = (line.lstrip().startswith(("-", "•", "*"))
                        or re.match(r"^\d+\.", line.lstrip()))
        is_plain_para = (stripped and not line.startswith(("#", "|", ">"))
                         and not is_list_item
                         and not stripped.startswith("<Mark bold>未来事件")
                         and "<Callout" not in line)
        if is_plain_para:
            if (any(k in line for k in PARA_HIGHLIGHT_KEYS)
                    and len(stripped) <= PARA_HL_MAX_LEN):
                # 短句决策行：浅黄底（长段不配黄底——满屏高亮=没有高亮）
                out.append(f'<Paragraph blockColor="light_yellow">')
                out.append("    " + line)
                out.append("</Paragraph>")
                i += 1
                continue
        if (is_plain_para or is_list_item) and any(k in line for k in RED_LINE_KEYS):
            # 风险/止损行：既有加粗段转红字，无加粗则整行红（列表行仅红加粗段，保留 bullet 结构）
            red_line = re.sub(r"<Mark bold>([^<]*?)</Mark>",
                              r'<Mark bold color="red">\1</Mark>', line)
            if "<Mark" not in red_line:
                red_line = f'<Mark color="red">{red_line}</Mark>'
            out.append(red_line)
            i += 1
            continue

        out.append(line)
        i += 1

    body = "\n".join(out)

    # 4) frontmatter（title 必填；icon 单 emoji）
    fm = f"---\ntitle: {title}\nicon: {icon}\n---\n\n"
    return fm + body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--title", default=None, help="文档标题（默认取输入一级标题）")
    ap.add_argument("--icon", default="📈")
    args = ap.parse_args()

    src = open(args.input, encoding="utf-8").read()
    title = args.title
    if not title:
        m = re.search(r"^#\s+(.+)$", src, re.M)
        title = m.group(1).strip() if m else "股票分析报告"
    result = transform(src, title, args.icon)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(result)
    para_hl = result.count('blockColor="light_yellow"')
    print(f"OK {args.output} ({len(result)} chars, "
          f"bold={result.count('<Mark bold>')}, callout={result.count('<Callout')}, para_hl={para_hl})")


if __name__ == "__main__":
    main()
