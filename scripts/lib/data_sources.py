#!/usr/bin/env python3
"""
data_sources.py —— stock-analysis 共享数据源（curl 直连，标准 envelope）

落点：stock-orchestrator/scripts/lib/data_sources.py
职责：为 stock-intraday-t-analyzer（日内低吸定位器）及其它 skill 提供
      统一形状的 fetcher。每个 fetcher 返回标准 envelope：

      {
        "status": "ok" | "failed",
        "api_used": str,
        "source": str,
        "data": {...},            # 结构化产出
        "_warnings": [str, ...],
      }

设计原则：
  - fetch 与 analyze 分离：本模块只负责抓数据，不做任何指标/信号计算。
  - 失败 graceful：任何异常都吞成 status=failed + _warnings，绝不抛给上层。
  - 编码：Sina hq/MoneyFlow/TransListV2 与腾讯 qt/s_p 均可能 GBK，统一 try UTF-8→GBK。

★ 2026-07-11 live 实测可用（非东财，无 IP 封禁）：
  - Sina getKLineData（分钟 K 线）
  - Sina MoneyFlow.ssi_ssfx_flzjtj（当日资金流快照）
  - Sina CN_TransListV2.php（内外盘）
  - 腾讯 s_p{code}（分价表 / 成交密集区）
  - 腾讯 q={code}（五档快照）
"""

import json
import re
import urllib.request

# ============================================================
# 内部工具
# ============================================================

_DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _curl(url: str, headers: dict = None, referer: str = None,
          timeout: int = 15, encodings=("utf-8", "gbk")) -> str:
    """GET 抓取，自动尝试多种编码。失败抛异常（由调用方吞成 failed envelope）。"""
    h = dict(_DEFAULT_HEADERS)
    if headers:
        h.update(headers)
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    last_err = None
    for enc in encodings:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError as e:
            last_err = e
    # 兜底：errors=replace
    return raw.decode(encodings[0], errors="replace")


def _ok(api_used: str, source: str, data: dict, warnings: list = None) -> dict:
    return {
        "status": "ok",
        "api_used": api_used,
        "source": source,
        "data": data,
        "_warnings": warnings or [],
    }


def _failed(api_used: str, source: str, error: str) -> dict:
    return {
        "status": "failed",
        "api_used": api_used,
        "source": source,
        "data": {},
        "_warnings": [f"{api_used}: {error}"],
    }


def _normalize_code(code: str) -> str:
    """归一化代码为带小写市场前缀：'600031'/'sh600031'/'SH600031' → 'sh600031'。"""
    c = code.strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        return c
    if c[0] in "6":          # 沪市主板/科创板
        return f"sh{c}"
    if c[0] in "03":         # 深市主板/中小板
        return f"sz{c}"
    if c[0] == "8":          # 北交所
        return f"bj{c}"
    return f"sz{c}"          # 兜底深市


# ============================================================
# 历史回测层：分钟 K 线（引擎核心输入）
# ============================================================

def fetch_kline_sina(code: str, scale: int = 5, datalen: int = 2016) -> dict:
    """Sina getKLineData —— 分钟 OHLCV + datetime。

    Args:
        code: 股票代码（带或不带市场前缀）
        scale: K 线周期（分钟），∈ {5,15,30,60,240}
        datalen: 返回 bar 数（硬上限 ~5049 ≈ 105 交易日 @5min）

    Returns envelope.data = {
        "symbol": "sh600031",
        "scale": 5,
        "bars": [{"datetime":"2026-...","open":..,"high":..,"low":..,"close":..,"volume":..}, ...]
    }
    """
    api = "fetch_kline_sina"
    sym = _normalize_code(code)
    url = (f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={sym}&scale={scale}&ma=no&datalen={datalen}")
    try:
        text = _curl(url, referer="https://finance.sina.com.cn")
        rows = json.loads(text)
        bars = []
        for r in rows:
            bars.append({
                "datetime": r["day"],
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]),
            })
        if not bars:
            return _failed(api, "sina", "返回空 bar 列表")
        return _ok(api, "sina", {"symbol": sym, "scale": scale, "bars": bars})
    except Exception as e:
        return _failed(api, "sina", str(e)[:150])


def fetch_daily_akshare(code: str, adjust: str = "qfq", datalen: int = 300) -> dict:
    """akshare stock_zh_a_daily —— 日线 OHLCV + amount + turnover + outstanding_share。

    Args:
        code: 股票代码（带或不带市场前缀）
        adjust: 复权，默认 "qfq"（前复权）；MA/缺口/周线必须复权，否则除权日跳空污染
        datalen: 返回日线根数（截尾；MA250 + 26 周聚合需 ≥250 交易日）

    Returns envelope.data = {
        "symbol": "sh600031", "scale": "daily", "adjust": "qfq",
        "bars": [{"date","open","high","low","close","volume","amount",
                  "turnover","outstanding_share"}, ...]
    }
    turnover 为比率（volume/outstanding_share），显示层需 ×100。
    """
    api = "fetch_daily_akshare"
    sym = _normalize_code(code)
    try:
        import akshare as ak
        df = ak.stock_zh_a_daily(symbol=sym, adjust=adjust)
        if df is None or len(df) == 0:
            return _failed(api, "akshare", "返回空 DataFrame")
        df = df.tail(datalen).reset_index(drop=True)
        has_amount = "amount" in df.columns
        has_turnover = "turnover" in df.columns
        has_share = "outstanding_share" in df.columns
        bars = []
        for i in range(len(df)):
            d = df["date"].iloc[i]
            bars.append({
                "date": d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d),
                "open": float(df["open"].iloc[i]),
                "high": float(df["high"].iloc[i]),
                "low": float(df["low"].iloc[i]),
                "close": float(df["close"].iloc[i]),
                "volume": float(df["volume"].iloc[i]),
                "amount": float(df["amount"].iloc[i]) if has_amount else None,
                "turnover": float(df["turnover"].iloc[i]) if has_turnover else None,
                "outstanding_share": float(df["outstanding_share"].iloc[i]) if has_share else None,
            })
        if not bars:
            return _failed(api, "akshare", "解析后空 bar 列表")
        return _ok(api, "akshare",
                   {"symbol": sym, "scale": "daily", "adjust": adjust, "bars": bars})
    except Exception as e:
        return _failed(api, "akshare", str(e)[:150])


# ============================================================
# 当日实盘增强层（描述性上下文，非触发）
# ============================================================

def fetch_fund_flow_sina(code: str) -> dict:
    """Sina MoneyFlow.ssi_ssfx_flzjtj —— 当日资金流快照（大单/特大单/小单/散单净流入）。

    Returns envelope.data = {
        "main_net": float,   # 主力(特大单+大单)净流入，万元
        "huge_net": float,   # 特大单净流入，万元
        "big_net":  float,   # 大单净流入，万元
        "mid_net":  float,   # 中单净流入，万元
        "small_net":float,   # 小单净流入，万元
        "retail_net":float,  # 散户(小单+散单)净流入，万元
    }
    """
    api = "fetch_fund_flow_sina"
    sym = _normalize_code(code)
    url = (f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"MoneyFlow.ssi_ssfx_flzjtj?daima={sym}")
    try:
        text = _curl(url, referer="https://vip.stock.finance.sina.com.cn/moneyflow/")
        d = json.loads(text)
        w = 10000.0  # 元 → 万元
        def net(a, b):
            return round((float(d.get(a, 0)) - float(d.get(b, 0))) / w, 2)
        huge, big = net("r0_in", "r0_out"), net("r1_in", "r1_out")
        small = net("r2_in", "r2_out")
        retail_unit = net("r3_in", "r3_out")
        return _ok(api, "sina", {
            "main_net": round(huge + big, 2),
            "huge_net": huge,
            "big_net": big,
            "mid_net": small,        # sina r2 字段语义为小单（与东财口径差异，仅展示）
            "small_net": retail_unit,
            "retail_net": round(small + retail_unit, 2),
        })
    except Exception as e:
        return _failed(api, "sina", str(e)[:150])


def fetch_inoutvol_sina(code: str) -> dict:
    """Sina CN_TransListV2.php —— 内外盘（日内主动买/卖累计量）。

    响应含 `var trade_INVOL_OUTVOL=[内盘,外盘];`（INVOL=内盘=主动卖, OUTVOL=外盘=主动买）。

    Returns envelope.data = {"invol": float, "outvol": float}  （单位：股）
    """
    api = "fetch_inoutvol_sina"
    sym = _normalize_code(code)
    rn = int(__import__("time").time() * 1000) % 100000000  # cache-buster
    url = (f"https://vip.stock.finance.sina.com.cn/quotes_service/view/"
           f"CN_TransListV2.php?num=11&symbol={sym}&rn={rn}")
    try:
        text = _curl(url, referer=f"https://finance.sina.com.cn/realstock/company/{sym}/")
        m = re.search(r"trade_INVOL_OUTVOL=\[(\d+)\s*,\s*(\d+)\]", text)
        if not m:
            return _failed(api, "sina", "未匹配到 trade_INVOL_OUTVOL")
        invol, outvol = int(m.group(1)), int(m.group(2))
        return _ok(api, "sina", {"invol": float(invol), "outvol": float(outvol)})
    except Exception as e:
        return _failed(api, "sina", str(e)[:150])


def fetch_pricezone_tencent(code: str, topn: int = 3) -> dict:
    """腾讯 s_p{code} 分价表 —— 成交密集区 topN。

    解析 v_s_p{code}="price~buyvol~sellvol~net~?^price~...^...";
    返回按成交量(买+卖)降序的 topN 区，单位：价(元)/量(手)。

    Returns envelope.data = {"zones": [{"price":..,"buyvol":..,"sellvol":..,"net":..,"total":..}, ...]}
    """
    api = "fetch_pricezone_tencent"
    sym = _normalize_code(code)
    tencent_code = sym  # 腾讯分价表用 sh/sz 前缀
    url = f"https://qt.gtimg.cn/?q=s_p{tencent_code}"
    try:
        text = _curl(url, referer="https://gu.qq.com/")
        # v_s_psh600031="...^...~...~..."; 取引号内内容
        m = re.search(r'v_s_p' + re.escape(sym) + r'="([^"]+)"', text)
        if not m:
            return _failed(api, "tencent", "未匹配到 v_s_p 变量")
        body = m.group(1)
        zones = []
        for seg in body.split("^"):
            seg = seg.strip()
            if not seg or seg == "?":
                continue
            f = seg.split("~")
            if len(f) < 4:
                continue
            try:
                price = float(f[0])
            except ValueError:
                continue
            buyvol = float(f[1]) if f[1] else 0.0
            sellvol = float(f[2]) if f[2] else 0.0
            net = float(f[3]) if f[3] not in ("", "?") else 0.0
            if price <= 0:
                continue
            zones.append({
                "price": price,
                "buyvol": buyvol,
                "sellvol": sellvol,
                "net": net,
                "total": buyvol + sellvol,
            })
        zones.sort(key=lambda z: z["total"], reverse=True)
        return _ok(api, "tencent", {"zones": zones[:topn]})
    except Exception as e:
        return _failed(api, "tencent", str(e)[:150])


def fetch_snapshot_tencent(code: str) -> dict:
    """腾讯 q={code} 五档快照 —— 当前价/涨跌幅/换手/内外盘/五档。

    Returns envelope.data = {
        "price": float, "pct": float, "turnover": float,
        "outvol": float, "invvol": float,
        "bid": [5 floats], "bidvol": [5], "ask": [5], "askvol": [5],
    }
    """
    api = "fetch_snapshot_tencent"
    sym = _normalize_code(code)
    url = f"https://qt.gtimg.cn/?q={sym}"
    try:
        text = _curl(url, referer="https://gu.qq.com/")
        m = re.search(r'v_' + re.escape(sym) + r'="([^"]+)"', text)
        if not m:
            return _failed(api, "tencent", "未匹配到快照变量")
        f = m.group(1).split("~")
        # 字段索引（腾讯快照标准）：1=名称 3=现价 32=涨跌幅 37=成交额 38=换手 7=外盘 8=内盘
        # 五档：9..19 (bid5price,bid5vol,...,bid1)/(19..29 ask) —— 实测索引可能漂移，做防御解析
        def g(i):
            try:
                return float(f[i])
            except (IndexError, ValueError):
                return 0.0

        price = g(3)
        pct = g(32)
        turnover = g(38)
        outvol = g(7)
        invvol = g(8)
        # 五档：买1-5 在索引 9..18（价量交替），卖1-5 在 19..28
        bid, bidvol, ask, askvol = [], [], [], []
        for k in range(5):
            bid.append(g(9 + k * 2))
            bidvol.append(g(10 + k * 2))
            ask.append(g(19 + k * 2))
            askvol.append(g(20 + k * 2))
        return _ok(api, "tencent", {
            "price": price, "pct": pct, "turnover": turnover,
            "outvol": outvol, "invvol": invvol,
            "bid": bid, "bidvol": bidvol, "ask": ask, "askvol": askvol,
        })
    except Exception as e:
        return _failed(api, "tencent", str(e)[:150])
