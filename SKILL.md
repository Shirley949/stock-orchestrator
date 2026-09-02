---
name: stock-orchestrator
description: >
  股票分析的入口与主控——当用户消息涉及股票分析（股票代码、股票名称、或"分析/看看/买不买/估值/风险/事件"等动词）时，必须最先加载本 Skill。
  本 Skill 是 stock-analysis-quality / financial-data-routing / data-source-registry 的统一入口，禁止跳过。
---

# Stock Orchestrator（主控 Skill，永远全量加载）

> **本 Skill 是股票分析的唯一入口。** 加载后，禁止 Skill 系统自动加载其他股票相关 Skill——它们的加载由本 Skill 通过 Read 显式触发（核心清单见 `skill_dep_graph.py` `MODE_FORCED_SKILLS`；数据源 skill 经引擎 client 集成）。

---

## 目录

- [🔴 强制约束（违反则质量无法保证）](#强制约束违反则质量无法保证)
- [触发条件（必须最先加载）](#触发条件必须最先加载)
- [Phase 0：执行清单生成 + 分析模式判定](#phase-0执行清单生成--分析模式判定)
- [Phase 1：会话级初始化（始终运行）](#phase-1会话级初始化始终运行)
- [Phase 2：数据拉取（按模式定制场景路径）](#phase-2数据拉取按模式定制场景路径)
- [Phase 3：报告生成（仅按模式加载需要的模块）](#phase-3报告生成仅按模式加载需要的模块)
- [Phase 4：输出 + Gate 校验（强制硬关卡）](#phase-4输出--gate-校验强制硬关卡)
- [Phase 5：调用契约（详见 `references/exec-protocol.md`）](#phase-5调用契约详见-referencesexec-protocolmd)

## 🔴 强制约束（违反则质量无法保证）

> **以下强制约束是脚本工件驱动的硬性协议，不是建议。**

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

### 约束 5：Gate 硬关卡（单一出口：sidecar + 指针行）
报告写完后、输出前 → **必须**运行 `verify_gates.py`，它会**自动产出 sidecar**（分数唯一真相源）：
```bash
python ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/verify_gates.py \
  --report /tmp/analysis_report_<code>.md \
  --data-snapshot /tmp/runner_snapshot_<code>.json \
  --profile full        # 或 quick
# → 产出 /tmp/analysis_report_<code>.md.verified.json（sidecar）+ 退出码
```
- **路径必须 run-scoped（带 `<code>`，2026-09-01 F3）**：`/tmp` 是跨会话共享区，裸 `/tmp/analysis_report.md` 会被并行分析会话互覆（实证：000887 审计中报告被 688385 会话覆盖）；verify_gates 同时校验 **report mtime ≥ snapshot mtime**（报告早于快照 = 写错了文件/陈旧拷贝，exit 2）。
- **m11 区只放指针行，禁止手填分数**：`[verified: self_score=N profile=full | see analysis_report.verified.json]`
- **c70 打勾必须用 sidecar 路径**（`update_checklist.py --check c70 --evidence-from /tmp/analysis_report_<code>.md.verified.json`）——`verdict==PASS` + `self_score>=80` + 新鲜度由代码强制，任一不满足 `sys.exit(1)`。
- `verify_gates` 退出码 1 = `verdict==FAIL`，报告不能输出，必须补全失败的 Gate。
→ 原因：Gate 校验是最后一道质量关卡。**分数、verdict、≥80 阈值全部由代码强制**（根治"三套分数 87/93/95"漂移：手填分数从不进报告，引擎产出无下游消费）。

### 约束 6：两段式问题映射
清单中的"用户问题映射"表，映射表匹配的标记 `映射表`，未匹配的标记 `[LLM兜底]`。
对于 `[LLM兜底]` 项 → 在主线程中判断需要什么数据，回写到清单。

### 约束 7：审计任务 fork 执行 + 独立复验（2026-09-01 WP-M 固化）
结构审计/大范围复核类任务 → fork 执行，主会话**独立复验后才收口**（回归 exit 0 / git 推送态 / 抽验关键修复点）。
→ 原因：审计者不给自己的作业打分（WP-M 实证：fork 报告 4 组迁出/4 对矛盾裁决，主会话复验全中才置 ✅）。

### 约束 8：机制宪法两条（2026-09-01 收官批）
1. **合同必写执法者**：写入 SKILL/模块文档的任何机制、数据合同、路径约定，条目必须注明**执法者**（gate 号/脚本/校验命令）；无执法者的合同 = 口头约定（漂移起点）。存量四条已补登记：F1 降级披露→**G72**；F8 web_research 机制→**G21/G45**；G54 ADX 双路→**G54 值对拍**；数值对拍容差→**G63**。
2. **指标必绑留盘点位**：定义/变更任何质量指标（收敛率/覆盖率/token 降幅…）必须同时绑定**留盘点位**（哪个文件哪个字段可复查实测数），此后每批次 REFACTOR_LOG 带实测数——无留盘点位的指标无法审计，等于没定义。记分卡阈值（如首轮收敛率 ≥90%/80-90%/<80%）**只作用于累计 n≥10**；单票展示不计判定（2026-09-01 记分卡条款 D）。

---

## 触发条件（必须最先加载）

以下条件满足任一即触发（OR 关系）：

- 股票代码（6 位数字 / SH·SZ 前缀 / .SS·.SZ 后缀）
- 分析动词（代表例："分析 / 看看 / 买不买 / 估值 / 风险 / 事件"）——**全量权威清单见 `scripts/generate_checklist.py` 的 `detect_mode`（`mode_a_triggers` / `mode_b_triggers`）**，此处不另抄全集（手抄副本 = 漂移源）

**兜底规则：** 无股票代码时，只要有分析动词就触发。opencode 用 `websearch` 搜索确认股票代码后继续执行。

---

## Phase 0：执行清单生成 + 分析模式判定

> **⚠️ Phase 0 的第一个动作必须是运行 `generate_checklist.py`（见约束 1）。**
> 脚本会自动判定模式、映射用户问题、解析 Skill 依赖图，输出完整执行清单。

| 触发关键词（代表例） | 模式 | 后续 Phase 加载 |
|-----------|-----|----------------|
| 深度分析 / 帮我看看 / 买不买 / 估值 / 风险 / 事件（全量见 `generate_checklist.py` `detect_mode` 的 `mode_a_triggers`） | **A：完整** | Phase 1 + 2 + 3 + 4 |
| 今天买不买 / 盘中 / 能加仓 / 要不要卖（全量见 `mode_b_triggers`） | **B：当日** | Phase 1 + 2 |

> **模式判定权威 = `generate_checklist.py:detect_mode`（代码）**；本表仅代表例 + 指针，禁手抄全集（第三份手抄 = 漂移源）。

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
   - **westock 数据**: westock_client.py（分析师评级/目标价/资金流/年度预测/EBIT 实际值，腾讯源 npx CLI，无限流）；估值 PE/PB/总市值用 akshare baidu（scene：`valuation_snapshot` / `consensus_forecast`）
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

### 模式 A 调用顺序

runner 一条命令全量并发（scene 编排 = `fetch_for_mode` 阶段A `_TASKS` + 阶段B 串行 s4 技术；
年报维度 s36 全 off-PDF：东财 datacenter + westock 分红，cninfo PDF 管道已退役）。

**拉完后第一步（强制 stop-gate）**：

```bash
python3 ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/precheck.py /tmp/runner_snapshot_<code>.json
```

exit 1 = 停机不写报告；其 stderr 即完整「执行后验证」（_warnings / 财务摘要期数 / 主营构成三态 / 收单 N/12），**禁手写 json.load 验收**。

### 模式 B 调用顺序

```
并行：s2 行情（实时行情快照）+ s2 K 线（近 60 日，同源拉取）
串行：s2 技术指标（自算，依赖 K 线数据）
串行：s2 盘口解读（依赖实时行情）
```

### ⚠️ websearch 素材落 snapshot（单一机制，2026-09-01 F8 裁决）

用户要求 websearch（行业规模/全球份额/需求预测/新闻线索等）时，素材**必须**先经 runner 写回 snapshot 再引用——**禁止对话内贴 findings 直写报告**（同票两次运行结论漂移、G21 溯源无从执法）：

```bash
python ~/.hermes/skills/stock-analysis/financial-data-routing/runner.py web_research <code> \
  --snapshot /tmp/runner_snapshot_<code>.json \
  --items '<json | @findings.json>'     # [{source,title,url,published,content}, ...]
```

- 写回后 scene=`web_research_findings`；报告引用处带 `[src: snapshot.web_research_findings...]`（**执法者：G21 溯源 + G45 目标价/预测口径**；裸贴 findings = 溯源断裂）。
- websearch 是**发现**工具非**验证**工具：API 结构化数据是权威上游，冲突时以 snapshot 为准（CLAUDE.md 同款原则）。

---

## Phase 3：报告生成（JIT 模块加载 + 视图直读）

### ⚠️ 模块 JIT 加载（2026-08-20 起，替代「Phase 3 开始全量 Read」）

**写某模块的章节前才 Read 该模块文件**，不提前批量加载。按报告章节顺序（m12→m0→m1→m2→m25→m3→m4→m5→m6→m7→m8→m10）逐个即时加载——后段模块推迟 100+ 轮暴露，省 token 零信息损失（各 m* 内嵌硬约束提示已覆盖写作期避错）。

| 模式 | 报告涉及模块（按此顺序 JIT） | 延迟加载 |
|------|------------------------------|---------|
| **A** | m12 / m0 / m1 / m2 / m25 / m3 / m4 / m5 / m6 / m7 / m8 / m10 | **m11-gates.md：首次 verify 有 FAIL 时才 Read**（verify 输出自带失败原因，全过时不需要） |
| **B** | m38 / m3 / m36 / m37 / m6 | 同上 m11（m38=核心结论头块，B 报告置顶必写） |

### ⚠️ 数据读取：snapshot_view 视图直出（禁手写提取脚本）

写报告需要**任何** snapshot 数据（K线/三表/新闻/事件/股东/估值/资金/ESG/治理/研报…）时，**用 CLI 直出已裁剪视图**，不要手写 Python 提取脚本、不要整段 Read snapshot JSON：

```bash
SV=~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/snapshot_view.py
python3 $SV /tmp/runner_snapshot_<code>.json kline       # K线：recent30 desc + 52周/YTD/量能 stats
python3 $SV /tmp/runner_snapshot_<code>.json cash_flow   # 现金流 12 期（FCF/CFO净利比已算好）
python3 $SV /tmp/runner_snapshot_<code>.json income      # 利润表 12 期（毛利率/同比已算好）
python3 $SV /tmp/runner_snapshot_<code>.json mainfina    # 主要指标 8 期（单季同比/ROIC/偿债）
python3 $SV /tmp/runner_snapshot_<code>.json balance     # 资产负债表：最新4期×~32关键科目（含合同负债，G16 面）
python3 $SV /tmp/runner_snapshot_<code>.json timeline    # 事件五桶 risk/catalyst/future/fatal + 买卖压力/股东动态 verdict
python3 $SV /tmp/runner_snapshot_<code>.json technical   # 技术面：信号态+TD+fib/S&R/筹码+ATR（G63 真值面）
python3 $SV /tmp/runner_snapshot_<code>.json valuation   # 估值：quote+分位(pe/pb/ev_ebitda)+评级/目标价+EV
python3 $SV /tmp/runner_snapshot_<code>.json consensus   # 一致预期：westock+东财双年度表+时序+实际值
python3 $SV /tmp/runner_snapshot_<code>.json peer        # 同业：核心6指标表+rank+行业中位+相对大盘
python3 $SV /tmp/runner_snapshot_<code>.json annual      # 年报维度：D3分红/D4前十大/D7客户供应商/D8员工
python3 $SV /tmp/runner_snapshot_<code>.json news        # 新闻 high+medium 标题级
python3 $SV /tmp/runner_snapshot_<code>.json events      # 大事提醒投影
python3 $SV /tmp/runner_snapshot_<code>.json holder      # 股东户数信号期
python3 $SV /tmp/runner_snapshot_<code>.json --list      # 14 视图状态 + 顶层 scene 键（= any 的目标空间）
# any 探查（视图外数据的第一入口）：
python3 $SV /tmp/runner_snapshot_<code>.json any governance --depth 1                                # ① 顶层 scene 第一步（结构探查/字段发现）
python3 $SV /tmp/runner_snapshot_<code>.json any s35_research_reports.data --depth 1                 # ② 逐层下钻（猜深路径必报「路径不存在」，必须逐层）
python3 $SV /tmp/runner_snapshot_<code>.json any s1_financial.data.segment_composition --depth 2     # ③ 扁平小节 depth 2（主营构成/指标/computed_metrics/千股千评 s_stock_evaluation.data 同款）
python3 $SV /tmp/runner_snapshot_<code>.json annual --raw s36_annual_analysis.data.D4_top10_holders.0  # ④ 单行全文深读（独立 `--raw <path>` 亦可）
python3 $SV /tmp/runner_snapshot_<code>.json --raw s1_financial.data.balance_sheet --field 合同负债   # ⑤ 外科投影：单字段全期直出（行表→「日期: 值」单列；字段错=显式报错）
```

**取数硬规则（六条）**：

1. 14 视图优先——覆盖面见上表，先查再探查（尾部 footer/指针行已含稳定需求，如 balance 尾部即 8 期合同负债）。视图外的字段按**显式阶梯**降级：`视图 → any（结构探查 / ≥3 字段需求）→ --raw <路径> --field <字段>（外科投影，单字段全期直出）→ --raw（全量子树）`。**--field 分流**：每次调用总成本 ≈ 命令文本 100-150c + result——单/双字段 → `--field`；≥3 字段或结构未知 → 一次 `any --depth 2`（3 次 --field 已反超一次 any）。⚠️ 宽表（balance_sheet 类）`any -d2` 最贵（29.6K > --raw 6.4K > 视图 2.5K > --field 0.28K）——宽表取列必用 `--field`。
2. 视图没有的，**第一步必是 `any <scene> --depth 1`**（--list 的 scenes 行即目标空间），再逐层下钻或 `.N` 取单条——**禁猜深路径、禁 json.load 探查结构**。
3. **长列表纪律**：父层只看 `list x N` 计数（计数即答案，N=0 是真空结论）；要单条用 `.N` 下钻（`remind_records.0 --depth 1` = 920c；直接展开 95 条 = 77K token 炸弹——引擎 cap 只保底 10 条，cap 是底线不是配额）。
4. 关键词定位：any/视图拿行索引 → `--raw` 单行深读；grep 只取计数不取全文。
5. 跨 scene 计算先查 `computed_metrics`（fetch 期已算好）；确无可用的（全景/跨 scene 复合提取等 `--field` 不适用形态）才允许一次性 `python3 -c` 只打 ≤40 行摘要、**每会话 ≤2 次**，命令须带一行 `# rule5-surgical` 声明注释（审计单列豁免桶，超额 ⚠️）——唯一豁免通道，`--field` 落地后应趋零。**中段自查锚：写作/gate 修复中段任何 json.load 冲动 → 先 `--list` 对照挂载层，单字段需求直接 `--field`。gate 修复期取数同本规则**——gate FAIL 的 action_required 已带数据核对现成命令（GATE_HINTS），照抄即合规，勿再 sed 源码或手写 dump。
6. **compact/续接后取数仪式**（2026-08-25 三会话 RCA：compact 后第一个取数动作锚定整段写作期——首动作 json.load 的段内手写 26 处/覆盖率 47.8%，首动作 `--list` 的仅 6 处/83.4%；审计 [v4] 行可量化复验）：续接后**第一个取数动作必是 `--list`** 重建 14 视图 + scenes 认知；存在性/结构验证用 `--list` 或 `any <路径> --depth 1`（路径不存在=显式报错即答案）——**禁 json.load 全树 walk 找键**；连续 2 处 json.load = 行为已分叉，立即停下按规则 5 自查锚改走视图/any。本文件 Phase 0 加载、compact 后不在上下文——compact 场景由全局 CLAUDE.md「Compact 续接取数仪式（硬规则）」（system 层每轮注入、compact 免疫）兜底，两处为同一规则双载体。

**为什么（token 审计实证）**：视图已在 runner 落盘时完成裁剪/反转（desc 最新在前）/换算（%·亿元），kline 视图 4.8K vs raw 146K（-96.7%）。688048 会话审计：手写 json.load 35 处 / 32,278 chars result / CLI 覆盖率仅 57%，其中 29 处 any 实测可达且 **any 输出全部 ≤ 手写**（top10 1,887 vs 3,790c、backtest 327 vs 2,380c）——手写不是省 token 的理性选择，是缺规范的训练默认。数值已对拍验证与 raw 分毫不差（41 股普适）。**视图没有的字段才用 `any`/`--raw`，禁止绕过 CLI 直接 json.load 写提取脚本。**

---

## Phase 4：输出 + Gate 校验（强制硬关卡）

> **⚠️ 报告写完后、输出前，必须运行 `verify_gates.py`（见约束 5）。单一出口 = sidecar + 指针行。**

1. 将报告写入 `/tmp/analysis_report_<code>.md`（**run-scoped 命名，2026-09-01 F3**——裸固定路径会被并行会话互覆）
2. 运行 Gate 校验脚本（**自动产出 sidecar**；同时校验 report mtime ≥ snapshot mtime，报告早于快照 = 错文件/陈旧拷贝 → exit 2）：
   ```bash
   python ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/verify_gates.py \
     --report /tmp/analysis_report_<code>.md \
     --data-snapshot /tmp/runner_snapshot_<code>.json \
     --profile full      # 或 quick
   # → 产出 /tmp/analysis_report_<code>.md.verified.json（含 verdict / self_score / failed_gates）
   ```
3. **Gate 全过后归档到固定目录 `/home/ubuntu/analysis_report/`**（原始 md + sidecar + 发布副本三件套一起归档）：
   ```
   ~/analysis_report/analysis_report-<模型>-<股票名>-<代码>/   ← 每股一目录（用股票名+代码区分）
       ├── analysis_report-<模型>-<股票名>-<代码>.md          ← 原始报告（明文 [src:]，gate 执法用，永不剥离）
       ├── analysis_report-<模型>-<股票名>-<代码>.md.verified.json   ← sidecar
       └── analysis_report-<模型>-<股票名>-<代码>_publish.md   ← 发布副本（已剥 src）
   ```
   示例：`~/analysis_report/analysis_report-glm5.1-源杰科技-688498/analysis_report-glm5.1-源杰科技-688498.md`
   > `<模型>` = 当前会话模型简称（如 glm5.1）；同股重分析（模型/日期不同）各自成目录，不覆盖。
3. **如果 `sys.exit(1)`**（`verdict==FAIL`）→ 报告不能输出，必须按脚本提示补全失败的 Gate 后重跑。
   **FAIL 修法直接看 verify 输出**：action_required 自带 `💡 Gxx 修法` hint（GATE_HINTS，高频 gate
   败因+修法速查）。hint 不足再 Read `stock-analysis-quality/references/modules/m11-gates.md` 对应节；
   **禁止 Read `gate_definitions.py`**（178K 源码，历史上单次全读 ≈ 全部模块文件之和）。
   **reason 带 `[数据层]` 前缀 → 不改报告**：该 FAIL 是数据拉取层问题（改稿无效），动作=重跑对应
   scene 拉取或上报数据源异常，报告侧等数据修复后重验（G32/G33/G61 拉取失败臂均此语义）。
   **复发晋级（第 2 次必须落引擎）**：同一陷阱第 2 次复发 → 必须落引擎修复（trap_ledger 该签名置
   `root_cause=engine` + `status=inflight`→修后 `landed`），禁第 3 次报告级修补；`trap_ledger_scan`
   对 delta>0 条目自动打 🔴 新增 + ⚠️ 晋级提示行，cron 复盘按提示升级。
   **现场验收簿记（C-4，cron 收尾必跑；审计/人工跑数一律加 `--inspect` 只读——簿记写回仅限 cron 运行态）**：`python3 regression-tests/trap_ledger_scan.py --field-acceptance`
   ——暴露探针（当窗报告 grep 触发形态）+ 窗口递减/达标关闭/展期/降级 + warn→硬断言翻转，全部自动落账
   `references/trap_ledger_acceptance.yaml`，scan 首行与 engine_pending 并排自报；**零暴露 ≠ 安全**，
   关闭须暴露达标（分位≥3/否定句≥2/定增≥1）。方向局限：现场只证假阳性方向，假阴性由 corpus+归档重放守。
4. 在报告 m11 区放指针行（**禁止手填分数**）：verify 全过时 stdout 末尾直接打印可复制的 📌 指针行——
   从 verify 输出原样复制（勿为格式提前读 m11-gates.md），**粘贴后重跑一次 verify 刷新 sidecar**（mtime 新鲜度）：
   ```
   [verified: self_score=<sidecar中的值> profile=full | see analysis_report.verified.json]
   ```
5. c70 打勾（代码强制）：`update_checklist.py --check c70 --file <清单> --evidence-from /tmp/analysis_report_<code>.md.verified.json`
   —— `verdict==PASS` + `self_score>=80` + 新鲜度由 `update_checklist.py` / `--check-pointer` 自动校验，不达标 `sys.exit(1)`。无需单独的"自评分≥80"判断。
   c50 同款在场证明：`update_checklist.py --check c50 --file <清单> --evidence-from /tmp/runner_snapshot_<code>.json`
   （映射叶子 `s10_checklist.completed`，snapshot 在场即过——凭空打勾会 exit 1）。
6. **发布到外部文档（腾讯文档等）前，先过发布闸门**（清洗/转换/lint 一体；规则真相源=tdx_publish.py rules 表）：
   ```bash
   python3 /home/ubuntu/tdx-publish-v4/tdx_publish.py prepare /tmp/analysis_report_<code>.md -o /tmp/tdx_out/
   # → 产出 publish.mdx（[src:] 剥净 + [verified:] 整段剥离；非零退出=禁止上传）
   #   原报告 md 永不修改（verify_gates 扫的就是它）；后续五步见 CLAUDE.md「腾讯文档发布 SOP」
   ```

### Gate Profile 对应关系
| 模式 | Profile | 失败阈值 |
|------|---------|---------|
| A | profile_full | 3 |
| B | profile_quick | 2 |

### Phase 6：Token 审计归档（报告完成后一条命令，LLM 零成本记录）

报告归档后跑一次事后审计（从会话 JSONL 提取 per-request 真实 usage + 内容块 context 压力归因，**分析过程零负担、勿在写作中自记 token**）：

```bash
python3 ~/.hermes/skills/stock-analysis/stock-orchestrator/scripts/token_audit.py \
  --latest --stock <code>
# → ~/analysis_report/token_audits/<code>-<日期>.md
# 含：Phase×类别矩阵 / 模块明细 / 新管线检查项(JIT/m11延迟/视图直读/无手写提取/模块占比) / Top-15 贵内容块
```

复盘看 5 项检查全 ✅ 与否即可；❌ 会给出具体量化（如「手写提取 N 处 / stdout X chars / 压力 Y%」）。

---

## Phase 5：调用契约（详见 `references/exec-protocol.md`）

- **subagent_type 和 category 互斥**（明确写，避免参数错误）
- **run_in_background 触发条件**（独立数据源可并行）
- **三次失败 → 降级为同步执行**（详见 `references/degradation-strategy.md`）
