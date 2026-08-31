#!/usr/bin/env python3
"""批2 五条引擎根因 monkeypatch 原型——不动文件，产 pre-declare 翻转证据。

用法：python3 _research/b2_prototype.py（在 stock-orchestrator 仓根；2026-08-31 自 /tmp 迁入）
输出：P1/P2a/P2b/P5 归档 44 对 verdict 差分 + 单元级 FAIL→PASS 演示 + P4 reason 演示。
"""
import copy
import json
import re
import sys
from pathlib import Path

HERE = Path("~/.hermes/skills/stock-analysis/stock-orchestrator").expanduser()
sys.path.insert(0, str(HERE / "scripts"))
sys.path.insert(0, str(HERE / "scripts" / "lib"))
sys.path.insert(0, str(HERE / "regression-tests"))

import gate_definitions as gd  # noqa: E402
from verify_gates import verify_gates  # noqa: E402
import test_archive_replay as tar  # noqa: E402

PAIRS = tar._pair_candidates()


def collect(tag):
    out = {}
    for pid, rpt, snap, prof in PAIRS:
        try:
            res = verify_gates(rpt.read_text(encoding="utf-8"),
                               json.loads(snap.read_text(encoding="utf-8")), prof)
            out[pid] = {d["gate"]: d["status"] for d in res["details"]
                        if d["status"] != "auto_pass"}
        except Exception as e:
            out[pid] = {"__error__": str(e)[:60]}
    print(f"  [{tag}] {len(out)} 对回放完成")
    return out


def diff(base, cur, tag):
    flips = []
    for pid in sorted(set(base) & set(cur)):
        for g in sorted(set(base[pid]) | set(cur[pid])):
            o, n = base[pid].get(g, "absent"), cur[pid].get(g, "absent")
            if o != n:
                flips.append(f"{pid} {g}: {o}→{n}")
    arrow = "→".join
    print(f"  [{tag}] 归档翻转 {len(flips)} 处" + (": " + "; ".join(flips[:8]) if flips else ""))
    return flips


BASE = collect("base")

# ============ P1: G63 tokenizer 第5类豁免——百分位变体 ============
_orig_epl = gd._extract_price_candidates


def _p1_extract(text):
    t = re.sub(r"\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*%", "", text)
    t = re.sub(r"\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*(?:百分位|分位)", " ", t)
    t = re.sub(r"[A-Za-z_][A-Za-z_0-9]*\s*[(（][^)）]*[)）]|[A-Za-z_][A-Za-z_0-9]*(?:\.\d+)?", " ", t)
    t = re.sub(r"(?<![\d.])(?:[1-9]|1[0-3])\s*/\s*13(?![\d.])", " ", t)
    t = re.sub(r"\d+\s*[日天]", " ", t)
    out = []
    for tok in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", t):
        n = float(tok.replace(",", ""))
        if n < 3 or 1990 <= n <= 2099:
            continue
        if n in (23.6, 38.2, 50.0, 61.8, 78.6):
            continue
        out.append(n)
    return out


print("\n== P1 G63 tokenizer 百分位豁免 ==")
print(f"  tokenizer 两极：第99百分位 原={_orig_epl('换手率处于第99百分位')} → 补={_p1_extract('换手率处于第99百分位')}")
gd._extract_price_candidates = _p1_extract
P1 = collect("P1")
p1_flips = diff(BASE, P1, "P1")
gd._extract_price_candidates = _orig_epl

# ============ P2a: G30#5 否定词表扩容 ============
print("\n== P2a G30#5 否定词表扩容（没有|难以|不再|放弃|拒绝|排除）==")
_orig_neg = gd._G30_NEG_RE
gd._G30_NEG_RE = re.compile(r"(不支持|不宜|不建议|不急于|暂不|勿|避免|无加仓|没有|难以|不再|放弃|拒绝|排除)")
P2a = collect("P2a")
p2a_flips = diff(BASE, P2a, "P2a")
gd._G30_NEG_RE = _orig_neg

# ============ P2b: G30#5 后置否定窗 ============
print("\n== P2b G30#5 后置否定（动词后 12 字符含否定词 → 同样跳过）==")
_orig_fa = gd._g30_first_action


def _p2b_first_action(scope):
    found = []
    for v in gd._G30_ACTION_VERBS:
        start = 0
        while True:
            i = scope.find(v, start)
            if i < 0:
                break
            found.append((i, v))
            start = i + 1
    for i, v in sorted(found):
        pre = scope[max(0, i - 12):i]
        post = scope[i + len(v):i + len(v) + 12]
        if gd._G30_NEG_RE.search(pre) or gd._G30_NEG_RE.search(post):
            continue
        return v
    return None


gd._g30_first_action = _p2b_first_action
P2b = collect("P2b")
p2b_flips = diff(BASE, P2b, "P2b")
gd._g30_first_action = _orig_fa

# ============ P5: G30#1 定增≡增发 同义词 ============
print("\n== P5 G30#1 fatal surface 同义词（定增≡增发）==")
_orig_arf = gd._g30_announcement_registry_findings


def _p5_arf(data, report):
    return _orig_arf(data, report.replace("定增", "增发"))


gd._g30_announcement_registry_findings = _p5_arf
P5 = collect("P5")
p5_flips = diff(BASE, P5, "P5")
gd._g30_announcement_registry_findings = _orig_arf

# ============ 单元级翻转演示 ============
print("\n== 单元级 FAIL→PASS 演示（归档对改造 + 最小构造）==")


def g63_of(rpt, snap, prof="profile_full"):
    res = verify_gates(rpt, snap, prof)
    d = next((x for x in res["details"] if x["gate"] == "G63"), None)
    return d["status"] if d else "absent"


# 找一个 G63 真值集在的归档对，注入「第99百分位」行
demo_pid = demo = None
for pid, rpt, snap, prof in PAIRS:
    snap_d = json.loads(snap.read_text(encoding="utf-8"))
    s4 = (snap_d.get("s4_technical") or {}).get("data") or {}
    fib = s4.get("fibonacci") or {}
    sr = s4.get("support_resistance") or {}
    if isinstance(fib, dict) and fib.get("levels") and prof == "profile_full":
        demo_pid, demo = pid, (rpt.read_text(encoding="utf-8"), snap_d, rpt)
        break
if demo:
    rpt_txt, snap_d, rpt_path = demo
    # 找一个真值做撞：levels 里的值 ±2% 即落 (0.5%,5%] 检测带
    lv = [v for v in snap_d["s4_technical"]["data"]["fibonacci"]["levels"].values()
          if isinstance(v, (int, float)) and v > 10]
    truth = lv[0] if lv else 94.78
    poison = truth * 1.03
    inject = rpt_txt.replace("## ", f"换手率处于第99百分位，支撑约 {poison:.2f} 附近\n\n## ", 1)
    if inject == rpt_txt:
        inject = rpt_txt + f"\n\n## 模块三 技术分析补充\n换手率处于第99百分位，支撑约 {poison:.2f} 附近"
    cur = g63_of(inject, snap_d)
    gd._extract_price_candidates = _p1_extract
    patched = g63_of(inject, snap_d)
    gd._extract_price_candidates = _orig_epl
    print(f"  P1 单元（{demo_pid.split(':')[0]} 注入 第99百分位+撞真值行）: G63 {cur} → {patched}")

# P5 最小构造：fatal event_type=增发，报告写 定增
snap_min = {"s5_events": {"data": {"risk_signals": {"processed": {
    "status": "ok",
    "timeline": {"status": "ok", "future": [], "active": [],
                 "fatal_events": [{"event_type": "增发", "level1_content": "增发新股"}]},
}}}}}
rpt_ok = "## 证据全景\n增发事项已在治理段落披露。"
rpt_syn = "## 证据全景\n定增事项已在治理段落披露。"
res_cur = verify_gates(rpt_syn, snap_min, "profile_full")
gd._g30_announcement_registry_findings = _p5_arf
res_p5 = verify_gates(rpt_syn, snap_min, "profile_full")
gd._g30_announcement_registry_findings = _orig_arf


def g30_of(res):
    d = next((x for x in res["details"] if x["gate"] == "G30"), None)
    return d["status"] if d else "absent"


print(f"  P5 单元（fatal 增发 × 报告写定增）: G30 {g30_of(res_cur)} → {g30_of(res_p5)}"
      f"（对照：报告写增发 = {g30_of(verify_gates(rpt_ok, snap_min, 'profile_full'))}）")

# ============ P4: G21 did-you-mean（data_contracts 建议，reason-only）============
print("\n== P4 G21 did-you-mean 设计验证（reason-only，verdict 恒 FAIL 不变）==")
from data_contracts import SCENES  # noqa: E402
scene_keys = sorted(SCENES) if isinstance(SCENES, dict) else []
print(f"  data_contracts.SCENES 可作建议源：{len(scene_keys)} scenes"
      f"（例 {scene_keys[:3]}…）；现 _explain_bad_path 只用 snapshot 兄弟键+PATH_ALIASES，"
      "scene 整体缺失/为空时无建议可给——原型将在建议串尾追加 registry difflib 近邻")
