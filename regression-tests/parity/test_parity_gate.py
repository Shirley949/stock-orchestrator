#!/usr/bin/env python3
"""P5 合一 parity gate（S6）：frozen 语料回放，双断言。

断言（每票）：
  A. 冻结时间下 process_snapshot(frozen_pureraw) 两次调用 byte-identical（确定性）
  B. == frozen golden（重构前后行为严格不变）
另附：socket 封禁下的纯度证明（process 内任何网络调用即抛错→FAIL）。

语料：corpus/{code}_pureraw.json.gz + {code}_processed_golden.json.gz
生成：在**原始代码**上 RUNNER_PARITY_DUMP=<dir> python3 runner.py A <code>。
时间冻结：datetime/date mock 到 raw.frozen_at——patch import 闭包内所有本项目模块
（按 sys.modules 扫描 __file__ 前缀发现，勿手工枚举模块清单）。

用法：python3 test_parity_gate.py [--quick]   # --quick 只跑首票
退出码：unittest（0=全绿）；语料缺失 print 提示后 exit 2
"""
import copy
import gzip
import json
import os
import socket
import sys
import unittest
from datetime import datetime as _real_datetime, date as _real_date
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROUTING_DIR = Path(os.path.expanduser(
    "~/.hermes/skills/stock-analysis/financial-data-routing"))
CORPUS = HERE / "corpus"
sys.path.insert(0, str(ROUTING_DIR))

STOCKS = ["000988", "002008", "300394"]  # 语料票清单；新增语料须同步此列表

_REPO_ROOTS = (str(ROUTING_DIR),
               str(ROUTING_DIR.parent / "stock-orchestrator" / "scripts" / "lib"))


def _make_frozen(iso: str):
    frozen_dt = _real_datetime.fromisoformat(iso)

    class _FrozenDatetime(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_dt.replace(tzinfo=tz) if tz else frozen_dt

        @classmethod
        def today(cls):
            return frozen_dt

    class _FrozenDate(_real_date):
        @classmethod
        def today(cls):
            return frozen_dt.date()

    return _FrozenDatetime, _FrozenDate


def _patch_project_datetime(frozen_cls, frozen_date_cls):
    """patch 已加载本项目模块中的 datetime/date 名（先 import runner 触发懒加载）。

    同时 patch datetime 模块本身的 datetime/date 类：函数内局部 `from datetime import
    datetime`（如 runner._build_timeline）从 sys.modules['datetime'] 取属性，仅 patch
    项目模块名覆盖不到——曾致 300394 的 2026-08-19 事件随真实日历翻转 future↔historical
    （回放时钟泄漏=定时炸弹，golden 生成后次日起必炸，2026-08-20 修）。
    """
    import datetime as _dtmod
    import runner  # noqa: F401
    patches = [
        mock.patch.object(_dtmod, "datetime", frozen_cls),
        mock.patch.object(_dtmod, "date", frozen_date_cls),
    ]
    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None)
        if not f or not any(str(f).startswith(r) for r in _REPO_ROOTS):
            continue
        if getattr(mod, "datetime", None) is _real_datetime:
            patches.append(mock.patch.object(mod, "datetime", frozen_cls))
        if getattr(mod, "date", None) is _real_date:
            patches.append(mock.patch.object(mod, "date", frozen_date_cls))
    return patches


class _BlockedSocket(socket.socket):
    def __init__(self, *a, **kw):
        raise AssertionError("parity 回放中发生网络调用（process 非纯——检查上提完整性）")


def _load(name):
    p = CORPUS / f"{name}.json.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _canon(obj):
    """与 _parity_dump 同构的序列化（default=str）——gate 比较在此保真度。"""
    return json.dumps(obj, ensure_ascii=False, default=str)


class ParityGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [c for c in STOCKS
                   if not (CORPUS / f"{c}_pureraw.json.gz").exists()
                   or not (CORPUS / f"{c}_processed_golden.json.gz").exists()]
        if missing:
            print(f"[parity] 语料缺失: {missing} → 先在原始代码上 "
                  f"RUNNER_PARITY_DUMP 冻结（见文件头说明）")
            sys.exit(2)

    def _run_stock(self, code):
        import runner
        raw = _load(f"{code}_pureraw")
        golden = _load(f"{code}_processed_golden")
        frozen_cls, frozen_date_cls = _make_frozen(raw["frozen_at"])
        patches = _patch_project_datetime(frozen_cls, frozen_date_cls)
        for p in patches:
            p.start()
        try:
            # 纯度证明：封 socket 后 process 必须成功（任何网络调用→AssertionError）。
            # ⚠️ process_snapshot 就地修改 raw["snapshot"]（与原 fetch_for_mode 同语义），
            # 同一 raw 复用两次会双重累积（如 _warnings）——每次调用必须深拷贝输入。
            with mock.patch.object(socket, "socket", _BlockedSocket), \
                 mock.patch.object(socket, "create_connection",
                                   side_effect=AssertionError("network")), \
                 mock.patch.object(socket, "getaddrinfo",
                                   side_effect=AssertionError("network")):
                out1 = runner.process_snapshot(copy.deepcopy(raw))
                out2 = runner.process_snapshot(copy.deepcopy(raw))
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(_canon(out1), _canon(out2),
                         f"{code}: 同输入两次回放不一致（非确定性）")
        self.assertEqual(_canon(out1), _canon(golden),
                         f"{code}: 回放 != golden（行为漂移）。有意变更？"
                         f"跑 parity/refresh_golden.py --diff-scope "
                         f"--expect-prefix '<变更面>' 证明后 --refresh 刷新")
        print(f"[parity] ✅ {code}: determinism + golden byte-parity "
              f"({len(_canon(out1))} bytes, frozen_at={raw['frozen_at']})")

    def test_parity_all_stocks(self):
        stocks = STOCKS[:1] if "--quick" in sys.argv else STOCKS
        for code in stocks:
            with self.subTest(stock=code):
                self._run_stock(code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
