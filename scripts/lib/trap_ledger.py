#!/usr/bin/env python3
"""trap_ledger — 陷阱台账单一实现（E10；两消费方 scanner/checklist 共用）。

ledger 落 references/trap_ledger.yaml，schema：
  signature: gate#subcheck:reason_class   ← 唯一键
  gate / subcheck / reason_class / fix    ← 定位与修法
  match:  正则（对该 gate 的 FAIL reasons 拼接串；空=gate 级兜底）
  count:  基线计数（--strict 增量拦截的参照；= 冻结时线上语料实测量）
  last_seen / status(landed|inflight|pending) / blocked(P3)

blocked(P3)：运营态开关——某 trap 复发/回退到「未修复不能再开新票」时置 true，
generate_checklist 见 blocked 非空 exit 2 硬阻断（--ignore-trap-ledger 逃生）。
"""
from pathlib import Path

import yaml

_LEDGER_PATH = Path(__file__).resolve().parent.parent.parent / "references" / "trap_ledger.yaml"


def load_ledger(path=None) -> list:
    """读 ledger（默认 repo references/trap_ledger.yaml）→ list[dict]；未建文件返 []。"""
    p = Path(path) if path else _LEDGER_PATH
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    entries = data.get("entries") if isinstance(data, dict) else data
    return [e for e in (entries or []) if isinstance(e, dict) and e.get("signature")]


def blocked_gates(path=None) -> list:
    """blocked(P3)=true 的条目（generate_checklist 硬阻断依据）。"""
    return [e for e in load_ledger(path) if e.get("blocked")]


def engine_pending(path=None) -> list:
    """root_cause=engine 且 status≠landed 的条目（晋级欠账指标：inflight=已立项未落地 + 未修存量，每轮回归可见）。"""
    return [e for e in load_ledger(path)
            if e.get("root_cause") == "engine" and e.get("status") != "landed"]
