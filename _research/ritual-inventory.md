# 仪式文档 inventory（cron 任务 / 复盘 prompt / 彩排脚本 三类实体索引）

> **何时读**：设置/修改/审计任何周期性仪式（复盘、验收簿记、彩排）之前（`_research/` 前缀=不自动加载）。孤儿 O5 收口产物。

## 1. cron 任务（周期触发实体）

| 实体 | 载体 | 状态 |
|---|---|---|
| nzx 项目 runner | 系统 crontab（06:08/18:08，`/home/ubuntu/projects` + flock） | 与股票分析体系无关，勿混 |
| 股票复盘 / trap_ledger `--field-acceptance` 簿记 | **无 durable 载体**（`~/.claude/scheduled_tasks.json` 空，crontab 无） | 靠会话内自觉/用户触发——REFACTOR_LOG 各批「cron 收尾」措辞指此 ad-hoc 形态 |

## 2. 复盘 prompt（事后审计实体）

- **无固定 prompt 文件**；复盘产物唯一落点=各 skill 仓 `REFACTOR_LOG.md` dated 条目（带验证链）。
- **B 复盘 prompt 落点（本 inventory 钉定）**：B 票收尾**会话内联**（Phase 6 token_audit `--mode B` + 加载集 diff 核对行，批 3.2 落地后自动产出）——不建 durable cron：B 复盘按票触发非按时刻触发，样本量低，durable cron 是过度机制化。
- token 审计命令：`python3 ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/token_audit.py <transcript> --stock <code> --mode B`，产出存 `~/analysis_report/token_audits/`。

## 3. 彩排脚本（发布链验证实体）

| 实体 | 触发 | 位置 |
|---|---|---|
| `tdx_publish.py self-test` | vendor skill 更新后 / 升级脚本后 | `/home/ubuntu/tdx-publish-v4/tdx_publish.py`（流程见 `~/tdx-publish-v4/SOP.md` 卷2） |
| 彩排档全链（create→read-all→verify→trash） | 每次发布会话先跑（MCP 行为漂移兜底） | 同上 |
| 再审计触发器 | verify 连续 2 FAIL / 不认识的 mdx2record 报错签名 | 条款在 SOP 卷2 尾部 |

## P5 盲测立卡（工单）

- **目标**：模式 B 分层基线正式判读（B 模块占比独立基线，替代退役的 BASE_MOD_PCT 对 A 基线混比）
- **判据**：B 票累计 n≥10 后按记分卡条款 D 判读（阈值只作用累计 n≥10；单票不计判定）
- **当前状态**：等待 B 票自然累积（盲测层已有 12/12 A/B 混合语料 + 20 as-of 快照，见 routing 仓 2026-08-26 条目）；到达后 token_audit 三桶汇总（批 3.3）出首份独立基线读数
