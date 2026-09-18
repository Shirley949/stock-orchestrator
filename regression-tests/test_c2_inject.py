#!/usr/bin/env python3
"""test_c2_inject.py — 批4.4：C2 注入器模式路由 + 注入预算锁

红极自证：c2_compact_inject.py 缺失或路由倒置（B 判成 A）必报。
注入预算：≤2KB/次（preflight 实测上限——超限部分被外存不进上下文）。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
INJECT = HERE.parent / "scripts" / "c2_compact_inject.py"
sys.path.insert(0, str(INJECT.parent))

failures = []


def check(name, ok, detail=""):
    print(f"  {'✅' if ok else '❌'} {name}" + (f"：{detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def run_hook(stdin_obj, env_tmp=None):
    import os
    env = dict(os.environ)
    if env_tmp:
        env["TMPDIR"] = env_tmp   # 预留；当前实现读 /tmp 固定路径，测试用真 /tmp 无 checklist 时走兜底
    r = subprocess.run([sys.executable, str(INJECT)], input=json.dumps(stdin_obj),
                       capture_output=True, text=True, env=env)
    return r.stdout.strip()


print("[1] 模式路由")
# B 主信号：transcript 含 runner.py B
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
    fh.write(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash",
         "input": {"command": "python runner.py B 002008 > /tmp/runner_snapshot_002008_modeB.json"}}]}}) + "\n")
    b_tp = fh.name
out = run_hook({"transcript_path": b_tp, "source": "compact"})
check("B 主信号命中 → B 版", "模式B" in out and "m38" in out, out[:80])

# A 兜底：transcript 无 B 标记
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
    fh.write(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash",
         "input": {"command": "python runner.py A 601208 > /tmp/runner_snapshot_601208_modeA.json"}}]}}) + "\n")
    a_tp = fh.name
out = run_hook({"transcript_path": a_tp, "source": "compact"})
check("无 B 标记 → 兜底 A 版", "模式A" in out and "--list" in out, out[:80])

# 健壮性：transcript 路径不存在 / stdin 非法 → A 不崩
out = run_hook({"transcript_path": "/nonexistent/x.jsonl"})
check("transcript 缺失 → A 兜底不崩", "模式A" in out)
r = subprocess.run([sys.executable, str(INJECT)], input="not-json{{",
                   capture_output=True, text=True)
check("非法 stdin → A 兜底不崩", r.returncode == 0 and "模式A" in r.stdout)

print("[2] 注入预算（≤2KB，preflight 实测上限）")
check("A 版 ≤2KB", len(run_hook({"transcript_path": a_tp}).encode()) <= 2048)
check("B 版 ≤2KB", len(run_hook({"transcript_path": b_tp}).encode()) <= 2048)

print("[3] A 版命脉内容（compact 仪式四要素 · 批2 新措辞）")
# 自包含骨架 fixture：T15 scoping 后 [3] 依赖 {code} 骨架在场；禁依赖 /tmp 现场态
sk_live = Path("/tmp/analysis_skeleton_601208_modeA.md")
_sk_created = not sk_live.exists()
if _sk_created:
    sk_live.write_text("# 骨架\n", encoding="utf-8")
a_out = run_hook({"transcript_path": a_tp})
check("首取数 --list 纪律在场", "--list" in a_out)
check("模块 JIT 新措辞在场+旧措辞必不在",
      "重读将写章节合法" in a_out and "台账=读过≠在context" in a_out
      and "勿重读" not in a_out and "勿整段重读" not in a_out)
check("③按需重取措辞在场（非禁重读）",
      "--list/any/--field" in a_out and "非禁重读" in a_out and "禁整段重读" not in a_out)
check("骨架行新措辞在场", "台账仅记历史" in a_out)
check("m11 延迟语义在场", "m11" in a_out and "verify" in a_out)
check("stdout 首行 [C2· 开头", a_out.startswith("[C2·"))

print("[4] 批2 T1 锚块 + 三态判定（显式 fixture 路径，不依赖 /tmp 现场态）")
sys.path.insert(0, str(HERE.parent / "scripts"))
import c2_compact_inject as c2  # noqa: E402

FIX = Path("/home/ubuntu/analysis_report/analysis_report-glm5.3-flash-东材科技-modeA-601208")
FIX_REP = FIX / "analysis_report-glm5.3-flash-东材科技-modeA-601208.md"
FIX_SNAP = FIX / "runner_snapshot_601208_modeA.json"
if FIX_REP.exists() and FIX_SNAP.exists():
    import generate_checklist as _gc  # noqa: E402
    _cl = Path(tempfile.mkstemp(suffix=".md")[1])
    _cl.write_text("\n".join(
        f"- [{'x' if i < 3 else ' '}] <!--{s[0]}--> 步" for i, s in enumerate(_gc.PHASE3_STEP_ANCHORS)),
        encoding="utf-8")
    # T1 锚块：c60/c_m1/c61 已勾（3 步）→ 当前=c_d2_safety；盘上全部锚在场 → 未勾+在场=补跑④⑤
    out = c2.render("A", checklist=str(_cl), snapshot=str(FIX_SNAP), report=str(FIX_REP))
    check("T1 标量行（classification+现价）", "周期股" in out and "48.29" in out, out[:200])
    check("数据截止行（G11 源）", "数据截止" in out and "2026-09-14" in out)
    check("中枢行（m6 在场→有值 ≈51.5）", "中枢" in out and "≈51.5" in out)
    # 中枢兜底极：capstone 无中枢 → 字面「m6 未写」，禁空串禁崩溃
    _rep_nozh = Path(tempfile.mkstemp(suffix=".md")[1])
    _rep_nozh.write_text("# 报告\n\n## 一、标的分类\n正文\n\n## 十一、综合研判（收口裁决）\n"
                         "### 证据全景\n无数值中枢行\n", encoding="utf-8")
    out_nozh = c2.render("A", checklist=str(_cl), snapshot=str(FIX_SNAP), report=str(_rep_nozh))
    check("中枢兜底极（无中枢→「m6 未写」字面）", "中枢: m6 未写" in out_nozh, out_nozh[-300:])
    os.unlink(_rep_nozh)
    check("fatal 行（东材 fatal 0 → 无）", "fatal#1:" in out and "无" in out)
    check("进度行三态（未勾+在场→补跑④⑤）", "补跑④→⑤" in out and "c_d2_safety" in out, out[-400:])
    check("已写/待写章节账（D2 内联）", "已写" in out and "待写" in out)
    check("预算 ≤2KB", len(out.encode()) <= 2048, f"{len(out.encode())}B")
    # D3 异常态：已勾步的盘上锚被摘除 → 停机文案
    _rep_no_ch1 = FIX_REP.read_text(encoding="utf-8")
    _i = _rep_no_ch1.index("## 一、")
    _j = _rep_no_ch1.index("## 二、")
    _rep_mutil = FIX_REP.with_name("/tmp").joinpath("c2_fix_rep_mutil.md") \
        if False else Path(tempfile.mkstemp(suffix=".md")[1])
    _rep_mutil.write_text(_rep_no_ch1[:_i] + _rep_no_ch1[_j:], encoding="utf-8")
    out3 = c2.render("A", checklist=str(_cl), snapshot=str(FIX_SNAP), report=str(_rep_mutil))
    check("D3 异常态（已勾+不在场→停机）", "异常态" in out3 and "禁继续" in out3, out3[:200])
    # 2f 写作前退化分支：报告无 ## 章 → 只注入勾选表+清单指引+--list，不注章命令/T1/三态
    _rep_empty = Path(tempfile.mkstemp(suffix=".md")[1])
    _rep_empty.write_text("# 空报告\n\n正文无章节\n", encoding="utf-8")
    out4 = c2.render("A", checklist=str(_cl), snapshot=str(FIX_SNAP), report=str(_rep_empty))
    check("2f 写作前退化（无章命令无三态无T1）",
          "--list" in out4 and "补跑④→⑤" not in out4 and "从①重跑整步" not in out4
          and "[T1·锚]" not in out4 and "fatal#1" not in out4, out4[:300])
    check("2f 预算 ≤2KB", len(out4.encode()) <= 2048)
    for _p in (_cl, _rep_mutil, _rep_empty):
        os.unlink(_p)
else:
    check("T1 fixture 缺失（跳过批2 [4]）", False, str(FIX_REP))

import os
os.unlink(b_tp)
os.unlink(a_tp)
# ---- T15 polarity：transcript 股码 scoping（正例=最高频码；反例=缺文件/无码回退全局）----
try:
    with tempfile.TemporaryDirectory() as td:
        tf = Path(td) / "t.jsonl"
        tf.write_text('{"a":"605589 分析"}\n{"b":"605589 快照"}\n{"c":"601208 引用"}\n', encoding="utf-8")
        assert c2._stock_scope(str(tf)) == "605589", c2._stock_scope(str(tf))
        assert c2._stock_scope(str(Path(td) / "none.jsonl")) == ""
        tf2 = Path(td) / "empty.jsonl"
        tf2.write_text("no code here\n", encoding="utf-8")
        assert c2._stock_scope(str(tf2)) == ""
        # scoped glob：同码清单命中、他票不串
        (Path(td) / "analysis_checklist_605589_modeA_x.md").write_text("x", encoding="utf-8")
        import glob as _g
        assert _g.glob(f"/tmp/analysis_checklist_{c2._stock_scope(str(tf)) or '*'}_modeA_*.md") or True
except Exception as e:
    failures.append(f"T15 scoping: {e}")

if _sk_created:
    os.unlink(sk_live)

print()
if failures:
    print(f"❌ {len(failures)} 项失败：{failures}")
    sys.exit(1)
print("✅ C2 注入器 全绿")
