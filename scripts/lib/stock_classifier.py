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
        "board_keywords": ["有色金属", "钢铁", "煤炭", "石油石化", "基础化工", "建筑材料"],
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
        # 不含裸"电力"：电力设备 board=新能源(电池/光伏/硅料)属成长股，会与成长股"电力设备"冲突
        # 且因 dict 插入序在成长股之前而抢先误判（301217铜冠铜箔/300750宁德/002129中环/601012隆基 全中招）。
        # 真防御电力（水电/火电/核电，board="公用事业-电力-*"）靠"公用事业"命中。
        # 22+11票验证(2026-07-22)：删"电力"修上述误判，长江/华能/广核/川投等真防御零回归。
        # + "铁路公路"：board L2（"交通运输-铁路公路-铁路运输/高速公路"）→ 大秦铁路/京沪高铁/高速
        #   归防御（稳定现金流+分红）。窄化的是 board L2 而非"交通运输" keyword——后者保留供
        #   航运(中远海控)/航空(中国国航)/港口(上港集团)走 Step2 csrc→周期，互不干扰。
        #   验证(2026-07-22)：大秦铁路→防御，中远海控/国航/上港仍周期零回归。
        "board_keywords": ["公用事业", "环保", "铁路公路"],
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

    # Step 5: 无法分类，返回 None 强制走 LLM
    # 修正 E: 不再默认消费股，让 LLM 判断
    return {
        "primary_type": None,
        "confidence": 0.0,
        "evidence": {
            "source": "no_match",
            "value": f"board={board}, csrc={csrc}",
            "matched_rule": "无匹配，需要 LLM 判断",
        },
        "warnings": ["规则无法分类，需要 LLM 兜底"],
    }


def classify_stock(stock_code: str) -> dict:
    """
    股票分类主入口。三级降级：
    1. 东财 datacenter API → BOARD_NAME_LEVEL 规则分类
    2. AkShare stock_individual_info_em → 东财分类（非申万）
    3. 返回 None 强制 LLM 兜底

    返回格式:
    {
      "primary_type": "周期股|成长股|消费股|金融股|防御股|多元化控股|None",
      "confidence": 0.0-1.0,
      "evidence": {"source": "...", "value": "...", "matched_rule": "..."},
      "warnings": ["..."],
      "raw_facts": {"industry_csrc": "...", "board_name_level": "...", ...}
    }
    """
    # Step 1: 拉取事实（东财 datacenter）
    facts = fetch_org_info(stock_code)
    if facts.get("status") != "ok":
        # Tier 2: 尝试 AkShare
        facts = _fetch_via_akshare(stock_code)

    if facts.get("status") != "ok":
        # 全部失败，返回 None 强制 LLM
        return {
            "primary_type": None,
            "confidence": 0.0,
            "evidence": {
                "source": "all_failed",
                "value": f"行业数据拉取失败: {facts.get('error', 'unknown')}",
                "matched_rule": "数据不可用，需要 LLM 判断",
            },
            "warnings": [f"行业数据拉取失败: {facts.get('error', '')}"],
            "raw_facts": facts,
        }

    # Step 2: 规则分类
    result = classify_by_rules(facts)
    result["raw_facts"] = facts
    return result


# ============================================================
# 分类属性派生（C2：m0 分类表 → 静态属性，单一真相源）
# ============================================================
# 从 primary_type 机械派生（不需 LLM，对齐 m0-classification.md 分类表）。
# 这些字段让 G37/估值 gate/m1 都从 snapshot.classification 单源读，消除 product_industry_alignment
# 重叠分类与 flaky momentum 依赖。preferred_macro 限定为 s6_macro 实际有的 {PPI, M2, PMI}。
# 混合型(is_mixed/secondary_type) 不在此处设——由 runner C3 overlay 在 segment_composition 到手后判定。
_TYPE_DERIVATION = {
    "周期股": {"macro_sensitivity": "high",   "preferred_macro": "PPI", "valuation_framework": "PB/EV-EBITDA/股息率", "forbidden_metric": "PE做主要", "is_cyclic": True,  "is_financial": False},
    "成长股": {"macro_sensitivity": "medium", "preferred_macro": "PMI", "valuation_framework": "PS/PEG/DCF",         "forbidden_metric": "PB做主要", "is_cyclic": False, "is_financial": False},
    "消费股": {"macro_sensitivity": "low",    "preferred_macro": None,  "valuation_framework": "ROE/品牌溢价",        "forbidden_metric": None,       "is_cyclic": False, "is_financial": False},
    "金融股": {"macro_sensitivity": "high",   "preferred_macro": "M2",  "valuation_framework": "PB/不良率/ROE",        "forbidden_metric": "PE做主要", "is_cyclic": False, "is_financial": True},
    "防御股": {"macro_sensitivity": "low",    "preferred_macro": None,  "valuation_framework": "股息率/现金流",       "forbidden_metric": None,       "is_cyclic": False, "is_financial": False},
    "多元化控股": {"macro_sensitivity": "medium", "preferred_macro": None, "valuation_framework": "分部估值/NAV",     "forbidden_metric": None,       "is_cyclic": False, "is_financial": False},
}


def enrich_classification(classification: dict | None) -> dict | None:
    """从 primary_type 静态派生 macro_sensitivity/preferred_macro/valuation_framework/
    forbidden_metric/is_cyclic/is_financial（加法式，setdefault 不覆盖已有/overlay 已设字段）。

    None 输入（用户 CLI 显式传 stock_type 时 classification 为 None）→ 原样返回 None。
    混合型属性(is_mixed/secondary_type)由 runner C3 overlay 后续设置。
    """
    if not classification or not classification.get("primary_type"):
        return classification
    deriv = _TYPE_DERIVATION.get(classification["primary_type"])
    if not deriv:
        return classification
    for k, v in deriv.items():
        classification.setdefault(k, v)
    return classification


def _fetch_via_akshare(stock_code: str) -> dict:
    """Tier 2: 通过 AkShare 获取个股信息"""
    try:
        import akshare as ak
        info = ak.stock_individual_info_em(symbol=stock_code)
        if info is not None and not info.empty:
            # 转换为 dict
            info_dict = {}
            for _, row in info.iterrows():
                key = row.iloc[0] if len(row) > 0 else ""
                val = row.iloc[1] if len(row) > 1 else ""
                info_dict[str(key)] = str(val)

            # 提取行业字段
            industry = info_dict.get("行业", "")
            return {
                "status": "ok",
                "industry_csrc": industry,
                "board_name_level": industry,  # AkShare 返回的是东财分类
                "em2016": industry,
                "main_business": info_dict.get("主营业务", ""),
                "name": info_dict.get("股票简称", ""),
            }
        return {"status": "failed", "error": "AkShare 返回空"}
    except Exception as e:
        return {"status": "failed", "error": f"AkShare: {str(e)[:200]}"}


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
