#!/usr/bin/env python3
"""refresh_golden —— parity golden 外科刷新一体工具（零代码参数，自动遍历 corpus 全部票）。

固化 CLAUDE.md「测试基线固化行为，不固化正确性」硬规则的标准动作：
有意行为变更撞 parity FAIL 时 → diff-scope 证明 → 离线外科刷新 golden → 全量回归。

子命令（二选一）：
  --diff-scope [--expect-prefix $<路径>]...
      逐路径深比 golden vs **当前代码**回放（冻结时钟 + 封 socket + both_nan 短路防假阳性）。
      带 --expect-prefix：强制全部差异 ⊆ 前缀白名单，越界 exit 1（= diff-scope 证明 PASS/FAIL）；
      不带：仅打印差异（调查模式）。
  --refresh
      golden == process_snapshot(frozen pureraw)，离线回放重算写回 *.gz（不联网、不重新 fetch），
      写回后立即回读自验 byte-parity。**必须先过 --diff-scope 证明再刷新**，工具不做联锁。

用法示例：
  python3 refresh_golden.py --diff-scope --expect-prefix '$.s10_checklist'
  python3 refresh_golden.py --refresh

退出码：0=动作完成且校验通过；1=差异越界 / 刷新后自验失败；2=语料缺失。
"""
import argparse
import copy
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from test_parity_gate import (  # noqa: E402  复用冻结时钟/socket 封禁/corpus 装载单一实现
    STOCKS, _BlockedSocket, _canon, _load, _make_frozen, _patch_project_datetime,
)


def is_nan(v):
    try:
        return isinstance(v, float) and v != v
    except Exception:
        return False


def deep_diff(a, b, path="$", out=None):
    """逐路径收集 golden(a) vs 回放(b) 差异；nan==nan 短路（balance_sheet NaN 字面量）。"""
    if out is None:
        out = []
    if is_nan(a) and is_nan(b):
        return out
    if type(a) != type(b):
        out.append((path, "TYPE", f"{type(a).__name__}={a!r}", f"{type(b).__name__}={b!r}"))
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append((f"{path}.{k}", "ADDED", "-", b[k]))
            elif k not in b:
                out.append((f"{path}.{k}", "REMOVED", a[k], "-"))
            else:
                deep_diff(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append((path, "LEN", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            deep_diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append((path, "VALUE", a, b))
    return out


def replay(code):
    """冻结时钟 + 封 socket 下回放当前代码；返回 (process_snapshot 输出, 冻结输入)。"""
    import runner
    raw = _load(f"{code}_pureraw")
    frozen_cls, frozen_date_cls = _make_frozen(raw["frozen_at"])
    patches = _patch_project_datetime(frozen_cls, frozen_date_cls)
    for p in patches:
        p.start()
    try:
        import socket as _socket_mod
        with _patch_ctx(_socket_mod):
            out = runner.process_snapshot(copy.deepcopy(raw))
    finally:
        for p in patches:
            p.stop()
    return out, raw


class _patch_ctx:
    """封 socket 纯度上下文（与 test_parity_gate 同语义：process 内任何网络调用即炸）。"""

    def __init__(self, socket_mod):
        self._m = socket_mod

    def __enter__(self):
        from unittest import mock
        self._p1 = mock.patch.object(self._m, "socket", _BlockedSocket)
        self._p2 = mock.patch.object(self._m, "create_connection",
                                     side_effect=AssertionError("network"))
        self._p3 = mock.patch.object(self._m, "getaddrinfo",
                                     side_effect=AssertionError("network"))
        for p in (self._p1, self._p2, self._p3):
            p.start()

    def __exit__(self, *exc):
        for p in (self._p1, self._p2, self._p3):
            p.stop()


def cmd_diff_scope(expect_prefixes):
    any_outside = False
    for code in STOCKS:
        golden = _load(f"{code}_processed_golden")
        out, _raw = replay(code)
        diffs = deep_diff(golden, out)
        outside = [d for d in diffs
                   if expect_prefixes and not any(d[0].startswith(p) for p in expect_prefixes)]
        flag = ""
        if expect_prefixes and outside:
            any_outside = True
            flag = f"  ❌ {len(outside)} 条越界"
        print(f"=== {code}: diff 路径数={len(diffs)}{flag}")
        show = diffs if not expect_prefixes else diffs[:8] + outside[:4]
        seen = set()
        for pth, kind, g, n in show:
            if (pth, kind) in seen:
                continue
            seen.add((pth, kind))
            print(f"  {kind:8s} {pth}: golden={g!r} -> new={n!r}")
        if len(show) < len(diffs):
            print(f"  ...（其余 {len(diffs) - len(seen)} 条同类省略，全量见上方计数）")
    if any_outside:
        print("\n❌ 存在越出预期前缀的差异——行为变更面超出预期，禁止刷新 golden")
        return 1
    if expect_prefixes:
        print("\n✅ diff-scope 证明通过：全部差异落于预期变更面前缀内")
    return 0


def cmd_refresh():
    for code in STOCKS:
        out, _raw = replay(code)
        gp = HERE / "corpus" / f"{code}_processed_golden.json.gz"
        tmp = Path(str(gp) + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, default=str)
        tmp.replace(gp)
        # 写回自验：回读并 byte-parity 比对本次回放输出
        with gzip.open(gp, "rt", encoding="utf-8") as fh:
            reloaded = json.load(fh)
        assert _canon(reloaded) == _canon(out), f"{code}: 刷新后回读不自洽"
        print(f"refreshed+verified {gp.name} ({gp.stat().st_size} bytes)")
    print("\n✅ golden 已离线刷新；下一步必跑全量回归 run_regression.sh")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--diff-scope", action="store_true",
                   help="逐路径深比 golden vs 当前代码回放")
    g.add_argument("--refresh", action="store_true",
                   help="离线回放重算写回 golden（先过 diff-scope 证明）")
    ap.add_argument("--expect-prefix", action="append", default=[],
                    metavar="$<路径>", help="差异白名单前缀（可重复）；仅配合 --diff-scope")
    args = ap.parse_args()

    missing = [c for c in STOCKS
               if not (HERE / "corpus" / f"{c}_pureraw.json.gz").exists()
               or not (HERE / "corpus" / f"{c}_processed_golden.json.gz").exists()]
    if missing:
        print(f"[parity] 语料缺失: {missing}")
        return 2
    return cmd_diff_scope(set(args.expect_prefix)) if args.diff_scope else cmd_refresh()


if __name__ == "__main__":
    sys.exit(main())
