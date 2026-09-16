#!/usr/bin/env python3
"""c2_compact_inject.py — C2 SessionStart(compact) hook 注入器（批4.4；批2 锚块升级）

stdin: Claude Code hook JSON（含 transcript_path）；stdout = 注入上下文的注入文本。
预算：≤2KB/次（preflight 实测超限部分被外存、上下文只留 ~2KB 预览）。

模式路由（单一语义单实现，与 token_audit IS_B_SESSION 同签名）：
  主信号 = transcript 内 runner A/B 调用形态计数（多者胜，B>A→B、仅 A→A）；
  副信号 = /tmp 下 modeB 清单 mtime 新于 modeA（transcript 零痕迹时）；
  兜底默认 A（A 版注入是 B 的超集 = 安全侧）。

A 版（批2）：命脉四要素 ①②③④ + T1 锚块 + 进度（D2 章节完成账）+ 恢复三态判定。
裁剪次序（超 2KB 时）：当前章命令 > 勾选表 > T1 标量 > 视图清单 > 进度。
2f 写作前退化：报告缺失或无 ## 章 → 只注入 勾选表+清单重读指引+--list。
"""
import glob
import json
import os
import re
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
for _p in (_SCRIPTS, os.path.join(_SCRIPTS, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

B_RE = re.compile(r"runner\.py[\"']?\s+B\s")
MAX_BYTES = 2048


def detect_mode(transcript_path: str) -> str:
    # 主信号决胜：transcript 同时含 A/B 痕迹时（如 A 会话引用过 B 票命令文本），
    # runner 调用形态计数多者胜；只有 A 痕迹 = 直接 A，不落副信号
    b_n = a_n = 0
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if B_RE.search(line):
                    b_n += 1
                elif re.search(r"runner\.py[\"']?\s+A\s", line):
                    a_n += 1
    except OSError:
        pass
    if b_n > a_n:
        return "B"
    if a_n > 0:
        return "A"
    # 副信号：modeB 清单 mtime 新于 modeA（transcript 不可读/零痕迹时）
    b = sorted(glob.glob("/tmp/analysis_checklist_*_modeB_*.md"), key=os.path.getmtime)
    a = sorted(glob.glob("/tmp/analysis_checklist_*_modeA_*.md"), key=os.path.getmtime)
    if b and (not a or os.path.getmtime(b[-1]) > os.path.getmtime(a[-1])):
        return "B"
    return "A"   # 兜底默认 A


def _latest(paths):
    c = sorted((p for p in paths if os.path.exists(p)), key=os.path.getmtime)
    return c[-1] if c else None


def render(mode: str, transcript_path: str = "", checklist: str = None,
           snapshot: str = None, report: str = None) -> str:
    cl = checklist or _latest(glob.glob(f"/tmp/analysis_checklist_*_mode{mode}_*.md"))
    if mode == "B":
        return "\n".join([
            "[C2·compact续接·模式B] ①首个取数动作=snapshot_view.py <最新快照> --list（禁 json.load 探查）",
            f"②B 模块 6 个 JIT（m38/m39/m3/m36/m37/m6）③清单：{cl or '未找到'}",
        ])
    snap = snapshot or _latest(glob.glob("/tmp/runner_snapshot_*_modeA.json"))
    rep = report or _latest(glob.glob("/tmp/analysis_report_*_modeA*.md"))
    return _render_a(cl, snap, rep, transcript_path)


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _ledger(cl_path, rep_text):
    """勾选台账 × 盘上锚 → [(sid, checked, present, mod, layout, sec_anchor)]（步序=PHASE3_STEP_ANCHORS）。"""
    from generate_checklist import PHASE3_STEP_ANCHORS
    text = _read(cl_path)
    out = []
    for sid, mod, layout, sec_anchor, grep_pat in PHASE3_STEP_ANCHORS:
        m = re.search(rf"- \[([ xX])\] <!--{re.escape(sid)}-->", text)
        if not m:
            continue
        present = bool(re.search(grep_pat, rep_text, re.MULTILINE)) if rep_text else False
        out.append((sid, m.group(1).lower() == "x", present, mod, layout, sec_anchor))
    return out


def _t1_scalars(snap_path, rep_text):
    """T1 锚块标量（禁空串禁崩溃：任一取不到给「?」占位）。"""
    code = name = cls = fw = price = "?"
    d = {}
    try:
        with open(snap_path, encoding="utf-8", errors="replace") as fh:
            d = json.load(fh)
    except Exception:
        pass
    code = d.get("stock_code") or code
    name = d.get("stock_name") or name
    cinfo = d.get("classification") or {}
    if isinstance(cinfo, dict):
        cls = cinfo.get("primary_type") or cls
        fw = cinfo.get("forbidden_metric") or fw
        if cls == "?":
            rule = (cinfo.get("evidence") or {}).get("matched_rule") or ""
            if rule:
                cls = f"?（{str(rule)[:24]}）"
    try:
        price = d["s2_quote_kline"]["data"]["realtime_quote"].get("current") or price
    except Exception:
        pass
    m = re.search(r"数据截止[：:]\s*(\d{4}-\d{2}-\d{2})", rep_text or "")
    d0 = m.group(1) if m else str(d.get("timestamp", ""))[:10] or "?"
    fatal = "无"
    try:
        fe = d["s5_events"]["data"]["risk_signals"]["processed"]["timeline"]["fatal_events"]
        if fe:
            e0 = fe[0]
            fatal = str(e0.get("event_type") or e0.get("description") or e0)[:60]
    except Exception:
        pass
    zh = "m6 未写"
    try:
        from section_locator import locate
        cap_slice, _diag = locate(rep_text or "")
        mz = re.search(r"中枢[^\d%]{0,8}([\d.]+)", cap_slice)
        if mz:
            zh = f"≈{mz.group(1)}元"
    except Exception:
        pass
    return code, name, cls, fw, price, d0, fatal, zh


_BUDGET_ALIAS = {  # 16 步 → 13 行：m2blk 尾两步共享 c61 四视图；m9blk 两步共享 c_d4 行
    "c_d2_safety": "c61", "c_d3_growth": "c61",
    "c_d4_dividend": "c_d4", "c_d5_governance": "c_d4",
}


def _budget_cmds(sid):
    """BUDGET_TABLE ②命令（别名映射外=零命令，禁误落他行）。"""
    try:
        from budget_probe import BUDGET_TABLE
    except Exception:
        return []
    key = sid if sid in {t[0] for t in BUDGET_TABLE} else _BUDGET_ALIAS.get(sid)
    if not key:
        return []
    for t_sid, _note, cmds, _budget in BUDGET_TABLE:
        if t_sid == key:
            return cmds
    return []


def _three_state_action(present):
    if present:
        return ("补跑④→⑤（1 grep+1 --section，不重写；④全臂 FAIL 且 reason 属内容缺失类"
                "→ --section '<锚>' --partial 确认残段→转重跑路径）")
    return "从①重跑整步（③ 前按节锚删残段兜底：先删『^<锚>.*?^(?=^#{1,2} )』区间再 append）"


def _render_a(cl, snap, rep, tp):
    rep_text = _read(rep) if rep else ""
    lines = [
        "[C2·compact续接·模式A] ①首个取数动作=snapshot_view.py <最新快照> --list（重建视图认知，禁 json.load 全树探查）",
        "②模块 JIT：写哪章读哪章；compact 后重读将写章节合法（台账=读过≠在context）；m11 仅首次 verify FAIL 才读",
        "③旧文按需重取走 --list/any/--field 投影（禁复读风暴，非禁重读）",
    ]
    sk = _latest(glob.glob("/tmp/analysis_skeleton_*.md"))
    # transcript_path 内联：load_skeleton 缺省 --latest 在并行会话下绑错（12:52 实证）
    tail = f"④清单：{cl or '未找到'}"
    if sk:
        tail += (f"｜骨架翻页=load_skeleton.py {sk} --transcript {tp or '<本会话jsonl>'}"
                 "（台账仅记历史，compact 后重读走当前章原子步①）")
    lines.append(tail)

    try:
        steps = _ledger(cl, rep_text)
    except Exception:
        steps = []

    # 2f 写作前退化分支：报告缺失或无 ## 章 → 只注入 勾选表+清单重读指引+--list
    if not rep_text or not re.search(r"^## ", rep_text, re.MULTILINE):
        done = [s for s in steps if s[1]]
        todo = [s for s in steps if not s[1]]
        lines.insert(1, f"[写作前退化] 报告未起章（{rep or '缺失'}）——按骨架推进，不注章命令")
        lines.append(f"勾选表: 已写 {len(done)}/{len(steps)}"
                     + (f"（{'·'.join(s[5] for s in done)}）" if done else "")
                     + f"｜待写 {len(todo)}（首步 {todo[0][0]}）" if todo else
                     f"勾选表: 已写 {len(done)}/{len(steps)}")
        lines.append(f"快照: {snap or '未找到'}｜--list 重建视图后再按清单步①起写")
        return "\n".join(lines)

    segs = []  # (裁剪优先级, 文本)；数值大=先裁（次序：进度4 > T1 3 > 当前章1，D3=0 恒留）
    # T1 锚块（prio 3）
    code, name, cls, fw, price, d0, fatal, zh = _t1_scalars(snap, rep_text)
    surface = "m4 事件扫描节"
    ms = re.search(r"^#{2,4}\s*(\d+(?:\.\d+)*)[^\n]*事件扫描", rep_text, re.MULTILINE)
    if ms:
        surface = f"§{ms.group(1)} 事件扫描节"
    segs.append((3, f"[T1·锚] {code} {name} modeA | classification={cls} 禁PE框架={fw}"
                    f" | 现价 {price}（{d0}）"))
    segs.append((3, f"fatal#1: {fatal}（G30 surface 锚={surface}）"))
    segs.append((3, f"数据截止: {d0}（G11 声明行照抄源）| snapshot: {snap or '未找到'}"))
    segs.append((3, f"中枢: {zh}（源=m6 capstone；未写时原样照抄兜底词，禁空串禁编造）"))

    # 进度 D2 章节完成账（prio 4 = 裁剪次序最先裁；勾选表与进度合并一行）
    done = [s for s in steps if s[1]]
    todo = [s for s in steps if not s[1]]
    prog = (f"进度: 已写 {len(done)}/{len(steps)}"
            + (f"（{'·'.join(s[5] for s in done)}）" if done else "")
            + f"｜待写 {len(todo)}（{'·'.join(s[5] for s in todo)}）" if todo else
            f"进度: 已写 {len(done)}/{len(steps)}（全部完成→走 c70 终验）")
    segs.append((4, prog))

    # 当前章命令 + 三态动作（prio 1 = 最保命）
    d3 = [s for s in done if not s[2]]
    if d3:
        segs.append((0, f"⛔异常态：步 {'、'.join(s[0] for s in d3)} 已勾但盘上锚不在场——"
                        "停下报告禁继续（疑误删/覆盖），人工核对，禁自行重写该章掩盖"))
    if todo:
        sid, _ck, present, mod, layout, sec_anchor = todo[0]
        cmds = " + ".join(
            "lib/capstone_panorama.py --snapshot" if c[:1] == ["PANO"] or c == ["PANO"]
            else "SV " + " ".join(c)
            for c in _budget_cmds(sid)) or "（零拉取，纯文本章）"
        five = (f"①Read modules/{mod}.md → ②{cmds} → ③Edit 报告 append『{layout}』"
                f" → ④$VG --section '{sec_anchor}' → ⑤勾[x]（磁盘为准）")
        segs.append((1, f"当前章 {sid}『{layout}』→ {_three_state_action(present)}\n{five}"))

    out = list(lines)
    for _p, text in segs:
        out.append(text)
    while len("\n".join(out).encode()) > MAX_BYTES:
        heavy = [i for i, (p, _t) in enumerate(segs) if p >= 1]
        if not heavy:
            break
        drop = max(heavy, key=lambda i: (segs[i][0], i))
        out.pop(len(lines) + drop)
        segs.pop(drop)
    return "\n".join(out)


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    tp = d.get("transcript_path", "")
    mode = detect_mode(tp) if tp and os.path.exists(tp) else "A"
    print(render(mode, tp))


if __name__ == "__main__":
    main()
