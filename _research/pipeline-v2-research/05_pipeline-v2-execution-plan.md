# v2 执行计划 v1.0（每批可直接开工）

> 检验标准（用户）：每批拿出来就能开工——引擎改点、fixture 名、反例/正例、回归命令、前置依赖全在纸面。
> 五件套（每批固定）：①引擎改 ②反例 FAIL（先跑，证明进执法分支）③正例 PASS ④回归绿 ⑤REFACTOR_LOG 记录（第 0 条：无状态叙事入代码/SKILL.md）。
> 回归命令（批 ④ 固定）：`bash ~/.hermes/skills/stock-analysis/stock-orchestrator/regression-tests/run_regression.sh`（exit 0 才算完成）。
> 批 commit 即回滚点；provision/预算线数字随对应批预注册，禁散落在 SKILL.md。

## A. P1 落地批图（当前不存在，执行链最大缺口）

### 批 P0 · 现场钉死（半天）
| 项 | 内容 |
|----|------|
| 引擎改 | 无代码。动作：①判据 v4 冻结 commit 打在 `04_pipeline-judgment-v4-frozen.md`（时点=Q1 终裁后）②T17 push 处置（见 §D）③/tmp 已归档核销（0b 已完成，`diff -rq` 零差异，本批只登记） |
| 反例/正例 | 冻结 commit 存在性＝`git log --all --oneline -- 04_pipeline-judgment-v4-frozen.md` 非空；冻结早于判据票首条消息＝commit ts < 票首消息 ts |
| 回归 | 不适用（无 .py 改动） |

### 批 P1a · T15 sidecar 承载 13 模块读态（C2 注入层）
- 引擎改：`c2_compact_inject.py` 渲染段追加 sidecar 读取（`<snapshot_dir>/c2_sidecar.json`，存在则并入渲染）；MAX_BYTES=2048 断言保留。
- fixture：`fixture_c2_sidecar_present`（sidecar 有值→13 模块读态入渲染）/ `fixture_c2_sidecar_absent`（无 sidecar→现行为不变，回退安全）/ `fixture_c2_over_2048`（超限截断→报错非静默）。
- 前置：归档真工件作渲染 fixture（4d L5：现余量 261B，sidecar 必须并行通道，不入锚块本体——V-13 已否决本体承载）。
- 两极：反例=两会话同 glob 错挂 688778 工件 repro（live #3+#4 已录）；正例=单会话正确注入。

### 批 P1b · T11 模块读扫描器＋T2 净新取数
- 引擎改：T11 扫描器（transcript 扫描模块 Read 事件），数据源切换（load_skeleton→transcript 直读）；T2 净新取数 ≤3 记账。
- fixture：`fixture_t11_edit_heredoc`（Edit+heredoc 形态标题）/ `fixture_t11_emoji_title`（emoji 标题漏检前科——4d L6 两极）/ `fixture_t11_all8of8`（8/8 读齐 PASS）/ `fixture_t11_7of8`（缺 1 FAIL＋reason 指名缺哪个）。
- 关键：三形态各两极（正例=识别成功，反例=构造变体证明非恒真）。
- 与 V2-2 关系：T11 先以「读没读」语义上线；V2-2 落地后语义升级为「kernel↔cases 触发读」，同扫描器扩列，不重写。

### 批 P1c · T12 中枢三态＋T13 章序/预算执法
- 引擎改：T12 `zh` 三态（已写值/未写兜底/缺源——现 L129 单态 `zh="m6 未写"` 硬编码）；T13 heading-order 检查进发布管线（厦钨错序 repro 作反例）。
- fixture：`fixture_zh_written`/`fixture_zh_fallback`/`fixture_zh_nosource`；`fixture_heading_order_厦钨repro`（七→十一→十→…序列→FAIL）/ `fixture_heading_order_normal`（→PASS）。
- 两极纪律：`fixture_zh_fallback` 须先证明「未写态」现状 FAIL 再证修后 PASS（单态硬编码=现役反例）。

## B. v2 批图（V0→V4，依赖 P1 全绿）

### 批 V0 · E2E 成本函数脚本（度量先行，判据 v4 R5）
- 引擎改：token_audit 延展——per-request usage 聚合 → `E2E_cost(w=0.1)`＋`(w=0)` 并报行＋subagent 条款断言（Task>0 → WARN）。
- fixture：`fixture_e2e_replay_三票`（威/东/先归档 transcript 重放，数值须逐位复现 5.48/4.67/5.69M）＋蓝晓 928e6ef4 重放=3,812,502（与官方审计逐位一致，已交叉验证）。
- 验收：重放复现＝口径落地；此批完成前一切 30% 讨论停在纸面。

### 批 V1 · 取数轴（R1 预算窗 WARN 期＋runner DONE 标记）
- 引擎改：①update_checklist 勾选时章窗记账（复用 T11 ⑤ 扫描），超窗 WARN（v2.0 不拦截）②runner 轮询替代：`--wait-done` DONE 标记文件＋单命令阻塞等待（东材 bash 循环 11.2K→~200c；同时 `--quiet` 化 liveness，保留 `--status`）。
- fixture：`fixture_budget_ch5_over`（五窗 22.3K 线超→WARN 行）/ `fixture_budget_normal`（东 17.1K→静默）/ `fixture_runner_done_marker`（等 DONE 单命令返回）/ `fixture_runner_quiet`（轮询 stdout 零数据）。
- 标定来源：仅威+东（观察票先导/厦钨剔除）；WARN 期积累判据票数据→v2.1 升拦截。

### 批 V2 · 条件态外置（V2-2 定型：静态分区＋quality_flags）
- 引擎改：①m6b/m3§3.8→B 侧静态分区（模式判定步①前可判，零运行时分支）②classification 金融 450c 留 kernel（写 m2 时已在 context——host 层证据）③caliber/tariff/ST7→runner 装配期预计算 `quality_flags` 上提＋清单条件命令＋probe 反向列（R8）。
- fixture：`fixture_flags_caliber_present`（flag=true→清单出现 cases 读命令）/ `fixture_flags_absent`（三票中威以外 3 票=flag 缺→零命令）/ `fixture_flags_missing_field`（信封字段缺失≠false——北交所教训，显式三态）/ `fixture_contract_kernel_cases`（kernel↔cases 键名对拍，regression 挂载）。
- 反向列正例：A 票读 m6b=审计 FAIL（R8 双向扫描）。

### 批 V3 · 执法面（capstone 配方＋DAG＋内容质量预研）
- 引擎改：①m6 capstone 模板加「中枢 X.XX」格式句（内联）②章序：内容依赖 DAG（依赖表导入既有硬链清单——盘点为批前置任务）＋版面序硬合同（T13 复用）③威 §五 双版本 diff 预研 fixture 入库（损失面特征提取，n-gram 已证假阴）。
- fixture：`fixture_capstone_fmt_missing`（无中枢数字句→R4① FAIL）/ `fixture_dag_violation`（依赖违例→拦）/ `fixture_dag_orderfree`（先导六位次偏离重放：依赖完好→放）/ `fixture_xm5_diff_pair`（威 §五 修复前后）。

### 批 V4 · 清删面（收尾，断空必验）
- 引擎改：R0 预载惯例删除（触发面已存在：分册索引）；load_skeleton 删除（三环断=死信，grep --exclude-dir=_research 断空必验）；重复视图 dedupe WARN。
- fixture：`fixture_r0_preload_detected`（P2 读 tooling-playbook→检查行 FAIL）/ `fixture_dead_ref_zero`（load_skeleton 全库零引用）。
- 尾件：token_audit 正式版＋modeA 审计报告归档（判据票验收附件）。

## C. 蓝晓 runbook v2（rerun 前读）

**GO 五条件**：①批 P1a/b/c 全绿（T15/T11/T2/T12/T13 上线）②判据 v4 冻结 commit 已打＋早于首条消息③provision 条文（a-公式版 28K）随批预注册④V0 E2E 脚本重放复现三票⑤snapshot 面与 928e6ef4 同源（同票同模式）。
**预登记基线锚（旧管线对比，非主基线）**：928e6ef4 ｜ 258 轮 ｜ E2E 3.81M（w=0.1）｜ 在册峰值 48,452c ｜ 总取数 69,778 ｜ gate 修复轮 1 ｜ report 56,086B。
**票类**：蓝晓 rerun＝**回测/对比票**（带 P1+V1 改动，非纯净 v1）——只作旧管线对照与 fixture，**非判据票、非主基线**。判据票=其后新票（预注册＋冻结 commit 前置）。

## D. T17 push 处置（用户裁决项）

未推（ahead 10）。建议：`git fetch origin` → `git diff origin/main main --stat` 看内容差（防重复 hash）→ 若仅内容一致重复提交，`git reset --soft origin/main` 重提干净 commit → fast-forward push。**禁 --force、禁 rebase 重复历史**。若用户裁 T17 含判据 v3 冻结 commit 预期→0b 已证不存在，预期作废。

## E. 验收协议（判据票）

1. **序贯停止**：V0 重放复现 →（不复现=停，修口径）→ 蓝晓 rerun 对照（观察）→ 判据票跑 → E2E(0.1) vs 0.70×东材 rerun【rerun 实测前此线不写死】→ 达标=验收 / 不达标=诚实报告，三选（接受折减/缺口入 v3/追加来源），禁换分母。
2. **分源归因表**（A-G 自验指标）：A=章窗超限次数；B=模块读 chars 实测 vs 103K；C=修复轮峰值序列；D=轮次+同轮率（诊断）；E=覆盖率 100%；F=违例计数；G=落点+重症度。逐源报数，禁只报合计。
3. **内容质量**：人工抽检 1-2 章＋描述统计（判据 v4 §4），探针数据只记录。

## F. 时序总图

```
Q1 终裁 → 批P0(冻结commit+T17) → 批P1a → 批P1b → 批P1c ──(回归绿)──→ 蓝晓 rerun(provision 28K)
                                                                    ↓ 对照锚(非基线)
        批V0(E2E重放复现) → 批V1(取数轴WARN) → 批V2(条件态) → 批V3(执法面) → 批V4(清删)
                                                                    ↓
                            判据票(预注册+冻结commit早于首条消息) → 30% 验收 → provision 复测销案/转正
```
回滚点＝每批 commit revert；P1 批互相独立可单独回退（P1a sidecar absent fixture 保证）。账本三笔：P8 计量随 V0 落地；P9 独立不变；在册量 provision 条件销案（V2-2 后复测，判据 v4 §5）。

## G. 688778 跟踪条款（收官观察票）

- 定位：第四观察票（在册量序列扩点：威/东/先/厦钨），观察/fixture 双用，**永不入标定**。
- 已登记实害点：①在册峰值 53,996c@轮110（视图 29,534+websearch 23,885——R1 预算窗超窗活体反例）②章序错乱（R9/T13 反例源头）③G80 编造型引文被 gate 抓住（引文类执法有效性正例，Q10 细化：gate 管引文类不管转写类）④终验 late repair 成本（D 源轮次论证证据）。
- 触发动作：生产票收官即自动登记观察票（编号递延）；观察票不跑 rerun、不占判据票额度。
