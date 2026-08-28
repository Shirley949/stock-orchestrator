# -*- coding: utf-8 -*-
"""section_locator —— markdown 报告章节定位器（候选迭代 + 切片验签）。

为什么是独立模块（而非并入 gate_definitions）：gate_definitions.py:20 已
`from capstone_panorama import ...`，capstone_panorama 若反向 import gate_definitions
会成环；两者都需要 capstone 定位（gate 执法 + panorama #7 advisory），共享实现只能
放中立模块。此前双实现（gate_definitions._g30_find_capstone 与
capstone_panorama._find_capstone）违反「同一语义只允许一个实现」硬规则，后者切到
文末无边界、更易劫持。

根治的失效类：定位器「单向取首个匹配 + 无验签」被前置标题劫持（G30 六起：
赛微 Q6「三情景裁决」/ 7.5.1「定性研判」、君正 §11.4「LLM 研判」、唯特偶
4.2「股东行为综合研判」、株冶 3.5.4「±30% 情景」、厦钨 §7.3「研判」——诱饵全是
5 词候选且排在真 capstone 之前）。

设计（G59 候选∪范式 :2574 的推广，差异在验签发生在切片级而非词级）：
  遍历 head_re 的**全部**候选（文档序）→ 取首个切片通过 verify_re（heading 级
  特征子节标题）者 → ok@heading；否则首个过 weak 词（乐观/基准/中性/悲观，模式 B
  无 A 形态子节的兜底）→ ok@weak；否则首个候选（= 旧「取首」语义，兜底保旧）→
  fallback@first；无候选 → no_anchor（调用方决定豁免或显式 FAIL）。

零回归论证：旧语义 = 首个候选；新逻辑的最终兜底即首个候选 → new-PASS ⊇ old-PASS。
26 份归档终态实测逐字节相等、诊断全 ok@heading（2026-08-28 电池 T1）。
"""
import re

# capstone 候选锚 = 现行 _G30_CAPSTONE_HEAD_RE（gate_definitions.py:1157）原样迁移。
# 单向取首是事故根因，词表本身没病——迭代+验签后保留全部候选。
CAPSTONE_HEAD_RE = re.compile(r"^#{1,4}\s.*(?:综合研判|情景|三档|概率|研判)", re.MULTILINE)
# 切片验签（heading 级）：capstone 特征子节标题。词表来源 = 模板契约词
# （m6-decision.md:27/:71/:98 钦定 证据全景/情景-动作矩阵/投资建议）∪ G60 :2624
# 四词表 ∪ _g30_panorama_section :1383 三词表。26 份语料实测真 capstone 切片内
# 特征子节数 min=1（芯碁微装 688630 整份无「证据全景」字样靠其余词兜住）max=4。
# 必须 heading 级（^#+ 行首锚）而非子串：T9a 反例——诱饵散文含「投资建议」会误过验签。
CAPSTONE_FEAT_RE = re.compile(
    r"^#{1,4}\s.*(?:证据全景|证据盘点|证据矩阵|全景|情景[-－—]?动作矩阵|情景矩阵|投资建议|观察清单)",
    re.MULTILINE)
# 弱验签（切片含情景 label 词即可信）：模式 B capstone（「## 九、m6 综研判定」无 A
# 形态子节标题）靠它过；A 语料 26/26 + 模式 B 特变电工均命中。
CAPSTONE_WEAK = ("乐观", "基准", "中性", "悲观")


def slice_of(report: str, m) -> str:
    """从匹配标题切到下一个同级/更高级标题或 '\\n---\\n'（算法 = 原
    gate_definitions._module_section :1204-1224 切片段，单一实现收编于此）。
    不在 #### 子标题截断（level-aware），让消费方读到模块全部子节。"""
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

    diagnosis 四态：
      ok@heading     首个过 heading 级验签的候选（健康路径）
      ok@weak        无候选过 heading 验签，首个含 weak 词（模式 B 正常形态）
      fallback@first 全部验签失败，退回首个候选（= 旧取首语义；调用方应上浮
                     「定位层异常」reason——疑似劫持或模板漂移）
      no_anchor      无任何候选（调用方决定豁免或显式 FAIL，替代旧静默全文回退）
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
