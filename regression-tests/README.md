# regression-tests/ — 数据契约 pact 回归

**一条命令**（每次改完代码跑一次）：

```bash
bash run_regression.sh
```

## 这套 pact 管什么

「**产出 ↔ 消费**」契约：runner 获取层声明的每个产出，都被 module/gate 实际消费；
每个消费引用，都有对应产出。契约单一真相源在 `scripts/lib/data_contracts.py`。

| 文件 | 角色 |
|------|------|
| `scripts/lib/data_contracts.py` | 契约注册表（17 scene：produces/consumers/confidence/priority/cost/depends_on/fallback） |
| `scripts/verify_data_contracts.py` | 契约 CI（断言型，hard=error / warn） |
| `test_data_contracts.py` | 反例测试（CI 健全性 + 真实注册表零 error + 已知暴露面锁定） |

两道防线：
1. **契约 CI** 跑真实注册表 → 必须 0 error（orphan/brokenConsumer 是 hard）。
2. **反例测试** 证明 CI 自身能抓违例（伪注册表注入 orphan/broken/coverage_only…），
   且锁定已知 warn 暴露面（s55 coverage_only、priceHighest_52week consumed=False、
   7 项 non_confirmed 断链候选）——防 regression 把该暴露的问题静默吞掉。

## 何时跑

- 改了 `data_contracts.py`（任何 produces/consumers/confidence 调整）
- 改了 `verify_data_contracts.py`
- 给某 scene 加/删产出或消费方（如新 module 消费某字段、某 gate 改依赖）

## 边界（这套 pact 不管）

运行时回归在 `gate-audit-20260704/fixtures/`，改 runner/gate/futu_client 后另跑：

| 那套 fixture | 管什么 |
|---|---|
| `test_futu_call_api.py` | futu_client 限流嗅探 / 缓存 / 熔断（离线） |
| `test_futu_fetchers_regression.py` | fetch_futu_overview/forecast 形状 + throttled 降级 |
| `test_gate_throttled.py` | 10 份冻结 snapshot self_score delta |
| `gate_fixture_test.py` | 27-gate verdict 0 漏报总闸 |

## 设计备忘

- pact = consumer-driven contract：registry 声明 produces/consumers，CI 断言双向闭合。
- 置信度分级：`confirmed`（hard fail）/ `assumed` / `unverified`（warn）——逐步硬化路径，
  字段形状经单股真连/mock 验证后升 `confirmed`，CI 自动收紧。
- S2 已上线 schema 覆盖 CI（校验3，warn-only）；S5（_EXPECTED_SCENES 派生）待落地，
  对应反例以 `@skip` 占位，**不伪测不存在的 check**。
