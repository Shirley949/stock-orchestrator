#!/usr/bin/env python3
"""
verify_data_contracts.py —— 数据契约断言型 CI（S1 实现）

把 gate-audit-20260704/fixtures/dataflow_trace.py（只读 trace）升级为**断言型**校验：
读 lib/data_contracts.py 的 SCENES 注册表，机械化断言「产出↔消费」契约。

S1 生效的校验（plan §3.2）：
  校验 1  无孤儿产出   confirmed produces 必有 consumer              → error
  校验 2  无断链消费   consumer 引用必命中本 scene produces           → error
  校验 6  非 confirmed assumed/unverified 字段逐条列出                → warn
  辅助    consumer tag 形态合法（m/G/R/s/computed_metrics/_EXPECTED） → warn

设计要点：
  - 所有 check_* 接受 scenes 参数（缺省 dc.SCENES），便于反例测试注入伪注册表。
  - 纯 stdlib，无网络、无 runner/gate 运行时副作用（S1 = 零运行时风险）。
  - coverage_only scene（s55）与 consumed=False 字段（priceHighest_52week 等）：
    confirmed 但无 consumer → 降级 warn（已审计的已知死数据，待 S5 处置）。

用法：
    python verify_data_contracts.py            # 校验真实注册表；有 error 退 1
    python verify_data_contracts.py --quiet    # 仅打印 error
    pytest fixtures/test_data_contracts.py     # 反例 + 真实注册表零报错
"""
import os
import re
import sys
from collections import namedtuple

# ---- 导入注册表（同仓库 lib/，与 gate_definitions 同级）----
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "lib"))
import data_contracts as dc

Finding = namedtuple("Finding", ["check", "severity", "scene", "path", "msg"])

# consumer 引用合法 tag 前缀（warn 校验用；tag 形如 "m25:67"/"G26"/"computed_metrics"）
_CONSUMER_TAG_RE = re.compile(
    r"^(m\d+|G\d+|R\d+|s\d+|computed_metrics|_EXPECTED_SCENES)"
)


def _path_matches(cpath, ppath):
    """consumer 路径 cpath 是否匹配 produce 路径 ppath。

    三种合法关系：精确相等 / consumer 更细（读子字段）/ consumer 更粗（读父对象）。
    """
    if cpath == ppath:
        return True
    if cpath.startswith(ppath + "."):
        return True
    if ppath.startswith(cpath + "."):
        return True
    return False


# ============================================================
# 校验 1：无孤儿产出（confirmed produces 必有 consumer）→ error
# ============================================================
def check_no_orphan_produces(scenes=dc.SCENES):
    finds = []
    for sname, entry in scenes.items():
        consumers = entry.get("consumers", {})
        coverage_only = entry.get("coverage_only", False)
        for p in entry.get("produces", []):
            if p.get("confidence") != dc.CONFIRMED:
                continue                       # 仅 confirmed 触发 hard；assumed/unverified 由校验6 warn
            if p.get("consumed") is False:     # 显式已知死字段，豁免
                finds.append(Finding("orphan_produces", "warn", sname, p["path"],
                    f"confirmed 产出显式 consumed=False（{p.get('note', '')}）"))
                continue
            if not any(_path_matches(c, p["path"]) for c in consumers):
                sev = "warn" if coverage_only else "error"
                tail = "（coverage_only scene，待 S5 处置）" if coverage_only else ""
                finds.append(Finding("orphan_produces", sev, sname, p["path"],
                    f"confirmed 产出无任何 consumer{tail}"))
    return finds


# ============================================================
# 校验 2：无断链消费（consumer 引用必命中本 scene produces）→ error
# ============================================================
def check_no_broken_consumers(scenes=dc.SCENES):
    finds = []
    for sname, entry in scenes.items():
        ppaths = [p["path"] for p in entry.get("produces", [])]
        for cpath in entry.get("consumers", {}):
            if not any(_path_matches(cpath, pp) for pp in ppaths):
                finds.append(Finding("broken_consumer", "error", sname, cpath,
                    f"consumer 引用的字段不在本 scene produces 中（produces={ppaths}）"))
    return finds


# ============================================================
# 校验 6：assumed/unverified 字段逐条列出 → warn
# ============================================================
def check_non_confirmed(scenes=dc.SCENES):
    finds = []
    for sname, entry in scenes.items():
        for p in entry.get("produces", []):
            conf = p.get("confidence")
            if conf != dc.CONFIRMED:
                finds.append(Finding("non_confirmed", "warn", sname, p["path"],
                    f"{conf}：{p.get('note', '（待单股真连/mock 验证后升级 confirmed）')}"))
    return finds


# ============================================================
# 辅助：consumer tag 形态合法 → warn
# ============================================================
def check_consumer_tags(scenes=dc.SCENES):
    finds = []
    for sname, entry in scenes.items():
        for cpath, tags in entry.get("consumers", {}).items():
            for tag in tags:
                if not _CONSUMER_TAG_RE.match(tag):
                    finds.append(Finding("consumer_tag", "warn", sname, cpath,
                        f"consumer tag 不匹配已知模式 (m/G/R/s\\d+|computed_metrics|_EXPECTED)：{tag!r}"))
    return finds


# ============================================================
# 校验 3：schema 覆盖（注册表 ⇔ snapshot_schema.md 双向覆盖）→ warn（S2）
# ============================================================
# 用户决策（2026-07-05）：schema 统一用「覆盖 CI」而非「生成替换」——文档保有人工
# type/desc/列子表，CI 仅抓 drift。warn-only（文档非按注册表撰写，初版必有 drift）。
SCHEMA_DOC = os.path.join(_HERE, "..", "..",
                          "stock-analysis-quality", "references", "snapshot_schema.md")

# 顶层 infra 键（非数据 scene）：doc 出现时不计入「未契约化」
_INFRA_TOP = {"mode", "stock_code", "stock_type", "classification", "timestamp",
              "_warnings", "_critical_failure", "_failure_summary"}


def extract_doc_paths(md_text):
    """从 markdown 抽取 snapshot 路径 token：反引号路径 + 标题中的全限定路径。"""
    paths = set()
    for m in re.finditer(r"`([A-Za-z_][\w.\[\]%]*)`", md_text):
        tok = m.group(1)
        if "." in tok or tok in _INFRA_TOP:
            paths.add(tok)
    # 标题中的全限定路径（如 `### s8_a_share.data.shareholder_count.processed`——
    # 该路径常不在表格反引号内，不捕获会让 registry 误报 undocumented）
    for line in md_text.splitlines():
        if line.lstrip().startswith("#"):
            for m in re.finditer(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_][\w\[\]]*)+)", line):
                paths.add(m.group(1))
    return paths


def _load_doc_paths():
    try:
        with open(SCHEMA_DOC, encoding="utf-8") as f:
            return extract_doc_paths(f.read())
    except OSError:
        return None


def check_schema_coverage(scenes=dc.SCENES, doc_paths=None):
    """注册表 produces 路径 ⇔ schema 文档路径双向覆盖（warn）。

    - 注册表路径无文档对应 → 'contracted but undocumented'
    - 文档路径（首段为 scene 名）无注册表对应 → 'documented but not contracted'
    粒度差由 _path_matches 前缀匹配兼容（注册表粗 / 文档细，或反之）。
    """
    finds = []
    if doc_paths is None:
        doc_paths = _load_doc_paths()
    if doc_paths is None:
        finds.append(Finding("schema_coverage", "warn", "*", "*",
            f"无法读取 {SCHEMA_DOC}，跳过 schema 覆盖校验"))
        return finds

    scene_names = set(scenes.keys())
    reg_paths = [(sname, f"{sname}.{p['path']}")
                 for sname, entry in scenes.items() for p in entry.get("produces", [])]

    for sname, rp in reg_paths:                     # (a) 注册表 → 文档
        if not any(_path_matches(dp, rp) for dp in doc_paths):
            finds.append(Finding("schema_coverage", "warn", sname, rp,
                "注册表 produces 路径在 snapshot_schema.md 无对应（contracted but undocumented）"))
    for dp in sorted(doc_paths):                     # (b) 文档 → 注册表（仅 scene 数据路径）
        if dp.endswith(".scene"):                    # 结构性字段（每个 scene 自带），跳过
            continue
        if ".data." not in dp:                       # 散文简写（如 classification.primary_type）非真实路径，跳过
            continue
        head = dp.split(".", 1)[0]
        if head not in scene_names:
            continue
        if not any(_path_matches(dp, rp) for _, rp in reg_paths):
            finds.append(Finding("schema_coverage", "warn", head, dp,
                "snapshot_schema.md 路径在注册表无对应（documented but not contracted）"))
    return finds


# ============================================================
# 校验 7：消费标注 ⇔ declared consumers 双向闭合（向A/向B）→ warn（plan 改动4）
# ============================================================
# 防御性 check：堵「4 环链路跨环交叉校验全缺」——契约层只遍历 SCENES 字典内部（produces⇔consumers
# 本 scene 前缀匹配），从不 grep 模块 .md；gate 层只 G21 认 [src:]（report 级总量，不与 declared 交叉）。
#   向B（actual→declared）：模块 .md 的 [src: snapshot.<X>]，X 不在 SCENES/_INFRA_TOP → warn（抓漏登 scene，classification 式）。
#   向A（declared→actual）：SCENES[s].consumers 的 m-tag，对应 module .md 无该 scene 消费标注 → warn（抓 declared ghost）。
# SOFT warn：向B [src:] 形式规范（0 噪声）；向A 中文/字段名引用匹配有噪声（plan §改动4「先 warn 观察一轮再考虑升 error」）。
MODULES_DIR = os.path.join(_HERE, "..", "..",
                           "stock-analysis-quality", "references", "modules")
_SRC_SNAPSHOT_RE = re.compile(r"\[src:\s*snapshot\.([A-Za-z_][A-Za-z_0-9]*)")


def _load_module_texts():
    """读取 modules/*.md → {module_id: (filename, content)}，module_id 如 'm4'/'m10'/'m25'。"""
    texts = {}
    if not os.path.isdir(MODULES_DIR):
        return texts
    for fn in sorted(os.listdir(MODULES_DIR)):
        if not fn.endswith(".md"):
            continue
        mid = fn.split("-", 1)[0]
        if not re.match(r"^m\d+$", mid):
            continue
        try:
            with open(os.path.join(MODULES_DIR, fn), encoding="utf-8") as f:
                texts[mid] = (fn, f.read())
        except OSError:
            pass
    return texts


def check_src_coverage_actual(scenes=dc.SCENES, module_texts=None):
    """向B：模块 .md 的 [src: snapshot.<X>]，X 不在 SCENES/_INFRA_TOP → warn（抓漏登 scene）。"""
    finds = []
    if module_texts is None:
        module_texts = _load_module_texts()
    if not module_texts:
        finds.append(Finding("src_coverage", "warn", "*", "*",
            f"无法读取 {MODULES_DIR}，跳过 [src:] 覆盖校验"))
        return finds
    scene_names = set(scenes.keys())
    for mid, (fn, content) in module_texts.items():
        for m in _SRC_SNAPSHOT_RE.finditer(content):
            token = m.group(1)
            if token in scene_names or token in _INFRA_TOP:
                continue
            finds.append(Finding("src_coverage", "warn", mid, f"[src: snapshot.{token}]",
                f"模块 {fn} 引用 snapshot.{token} 未在 SCENES/_INFRA_TOP 登记（漏登 scene？）"))
    return finds


def check_declared_consumption(scenes=dc.SCENES, module_texts=None):
    """向A：SCENES[s].consumers 的 m-tag，对应 module .md 无该 scene 消费标注 → warn（抓 declared ghost）。

    匹配宽松：module.md 含 scene 名 OR consumer path 字段段（≥3字符，过滤 data/items 泛词）。
    噪声说明：中文/散文引用可能漏匹配 → warn 表示 declared 与文档 drift，需人工核实（SOFT）。
    """
    finds = []
    if module_texts is None:
        module_texts = _load_module_texts()
    if not module_texts:
        return finds  # 向B 已报读取失败，向A 静默跳过
    seen = set()
    for sname, entry in scenes.items():
        for cpath, tags in entry.get("consumers", {}).items():
            for tag in tags:
                mm = re.match(r"^(m\d+)", tag)
                if not mm:
                    continue
                mid = mm.group(1)
                mt = module_texts.get(mid)
                if mt is None:
                    continue
                key = (sname, mid, cpath)
                if key in seen:
                    continue
                fn, content = mt
                segs = [sname] + [seg for seg in cpath.split(".")
                                  if seg not in ("data", "items") and len(seg) >= 3]
                if not any(seg in content for seg in segs):
                    seen.add(key)
                    finds.append(Finding("declared_consumption", "warn", sname,
                        f"{cpath} ← {tag}",
                        f"declared consumer {tag} 但 {fn} 未见 {sname}/{cpath} 消费标注"
                        f"（declared ghost 或中文/字段名引用误报？）"))
    return finds


# ============================================================
# 汇总
# ============================================================
def all_findings(scenes=dc.SCENES):
    """跑全部校验，返回 Finding 列表（error + warn 混排）。"""
    out = []
    out += check_no_orphan_produces(scenes)
    out += check_no_broken_consumers(scenes)
    out += check_non_confirmed(scenes)
    out += check_consumer_tags(scenes)
    out += check_schema_coverage(scenes)
    out += check_src_coverage_actual(scenes)
    out += check_declared_consumption(scenes)
    return out


def run_all(scenes=dc.SCENES):
    """返回 (errors, warnings) 两个 Finding 列表。测试主入口。"""
    finds = all_findings(scenes)
    errors = [f for f in finds if f.severity == "error"]
    warnings = [f for f in finds if f.severity == "warn"]
    return errors, warnings


def _format(f):
    return f"  [{f.severity.upper():5}] {f.check:<16} {f.scene:<18} {f.path}\n         {f.msg}"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    quiet = "--quiet" in argv
    errors, warnings = run_all()
    print(f"数据契约校验：{len(dc.SCENES)} scenes | "
          f"{len(errors)} error(s) | {len(warnings)} warn(s)")
    if not quiet:
        for f in warnings:
            print(_format(f))
    for f in errors:
        print(_format(f))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
