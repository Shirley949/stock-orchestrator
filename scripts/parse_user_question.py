#!/usr/bin/env python3
"""
parse_user_question.py — 两段式用户问题 → 数据需求映射
Stage 1: 关键词映射表（覆盖 80% 高频问题）
Stage 2: LLM 兜底标记（覆盖剩余 20%，由主线程 Claude 执行）

输出: JSON 格式的映射结果，供 generate_checklist.py 消费
"""

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
MAP_FILE = SCRIPT_DIR / "lib" / "question_to_data_map.json"


def load_mapping_rules():
    """加载关键词映射表"""
    with open(MAP_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["rules"]


def segment_user_prompt(user_prompt: str) -> list[str]:
    """
    将用户 prompt 拆解为多个子问题。
    按逗号、分号、句号、"而且"、"另外"、"同时"、"以及" 分割。
    如果拆不出多个子问题，则整段作为一个子问题。
    """
    separators = r"[,;，；。]|而且|另外|同时|以及|还有|并且"
    segments = re.split(separators, user_prompt)
    segments = [s.strip() for s in segments if s.strip()]
    return segments if segments else [user_prompt.strip()]


def match_segment_to_rules(segment: str, rules: list[dict]) -> list[dict]:
    """
    Stage 1: 对单个子问题做关键词匹配。
    返回匹配到的规则列表（一个子问题可能匹配多条规则）。
    """
    matched = []
    segment_lower = segment.lower()
    for rule in rules:
        for kw in rule["keywords"]:
            if kw.lower() in segment_lower:
                matched.append(rule)
                break  # 一条规则只需命中一个关键词
    return matched


def deduplicate_matches(all_matches: list[dict]) -> list[dict]:
    """去重：同一规则可能被多个子问题命中，只保留一次"""
    seen = set()
    deduped = []
    for match in all_matches:
        key = match["data_needs"]
        if key not in seen:
            seen.add(key)
            deduped.append(match)
    return deduped


def parse_user_question(user_prompt: str) -> dict:
    """
    两段式解析入口。

    返回:
    {
        "segments": ["子问题1", "子问题2", ...],
        "matched": [
            {
                "segment": "原始子问题",
                "data_needs": "需要的数据",
                "api_sources": ["API1", "API2"],
                "related_skills": ["skill_path"],
                "modules": ["m2"],
                "priority": "P0",
                "source": "mapping_table"
            },
            ...
        ],
        "unmapped": [
            {
                "segment": "未匹配的子问题",
                "reason": "关键词映射表无匹配",
                "action": "LLM兜底：请Claude判断此子问题需要什么数据和API"
            },
            ...
        ],
        "llm_fallback_prompt": "给Claude的兜底提示（仅当unmapped非空时生成）"
    }
    """
    rules = load_mapping_rules()
    segments = segment_user_prompt(user_prompt)

    matched_segments = []
    unmapped_segments = []

    for segment in segments:
        rules_matched = match_segment_to_rules(segment, rules)
        if rules_matched:
            for rule in rules_matched:
                matched_segments.append({
                    "segment": segment,
                    "data_needs": rule["data_needs"],
                    "api_sources": rule["api_sources"],
                    "related_skills": rule.get("related_skills", []),
                    "modules": rule.get("modules", []),
                    "priority": rule.get("priority", "P1"),
                    "source": "mapping_table"
                })
        else:
            unmapped_segments.append(segment)

    # 去重
    matched_segments = deduplicate_matches(matched_segments)

    # 构建 LLM 兜底提示
    llm_fallback_prompt = None
    unmapped_result = []
    if unmapped_segments:
        unmapped_result = [
            {"segment": s, "reason": "关键词映射表无匹配", "action": "LLM兜底"}
            for s in unmapped_segments
        ]
        llm_prompt_parts = [
            "以下用户子问题未被关键词映射表覆盖，请判断每个子问题需要什么数据和 API。",
            "按 stock-analysis-quality 模块结构，输出 JSON 格式。",
            "",
            "格式要求：",
            '```json',
            '[{"segment": "子问题", "data_needs": "需要的数据", "api_sources": ["API"], "modules": ["模块ID"]}]',
            "```",
            "",
            "未匹配的子问题：",
        ]
        for i, s in enumerate(unmapped_segments, 1):
            llm_prompt_parts.append(f"{i}. {s}")
        llm_fallback_prompt = "\n".join(llm_prompt_parts)

    return {
        "segments": segments,
        "matched": matched_segments,
        "unmapped": unmapped_result,
        "llm_fallback_prompt": llm_fallback_prompt,
    }


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="两段式用户问题 → 数据需求映射")
    parser.add_argument("--user-prompt", required=True, help="用户的原始分析请求")
    parser.add_argument("--output", help="输出 JSON 文件路径（默认 stdout）")
    args = parser.parse_args()

    result = parse_user_question(args.user_prompt)

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"✅ 映射结果已写入 {args.output}")
        print(f"   匹配: {len(result['matched'])} 条 | 未匹配: {len(result['unmapped'])} 条")
        if result['unmapped']:
            print(f"   ⚠️  {len(result['unmapped'])} 条需要 LLM 兜底解析")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
