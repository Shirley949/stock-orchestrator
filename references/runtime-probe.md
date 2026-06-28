# Runtime Probe（运行时探针协议）

> **目的：** 解决"静态评级 vs 运行时事实"脱节问题。每次会话第一次拉数据前，对关键 API 跑 health check。
> **实现脚本：** `~/.hermes/skills/stock-analysis/data-source-registry/references/runtime-probe.py`

---

## 8 个关键 API 清单

| 序号 | API 名称 | 用途 | 状态 |
|------|---------|------|------|
| 1 | `stock_hsgt_fund_flow_summary_em` | 北向资金汇总级 | ⚫ 已废弃(返回0.0) |
| 2 | `stock_zh_a_spot_em` | 实时行情（东财源） | ⚠️ 频繁断连 |
| 3 | `stock_zh_a_daily` | K线首选源（新浪源） | ✅ 稳定 |
| 4 | `stock_financial_report_sina` | 三表数据 | ✅ 稳定 |
| 5 | `stock_comment_detail_zlkp_jgcyd_em` | 机构参与度（评级 fallback） | ✅ 稳定 |
| 6 | `stock_news_em` | 个股新闻 | ✅ 稳定 |
| 7 | `stock_yjyg_em` | 业绩预告 | ✅ 季度更新 |
| 8 | `curl hq.sinajs.cn` | 新浪行情降级源 | ✅ shell级 |

> **已移除的 API：**
> - `stock_gdfx_free_holding_detail_em`（股东持仓）：API 返回 None，已失效

---

## 缓存策略

```
~/.cache/skill-probes/YYYY-MM-DD.json   # 当日缓存
```

- 同一天多次会话能复用（避免每次新会话都跑 5 秒探针）
- 跨日自动失效（不会污染历史结果）
- 缓存文件格式：JSON，包含每个 API 的 status + latest_date

---

## 失败处理矩阵

| 故障情形 | 处理 |
|---------|------|
| 超时 > 10s | 信任静态评级，标注 [probe 未完成] |
| ImportError（akshare 损坏） | 信任静态评级 + 标注 [probe 失败] |
| ConnectionError（网络问题） | 信任静态评级 + 标注 [probe 失败]，建议用户检查网络 |
| probe 跑完但部分 API 异常 | session override 中降级该 API（评级 A → B 或 N/A） |
| probe 数据存在但 > 7 天前 | 触发 routing 场景十二的"陈旧"动态降级 |

---

## 与静态评级的联动

- 静态评级表是 baseline（data-source-registry）
- runtime probe 是"会话期间的覆盖层"
- 任一字段触发 4 类降级条件（5%偏差 / API 失败 / 陈旧 / 搜索结果稀少）→ 写入 session override
