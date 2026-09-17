#!/usr/bin/env python3
"""
generate_checklist.py — 执行清单生成器（机制 1）
Phase 0 第一步必须调用，输出本次任务的完整执行清单。

功能：
1. 解析用户问题 → 两段式映射（映射表 80% + LLM 兜底 20%）
2. 匹配模式 + 展开 Phase
3. 解析 Skill 依赖图 → 输出必须加载文件清单
4. 生成可勾选 Markdown → 每步前面有 [ ]，后面有 <!--check_id:X--> 标记

用法:
  python generate_checklist.py \
    --user-prompt "深度分析沃尔核材002130，重点看期货成本和订单" \
    --stock-codes "002130" \
    --mode A \
    --output /tmp/analysis_checklist_002130_modeA_20260612_1030.md
"""

import argparse
import json
import os
import sys
import re
from datetime import datetime
from pathlib import Path

# 添加 lib 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from skill_dep_graph import resolve_required_files, get_mode_profile
from parse_user_question import parse_user_question


# ============================================================
# 模式判定（从 orchestrator SKILL.md 提取的规则）
# ============================================================

def detect_mode(user_prompt: str) -> str:
    """根据用户 prompt 自动判定分析模式。只支持 A/B 两种模式。

    优先级（2026-08-26 v2 重排，模式B深度重构 P1）：
      显式模式B > 显式模式A > B 时间窗/走势操作词 > A-strong（深度/整体/财报/全面）> 普通 A > 默认 A
    「帮我看看」降为普通 A 词（原 a_strong 截胡导致「帮我看看最近几天走势」误判 A）。
    """
    # 显式模式声明最高优先
    if "模式B" in user_prompt or "模式b" in user_prompt or "只看技术面" in user_prompt or "只看技术" in user_prompt:
        return "B"
    if "模式A" in user_prompt or "模式a" in user_prompt:
        return "A"

    # B 时间窗词（短期视野）+ 走势操作词（当日/短线操作语义）
    b_time_words = ["今天", "明天", "后天", "本周内", "本周", "近日", "最近几天",
                    "短期", "短线", "接下来几天", "未来几天", "几天内", "当日", "盘中", "尾盘"]
    b_action_words = sorted([
        "今天买不买", "要不要卖", "当日操作", "盘中建议", "还会跌", "还会涨",
        "会不会涨", "会不会反弹", "能不能买", "现在买", "现在卖",
        "现在能买吗", "现在能加仓吗", "要不要减仓", "能加仓",
        "加仓", "减仓", "做T", "做t", "低吸", "高抛", "抄底", "止盈",
        "止损位", "止损", "支撑位", "压力位", "支撑", "压力", "现价",
        "涨还是跌", "走势",
    ], key=len, reverse=True)
    has_b_time = any(w in user_prompt for w in b_time_words)
    has_b_action = any(w in user_prompt for w in b_action_words)
    # 走势词自带短期语义；时间窗词需叠加操作/走势词避免「今天的年报」误判
    if any(w in user_prompt for w in b_action_words):
        return "B"
    if has_b_time and any(w in user_prompt for w in ["走势", "涨", "跌", "买", "卖", "反弹", "加仓", "减仓"]):
        return "B"

    # A-strong（仅四词；「帮我看看」已降级）
    a_strong_triggers = ["深度分析", "整体分析", "财报分析", "全面分析"]
    for trigger in a_strong_triggers:
        if trigger in user_prompt:
            return "A"

    # 普通 A 词
    mode_a_triggers = sorted([
        "值不值得买", "分析一下", "帮我看看", "怎么样",
        "买不买", "估值", "分析", "看看",
        "有没有风险", "最近有什么公告", "事件扫描", "有没有雷", "风险", "事件",
        "估值多少", "贵不贵", "PE多少", "股息", "分红", "长期", "价值",
    ], key=len, reverse=True)
    for trigger in mode_a_triggers:
        if trigger in user_prompt:
            return "A"

    return "A"  # 默认模式 A（宁多勿少）


def extract_stock_codes(user_prompt: str) -> list[str]:
    """从用户 prompt 中提取股票代码"""
    # 6 位数字代码（支持中文紧邻、空格、标点等多种边界）
    codes = re.findall(r'(?:^|[^\d])(\d{6})(?:[^\d]|$)', user_prompt)
    # 也支持中文名+代码紧邻的情况（如"沃尔核材002130"）
    codes2 = re.findall(r'[一-鿿](\d{6})', user_prompt)
    # SH/SZ 前缀
    prefixed = re.findall(r'(?:SH|SZ|sh|sz)[.\s]?(\d{6})', user_prompt)
    # .SS/.SZ 后缀
    suffixed = re.findall(r'(\d{6})\.(?:SS|SZ|ss|sz)', user_prompt)
    all_codes = list(set(codes + codes2 + prefixed + suffixed))
    return all_codes


# ============================================================
# Phase 步骤定义
# ============================================================

PHASE_STEPS = {
    "A": {
        "phase_0": [
            {"id": "c01", "desc": "Skills 全部加载（orchestrator + routing + registry + quality）"},
            {"id": "c02", "desc": "用户问题映射表已生成（见下方）"},
            {"id": "c03", "desc": "必须加载文件清单已确认"},
            {"id": "c04", "desc": "运行 routing/runner.py A <stock_code> → 拉取全量数据 snapshot（⚠️ 必须 > file 重定向，禁止 | head/tail pipe截断）"},
            {"id": "c04b", "desc": "错码前置核对：runner stderr 的 [verify] stock_code=…→stock_name=… × 任务书代码/公司名逐一比对；snapshot --list 头部 code= 同比——不一致立即停（错码会跑完全量拉取落盘后才暴露，白跑一次）"},
            {"id": "c05", "desc": "订单数据：snapshot 已含合同负债(balance_sheet)+分地区(segment_composition)+中标事件(s5 contract)，见 m25"},
            {"id": "c06", "desc": "检查 runner._warnings → 处理降级/失败项"},
        ],
        "phase_1": [
            {"id": "c10", "desc": "runner 返回的实时行情数据确认", "agent": 1},
            {"id": "c11", "desc": "runner 返回的资金流向数据确认", "agent": 1},
            {"id": "c12", "desc": "降级链验证：检查 runner._warnings 中的降级项", "agent": 1},
            {"id": "c13", "desc": "runner 返回的财务三表数据确认（8季度）", "agent": 2},
            {"id": "c14", "desc": "runner 返回的合同负债趋势确认", "agent": 2},
            {"id": "c15", "desc": "提取扣非净利润（从 runner snapshot）", "agent": 2},
            {"id": "c_analyst_forecast", "desc": "机构盈利预测已提取并展示（EPS/PE/评级分布）", "agent": 2},
            {"id": "c16", "desc": "读 risk_signals.processed（M 风险/P 利好信号，公告大全编码）→ Claude 研判重大事件", "agent": 3},
            {"id": "c17", "desc": "runner 返回的公告标题 → Claude 筛选中标/重大合同", "agent": 3},
            {"id": "c18", "desc": "snapshot 海外派生（D6_geo_revenue + segment_composition.geo）确认 + Claude 判断间接出海", "agent": 4},
            {"id": "c19", "desc": "同业对比 s11_peer 由 runner mode A 东财行业自动注入（fetch_peer_comparison_em 自动发现 peer，无需单独命令）；确认在位 → m5§5.2 消费 items[].metrics 并 [src: snapshot.s11_peer]，G15 校验核心6计数", "agent": 4},
            {"id": "c19b", "desc": "Claude 判断期货品种（如用户提到期货）", "agent": 4},
        ],
        "phase_1_skipped": [
            {"id": "c_skip_irm", "desc": "❌ Layer 1 互动易（永久跳过，不可程序化）"},
            {"id": "c_skip_dev", "desc": "❌ Layer 2 设备/产能（永久跳过，需人工）"},
            {"id": "c_skip_demand", "desc": "❌ Layer 4-B 步骤1 全球需求基数（永久跳过）"},
        ],
        "phase_2": [
            {"id": "c50", "desc": "收单清单 12 项全部勾选（来自 runner s10_checklist）"},
            {"id": "c50b", "desc": "视图认知重建：snapshot_view --list（合法视图以 --list 输出为准——❌未挂载视图勿引用；凭记忆写视图名/写非法视图名 exit 2 是 fumble 主源，命令见下方 Runner 调用命令块）"},
            {"id": "c51", "desc": "缺失项已在'分析局限性'标注"},
        ],
        "phase_3": [
            {"id": "c60", "desc": "m0 分类：① 读 modules/m0-classification.md → ② $SV any classification --depth 1（≤0.9K）→ ③ Edit 报告 append『## 一、标的分类与分析框架』→ ④ $VG --section '一、标的分类' → ⑤ 勾[x]（磁盘为准）"},
            {"id": "c_m1", "desc": "m1 公司概览与叙事：① 读 modules/m1-narrative.md → ② $SV --raw xq_market_voice.data.answers.d1_intel（可选辅证 ≤0.7K）→ ③ append『## 二、公司概况』→ ④ $VG --section '二、公司概况' → ⑤ 勾[x]"},
            {"id": "c61", "desc": "m2 财务（含扣非+利润归因+现金流）：① 读 modules/m2-financial.md → ② $SV cash_flow + income + balance + mainfina（四视图 ≤9.6K；FCF=本章全表现算 CFO−Capex，无 --field 依赖）→ ③ append『## 三、财务分析』章体（至 §3.9）→ ④ $VG --section '三、财务分析' → ⑤ 勾[x]"},
            {"id": "c_d2_safety", "desc": "m2.10 资产安全检查（货币资金 vs 有息负债 + 商誉）：① 读 modules/m2-financial.md（同章续写，compact 后重读合法）→ ② 无新拉取（复用 c61 四视图在册投影）→ ③ append『### 3.10 资产安全检查』→ ④ $VG --section '3.10' → ⑤ 勾[x]"},
            {"id": "c_d3_growth", "desc": "m2.11 行业位置与成长性（行业景气 + 份额 + 研发）：① 读 modules/m2-financial.md → ② 无新拉取（复用 c61）→ ③ append『### 3.11 行业位置与成长性』→ ④ $VG --section '3.11' → ⑤ 勾[x]"},
            {"id": "c62", "desc": "m25 订单诊断（合同负债+segment_composition+中标事件）：① 读 modules/m25-orders.md → ② $SV --raw xq_market_voice.data.answers.d1_intel（对撞，可选 ≤0.7K）→ ③ append『## 四、订单质量诊断』→ ④ $VG --section '四、订单' → ⑤ 勾[x]"},
            {"id": "c63", "desc": "m3 技术面（TD 4 步 + 多指标交叉）：① 读 modules/m3-technical.md → ② $SV kline + technical + any s3_fund_flow.data.fund_flow --depth 1 + --raw xq_market_voice.data.answers.d5_moves（≤6.3K）→ ③ append『## 五、技术面分析』→ ④ $VG --section '五、技术面' → ⑤ 勾[x]"},
            {"id": "c64", "desc": "m4 市场情绪与消息面（含 4.1.1 事件扫描）：① 读 modules/m4-sentiment.md → ② $SV news + timeline + xqvoice + --raw s35_research_reports.data.layer1.em_reports_count + any northbound.data.processed（≤11.2K+exa 分量 P3 窗实测 0~4.4K，超 20K 先章内即时消化再检索前移视图化；timeline m4/m9 双拉=有意设计禁合并预拉）→ ③ append『## 六、消息面与重大事件时间线』→ ④ $VG --section '六、消息面' → ⑤ 勾[x]"},
            {"id": "c65", "desc": "m5 估值（历史分位 + 同业对比 + 机构一致预期）：① 读 modules/m5-valuation.md → ② $SV valuation + consensus + peer（≤5.0K）→ ③ append『## 七、估值分析』→ ④ $VG --section '七、估值' → ⑤ 勾[x]"},
            {"id": "c66", "desc": "m6 综合研判 capstone（证据全景 + 三情景 + 情景-动作矩阵）：① 读 modules/m6-decision.md → ② python ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/lib/capstone_panorama.py --snapshot $SNAP（3.4K）+ $SV --raw xq_conclusion_check.processed + --raw xq_market_voice.data.answers.d3_bullbear + 盘上 §2/§3/§5 结论段（grep '^#{2,3} .*(结论|小结|要点)' 子节，无则章区间末 20 行；合计 ≤10.7K）→ ③ append『## 十一、综合研判（收口裁决）』→ ④ $VG --section '十一、综合研判' → ⑤ 勾[x]"},
            {"id": "c_d4_dividend", "desc": "m9.1 分红与股东回报（分红比例 + 股息率 + 稳定性；章头由本步建）：① 读 modules/m9-governance.md → ② $SV timeline + annual + holder + any s_esg.data + any governance（m9blk 两步合计 ≤5.0K；timeline 信封三件套已全覆盖）→ ③ append『## 十、公司治理与股东回报』+『### 10.1 分红与股东回报』→ ④ $VG --section '10.1' → ⑤ 勾[x]"},
            {"id": "c_d5_governance", "desc": "m9.2 股东结构与治理（控股股东 + 质押 + 关联交易）：① 读 modules/m9-governance.md → ② 无新拉取（复用 c_d4 投影）→ ③ append『### 10.2 股东结构与治理』→ ④ $VG --section '10.2' → ⑤ 勾[x]"},
            {"id": "c67", "desc": "m7 风险 + 反转假设：① 读 modules/m7-risk.md → ② $SV any classification + any s6_macro.data + any s_margin.data + any lhb + --raw s_stock_evaluation.data.processed.conclusions + --raw computed_metrics.tariff_vulnerability + --raw computed_metrics.concentration_composite + --raw xq_market_voice.data.answers.d6_risk（≤6.1K；对冲注记可选 + --raw xq_conclusion_check.processed ≤+1.6K）→ ③ append『## 九、风险提示与反转假设』→ ④ $VG --section '九、风险' → ⑤ 勾[x]"},
            {"id": "c68", "desc": "m8 局限性 ≥3 条：① 读 modules/m8-disclaimer.md → ② 零拉取（纯文本，引盘上已写章结论）→ ③ append『## 十二、数据时效与局限性』→ ④ $VG --section '局限性' → ⑤ 勾[x]"},
            {"id": "c_m10", "desc": "m10 机构观点与预测（版面 §八、写作序在 m8 后）：① 读 modules/m10-forecast.md → ② $SV --raw xq_market_voice.data.answers.d2_analyst + m10 白名单 --raw 小件（≤1.6K）→ ③ append『## 八、机构共识与盈利预测』→ ④ $VG --section '八、机构共识' → ⑤ 勾[x]"},
            {"id": "c68b", "desc": "m12 速览（TL;DR 两段式：值得买吗+面价背离度）——版面插顶、写作序末位：① 读 modules/m12-summary.md → ② $SV --raw xq_market_voice.processed.summary（status=ok 时 ≤0.2K；聚合磁盘章节）→ ③ 插顶 Edit（G11 声明行后、『## 一、』前，非 append；措辞避开 综合研判/情景/三档/概率/研判 锚词）→ ④ $VG --section '速览' → ⑤ 勾[x]（插顶后必经 c70 终验）"},
        ],
        "phase_4": [
            {"id": "c70", "desc": "运行 verify_gates.py 产出 sidecar，用其路径打勾（verdict=PASS + self_score≥80 由代码强制）；R9 章序检查 = $SO（违例 exit 1 = 先 $SO --fix 修序再 publish，写作序是写作面事实、显示序才是产品合同）"},
            {"id": "c70b", "desc": "失败轮关闭且引擎侧未修 → 落 ledger/memory 后再开下一股（写侧纪律：修完即走 = 教训不落笔，下批同法再撞）"},
        ],
        "phase_4_5": [
            {"id": "c_xq_delta", "desc": "增量逐条过堂：d1-d6+check 每维增量逐条显式落点（利空→m7 §7.1、利好→对撞行/观察清单）或写明弃用理由（漏填=修订未完）"},
        ],
        "phase_5": [
            {"id": "c80", "desc": "报告写入腾讯文档（发布前先 $SO --fix 重排至显示序——R9 硬合同）"},
        ],
    },
    "B": {
        "phase_0": [
            {"id": "c01", "desc": "Skills 加载（orchestrator + routing + registry）"},
            {"id": "c02", "desc": "用户问题映射表已生成"},
            {"id": "c04", "desc": "运行 routing/runner.py B <stock_code> → 拉取行情+K线+资金流+技术面（⚠️ 必须 > file 重定向，禁止 | head/tail pipe截断）"},
            {"id": "c04b", "desc": "错码前置核对：runner stderr 的 [verify] stock_code=…→stock_name=… × 任务书代码/公司名逐一比对；snapshot --list 头部 code= 同比——不一致立即停（错码会跑完全量拉取落盘后才暴露，白跑一次）"},
            {"id": "c06", "desc": "检查 runner._warnings → 处理降级/失败项"},
        ],
        "phase_1": [
            {"id": "c10", "desc": "runner 返回的实时行情数据确认", "agent": 1},
            {"id": "c11", "desc": "runner 返回的 K 线数据确认", "agent": 1},
            {"id": "c12", "desc": "确认 fetch_technical 预计算结果（MACD/KDJ/RSI/TD 已算好，勿自算）", "agent": 1},
            {"id": "c13", "desc": "60min 信号解读（s4.short_term_enrich.intraday_60m）", "agent": 1},
        ],
        "phase_2": [
            {"id": "c50", "desc": "数据收单完成（来自 runner s10_checklist）"},
            {"id": "c50b", "desc": "视图认知重建：snapshot_view --list（合法视图以 --list 输出为准——❌未挂载视图勿引用；凭记忆写视图名/写非法视图名 exit 2 是 fumble 主源，命令见下方 Runner 调用命令块）"},
        ],
        "phase_3": [
            {"id": "c59", "desc": "m38 核心结论头块（G11 声明后、首章节前；整块照抄 b_head 视图 head_draft_md，数字禁改）"},
            {"id": "c60", "desc": "m3 技术面"},
            {"id": "c61", "desc": "m6 操作建议"},
            {"id": "c62", "desc": "m36 短期多周期共振 + m37 筹码与资金结构"},
            {"id": "c63", "desc": "站内声量 T1-B 七维消费 + 总评 surface（m39 规则 R1-R6：非真空维 [src:] 落地、d3 看空同节、引文逐字；G80-B 三臂执法）"},
        ],
        "phase_4": [
            {"id": "c70", "desc": "运行 verify_gates.py（profile_quick）产出 sidecar，用其路径打勾"},
            {"id": "c70b", "desc": "失败轮关闭且引擎侧未修 → 落 ledger/memory 后再开下一股（写侧纪律：修完即走 = 教训不落笔，下批同法再撞）"},
        ],
        "phase_5": [
            {"id": "c80", "desc": "报告输出"},
        ],
    },
}


# ============================================================
# 清单生成
# ============================================================

# 批 1（流水架构 v1.1）步-锚映射三列表（P0.2 17 步表 baked；§n 终值=东材归档版面惯例复核）。
# 形态锁定：m0/m1/m2/m25/m3/m4/m5/m6/m7/m8/m10 = ## 级；m2blk 三步 = ## 三 + ### 3.10/3.11；
# m9blk 两步 = ### 10.1/10.2（章头由 c_d4 建）；m12 = 无编号锚（插顶）；终验步无锚。
# 写作序 = 版面序除 m10（版面 §八、写作序在 m8 后）与 m12（插顶）外。
PHASE3_STEP_ANCHORS = [
    # (步id, 模块, 版面锚, --section 锚, 半章判定 grep)
    ("c60", "m0", "## 一、标的分类与分析框架", "一、标的分类", r"^## 一、"),
    ("c_m1", "m1", "## 二、公司概况", "二、公司概况", r"^## 二、"),
    ("c61", "m2", "## 三、财务分析（至 §3.9）", "三、财务分析", r"^## 三、"),
    ("c_d2_safety", "m2", "### 3.10 资产安全检查", "3.10", r"^### 3\.10"),
    ("c_d3_growth", "m2", "### 3.11 行业位置与成长性", "3.11", r"^### 3\.11"),
    ("c62", "m25", "## 四、订单质量诊断", "四、订单", r"^## 四、"),
    ("c63", "m3", "## 五、技术面分析", "五、技术面", r"^## 五、"),
    ("c64", "m4", "## 六、消息面与重大事件时间线", "六、消息面", r"^## 六、"),
    ("c65", "m5", "## 七、估值分析", "七、估值", r"^## 七、"),
    ("c66", "m6", "## 十一、综合研判（收口裁决）", "十一、综合研判", r"^## 十一、"),
    ("c_d4_dividend", "m9", "## 十、公司治理与股东回报 + ### 10.1（章头由本步建）", "10.1", r"^### 10\.1"),
    ("c_d5_governance", "m9", "### 10.2 股东结构与治理", "10.2", r"^### 10\.2"),
    ("c67", "m7", "## 九、风险提示与反转假设", "九、风险", r"^## 九、"),
    ("c68", "m8", "## 十二、数据时效与局限性", "局限性", r"^## .*局限"),
    ("c_m10", "m10", "## 八、机构共识与盈利预测（版面 §八）", "八、机构共识", r"^## 八、"),
    ("c68b", "m12", "速览（插顶：G11 声明行后、『## 一、』前）", "速览", r"^## .*速览"),
]

# phase_3 头部三行（C1 语义句 / 护栏句 / 恢复三步索引——plan 批 1a baked 全文）
PHASE3_HEADER_LINES = [
    "> **原子步纪律（流水架构 v1.1）**：compact 后重读将写章节的模块合法且必须——台账「已读」仅记历史，不代表仍在 context；恢复三步见下。",
    "> 恢复只拉当前章投影；一次重拉 ≥2 章的全量视图 = 瀑布回潮，停下按预算表改投影（各步②括号内=预算实测值）。",
    "> 恢复三步：① grep 当前步锚 + 对照勾选台账定状态（三态判定）② 按状态跳补跑④⑤或重跑① ③ 残段按节锚整节替换。",
]


def get_phase_name(phase_key: str) -> str:
    """Phase key → 中文名"""
    names = {
        "phase_0": "Phase 0: 准入校验",
        "phase_1": "Phase 1: 数据拉取（并行 4 路 Agent）",
        "phase_2": "Phase 2: 数据收单",
        "phase_3": "Phase 3: 报告生成",
        "phase_4": "Phase 4: Gate 校验",
        "phase_4_5": "Phase 4.5: 站内结论求证（仅模式 A）",
        "phase_5": "Phase 5: 输出",
    }
    return names.get(phase_key, phase_key)


def generate_agent_steps(mode: str, question_result: dict) -> list[str]:
    """为 Phase 1 生成 Agent 分组描述（仅模式 A，v3 runner 模型）"""
    if mode != "A":
        return []

    # 根据用户问题动态调整 Agent 4 的内容
    has_futures = any(kw in str(question_result) for kw in ["期货", "商品", "铜价", "LME"])
    has_orders = any(kw in str(question_result) for kw in ["订单", "在手", "饱和", "合同负债"])

    extra_items = []
    if has_futures:
        extra_items.append("Claude 判断期货品种 → futures_main_sina(CU0)")
        extra_items.append("Claude 解读 LME 库存数据")
    if has_orders:
        extra_items.append("Claude 判断间接出海（主 runner 返回 reported_overseas_pct，D6 派生）")
        extra_items.append("Claude 筛选中标公告（runner 返回标题列表）")

    lines = [
        "### Agent 1: 行情 + 资金流（runner 已拉取，Claude 验证）",
        "  - runner 返回实时行情 + 资金流向 → Claude 确认数据完整性",
        "  - runner._warnings 中的降级项 → Claude 标注到报告",
        "",
        "### Agent 2: 财务三表（runner 已拉取，Claude 分析）",
        "  - runner 返回利润表/资产负债表/现金流 → Claude 做扣非诊断 + 利润归因",
        "  - runner 返回合同负债趋势 → Claude 确认数据",
        "",
        "### Agent 3: 事件扫描（读 processed 信号，Claude 研判）",
        "  - 读 risk_signals.processed（M 风险/P 利好信号）→ Claude 研判重大事件",
        "  - runner 返回公告标题 → Claude 筛选中标/重大合同",
        "",
        "### Agent 4: 订单 + 期货 + 同业（runner 返回数据，Claude 判断）",
        "  - snapshot 海外派生数据（D6_geo_revenue）→ Claude 判断间接出海 + 供需轴",
        "  - Claude 选择可比公司（runner 返回候选池）",
    ]
    for item in extra_items:
        lines.append(f"  - {item}")

    return lines


def generate_skeleton(required_files: list, mode_steps: dict, stock_codes: str,
                      checklist_path: str, out_path: str) -> str:
    """C1' 加载骨架（A-only，批4.2）——compact 免疫的加载集台账 + Phase 骨架。

    行式 `- ▸ `（禁 `[ ]`/`<!--` 前缀：防 update_checklist tick 计数误吞）；
    deferred 语义必须渲染进 m11 行（防注入骨架反而诱发重读）；
    台账翻页走 load_skeleton.py（C0 副作用化，禁依赖 LLM 自发 Edit）。
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# 加载骨架 — {stock_codes}（mode=A）",
        f"- 生成时间：{ts}",
        "- 台账：本文件（翻页走 load_skeleton.py，禁手工 Edit）",
        f"- 执行清单：{checklist_path}",
        "- 用法：compact/续接后先看本骨架——台账=读过≠在context，重读将写章节合法；未读模块按 JIT 序写前才读",
        "",
        "## 台账（加载集 × 已读状态）",
        "### 模块（JIT：写该模块章节前才 Read）",
    ]
    for f in required_files:
        if "/modules/" not in f["path"]:
            continue
        note = (" | ⏸ 延迟读：首次 verify FAIL 才 Read，勿预读"
                if f.get("load") == "deferred" else "")
        lines.append(f"- ▸ {f['path']} | 状态:未读{note}")
    scen = [f for f in required_files if "/scenarios/" in f["path"]]
    if scen:
        lines.append("### 场景（按需读）")
        lines.extend(f"- ▸ {f['path']} | 状态:未读" for f in scen)
    lines.append("### P0 Skill（会话启动已载，无需 Read）")
    lines.extend(f"- ▸ {f['path']} | 状态:已载" for f in required_files
                 if f["priority"] == "P0")
    lines.append("")
    lines.append("## Phase 骨架")
    for key in ("phase_0", "phase_1", "phase_2", "phase_3",
                "phase_4", "phase_4_5", "phase_5"):
        steps = mode_steps.get(key)
        if not steps:
            continue
        ids = [s["id"] for s in steps]
        rng = ids[0] if len(ids) == 1 else f"{ids[0]}…{ids[-1]}"
        lines.append(f"- ▸ {get_phase_name(key)}（{rng}）")
    content = "\n".join(lines) + "\n"
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return content


def generate_checklist(user_prompt: str, stock_codes: str = None,
                       mode: str = None, output: str = None,
                       skeleton_out: str = None) -> str:
    """
    生成完整执行清单的主函数。

    参数:
        user_prompt: 用户原始分析请求
        stock_codes: 股票代码（逗号分隔），None 则自动提取
        mode: 分析模式（A/B/C/D），None 则自动判定
        output: 输出文件路径，None 则返回字符串
        skeleton_out: C1' 加载骨架输出路径（A-only；模式 B 豁免——0 compact n=2、
                      JIT 下骨架纯增量、纳入折扣比 25.6%=A 侧 2.2 倍而收益恒 0）

    返回: 清单 Markdown 内容
    """
    # 自动提取/判定
    if not stock_codes:
        codes = extract_stock_codes(user_prompt)
        stock_codes = ",".join(codes) if codes else "未知"
    if not mode:
        mode = detect_mode(user_prompt)

    stock_code_list = [c.strip() for c in stock_codes.split(",") if c.strip()]

    # Stage 1: 两段式问题映射
    question_result = parse_user_question(user_prompt)

    # Stage 2: Skill 依赖图
    required_files = resolve_required_files(mode, user_prompt)
    profile_name = get_mode_profile(mode)

    # 获取 Phase 步骤
    mode_steps = PHASE_STEPS.get(mode, PHASE_STEPS["A"])

    # 生成时间戳
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_file = output or f"/tmp/analysis_checklist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    # 统计总步骤数（排除 phase_1_skipped：3 项 ❌ 永久跳过、不可勾选、无 c-tag，计入则与 update_checklist 分母不一致）
    total_steps = sum(len(steps) for k, steps in mode_steps.items() if k != "phase_1_skipped")
    # 加上用户问题映射行数（每行带 c_map_N c-tag，可被 update_checklist 计数/打勾 → 与步骤分母同源）
    mapping_rows = len(question_result["matched"]) + len(question_result["unmapped"])
    total_steps += mapping_rows

    # 构建清单
    lines = []
    lines.append(f"# 执行清单 — {'、'.join(stock_code_list)} 分析（mode={mode}）")
    lines.append(f"生成时间：{timestamp}")
    lines.append(f"用户问题：{user_prompt}")
    lines.append("")

    # Phase 0
    lines.append(f"## {get_phase_name('phase_0')}")
    for step in mode_steps["phase_0"]:
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
    lines.append("")

    # Runner 调用命令（v3 机制 6）
    if mode in ("A", "B") and stock_code_list:
        sc = stock_code_list[0]
        lines.append("### 🔧 Runner 调用命令（机械化部分）")
        lines.append("```bash")
        if mode == "A":
            lines.append(f"# Step 1: 数据拉取（routing runner）")
            lines.append(f"# ⚠️ 必须使用 > file 重定向，禁止 | head / | tail 等管道截断")
            lines.append(f"python ~/.hermes/skills/stock-analysis/financial-data-routing/runner.py A {sc} \\")
            lines.append(f"  > /tmp/runner_snapshot_{sc}_mode{mode}.json 2>/tmp/runner_stderr_{sc}_mode{mode}.log")
            lines.append(f"# 订单数据已并入主 snapshot（合同负债+分地区+中标事件），无需独立 runner")
        elif mode == "B":
            lines.append(f"# 数据拉取（routing runner）")
            lines.append(f"# ⚠️ 必须使用 > file 重定向，禁止 | head / | tail 等管道截断")
            lines.append(f"python ~/.hermes/skills/stock-analysis/financial-data-routing/runner.py B {sc} \\")
            lines.append(f"  > /tmp/runner_snapshot_{sc}_mode{mode}.json 2>/tmp/runner_stderr_{sc}_mode{mode}.log")
        # Step 2: 错码核对 + 视图认知（P1c 2026-09-03，内联产生真相的命令、拒绝视图计数）
        lines.append(f"# Step 2: 错码核对（不一致立即停——错码跑完全量拉取落盘后才在 [verify] 行暴露，白跑一次）")
        lines.append(f"grep '\\[verify\\]' /tmp/runner_stderr_{sc}_mode{mode}.log   # stock_code=…→stock_name=… × 任务书代码/公司名逐一比对")
        lines.append(f"python3 ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/snapshot_view.py /tmp/runner_snapshot_{sc}_mode{mode}.json --list   # 头部 code= 复核 + 全部视图挂载状态（合法视图以 --list 输出为准）")
        if mode == "A":
            # 批 1（流水架构 v1.1）：原子步记号展开一次，phase_3 步内 $SV/$VG/$SNAP 勿重写全路径
            lines.append(f"# Step 3: 原子步记号（phase_3 各步②④用；$SNAP=本票快照，$VG --report=本票报告）")
            lines.append(f'SNAP="/tmp/runner_snapshot_{sc}_mode{mode}.json"')
            lines.append(f'SV="python3 ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/snapshot_view.py /tmp/runner_snapshot_{sc}_mode{mode}.json"')
            lines.append(f'VG="python3 ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/verify_gates.py --report /tmp/analysis_report_{sc}_mode{mode}.md --data-snapshot /tmp/runner_snapshot_{sc}_mode{mode}.json"')
            lines.append(f'SO="python3 ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/check_section_order.py --report /tmp/analysis_report_{sc}_mode{mode}.md"')
        lines.append("```")
        lines.append("")

    # 用户问题 → 数据需求映射
    lines.append("## 用户问题 → 数据需求映射")
    lines.append("| 用户问题 | 需要数据 | API/源 | 来源 | 状态 |")
    lines.append("|---------|---------|-------|------|------|")

    # mapping 行带 c_map_N c-tag（c-tag 在 [ ] 之后，对齐 phase 步骤写法 + update_checklist:163 正则 [ ] <!--cid-->）
    # → update_checklist:185 的 <!--c[\w]+--> 计数包含 mapping 行，与 generate 分母一致（Bug 2 分母对齐）
    _all_map = ([("matched", m) for m in question_result["matched"]]
                + [("unmapped", u) for u in question_result["unmapped"]])
    for i, (kind, row) in enumerate(_all_map, 1):
        cid = f"c_map_{i}"   # c[\w]+ 匹配；唯一不撞现有 c01..c80 / c_d2_* / c_pdf_*
        if kind == "matched":
            apis = ", ".join(row["api_sources"][:2])  # 最多显示2个API
            lines.append(f"| {row['segment'][:20]} | {row['data_needs'][:30]} | {apis} | 映射表 | [ ] <!--{cid}--> |")
        else:
            lines.append(f"| {row['segment'][:20]} | ⚠️ 待LLM判断 | — | [LLM兜底] | [ ] <!--{cid}--> |")

    lines.append("")

    # Phase 1
    lines.append(f"## {get_phase_name('phase_1')}")
    agent_lines = generate_agent_steps(mode, question_result)
    if agent_lines:
        lines.extend(agent_lines)
        lines.append("")
    for step in mode_steps["phase_1"]:
        agent_tag = f"（Agent {step.get('agent', '?')}）" if "agent" in step else ""
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}{agent_tag}")
    lines.append("")

    # 永久跳过项（v3：显式标记不可达步骤）
    if "phase_1_skipped" in mode_steps:
        lines.append("### ❌ 永久跳过的步骤（runner 内部已硬跳）")
        for step in mode_steps["phase_1_skipped"]:
            lines.append(f"- {step['desc']}")
        lines.append("")

    # Phase 2
    lines.append(f"## {get_phase_name('phase_2')}")
    for step in mode_steps["phase_2"]:
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
    lines.append("")

    # Phase 3
    lines.append(f"## {get_phase_name('phase_3')}")
    # 批 1：原子步纪律头部三行（仅模式 A；B 面零触碰）
    if mode == "A":
        lines.extend(PHASE3_HEADER_LINES)
    for step in mode_steps["phase_3"]:
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
    if mode == "A":
        # 批 1：步-锚映射三列表（B-2 baked）+ m12 插顶必经终验注（B-3）
        lines.append("")
        lines.append("### 步-锚映射（16 写作步 × 版面锚 × ④ --section 锚；写作序=版面序除 m10/m12 外）")
        lines.append("")
        lines.append("| 序 | 步 | 模块 | 版面锚 | ④ --section 锚 | 半章判定 grep |")
        lines.append("|---|---|---|---|---|---|")
        for i, (sid, mod, layout, sec_anchor, grep_pat) in enumerate(PHASE3_STEP_ANCHORS, 1):
            lines.append(f"| {i} | {sid} | {mod} | {layout} | {sec_anchor} | `grep -cE '{grep_pat}'` |")
        lines.append("")
        lines.append("**④⑤ 烘焙链速查（V-D；每步收尾=单命令，gate 败自动阻断勾选 = T2 执法）**：")
        for sid, _mod, _layout, sec_anchor, _grep_pat in PHASE3_STEP_ANCHORS:
            lines.append(f"- {sid}：`$VG --section '{sec_anchor}' && python3 ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/update_checklist.py --check {sid} --file $FL`")
        lines.append("")
        lines.append("> m12（c68b）版面插顶、写作序末位；插顶后必经 c70 终验（mtime 合同：sidecar≥report，verify_gates.py check_pointer）。④ 每步未过不勾⑤；④ 全臂 FAIL 且 reason 属内容缺失类 → `--section <锚> --partial` 确认残段后按恢复三步走。")
        if mode == "A":
            lines.append("> **V-D 复合执行令**：③④⑤ 烘焙单命令链（`③append && $VG --section '<锚>' && python3 …/update_checklist.py --check <cid> --file $FL`；gate 败自动阻断勾选 = T2 执法；gate 首败修复轮回流已预注册）；② 多视图一律单命令链式（`$SV a && $SV b`）；**管理轮禁令：禁 TaskCreate/TaskUpdate，清单即唯一状态（≤3 次兜底更新）**。")
    lines.append("")

    # Phase 4
    lines.append(f"## {get_phase_name('phase_4')}")
    lines.append(f"Profile: `{profile_name}`")
    for step in mode_steps["phase_4"]:
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
    lines.append("")

    # Phase 4.5（仅模式 A：PHASE_STEPS 仅 A 含此键，B 跳过站内求证）
    if "phase_4_5" in mode_steps:
        lines.append(f"## {get_phase_name('phase_4_5')}")
        for step in mode_steps["phase_4_5"]:
            lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
        lines.append("")

    # Phase 5
    lines.append(f"## {get_phase_name('phase_5')}")
    for step in mode_steps["phase_5"]:
        lines.append(f"- [ ] <!--{step['id']}--> {step['desc']}")
    lines.append("")

    # 必须加载的文件清单
    lines.append("---")
    lines.append("")
    lines.append("## 🔴 必须加载的文件（Phase 0 完成前不许进 Phase 1）")
    lines.append("")
    lines.append("| 优先级 | 文件 | 状态 | 原因 |")
    lines.append("|-------|------|------|------|")

    for f in required_files:
        priority = f["priority"]
        path = f["path"]
        reason = f["reason"]
        # orchestrator 和 data-source-registry 视为已加载
        if "orchestrator" in path or "data-source-registry" in path:
            status = "✅ 已加载"
        elif f.get("load") == "deferred":
            status = "⏸ 延迟读：首次 verify FAIL 才 Read"
        else:
            status = "[ ] 未加载"
        bold = "**" if priority == "P0" else ""
        lines.append(f"| {bold}{priority}{bold} | {bold}{path}{bold} | {status} | {reason} |")

    lines.append("")

    # LLM 兜底提示（如果有未匹配的问题）
    if question_result["unmapped"]:
        lines.append("---")
        lines.append("")
        lines.append("## ⚠️ LLM 兜底任务（以下子问题需要 Claude 判断数据需求）")
        lines.append("")
        lines.append("```")
        lines.append(question_result["llm_fallback_prompt"] or "无")
        lines.append("```")
        lines.append("")
        lines.append("请在主线程中解析上述未匹配问题，将结果回写到清单的映射表中。")
        lines.append("")

    # 完成进度
    lines.append("---")
    lines.append(f"**完成进度：0/{total_steps}**")
    lines.append(f"**下一步**：开始执行 Phase 0")
    lines.append("")

    content = "\n".join(lines)

    # 写入文件
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        print(f"✅ 执行清单已生成: {output}")
        print(f"   模式: {mode} | 股票: {stock_codes} | 步骤: {total_steps}")
        if question_result["unmapped"]:
            print(f"   ⚠️  {len(question_result['unmapped'])} 条问题需要 LLM 兜底")
        if skeleton_out:
            if mode == "A":
                generate_skeleton(required_files, mode_steps, stock_codes,
                                  output, skeleton_out)
                print(f"✅ 加载骨架已生成: {skeleton_out}")
            else:
                print(f"ℹ️ 模式 {mode} 豁免骨架（A-only；B 证据：0 compact / JIT 纯增量 / "
                      f"折扣比 25.6%）——骨架未生成")
    else:
        print(content)

    return content


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="执行清单生成器（机制 1）")
    parser.add_argument("--user-prompt", required=True, help="用户的原始分析请求")
    parser.add_argument("--stock-codes", help="股票代码（逗号分隔），不传则自动提取")
    parser.add_argument("--mode", choices=["A", "B"], help="分析模式，不传则自动判定")
    parser.add_argument("--output", help="输出清单文件路径")
    parser.add_argument("--skeleton-out", help="C1' 加载骨架输出路径（A-only，B 豁免）")
    parser.add_argument("--ignore-trap-ledger", action="store_true",
                        help="逃生口：跳过 TRAP_LEDGER blocked(P3) 硬阻断检查")
    args = parser.parse_args()

    # E10（TRAP_LEDGER P3 硬阻断）：台账存在 blocked 条目（某 trap 复发/回退到
    # 「未修复不能再开新票」的运营态）→ 拒生成新清单 exit 2；修复后置 blocked: false。
    if not args.ignore_trap_ledger:
        import trap_ledger
        blocked = trap_ledger.blocked_gates()
        if blocked:
            print("🔴 TRAP_LEDGER 存在 blocked(P3) 条目，新分析清单生成被阻断"
                  "（修复后置 blocked: false，或 --ignore-trap-ledger 逃生）：", file=sys.stderr)
            for e in blocked:
                print(f"   · {e.get('signature')} — {e.get('fix', '')}", file=sys.stderr)
            sys.exit(2)

    generate_checklist(
        user_prompt=args.user_prompt,
        stock_codes=args.stock_codes,
        mode=args.mode,
        output=args.output,
        skeleton_out=args.skeleton_out,
    )


if __name__ == "__main__":
    main()
