#!/usr/bin/env python3
"""
skill_dep_graph.py — Skill 依赖图解析器
递归解析 SKILL.md 中所有 '调用/引用/必须加载' 的依赖，输出本次分析必须加载的文件清单。
"""

import os
import re
from pathlib import Path

# Skill 根目录
SKILL_ROOT = Path(os.path.expanduser("~/.hermes/skills/stock-analysis"))

# 已知 Skill 的 SKILL.md 路径
SKILL_PATHS = {
    "stock-orchestrator": SKILL_ROOT / "stock-orchestrator" / "SKILL.md",
    "data-source-registry": SKILL_ROOT / "data-source-registry" / "SKILL.md",
    "financial-data-routing": SKILL_ROOT / "financial-data-routing" / "SKILL.md",
    "stock-analysis-quality": SKILL_ROOT / "stock-analysis-quality" / "SKILL.md",
}

# 模式 → 强制加载的 Skill 列表
MODE_FORCED_SKILLS = {
    "A": [
        "stock-orchestrator",
        "data-source-registry",
        "financial-data-routing",
        "stock-analysis-quality",
    ],
    "B": [
        "stock-orchestrator",
        "data-source-registry",
        "financial-data-routing",
        "stock-analysis-quality",   # B 报告模块 m3/m6/m36/m37/m11 在此仓（2026-08-26 B v2 补）
    ],
}

# 用户问题关键词 → 额外需要的子文件
KEYWORD_TO_FILES = {
    "期货": ["financial-data-routing/references/scenarios/s7-cyclical.md"],
    "商品价格": ["financial-data-routing/references/scenarios/s7-cyclical.md"],
    "铜价": ["financial-data-routing/references/scenarios/s7-cyclical.md"],
    "铝价": ["financial-data-routing/references/scenarios/s7-cyclical.md"],
    "LME": ["financial-data-routing/references/scenarios/s7-cyclical.md"],
    "周期": ["financial-data-routing/references/scenarios/s7-cyclical.md"],
    "订单": ["stock-analysis-quality/references/modules/m25-orders.md"],
    "在手": ["stock-analysis-quality/references/modules/m25-orders.md"],
    "饱和": ["stock-analysis-quality/references/modules/m25-orders.md"],
    "合同负债": ["stock-analysis-quality/references/modules/m25-orders.md"],
    "出海": ["stock-analysis-quality/references/modules/m25-orders.md"],
    "海外": ["stock-analysis-quality/references/modules/m25-orders.md"],
    "关税": ["stock-analysis-quality/references/modules/m25-orders.md"],
    "事件": ["financial-data-routing/references/scenarios/s5-events-18.md"],
    "风险": ["financial-data-routing/references/scenarios/s5-events-18.md"],
    "公告": ["financial-data-routing/references/scenarios/s5-events-18.md"],
    "同业": ["financial-data-routing/references/scenarios/s11-peer.md"],
    "可比": ["financial-data-routing/references/scenarios/s11-peer.md"],
    "对比": ["financial-data-routing/references/scenarios/s11-peer.md"],
    "资金流": ["financial-data-routing/references/scenarios/s3-fund-flow.md"],
    "主力": ["financial-data-routing/references/scenarios/s3-fund-flow.md"],
    "评级": ["financial-data-routing/references/scenarios/s4-rating.md"],
    "目标价": ["financial-data-routing/references/scenarios/s4-rating.md"],
    "北向": ["financial-data-routing/references/scenarios/s3-fund-flow.md"],
    "融资融券": ["financial-data-routing/references/scenarios/s8-a-share.md"],
    # ── 日内低吸定位器（stock-intraday-t-analyzer）：纯技术面日内，独立 skill ──
    "走势": ["stock-intraday-t-analyzer/SKILL.md"],
    "分时": ["stock-intraday-t-analyzer/SKILL.md"],
    "日内": ["stock-intraday-t-analyzer/SKILL.md"],
    "低吸": ["stock-intraday-t-analyzer/SKILL.md"],
    "做T": ["stock-intraday-t-analyzer/SKILL.md"],
    "做t": ["stock-intraday-t-analyzer/SKILL.md"],
}

# 模式 → 需要加载的子文件（两张分表：scenario=拉数面 / module=写作面，混装曾是增删漏温床）
# 条目为 dict；`"load": "deferred"` = JIT 延迟读（不进 Phase 0 强制装载，首次 verify FAIL 才 Read）。
# module 表与 orchestrator SKILL.md Phase 3 JIT 表 / quality SKILL.md 模块表三方一致性
# 由 regression-tests/test_load_set_single_source.py 锁（机制=单源，文档=投影）。
MODE_SCENARIO_FILES = {
    "A": [
        {"path": "financial-data-routing/references/scenarios/s1-financial.md"},
        {"path": "financial-data-routing/references/scenarios/s2-quote-kline.md"},
        {"path": "financial-data-routing/references/scenarios/s3-fund-flow.md"},
        {"path": "financial-data-routing/references/scenarios/s5-events-18.md"},
        {"path": "financial-data-routing/references/scenarios/s7-cyclical.md"},
        {"path": "financial-data-routing/references/scenarios/s8-a-share.md"},
        {"path": "financial-data-routing/references/scenarios/s9-news-peer.md"},
        {"path": "financial-data-routing/references/scenarios/s10-checklist.md"},
        {"path": "financial-data-routing/references/scenarios/s11-peer.md"},
        {"path": "financial-data-routing/references/scenarios/s12-orders.md"},
    ],
    "B": [
        {"path": "financial-data-routing/references/scenarios/s2-quote-kline.md"},
        {"path": "financial-data-routing/references/scenarios/s3-fund-flow.md"},
        {"path": "financial-data-routing/references/scenarios/market-context.md"},
        {"path": "financial-data-routing/references/scenarios/intraday-60min.md"},
    ],
}

# 模式 → 报告模块（quality references/modules；顺序=JIT 表报告章节顺序）
# A = 12 模块 + m11 延迟读；B = 6 模块（m11 依 JIT B 行「同上」延迟读——不入 B 装载集，即其延迟表示）
MODE_MODULE_FILES = {
    "A": [
        {"path": "stock-analysis-quality/references/modules/m12-summary.md"},
        {"path": "stock-analysis-quality/references/modules/m0-classification.md"},
        {"path": "stock-analysis-quality/references/modules/m1-narrative.md"},
        {"path": "stock-analysis-quality/references/modules/m2-financial.md"},
        {"path": "stock-analysis-quality/references/modules/m25-orders.md"},
        {"path": "stock-analysis-quality/references/modules/m3-technical.md"},
        {"path": "stock-analysis-quality/references/modules/m4-sentiment.md"},
        {"path": "stock-analysis-quality/references/modules/m5-valuation.md"},
        {"path": "stock-analysis-quality/references/modules/m6-decision.md"},
        {"path": "stock-analysis-quality/references/modules/m7-risk.md"},
        {"path": "stock-analysis-quality/references/modules/m8-disclaimer.md"},
        {"path": "stock-analysis-quality/references/modules/m10-forecast.md"},
        {"path": "stock-analysis-quality/references/modules/m11-gates.md", "load": "deferred"},
    ],
    "B": [
        {"path": "stock-analysis-quality/references/modules/m38-b-conclusion-head.md"},
        {"path": "stock-analysis-quality/references/modules/m39-b-xq-voice.md"},
        {"path": "stock-analysis-quality/references/modules/m3-technical.md"},
        {"path": "stock-analysis-quality/references/modules/m36-short-term.md"},
        {"path": "stock-analysis-quality/references/modules/m37-positioning.md"},
        {"path": "stock-analysis-quality/references/modules/m6-decision.md"},
    ],
}


def get_keyword_files(user_prompt: str) -> list[str]:
    """根据用户 prompt 中的关键词，返回额外需要加载的子文件"""
    extra_files = set()
    for keyword, files in KEYWORD_TO_FILES.items():
        if keyword in user_prompt:
            for f in files:
                extra_files.add(f)
    return sorted(extra_files)


def resolve_required_files(mode: str, user_prompt: str) -> list[dict]:
    """
    根据模式 + 用户问题，输出本次必须加载的所有文件。

    返回:
    [
        {
            "path": "relative/path/to/file.md",
            "priority": "P0" | "P1",
            "reason": "模式A强制" | "用户提到'期货'" | "场景依赖"
        },
        ...
    ]
    """
    result = []
    seen = set()

    # 1. 模式强制的 Skill 文件
    for skill_name in MODE_FORCED_SKILLS.get(mode, []):
        rel_path = f"{skill_name}/SKILL.md"
        if rel_path not in seen:
            seen.add(rel_path)
            result.append({
                "path": rel_path,
                "priority": "P0",
                "reason": f"模式{mode}强制加载"
            })

    # 2. 模式对应的场景/模块子文件（两分表；dict 条目可带 load=deferred 延迟语义透传）
    for table, dep_label in ((MODE_SCENARIO_FILES, "场景依赖"), (MODE_MODULE_FILES, "模块依赖")):
        for entry in table.get(mode, []):
            if isinstance(entry, str):          # 兼容 str 条目旧写法
                entry = {"path": entry}
            rel_path = entry["path"]
            if rel_path not in seen:
                seen.add(rel_path)
                item = {
                    "path": rel_path,
                    "priority": "P1",
                    "reason": f"模式{mode}{dep_label}",
                }
                if entry.get("load"):
                    item["load"] = entry["load"]
                result.append(item)

    # 3. 用户关键词触发的额外文件
    for rel_path in get_keyword_files(user_prompt):
        # 模式B v2：走势/分时/做T 关键词不再路由 intraday-t-analyzer（B 的 60min 信号已覆盖其职责）
        if mode == "B" and "stock-intraday-t-analyzer" in rel_path:
            continue
        if rel_path not in seen:
            seen.add(rel_path)
            result.append({
                "path": rel_path,
                "priority": "P1",
                "reason": f"用户问题关键词触发"
            })

    return result


def get_mode_profile(mode: str) -> str:
    """模式 → Gate Profile 映射"""
    return {
        "A": "profile_full",
        "B": "profile_quick",
    }.get(mode, "profile_full")
