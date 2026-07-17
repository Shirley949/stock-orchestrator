#!/usr/bin/env python3
"""
quality_checks.py — 通用数据质量检查函数

同时被 DataSnapshot (Part A) 和 AkshareGuard (Part B Layer 1) 使用。
不依赖 DataSnapshot 或 AkshareGuard 的任何类。
"""
from datetime import datetime
from typing import Optional, Tuple, List
import pandas as pd

# ============================================================
# 日期字段自动发现
# ============================================================

_DATE_FIELDS = [
    # 通用
    "日期", "报告日", "时间", "date", "Date",
    "交易日", "报告期", "截止日", "公布日期",
    # 股东户数
    "股东户数统计截止日", "股东户数公告日期",
    # 公告/事件
    "公告日期", "业绩披露日期", "预案公告日",
    # 宏观
    "月份", "TRADE_DATE",
    # 分红
    "分红年度",
]

_DATE_KEYWORDS = [
    "日期", "date", "Date", "时间", "月份", "报告",
    "统计", "截止", "公布", "公告", "披露", "交易日",
]

_DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y年%m月%d日",
    "%Y年%m月份",               # 宏观月份格式 (macro_china_pmi et al.)
    "%Y-%m",                     # 月份简写
    "%Y-%m-%d %H:%M:%S",        # 分钟K线时间戳
    "%Y-%m-%d %H:%M",
]


def find_date_column(df: pd.DataFrame) -> Optional[str]:
    """在 DataFrame 中自动发现日期列。"""
    for col in df.columns:
        if str(col) in _DATE_FIELDS:
            return str(col)
    for col in df.columns:
        col_str = str(col)
        if any(kw in col_str for kw in _DATE_KEYWORDS):
            return col_str
    return None


def parse_date(val) -> Optional[datetime]:
    """稳健的日期解析。"""
    if val is None:
        return None
    if isinstance(val, (datetime, pd.Timestamp)):
        return val if isinstance(val, datetime) else val.to_pydatetime()
    val_str = str(val)[:19].strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            continue
    try:
        return pd.to_datetime(val_str).to_pydatetime()
    except Exception:
        return None


# ============================================================
# 排序方向自动检测
# ============================================================

def detect_ordering(df: pd.DataFrame, date_col: str) -> str:
    """自动检测 DataFrame 的日期排序方向。"""
    try:
        first_dates = df[date_col].head(5).apply(parse_date).dropna()
        last_dates = df[date_col].tail(5).apply(parse_date).dropna()
        if len(first_dates) == 0 or len(last_dates) == 0:
            return "unknown"
        if max(first_dates) < max(last_dates):
            return "oldest_first"
        elif max(first_dates) > max(last_dates):
            return "newest_first"
        return "unknown"
    except Exception:
        return "unknown"


def find_latest_date(data: list, date_col: str) -> Optional[datetime]:
    """从 data_full (list of dicts) 全量扫描找出最新日期。"""
    latest = None
    for row in data:
        if not isinstance(row, dict):
            continue
        val = row.get(date_col)
        if val is None:
            continue
        dt = parse_date(val)
        if dt and (latest is None or dt > latest):
            latest = dt
    return latest


# ============================================================
# 数据方向纠正
# ============================================================

def ensure_newest_first(df: pd.DataFrame, date_col: str) -> Tuple[pd.DataFrame, bool]:
    """确保 DataFrame 为 newest_first 排序。"""
    ordering = detect_ordering(df, date_col)
    if ordering == "oldest_first":
        return df.iloc[::-1].reset_index(drop=True), True
    return df, False


# ============================================================
# 陈旧度计算
# ============================================================

def compute_staleness(
    api_name: str,
    data: list,
    date_col: str,
) -> Tuple[Optional[int], Optional[datetime]]:
    """计算数据陈旧度 (days_old, latest_date)。"""
    latest = find_latest_date(data, date_col)
    if latest is None:
        return None, None
    days_old = (datetime.now() - latest).days
    return days_old, latest


def get_staleness_threshold(api_name: str) -> int:
    """返回陈旧告警阈值（天数）。用于 _check_staleness()。"""
    KLINE_APIS = {"stock_zh_a_daily", "stock_zh_a_hist", "curl_eastmoney_kline",
                  "stock_zh_a_hist_min_em"}
    DAILY_APIS = {"stock_comment_detail_zlkp_jgcyd_em"}
    # 龙虎榜历史榜单：距上次上榜天数本身就是信号（非热门=有效结论），不套新鲜度告警。
    if api_name in {"stock_lhb_stock_detail_date_em", "stock_lhb_stock_detail_em"}:
        return 10_000  # 永不告警（与 should_reject_cache 豁免一致）
    if api_name in KLINE_APIS or api_name in DAILY_APIS:
        return 5
    elif "financial" in api_name or api_name in {
        "stock_financial_report_sina", "stock_financial_abstract",
        "stock_financial_abstract_ths",
    }:
        return 120
    elif api_name in {
        "stock_zh_a_gdhs_detail_em",   # 季度数据（每季度公布一次）
        "stock_fhps_detail_em",        # 分红数据（不定期）
        "stock_yjyg_em",               # 业绩预告（不定期）
        "stock_shareholder_change_ths",# 增减持（不定期）
    }:
        return 120  # 季度/不定期数据，允许 120 天（4 个月）
    elif api_name.startswith("macro_"):
        return 60
    return 7


def should_reject_cache(api_name: str, days_old: int, row_count: int = 0) -> bool:
    """判断是否应拒绝缓存（两段式：保守拒绝 + 主动告警）。"""
    KLINE_APIS = {"stock_zh_a_daily", "stock_zh_a_hist", "curl_eastmoney_kline",
                  "stock_zh_a_hist_min_em"}
    if api_name in KLINE_APIS:
        return days_old > 30
    if ("financial" in api_name or api_name in {
        "stock_financial_report_sina", "stock_financial_abstract",
        "stock_financial_abstract_ths",
    }) and row_count < 4:
        return True
    # 龙虎榜历史榜单是参考数据（"最近何时上榜"本身就是信号），旧日期=非热门的有效结论，
    # 非脏缓存；freshness 由 fetch_lhb 的 90 天窗 + never_listed 语义控制。永不拒绝。
    if api_name in {"stock_lhb_stock_detail_date_em", "stock_lhb_stock_detail_em"}:
        return False
    # 所有其他 API：仅拒绝超过 365 天的，季度数据可能是最新的
    return days_old > 365
