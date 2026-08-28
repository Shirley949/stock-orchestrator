# -*- coding: utf-8 -*-
"""section_locator —— markdown 报告章节定位器（候选迭代 + 切片验签）。

独立模块原因：gate_definitions 已 import capstone_panorama，反向委托成环；
两侧都需要 capstone 定位，共享实现只能放中立模块。

locate 契约：遍历 head_re 全部候选（文档序）→ 首个切片过 verify_re（heading 级）
→ ok@heading；否则首个含 weak 词 → ok@weak；否则首个候选（= 旧取首语义）→
fallback@first；无候选 → no_anchor。最终兜底即旧语义 ⇒ new-PASS ⊇ old-PASS
（26 份归档实测切片逐字节相等）。
"""
import re

# 候选锚（原 _G30_CAPSTONE_HEAD_RE 词表；单向取首是事故根因，词表本身没病）
CAPSTONE_HEAD_RE = re.compile(r"^#{1,4}\s.*(?:综合研判|情景|三档|概率|研判)", re.MULTILINE)
# 切片验签：capstone 特征子节标题（模板契约词 m6-decision.md:27/:71/:98 ∪ G60 词表）。
# 必须 heading 级而非子串——诱饵散文含「投资建议」不得过验签。
CAPSTONE_FEAT_RE = re.compile(
    r"^#{1,4}\s.*(?:证据全景|证据盘点|证据矩阵|全景|情景[-－—]?动作矩阵|情景矩阵|投资建议|观察清单)",
    re.MULTILINE)
# 弱验签：模式 B capstone 无 A 形态子节标题，靠情景 label 词兜底
CAPSTONE_WEAK = ("乐观", "基准", "中性", "悲观")


def slice_of(report: str, m) -> str:
    """从匹配标题切到下一个同级/更高级标题或 '\\n---\\n'（level-aware，
    不在 #### 子标题截断）。"""
    hm = re.match(r"^(#+)", report[m.start():m.end()])
    lvl = len(hm.group(1)) if hm else 4
    rest = report[m.end():]
    stop = len(rest)
    for h in re.finditer(r"^(#{1,4})\s+\S", rest, re.MULTILINE):
        if len(h.group(1)) <= lvl:
            stop = h.start()
            break
    dm = re.search(r"\n---\s*\n", rest[:stop])
    if dm:
        stop = min(stop, dm.start())
    return report[m.start():m.end() + stop]


def locate(report: str, head_re=CAPSTONE_HEAD_RE, verify_re=CAPSTONE_FEAT_RE,
           weak=CAPSTONE_WEAK):
    """候选迭代 + 切片验签定位。返回 (section, diagnosis)。

    diagnosis：
      ok@heading / ok@weak        健康路径（weak=模式 B 形态）
      fallback@first              全部验签失败退回旧取首语义；调用方上浮「定位层」reason
      no_anchor                   无候选；调用方决定豁免或显式 FAIL（替代旧静默全文回退）
    """
    ms = list(head_re.finditer(report))
    if not ms:
        return report, "no_anchor"
    weak_fb = None
    first = None
    for m in ms:
        sl = slice_of(report, m)
        if first is None:
            first = (sl, m)
        if verify_re.search(sl):
            return sl, "ok@heading"
        if weak and weak_fb is None and any(w in sl for w in weak):
            weak_fb = (sl, m)
    if weak_fb:
        return weak_fb[0], "ok@weak"
    return first[0], "fallback@first"
