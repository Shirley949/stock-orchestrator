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
→ 原因：清单是 Phase 判断的唯一依据。跳过清单会导致后续 Phase 不知道该拉哪些数据、加载哪些模块，最终产出质量不可控。

### 约束 2：清单项必须跟踪
清单生成后 → 用 `TaskCreate` 把每个 `[ ]` 项加到 task list（让 Claude 的 task 系统也跟踪）。
→ 原因：跟踪清单项可以防止遗漏，确保每个步骤都被执行。如果没有跟踪，Claude 可能会跳过某些步骤，导致分析不完整。

### 约束 3：完成必须打勾
每完成一个 `[ ]` 项 → 用 `update_checklist.py` 更新清单：
```bash
python ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/update_checklist.py \
  --check c01 \
  --file /tmp/analysis_checklist_{timestamp}.md
```
→ 原因：打勾是进度跟踪的唯一方式。如果不打勾，Phase 门控无法判断是否可以进入下一阶段，可能导致未完成的步骤被跳过。

### 约束 4：Phase 门控
Phase N 结束前 → 检查 Phase N 所有 `[ ]` 项是否打勾，**未打勾不许进入 Phase N+1**。
→ 原因：Phase 门控是质量保证的关键机制。如果允许跳过未完成的步骤，可能会导致数据缺失或分析错误，最终影响报告质量。

### 约束 5：Gate 硬关卡
报告写完后、输出前 → **必须**运行 `verify_gates.py`：
```bash
python ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/verify_gates.py \
  --report /tmp/analysis_report.md \
  --profile full
```
`sys.exit(1)` = 报告不能输出，必须补全。
→ 原因：Gate 校验是最后一道质量关卡。如果不运行 Gate 校验，可能会输出不符合质量标准的报告，影响用户决策。

### 约束 6：两段式问题映射
清单中的"用户问题映射"表，映射表匹配的标记 `映射表`，未匹配的标记 `[LLM兜底]`。
对于 `[LLM兜底]` 项 → 在主线程中判断需要什么数据，回写到清单。

---

## 触发条件（必须最先加载）

以下条件满足任一即触发（OR 关系）：

- 股票代码（6 位数字 / SH·SZ 前缀 / .SS·.SZ 后缀）
- 分析动词："分析 / 看看 / 买不买 / 估值 / 风险 / 事件 / 财报 / 怎么样"

**兜底规则：** 无股票代码时，只要有分析动词就触发。opencode 用 `websearch` 搜索确认股票代码后继续执行。

---

## Phase 0：执行清单生成 + 分析模式判定

> **⚠️ Phase 0 的第一个动作必须是运行 `generate_checklist.py`（见约束 1）。**
> 脚本会自动判定模式、映射用户问题、解析 Skill 依赖图，输出完整执行清单。

| 触发关键词 | 模式 | 后续 Phase 加载 |
|-----------|-----|----------------|
| 深度分析/帮我看看/买不买/估值/财报分析/全面分析/风险/事件/贵不贵 | **A：完整** | Phase 1 + 2 + 3 + 4 |
| 今天买不买/盘中/能加仓/要不要卖 | **B：当日** | Phase 1 + 2 |

### Phase 0 执行步骤
1. 运行 `generate_checklist.py` → 生成 `/tmp/analysis_checklist_*.md`
2. 检查清单中的"必须加载文件清单" → 按清单 Read 所有 `P0` 文件
3. 检查"用户问题映射"表 → 对 `[LLM兜底]` 项做自然语言判断，回写清单
4. 用 `TaskCreate` 跟踪清单所有步骤（约束 2）

### 混合模式处理规则

1. **多个模式关键词同时命中** → 取最高优先级 A > B（A 已含 B 所需数据）
2. **对比请求**（"对比/和/vs"）→ 对每只股票分别跑模式 A，同业对比合并写
3. **组合请求**（"分析+风险"）→ 直接跑模式 A（已包含 m4.1.1 + m5）
4. **模糊请求**（"看看 xxx"）→ 默认模式 A（宁多勿少）
5. **明确否定**（"只看技术"）→ 按否定关键词裁剪 Profile

---

## Phase 1：会话级初始化（始终运行）

1. 加载 `data-source-registry/SKILL.md`（评级体系）
2. **数据源架构（2026-06-19 更新）**：
   - 财报快速: 东财datacenter API (curl)
   - 财报深挖: cninfo全文PDF (curl+pdfplumber) — 3步happy path
   - K线: 新浪K线API (curl, datalen=60)
   - 机构EPS: AkShare stock_profit_forecast_ths
   - 技术指标: 自算(新浪K线+Python)
   - **富途数据**: futu_client.py（分析师评级/目标价/资金分布/财报预测/主营构成/三大表）
   - API模板: `financial-data-routing/references/api-templates/`
3. **不运行 runtime-probe**（节省 5 秒）。probe 仅在后续 API 调用失败时按需触发

---

## Phase 2：数据拉取（按模式定制场景路径）

### ⚠️ Runner 调用强制规范（P1-2 fix — 2026-06-30）

```bash
# ✅ 正确：使用 > file 重定向 stdout（输出完整 JSON）
python ~/.hermes/skills/stock-analysis/financial-data-routing/runner.py A <code> \
  > /tmp/runner_snapshot_<code>.json 2>/tmp/runner_stderr_<code>.log

# ❌ 错误：使用管道截断（会导致 BrokenPipeError，丢失 90% 数据）
python runner.py A <code> | head -2000    # ← 禁止
python runner.py A <code> | tail -100     # ← 禁止
python runner.py A <code> 2>&1 | tee ...  # ← 禁止（除非全程不截断）
```

**验证：** 5 股票实测，`> file` 重定向输出 460K-621K chars 完整 JSON；`| head -2000` 仅捕获 67K chars 并触发 BrokenPipeError。

### 模式 A 调用顺序（带并行标注）

```
串行：s1-financial（财报必须先拿到）
    ↓
强制：s1 内部已自动执行以下步骤（runner 已实现）：
  ├─ 步骤3: fetch_cninfo_reports() → cninfo 年报/季报 PDF 下载+解析
  ├─ 步骤3.5: fetch_research_reports() → 东财机构研报 PDF 下载+解析
  └─ 步骤3.6: fetch_annual_report_analysis() → 年报 6 维度数据提取（D2-D6）
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
并行：s2 行情（实时行情快照）+ s2 K 线（近 60 日，同源拉取）
串行：s2 技术指标（自算，依赖 K 线数据）
串行：s2 盘口解读（依赖实时行情）
```

---

## Phase 3：报告生成（仅按模式加载需要的模块）

| 模式 | 加载模块文件 |
|------|------------|
| **A** | m0 / m1 / m2 / m25 / m3 / m4 / m5 / m6 / m7 / m8 / m10 / m11 |
| **B** | m3 / m6 / m11 |

---

## Phase 4：输出 + Gate 校验（强制硬关卡）

> **⚠️ 报告写完后、输出前，必须运行 `verify_gates.py`（见约束 5）。**

1. 将报告写入 `/tmp/analysis_report.md`
2. 运行 Gate 校验脚本：
   ```bash
   python ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/verify_gates.py \
     --report /tmp/analysis_report.md \
      --profile full  # 或 quick
   ```
3. 脚本输出每个 Gate 的通过/失败状态 + 自评分
4. **如果 `sys.exit(1)`** → 报告不能输出，必须按脚本提示补全失败的 Gate
5. 自评分 ≥ 80 分方可输出

### Gate Profile 对应关系
| 模式 | Profile | 失败阈值 |
|------|---------|---------|
| A | profile_full | 3 |
| B | profile_quick | 2 |

---

## Phase 5：调用契约（详见 `references/exec-protocol.md`）

- **subagent_type 和 category 互斥**（明确写，避免参数错误）
- **run_in_background 触发条件**（独立数据源可并行）
- **三次失败 → 降级为同步执行**（详见 `references/degradation-strategy.md`）
