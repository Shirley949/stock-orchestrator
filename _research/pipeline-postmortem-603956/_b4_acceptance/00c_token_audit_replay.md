# Token 审计 — 601208（2026-09-16 22:07）
- 语义口径：**semantics v3.1**（deduped · result-only · path-tiered · 3-bucket 处数，webfindings/web_research 策展归 fetch 桶）——处数口径与 v2 不可比（gate 调试/fetch 补救另计）；chars 口径可比

- 会话：`11f32cf4-4d15-4480-8c88-b90dab80ccb9.jsonl`（407 轮 API 调用，619 内容块）
- 被分析文件：`/home/ubuntu/.claude/projects/-home-ubuntu/11f32cf4-4d15-4480-8c88-b90dab80ccb9.jsonl`
- 内容自提股票码：601208（与 --stock 一致 ✓）
- 真实口径（per-request usage 累计）：input **1,123,154**（cache_read 34,176,000 / cache_write 0）+ output **353,469**
- 归因口径：Σ chars×存活轮数 = 131.4M char·turn（定位浪费用，非计费单位）
- **总取数 = CLI 73,551 + 手写 0 = 73,551 chars**（覆盖率 100.0%｜末次 gate FAIL —｜gate修复轮 0·已全过｜P4 dump 0c｜外科豁免 0 处）
- 环比（最近 3 次；'？'股码=旧条目未存 stock 字段）：2026-09-16 20:11 [A] 601208: 106,832c；2026-09-16 21:24 [A] 601208: 73,551c；2026-09-16 21:28 [A] 601208: 73,551c

## ① Phase × 类别矩阵（归因占比 %）

| 类别 | P0加载/其它 | P2拉取 | P3写作 | P4gate | P5发布 | 合计 |
|------|------|------|------|------|------|------|
| LLM输出(thinking) | 1.7 | 5.4 | 0.8 | 21.4 | — | **29.2** |
| Skill加载 | 10.9 | 0.4 | — | — | — | **11.3** |
| bash其它 | — | 5.5 | — | 3.5 | — | **9.0** |
| 视图:any | — | — | 0.4 | 7.9 | — | **8.3** |
| Read其它 | 4.1 | 1.8 | — | — | — | **5.9** |
| 模块文件m2 | — | — | — | 4.8 | — | **4.8** |
| gate校验 | — | — | 0.3 | 3.1 | — | **3.4** |
| runner拉取 | — | 3.3 | — | — | — | **3.3** |
| 模块文件m3 | — | — | — | 3.1 | — | **3.1** |
| 模块文件m4 | — | — | — | 2.9 | — | **2.9** |
| 用户输入 | 0.0 | — | — | 2.4 | — | **2.5** |
| 模块文件m6 | — | — | — | 2.0 | — | **2.0** |
| 模块文件m7 | — | — | — | 1.6 | — | **1.6** |
| 模块文件m9 | — | — | — | 1.4 | — | **1.4** |
| 模块文件m1 | — | — | — | 1.2 | — | **1.2** |
| 模块文件m5 | — | — | — | 1.1 | — | **1.1** |
| 视图:news | — | — | — | 1.0 | — | **1.0** |
| 模块文件m10 | — | — | — | 0.9 | — | **0.9** |
| 模块文件m25 | — | — | — | 0.9 | — | **0.9** |
| 视图:income | — | — | — | 0.8 | — | **0.8** |
| 视图:list/raw | — | — | 0.2 | 0.5 | — | **0.8** |
| 视图:valuation | — | — | — | 0.7 | — | **0.7** |
| LLM输出(写作) | 0.0 | 0.4 | 0.0 | 0.1 | — | **0.6** |
| 模块文件m0 | — | — | 0.6 | — | — | **0.6** |
| 视图:technical | — | — | — | 0.4 | — | **0.4** |
| 复合命令(view+提取) | — | — | — | 0.4 | — | **0.4** |
| 模块文件m12 | — | — | — | 0.4 | — | **0.4** |
| 视图:timeline | — | — | — | 0.4 | — | **0.4** |
| websearch | 0.1 | 0.3 | — | — | — | **0.3** |
| 其它工具 | 0.2 | 0.0 | 0.0 | 0.0 | — | **0.2** |
| 视图:balance | — | — | — | 0.2 | — | **0.2** |
| 视图:annual | — | — | — | 0.1 | — | **0.1** |
| xq拉取 | — | 0.1 | — | 0.0 | — | **0.1** |
| 视图:xqcheck | — | — | — | 0.1 | — | **0.1** |
| 模块文件m8 | — | — | — | 0.1 | — | **0.1** |
| LLM输出(写文件) | — | — | — | 0.1 | — | **0.1** |
| **合计** | **17** | **17** | **2** | **63** | — | **100** |

### 三桶汇总（归因% 管道内｜字节 KB 静态）

| 桶 | 归因%（context 压力） | 字节 KB |
|----|----------------------|---------|
| 固定层 | 11.3（仅 SKILL.md Read；CLAUDE/MEMORY 管道外） | 离线 wc 27.6 + 会话内 36.3 |
| 场景面 | 0.0 | 0.0 |
| 模块面 | 20.9 | 121.7 |

## ② 模块维度（Phase 3 内）

| 模块 | 文件Read轮次 | 首读轮 | 视图取数（chars） |
|------|------------|-------|-----------------|
| m0- | 1 | 91 | — |
| m1- | 1 | 99 | — |
| m10 | 1 | 266 | — |
| m12 | 2 | 275 | — |
| m2- | 1 | 113 | — |
| m25 | 1 | 145 | — |
| m3- | 1 | 156 | — |
| m4- | 1 | 171 | — |
| m5- | 1 | 206 | — |
| m6- | 1 | 218 | — |
| m7- | 1 | 253 | — |
| m8- | 1 | 263 | — |
| m9- | 1 | 242 | — |

- 模块 Read 轮次跨度：**187 轮**（JIT 生效=跨度大且穿插写作；旧全量加载=集中 1-3 轮）
- snapshot_view 调用 **66 次**（含 any 47 次，其中扁平小节命中 13 次），结果合计 73,551 chars
- --field 外科投影调用 **8 次 / 10,322 chars**（分布行——防散便宜调用刷覆盖率：3c/调使刷分子成本趋零，须与手写残余同读）

## ③ 新管线检查项（基线=瑞丰 300243 旧路径，2026-08-20）

- ✅ **模块 JIT 加载**：跨度 187 轮（旧：Phase3 开头集中全量 Read）
- ✅ **m11 延迟加载**：未提前读
- ✅ **视图直读**：66 次调用 / 73,551 chars（旧 kline 单项 146K）
- ✅ **无视图内手写提取**：0 处（stdout 节省基线 ~20%）
- ✅ **真提取 ≤5（记录态·非阻断）**：0 处（超线=❌ 留痕不阻断出口；定性=记录态，禁仪式态）
- ✅ **无快照写回**：0 处（快照只读）
- ✅ **gate 源码零读入**：0 次
- ✅ **视图覆盖率>80%**：CLI 直读 73,551 / (CLI+手写) 73,551 chars = 100%（any 命中扁平小节计合规）
- ✅ **加载集 diff·漏读**：模式A 应读 13 模块 m0-/m1-/m10/m12/m2-/m25/m3-/m4-/m5-/m6-/m7-/m8-/m9-，漏读 无
- ℹ️ gate 源码 Bash 侧访问（sed/grep/cat/awk 撞 gate_definitions，sanctioned fallback 透明度）：**5 次 / 6,739c**（vs Read 全文 178K）
- ℹ️ compact 锚定（v4 诊断，不进验收线；首取数动作锚定段内行为）：**2 段**
  - c1@轮172 → 首取数 **CLI**@轮173(+1) | 段内手写 0 处 | cd /tmp && python3 ~/.hermes/skills/stock-analysis/stock-orc
  - c2@轮272 → 首取数 **CLI**@轮296(+24) | 段内手写 0 处 | cd /tmp && python3 /home/ubuntu/.hermes/skills/stock-analysi
- ℹ️ 数据驻留在册量（v5·P0.3，P3 窗口；判据线 ≤20K chars）：**峰值 15,031c@轮93**（章≈m0｜峰值构成 视图 2,574c + websearch 930c + runner 11,212c + xq 315c｜compact 重置 2 段）

## ④ Top-15 最贵内容块（context 压力）

| 轮 | Phase | 类别 | chars | 在册@轮 | 压力% | 内容 |
|----|-------|------|-------|--------|------|------|
| 8 | P0加载/其它 | Skill加载 | 19,738 | 0c | 6.0 | Read: tu/.hermes/skills/stock-analysis/stock-orchestrator/SK |
| 113 | P4gate | 模块文件m2 | 21,453 | 20,037c | 4.8 | Read: is/stock-analysis-quality/references/modules/m2-financ |
| 13 | P0加载/其它 | Read其它 | 13,597 | 164c | 4.1 | Read: /tmp/analysis_checklist_601208_modeA_1789560524.md |
| 156 | P4gate | 模块文件m3 | 15,974 | 36,321c | 3.1 | Read: is/stock-analysis-quality/references/modules/m3-techni |
| 171 | P4gate | 模块文件m4 | 16,001 | 41,845c | 2.9 | Read: is/stock-analysis-quality/references/modules/m4-sentim |
| 9 | P0加载/其它 | Skill加载 | 7,572 | 0c | 2.3 | Read: hermes/skills/stock-analysis/stock-analysis-quality/SK |
| 218 | P4gate | 模块文件m6 | 14,108 | 22,845c | 2.0 | Read: sis/stock-analysis-quality/references/modules/m6-decis |
| 6 | P0加载/其它 | Skill加载 | 6,262 | 0c | 1.9 | Read: hermes/skills/stock-analysis/financial-data-routing/SK |
| 47 | P2拉取 | bash其它 | 6,483 | 5,358c | 1.8 | Bash: cd /tmp/exa_601208 && python3 - <<'EOF' import json fo |
| 25 | P2拉取 | Read其它 | 6,097 | 547c | 1.8 | Read: /home/ubuntu/.claude/docs/tooling-playbook.md |
| 253 | P4gate | 模块文件m7 | 13,314 | 30,513c | 1.6 | Read: nalysis/stock-analysis-quality/references/modules/m7-r |
| 242 | P4gate | 模块文件m9 | 11,395 | 25,595c | 1.4 | Read: s/stock-analysis-quality/references/modules/m9-governa |
| 171 | P4gate | 用户输入 | 7,872 | 41,845c | 1.4 | user 消息 |
| 127 | P4gate | LLM输出(thinking) | 6,032 | 33,165c | 1.3 | thinking |
| 227 | P4gate | LLM输出(thinking) | 9,241 | 25,595c | 1.3 | thinking |
