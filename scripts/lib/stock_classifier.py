#!/usr/bin/env python3
"""
stock_classifier.py — 股票分类器（PR 9）

基于可验证事实做股票分类，消除"医药当周期股"的分类 bug。
三层约束：
  1. 输入必须是可验证事实（东财 API 返回的行业/主营业务）
  2. 规则优先，LLM 兜底
  3. 输出必须带 evidence（引用哪个事实做判断）

用法:
  from stock_classifier import classify_stock
  result = classify_stock("601607")
  # {"primary_type": "消费股", "confidence": 0.9, "evidence": {...}}
"""

import json
import subprocess
import sys
from pathlib import Path

# 东财 datacenter API: 个股基本信息
_ORGINFO_URL = (
    "https://datacenter.eastmoney.com/securities/api/data/v1/get"
    "?reportName=RPT_F10_BASIC_ORGINFO"
    "&columns=SECUCODE,SECURITY_NAME_ABBR,INDUSTRYCSRC1,BOARD_NAME_LEVEL,"
    "EM2016,MAIN_BUSINESS,BUSINESS_SCOPE"
    "&filter=(SECUCODE=%22{secucode}%22)"
    "&pageNumber=1&pageSize=1&source=SECURITIES&client=PC"
)

# 申万行业关键词 → 股票类型映射
SWL_RULES = {
    "周期股": {
        "keywords": [
            "有色金属", "钢铁", "煤炭", "化工", "航运", "工程机械",
            "石油", "天然气", "稀土", "锂", "铜", "铝", "黄金",
            "建筑装饰", "建筑材料", "基础化工", "交通运输",
        ],
        "board_keywords": ["有色金属", "钢铁", "煤炭", "石油石化", "基础化工"],
    },
    "金融股": {
        "keywords": ["银行", "保险", "证券", "多元金融", "信托", "期货"],
        "board_keywords": ["银行", "非银金融", "证券", "保险"],
    },
    "消费股": {
        "keywords": [
            "食品饮料", "白酒", "啤酒", "乳制品", "调味品",
            "家电", "纺织服饰", "美容护理", "医美", "旅游",
            "酒店", "餐饮", "零售", "商贸", "医药", "中药",
            "生物制品", "医疗器械", "化学制药",
        ],
        "board_keywords": [
            "食品饮料", "家用电器", "纺织服饰", "美容护理",
            "社会服务", "商贸零售", "医药生物",
        ],
    },
    "防御股": {
        "keywords": ["电力", "水务", "燃气", "高速公路", "铁路", "环保", "公用事业"],
        "board_keywords": ["公用事业", "电力", "环保"],
    },
    "成长股": {
        "keywords": [
            "半导体", "新能源", "光伏", "锂电", "计算机", "软件",
            "通信", "电子", "军工", "国防", "航空航天", "人工智能",
            "游戏", "传媒", "互联网",
        ],
        "board_keywords": [
            "电子", "计算机", "通信", "国防军工", "电力设备",
            "传媒", "汽车",
        ],
    },
}

# 多元化控股检测关键词
CONGLOMERATE_KEYWORDS = [
    "控股", "集团", "投资", "多元化", "综合",
]


def _to_secucode(stock_code: str) -> str:
    """将股票代码转换为东财 secucode 格式"""
    if stock_code.startswith("0") and len(stock_code) == 5:
        return f"{stock_code}.HK"
    elif stock_code.startswith("6"):
        return f"{stock_code}.SH"
    else:
        return f"{stock_code}.SZ"


def fetch_org_info(stock_code: str) -> dict:
    """从东财 datacenter 获取个股基本信息（行业/主营业务）"""
    secucode = _to_secucode(stock_code)
    url = _ORGINFO_URL.format(secucode=secucode)

    try:
        result = subprocess.run(
            ["curl", "-s", "--connect-timeout", "10", "-m", "15",
             "-H", "User-Agent: Mozilla/5.0", url],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {"status": "failed", "error": "curl 返回空"}

        data = json.loads(result.stdout)
        if data.get("result") and data["result"].get("data"):
            row = data["result"]["data"][0]
            return {
                "status": "ok",
                "industry_csrc": row.get("INDUSTRYCSRC1", ""),
                "board_name_level": row.get("BOARD_NAME_LEVEL", ""),
                "em2016": row.get("EM2016", ""),
                "main_business": row.get("MAIN_BUSINESS", ""),
                "business_scope": row.get("BUSINESS_SCOPE", ""),
                "name": row.get("SECURITY_NAME_ABBR", ""),
            }
        return {"status": "failed", "error": "无数据"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


def classify_by_rules(facts: dict) -> dict:
    """
    基于规则的分类。规则优先级：
    1. BOARD_NAME_LEVEL（东财行业分类，最可靠）
    2. INDUSTRYCSRC1（证监会行业分类）
    3. MAIN_BUSINESS（主营业务关键词）
    """
    board = facts.get("board_name_level", "") or ""
    csrc = facts.get("industry_csrc", "") or ""
    business = facts.get("main_business", "") or ""
    combined_text = f"{board} {csrc} {business}"

    # Step 1: 基于 BOARD_NAME_LEVEL 匹配
    for stock_type, rules in SWL_RULES.items():
        for kw in rules["board_keywords"]:
            if kw in board:
                return {
                    "primary_type": stock_type,
                    "confidence": 0.95,
                    "evidence": {
                        "source": "BOARD_NAME_LEVEL",
                        "value": board,
                        "matched_rule": kw,
                    },
                }

    # Step 2: 基于 INDUSTRYCSRC1 匹配
    for stock_type, rules in SWL_RULES.items():
        for kw in rules["keywords"]:
            if kw in csrc:
                return {
                    "primary_type": stock_type,
                    "confidence": 0.90,
                    "evidence": {
                        "source": "INDUSTRYCSRC1",
                        "value": csrc,
                        "matched_rule": kw,
                    },
                }

    # Step 3: 基于 MAIN_BUSINESS 关键词匹配
    for stock_type, rules in SWL_RULES.items():
        for kw in rules["keywords"]:
            if kw in business:
                return {
                    "primary_type": stock_type,
                    "confidence": 0.80,
                    "evidence": {
                        "source": "MAIN_BUSINESS",
                        "value": business[:100],
                        "matched_rule": kw,
                    },
                }

    # Step 4: 多元化控股检测
    for kw in CONGLOMERATE_KEYWORDS:
        if kw in board or kw in business:
            return {
                "primary_type": "多元化控股",
                "confidence": 0.75,
                "evidence": {
                    "source": "BOARD_NAME_LEVEL+MAIN_BUSINESS",
                    "value": f"board={board}, business含'{kw}'",
                    "matched_rule": kw,
                },
            }

    # Step 5: 无法分类，返回低置信度
    return {
        "primary_type": "消费股",  # 默认消费股（宁多勿少）
        "confidence": 0.40,
        "evidence": {
            "source": "default",
            "value": f"board={board}, csrc={csrc}",
            "matched_rule": "无匹配，使用默认",
        },
        "warnings": ["分类置信度低，建议人工确认"],
    }


def classify_stock(stock_code: str) -> dict:
    """
    股票分类主入口。

    返回格式:
    {
      "primary_type": "周期股|成长股|消费股|金融股|防御股|多元化控股",
      "confidence": 0.0-1.0,
      "evidence": {"source": "...", "value": "...", "matched_rule": "..."},
      "warnings": ["..."],
      "raw_facts": {"industry_csrc": "...", "board_name_level": "...", ...}
    }
    """
    # Step 1: 拉取事实
    facts = fetch_org_info(stock_code)
    if facts.get("status") != "ok":
        # 拉取失败，返回低置信度默认分类
        return {
            "primary_type": "消费股",
            "confidence": 0.30,
            "evidence": {
                "source": "fallback",
                "value": f"行业数据拉取失败: {facts.get('error', 'unknown')}",
                "matched_rule": "数据不可用，使用默认",
            },
            "warnings": [f"行业数据拉取失败: {facts.get('error', '')}"],
            "raw_facts": facts,
        }

    # Step 2: 规则分类
    result = classify_by_rules(facts)
    result["raw_facts"] = facts
    return result


# ============================================================
# CLI 测试入口
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python stock_classifier.py <stock_code>")
        print("示例: python stock_classifier.py 601607")
        sys.exit(1)

    code = sys.argv[1]
    result = classify_stock(code)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
