# 统一降级策略

> 集中定义所有 Skill 共用的降级行为，避免各 Skill 各自定义导致行为不一致。

---

## 场景 1：数据拉取失败

```
第 1 次失败 → 重试（可能是 ConnectionError）
第 2 次失败 → 切备用 API（按 routing 降级链）
第 3 次失败 → 标注 [数据缺失]，继续分析（在"分析局限性"披露）
```

---

## 场景 2：runtime-probe 失败

| 故障情形 | 处理 |
|---------|------|
| 超时 > 10s | 信任静态评级，标注 [probe 未完成] |
| ImportError（akshare 损坏） | 信任静态评级 + 标注 [probe 失败] |
| ConnectionError（网络问题） | 信任静态评级 + 标注 [probe 失败]，建议用户检查网络 |
| probe 跑完但 1+ 关键 API 异常 | 在 session override 中降级该 API |

---

## 场景 3：subagent 并行失败

```
第 1 次失败 → 重试（参数错误时检查 subagent_type/category 互斥，详见 exec-protocol.md）
第 2 次失败 → 降级为串行执行 + run_in_background
```

---

## 场景 4：Skill 子文件加载失败

| 情况 | 处理 |
|------|------|
| 文件不存在 | 跳过该模块/场景，标注 [模块缺失] |
| 文件存在但格式异常 | 用主 SKILL.md 索引中的简短描述兜底 |

---

## 场景 5：Gate 校验失败

### 判定流程

```
verify_gates.py 返回 failed_gates → 分类处理
  ├─ 失败数 ≤ fail_threshold → 补全对应模块后重新校验
  └─ 失败数 > fail_threshold → 按下方 Gate→Scene 映射精准重做
```

### "重做"定义：精准重做，不是从头跑

| 含义 | ✅ 是 | ❌ 不是 |
|------|------|---------|
| 范围 | 重拉失败 Gate 对应的数据场景 | 从头跑 Phase 0-4 全部流程 |
| 数据 | 仅失败 Gate 对应的 scene | 所有 14 个 scene |
| 报告 | 仅重写失败 Gate 对应的模块 | 整个报告重新生成 |

### Gate → 数据场景映射

| 失败 Gate | 需要重拉的数据 | 需要重写的模块 |
|----------|--------------|--------------|
| G6~G9 | 重拉 s1_financial | 补写 m2 |
| G10 | 重拉 s5_events | 补写 m4 |
| G14 | 重拉 s2_quote_kline | 补写 m3 |
| G15, G18 | 重拉 s11_peer | 补写 m5 |
| G16, G17, G19 | 重拉 s12_orders | 补写 m25 |
| G1~G5, G11~G13, G20, G21 | **不重拉数据** | 补写对应模块 |

### 重做执行步骤

```
Step 1: 从 verify_gates.py 输出获取 failed_gates 列表
Step 2: 按上方映射表，确定需要重拉的场景集合
Step 3: 仅重拉这些场景（避免重拉已成功的数据）
Step 4: 仅重写受影响的报告模块
Step 5: 重新运行 verify_gates.py
Step 6: 仍在阈值外 → 在"分析局限性"标注未通过的 Gate，不再重试
```
