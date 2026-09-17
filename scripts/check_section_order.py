#!/usr/bin/env python3
"""R9 版面序检查/重排（判据 v5 前置机械化；检查器挂 c70/audit 全票，重排器挂发布路径）。

显示序 = 产品合同：速览(顶) → 一..十二。写作序（…七→十一→十→九→十二→八）是依赖驱动的
写作面事实，允许存在于写作过程；终验/发布前必须为显示序。
- 检查：--report <md>            违例 exit 1（FAIL 带观察序 + 修法）
- 重排：--report <md> --fix      章块整体搬运（### 子节随章），非合同 ## 头（附：等）保序缀尾
序数解析严格处理 十一/十二（禁『一、』『二、』子串误配）；3.10/3.11 为 ### 层，不参与 ## 检查。
"""
import argparse
import re
import sys

CONTRACT = ["速览", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]
NUM = {n: i for i, n in enumerate(CONTRACT)}
HEAD = re.compile(r"^##\s*(?:⚡\s*)?(速览(?!\S*[、])|[一二三四五六七八九]{1}|十[一二]?)[、（]?", re.MULTILINE)


def _scan(text):
    """返回 [(ordinal, header_line)]；非合同 ## 头不产出。"""
    out = []
    for m in HEAD.finditer(text):
        name = m.group(1)
        if name in NUM:
            out.append((NUM[name], m.group(0).strip()))
    return out


def check(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    found = _scan(text)
    ords = [o for o, _ in found]
    if len(set(ords)) != len(ords):
        dup = sorted({o for o in ords if ords.count(o) > 1})
        print(f"❌ R9 FAIL：章节重复 {[CONTRACT[o] for o in dup]}——先查删重再 --fix")
        return 1
    if ords == sorted(ords):
        print(f"✅ R9 PASS：显示序 {'→'.join(CONTRACT[o] for o in ords)}")
        return 0
    print("❌ R9 FAIL：章序违例（写作序直发）")
    print(f"  观察序：{'→'.join(CONTRACT[o] for o in ords)}")
    print(f"  合同序：{'→'.join(CONTRACT[o] for o in sorted(ords))}")
    print("  修法：python3 check_section_order.py --report <md> --fix（章块整体搬运，子节随章）")
    return 1


def fix(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    marks = list(HEAD.finditer(text))
    if not marks:
        print("❌ 无 ## 章头，无事可做")
        return 1
    preamble = text[:marks[0].start()]
    blocks = []  # (ordinal 或 None, 块文本)
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        name = m.group(1)
        blocks.append((NUM.get(name), text[m.start():end]))
    ordered = sorted((b for b in blocks if b[0] is not None), key=lambda b: b[0]) + \
              [b for b in blocks if b[0] is None]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(preamble + "".join(b[1] for b in ordered))
    print("✅ R9 重排完成：" + "→".join(CONTRACT[b[0]] if b[0] is not None else "附" for b in ordered))
    return 0


def main():
    ap = argparse.ArgumentParser(description="R9 版面序检查/重排")
    ap.add_argument("--report", required=True)
    ap.add_argument("--fix", action="store_true", help="重排至显示序（章块整体搬运）")
    a = ap.parse_args()
    sys.exit(fix(a.report) if a.fix else check(a.report))


if __name__ == "__main__":
    main()
