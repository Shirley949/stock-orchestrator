# 规则实证档案（SKILL.md 规则的 RCA/审计数据存档）

> **何时读**：需要追溯 SKILL.md 取数硬规则/C-4 簿记/Gate 修复纪律的实证出处时（`_research/` 前缀=不自动加载）。规则本体驻留 SKILL.md，本文件只存证据。

## 取数硬规则 6（compact/续接后取数仪式）RCA

2026-08-25 三会话 RCA：compact 后第一个取数动作锚定整段写作期行为——首动作 json.load 的段内手写 26 处/覆盖率 47.8%，首动作 `--list` 的仅 6 处/83.4%（token 审计 [v4] 行可量化复验）。

## 取数硬规则 1-5（视图优先/阶梯降级）token 审计实证

- 视图已在 runner 落盘时完成裁剪/反转（desc 最新在前）/换算（%·亿元）：kline 视图 4.8K vs raw 146K（-96.7%）。
- 688048 会话审计：手写 json.load 35 处 / 32,278 chars result / CLI 覆盖率仅 57%；其中 29 处 any 实测可达且 **any 输出全部 ≤ 手写**（top10 1,887 vs 3,790c、backtest 327 vs 2,380c）——手写不是省 token 的理性选择，是缺规范的训练默认。
- 数值已对拍验证与 raw 分毫不差（41 股普适）。

## C-4 现场验收簿记语义（cron 运行态细节）

单一真相源 = `regression-tests/trap_ledger_scan.py` docstring。要点：暴露探针（当窗报告 grep 触发形态）+ 窗口递减/达标关闭/展期/降级 + warn→硬断言翻转，自动落账 `references/trap_ledger_acceptance.yaml`，scan 首行与 engine_pending 并排自报；**零暴露 ≠ 安全**——关闭须暴露达标（分位≥3/否定句≥2/定增≥1）；方向局限=现场只证假阳性方向，假阴性由 corpus+归档重放守。
