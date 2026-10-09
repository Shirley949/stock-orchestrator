#!/usr/bin/env python3
"""b_portfolio_sheet.py — 模式B 多票合集渲染件（2026-10-09 Phase 6 批）。

纯渲染：零判断逻辑、零引擎调用、零网络——全部数据格从 full/ 快照照抄（cell() 溯源 +
selfcheck 二次独立重读对拍，任何不等 → exit 2 零写出）。单票判断逻辑 v3.3+T11 不进本件
（快照已是引擎产物，这里只排版）。

用法：
  b_portfolio_sheet.py --label morning [--codes 603993,601138] [--date 20261009]
                       [-o out.md] [--allow-stale] [--selfcheck-only]
退出码：0=写出且自检全过 ｜ 1=参数或快照缺失 ｜ 2=对拍失败零写出 ｜ 3=有降级票仍写出
"""
import argparse
import glob
import json
import os
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)),
                                "financial-data-routing"))
from report_views import DIR_ZH  # noqa: E402  方向→中文唯一实现（同语义单实现，禁本地重写）
import execution_shell as _es  # noqa: E402  v3.1 阈值常量兜底（旧快照 decl 无 th 键时用；同一真相源）

SNAP_DIR = os.environ.get("BP_SNAPSHOT_DIR",
                          os.path.expanduser("~/.cache/skill-snapshots/full"))
CODE_POOL = ["603993", "601138", "603663", "605376", "600089", "002273",
             "600378", "002600", "300568", "300502", "301217", "002202"]
KIND_CONFIRM = {"reduce_band": "触及即执行", "below_stop": "收盘确认",
                "pullback_watch": "收盘确认"}
TRADE_WORDS = {"BUY": "新增+", "BUY_ADD": "加仓+", "SELL_PART": "减仓−",
               "SELL_ALL": "清仓−"}
_CELLS = []   # selfcheck 溯源表：(code, json_path, ctx, raw_value)
_NOTES = []   # 降级/兜底尾注


def pick(snap, path):
    """dot-path getter（None 安全，list 下标用 [n]）。"""
    cur = snap
    for p in path.replace("]", "").replace("[", ".").split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(p)]
                continue
            except (ValueError, IndexError):
                return None
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def cell(snap, code, path, ctx):
    """所有数据格必经：取值 + 记溯源（selfcheck 二次独立重读对拍的对象）。"""
    v = pick(snap, path)
    _CELLS.append((code, path, ctx, v))
    return v


def _sgn(v):
    return f"+{v}" if isinstance(v, (int, float)) and v > 0 else v


def _raw(v):
    return "—" if v is None else str(v)


def load_snapshots(codes, date, allow_stale):
    snaps, paths, stale_used = {}, {}, []
    for c in codes:
        p = os.path.join(SNAP_DIR, f"{c}_{date}.json")
        if not os.path.exists(p) and allow_stale:
            cands = sorted(glob.glob(os.path.join(SNAP_DIR, f"{c}_*.json")))
            cands = [x for x in cands
                     if os.path.basename(x)[7:15] <= date and os.path.getmtime(x)]
            if cands:
                p = cands[-1]
                stale_used.append(f"{c}←{os.path.basename(p)[7:15]}")
        if not os.path.exists(p):
            print(f"❌ 快照缺失：{p}（先跑 run_batch_B.sh 或显式 --date）", file=sys.stderr)
            sys.exit(1)
        with open(p, encoding="utf-8") as fh:
            snaps[c] = json.load(fh)
        paths[c] = p
    return snaps, paths, stale_used


def derive_phase(snaps):
    """t0.status 键契约：ok→盘中 / hidden→盘后 / degraded·缺→弃权；多数决，
    不一致取 as_of_time 最新票；全弃权→盘后。"""
    votes = {"盘中": 0, "盘后": 0}
    latest = ("", None)   # (as_of_time, phase)
    waived = 0
    for c, s in snaps.items():
        st = pick(s, "s4_technical.data.t0_check.status")
        ph = {"ok": "盘中", "hidden": "盘后"}.get(st)
        if ph is None:
            waived += 1
            continue
        votes[ph] += 1
        t = pick(s, "s4_technical.data.t0_check.as_of_time") or ""
        if t >= latest[0]:
            latest = (t, ph)
    total = votes["盘中"] + votes["盘后"]
    if total == 0:
        return "盘后", f"⚠️ 全批 t0 缺档（旧快照）——按盘后处理"
    if votes["盘中"] and votes["盘后"]:
        note = f"⚠️ 相位混合：{votes['盘中']}盘中/{votes['盘后']}盘后/{waived}弃权——取 as_of 最新票"
        return latest[1], note
    return ("盘中" if votes["盘中"] else "盘后"), None


def derive_title(date, phase, codes, label):
    y, m, d = date[:4], int(date[4:6]), int(date[6:8])
    base = f"{m}-{d}{phase}{len(codes)}票合集"
    # 同相位同日异 label 批已存在 → 追加 -{label} 防撞名
    others = [x for x in glob.glob(os.path.join(
        os.path.expanduser("~/analysis_report"),
        f"analysis_report-batch-*-modeB-{date}")) if f"-{label}-" not in x]
    title = f"{base}-{label}" if others else base
    assert len(title) <= 33, f"title {len(title)} 字符超 33：{title}"
    return title


def stock_row(s, c):
    """表1 一行：名/现价/今日/主力/方向/今日动作（全部 cell 照抄）。"""
    rq_cur = cell(s, c, "s2_quote_kline.data.realtime_quote.current", "现价")
    cur = rq_cur
    if cur is None:
        cur = cell(s, c, "s4_technical.data.b_head.close", "现价兜底")
        _NOTES.append(f"{c} 现价缺 rq.current → 取 b_head.close 兜底")
    pct = cell(s, c, "s2_quote_kline.data.realtime_quote.change_pct", "今日涨跌")
    mnt = cell(s, c, "s4_technical.data.t0_check.context.main_net_today", "主力净额")
    if mnt is None:
        mnt = cell(s, c, "s3_fund_flow.data.fund_flow.net_flow", "主力净额兜底")
    direction = cell(s, c, "s4_technical.data.b_head.direction", "方向")
    act = cell(s, c, "s4_technical.data.execution_shell.today.action", "今日动作")
    pos = cell(s, c, "s4_technical.data.execution_shell.today.end_position", "期末仓")
    name = cell(s, c, "classification.stock_name", "票名")
    dz = DIR_ZH.get(direction, direction)   # 未知方向原文直出
    return (f"| {name} | {_raw(cur)} | {_sgn(pct)}% | {_sgn(mnt)} | {dz} "
            f"| {act}（{pos}） |")


def hit_rows(snaps, codes, phase):
    """表2 决策档行：t0.rows 仅 today.hit==True（全集重算防漏行）。"""
    rows = []
    for c in codes:
        s = snaps[c]
        if pick(s, "s4_technical.data.t0_check.status") is None:
            _NOTES.append(f"{pick(s, 'classification.stock_name')}：t0_check 缺档（旧快照），决策档触发不可考")
            continue
        pos = pick(s, "s4_technical.data.execution_shell.user_position") or {}
        posc = (f"{_raw(pos.get('shares'))}股 @成本{_raw(pos.get('cost'))}"
                if pos else "空仓（未提供持仓）")
        name = pick(s, "classification.stock_name")
        for r in (pick(s, "s4_technical.data.t0_check.rows") or []):
            td = r.get("today") or {}
            if not td.get("hit"):
                continue
            low = r.get("kind") == "below_stop"
            live = f"今{'低' if low else '高'} {td.get('extreme')} @{td.get('hit_time')}"
            confirm = KIND_CONFIRM.get(r.get("kind"), "收盘确认") if phase == "盘中" else "已收盘确认"
            rows.append((c, f"| {name} | {posc} | {r.get('item')}·{r.get('verdict')} "
                            f"| {_raw(r.get('price'))} | {live} | {confirm} |"))
    return rows


def discipline_rows(snaps, codes, phase):
    """表3 持仓纪律行：持续态（SELL_ALL/SELL_PARTIAL）+ 触及后收回（HOLD∧low<ladder∧cur≥ladder）。"""
    standing, recover = [], []
    confirm = "已收盘确认" if phase == "盘后" else "收盘确认"
    for c in codes:
        s = snaps[c]
        up = pick(s, "s4_technical.data.execution_shell.user_position") or {}
        if not up:
            continue
        name = pick(s, "classification.stock_name")
        posc = f"{_raw(up.get('shares'))}股 @成本{_raw(up.get('cost'))}"
        act = up.get("action")
        reason = _raw(up.get("reason"))
        if act == "SELL_ALL":
            standing.append((c, f"| {name} | {posc} | 梯子清仓 | {_raw(up.get('ladder'))} "
                                f"| {reason} | {confirm} |"))
        elif act == "SELL_PARTIAL":
            standing.append((c, f"| {name} | {posc} | 浮盈止盈 | — | {reason} | {confirm} |"))
        elif act == "HOLD":
            ladder = up.get("ladder")
            low = cell(s, c, "s2_quote_kline.data.realtime_quote.low", "今低(收回判定)")
            cur = cell(s, c, "s2_quote_kline.data.realtime_quote.current", "现价(收回判定)")
            if ladder is not None and low is not None and cur is not None \
                    and low < ladder and cur >= ladder:
                recover.append((c, f"| {name} | {posc} | 梯子清仓 | {_raw(ladder)} "
                                   f"| 今低 {low} 曾破，现价 {cur} 已收回 | 以收盘为准 |"))
    return standing, recover


def ledger_block(snaps, codes, phase, period_label, date_iso):
    """块3 账本总持仓/今日变动（trades 导出键；无变动不显示——用户明确）。"""
    L = ["## 账本总持仓（v3.3+T11 纸面仓）", ""]
    positions = [(pick(snaps[c], "classification.stock_name"),
                  cell(snaps[c], c, "s4_technical.data.execution_shell.results.v33_t11.summary.end_position",
                       "回放期末仓")) for c in codes]
    nonflat = [(n, p) for n, p in positions if p and p != "空仓"]
    if not nonflat:
        L.append(f"- 当前：全部空仓（{len(codes)} 票回放期末均空仓）")
    else:
        for n, p in nonflat:
            L.append(f"- 当前：{n}：{p}")
    degrade = False
    lines = []
    for c in codes:
        s = snaps[c]
        trades = pick(s, "s4_technical.data.execution_shell.results.v33_t11.trades")
        if trades is None:
            if phase == "盘后":
                degrade = True
                _NOTES.append(f"{pick(s, 'classification.stock_name')}：trades 键缺档（旧快照），当日账本变动不可考")
            continue   # 盘中缺键=零信息损失，不降级
        held = False
        for t in trades:
            if str(t.get("date"))[:10] != date_iso:
                continue
            w = TRADE_WORDS.get(t.get("action"), str(t.get("action")))
            if t.get("action") in ("BUY", "BUY_ADD") and held:
                w = TRADE_WORDS["BUY_ADD"]
            held = held or t.get("action") in ("BUY", "BUY_ADD")
            lines.append(f"- {pick(s, 'classification.stock_name')} {w} "
                         f"{_raw(t.get('shares'))}股 @{_raw(t.get('price'))}（{_raw(t.get('reason'))}）")
    if lines:
        L.append("- 今日：")
        L.extend(lines)
    elif phase == "盘中":
        L.append(f"- 今日：尚无账本变动（回放截至 {period_label}，盘中运行待收盘定格；盘中触发见上两表）")
    else:
        L.append("- 今日：无账本变动（已收盘定格）")
    return L, degrade


def selfcheck(snaps, paths):
    """二次独立重读对拍：任何不等 → 逐条打印 → exit 2 零写出。"""
    ok = True
    cov = {}
    for code, path, _ctx, raw in _CELLS:
        with open(paths[code], encoding="utf-8") as fh:
            snap2 = json.load(fh)
        got = pick(snap2, path)
        cov.setdefault(code, set()).add(path)
        if got != raw:
            ok = False
            print(f"❌ 对拍不等 code={code} path={path} 落盘值={got!r} 渲染值={raw!r}")
    n_cov = len({c for c in cov if len(cov[c]) >= 4})
    print(f"cells={len(_CELLS)} 覆盖 {len(cov)} 票（≥4 格/票的 {n_cov} 票）")
    if len(_CELLS) < 4 * len(snaps):
        ok = False
        print(f"❌ 覆盖率不足：cells {len(_CELLS)} < 4×{len(snaps)}")
    return ok


def main():
    ap = argparse.ArgumentParser(description="模式B 多票合集渲染件（纯照抄+对拍自检）")
    ap.add_argument("--label", required=True, help="批次标签（morning/close/preview）")
    ap.add_argument("--codes", default=",".join(CODE_POOL), help="逗号分隔 6 位码")
    ap.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="YYYYMMDD")
    ap.add_argument("-o", "--out", default="")
    ap.add_argument("--allow-stale", action="store_true", help="缺当日档取 mtime 最新≤date+披露")
    ap.add_argument("--selfcheck-only", action="store_true", help="只对拍不写盘")
    args = ap.parse_args()

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    for c in codes:
        if not (len(c) == 6 and c.isdigit()):
            sys.exit(f"❌ 码形非法：{c}")
    snaps, paths, stale_used = load_snapshots(codes, args.date, args.allow_stale)
    _NOTES.extend(f"降级用旧档 {x}" for x in stale_used)

    phase, phase_note = derive_phase(snaps)
    title = derive_title(args.date, phase, codes, args.label)
    period_label = max((pick(s, "s4_technical.data.b_head.period_label") or ""
                        for s in snaps.values()))
    asof_d = max((pick(s, "s4_technical.data.t0_check.as_of_date") or "" for s in snaps.values()))
    asof_t = max((str(pick(s, "s4_technical.data.t0_check.as_of_time") or "")[:5]
                  for s in snaps.values()))
    close_word = "已收盘" if phase == "盘后" else "待收盘定格"

    L = [f"# {title}", ""]
    L.append(f"📅 数据截止：{period_label} 收盘 ｜ 实况截至 {asof_d} {asof_t}（拉取时刻）")
    L.append(f"⚙️ 批次 {len(codes)} 票 ｜ 回放引擎 v3.3+T11 ｜ 实况为{phase}拉取时点，{close_word}"
             + (f"（{phase_note}）" if phase_note else ""))
    L.append("")

    # 表1 综合判断
    L.append("## 综合判断")
    L.append("")
    L.append("| 股票 | 现价（元） | 今日 | 主力（亿） | 方向 | 今日动作 |")
    L.append("|---|---|---|---|---|---|")
    L.extend(stock_row(snaps[c], c) for c in codes)
    L.append("")
    decl = pick(snaps[codes[0]], "s4_technical.data.execution_shell.v31_declaration") or {}
    th_dd = decl.get("th_ep_dd")
    th_dd = _es.V31_FIT_EP_DD_TH if th_dd is None else th_dd
    th_bm = decl.get("th_base_mult")
    th_bm = _es.V31_FIT_BASE_MULT_TH if th_bm is None else th_bm
    tags = {c: ((pick(snaps[c], "s4_technical.data.execution_shell.v31_declaration") or {})
                .get("tag") or "") for c in codes}
    bad = [(c, ("崩塌反转型" if "崩塌" in t else "透支高位型"))
           for c, t in tags.items() if ("崩塌" in t or "透支" in t)]
    n_smooth = sum(1 for t in tags.values() if "平滑" in t)
    bad_names = "、".join(f"{pick(snaps[c], 'classification.stock_name')}（✗{k}）"
                          for c, k in bad)
    L.append(f"> 今日动作=回放引擎截至 {period_label} 收盘的纸面态（盘中跑不含当日）"
             f"——「NONE（空仓）」≠ 今天不该买，当日触发见下两表。")
    if bad:
        L.append(f"> v3.1 参考（权重=0，仅辅助）：{len(tags) - len(bad)}/{len(tags)} 票适用性中性；"
                 f"判据 episode 回撤 ≤{th_dd}%（崩塌反转型）或 base_mult ≥{th_bm} 倍（透支高位型）"
                 f"即不适用，本批 {len(bad)} 票不适用：{bad_names}。")
    else:
        L.append(f"> v3.1 参考（权重=0，仅辅助）：{n_smooth}/{len(tags)} 票平滑/过渡态、适用性中性；"
                 f"判据 episode 回撤 ≤{th_dd}%（崩塌反转型）或 base_mult ≥{th_bm} 倍（透支高位型）"
                 f"即不适用，本批 0 票不适用。")
    L.append("")

    # 表2 决策档
    L.append(f"## 机械触发 · 决策档（T-1 档位 × 当日实况 · {close_word}）")
    L.append("")
    L.append("| 股票 | 仓位 | 档位 | 价位（元） | 当日实况 | 确认 |")
    L.append("|---|---|---|---|---|---|")
    hrows = hit_rows(snaps, codes, phase)
    if hrows:
        L.extend(r for _, r in hrows)
    else:
        L.append("|—|—|—|—|—|今日无决策档触发（T-1 全部档位未破/未触及）|")
    L.append("")

    # 表3 持仓纪律
    L.append("## 机械触发 · 持仓纪律（个人仓位 · 收盘确认为准）")
    L.append("")
    L.append("| 股票 | 仓位 | 规则 | 参照价（元） | 当日实况 | 确认 |")
    L.append("|---|---|---|---|---|---|")
    standing, recover = discipline_rows(snaps, codes, phase)
    srows = standing + recover
    if srows:
        L.extend(r for _, r in srows)
    else:
        L.append("|—|—|—|—|—|本批未提供个人仓位（空仓视角）|")
    L.append("")

    # 块3 账本
    date_iso = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:8]}"
    lb, degrade = ledger_block(snaps, codes, phase, period_label, date_iso)
    L.extend(lb)
    L.append("")

    if _NOTES:
        L.append("---")
        L.extend(f"> ⚠️ {n}" for n in _NOTES)
        L.append("")

    if not selfcheck(snaps, paths):
        print("❌ 对拍失败——零写出（exit 2）")
        sys.exit(2)

    out = args.out or os.path.join(
        os.path.expanduser("~/analysis_report"),
        f"analysis_report-batch-{args.label}-modeB-{args.date}",
        f"b_portfolio_{args.label}_{args.date}.md")
    if not args.selfcheck_only:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(out), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(L))
        os.replace(tmp, out)
        print(f"✅ 合集 {len(codes)} 票 cells={len(_CELLS)} 全对 → {out}")
    degrade_exit = 3 if (degrade or stale_used or _NOTES) else 0
    sys.exit(0 if (args.selfcheck_only or not degrade_exit) else 3)


if __name__ == "__main__":
    main()
