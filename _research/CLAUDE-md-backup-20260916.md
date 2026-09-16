# 第 0 条 · 最高权重：加载层只写现行执行指导

> **适用面：本文件、memory、SKILL.md、代码注释——一切被 LLM 加载的文本。改 memory / skill / 代码时一律 follow 本条。**
> 只写「现在怎么做 / 勿做什么 / 注意什么」。一切变更记录——改了什么、何时改的、为什么改、实证数据、RCA 出处、版本/日期变迁、「已修/已废/已退役」类状态叙事——**只进 REFACTOR_LOG（唯一 changelog），禁入加载层**。
> 例外仅两个：① 宪法②要求的规避条款须带工单号+失效条件；② trap_ledger 状态字段（landed/pending）按其自身 schema。

# 行为准则

减少常见 LLM 编码错误的行为准则。可根据需要与项目特定指令合并。

**权衡：** 这些准则倾向于谨慎而非速度。对于简单任务，自行判断即可。

## 1. 先思考再写代码

**不要假设。不要隐藏困惑。把权衡摆到台面上。**

在动手实现之前：

- 明确说出你的假设。不确定就问。
- 如果存在多种理解方式，全部列出来——不要默默选一个。
- 如果有更简单的方案，说出来。该反驳就反驳。
- 如果有什么不清楚的，停下来。说明哪里让你困惑。提问。

## 2. 简洁优先

**用最少的代码解决问题。不写投机性代码。**

- 不加超出需求的功能。
- 一次性代码不搞抽象。
- 没人要求的"灵活性"和"可配置性"不要加。
- 不要为不可能出现的场景写错误处理。
- 如果你写了 200 行但 50 行就能搞定，重写。

问自己一句："一个资深工程师会说这写复杂了吗？"如果是，简化。

## 3. 精准修改

**只动必须动的地方。只清理自己制造的问题。**

编辑已有代码时：

- 不要顺手"改进"旁边的代码、注释或格式。
- 没坏的东西不要重构。
- 匹配现有风格，即使你会用不同的写法。
- 如果注意到不相关的死代码，提一嘴就好——别删。

当你的修改产生了孤立代码时：

- 移除因你的改动而变成未使用的 import、变量和函数。
- 不要动原本就存在的死代码，除非被明确要求。

检验标准：每一行改动都应该能直接追溯到用户的需求。

## 4. 目标驱动执行

**定义成功标准。循环验证直到确认通过。**

把任务转化为可验证的目标：

- "加验证" → "为非法输入写测试，然后让测试通过"
- "修这个 bug" → "写一个能复现它的测试，然后让测试通过"
- "重构 X" → "确保重构前后测试都能通过"

对于多步骤任务，列出简要计划：

1. [步骤] → 验证：[检查项]
2. [步骤] → 验证：[检查项]
3. [步骤] → 验证：[检查项]

强成功标准让你能独立循环推进。弱标准（"让它能跑"）则需要不断澄清。

## 5. 通用代码准则

**硬规则，写任何代码都适用。**

1. **检查项两极验证**：新增断言/布尔 flag/校验逻辑，完工前正例反例各跑一次，亲眼见过 True 和 False 两种取值。
2. **键名/路径映射是裸字符串合同**：改数据结构（加信封层、dict↔list、改布局）时，必须 grep 反查所有硬编码该路径的映射表/消费方。读错键不报错，静默恒 None。
3. **批量操作原子性 + 输出诚实**：先全部校验、后统一写入，任一步失败零写入。打印的「成功」必须与落盘状态一致。
4. **测试基线固化行为，不固化正确性**：有意行为变更撞上回归/parity/golden 失败时，禁回退修复换绿。正确动作：回放冻结输入做 diff-scope 证明（逐单元 diff == 且仅 == 预期变更面）→ 外科式刷新基线 → 全量回归。
5. **同一语义只允许一个实现**：切片/解析/格式化等共享逻辑统一走一个 helper，需要时 import，不内联复制。
6. **副作用推到边界，核心纯函数化**：网络/IO 集中在获取层，加工逻辑写成 `process(raw)` 纯函数。新建数据管道按此分层起步。

# Project Context

## Stock Analysis Skills（模块化架构，按需加载）

> **架构原则：** orchestrator 是唯一入口，子 Skill 的 SKILL.md 只放索引，详细内容在 `references/` 子文件中按需 Read。

### 入口 Skill（永远全量加载）

| Skill | 路径 | 职责 |
|-------|------|------|
| **stock-orchestrator** | `~/.hermes/skills/stock-analysis/stock-orchestrator/SKILL.md` | 主控入口：模式判定(A/B) + Phase 路由 + 混合模式处理 |

### 子 Skill（SKILL.md 仅索引，子文件按需 Read）

| Skill | SKILL.md 路径 | 子文件目录 | 职责 |
|-------|-------------|-----------|------|
| **数据源评级** | `~/.hermes/skills/stock-analysis/data-source-registry/SKILL.md` | `references/catalog/` | 数据源质量单一真相源（A/B/C/D 评级 + 动态降级） |
| **数据路由** | `~/.hermes/skills/stock-analysis/financial-data-routing/SKILL.md` | `references/scenarios/` | 拉什么数据、用哪个 API、怎么降级（场景清单见 SKILL.md 索引，数量不固定，勿硬编码） |
| **报告质量** | `~/.hermes/skills/stock-analysis/stock-analysis-quality/SKILL.md` | `references/modules/` | 怎么写报告（报告模块体系 + Gate 自评分；清单见 `modules/` 目录与 `gate_definitions.py` 的 `check_g*`） |

### 加载顺序（严格按此执行）

```
1. stock-orchestrator/SKILL.md          ← 唯一入口，全量加载
2. data-source-registry/SKILL.md        ← 评级体系索引
3. data-source-registry/references/runtime-probe.py  ← 运行时探针（按需，API失败时才触发）
4. financial-data-routing/SKILL.md      ← 路由索引（含 Step0 模式校验）
5. 按模式 Read 场景子文件：               ← 按需加载
   - 场景面单一真相源 = routing SKILL.md 场景索引 + runner `fetch_for_mode` 实拉 scene（本文件勿维护副本）
6. stock-analysis-quality/SKILL.md      ← 报告索引
7. 按模式 Read 模块子文件：               ← 按需加载
   - 模块面单一真相源 = orchestrator SKILL.md Phase 3 JIT 表（A 12 模块 + m11 延迟读；B 见 JIT 表 B 行）
```

### 模式判定规则（orchestrator Phase 0）

判定权威 = `generate_checklist.py` `detect_mode`（词表/优先级/边界唯一真相源，勿在本文件维护副本）：**A：完整**＝全部 Phase+全部模块；**B：当日**＝仅技术面+操作建议。

### Runtime Probe（运行时探针）— 按需触发

- 脚本：`~/.hermes/skills/stock-analysis/data-source-registry/references/runtime-probe.py`
- **不作为必经步骤**，仅在后续 API 调用失败时按需运行做诊断
- 同日首次运行：探测核心 API（清单见 `runtime-probe.py` `CRITICAL_APIS`），~5s，结果缓存到 `~/.cache/skill-probes/YYYY-MM-DD.json`
- 同日再次运行：读缓存，瞬间返回
- 探针发现的异常覆盖静态评级（session override）

### 🗂️ `_research/` 目录约定（非运行时素材归属）

- 各 skill repo 内 `_research/` = **非运行时**研究/保级素材（API 速查卡、独有流程文档等）；`_` 前缀 = **LLM 不自动加载**，grep 用 `--exclude-dir=_research` 一键排除。运行时资源只放 `references/`
- 新文件先 grep 引用（断空必验），按分类法归类：死退役代码/死日志/stale 重复 → `git rm`；保级孤儿/研究卡 → `_research/`；分类法全文见 `financial-data-routing/_research/README.md`
- 退役/变更的「为什么」写进 REFACTOR_LOG（唯一 changelog），**不再另起 `v4_*`/`regression_log_*` 单文件**
- 树卫生检查（每 phase 收尾跑）：skill 根 `*.md` ⊆ `{SKILL, README, REFACTOR_LOG}.md`，root 冒出新 .md 立即定性归类

### ✍️ SKILL.md 写法范式（P3+P4 编辑准绳）

> 渐进披露标尺（skill-creator/financial-services 运营范式）。新增/改 SKILL.md 先过两问：「触发判据藏 body 里了没？」「ALL-CAPS 是否只留命脉规则？」

1. **description = 唯一触发器**：`what + when + 触发词` 全放 YAML `description`（触发判定时唯一被读的字段）；body 触发后才载——判据只藏 body = 永不触发。
2. **自由度匹配脆弱性**：脆弱操作（数据拉取/gate/数值校验/降级）→ 低自由度（确定性脚本/严格 schema）；开放决策（叙事/解读）→ 高自由度（散文/示例）。分层准绳：**脆弱的归引擎，开放的归散文**。
3. **5 手法**：真实示例 > 抽象解释；具体容差（"5%"）代替模糊词（"合理范围"）；反模式红旗（`❌ 错在…`）；ALL-CAPS 只留 1-2 条命脉规则；输出 schema 钉死（字段名/顺序/必填）。
4. **do-not-include**：skill 内禁 README/CHANGELOG（git 存历史 + 膨胀加载）；变更记录写 `REFACTOR_LOG.md`。
5. **行数/分层**：SKILL.md 默认 ≤500 行，逼近则按渐进披露外移 ref；`references/` 仅一层深；**>100 行的 SKILL.md 带 TOC**；ref 开头带类别披露（scenario=触发/职责/时机；module=目的/权责边界/数据白名单；catalog=目的/执行时机）。

### 禁用 API 与场景面口径（详情=场景文档，本文件不维护副本）

| API | 状态 | 替代 |
|-----|------|------|
| `stock_gdfx_free_holding_detail_em` | **禁用**：恒返 None | 股东户数派发信号（`s8_a_share.processed`） |

> 龙虎榜（个股席位）、北向资金（外资持仓）、股东户数、资金流、估值/评级/目标价的 API 选型、端点陷阱与降级链，单一真相源=routing 场景文档：龙虎榜→`scenarios/lhb.md`、北向→`scenarios/northbound.md`、资金流（历史序列端点限流/当日快照/全市场排行陷阱）→`scenarios/s3-fund-flow.md`、股东与两融→`scenarios/s8-a-share.md`、估值与一致预期（westock 腾讯源）→`scenarios/s4-rating.md`。拉对应 scene 前先读该文档。

### ⚠️ Skill 依赖规则（引用 = 必须执行）

当 Skill A 引用 Skill B 时，**必须同时加载 A 和 B**。引用不是"参考"，是"必须执行"。
→ 原因：不加载被引用方 = 引用步骤缺上下文 → 半执行/误执行。典型：quality/routing 引用 registry 的数据源评级而不加载 registry → LLM 自行评估数据源 → 违反单一真相源、可能选到已降级/退役源。

### 子文件清单（单一真相源 = 各 Skill 的 SKILL.md 索引，勿在本文件维护副本）

scene 清单 → `financial-data-routing/SKILL.md`；模块清单 → `stock-analysis-quality/SKILL.md`；catalog 清单 → `data-source-registry/SKILL.md`（新增/改名文件只改各索引，本文件不跟）。

### ⚠️ 环境约束

| 工具 | 状态 | 替代方案 |
|------|------|---------|
| `WebSearch` | ✅ 可用（链路见触发分册索引·工具卷） | — |
| `WebFetch`（内置） | ❌ 不可用 | `mcp__web_reader__webReader`（URL→markdown，实测可用）或 `curl` |
| AkShare | ✅ 可用 | — |
| curl | ✅ 可用 | — |
| pdfplumber | ✅ 可用 | — |
| Playwright + Chromium | ✅ 可用（仅无头模式） | 浏览器自动化（打开网站、抓取动态内容）— 本机无 GUI，只能 headless |
| GLM 配额查询 | ✅ API 直查（见触发分册索引·工具卷） | 无需登录控制台 |

### 📚 触发分册索引（按需 Read，勿预载）

| 触发词（任务侧措辞） | 分册路径 | 何时读 | 摘要 |
|---|---|---|---|
| 改 pipeline；新增/修改 scene、gate、信封、时序信号；读三表/双兜底 | `~/.hermes/skills/stock-analysis/stock-orchestrator/_research/engineering-paradigms.md` | 动码前 | 黄金/信封/读三表/断言全文 |
| 发布；上传/腾讯文档/tdx；彩排/查重 | `~/tdx-publish-v4/SOP.md` | 发布动作前 | 五步闸流程 |
| 搜索/websearch；Exa/豆包/Tavily/Firecrawl；playwright/chromium/浏览器自动化；GLM 配额/quota | `~/.claude/docs/tooling-playbook.md` | 任一工具动作前 | 链路序+调用法 |
| 龙虎榜/北向/股东户数/资金流/估值 API 细节 | `~/.hermes/skills/stock-analysis/financial-data-routing/references/scenarios/`（lhb·northbound·s3-fund-flow·s8-a-share·s4-rating） | 拉对应 scene 前 | 端点陷阱+降级链 |

### 🔴 工具红线（恒驻，不可触发化）

- websearch 链路序恒定：**Exa →（当日额度尽）→ Firecrawl / 豆包 → 内置 WebSearch / Tavily → Playwright 兜底**；**豆包 500 次/月必须省**（单次全量分析 ≤10 次）；**Exa 并发 ≤2**。

---

## 提交 skill 改动到 GitHub（双仓库防发散）

每个 skill 目录是**独立 git 仓库**（远端 `github.com:Shirley949/{skill}.git`）。`~/.hermes/skills/stock-analysis/{skill}/`（**live 工作区，编辑在此**）与 `~/stock_analysis/skills/{skill}/`（父仓库 `stock_analysis` 的 submodule）是**同一远端的两份独立 clone**（非软链），**会各自提交、发散**——`git push` 常被拒 `fetch first`。

**最佳实践（在 live 副本 `~/.hermes/skills/stock-analysis/{skill}/` 操作）：**
1. push 前先 `git fetch origin`，再 `git diff origin/main main --stat` 看真实**内容**差（不看提交 hash——本地"领先"提交常是远端的**重复 hash**，标题相同内容一致）。
2. 若除新增文件外内容一致 → `git reset --soft origin/main` 重接基准，重提一个干净 commit，再 fast-forward 推送。
3. **禁 `git push --force`、禁 rebase 重复历史**（会丢工作 / 污染远端）。
4. 速查卡（`*-api.md`）落点 `references/api-templates/`（**非仓库根目录**）。
5. 子模块镜像 `~/stock_analysis/skills/{skill}/` 是另一份 clone，**不会自动跟随** live 副本——需单独同步 + 更新父仓库 `stock_analysis` 的 submodule 指针（另起 commit）。

---

## Gate 修复验证（硬规则）

1. **先跑必FAIL反例**：反例真FAIL才证明进了执法分支；反例PASS=豁免短路（空段/无真值），后续正例全为假验证。
2. **宽松化修复后重验反例仍FAIL**（防执法力回退）；修后冒出新FAIL先判「双bug对冲拆开后的真漏报」，勿直接修回。
3. **强制消费gate×对拍gate死锁**：gate要求报告必写字段X时，X须在对拍gate的truths集，否则写也FAIL不写也FAIL（G52的ATR止损价∉G63 truths）。
4. 多源scene判has_value须兜底items[]（latest_period.value可能被占位行'—'抢先，真值在items[1]）。
5. **FAIL reason 真值化合同**：reason 自带快照真值 + 违规行 `L{n}:『原句』` + 可照抄修法——修报告**直接照抄 reason 修法**，勿重查快照/读 gate 源码；带 **`[数据层]` 前缀**的 FAIL = 数据拉取失败臂，**不改报告**（fix 不含改稿动词），重跑对应 scene 拉取或上报数据源异常。
6. **新 gate 代码禁裸 bool FAIL**：FAIL 臂必须 `return GateResult(passed=False, reasons=[真值+行号+修法])`——verify_gates 只消费 verdict，reason 升级 verdict 中性（零翻转）；`verify_gates` 对 bool 返回打 **warn**，全库审计由 `test_diag_contract.py` 把守。

> 写读三表 / 新时序 scene / 信号信封相关代码前，必读 `stock-orchestrator/_research/engineering-paradigms.md`。

## 规避条款注册纪律（宪法②）

> 凡 ledger/memory 中的**写作侧规避条款**，必须注明针对的引擎工单号（trap_ledger `signature`）与失效条件；该工单 **landed 之批次，规避条款同批复审删除**。防化石层——规避条款在引擎修复后残留 = 下批删真数据的隐性指令。

## Memory 路由口径（宪法③）

> **路由三分**：引擎缺陷 → `trap_ledger.yaml`（repo 真相源，新 trap 先入 ledger）；跨票程序性/根因族 gotchas → memory 白名单文件（`publish-chain-gotchas`、gate 族根因 8 份等，合法层）；单票教训 → 无 home，不落盘（写进该票目录或丢弃）。
> **白名单升级触发器**：memory 白名单条目**当日复发 ≥2 次或跨会话复发** → 升格为 CLAUDE.md 硬规约或引擎机械化前置，不再留在 memory 散点层（散点 memory 不产生行为改变；只有硬规约 + 机械化闸门防复发）。
> **retro 记分卡**：复盘审计中，白名单文件的合规增改记「白名单层合法落笔」，**不计违规**。

## A 类机制化门槛

> 执行违例**当日 ≥2 次或跨会话复发 → 加机械化前置**（checklist 内联命令 / 引擎预检）；n=1 不机制化。

## 修向政策（宪法⑧）

> **裁决规则**：同一引擎缺陷类**当日复发 ≥2 次**、且引擎收窄一次性成本 < 写作侧规避实测成本总和 → **默认引擎修**。成本例外（收窄明显更贵）须书面记录，不得默认走报告侧。
> **观察期**：起点 2026-09-03（G71④ landed），零复发零新假阴；如再现新假阴按下方转正条件退回评审。
> **写作侧规避纪律**：见宪法②（工单 + 失效条件 + landed 批删除）。
> **转正条件（数据裁决，非会议再议）**：落地后下一批 G71④ 失败事件 = 0 且收窄零新假阴 → 转正为正式条文；出现新假阴 → 退回评审。

## Compact 续接取数仪式（硬规则）

> context compact / 会话续接后，**第一个取数动作锚定整段写作期取数行为**——首动作 `--list` → 手写少、覆盖率高；首动作 json.load 全树探查 → 段内手写激增。本节每轮 system 注入、compact 免疫，是主防线；orchestrator SKILL.md 取数硬规则第 6 条为同一规则的正常流全量版（compact 后不在上下文）。

1. compact/续接后**第一个取数动作必是 `snapshot_view.py <snapshot> --list`**（重建全部视图 + scenes 目标空间认知——合法视图以 --list 输出为准，勿凭记忆写视图名）。
2. 存在性/结构验证用 `--list` 或 `any <路径> --depth 1`（路径不存在=显式报错，即存在性答案）——**禁 json.load 全树 walk 找键**。
3. 连续 2 处 json.load = 行为已分叉，立即停下改走视图/any。
4. compact 后另有 C2 hook 自动注入续接上下文（模式路由 + 清单/骨架台账指针，≤2KB）；模式A 骨架台账经 generate_checklist `--skeleton-out` 生成、`load_skeleton.py` 翻页——已读项勿重读。

## 改完代码必跑回归（Regression）

> **改 stock-analysis 任何 `.py` 之后必跑**，`exit 0` 才算完成（零回退总闸）：

```bash
bash ~/.hermes/skills/stock-analysis/stock-orchestrator/regression-tests/run_regression.sh
```

一键串联两层、任一失败非零退出：
- **契约层**（恒跑）：`data_contracts ⇔ consumers` 双向闭合，**全部 scene 必须 0 error**（orphan/brokenConsumer = hard；计数规则见上「断言必验」）。
- **运行时层**（gate-audit 在线时跑）：`gate_fixture_test` **全部活跃 gate 漏报 = 0**。契约层另含 `test_fixed_layer_index.py`（固定层分册索引对拍）、`test_skeleton_schema.py`（骨架 schema + load_skeleton 台账翻页契约）、`test_c2_inject.py`（C2 注入器 A/B 路由 + ≤2KB 预算）、`test_westock_integration.py`（westock_client 解析 + 三 fetcher reshape 形状）、`test_diag_contract.py`（gate FAIL reason 诊断契约：全库零裸 False 审计 + [数据层] lint + 崩溃面）。
- 尾部输出 **`engine_pending`** 指标行（root_cause=engine 且未 landed 的 trap_ledger 存量 = 引擎欠修欠账）。

> ⚠️ 契约测试**只属于** `stock-orchestrator/regression-tests/`——**禁止**在 `gate-audit-20260704/fixtures/` 放契约测试副本（该目录只存运行时层 fixtures，两处副本会 drift）。

---

## 回归测试集（Regression Test Datasets）

> **速查表：** 用户说"季报测试集"或"研报测试集"时，直接使用对应路径，无需搜索。

| 简称 | 路径 | 内容 |
|------|------|------|
| **季报测试集** | `/home/ubuntu/regression-test-dataset/一季报测试集-DO-NOT-DELETE/` | 2026Q1 季报 PDF（同批公司，~140+份） |
| **研报测试集** | `/home/ubuntu/regression-test-dataset/2026研报测试集-DO-NOT-DELETE/` | 2026年券商研报 PDF |

**用途：** 回归测试、批量验证 Skill 覆盖度、端到端性能测试

**文件命名：** `{年份}{报告类型}-{公司名}-{股票代码}-{行业}-{页数}p.pdf`
