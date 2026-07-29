# -*- coding: utf-8 -*-
"""公告重要性矩阵 v3 —— material 过滤 / horizon 派生 / title 派生 machine_fields / M4 拆分。

**单一真相源（NEW 逻辑）**。加法式：不动 runner 既有的 _SIG_NAME/_SIG_ACTION/_RISK_REG/
_CAT_REG/_reg_sev（M11 在 runner 内就地加行）。本模块只提供 NEW 的 materiality 纯函数，
runner._process_material_signals 调用。设计见 plan: 公告重要性矩阵 v3。

为什么是独立模块：
  - 矩阵（码→material子类/horizon/machine_field）与 label→code 映射（_NOTICE_MAP）解耦；
  - 纯函数无 IO，可单测；
  - gate_definitions / capstone 可复用同一 MATRIX（机判谓词一致）。

断言必验数据基线（/tmp/notices_33d.json 59185 条，2026-07-26）：
  - M11「高管人员任职变动」3303 条（第 3 高频 label，原完全未映射）；
  - M2「股份质押、冻结」1069 条（M2 原零 label 映射）；
  - 标题含 machine_field 的高密度码：M11 角色 ~88% / M9 被担保方 ~52% / M1 占比 ~36%；
  - 金额/股数/认购方 在标题里 ~0% → depth_fields 不机判（走 LLM「⚠️ 注」）。
"""
import re
from datetime import date, datetime, timezone

# ============================================================
# M4 拆分：监管类(any→critical) vs 诉讼仲裁(default warning)
# ============================================================
# 监管类 label：处罚/违法违规/资金占用/审计非标/会计差错/审计机构变更 → critical
_M4_REGULATORY_LABELS = {
    "处罚", "违法违规", "会计差错更正", "审计机构变更",
}
# 诉讼仲裁 label → default warning（仅当 body/news 确认金额/涉案才升 critical，走 depth→LLM「⚠️ 注」）
_M4_LITIGATION_LABELS = {"诉讼仲裁"}


def m4_subtype_severity(label):
    """M4 拆分。返回 (子类, severity) 或 None（非 M4 子类）。

    监管类(处罚/违法违规/会计差错/审计机构变更) → ('regulatory','critical')；
    诉讼仲裁 → ('litigation','warning')。
    """
    if label in _M4_REGULATORY_LABELS:
        return ("regulatory", "critical")
    if label in _M4_LITIGATION_LABELS:
        return ("litigation", "warning")
    return None


# ============================================================
# material 子类过滤：routine 子类不进 announcements[] 登记表（致命缺陷2）
# ============================================================
# code → [(drop_regex, reason)]：title 命中任一 pattern → 剔除（routine 备案）。
# 设计：M9 剔境内子公司担保（境外保留）/ M6 剔预案获准提示 / P5 剔行权归属调整 /
#       P8 剔设立子公司。P3 分红整体不进 critical（已 info，m9.1 详述）。
_ROUTINE_DROP = {
    "M9": [(r"境内|为全资子公司|为控股子公司|为子公司", "境内子公司担保（境外担保保留）")],
    "M6": [(r"预案|获准|提示性|进展|方案修订", "增发预案/获准/提示（routine 备案）")],
    "P5": [(r"行权|归属|对象名单|激励进展|行权价|数量调整", "行权归属/调整（routine）")],
    "P8": [(r"设立.*公司|增资扩股", "设立子公司/增资（routine）")],
    "P3": [],  # 分红整体不进 critical 表（已 info；m9.1 详述，登记表只留 flag）
}


def is_material(code, label, title):
    """routine 子类过滤。True=material（进登记表），False=routine（剔除）。

    机判谓词：title 正则匹配 _ROUTINE_DROP[code] 任一 → False。
    """
    t = title or ""
    for pat, _reason in _ROUTINE_DROP.get(code, []):
        if re.search(pat, t):
            return False
    return True


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
# title 派生 machine_fields（高密度码，10x 实证标题高频含此信息）
# ============================================================
# depth_fields（金额/股数/认购方/破发）标题 ~0%，不在本函数——走 LLM「⚠️ 注」，gate 不校验。

_M11_ROLES = ["实际控制人", "实控人", "董事长", "总经理", "首席执行官", "CEO", "首席",
              "财务总监", "CFO", "董事会秘书", "董秘", "副总经理", "总经理助理", "独立董事"]


def extract_machine_fields(code, title):
    """从公告标题抽高密度码的 machine_field（机判可校验）。返回 dict（空=抽不到）。

    - M11: role（角色名）+ change（离任/聘任/被立案）
    - M9:  guarantee_party（被担保方）
    - M1:  ratio_pct（占比，如 5%）
    - M5:  st_action（实施/撤销/破产）
    - P7:  subject（专利/认证/补贴项目名）
    - P8:  target（重组标的）
    """
    t = title or ""

    if code == "M11":
        out = {}
        roles = [kw for kw in _M11_ROLES if kw in t]
        if roles:
            # 去重保序（实际控制人/实控人 同义，取首现）
            seen, uniq = set(), []
            for r in roles:
                key = "实控人" if r in ("实际控制人", "实控人") else r
                if key not in seen:
                    seen.add(key)
                    uniq.append(key)
            out["role"] = "、".join(uniq)
        if any(k in t for k in ["离职", "辞职", "离任", "免去", "免职", "辞任"]):
            out["change"] = "离任"
        elif any(k in t for k in ["立案", "调查", "留置", "监察"]):
            out["change"] = "被立案/调查"
        elif any(k in t for k in ["聘任", "选举", "任命", "上任", "继任"]):
            out["change"] = "聘任"
        return out

    if code == "M9":
        m = re.search(r"(?:为|对|向)([一-龥A-Za-z（）()]{2,12}?)(?:提供)?(?:担保|质押|保证)", t)
        return {"guarantee_party": m.group(1).strip("的之提供")} if m else {}

    if code == "M1":
        # trap-1 guard（10× 实测）：裸 `(\d+)%` 会把「持股5%以上股东」的 5% 误当减持上限。
        # 排除「X%以上」actor 门槛型（负向前瞻），且要求真上限上下文（不超/不超过/比例/占）。
        # 注：ratio_pct 仅 title 派生参考，无下游消费者；权威上限% 由 body-parse →
        # programs[].announced_pct_cap 提供（ST5.1），此处仅防误导。
        m = re.search(r"(\d+(?:\.\d+)?)\s*%(?!以上)", t)
        if m and any(k in t for k in ("不超", "比例", "占")):
            return {"ratio_pct": m.group(1) + "%"}
        return {}

    if code == "M5":
        if "破产" in t or "清算" in t:
            return {"st_action": "破产清算"}
        if "实施" in t and "退市" in t:
            return {"st_action": "实施退市风险警示"}
        if "终止上市" in t:
            return {"st_action": "终止上市风险"}
        if "撤销" in t:
            return {"st_action": "撤销风险警示（摘帽）"}
        return {}

    if code == "P7":
        m = re.search(r"(?:获得|取得|通过)([一-龥A-Za-z0-9]{2,20})(?:认证|专利|补贴|资助)", t)
        return {"subject": m.group(1)} if m else {}

    if code == "P8":
        # 标的全名：贪婪 ≤40（治 SJSEMICONDUCTORCORPORATION 类长名截断），在「第一个
        # 非名称边界词」处截断。原则：标的名是紧实体（公司/集团/资产名），其后的一切
        # （连词/instrument/登记/文档/法律词）都是噪声——在第一个边界词切断即得干净名。
        #   ① 剥评估报告书前缀噪声「(股权|股份|资产)?所?涉及的」；
        #   ② 在第一个边界词截断（暨/及/并｜instrument 股权/股东/股份｜登记/文档/法律词）；
        #      股份用负向先行保护「股份有限公司」（股份不在名内时才切）；
        #   ③ rstrip 尾 的/之/数字/%。**不截 资产**（存货资产/无形资产 是名一部分）。
        # 实测 2605 material 标题：0 真回退（V0 干净实体 12 例全保住）、G46 可用 +186
        # （1490→1676）、股份有限公司名 27/27 保留（V2 裸切股份会误截）；修 SJSE 长名。
        # G46 子串校验天然兼容过截（更短仍是子串），故优先保证「无尾噪声」而非「最长」。
        m = re.search(r"(?:收购|购买|出售|受让|转让|并购|重组)([一-龥A-Za-z0-9]{2,40})", t)
        if not m:
            return {}
        x = re.sub(r"^(?:股权|股份|资产)?所?涉及[的之]?", "", m.group(1))
        x = re.split(
            r"暨|及|并|股权|股东|股份(?!有限|公司)|"
            r"免于|完成|过户|登记|结果|进展|提示|说明|报告|确认|签署|问询|草案|预案|"
            r"摘要|事项|权益|配套|募集|审计|备考|增资|解禁|复牌|过渡|减值|承诺|投资者|"
            r"签字|更正|询价|核查|法律|自查|预披露|要约|持有|部分|摊薄|召开|解除|终止|"
            r"停牌|意向|协议|框架",
            x, maxsplit=1)[0]
        x = x.rstrip("的之0123456789%")
        return {"target": x} if len(x) >= 2 else {}

    return {}


# ============================================================
# material_subtype 派生（code + label/title → 子类标签，登记表/machine_field 用）
# ============================================================
def derive_material_subtype(code, label, title):
    """返回人类可读 material 子类标签（登记表 surface / signal.material_subtype 用）。

    M4 → 监管类/诉讼；M9 → 境内/境外担保；其余用 label 原文。
    """
    t = title or ""
    if code == "M4":
        sub = m4_subtype_severity(label)
        if sub:
            return sub[0]  # 'regulatory' / 'litigation'
    if code == "M9":
        if re.search(r"境外|海外|海外子公司", t):
            return "境外担保"
        if re.search(r"境内|为.*子公司", t):
            return "境内担保"
    if code == "M11":
        mf = extract_machine_fields("M11", t)
        if mf.get("change"):
            return mf["change"]
    return label or ""


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
    标签值同时供 escalate() 逻辑判断 + m4 §4.2 actor 列 surface（G46 泛型校验须 verbatim 出现）。

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


# ============================================================
# severity 三态升档（actor/金额确认才升；供 announcements[] 渲染）
# ============================================================
def escalate(code, base_severity, machine_fields=None, depth_fields=None, title="", label=""):
    """ST1 actor 级别 → severity 升档（**UP-ONLY**，门禁分级：仅确认实控人时升 critical）。

    10x 统计（59185 条/5775 票）修正的精度门（防关键词误报）：
      · M1 减持 + 实控人 → critical（股权转让/询价转让 base warning → 升 critical；主 label 已 critical 确认）；
      · M2 质押 + 实控人 + **非解押** → critical（解押=利好，regex 排除「解押/解除质押」，M2 解押占 48%）；
      · M9 担保 + 实控人 → critical（境内担保已在 is_material 剔除，余为境外）；
      · major5pct / executive / P1 增持 → **不升**（门禁分级：5%减持重大但非治理变更，靠 m4 actor 列 surface）。

    **UP-ONLY 设计**（保守，勿降级）：actor_tier 未检出(None)→保持 base（主 label 保守留 critical）；
    检出 major5pct/executive→保持 base（透明不门禁）。仅实控人确认才升 critical——稀有但致命，零误报。
    """
    mf = machine_fields or {}
    tier = mf.get("actor_tier") or ""
    is_ctrl = "实控人" in tier            # detect_actor_tier controller 标签
    if not is_ctrl:
        return base_severity              # major5pct/executive/未检出 → 不升（m4 actor 列透明）
    t = title or ""
    if code == "M1":
        return "critical"                 # 实控人减持/股权转让 → critical
    if code == "M2" and not re.search(r"解押|解除质押", t):
        return "critical"                 # 实控人质押（非解押）→ critical
    if code == "M9":
        return "critical"                 # 实控人对外担保（境内已剔）→ critical
    return base_severity
