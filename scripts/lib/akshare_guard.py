#!/usr/bin/env python3
"""
akshare_guard.py — Monkey-patch akshare 模块，强制所有调用经过质量检查。

激活后，进程中所有 `import akshare as ak; ak.xxx()` 调用都会被拦截，
优先路由到 DataSnapshot（缓存 + 完整质量检查），
失败则直接调用原始函数 + 施加基础质量检查。

递归保护:
  DataSnapshot._call_akshare() 内部使用 _get_real_ak()
  获取原始模块，避免 guard → ds → ak → guard 死循环。

用法:
    import akshare_guard
    akshare_guard.activate(stock_code="600519")
    try:
        import akshare as ak
        df = ak.stock_zh_a_gdhs_detail_em(symbol="600519")
    finally:
        log = akshare_guard.get_audit_log()
        akshare_guard.deactivate()
"""
import functools
import sys
import threading
import types
from datetime import datetime
from typing import Any, Optional, List, Dict
import pandas as pd

from quality_checks import (
    find_date_column, detect_ordering, compute_staleness,
)

# ============================================================
# 全局状态
# ============================================================

_ORIGINAL_AKSHARE = None
_ACTIVE_GUARD: Optional['AkshareGuard'] = None
_recursion_guard = threading.local()


def is_active() -> bool:
    return _ACTIVE_GUARD is not None and _ACTIVE_GUARD._active


def activate(stock_code: Optional[str] = None):
    """激活全局拦截。幂等。"""
    global _ACTIVE_GUARD, _ORIGINAL_AKSHARE
    if _ACTIVE_GUARD is not None:
        _ACTIVE_GUARD.deactivate()
    guard = AkshareGuard()
    guard.activate(stock_code)
    _ACTIVE_GUARD = guard
    _ORIGINAL_AKSHARE = guard._original_ak


def deactivate():
    """停用全局拦截。"""
    global _ACTIVE_GUARD, _ORIGINAL_AKSHARE
    if _ACTIVE_GUARD is not None:
        _ACTIVE_GUARD.deactivate()
        _ACTIVE_GUARD = None
    _ORIGINAL_AKSHARE = None


def set_ds(ds):
    """将外部 DataSnapshot 注入 guard，实现缓存共享。"""
    global _ACTIVE_GUARD
    if _ACTIVE_GUARD is not None:
        _ACTIVE_GUARD._ds = ds


def get_audit_log() -> List[Dict]:
    if _ACTIVE_GUARD is None:
        return []
    return _ACTIVE_GUARD.get_audit_log()


def get_unprotected_calls() -> List[Dict]:
    if _ACTIVE_GUARD is None:
        return []
    return _ACTIVE_GUARD.get_unprotected_calls()


def _get_real_ak():
    """获取真实 akshare 模块，绕过 proxy。供 DataSnapshot._call_akshare() 使用。"""
    if _ORIGINAL_AKSHARE is not None:
        return _ORIGINAL_AKSHARE
    import akshare
    return akshare


# ============================================================
# AkshareGuard
# ============================================================

class AkshareGuard:
    def __init__(self):
        self._original_ak = None
        self._active = False
        self._ds = None
        self._audit_log: List[Dict] = []
        self._lock = threading.Lock()

    def activate(self, stock_code: Optional[str] = None):
        if self._active:
            self.deactivate()
        import akshare as ak
        self._original_ak = ak
        self._active = True
        self._audit_log = []
        if stock_code:
            try:
                from data_snapshot import DataSnapshot
                self._ds = DataSnapshot(stock_code)
            except ImportError:
                pass
        sys.modules['akshare'] = AkshareProxy(self)

    def deactivate(self):
        if self._original_ak is not None:
            sys.modules['akshare'] = self._original_ak
        self._active = False
        self._ds = None

    def get_audit_log(self) -> List[Dict]:
        with self._lock:
            return list(self._audit_log)

    def get_unprotected_calls(self) -> List[Dict]:
        with self._lock:
            return [log for log in self._audit_log if log.get("route") != "datasnapshot"]

    def _log_call(self, api_name, route, rows=0, ordering="unknown",
                  stale=False, warning=None, error=None):
        with self._lock:
            self._audit_log.append({
                "api": api_name, "route": route, "rows": rows,
                "ordering": ordering, "stale": stale,
                "warning": warning, "error": error,
                "timestamp": datetime.now().isoformat(),
            })


# ============================================================
# AkshareProxy
# ============================================================

class AkshareProxy(types.ModuleType):
    def __init__(self, guard: AkshareGuard):
        super().__init__('akshare')
        self._guard = guard

    def __getattr__(self, name: str):
        if name.startswith('_') and name not in ('__version__', '__doc__', '__all__'):
            raise AttributeError(name)
        original_ak = self._guard._original_ak
        original_func = getattr(original_ak, name, None)
        if original_func is None or not callable(original_func):
            return original_func

        guard = self._guard
        @functools.wraps(original_func)
        def wrapped(*args, **kwargs):
            return _guarded_call(guard, name, original_func, args, kwargs)
        return wrapped

    @property
    def __version__(self):
        return self._guard._original_ak.__version__

    @property
    def __doc__(self):
        return self._guard._original_ak.__doc__

    @property
    def __all__(self):
        return getattr(self._guard._original_ak, '__all__', None)


# ============================================================
# _guarded_call
# ============================================================

def _guarded_call(guard, api_name, original_func, args, kwargs):
    """拦截 ak.xxx() 调用，优先路由到 DataSnapshot。"""
    ds = guard._ds

    # 策略 1: DataSnapshot
    if ds is not None:
        try:
            params = dict(kwargs)
            if args and isinstance(args[0], str):
                params.setdefault("symbol", args[0])
            result = ds.fetch_or_cache(api_name, params)
            if result["status"] in ("ok", "cached"):
                df = pd.DataFrame(result.get("data_full", []))
                # ★ 确保 newest_first：head() 应显示最新数据
                if result.get("_ordering") == "oldest_first" and len(df) > 0:
                    df = df.iloc[::-1].reset_index(drop=True)
                guard._log_call(api_name, "datasnapshot", len(df),
                                ordering=result.get("_ordering", "unknown"),
                                stale=result.get("_stale", False))
                return df
        except Exception:
            pass

    # 策略 2: 直接调用 + 基础质量检查
    result_raw = original_func(*args, **kwargs)
    if isinstance(result_raw, pd.DataFrame) and len(result_raw) > 0:
        date_col = find_date_column(result_raw)
        ordering = "unknown"
        stale = False
        warning = None
        if date_col:
            ordering = detect_ordering(result_raw, date_col)
            # ★ 自动翻转：确保 DataFrame 为 newest_first
            if ordering == "oldest_first":
                result_raw = result_raw.iloc[::-1].reset_index(drop=True)
                warning = (f"{api_name} 已自动翻转为 newest_first, "
                          f"date_col='{date_col}'")
            data_full = result_raw.to_dict(orient="records")
            days_old, latest = compute_staleness(api_name, data_full, date_col)
            if days_old is not None and latest is not None:
                threshold = 60 if api_name.startswith("macro_") else (
                    120 if "financial" in api_name else 90)
                stale = days_old > threshold
                if stale:
                    warning = (f"{api_name} 数据陈旧: "
                              f"最新 {latest.date()}, 已 {days_old}d")
        guard._log_call(api_name, "direct", len(result_raw),
                        ordering=ordering, stale=stale, warning=warning)
        return result_raw
    else:
        guard._log_call(api_name, "passthrough", 0)
        return result_raw
