---
name: stock-orchestrator
description: >
  股票分析的入口与主控——当用户消息涉及股票分析（股票代码、股票名称、或"分析/看看/买不买/估值/风险/事件"等动词）时，必须最先加载本 Skill。
  本 Skill 是 stock-analysis-quality / financial-data-routing / data-source-registry / order-intelligence 的统一入口，禁止跳过。
---

# Stock Orchestrator（主控 Skill，永远全量加载）

> **本 Skill 是股票分析的唯一入口。** 加载后，禁止 Skill 系统自动加载其他 4 个股票相关 Skill——它们的加载由本 Skill 通过 Read 显式触发。

---

## 🔴 强制约束（违反则质量无法保证）

> **以下 4 条约束是脚本工件驱动的硬性协议，不是建议。**

### 约束 1：执行清单必须首先生成
收到任何股票分析请求 → **第一个动作**必须是运行 `generate_checklist.py`：
```bash
python ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/generate_checklist.py \
  --user-prompt "用户原始问题" \
  --stock-codes "股票代码" \
  --output /tmp/analysis_checklist_{timestamp}.md
```
不跑清单 = 不知道该做什么 = 不能开始分析。

### 约束 2：清单项必须跟踪
清单生成后 → 用 `TaskCreate` 把每个 `[ ]` 项加到 task list（让 Claude 的 task 系统也跟踪）。

### 约束 3：完成必须打勾
每完成一个 `[ ]` 项 → 用 `update_checklist.py` 更新清单：
```bash
python ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/update_checklist.py \
  --check c01 \
  --file /tmp/analysis_checklist_{timestamp}.md
```

### 约束 4：Phase 门控
Phase N 结束前 → 检查 Phase N 所有 `[ ]` 项是否打勾，**未打勾不许进入 Phase N+1**。

### 约束 5：Gate 硬关卡
报告写完后、输出前 → **必须**运行 `verify_gates.py`：
```bash
python ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/verify_gates.py \
  --report /tmp/analysis_report.md \
  --profile full
```
`sys.exit(1)` = 报告不能输出，必须补全。

### 约束 6：两段式问题映射
清单中的"用户问题映射"表，映射表匹配的标记 `映射表`，未匹配的标记 `[LLM兜底]`。
对于 `[LLM兜底]` 项 → 在主线程中判断需要什么数据，回写到清单。

---

## 触发条件（必须最先加载）

- 股票代码（6 位数字 / SH·SZ 前缀 / .SS·.SZ 后缀）
- 已知股票名称（`references/stock-name-list.md` 维护白名单）
- 分析动词："分析 / 看看 / 买不买 / 估值 / 风险 / 事件 / 财报 / 怎么样"

---

## Phase 0：执行清单生成 + 分析模式判定

> **⚠️ Phase 0 的第一个动作必须是运行 `generate_checklist.py`（见约束 1）。**
> 脚本会自动判定模式、映射用户问题、解析 Skill 依赖图，输出完整执行清单。

| 触发关键词 | 模式 | 后续 Phase 加载 |
|-----------|-----|----------------|
| 深度分析/帮我看看/买不买/估值/财报分析/全面分析 | **A：完整** | Phase 1 + 2 + 3 + 4 |
| 今天买不买/盘中/能加仓/要不要卖 | **B：当日** | Phase 1 + 2 |
| 有没有风险/事件/最近有什么公告 | **C：事件扫描** | Phase 1（仅 s5）|
| 估值/贵不贵/PE多少 | **D：估值** | Phase 1（仅 s9/s11）+ 部分 Phase 3 |

### Phase 0 执行步骤
1. 运行 `generate_checklist.py` → 生成 `/tmp/analysis_checklist_*.md`
2. 检查清单中的"必须加载文件清单" → 按清单 Read 所有 `P0` 文件
3. 检查"用户问题映射"表 → 对 `[LLM兜底]` 项做自然语言判断，回写清单
4. 用 `TaskCreate` 跟踪清单所有步骤（约束 2）

### 混合模式处理规则

1. **多个模式关键词同时命中** → 取最高优先级 A > D > C > B（A 已含 C 的事件扫描和 D 的估值）
2. **对比请求**（"对比/和/vs"）→ 对每只股票分别跑模式 A，同业对比合并写
3. **组合请求**（"分析+风险"）→ 直接跑模式 A（已包含 m4.1.1 + m5）
4. **模糊请求**（"看看 xxx"）→ 默认模式 A（宁多勿少）
5. **明确否定**（"只看技术"）→ 按否定关键词裁剪 Profile

---

## Phase 1：会话级初始化（始终运行）

1. 加载 `data-source-registry/SKILL.md`（200 行评级体系）
2. **不运行 runtime-probe**（节省 5 秒）。probe 仅在后续 API 调用失败时按需触发：
   ```bash
   python3 ~/.hermes/skills/stock-analysis/data-source-registry/references/runtime-probe.py
   ```
   - 同日首次运行：探测 8 个 API，~5 秒，结果缓存到 `~/.cache/skill-probes/YYYY-MM-DD.json`
   - 同日再次运行：读缓存，瞬间返回
3. 静态评级已足够覆盖大部分场景（东财源断连等已标注），probe 是诊断工具不是必经步骤

---

## Phase 2：数据拉取（按模式定制场景路径）

### 模式 A 调用顺序（带并行标注）

```
串行：s1-financial（财报必须先拿到）
    ↓
并行 4 路 explore subagent：
  ├─ Agent 1: s2 行情 + s3 资金流
  ├─ Agent 2: s5 事件扫描（18 类一次拉完）
  ├─ Agent 3: s7/s8 周期/A 股专属（按分类）
  └─ Agent 4: s9 新闻 + s11 可比公司
    ↓
串行：s12 订单（依赖 s1 的合同负债）
```

### 模式 B 调用顺序

```
串行：s2 行情（实时行情快照）
串行：s2 K 线（近 60 日）
串行：s2 技术指标（自算）
串行：s2 盘口解读
```

### 模式 C 调用顺序

```
串行：s5 事件扫描（18 类）
```

### 模式 D 调用顺序

```
串行：s9 情景概率 + s11 可比公司
串行：s4 机构评级/目标价
```

---

## Phase 3：报告生成（仅按模式加载需要的模块）

| 模式 | 加载模块文件 |
|------|------------|
| **A** | m0 / m1 / m2 / m25 / m3 / m4 / m5 / m6 / m7 / m8 / m11 |
| **B** | m3 / m6 / m11 |
| **C** | m4 / m11 |
| **D** | m5 / m11 |

---

## Phase 4：输出 + Gate 校验（强制硬关卡）

> **⚠️ 报告写完后、输出前，必须运行 `verify_gates.py`（见约束 5）。**

1. 将报告写入 `/tmp/analysis_report.md`
2. 运行 Gate 校验脚本：
   ```bash
   python ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/verify_gates.py \
     --report /tmp/analysis_report.md \
     --profile full  # 或 quick/event_scan/valuation
   ```
3. 脚本输出每个 Gate 的通过/失败状态 + 自评分
4. **如果 `sys.exit(1)`** → 报告不能输出，必须按脚本提示补全失败的 Gate
5. 自评分 ≥ 80 分方可输出

### Gate Profile 对应关系
| 模式 | Profile | 失败阈值 |
|------|---------|---------|
| A | profile_full | 3 |
| B | profile_quick | 2 |
| C | profile_event_scan | 1 |
| D | profile_valuation | 2 |

---

## Phase 5：调用契约（详见 `references/exec-protocol.md`）

- **subagent_type 和 category 互斥**（明确写，避免参数错误）
- **run_in_background 触发条件**（独立数据源可并行）
- **三次失败 → 降级为同步执行**（详见 `references/degradation-strategy.md`）
