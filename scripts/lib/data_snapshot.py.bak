#!/usr/bin/env python3
"""
data_snapshot.py — 共享数据快照库（PR 1.5 of v3 execution discipline）

消除重复 API 调用，内置交叉验证。
所有 runner（financial-data-routing、order-intelligence）统一使用本库。

核心接口:
  ds = DataSnapshot("002130")
  result = ds.fetch_or_cache("stock_zh_a_hist", {"symbol": "002130", "period": "daily"})
  result = ds.fetch_with_fallback("stock_zh_a_spot_em", {}, fallbacks=[...])
  result = ds.fetch_curl("https://hq.sinajs.cn/list=sz002130", "实时行情")
  ds.save()

缓存路径: ~/.cache/skill-snapshots/{stock_code}_{YYYYMMDD}.json
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# ============================================================
# API 超时配置（来自 financial-data-routing/SKILL.md）
# ============================================================

TIMEOUT_MAP = {
    "stock_fund_flow_individual": 40,   # 极慢 12-35s
    "stock_individual_fund_flow": 30,   # 极慢 12-20s
    "stock_zh_a_hist": 25,              # 慢 8-12s
    "stock_financial_abstract": 20,     # 慢 6-10s
    "stock_zh_a_daily": 15,             # 中 3-6s
    "stock_financial_report_sina": 15,  # 中 3-5s
    "stock_zh_a_spot_em": 15,           # 中 3-5s
    "stock_news_em": 10,                # 快 1-2s
    "stock_zh_a_gdhs_detail_em": 10,    # 快 0.5-1s
    "stock_zh_a_hist_min_em": 10,       # 快 0.3-0.5s
    "stock_rank_forecast_cninfo": 15,   # 中 3-5s
    "stock_profit_forecast_ths": 15,    # 中 3-5s
    "stock_comment_detail_zlkp_jgcyd_em": 15,  # 中 3-5s
    "stock_zh_a_gdhs": 10,              # 快
    "stock_notice_report": 10,          # 快
    "macro_china_pmi": 10,              # 快
}

# ============================================================
# 数据源评级映射（来自 data-source-registry）
# ============================================================

SOURCE_GRADE = {
    # A 级 — 高质量，可直接使用
    "stock_zh_a_spot_em": "A",
    "stock_zh_a_daily": "A",
    "stock_zh_a_hist_min_em": "A",
    "stock_financial_report_sina": "A",
    "stock_financial_abstract": "A",
    "stock_news_em": "A",
    "stock_individual_fund_flow": "A",
    "stock_comment_detail_zlkp_jgcyd_em": "A",
    "stock_profit_forecast_ths": "A",
    # B 级 — 中性，需交叉验证
    "stock_zh_a_hist": "B",
    "stock_financial_abstract_ths": "B",
    "stock_rank_forecast_cninfo": "B",
    # C 级 — 低质量，仅辅助
    "web_search": "C",
    # D 级 — 已失效
    "stock_institute_recommend": "D",
}

# 降级源到首选源的映射（用于 cross_check）
PRIMARY_SOURCE_FOR = {
    "stock_zh_a_hist": "stock_zh_a_daily",
    "stock_financial_abstract_ths": "stock_financial_abstract",
    "stock_rank_forecast_cninfo": "stock_profit_forecast_ths",
}

# ============================================================
# 性能优化：已知全市场 API 列表（返回全量但分析只用1行）
# 拉取后自动 filter 到目标股票，避免内存飙升
# ============================================================
FULL_MARKET_APIS = {
    "stock_zh_a_spot_em": "代码",           # 实时行情，列名：代码
    "stock_fund_flow_individual": "股票代码", # 资金流向，列名：股票代码
    "stock_rank_forecast_cninfo": "证券代码", # 机构评级，列名：证券代码
    "bond_zh_cov": "正股代码",               # 可转债
    "stock_tfp_em": "代码",                 # 停复牌
}

# 已知全历史 API：自动截取最近 N 行（下游只需近期数据）
HISTORY_APIS = {
    "stock_financial_report_sina": 12,    # 最近 12 期（3年季度）
    "stock_financial_abstract": 12,       # 最近 12 期
    "stock_zh_a_daily": 750,              # 最近 750 个交易日（~3年）
    "stock_zh_a_hist": 750,               # 同上
    "macro_china_pmi": 12,                # 最近 12 期
}


class DataSnapshot:
    """
    共享数据快照：缓存 + 降级 + 交叉验证。

    同一 session 内，相同 (api_name, params) 只调用一次。
    每次 fetch 自动运行 3 项校验。
    """

    def __init__(self, stock_code: str):
        self.stock_code = stock_code
        self._today = datetime.now().strftime("%Y%m%d")
        self._cache_dir = Path(os.path.expanduser("~/.cache/skill-snapshots"))
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = self._cache_dir / f"{stock_code}_{self._today}.json"

        # 内存缓存: cache_key -> result_dict
        self._mem_cache: dict[str, dict] = {}
        # 累积告警
        self._warnings: list[str] = []
        # 已 fetch 记录（用于 summary）
        self._fetch_log: list[dict] = []

        # 从磁盘加载已有缓存
        self._load_disk_cache()

    # --------------------------------------------------------
    # 缓存键生成
    # --------------------------------------------------------

    @staticmethod
    def _cache_key(api_name: str, params: dict) -> str:
        """生成确定性缓存键: api_name + sorted(params) 的 MD5"""
        param_str = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
        raw = f"{api_name}|{param_str}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    # --------------------------------------------------------
    # 磁盘缓存 I/O
    # --------------------------------------------------------

    def _load_disk_cache(self):
        """从磁盘加载当日缓存"""
        if not self._cache_path.exists():
            return
        # 性能优化：缓存文件超过 10MB 则删除重建（可能是旧的全市场数据）
        try:
            file_size_mb = self._cache_path.stat().st_size / (1024 * 1024)
            if file_size_mb > 10:
                self._cache_path.unlink()
                self._warnings.append(f"[cache] 磁盘缓存 {file_size_mb:.1f}MB 超限，已删除重建")
                return
        except OSError:
            pass
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._mem_cache = data.get("entries", {})
            self._warnings = data.get("warnings", [])
            self._fetch_log = data.get("fetch_log", [])
        except (json.JSONDecodeError, OSError) as e:
            self._warnings.append(f"[cache] 加载磁盘缓存失败: {e}")

    def save(self):
        """持久化缓存到磁盘"""
        payload = {
            "stock_code": self.stock_code,
            "date": self._today,
            "updated_at": datetime.now().isoformat(),
            "entries": self._mem_cache,
            "warnings": self._warnings,
            "fetch_log": self._fetch_log,
        }
        try:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        except OSError as e:
            self._warnings.append(f"[cache] 写入磁盘缓存失败: {e}")

    # --------------------------------------------------------
    # 核心接口: fetch_or_cache
    # --------------------------------------------------------

    def fetch_or_cache(
        self,
        api_name: str,
        params: dict,
        cross_check: bool = False,
    ) -> dict:
        """
        拉取数据（带缓存 + 交叉验证）。

        1. 检查缓存（相同 api_name + sorted params）
        2. 未命中则调用 akshare API
        3. 运行 3 项校验
        4. 缓存结果
        5. 返回 result dict（含 _warnings）

        返回格式:
          {
            "status": "ok" | "failed" | "cached",
            "api_used": str,
            "params": dict,
            "rows": int,
            "columns": list,
            "data_preview": list,   # 前 5 行
            "data_full": list,      # 全量
            "fetch_time": str,
            "_warnings": list,
            "_grade": str,          # 数据源评级
            "_stale": bool,         # 数据是否陈旧
          }
        """
        key = self._cache_key(api_name, params)

        # 1. 缓存命中
        if key in self._mem_cache:
            cached = self._mem_cache[key].copy()
            cached["status"] = "cached"
            cached["_warnings"] = []
            return cached

        # 2. 调用 API
        result = self._call_akshare(api_name, params)

        # 3. 交叉验证
        if cross_check and result.get("status") == "ok":
            cross_warnings = self._run_cross_checks(api_name, params, result)
            result.setdefault("_warnings", []).extend(cross_warnings)
            self._warnings.extend(cross_warnings)
        else:
            # 仍然运行 staleness 和 encoding 检查（不需 cross_check 标志）
            auto_warnings = self._auto_validations(api_name, result)
            result.setdefault("_warnings", []).extend(auto_warnings)
            self._warnings.extend(auto_warnings)

        # 4. 缓存
        if result.get("status") == "ok":
            self._mem_cache[key] = result.copy()
            self._fetch_log.append({
                "api": api_name,
                "params": params,
                "status": "ok",
                "time": datetime.now().isoformat(),
            })
        else:
            self._fetch_log.append({
                "api": api_name,
                "params": params,
                "status": result.get("status", "unknown"),
                "error": result.get("error", ""),
                "time": datetime.now().isoformat(),
            })

        return result

    # --------------------------------------------------------
    # 核心接口: fetch_with_fallback
    # --------------------------------------------------------

    def fetch_with_fallback(
        self,
        api_name: str,
        params: dict,
        fallbacks: list = None,
        cross_check: bool = False,
    ) -> dict:
        """
        尝试 api_name，失败则依次尝试 fallbacks。
        fallbacks 格式: [(api_name, params), ...]
        返回第一个成功的结果。
        """
        apis_to_try = [(api_name, params)] + (fallbacks or [])

        for api, p in apis_to_try:
            result = self.fetch_or_cache(api, p, cross_check=cross_check)
            if result.get("status") in ("ok", "cached"):
                return result

        # 全部失败
        all_tried = [a for a, _ in apis_to_try]
        warn = f"[fallback] 全部失败: {all_tried}"
        self._warnings.append(warn)
        return {
            "status": "all_failed",
            "apis_tried": all_tried,
            "_warnings": [warn],
        }

    # --------------------------------------------------------
    # 核心接口: fetch_curl
    # --------------------------------------------------------

    def fetch_curl(self, url: str, label: str) -> dict:
        """
        Shell curl 降级（用于 sina hq.sinajs.cn 等不走 AkShare 的源）。
        自动运行 UTF-8 编码校验。
        """
        cache_key = self._cache_key(f"curl_{label}", {"url": url})

        if cache_key in self._mem_cache:
            cached = self._mem_cache[cache_key].copy()
            cached["status"] = "cached"
            cached["_warnings"] = []
            return cached

        result = self._call_curl(url, label)

        # 编码校验
        if result.get("status") == "ok":
            encoding_warnings = self._check_encoding(result.get("raw", ""))
            if encoding_warnings:
                result.setdefault("_warnings", []).extend(encoding_warnings)
                self._warnings.extend(encoding_warnings)

        # 缓存成功结果
        if result.get("status") == "ok":
            self._mem_cache[cache_key] = result.copy()
            self._fetch_log.append({
                "api": f"curl_{label}",
                "params": {"url": url},
                "status": "ok",
                "time": datetime.now().isoformat(),
            })

        return result

    # --------------------------------------------------------
    # 查询接口
    # --------------------------------------------------------

    def get_warnings(self) -> list:
        """返回所有累积告警"""
        return list(self._warnings)

    def finalize(self, snapshot: dict = None) -> dict:
        """
        在 runner 结束时调用，判定是否触发 critical_failure 停机。
        优先检查 snapshot 中各场景的最终状态（含 curl 补救），
        只有当 curl 补救也失败时才标记 critical_failure。

        返回 {"critical_failure": bool, "failed_scenes": list, "failure_summary": list}
        """
        core_scenes = ['s1_financial', 's2_quote_kline', 's5_events']
        critical_scenes = []

        if snapshot:
            # 方法 1: 从 snapshot 检查各场景的最终状态
            for scene in core_scenes:
                scene_data = snapshot.get(scene, {})
                if not isinstance(scene_data, dict):
                    continue

                data = scene_data.get("data", {})
                if not data:
                    # 没有 data 字段 → 场景未执行
                    critical_scenes.append(scene)
                    continue

                # 检查该场景的所有子项是否全部 failed
                # 修正 D: rows=0 也视为失败（空数据 = 假性成功）
                all_items_failed = True
                for key, val in data.items():
                    if isinstance(val, dict):
                        if val.get("status") in ("ok", "cached"):
                            # 检查是否有实际数据
                            rows = val.get("rows", -1)  # -1 表示无 rows 字段（非数据型）
                            if rows != 0:  # rows=0 视为失败，rows=-1 或 rows>0 视为有数据
                                all_items_failed = False
                                break

                if all_items_failed and data:
                    critical_scenes.append(scene)
        else:
            # 方法 2: 从 _fetch_log 推断（无 snapshot 时的降级）
            for scene in core_scenes:
                keywords = self._scene_keywords(scene)
                scene_logs = [l for l in self._fetch_log if any(k in l.get("api", "") for k in keywords)]
                if scene_logs and all(l.get("status") not in ("ok", "cached") for l in scene_logs):
                    critical_scenes.append(scene)

        result = {
            "critical_failure": len(critical_scenes) >= 2,
            "failed_scenes": critical_scenes,
            "failure_summary": [w for w in self._warnings if "all_failed" in w],
        }
        return result

    @staticmethod
    def _scene_keywords(scene: str) -> list:
        """场景名到 API 关键词的映射"""
        mapping = {
            's1_financial': ['stock_financial_report_sina', 'stock_financial_abstract',
                             'curl_eastmoney_datacenter', 'curl_sina_hq'],
            's2_quote_kline': ['stock_zh_a_spot_em', 'stock_zh_a_hist', 'stock_zh_a_daily',
                               'curl_eastmoney_kline', 'curl_sina_hq'],
            's5_events': ['stock_news_em'],
        }
        return mapping.get(scene, [scene])

    def get_summary(self) -> dict:
        """返回缓存摘要（哪些成功、哪些失败）"""
        ok_count = sum(1 for e in self._fetch_log if e.get("status") == "ok")
        fail_count = sum(1 for e in self._fetch_log if e.get("status") not in ("ok",))
        return {
            "stock_code": self.stock_code,
            "date": self._today,
            "total_fetches": len(self._fetch_log),
            "ok": ok_count,
            "failed": fail_count,
            "cached_entries": len(self._mem_cache),
            "warning_count": len(self._warnings),
            "fetch_log": self._fetch_log,
        }

    # ============================================================
    # 内部方法
    # ============================================================

    def _call_akshare(self, api_name: str, params: dict) -> dict:
        """调用 akshare API，返回标准化结果"""
        try:
            import akshare as ak
        except ImportError:
            msg = "[akshare] 未安装"
            self._warnings.append(msg)
            return {"status": "failed", "error": msg}

        func = getattr(ak, api_name, None)
        if func is None:
            msg = f"[akshare] API {api_name} 不存在"
            self._warnings.append(msg)
            return {"status": "failed", "error": msg}

        # 检查是否已知失效
        grade = SOURCE_GRADE.get(api_name, "B")
        if grade == "D":
            msg = f"[akshare] {api_name} 已知失效(D级)，跳过"
            self._warnings.append(msg)
            return {"status": "failed", "error": msg}

        try:
            df = func(**params)

            if df is None:
                return {"status": "failed", "error": f"{api_name} 返回 None"}

            # 处理非 DataFrame 返回（如 dict、list）
            if not hasattr(df, "empty"):
                return {
                    "status": "ok",
                    "api_used": api_name,
                    "params": params,
                    "rows": 0,
                    "columns": [],
                    "data_preview": [],
                    "data_full": [],
                    "raw_value": str(df)[:500],
                    "fetch_time": datetime.now().isoformat(),
                    "_grade": grade,
                    "_warnings": [],
                }

            if df.empty:
                return {"status": "failed", "error": f"{api_name} 返回空数据"}

            # 性能优化：全市场 API 自动过滤到目标股票
            if api_name in FULL_MARKET_APIS:
                code_col = FULL_MARKET_APIS[api_name]
                if code_col in df.columns:
                    stock_code_str = str(self.stock_code).zfill(6)
                    df_filtered = df[df[code_col].astype(str).str.zfill(6) == stock_code_str]
                    if len(df_filtered) == 0:
                        # 尝试不带前缀匹配
                        df_filtered = df[df[code_col].astype(str).str[-6:] == stock_code_str]
                    if len(df_filtered) > 0:
                        df = df_filtered
                    # 如果仍然匹配不到，保留全量（降级行为）

            # 性能优化：全历史 API 自动截取最近 N 行
            # 注意：大部分 API 返回数据是最新在前（head=最新），用 head() 截取
            if api_name in HISTORY_APIS:
                max_rows = HISTORY_APIS[api_name]
                if len(df) > max_rows:
                    df = df.head(max_rows).reset_index(drop=True)

            return {
                "status": "ok",
                "api_used": api_name,
                "params": params,
                "rows": len(df),
                "columns": list(df.columns),
                "data_preview": df.head(5).to_dict(orient="records"),
                "data_full": df.to_dict(orient="records"),
                "fetch_time": datetime.now().isoformat(),
                "_grade": grade,
                "_warnings": [],
            }

        except Exception as e:
            msg = f"[akshare] {api_name} 失败: {str(e)[:200]}"
            self._warnings.append(msg)
            return {"status": "failed", "error": msg, "api_used": api_name}

    def _call_curl(self, url: str, label: str) -> dict:
        """Shell curl 调用"""
        try:
            result = subprocess.run(
                ["curl", "-s", "--connect-timeout", "10", "-m", "15", url],
                capture_output=True,
                text=False,  # 二进制模式，手动解码以检测编码
                timeout=20,
            )
            if result.returncode == 0 and result.stdout:
                # 尝试 UTF-8 解码
                try:
                    text = result.stdout.decode("utf-8")
                except UnicodeDecodeError:
                    text = result.stdout.decode("gbk", errors="replace")
                    self._warnings.append(f"[curl] {label}: UTF-8 解码失败，已用 GBK fallback")

                if not text.strip():
                    return {"status": "failed", "error": f"curl_{label} 返回空"}

                return {
                    "status": "ok",
                    "api_used": f"curl_{label}",
                    "raw": text[:2000],
                    "fetch_time": datetime.now().isoformat(),
                    "_grade": "A",  # sina curl 为 A 级
                    "_warnings": [],
                }
            else:
                msg = f"[curl] {label} 失败: returncode={result.returncode}"
                self._warnings.append(msg)
                return {"status": "failed", "error": msg}

        except subprocess.TimeoutExpired:
            msg = f"[curl] {label} 超时(20s)"
            self._warnings.append(msg)
            return {"status": "failed", "error": msg}
        except Exception as e:
            msg = f"[curl] {label} 异常: {str(e)[:100]}"
            self._warnings.append(msg)
            return {"status": "failed", "error": msg}

    # --------------------------------------------------------
    # 三项内置校验
    # --------------------------------------------------------

    def _auto_validations(self, api_name: str, result: dict) -> list:
        """自动运行的校验（不需 cross_check 标志）"""
        warnings = []

        # 1. 陈旧检查
        stale_warn = self._check_staleness(result)
        if stale_warn:
            warnings.append(stale_warn)

        # 2. 编码检查（对 curl 结果）
        if result.get("api_used", "").startswith("curl_"):
            encoding_warns = self._check_encoding(result.get("raw", ""))
            warnings.extend(encoding_warns)

        return warnings

    def _run_cross_checks(self, api_name: str, params: dict, result: dict) -> list:
        """完整交叉验证（需 cross_check=True）"""
        warnings = []

        # 1. 陈旧检查
        stale_warn = self._check_staleness(result)
        if stale_warn:
            warnings.append(stale_warn)

        # 2. 降级源检查：如果用的是 B/C 级源，尝试与首选源对比
        grade = SOURCE_GRADE.get(api_name, "B")
        if grade in ("B", "C"):
            primary_name = PRIMARY_SOURCE_FOR.get(api_name)
            if primary_name:
                primary_result = self._call_akshare(primary_name, params)
                if primary_result.get("status") == "ok":
                    warn = (
                        f"[cross_check] {api_name}({grade}级) 已获取数据，"
                        f"首选源 {primary_name} 也可用，建议对比。"
                    )
                    warnings.append(warn)
                else:
                    warn = (
                        f"[cross_check] {api_name}({grade}级) 为当前最优源，"
                        f"首选源 {primary_name} 不可用。"
                    )
                    warnings.append(warn)

        # 3. 编码检查
        if result.get("api_used", "").startswith("curl_"):
            encoding_warns = self._check_encoding(result.get("raw", ""))
            warnings.extend(encoding_warns)

        return warnings

    @staticmethod
    def _check_staleness(result: dict, max_age_days: int = 7) -> Optional[str]:
        """
        陈旧检查：如果数据最新日期超过 max_age_days 天，发出告警。
        从 data_full 或 data_preview 中提取日期字段。
        """
        if result.get("status") != "ok":
            return None

        data = result.get("data_full", result.get("data_preview", []))
        if not data or not isinstance(data, list):
            return None

        # 尝试常见的日期字段名
        date_fields = [
            "日期", "报告日", "时间", "date", "Date",
            "交易日", "报告期", "截止日", "公布日期",
        ]

        latest_date = None
        for row in data[:10]:  # 只检查前 10 行
            if not isinstance(row, dict):
                continue
            for field in date_fields:
                val = row.get(field)
                if val is None:
                    continue
                val_str = str(val)[:10]
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y年%m月%d日"):
                    try:
                        dt = datetime.strptime(val_str, fmt)
                        if latest_date is None or dt > latest_date:
                            latest_date = dt
                        break
                    except ValueError:
                        continue

        if latest_date is None:
            return None

        age = (datetime.now() - latest_date).days
        if age > max_age_days:
            return (
                f"[staleness] 数据陈旧: 最新日期 {latest_date.strftime('%Y-%m-%d')}，"
                f"距今 {age} 天（阈值 {max_age_days} 天）"
            )
        return None

    @staticmethod
    def _check_encoding(text: str) -> list:
        """
        编码检查：验证文本是否为有效 UTF-8 且无乱码特征。
        """
        warnings = []

        if not text:
            return warnings

        # 检查常见乱码模式（GBK 被错误当 Latin-1 解码）
        garbled_patterns = [
            "�",           # Unicode 替换字符
            "\xc0\xc1",         # GBK 典型乱码
            "锟斤拷",           # UTF-8 乱码经典特征
            "烫烫烫",           # 未初始化内存乱码
        ]
        for pattern in garbled_patterns:
            if pattern in text:
                warnings.append(f"[encoding] 检测到疑似乱码: '{pattern}'")
                break

        # 检查非打印字符比例
        non_printable = sum(1 for c in text[:500] if ord(c) < 32 and c not in "\n\r\t")
        if non_printable > 10:
            warnings.append(
                f"[encoding] 前500字符含 {non_printable} 个非打印字符，可能编码异常"
            )

        return warnings


# ============================================================
# CLI 测试入口
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python data_snapshot.py <stock_code> [api_name]")
        print("示例: python data_snapshot.py 002130")
        print("      python data_snapshot.py 002130 stock_zh_a_daily")
        sys.exit(1)

    code = sys.argv[1]
    api = sys.argv[2] if len(sys.argv) > 2 else "stock_zh_a_daily"

    ds = DataSnapshot(code)
    print(f"--- 测试 {api} ---")
    r = ds.fetch_or_cache(api, {"symbol": code})
    print(json.dumps({k: v for k, v in r.items() if k != "data_full"},
                     ensure_ascii=False, indent=2, default=str))

    if r.get("status") == "ok":
        print(f"\n--- 缓存命中测试 ---")
        r2 = ds.fetch_or_cache(api, {"symbol": code})
        print(f"第二次状态: {r2['status']}")

    print(f"\n--- Summary ---")
    print(json.dumps(ds.get_summary(), ensure_ascii=False, indent=2, default=str))

    print(f"\n--- Warnings ---")
    for w in ds.get_warnings():
        print(f"  {w}")

    ds.save()
