#!/usr/bin/env python3
"""test_skeleton_schema.py — 批4.2/4.3：C1' 骨架 schema 锁 + load_skeleton 台账翻页副作用

红极自证：generate_checklist 无 --skeleton-out / load_skeleton.py 缺失时本测试必报错
（fixture 先行，先红后绿）。schema 单一真相源 = 本文件断言；模块顺序真相源 =
skill_dep_graph.MODE_MODULE_FILES（勿手抄清单）。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
GEN = SCRIPTS / "generate_checklist.py"
LOAD = SCRIPTS / "load_skeleton.py"
sys.path.insert(0, str(SCRIPTS / "lib"))
from skill_dep_graph import MODE_MODULE_FILES   # 顺序真相源（勿手抄）

PROMPT = "深度分析 603920，完整走一遍全流程"

failures = []


def check(name, ok, detail=""):
    print(f"  {'✅' if ok else '❌'} {name}" + (f"：{detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def gen_skeleton(mode="A"):
    """生成 checklist + skeleton 到临时目录，返回 (proc, checklist_path, skeleton_path)"""
    tmp = tempfile.mkdtemp(prefix="skel_test_")
    cl = str(Path(tmp) / "checklist.md")
    sk = str(Path(tmp) / "skeleton.md")
    r = subprocess.run(
        [sys.executable, str(GEN), "--user-prompt", PROMPT, "--mode", mode,
         "--stock-codes", "603920", "--output", cl, "--skeleton-out", sk,
         "--ignore-trap-ledger"],
        capture_output=True, text=True)
    return r, cl, sk


print("[1] A 模式骨架生成 + schema")
r, cl, sk = gen_skeleton("A")
check("generate_checklist exit 0", r.returncode == 0, r.stderr[-300:])
sk_path = Path(sk)
check("骨架文件已落盘", sk_path.exists())
text = sk_path.read_text(encoding="utf-8") if sk_path.exists() else ""

# schema 必填：标题/台账行/清单指针行
check("标题含 mode=A", "mode=A" in text and "加载骨架" in text)
check("台账行在场（指向本文件+load_skeleton 翻页）", "台账" in text and "load_skeleton" in text)
check("执行清单指针行在场", "执行清单" in text and "checklist" in text)

# 模块区：JIT 顺序 == MODE_MODULE_FILES.A（单源对拍，勿手抄）
mod_lines = [l for l in text.splitlines() if "references/modules/" in l and l.startswith("- ▸ ")]
expect = [e["path"] for e in MODE_MODULE_FILES["A"]]
got = [l.split(" ")[2] for l in mod_lines]
check(f"模块台账行数={len(expect)}（含 m11 延迟行）", len(mod_lines) == len(expect),
      f"got {len(mod_lines)}")
check("模块顺序 == MODE_MODULE_FILES.A（JIT 序）", got == expect, f"got={got}")
check("每行带 状态: 字段", all("| 状态:" in l for l in mod_lines))

# deferred 语义必须渲染（防骨架反而诱发重读 m11）
m11 = next((l for l in mod_lines if "m11-gates" in l), "")
check("m11 行渲染延迟语义", "延迟" in m11 and "verify" in m11, m11)

# 禁 [ ] / <!-- 前缀（防 update_checklist tick 误吞）
check("全文零 '[ ]' 前缀", "[ ]" not in text)
check("全文零 '<!--' c-tag", "<!--" not in text)

# Phase 骨架在场
check("Phase 骨架区在场", "Phase 骨架" in text and "Phase 0" in text and "Phase 5" in text)

print("[2] B 模式豁免（A-only 骨架）")
r, cl, sk = gen_skeleton("B")
check("B：checklist 仍生成", r.returncode == 0 and Path(cl).exists())
check("B：骨架不生成", not Path(sk).exists())
check("B：stdout 显式豁免说明", "豁免" in (r.stdout + r.stderr))

print("[3] load_skeleton 台账翻页（C0 副作用化）")
if LOAD.exists():
    # 合成 transcript：Read 事件命中 m12/m3/m11（含一次重复读——幂等性）
    reads = ["m12-summary", "m3-technical", "m11-gates", "m3-technical"]
    events = [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": f"t{i}", "name": "Read",
         "input": {"file_path": f"/home/ubuntu/.hermes/skills/stock-analysis/stock-analysis-quality/references/modules/{m}.md"}}
    ]}} for i, m in enumerate(reads)]
    tp = Path(cl).parent / "fake_transcript.jsonl"
    tp.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    r, cl, sk = gen_skeleton("A")
    out = subprocess.run([sys.executable, str(LOAD), sk, "--transcript", str(tp)],
                         capture_output=True, text=True)
    check("load_skeleton exit 0", out.returncode == 0, out.stderr[-300:])
    t2 = Path(sk).read_text(encoding="utf-8")
    mod2 = [l for l in t2.splitlines() if "references/modules/" in l and l.startswith("- ▸ ")]
    read_now = [l for l in mod2 if "状态:已读" in l]
    unread = [l for l in mod2 if "状态:未读" in l]
    check("翻页恰好 3 项（m12/m3/m11；重复读不重复计）", len(read_now) == 3,
          f"已读 {len(read_now)}")
    check("两态并存亲见（已读+未读）", len(read_now) >= 1 and len(unread) >= 1,
          f"已读 {len(read_now)} / 未读 {len(unread)}")
    check("m11 延迟语义翻页后保留", any("m11-gates" in l and "延迟" in l for l in read_now))
    check("stdout 出内容（骨架全文含状态）", "加载骨架" in out.stdout and "状态:已读" in out.stdout)
    # 幂等：重跑零新增
    out2 = subprocess.run([sys.executable, str(LOAD), sk, "--transcript", str(tp)],
                          capture_output=True, text=True)
    t3 = Path(sk).read_text(encoding="utf-8")
    check("幂等（重跑仍 3 项已读）", t3 == t2)
else:
    check("load_skeleton.py 存在", False, "脚本缺失（红态）")

print()
if failures:
    print(f"❌ {len(failures)} 项失败：{failures}")
    sys.exit(1)
print("✅ 骨架 schema + 台账翻页 全绿")
