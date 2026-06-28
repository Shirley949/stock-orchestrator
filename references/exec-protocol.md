# 执行协议（exec-protocol）

> 本文件定义 subagent 并行调用的契约，避免参数错误和执行失败。

---

## Subagent 调用契约

### 核心规则：subagent_type 和 category 互斥

```
❌ 错误：同时传 subagent_type="explore" 和 category="quick"
✅ 正确：只传 subagent_type，或只传 category，二选一
```

- `subagent_type`：使用 Claude Code 内置的 agent 类型（如 `explore`、`librarian`、`oracle`）
- `category`：自定义任务分类（如 `deep`、`quick`），用于路由到不同执行策略
- **两者互斥**，同时传系统直接拒绝执行

**实际报错行为：**
```
同时传 subagent_type + category → Tool execution aborted（系统拒绝执行）
```

**修复方法：**
```
遇到此错误时 → 去掉 category 参数，只保留 subagent_type。
explore/librarian/oracle/metis/momus 只用 subagent_type，
category 只用于业务任务（deep/quick/visual-engineering 等）。
```

### 触发条件

使用 subagent 的场景：
- 单步任务输出 > 5K tokens
- 涉及独立的搜索/数据拉取
- 需要大量原始数据处理

不使用 subagent 的场景：
- 简单查询（< 1K tokens）
- 依赖前序结果的串行任务
- 报告生成（依赖所有数据）

---

## run_in_background 触发条件

### 适用（可并行）

- ✅ 拉取财务数据 + 拉取技术数据（独立数据源）
- ✅ 事件扫描 + 新闻搜索（独立维度）
- ✅ 多只股票的并行分析

### 不适用（必须串行）

- ❌ 报告生成（依赖前面所有数据）
- ❌ 订单分析（依赖财报的合同负债）
- ❌ Gate 校验（依赖报告完成）

---

## 三次失败降级规则

```
第 1 次失败 → 重试（可能是 ConnectionError）
第 2 次失败 → 切备用 API（按 routing 降级链）
第 3 次失败 → 切同步执行 + 标注"分析局限性"
```

---

## 模式 A 的标准并行图

```
Phase 1 (串行):
└─ s1 财报（必须先拿到，后续依赖合同负债）

Phase 2 (并行 4 路 explore subagent):
├─ Agent 1: s2 行情 + s3 资金流
├─ Agent 2: s5 事件扫描 18 类
├─ Agent 3: s7/s8 周期/A 股专属（按模块零分类结果）
└─ Agent 4: s9 新闻 + s11 可比公司

Phase 3 (串行):
└─ s12 订单（依赖 s1 合同负债 + Phase 2 的行业数据）

Phase 4 (串行):
└─ 报告生成 + Gate 校验 + 自评分
```

### 并行执行注意事项

1. **并行 ≠ 无序**：Phase 2 的 4 个 Agent 互不依赖，但都依赖 Phase 1 完成
2. **结果收集**：所有并行 Agent 完成后，主线程统一汇总再进入 Phase 3
3. **失败处理**：任一 Agent 失败 → 按"三次失败降级规则"处理，不阻塞其他 Agent
4. **上下文隔离**：每个 Agent 只拿到自己需要的数据，不共享完整上下文
