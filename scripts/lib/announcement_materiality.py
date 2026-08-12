# -*- coding: utf-8 -*-
"""大事提醒事件分类（RPT_F10_REMIND · 45 码）+ fatal / horizon / actor 派生纯函数。

事件层主源：东财 F10 大事提醒。`_EVENT_FLAVOR` 45 码表（名称 + flavor）→ frozenset 派生
（`_RISK/_CATALYST/_FORWARD/_FATAL_CODES`）。本模块提供分类/派生纯函数，runner._build_timeline
与 capstone.fatal 共用。纯函数无 IO，可单测。

  - `is_fatal`：公司级致命缺陷（330/360/430 代码级 ∪ 230退市/240新名ST/270重大违法 条件升级）；
  - `directional_flavor`：002 业绩快报 / 003 业绩预告 方向派生（LV1 关键词）；
  - `derive_horizon`：按码派生 {reaction, overhang, proximity_days}（capstone present_signals 用）；
  - `detect_actor_tier`：label PRIMARY + 标题细化 → actor 级别中文标签（programs / shareholder_dynamics 用）。
"""
import re
from datetime import date, datetime, timezone

# ============================================================
# 大事提醒时间线事件分类（RPT_F10_REMIND · 45 码 · 事件层主源）
# ============================================================
# 东财 F10 大事提醒 EVENT_TYPE_CODE → (名称, flavor)。flavor∈{risk,catalyst,forward,
# neutral,directional}。45 码经 65+ 票（含科创/北交/B股/新股/退市）多深页穷尽实测，
# 完整性扫描「45 码外无新增」。directional（002 业绩快报 / 003 业绩预告）由 LV1 关键词
# 定方向（directional_flavor）。官方码上扁平查表（无三档 severity/escalate/R-C-register）。
# runner._build_timeline + capstone.fatal 共用。
_EVENT_FLAVOR = {
    "001": ("报表披露", "neutral"), "002": ("业绩快报", "directional"), "003": ("业绩预告", "directional"),
    "004": ("分红送转", "catalyst"), "005": ("股东大会", "neutral"), "006": ("龙虎榜", "neutral"),
    "070": ("沪深港通", "neutral"), "080": ("限售解禁", "risk"), "090": ("股东增减持", "forward"),
    "100": ("高管及关联方增减持", "forward"), "110": ("股票回购", "catalyst"), "120": ("新增概念", "neutral"),
    "130": ("机构调研", "neutral"), "140": ("资本运作", "neutral"), "150": ("股权激励", "catalyst"),
    "160": ("股权质押", "risk"), "170": ("解除质押", "catalyst"), "180": ("增发", "risk"), "190": ("配股", "risk"),
    "200": ("申购提示", "neutral"), "210": ("可转债", "catalyst"), "220": ("停复牌", "risk"),
    "230": ("上市状态变动", "risk"), "240": ("名称变动", "risk"), "250": ("对外担保", "risk"),
    "260": ("诉讼仲裁", "risk"), "270": ("违规处罚", "risk"), "280": ("股东户数", "neutral"),
    "290": ("融资融券", "neutral"), "300": ("大宗交易", "neutral"), "310": ("项目投资", "catalyst"),
    "320": ("增减持计划", "forward"), "330": ("非标审计意见", "risk"), "340": ("监管问询", "risk"),
    "350": ("风险提示", "risk"), "360": ("破产重整", "risk"), "370": ("法定代表人变更", "neutral"),
    "380": ("董事长变更", "neutral"), "390": ("总经理变更", "neutral"), "400": ("投资互动", "neutral"),
    "410": ("项目中标", "catalyst"), "420": ("重要合同", "catalyst"), "430": ("风险警示", "risk"),
    "450": ("吸收合并", "risk"), "460": ("股权转让", "neutral"),
}
# flavor 派生 frozenset（_build_timeline 分桶用；110 回购 catalyst 亦是 forward 装配源，故 _FORWARD 含 110）
_RISK_CODES = frozenset(c for c, (_, fl) in _EVENT_FLAVOR.items() if fl == "risk")
_CATALYST_CODES = frozenset(c for c, (_, fl) in _EVENT_FLAVOR.items() if fl == "catalyst")
_FORWARD_CODES = frozenset({"090", "100", "110", "320"})
# 代码级自动 fatal（公司致命缺陷：非标审计 / 破产重整 / 风险警示ST）。条件升级见 is_fatal()。
_FATAL_CODES = frozenset({"330", "360", "430"})


def is_fatal(code, level1_content="", specific=""):
    """大事提醒事件是否构成公司级致命缺陷（capstone fatal=True 不可投的唯一源）。

    - 代码级：{330 非标审计, 360 破产重整, 430 风险警示} → True
    - 条件升级（LV1/SPECIFIC 关键词）：
      · 230 上市状态变动 & SPECIFIC 含「退市」→ True（新股上市 SPECIFIC="新股上市"→False）
      · 240 名称变动 & 新名(→右侧)以 ST/*ST 开头 → True（去ST/摘帽→False；5 向判定见下）
      · 270 违规处罚 & LV1 含「重大违法|立案调查|强制退市」→ True（轻量信披违规→False）
    - 080 大额解禁**不**升级 fatal（供给压力=m6 悲观核心 risk，非公司致命缺陷）。
    """
    if code in _FATAL_CODES:
        return True
    s = f"{level1_content or ''}{specific or ''}"
    if code == "230" and "退市" in s:
        return True
    if code == "240":
        # 旧名→新名(ST/*ST+公司名)；5 向：加*ST→fatal / 加ST(旧名无*)→fatal /
        # 去*ST(旧名带*)→降级risk / 摘帽→catalyst。实测校正：旧「LV1含ST」误判去ST为fatal。
        m = re.match(r"(.+?)→\s*(\*?ST)\s*(\S*)", s)
        if m:
            old, new_pref = m.group(1), m.group(2)
            if new_pref == "*ST":
                return True
            return not old.startswith("*ST")
        return False
    if code == "270" and re.search(r"重大违法|立案调查|强制退市", s):
        return True
    return False


def directional_flavor(level1_content=""):
    """002 业绩快报 / 003 业绩预告 的方向派生（LV1 关键词）。→catalyst/risk/neutral。

    实测：003「业绩预增…同比上升50%」→catalyst；预减/亏损→risk。
    """
    s = level1_content or ""
    if re.search(r"预增|扭亏|续盈|上升|增长|盈利", s):
        return "catalyst"
    if re.search(r"预减|亏损|下滑|下降|转亏|减少", s):
        return "risk"
    return "neutral"


# ============================================================
# structured_horizon 默认（按码派生，无 IO）
# ============================================================
# reaction: immediate(即时反应) / latent(潜伏) / none(无即时反应)
# overhang: sustained(持续压制/支撑) / transient(短暂)
_HORIZON_DEFAULT = {
    "M1":  {"reaction": "immediate", "overhang": "sustained"},   # 减持窗口持续压制
    "M2":  {"reaction": "latent",    "overhang": "sustained"},   # 质押平仓线潜伏
    "M3":  {"reaction": "immediate", "overhang": "transient"},   # 解禁日临近（窗口）
    "M4":  {"reaction": "immediate", "overhang": "sustained"},   # 监管/诉讼持续
    "M5":  {"reaction": "immediate", "overhang": "sustained"},   # ST/退市
    "M6":  {"reaction": "latent",    "overhang": "sustained"},   # 增发稀释
    "M7":  {"reaction": "immediate", "overhang": "transient"},   # 监管函
    "M8":  {"reaction": "immediate", "overhang": "sustained"},   # 业绩下修
    "M9":  {"reaction": "latent",    "overhang": "sustained"},   # 或有负债
    "M10": {"reaction": "immediate", "overhang": "transient"},   # 异动/停牌
    "M11": {"reaction": "immediate", "overhang": "sustained"},   # 人员变动/立案（治理持续）
    "P1":  {"reaction": "immediate", "overhang": "transient"},   # 增持信号
    "P2":  {"reaction": "latent",    "overhang": "sustained"},   # 回购期持续支撑
    "P4":  {"reaction": "immediate", "overhang": "sustained"},   # 业绩上修
    "P6":  {"reaction": "latent",    "overhang": "sustained"},   # 合同催化
    "P7":  {"reaction": "latent",    "overhang": "transient"},   # 补贴/认证
    "P8":  {"reaction": "latent",    "overhang": "sustained"},   # 重组/扩张
    "P3":  {"reaction": "none",      "overhang": "transient"},   # 分红（m9.1 详述）
    "P5":  {"reaction": "none",      "overhang": "transient"},   # 激励（治理，弱即时）
    "P9":  {"reaction": "immediate", "overhang": "sustained"},   # 经营数据（即时反应+持续跟踪价值）
}


def _parse_date(s):
    """解析 ISO 字符串 'YYYY-MM-DD' / epoch 秒 / epoch 毫秒 / date 对象 → date 或 None。"""
    if s is None or s == "":
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, (int, float)):
        v = float(s)
        if v > 1e12:  # 毫秒
            v /= 1000.0
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None
    st = str(s).strip()
    m = re.match(r"(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})?", st)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def derive_horizon(code, event_date=None, today=None):
    """按码派生 {reaction, overhang, proximity_days}。

    proximity_days = event_date - today（正=未来，负=已过）。仅 M3 解禁/M1 减持窗口/M6 破发
    等时窗型事件有意义；无 event_date → None。
    """
    base = dict(_HORIZON_DEFAULT.get(code, {"reaction": "immediate", "overhang": "transient"}))
    prox = None
    if event_date is not None:
        d0 = _parse_date(event_date)
        d1 = _parse_date(today) if today is not None else date.today()
        if d0 is not None and d1 is not None:
            prox = (d0 - d1).days
    base["proximity_days"] = prox
    return base


# ============================================================
# ST1 actor 级别检测（label PRIMARY + 标题细化）→ actor_tier 中文标签
# ============================================================
# 10x 实证（59185 条）：减持族 855 条，"控股股东/实控人"关键词仅覆盖 16.7%，5%以上/特定/大股东占 27.8%。
# label「股东/实际控制人股份减持」761 条官方结构化（317 条标题无关键词）→ label 作 PRIMARY（硬规则②）。
_CONTROLLER_KEYWORDS = ("实际控制人", "实控人", "控股股东")
# 5%以上股东/特定股东/大股东/前N大股东（标题 SECONDARY 细化）
_MAJOR5PCT_PATTERNS = re.compile(r"(5\s*%\s*以上|持股\s*5\s*%|特定股东|大股东|前\s*\d+\s*大股东)")
# label PRIMARY：官方公告类型已结构化标记"股东级"（覆盖标题无关键词 case）
_MAJOR5PCT_LABEL_HINTS = ("股东/实际控制人", "股东减持", "股东增持", "实际控制人股份")
_EXECUTIVE_KEYWORDS = ("董监高", "董事", "监事", "高级管理人员", "总经理", "经理", "董事会秘书", "董秘")


def detect_actor_tier(label, title):
    """label PRIMARY + 标题细化 → actor 级别中文标签。

    返回 "实控人" / "5%以上股东" / "董监高" / None（未明，omit 避免 G46 误校验）。
    标签值供 m4 §4.2 actor 列 surface（G46 泛型校验须 verbatim 出现）。

    优先级（硬规则②：官方结构化分类器 PRIMARY，regex SECONDARY）：
      1. 标题含 实际控制人/实控人/控股股东 → "实控人"（最强信号，标题点名）
      2. label 含「股东/实际控制人股份减持」类 → "5%以上股东"（label PRIMARY 覆盖无关键词 case）
      3. 标题 5%/特定/大股东 regex → "5%以上股东"
      4. 标题 董监高/董事/经理 → "董监高"
    """
    t = title or ""
    l = label or ""
    if any(k in t for k in _CONTROLLER_KEYWORDS):
        return "实控人"
    if any(k in l for k in _MAJOR5PCT_LABEL_HINTS):
        return "5%以上股东"
    if _MAJOR5PCT_PATTERNS.search(t):
        return "5%以上股东"
    if any(k in t for k in _EXECUTIVE_KEYWORDS):
        return "董监高"
    return None
