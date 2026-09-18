# Phase 执行协议（phase-protocols）

> **类别：phase 协议（按需 Read）**。时机：执行到对应 Phase 且需要参数细节/降级规则/路由表时。
> SKILL.md 只保留时序合同+命令+指针，本文件承载细节——正常路径不进 LLM 阅读面。

## P1.5 雪球站内声量（voice）

- **执行时机（钉死）：Phase 2 的 runner 拉取完成 + precheck 通过之后、Phase 3 写作之前**——voice 相锚点全部从 snapshot 提取（K线异动日/公告事件/板块/股东户数/风险身份），快照不存在脚本直接报错。本节是数据获取阶段子步骤，不是新 Phase 门（checklist 无对应项）。
- **写 `xq_market_voice` scene**（加法式合入 snapshot，不动 runner scenes）：T1-v2 六维问市场（d1 最新经营情报→d6 风险讨论 + 尾行【站内总评】），`processed` 含 summary/stats/module_map。
- **幂等**：同日 status=ok 即跳过（零配额）；跨日旧 scene 当日重拉（站内声量是当日观点快照）。`--force` 强制重拉。
- **配额保险丝**：当日 xqSearch 已用 >160（剩余 <40）→ 自动熔断写 `status="degraded_quota"`（零发问），报告数据局限节一行披露（R6），G80 全臂豁免。
- **会话保留**：cid 落 `data.meta.cid`，**永不删除**（用户 review + 零配额恢复用）。
- **写作期消费**（Phase 3）：视图 `snapshot_view.py <snap> xqvoice`（总评/stats/各维首 12 行；长引文 `--raw xq_market_voice.data.answers.<dim>` 定向兜底，仍为 CLI 审计合规）；模块路由 = `processed.module_map`（m12←summary、m1/m2/m25←d1_intel、m3←d5_moves、m4←d1+d3+d4、m7←d6_risk、m10←d2_analyst）。**写作规则 R1-R6 见 m4 §4.5**（引文逐字/传闻标注/反对处理/锚点/声量分歧/降级披露，G80 三臂执法）。**模式 B**：T1-B 七维路由 = m39←d0+d2+d3+d4、m37←d0、m36←d1、m6←d1+d6、m3←d5、m38←summary；写作规则 R1-R6 见 m39 内联（G80-B 三臂执法）。
- 路由表速查注：运行时真相源 = snapshot `processed.module_map` 投影，表与 snapshot 不一致时以 snapshot 为准。

## P2 web_research 素材落盘

- 载荷白名单 5 键：`[{topic,value,provider,url,query}, ...]`；`content/title/source` 系别名自动映射（仅当目标键空回填），白名单外非空键丢弃并 WARN（进 `_warnings`→precheck/G72 披露通道）。
- **多批合并（引擎默认 merge）**：同票多次调用按 `topic`（strip 后精确匹配，strip 含全角空格 U+3000）upsert——同 topic **整行替换**（新策展胜，修正后到）、空 topic（URL-only 行）只追加、**无模糊匹配/大小写折叠**（全角/半角标点、大小写、简繁差异=不同键，宁重复不误并）。URL-only/空场告警按合并后 items 现算（跨批存活、修正后自清，G72 披露不丢）；覆盖旧行时 `_warnings` 留痕「旧值→新值」。
- **修剪语义（勿踩）**：merge 下故意**不带**某 topic = 该行**保留**（不删），误删面靠 stdout `total>incoming` 暴露；故意删行/推倒重建必须 `--replace`（整场替换 + 旧 `[web_research]` 告警清空）。
- 写回后 scene=`web_research_findings`；报告引用处带 `[src: snapshot.web_research_findings...]`（**执法者：G21 溯源 + G45 目标价/预测口径**；裸贴 findings = 溯源断裂）。
- **策展面披露（读侧协议 v3）**：写回必带 `--accounting`——snapshot `data.accounting` 累积记账 `RAW_N 总数 = 策展 kept + 弃读 discarded（逐条规则+理由）+ 口径对撞 caliber_flags`；读了没策展、搜到没读，在账上一目了然（**执法者：G81 消费/披露**）。
- websearch 是**发现**工具非**验证**工具：API 结构化数据是权威上游，冲突时以 snapshot 为准（CLAUDE.md 同款原则）。

## P4.5 站内结论求证

- **时序（硬约束）**：插在 Phase 4 第 1 步（报告写入 /tmp）与第 2 步（verify_gates）之间。② 写 scene 会刷新 snapshot mtime，③ 修订重存报告在其后 → verify 的 mtime 检查（报告 ≥ snapshot）天然满足；错序（先 verify 后写 scene）= exit 2。模式 B 跳过本节（无 capstone 反对处理刚需，省配额）。
1. **提取结论**：从报告草稿提取 10-15 条核心结论（每条一句、含关键数字），一行一条写入 `/tmp/conclusions_<code>.txt`。
2. **Q2 独立会话求证**（**必须独立会话**——同会话续问会把站内检索退化成上文检索；防迎合问句由脚本 FRAME 内置，勿手写）：写 `xq_conclusion_check` scene（verdicts 四值：支持/部分支持/反对/无讨论 + objections 反对条目号）。**幂等 = 同日 ok 且 conclusions 未变**才跳过（修订后新结论集必须重问）。
3. **定向修订草稿**：读 `snapshot_view.py <snap> xqcheck`，每条 objection 在报告（§13.2 反方证据列）写「**站内反对·须直视**」处理段——三要件：标记词（站内反对/站内反驳/市场反对/反对意见）+ 证据 token（数字/≥6 字串）**同段** + 处理三选一（维持/降档/修正），禁静默忽略（详见 m6 capstone「站内反对·须直视」节）。修订后**重存报告文件**。
3b. **增量逐条过堂**（增量利空/利好不留黑洞，checklist `c_xq_delta`）：d1-d6 各维与 check raw 中「我方此前未覆盖的增量」**逐条显式落点**——利空→m7 §7.1 收录、利好→§4.5 对撞行/观察清单——或写明弃用理由；报告只写结果（对撞行增量句），不出现工序表（规则句见 m4 §4.5 R5）。

## P6 Token 审计

- 产物：`<股票的 analysis_report-*-mode<X>-<code>/token_audit-<code>-<日期>.md`；`--mode` 过滤模式目录，缺省不过滤（兼容旧目录）。
- 审计内容：
  ```
  # 含：Phase×类别矩阵 / 模块明细 / 新管线检查项(JIT/m11延迟/视图直读/无手写提取/模块占比) / Top-15 贵内容块
  ```
- 复盘看 5 项检查全 ✅ 与否即可；❌ 会给出具体量化（如「手写提取 N 处 / stdout X chars / 压力 Y%」）。
