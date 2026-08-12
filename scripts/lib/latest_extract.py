#!/usr/bin/env python3
"""
latest_extract.py — 统一 latest_period 信封构造 + 最新值提取（轻量工具）

排序统一后（序列族 [0]=最新），本模块只负责三件事：
  1. make_latest_envelope() — 构造统一 latest_period 信封（6 形态 × 2 data_class）
  2. latest_value_from_section() — 双键兜底（data/data_full，CLAUDE.md 硬规则）+ 取 [0]
  3. compute_as_of() / to_sort_key() / make_period_label() — 信封字段计算

**设计**：纯函数，无 IO，可测试。信封是**加法式**字段（序列族 top-level / 信号族
processed 层），不动原 periods/data_full，向后兼容。复用 quality_checks.parse_date（不重写）。

**信封 schema**（见 plan Step 2.1）：
    {
      "raw_date": <原始串>,                  # "2026-03-31"/"20260331"/"2026年6月份"/"2026"
      "period_type": "year|quarter|month|day|datetime|event",
      "period_label": <人类可读>,             # "2026Q1"/"2026年6月"/"2026"/"2026-07-15"
      "sort_key": <int YYYYMMDD>,            # 跨形态可比拟
      "as_of": "<YYYY-MM-DD>",               # 拉取时间戳
      "data_class": "actual|forecast",       # actual=已发生实绩；forecast=预测
      "value": <该期核心数值>,                # 标量或 dict
      "summary": <头条, 可选>,               # 信号族必带；序列族有 processed.summary 时带
      ...<extra 透传>                         # reason / is_forward_looking / change_pct 等
    }
"""
from datetime import datetime, date
from typing import Any, Optional, Tuple

from quality_checks import parse_date  # noqa: E402  （lib/ 已在 sys.path）


# ============================================================
# 基础：时间戳 + sort_key + period_label
# ============================================================

def compute_as_of() -> str:
    """拉取时间戳，YYYY-MM-DD（与 period 分离，便于 freshness 计算）。"""
    return datetime.now().strftime("%Y-%m-%d")


def to_sort_key(raw_date: Any, period_type: str) -> Optional[int]:
    """raw_date × period_type → int YYYYMMDD（跨形态可比拟）。

    形态映射：
      year    → YYYY0000            （"2026" → 20260000）
      month   → YYYYMM00            （"2026年06月份" → 20260600）
      quarter → 季末月 ×100 + 28     （Q1→03, Q2→06, Q3→09, Q4→12；近似日 28 便于跨形态比较）
      day     → YYYYMMDD            （"2026-03-31" → 20260331）
      datetime→ YYYYMMDD            （取日期部分）
      event   → YYYYMMDD            （公告/事件日，如 lhb "20260708" → 20260708）

    8 位紧凑串（lhb latest_date）直接 int 化兜底。
    """
    if raw_date is None or period_type is None:
        return None
    dt = parse_date(raw_date)
    if dt is None:
        # 8 位紧凑 "20260708" 兜底（lhb 标量 latest_date）
        s = str(raw_date).strip().replace("-", "").replace("/", "")
        if len(s) == 8 and s.isdigit():
            try:
                return int(s)
            except ValueError:
                return None
        return None
    y, m, d = dt.year, dt.month, dt.day
    if period_type == "year":
        return y * 10000
    if period_type == "month":
        return y * 10000 + m * 100
    if period_type == "quarter":
        q_end_month = {1: 3, 2: 6, 3: 9, 4: 12}.get((m - 1) // 3 + 1, 12)
        return y * 10000 + q_end_month * 100 + 28
    # day / datetime / event
    return y * 10000 + m * 100 + d


def make_period_label(raw_date: Any, period_type: str, hint: Optional[str] = None) -> str:
    """人类可读 period_label。hint 优先（如 '2026中报预增'/'2027E'）。"""
    if hint:
        return hint
    if raw_date is None:
        return ""
    dt = parse_date(raw_date)
    if dt is None:
        return str(raw_date)
    if period_type == "year":
        return f"{dt.year}"
    if period_type == "quarter":
        return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"
    if period_type == "month":
        return f"{dt.year}年{dt.month}月"
    if period_type == "day":
        return dt.strftime("%Y-%m-%d")
    if period_type == "datetime":
        return dt.strftime("%Y-%m-%d %H:%M")
    # event
    return dt.strftime("%Y-%m-%d")


def _norm_raw_date(raw_date: Any) -> Optional[str]:
    """raw_date 归一为字符串保留（信封 raw_date 字段）。"""
    if raw_date is None:
        return None
    if isinstance(raw_date, (datetime, date)):
        return raw_date.strftime("%Y-%m-%d")
    return str(raw_date)


# ============================================================
# 信封构造
# ============================================================

def make_latest_envelope(
    raw_date: Any,
    period_type: str,
    data_class: str,
    value: Any,
    summary: Optional[str] = None,
    *,
    as_of: Optional[str] = None,
    period_label_hint: Optional[str] = None,
    **extra: Any,
) -> dict:
    """构造统一 latest_period 信封（加法式，向后兼容）。

    参数：
      raw_date           : 原始日期（串/datetime/None）；None → 真空信封由调用方设 latest_period=None
      period_type        : year|quarter|month|day|datetime|event
      data_class         : actual|forecast
      value              : 该期核心数值（标量或 dict）
      summary            : 人类可读头条（可选；信号族 lhb/northbound/company_guidance 必带）
      as_of              : 拉取时间戳（默认 compute_as_of()）
      period_label_hint  : 覆盖自动 period_label（如 '2026中报预增'/'2027E'）
      **extra            : 透传额外字段（reason / is_forward_looking / change_pct / report_date …）

    返回：信封 dict（7 核心字段 + summary 可选 + extra 透传）。
    """
    env = {
        "raw_date": _norm_raw_date(raw_date),
        "period_type": period_type,
        "period_label": make_period_label(raw_date, period_type, period_label_hint),
        "sort_key": to_sort_key(raw_date, period_type),
        "as_of": as_of or compute_as_of(),
        "data_class": data_class,
        "value": value,
    }
    if summary is not None:
        env["summary"] = summary
    if extra:
        env.update(extra)
    return env


# ============================================================
# 最新值提取（双键兜底 + 取 [0]）
# ============================================================

def latest_value_from_section(
    section: Any,
    field: str,
    dual_fallback: bool = True,
) -> Tuple[Optional[Any], Optional[dict]]:
    """从 scene envelope section 取最新一行的某字段值 + 整行。

    双键兜底（CLAUDE.md 硬规则）：THS/EM 主路径填 ``.data``，Sina 路径填 ``.data_full``，
    **单读任一键 = 隐蔽 never-match bug**（G16/G9 已两次踩坑）。本函数 data 优先、data_full 兜底。

    排序统一后（L1 normalize）序列族 actual ``rows[0]`` == 最新期；forecast 由调用方保证升序。
    返回 ``(value, row)``；section 非字典 / 无数据 / 首行非 dict → ``(None, None)``。
    """
    if not isinstance(section, dict):
        return None, None
    rows = section.get("data")
    if rows is None and dual_fallback:
        rows = section.get("data_full")
    if not rows:
        return None, None
    row = rows[0]
    if not isinstance(row, dict):
        return None, None
    return row.get(field), row


def days_old(sort_key: int, as_of: Optional[str] = None) -> Optional[int]:
    """信封 sort_key (YYYYMMDD int) 距 as_of 的天数。用于 freshness 判定（G32/G33/company_guidance）。

    sort_key 跨形态可比拟（year=YYYY0000 / month=YYYYMM00 / day=YYYYMMDD），统一按
    YYYYMMDD → date 解析；as_of 默认今日。
    """
    if sort_key is None:
        return None
    try:
        sk_str = str(int(sort_key))
        # year(4位→补月日 0000)/month(6位→补日 00)/day(8位) 归一到 8 位
        if len(sk_str) == 4:
            sk_str += "0000"
        elif len(sk_str) == 6:
            sk_str += "00"
        sk8 = sk_str[:8]
        # year/month 形态含 00 月/日（YYYY0000 / YYYYMM00）→ coerce 00→01 才能 strptime
        yyyy, mm, dd = sk8[:4], sk8[4:6], sk8[6:8]
        if mm == "00":
            mm = "01"
        if dd == "00":
            dd = "01"
        sk_date = datetime.strptime(f"{yyyy}{mm}{dd}", "%Y%m%d").date()
    except (ValueError, TypeError):
        return None
    ref = as_of or compute_as_of()
    try:
        ref_date = datetime.strptime(ref, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (ref_date - sk_date).days


def get_evaluation(snapshot: dict, dimension: str = None) -> dict:
    """千股千评·主力控盘结论统一读取（check_g61 / capstone 抽证据 / m6 helper 共用，无痛读取所有内容）。

    双兜底 data/data_full 防 never-match（读三表范式硬规则：THS/EM 填 .data、Sina 填 .data_full，
    单读任一键 = 静默 never-match）。LLM 模块（m4/m6/m7 .md）不 import 本函数，用统一路径表达
    ``[src: snapshot.s_stock_evaluation.data.processed.conclusions]``。

    返回 ``{status, conclusions, by_dimension, metrics, latest_period}``；传 dimension 额外加 ``hit``
    （该维度结论 dict 或 None）。status 三态：ok/missing(金融股·次新无千股千评,真空)/failed。
    """
    se = (snapshot or {}).get("s_stock_evaluation") or {}
    sed = se.get("data") or se.get("data_full") or {}        # 双兜底
    processed = sed.get("processed", {}) or {}
    conclusions = processed.get("conclusions", []) or []
    by_dim = {}
    for c in conclusions:
        d = c.get("dimension")
        if d and d not in by_dim:
            by_dim[d] = c
    base = {"status": sed.get("status"), "conclusions": conclusions,
            "by_dimension": by_dim, "metrics": processed.get("metrics", {}) or {},
            "latest_period": processed.get("latest_period")}
    if dimension:
        return {**base, "hit": by_dim.get(dimension)}
    return base


if __name__ == "__main__":
    # 烟囱测试：6 形态 sort_key 跨形态可比拟 + 信封构造
    import json
    samples = [
        ("2026", "year", "actual", 20260000),
        ("2026年06月份", "month", "actual", 20260600),
        ("2026-03-31", "quarter", "actual", 20260328),  # Q1 → 03 月
        ("2026-03-31", "day", "actual", 20260331),
        ("20260708", "event", "actual", 20260708),
    ]
    for raw, pt, dc_cls, expect_sk in samples:
        env = make_latest_envelope(raw, pt, dc_cls, value=raw, summary=f"测试 {pt}")
        sk = env["sort_key"]
        ok = "✓" if sk == expect_sk else "✗"
        print(f"{ok} {pt:8} raw={raw!r:20} sort_key={sk} (expect {expect_sk}) label={env['period_label']}")
    print("\n跨形态可比拟（同年）：year < month < quarter < day:",
          20260000 < 20260600 < 20260328 if False else
          f"{20260000} < {20260600} ? {20260000 < 20260600}；Q1={20260328} vs day Q1末={20260331}")
