## 2026-09-01 批2 落码 #5：G30#1 fatal surface 同义词归一（定增≡增发）

德福 301511 实锤从写作纪律升级 engine 修复：东财 `event_type=增发` × 报告合法写「定增」→ 子串判定漏 surface 误报。`_g30_announcement_registry_findings` 内建 `_SURFACE_SYNONYMS = {增发↔定增}`（保守起步仅此一对，按语料实锤增补；同义归一只增命中，new-PASS ⊇ old-PASS）。两极：修前 HEAD 复跑 finding 误报 → 修后同义措辞 []；**执法力反例（配售=两者皆非）仍报缺失**，无过宽。归档 44 对三层差分 0 翻转。trap_corpus 登记 `g30_surf_dingzeng_defu`；ledger `G30#1:synonym_dingzeng` inflight→**landed**。担保词表部分仍属写作纪律（G30#1:substring_keyword 保持 pending）。

验证：test_diag_contract 40 用例全绿；run_regression.sh exit 0（engine_pending 3→2）。


## 2026-09-01 批2 落码 #1：G63 分位族全形态豁免（百分位/分位数变体）+ trap_corpus 永久语料

触发：裁决C-1 取证——cron 原始措辞「N 分位」E1 已覆盖，但语料现存「94/3/1 百分位」7 处活雷：`百` 挡在 `\s*分位` 前，数字仍泄漏价位对拍。修法一行：E1 正则 `\s*分位` → `\s*(?:百分位|分位数|分位)`（长形在前防前缀截断；分数形式原样保留）。

- **证据链**：HEAD 旧引擎忠实复跑（git show 取归档模块，非模拟）——「94 百分位」FAIL（94≈94.78 偏 0.8% 误伤）、「第99百分位」FAIL（偏 4.5%）→ 修后双 PASS；tokenizer 5 形态修前泄漏 [94]/[99] → 修后全 `[]`（「N 分位数」旧正则本就覆盖=防御性）。**归档级零漂移**：44 对全 gate verdict 向量双引擎差分 **0 翻转**（verdict/failed_gates/gate 三层均无）。
- **trap_corpus.yaml 永久语料**（裁决C-1：形态进 fixture 才是回归保护，禁散落单元测试）：`regression-tests/trap_corpus.yaml` 单一真相源，每条带 id/gate/check/line/source（实证来源必注）；消费方 `TestTrapCorpus`（schema 唯一性 + tokenizer 5 形态 + e2e 翻转对账）。批2 #2 的 7 句评测集随后同落此处。
- **风险面**：regex 锚定数字前缀，价位句不以「N百分位」收尾——无新增误剥（长形只增剥离域，new-PASS ⊇ old-PASS 方向安全）。
- ledger：`G63#percentile_variant:bai_percentile_leak` inflight→**landed**（count=0 基线，复发=回归）。

验证：test_diag_contract 39 用例全绿；test_archive_replay 44 对 REPLAY_ERROR 0；run_regression.sh exit 0。


## 2026-08-31 诊断契约 v2.1：11 站点 reason 真值化（批1）+ 双防线 + 删记忆实验 + 两指标 + 契约路线图（plan wiggly-moseying-spring）

触发：圣邦实测 G57 裸 False 臂只回 registry 泛句，LLM 被迫重查快照多花一轮。定理锚定：verify_gates.py 只消费 verdict ⇒ `return False` ≡ `GateResult(passed=False, reasons=[...])`——reason 升级 verdict 天然中性（418 次真实调用差分零翻转）。批1 = 11 站点（7 裸 False 尾注 + 4 静态编造 reason）原位真值化；批2（5 引擎根因）独立立项勿合并。

- **S1 引擎 11 臂升级**（`gate_definitions.py`）：统一模板=病名(含快照真值) + 违规行 `L{n}:『原句』`（`locate_lines` sec 切片→全文行号回映 + `_fmt_violation_lines`，全量清单截前3）+ 可照抄修法（含示例句 + `[src:]` 路径）+ diag 六键 `{subcheck,expected,found,fix,src,degraded:False}`。G32/G33/G61 拉取失败臂带 **`[数据层]` 前缀**（fix 禁改稿动词，只指重跑拉取/上报）；G52 捕获组带出 ATR 报告值；G53 偏离分位算术；G57 两臂带 growth_tier 档位语义（high=INCREASE_JZ>50%）；`_sgr_claim_lines` 收敛 SGR 数值行定位单一实现。C14 审计盲区实证封堵：`return False\s*(?:#.*)?$` 收紧后全库裸 False=0（早前 G1/G14/G16/G49/G71 "发现"为扫描器缺 `^(def|class)` 重置的伪发现）。
- **S2 双防线**：`verify_gates.py` 运行时 warn——checker 返回裸 bool 且 `not ok`（FAIL 侧才计，PASS 返回 bool 无害）→ warn + 降级 fail_hint + `base_result["bool_return_warn"]`；注释留升级条件（一轮 cron 零命中后升硬断言）。归档 44 对重放实测仅 G7/G8/G9 三处真实 bool-FAIL（=lossy 面真实存量）。
- **S3 测试四族**（`test_diag_contract.py` 36 用例+49 subtests）：审计 v2 全库零裸 False；11 臂行为级（FAIL verdict 保持 + 真值 token + 行号 + PASS 变体不翻转）；逐臂崩溃面 ×11（scene缺/字段None/`{"error":...}` 类型异常信封，deepcopy 挖键构造）；`[数据层]` 契约 lint（fix 禁 照抄/改写/删除/删或改/补写 + degraded⇔found 一致性）；双形态渲染（原生 diag ⚙️ 行与 fail_hint 兜底过渡期共存）。SKILL.md 约束5 加一行：reason 带 `[数据层]` → 不改报告，重跑拉取或上报。
- **S4 全量验证闸**：run_regression.sh exit 0（62 门漏报=0）；test_archive_replay 44 对 EXPECTED_FLIPS 恒空（批1 verdict 中性证明——批2 禁复用恒空模板）；研究脚本重跑全绿（真值携带 4/11→11/11、行号 0/5→5/5、PASS 性能比 0.96–1.04）。
- **S5 删记忆实验（诊断税量化）**：fresh 无上下文 subagent（不给快照/不给 memory/不浏览）仅收 `{FAIL reason 原文 + 报告片段}` 产修正行，11 站点逐点评分（值对/行对/语义对/数据层不改稿）。**新 reason 11/11 vs 旧泛句 4/11**（4 个全中=旧静态句本就带修法的 G51×2/G52/G58 站点）。对照组 7 失手里 **3 处产出假陈述**（G57-mod 把「业绩预增公告」删成「数据未获取」、G53 把有数据的 pct_250=80 写成「数据缺失」、G21 诊断方向即错）+1 处会给 failed 场景编造结论补 src 锚背书（G61）——诊断税不止轮数，还有纠错成本（假陈述入稿再返工）。**升格（批1 验收裁决）**：假陈述发现=「真值携带 reason 是反编造基础设施」（诊断贫困诱发编造，且编造会带真 [src:] 锚部分击穿 G21/G48 反编造层），已写入《Gate 编写公理》第 9 条（quality 仓 m11-gates.md）——回退 fail_hint 短句的提案以此否决。
- **S6 两指标埋点（裁决⑤）**：①诊断税 `token_audit.py` 新增 `gate_fix_rounds`/`gate_converged`（首次全过前 FAIL verify 次数；0=一次全过；未收敛仍计并标记）——md 报告行+stdout+history 三处落；真会话 smoke 实测「gate修复轮 1·未收敛」正确。②晋级欠账 `trap_ledger.engine_pending()`（root_cause=engine 且 status≠landed）——trap_ledger_scan 恒打首行 + run_regression.sh 尾部 echo 同源（两极验证：engine+pending 计入 / landed 不计 / 无 root_cause 不计）。
- **S7 61→62 门契约覆盖度路线图（AST 基线 2026-08-31，gate-own return 口径，嵌套 helper 剔除）**：
  - **lossy bool 22 门**（FAIL 可达裸 bool/表达式 return，reason 丢失面）：G1 G6 G7 G8 G9 G11 G12 G13 G14 G15 G16 G17 G19 G21 G22 G26 G28 G31 G34 G35 G36 G37（G30 剔除——`_g30_run` 返 dict 非 lossy）。
  - **GateResult 无 diag 115 臂/45 门**（高频先：G65×10 G61×6 G51×6 G15×5 G16×5 G40×4 G23×4 G53×4 G66×4 G68×4）。
  - **return True PASS 短路 108 处**（无害）；dict 形合法 2 处（G32/G33 历史 PASS reason）。
  - **WP1 lossy→GateResult**（复用 S1 模板，优先序=真实 FAIL 面：G28 语料 10 实 FAIL → G7/G8/G9 归档重放实测 bool-FAIL → report-only 词表门 G11/G12/G13/G17/G19/G22/G26/G31/G37（reason=缺哪词+补写句）→ G1/G14 legacy → G6/G15/G16/G21/G34/G35/G36 带真值）；**WP2 diag 补齐**（fail_hint 六键合成兜底已由 E9 框架覆盖，此项=原生 diag 质量升级）；**WP3 return True→GateResult(passed=True) 机械批**。
  - **完成判据（机器把守）**：①审计升 AST 级断言 lossy=0 ②S2 warn 升硬断言 ③GateResult 无 diag 臂=0 ④bool 返回=0 且 diag 六键=全门。WP1 各批 reason 升级仍 verdict 中性（archive replay 对拍面=verdict/reasons 门集合，不含 reason 文本），EXPECTED_FLIPS 对账纪律与批2 同。
- **S8 收尾**：trap_ledger 增 9 签名（11 站点归并——G51 双臂/G57 双臂各一；root_cause=engine，count=0 基线，status=landed，ledger 19 条签名唯一）；memory 族更新（g21/g63 族+misc 按新 reason 语义）；`engine_pending` 指标即批2 五条立项后的可见欠账（root_cause=engine+pending）。

验证：run_regression.sh exit 0（62 门漏报=0 + engine_pending 指标行）；test_diag_contract 36+49 subtests；test_archive_replay 44 对零翻转；test_token_audit 7 OK；engine_pending/gate_fix_rounds 两极+真会话 smoke。


## 2026-08-31 诊断契约 v2：全 gate 自包含失败诊断 + G62 表头签名/G63 分位剥离/G30#5 否定窗/G21 路径指引 + TRAP_LEDGER（plan b-snapshot-5-eager-tome）

触发：金安 002636 / 德福 301511 两轮暴露「gate FAIL 后排障靠读 178K 源码 + hint 覆盖不足 + 教训散落 memory」。四层：引擎修复（E1-E8）/ 诊断管线（E9）/ 补线（E7）/ 台账（E10-E11）。全程 **43 对归档(报告,快照) verdict 回放零翻转**锚定（test_archive_replay.py + fixtures/archive_replay_baseline.json，函数直调禁 CLI 防 sidecar 污染）。

- **E1 G63 分位剥离**：`N 分位`/`N/100 分位` 数字不再进价位对拍（金安「99 分位」曾被当价位与 94.78 对拍误判转录错）。
- **E2 G30#5 两遍锚定+否定窗**：强锚（投资建议/主推荐…）优先于弱锚「结论」；前置 12 字符否定词窗内动作词不算主推荐（「不支持现价加仓」不再污染分类；「观望」不入否定表——它本身是持有类动作）。
- **E3 G55/G56 收集化**：五臂/七臂 violations 全量齐报（旧首臂早退）；GATE_HINTS G56 剔除 G51 的 SGR 句。
- **E4 G62 表头签名 + T1/T2 分层 + 披露感知 claimed**：`_tally_table_counts` 只数「表头第 2 列字面=方向」的表（§3.2 状态表污染根修）；T1 硬臂（自称≠表格）**先于** T2 软臂（自称≠引擎 advisory 未披露→SOFT 提示+diag，F1 铁证：引擎≠自称是 m6 合法设计）；claimed 取最后匹配——「引擎 7/4/2，本表裁决 5/6/3」明示分歧写法合法（旧引擎抓首个=引擎值必炸）。执法序 bug 由 C9 反例抓出（软臂短路硬臂）。
- **E5 G21 坏路径指引**：`PATH_ALIASES`（s9_news→s5_events.data.news / td.daily→td / cash_flow_statement→cash_flow / technical.relative_strength→data.relative_strength / peer 子键）+ `_explain_bad_path`（最深节点+兄弟键≤8+difflib 近邻）；reasons cap5+溢出行带余量建议；diag.found 全量；「本清单为全量」自相矛盾尾句废除。G21 dict-only 步进保持（有意合同，禁换 _snapshot_get）。
- **E9 diag 管线**：verify_gates FAIL detail 100% 带 diag（checker 原生或框架 degraded 合成，expected/found=None+fix=fail_hint）；`_build_action_required` 追加 expected/found/src 行；L2 lint（diag.fix 含 绕过/规避/换词避开/改成不含 → result.diag_lint 警告）。
- **E7 R5 28 门/62+3 处裸 False 补线**：GateResult reasons 带作用域内触发真值（判决布尔不动，replay 零翻转+62 门漏报=0 双锚定）。
- **E8 panorama 双调用消除**：`_g30_signal_coverage_findings(data, cov, pan=None)`，_g30_run 传已算 pan。
- **E10/E11 TRAP_LEDGER 三件套**：`references/trap_ledger.yaml`（首批 10 条，金安/德福 13 陷阱归并；schema 含 match/count 基线/status/blocked(P3)）+ `scripts/lib/trap_ledger.py` + `regression-tests/trap_ledger_scan.py`（**strict=增量拦截**（P12）：signature 计数>count 基线才 exit1，72 份存量 sidecar 10 处历史 FAIL 不误拦）+ generate_checklist blocked 硬阻断 exit2（--ignore-trap-ledger 逃生）+ run_regression.sh 接线两极沙箱（fixtures/trap_ledger_sandbox pole_fail=期望 exit1/pole_pass=期望 exit0）。
- **测试**：test_diag_contract.py 28 用例（C2-C15/L2：先红在功能缺席处）；test_src_hidden_style G62 fixture 外科刷新（E4 有意行为变更：无表头裸数据行不再计数，测试主张不变加表头行）。

验证：run_regression.sh exit 0（62 门漏报=0）；test_archive_replay --compare 43 对白名单外零翻转；test_diag_contract 28/28；trap_ledger strict 两极 + checklist 硬阻断两极实测。


## 2026-08-31 模式B核心结论头块固化：G71 + b_head 视图接线 + m38 契约（plan b-snapshot-5-eager-tome）

触发：用户拍板 300433 模式B v2 报告的「核心结论」置顶块固化为 B 报告标准开头（点名 10 槽位），硬要求「模板每次一致 + 数据新鲜正确」。三层分工：脆弱归引擎（routing 仓 `build_b_head_view` 预渲染 `head_draft_md`）、结构归 gate（G71）、开放归散文（quality 仓 m38）。

- **G71（check_g71，B_ONLY，weight=1，owner=m38）四段执法**——只执法 G65/G68 未覆盖的净增量（方向/p/胜率/凯利/ATR 数值不二次执法，防双执法漂移）：①头块存在性（`核心结论` 标题锚 + 方向预测/纪律位 verify；整块省略仍 10/10 过 = 执法空白，正是「每次都是这种」的产品需求编码）②10 槽锚词完整性（现价/近5日/分时/方向预测/情景/关键位/纪律位/筹码/主力/仓位——v2 金票回放实测恰缺『现价/分时』= 用户点名的第 1/3 优先槽）③纪律位散文**标签配对**对拍（`（60m MA60 档已失守?）` 标签消歧 vs `risk_control.stops`，±1%——G68 刻意收窄到表格行防档间互 hit，G71 用标签配对无此面）④头表概率=§5 capstone 投影字符串相等。
- **G71×引擎死锁消解（002202 fresh 全链路实测）**：bear 方向头块的悲观行=主推行（目标=er_low，G65/引擎区间管）非 pess 档 → pess 对拍门控 `direction != "bear"`（Gate 修复验证硬规则③死锁类：强制消费 gate × 对拍 gate 真值域不交）。
- **接线面**：snapshot_view.py 加 b_head 视图（VIEW_PATHS/_print_b_head/PRINTERS）；token_audit.py VIEW_NAMES+VIEW_TO_MODULE 成对（漏 VIEW_TO_MODULE = classify_block KeyError）；gate_fixture_test.py EXPECTED 加 G71 行（3 A 票 mode 短路结构性 True）；generate_checklist.py B phase_3 加 c59（m38 头块步骤）；skill_dep_graph.py MODE_SCENARIO_FILES["B"] 加 m38；data_contracts.py m38-b-conclusion-head consumer tag（s2 kline/realtime_quote、s4 short_term_enrich+G71/chip/support_resistance、s3 fund_flow、intraday_60min）；SKILL.md:180 B 行 m38/m3/m36/m37/m6（顺手修 m36/m37 缺登 drift）；run_regression.sh 挂 test_b_head_g71.py。
- **新增 `regression-tests/test_b_head_g71.py` 28 用例**：C1 18 票真实语料回放（十槽全非空、数字==raw、300054 双快照逐字节幂等、7 破位票 stop_side/pess 分支）+ C2-C12 聚合/换算/分支/降级/A no-op/截断残骸 + C13 G71 四极反例（无头块/缺槽/纪律位偏差/概率漂移全 FAIL）+ C14 v2 金票对齐裁决（标记缺现价/分时，执法面收敛在真缺口）。

验证：run_regression.sh exit 0（62 门漏报=0 误伤=0；契约双向闭合 m38 零 error；checklist 分母自适配）；002202 fresh runner B 全链路（fetch→store→read→consume）check_g71 PASS + verify_gates quick G71 ✅。


## 2026-08-30 第4批机制层：R8 静默降级 fail-fast + R10 文档路径机器校验 + R12 fixture 真实正文探针（failure-family 修复执行令）

触发：同执行令第4批（机制层是「彻底解决」构成要件）。gate 逻辑零改动（`scripts/lib/gate_definitions.py` 相对 HEAD 空 diff），全部为机制/测试/文档层：

- **R8 机制档（三处 fail-fast）**：① `scripts/precheck.py` exit 3=⚠️有条件通过（_warnings 非空不再混进 exit 0，「通过」不再被高估；`precheck_critical_failure` 改返 `(ok, n_warnings)` 元组）；② `scripts/verify_gates.py` `load_data_snapshot` 传了 `--data-snapshot` 但文件不存在/非 JSON → exit 1 拒静默降级 report-only（未传仍合法走 report-only）；③ `scripts/update_checklist.py` 未知 cid 无 evidence 映射 → exit 1 零写入（旧=静默跳过校验照常打勾 = 无证据打勾通道）。新增 `regression-tests/test_r8_mechanism.py` 3 测试两极（正常流不受影响/错误流必拦）。
- **R10 文档路径机器校验**：新增 `scripts/verify_doc_src_paths.py`——扫 quality/references 文档树全部 `[src: snapshot.<path>]` 标记（默认）+ 条件性标注（仅当/条件性/禁标）降级 WARN，dot-split resolve 镜像 G21 语义（`[]` 记法不解析、list 引用止步父键、`<placeholder>` 跳过、websearch 跳过），快照池=parity 3 金票 + 新增 `fixtures/600183_modeB_golden.json.gz`（生益科技模式B真实快照冻结，B 门探针语料），任一快照可解析即过、全不通→error；CLI `--doc-root` 供测试注入，exit 1 on error。当前基线：22 文档/166 标记/坏路径 0/WARN 3（web_research_findings 条件性正确降级）。新增 `test_doc_src_paths.py` 9 测试。**配套文档修复**（quality 仓，R10 标注规范）：m5-valuation.md / m10-forecast.md 的 `web_research_findings` 教学路径补「（仅当写回成功、场景已存在）」条件性标注；snapshot_schema.md 顶部加「路径记法双轨制」声明（`[]` 仅限契约键描述，正文一律 dot-split）。
- **R12 fixture Level D（真实正文探针）**：`gate_fixture_test.py` 新增三桶——REAL_HONEST 9 条（龙磁 300835 事故行原样「| 股东层面风险 | …无待执行增减持计划 |」等诚实写法必须 PASS，R5 片段级收窄等修复冻结为回归红线）/ REAL_TWIN 4 条（反编造反例必 FAIL：G48「待执行+%」同片段、G47 degraded 态具名增持、G61 结论词无锚、G29 空数据写「货币资金约 35 亿」）/ REAL_WATCH 3 条（疑似误伤与漏洞形态冻结当前判决：G49「卖方研报」跨行共现触发反编造、G57 诚实免责括号复用「业绩预告」触发词、G69 src_token+维度词两独立全文条件跨行拼「消费」——R7 观察档显性化，判决漂移即 exit 1 禁静默变化）。构造快照补冻结票覆盖不到的三态分支：degraded_sd（G47 反编造臂仅对 ≠ok/≠failed 中间态生效，failed 在 :2147 早退）/ no_bsp / eval_ok（千股千评 ok 最小构造）/ empty。汇总行扩为「+ 13 真实正文探针/watch=3 …drift=0」。
- **R9 gate 写作公理升 8 条**（quality 仓 m11-gates.md）：公理 2 改「词表四问」（+④作用域：行/片段/段/全文+理由，G48 教训=全文双条件跨段共现误判）；新增公理 7「violation 一律全量收集」（镜像 check_g63，列 G16/G45/G54/G56/G57/G58/G60/G61/G64/G66）、公理 8「reasons 底线：禁丢弃已持有信息」（6 违例史）；构件 3 重写为「原生 reasons（契约制）」——废除 9 门白名单（2026-08-17 前提被龙磁 F2 六处证伪）。

验证：全量回归 exit 0（gate_fixture_test 漏报=0 误伤=0 crash=0 drift=0，含 Level D；test_doc_src_paths 9 + test_r8_mechanism 3 新挂载全过）；/tmp/replay postfix4→postfix5 五维零变化（verdict/score/failed_gates/逐门向量/reasons 门集合，23 用例）；gate_definitions.py 相对 HEAD 空 diff（无 gate 逻辑改动=A/B 对照天然成立）。预存脏状态（parity corpus 3 gz / test_parity_gate / test_src_hidden_style / test_market_context_order / test_s10_checklist_cached / refresh_golden.py / strip_publish_sample.md / REFACTOR_LOG 预存条目）hunk 级隔离未混入。


## 2026-08-30 第3批族级清扫：F3 十门违规早退收集化 + F2 六处「收集后丢弃」reasons 化 + G63 词表补「阻力」（failure-family 修复执行令）

触发：/tmp/failure_family_report.md 审计定稿的 F2/F3 两族全量灭绝 + F4 同构面审查。性质=纯 reasons 面强化（判决面零变化，A/B + 重放双证），全部在 `scripts/lib/gate_definitions.py`：

- **F3 十门收集化**（循环内 FAIL 早退 → 全量收集+尾部统一 return，镜像 G63 范式 top5+「另有N处」尾注）：G16 冲突行（报告值/真值亿/行摘录入 reason）、G54 `_bad_types`（非 str 键全量）、G56 五块缺口全量、G57 反编造行收集（含 growth_tier=None 成因）、G58 三维分位缺口全量（带 pct_5y 真值）、G60 裸奔行+研发强度偏离合并清单、G61 ④ 消费缺口带维度词表、G66 四周期反义矛盾全量（G45/G64 第2批已修）。
- **F2 六处 reasons 化**（FAIL 分支作用域已持信息却裸 False）：G15 peer 反编造（禁编造+诚实降级指引）、G23 维度覆盖（ok_count/threshold+缺失维名单）——G21 第1批、G53/G60/G61 本批 F3 改造顺带覆盖。
- **G63 语境词表补「阻力」**（F4 审查产出）：m3-technical.md:22/120/129/163 教写「阻力位/TDST阻力/上方套牢盘阻力」，旧词表漏扫=文档-gate 失配（漏报方向）；加词只扩扫描面，old-FAIL ⊆ new-FAIL。
- **F4 同构面四问裁定不修**（收紧=提升执法力需真实案例，公理④禁盲改）：G49/G69 全文双条件 AND、G25/G29/G13/G39/G47 单词 presence、G16:696/G67 全文数值对拍——全部第4批 R12 探针覆盖；新观察证据：G49 反编造臂或被「卖方一致预期」措辞误触发，记入探针清单。

验证：全量回归 exit 0（61 门漏报=0 误伤=0，parity 3 票 byte-parity）；/tmp/replay 23 用例 HEAD A/B 276 组对照判决 0 翻转 + 全门 sanity 0 差异；postfix3→4 判决/分数/逐门向量零变化（reasons 面唯一变化=asis_tengjing G60 由笼统一句→4 条具体裸奔行，即改造目的本身）；新增 `regression-tests/test_f2f3_collection.py` 26 判例两极直调（11 门新收集路径 FAIL 必带真值/行摘录 + 干净输入 PASS）入回归链；AST 扫描全 check_g* 「循环内 FAIL return」残留仅 G67:3222（R7 观察档，不在 F3 清单）。

## 2026-08-28 G63 打地鼠根治：批量 reasons + tokenizer 通用剥标识符 + 两层制真值集（plan lazy-dazzling-sifakis v3.1）

触发：万润 002654 / 江海 002484 双会话 transcript 取证——gate 期 output 增量 91% 来自 G63 每轮只报一个违例的循环修复（5 轮/3 轮打地鼠），叠加 tokenizer 把 MA20/ATR14/BIAS_12/ADX22.56 类粘连参数数字解析为价位、真值集漏 TDST（江海 93.68/万润 14.18/中钨 000657 72.22/76.50 三例照抄 TDST 被误判转录错）与漏渲染值豁免通道（曾被迫把券商锚数值迁出 m3 段）。四 commits（730f368/6917829/8dbf91f/f2a8000）全在 `scripts/lib/gate_definitions.py` + fixture：

- **批量收集（730f368）**：`check_g63` 执法循环由循环内 `return GateResult` 改全量收集——(n,near) 去重、top5 + 尾注（「另有 N 处同类转录错（本清单为全量，一轮修完再重跑）」），reasons 渲染走 verify_gates 既有循环、compute_score 只读 passed/failed 零分数影响。fixture +2 反极：双编造价批量照抓（≥2 条全量断言）+ TDST 手抄照抓（真值集补全≠豁免）。
- **tokenizer（6917829）**：`_extract_price_candidates` 三条新剥——①ASCII 标识符整体剥（`[A-Za-z_][A-Za-z_0-9]*(?:\.\d+)?` + 括号调用交替分支，白名单制→通用制免维护）②TD countdown N/13 整数对 ③N日/N天时间窗。设计依据=江海语料实测教训：`ADX22.56` 剥成 `ADX22` 残留 `.56` 撞 S&R 56.87，故小数后缀必须吸收；中文标签行（支撑位14.18）不受影响。
- **两层制真值集（8dbf91f）**：tier-1 对拍集补 TDST（`td.tdst`+`weekly_td.tdst` 的 buy/sell）；tier-2 `rendered` 豁免集（MA_5-250/BOLL×3/close/vwap/千股千评 support+resistance+prime_cost_1d/20d/60d）**精确到分（round 2）相等才豁免**。不并入 truths 的实测依据：密集渲染值按 0.5% 带豁免会吞 (0.5%,5%] 检测带（13.3/13.9/15.2 类编造价全部逃逸）；振荡量（RSI/KDJ/ADX 0-100）不入任何集——入集掩护同量级编造价位。
- **GATE_HINTS 合并（f2a8000）**：与既有 hint（拆行隔离/VWAP 勿标成本位）合并一条，新增全量清单纪律 + 两层制豁免口径。预扫脚本方案降级为一句话流程纪律（三修后 run1 reasons 即全量清单，残余收益仅一次秒级往返）。

验证：67 判例矩阵（反极/照抄正极/标识符/语境/000988 golden 五族）断言失败=0、新误伤=0；万润 run1 重建报告 old FAIL(1r)→new PASS；15 票语料 A/B 824 gate 组合 0 old-PASS→new-FAIL、唯一翻转=000657 G63 fail→pass（存量 tdst 误伤修复）；fixture 61 门×3 票+9 探针漏报=0 误伤=0；parity golden 6 文件 md5 全程未漂；全量回归 exit 0。消费侧同步：stock-analysis-quality 仓 m3-technical.md G63 指引一行收敛（措辞绕行类 workaround 全部作废）。

known-limits：①reasons top5 截断（尾注保总量可见）②`N/13` 整数对作价格区间写法漏抓（A股价格带小数，实证语料未见）③渲染值 1 位小数舍入（如 15.17→15.2）仍报——照抄 2 位小数即免 ④振荡量值（RSI 57 等）与支撑压力同句且落 (0.5%,5%] 带仍报（不入集防编造掩护）⑤全角数字照抓（新旧一致）⑥rendered 字段集=当前已固化渲染字段，未来新增渲染字段需同步扩展。

## 2026-08-24 301682 复盘五修批：M5 幻影信号根因剔除 + G30 reason 携带事件 + 审计三分桶（plan fuzzy-swinging-marble）

触发：301682（宏明电子·次新）全量分析收尾审计——手写 9 处 > 验收线 ≤5 ❌。真实会话数据下钻拆成两个根因 + 一个度量缺陷：① **G30-M5 幻影信号**：`_TIMELINE_CODE_TO_M` 无条件 230→M5，把 2026-03-25「上市状态变动·新股上市」（IPO 事件）编码成 ST/退市 风险信号，三层代价全实证——(a) 触发 3 处手写 + gate 源码排查调试链；(b) reason 只给 code/name 无事件明细，LLM 被迫手挖 timeline 甄别；(c) **发布报告被污染**（analysis_report.md:270 被迫写 200+ 字「M5 属新股上市误编码…如实列示」托底段，给零 ST 风险股票写了 ST/退市 表面）。② 9 处 = 真提取 3 + gate 调试 3 + fetch 补救 3 混装——验收线量的是取数纪律，混装让 gate 失败谱重的会话永远过线且诱发错误工程修法；fetch 三条都含真 `json.dump(` 注入写（`open(p,'w')` 变量间接使 D4 漏报）。③ 度量缺陷：处数不分行為。

- **`capstone_panorama.py` 幻影 M5 源头剔除（修A）**：新增 `_is_phantom_m5(e)`（code 230 且 specific/level1_content=新股上市）→ `present_signals` 派生与 `_render_material_events._add_mc` 两处同款 continue/return（同一语义一个实现，镜像既有 320/090/100 减持-flavor 先例）。影响面：parity 三票零「新股上市」无 golden 漂移；gate_fixture G30 EXPECTED（空报告 FAIL 与信号无关）不翻转；`by_code_count`/raw 投影不动（code 230 存在是事实，只改 M-code 派生语义）。两极验证：301682 快照改后 present_signals 只剩 M3、重大事件行「风险1类：限售解禁」；**剥离报告 :270 托底段后 verify_gates G30 仍 pass**（54 过/1 失败=既有 G28 杜邦无关项）——托底段从此不再需要。
- **`gate_definitions.py` G30 #1 reason 携带底层事件（修B）**：`_g30_signal_event_evidence`——timeline 源未覆盖信号回查 fatal∪risk∪active 经 `_TIMELINE_CODE_TO_M` 映射的最近事件（notice_date+event_type+specific+[code]）附进 finding；reason 携带甄别数据免手挖（B2 reasons-carry-data 先例）。s8 源信号不加（数值趋势信号 kws 已足）。两极：缺「解禁」cov → M3 finding 含 `事件: 2029-03-26 限售解禁·限售解禁 [080]`；含「解禁」cov → 零 finding。
- **`gate_definitions.py` GATE_HINTS 两处（修C，15→16 条）**：G30 追「#1 未 surface 看 reasons 携带事件直接甄别」+ 事件桶核对命令（`any s5_events.data.risk_signals.processed.report_view --depth 1`，实测 1,196c 直出 by_code_count/fatal 桶，替代手写 json.load 过滤 timeline.events）；G54 新条目（**预防性**——本批 3 会话 G54 零 FAIL 效力不可实证）含 adx_state 反陷阱：**ADX 真值以 dmi.ADX 为准，adx_state 括号内嵌值是另一路计算**（301682 实测 36.59 vs dmi.ADX 29.885/ADXR 35.313 均不等，照抄撞 5% 容差）。
- **`token_audit.py` 处数三分桶 semantics v3（修D，chars 口径不变）**：hit dict 加 bucket（`gate_definitions` 字面量>gate；`akshare`/`financial-data-routing`>fetch；其余 extract）+ 注入写标记；② 加 🔧 gate 调试 / 🔄 fetch 补救（⚠️ 注入写 N 处）两段；③ 检查项与 [v2] stdout 行改分解式 `手写 N = 真提取 X（视图内 a / 视图外 b）+ gate Y + fetch Z`，**验收线 ≤5 此后 = 真提取桶**；hist_entry 加 hw_extract/hw_gate/hw_fetch；版本戳 v3（处数口径与 v2 不可比、chars 可比）。注入写标记必须 `re.search(r"json\.dump\s*\(", c)`——**禁裸子串**（误中 json.dumps 打印惯用法，实测 gate/extract 桶多条全被误点亮）。test_token_audit 6 测试（新增 test_bucket_split：3=1+1+1 分解/🔧🔄 段/json.dumps 反例不误中/D4 盲区写回仍 0 透明断言）。
- **跨会话泛化重放**：301682 `9=3（2/1）+3+3｜注入写3｜写回0｜88.3%（50,964/6,723）｜总取数 57,687c` 与 v2 基线逐位一致（chars 未漂）；688127 `6=4（2/2）+2+0`（外科豁免 2 处机制被真实使用）；600961 `23=21（12/9）+2+0`——**桶不洗白坏会话**（提取 21 照样 ❌）。三会话 38 处签名零误归。

明确不做（证据否决）：❌ present_signals 视图挂载点（runtime 派生量 snapshot 全树 0 命中，路径名不存在；事件桶已由 report_view 投影）；❌ `--structure` 顶层键速览（与 `--list` scenes 行同语义）；❌ 消费模块改动（`--list` 758c < 顶层探查 2,482c 合规更省；过滤形态 360c < 合规 1,196c 属 rule⑤ 外科配额内）；❌ D4 写回正则扩捕变量间接（fetch 桶 ⚠️ 透明标记代替）；❌ 预加 G52/G57/G60/G64 hint（3 会话实测谱未撞）。边界记录：600961 型写作期爆发（t138-153 连续 16 处）是残留主战场，属散文/行为层既有机制覆盖，非本批范围。

验证：修A/修B 两极 + 端到端（剥托底段 verify G30 pass）；修D 三会话重放逐位对拍；test_token_audit 6 绿；G54 两命令实跑（signals.state 直出三键 / `--field ADX`→29.89）；全量回归 exit 0（parity 三票 byte-parity + 55 门漏报=0）。

## 2026-08-23 token 审计 v3 + `--field` 外科投影 + GATE_HINTS 数据行（plan stateful-finding-alpaca Fix A-E）

触发：688195 会话审计 v3 深度归因——手写 18 处（v2 口径 4 视图内 / 14 视图外）+ sed 撞 gate_definitions 16 次 33,610c；P4 gate 修复期 6 处 8,346c（48.3% chars）是最大单一簇。四条裁决（v1→v4 全实证）：①m11 ❌ 系 `--latest` mtime 张冠李戴（688195 实际 ✅）；②「全量转合规」成本 +12.8% 反升——**纪律线与成本线张力是根因**；③6/7 sed 热门 gate 已有 hint 仍 sed（要执法语义非一句话）；④s35/lhb 视图外清零系**数据真空非纪律**（items=0 / never_listed，断空必验裁定，勿再引为修复证据）。

- **`token_audit.py` v3（Fix A）**：A1 被分析文件路径打印 + 扫前 5 条用户文本消息提码错目标 ⚠️（杀 `--latest` 不可检测）；A2 gate 源码 Bash 侧访问透明度行（sed/grep/cat/awk 撞 gate_definitions，与手写并集去重）；A3 手写全列 + `# rule5-surgical` 外科豁免桶（quota≤2 超额 ⚠️）；A4 总账行 `CLI+手写=总取数` + `~/.cache/token_audit_history.jsonl` 环比（gate FAIL/P4 dump 上下文列；`TOKEN_AUDIT_NO_HISTORY` 防污染闸门先读后写）；A5 `--field` 调用分布行（防 coverage 灌水）。test_token_audit 5 测试。
- **`snapshot_view.py` `--field` 外科投影（Fix C）**：白名单单 flag（非 DSL）`--raw <路径> --field <字段>`——行表→全期单列「日期: 值」（data/data_full 双键兜底=家规）；字段缺失显式报错+前 10 可用字段（杀静默 None 假阳形态）；空列表三态「0 行（真空）」；`.N` 含点拒绝。**H1 双帽**：非标量过 `_any_render(depth=1)` 10 条帽 + 4,000c 硬截断（remind_records x97 裸 dump 70.7K → 双帽 4,120c）。C1 balance footer（8 期合同负债，routing 8 季度执法要求）+ `_print_period_table` data-driven 截断指针；C2 timeline 子层指针。test_snapshot_view_field 11 测试已接线。**实测成本**：合同负债 12 期 304c / targetPrice 143c / primary_type 47c——纪律合规与省 token 从此同向（#04 案例 25.8×→1.2×）。
- **`gate_definitions.py` GATE_HINTS 扩容（Fix B）**：sed 热门 7 gate（G61/G30/G45/G48/G58/G62 + 新增 G56，14→15 条）各补「数据核对」现成命令，选型**最小充分非最小成本**——单字段即充分用 `--field`（G45 targetPrice/G48 programs/G58 valuation_percentile/G30 primary_type），需结构对拍保持 `any -d2`（G61 conclusions 四键/G56 五块结构对拍，勿用 primary_type 3c 不充分换 gate 重试负优化）；G62 附全表第 2 列方向词 `grep|awk` 计数命令（真实报告实测）。
- **SKILL.md 取数硬规则（Fix D）**：规则① 视图外字段改**显式阶梯** `视图→any→--field→--raw` + H3 分流（单/双字段→--field；≥3 字段或结构未知→一次 any -d2；3 次 --field 已反超）+ 宽表警示（balance_sheet：any -d2 29.6K > --raw 6.4K > 视图 2.5K > --field 0.28K，宽表取列必 --field）；规则⑤ 扩句（全景/跨 scene 复合提取等 --field 不适用形态，`# rule5-surgical` 声明豁免，应趋零）+ 中段自查锚（json.load 冲动→先 --list 对照，单字段直接 --field）+ gate 修复期同规则（hint 已带命令照抄即合规）；命令块补 ⑤ --field 示例、③ 扁平小节示例补千股千评。
- **复评触发器新形式（只定形式，数值 n=2 后冻结）**：`覆盖率<80% 或 豁免超额/无声明手写残余按 scene 聚类达次数阈值 → 复评该 scene 引擎侧（footer/--field/视图扩期，按 V9 尺寸优先级）`。旧形式作废原因：字面不触发（fund_flow 1 处 369c/lhb 0/s35 0）+ scene 列表窄于 A2 拒绝集 + P5 数值倒推。**n=2 环比基线**（±20% 方向对照非硬线）：总取数 82,365c / sed 侧 34,087c（A2 落地口径）。n=2 选股：类型相异（次新/亏损股 gate 失败谱高压，真考 Fix B 效力）。
- **审计纪律（V4）**：收尾审计一律显式传会话路径，**禁 `--latest`**（mtime 会选中活跃会话自身或错目标——A1 ⚠️ 是事后检测不是事前防护）。

验证：T1 冻结语料重放总取数 82,365c 与 v2 完全一致（口径未漂）；T2 错目标 ⚠️ 必出；T3 7 gate hint 关键词+命令实跑全绿；T4 --field 六案例+双帽 4,120c+footer/指针全过；全量回归 exit 0（三票 parity byte-parity 完好）。明确不做：json.load 钩子 / 查询 DSL / 新增 named 视图 / FLAT_SECTIONS 扩容 / runner 预计算投影（消费层严格占优）/ --find 反向索引（重复 any -d1 职能）/ 修 sed 行为（sanctioned，只加透明度）。

## 2026-08-22 token 审计 v2 + 取数行为修复批（plan fuzzy-swinging-marble T2/T3/T4）

触发：688048 会话 token 审计——手写 `json.load(snapshot)` 35 处（v2 口径 33 / 31,804c）vs CLI 覆盖率 57%（目标 ≤5 / >80%）。全量归因：T2 行为缺口 29 处（79% chars，any 实测全部可达且**输出 ≤ 手写**：top10 1,887 vs 3,790c——手写非省 token 理性选择，是缺规范的训练默认）/ T3 流程缺口 1 处（precheck.py 孤儿，SKILL 零引用）/ T4 度量四重假信号（双计 70=35×2、排除不对称、自匹配两路径、分层内联表与死常量漂移）。

- **`token_audit.py` v2（D1-D5）**：单一计数源 handwrite_hits（tool_use-only 天然去重，扩成 turn/chars/in_view/全命令记录）；覆盖率 result-only（`kind=="result"` 块）；分层=命令提取路径 vs 复活常量 `VIEW_MOUNT_PREFIXES` 全链前缀匹配（**禁尾分量**——`data` 是 4 挂载点尾分量，尾匹配 4 处假阳）；排除 `.jsonl` 自匹配（轮364/367 恰中、33 处零误伤）；写回=写模式 open 的**文件参数本身**命中快照路径（D4，防跨文件假阳——旧 3 条件 AND 把「读快照+写报告md」误判 7 处）；头部 `semantics: v2` 版本戳。
- **`test_token_audit.py`（D6）**：合成 9 命令微型会话 → 断言处数/视图内外/写回/覆盖率全语义（含跨文件假阳反例）。表计是验收线的尺，尺的语义此后由回归脚本判定，**永久消除 LLM 手跑模拟重验**（用户成本原则：算 token 的成本必须低、脚本顺手完成、绝不 LLM 手算）。
- **`snapshot_view.py`**：F1 独立 `--raw <path>` 修复（原 SKILL:201 教的全文兜底形式是静默 no-op——main() 只在命名视图分支处理 --raw）；B2 `--list` 增 scenes 行（顶层 scene 键=any 目标空间，可发现性断裂修复）；B2b any list 展开上限 10 条+`…(+N more; 用 .N 单条下钻)`（实测 remind_records 直接展开 95 条=77,349c token 炸弹→8,815c，引擎 cap 是底线，散文纪律仍须遵守）。
- **`verify_gates.py`**：verdict==PASS 且非 quiet 时 stdout 末尾打印可复制 📌 指针行（`args.profile` 非 `profile_name`，与 check_pointer 双匹配）——消除「为格式提前读 m11-gates.md」预读；已实跑对拍 check_pointer PASS。
- **`precheck.py` +15 行**：执行后验证脚本化（income 期数双键兜底/主营构成三态/`_warnings` 前5条，全 stderr）——T3「Skill 要求验收却没给工具」的工具层。
- **`update_checklist.py`**：`c50 → s10_checklist.completed` **叶子**映射（dict 级会因无 status 键恒 FAIL——两极验证：叶子 True/假键 False/dict 级 False）；在场证明语义（同 c13/c14），不造 completed==12 阈值（零覆盖股合法 <12，==12 误伤真空股）。
- **SKILL.md 散文批**：① 数据读取节 any 示例 3→4 条（顶层 scene 第一步/逐层下钻/扁平 depth2/单行 --raw，四命令全实跑验证）+ **取数硬规则五条**（视图优先/any 第一步禁猜深路径禁 json.load 探查/长列表 `.N` 纪律/关键词定位/computed_metrics 先查+`python3 -c` ≤40行·每会话≤2次唯一豁免）+ 688048 实证与经济性对拍入「为什么」；② Phase 2 runner 后第一步 precheck **stop-gate**（exit 1 停机——复活死掉的 gate，本会话实测零人跑过它）；③ Phase 4 指针行从 verify 输出复制+粘贴后重跑刷新 sidecar（mtime 新鲜度）+ c50 `--evidence-from` 示例（仿 c70 先例）。
- **routing SKILL.md**：执行后验证三项改写——①②已内置 precheck（跑它，禁手写 json.load 验收）、③[src:] 属写作期。
- **run_regression.sh** +2 行：test_report_views_kline / test_token_audit（脚本显式列举非 glob，不加则防线永不跑）。

验证：全量回归 exit 0（含 D6/A1T 新行、parity 三票 byte-parity 完好）；DoD 冻结语料重放 33/23/10/写回0/59.2% 逐一命中；precheck/verify 指针行/c50 CLI 端到端实跑绿。明确不做：禁 json.load 钩子拦截、禁查询 DSL、不新增 named 视图（六候选 any 输出合格，扩视图违 FLAT_SECTIONS 哲学；复评触发器=下个干净会话覆盖率仍<80% 且残余由 fund_flow/lhb/s35 主导）、D7 SessionEnd hook 默认不加（待用户点头）。

## 2026-08-18 报告归档固定目录 + 命名规范

- **SKILL.md Phase 4 第 3 步（新增）**：Gate 全过后三件套归档到 `~/analysis_report/analysis_report-<模型>-<股票名>-<代码>/`（原始 md 明文 [src:] / sidecar / _publish 剥离副本）。用户指令：目录固定 `/home/ubuntu/analysis_report/`，用股票名+代码区分，例 `analysis_report-glm5.1-源杰科技-688498`。同股重分析各自成目录不覆盖。
- 首次归档完成：源杰科技三件套（sidecar PASS / self_score 100）。

验证：归档目录 ls 三件套齐全；sidecar JSON 可解析。


## 2026-08-18 发布层剥离器 strip_src_for_publish + src 写法契约 fixture

- **背景**：用户视认证实腾讯文档 smartcanvas 前台**原样显示** `<!-- [src:...] -->` 注释文本（散文+表格皆可见）——推翻此前「前台不渲染」判断（存储转义 ≠ 前台隐藏），隐藏式写法否决。gate 侧本免疫（21 匹配点静态审计 + A/B 全量对拍 55 gate byte-equal），阅读体验诉求改由**发布层剥离**满足。
- **新增 `scripts/strip_src_for_publish.py`**：本地 md（gate 执法用，明文 `[src:]`）→ 外部文档发布副本（剥明文+注释两式；`[verified:]` 指针保留可回查 sidecar；行数/表格结构不变；出口断言零残留+行数守恒）。真实报告实测：226 标记全剥、592 行不变、207 表格行不变。
- **SKILL.md Phase 4**：新增第 6 步——写入腾讯文档前先跑剥离器，发布用副本、原 md 永不剥离。
- **新增 `regression-tests/test_src_hidden_style.py`**（7 tests）：①gate 对注释包裹等价性（G45 行级豁免/freshness 双通道隔离/G60 Layer1 锚，含必FAIL反例）；②G62 tally 方向词格禁区（`cells[1]` 精确匹配漏数实锤）；③strip_for_publish 两式全剥+指针保留+结构不变；④转换器口径幂等（防双包裹）。已接线 run_regression.sh。
- **规范同步**（quality 仓）：m11 G21 行第⑤条 + m12 §12.3 第 0 条改写为「明文+发布层剥离」，4 条实测禁区留档（跨行注释/行首\|前/行尾\|后/tally 方向词格）。

验证：test_src_hidden_style 7 tests OK；strip 正反例双验（[verified:] 保留、[src: 全剥）；回归 exit 0。


## 2026-08-18 m12 开头速览块接入 orchestrator（模式 A）

- **SKILL.md Phase 3 加载表**：模式 A 模块序列头部加 `m12`（速览块与 m6 capstone 对称：m12 开头收口 / m6 结尾论证）；模式 B 不加（quick 无估值/财务深度，速览缺字段）。
- **generate_checklist.py**：模式 A phase_3 加 `c59`（m12 开头速览块：TL;DR 两段式，G11 声明后、首个章节前）。c59 无历史占用（全仓 grep 验证）；B 模式清单不含 c59（生成实测 0 命中）。模板本体与字段缺失态规范在 quality 仓 `references/modules/m12-summary.md`（两仓分工不变：orchestrator 管路由/清单，quality 管写作规范）。

验证：generate_checklist A(600519) 38 步含 c59 / B 15 步无 c59；回归 exit 0（55 门漏报=0）。


## 2026-08-17 Gate 体系 2.0 + S1/S3（plan ticklish-soaring-beacon Part B）

> 设计论证核心：8 次真实运行失败人口全在 golden/自定义数值族（G27/G45/G51/G52/G54/G55/G56/G58/G59），consume 族零失败——**重写零失败区=承担 56 门行为漂移风险换不来成功率**。最优解 = 保留全部具名 checker，建「一张注册表驱动三件事」（preflight 前置告知 / verify 后置执法 / 词表审计）+ reasons 精准投放到真实失败人口。parity 硬闸：8 对 report+snapshot 逐门 verdict diff==0。

- **B-pilot G53 同维真值**：删 :2180/:2182 跨维裸词「放量/缩量」（量价维词被换手分位维执法=维度错配，全 56 门唯一确诊）；新增量价同维反捏造（报告含"放量"→`volume_price` 须有支撑：volume_state=="放量"∨ratio_rt>1∨vs_ma20>1；含"缩量"对偶）；volume_price 缺→skip（三态）。
- **B1 GATE_REGISTRY 单一真相源**（gate_definitions.py 文件尾）：一行一门 `{checker, weight, owner, data_dim, requires, fail_hint[, preview_dims]}`；GATE_WEIGHTS 从注册表派生（外部 import 面不变）；import 时一致性断言（REGISTRY==ALL_GATES==GATE_CHECKERS 三方同步、退役门不重叠、weight≥1）。
- **B2 失败人口 9 门原生 reasons**（G27/G45/G51/G52/G54/G55/G56/G58/G59）：FAIL 分支返 `GateResult(passed=False, reasons=[具体值+可执行指引])`；其余 bool 门由注册表 fail_hint 薄壳兜底。`GateResult` 的 `__bool__=passed` 保裸 bool 断言兼容。
- **B3 占位退役 56→52**：G10/G18/G46/G50 移出活跃集（恒 PASS 死重；执法力已由 G30#1 fatal_events 承接零损失）；`RETIRED_GATES` 留档 `{retired, successor, reason}` 防编号误复用；quick auto_pass 同步清理。
- **B4 preflight 模式**（verify_gates.py `--preflight --data-snapshot D.json`）：写作**前**从注册表+活 snapshot 生成逐门要求清单（🟢 须消费对齐/⚪ 三态豁免禁编造 + 真值预览）；要求与执法同源零漂移，round-1「要求不明」类 FAIL（603986 六败/600703 结构败）结构性消失。
- **B5 盲区新门 G62-64**（SOFT weight1，漏报可忍误报不可忍）：G62 tally 跨章一致（§6.1 表方向计数==§6.4 自称数）；G63 技术位数值对拍（fib/S&R/成本位 == snapshot ±0.5%，治 666→662 转录错）；G64 资金流术语口径（「大单」行禁写主力口径 trend_5/10/20d/net_flow）。fixture 策展同步补齐。
- **B6 m11 Gate 编写公理 5 条**（m11-gates.md）：真值优先于措辞 / 词表入表三问 / 跨维即 bug / 提升不靠放宽 / FAIL 可执行。配 parity harness `/tmp/gate_ab_parity.py`（8 对全 MATCH）。
- **S1 修复**（data_snapshot.py fetch_web_research）：dict 自动解包 items + 非 list[dict] raise + 旧 `[web_research]` fetch_log 条目清理；配 runner CLI 侧 exit(2)（routing 仓）。
- **S3 修复**（data_snapshot.py）：`log_fetch()` 公共方法（持锁）+ 缓存命中 `status="cached"` 记录 + futu client 注册（try/except 静默）。
- **data_contracts.py 新叶**：targetPrice.source/as_of、analystRating.source/em_counts/em_compre_rating、em_annual/em_annual_latest_period、fair_value_estimate、reports_meta[].aim_price（均 CONFIRMED + 消费者配对）；snapshot_schema.md 同步登记（新叶 schema_coverage warn 清零）。

验证：test_data_contracts 15 tests 0 error；parity 8 对 diff==0；恒等断言 `GATE_CHECKERS['G37'] is check_g37` 不破；回归 exit 0。

- **退役引用残留清理（08-17 晚，全仓注释/文档审计）**：degradation-strategy.md 删 G10 映射行 + "G15, G18"→G15 + "所有 14 个 scene" 计数措辞改 `len(SCENES)`；gate_definitions.py PROFILES 注释删 Step 0/Step 2 changelog 历史句、G57/G58 docstring "mirror G50" 改范式措辞；announcement_materiality.py detect_actor_tier docstring 去 G46 引用（改 m4 surface 对拍措辞）。workspace 级 CLAUDE.md/AGENTS.md 同步：事件层旧叙事（M-P 码/公告大全）→ timeline 45 码 + fatal 码表、AGENTS 删 `akshare-stock` 死引用、WebSearch 节补 Exa 优先链。回归 exit 0。

## 2026-08-16 删除审计意见数据维度（用户决定：不需要）
- generate_checklist.py：删 c_d6_audit（m9.3 审计意见排雷）清单项
- update_checklist.py：删 c_d6_audit 孤儿 evidence 映射（s36_annual_analysis.data）
- 保留：announcement_materiality 330 非标审计致命码 + gate 事件 surface 词表「审计」（事件层，非数据维度）

## 2026-08-20 转换器新增 SGR 条形段着色（░灰/▓红，表格单元格内）

- **背景**：SGR 进度条图考古定性——历史三形态（fence/裸文本/表格）中 fence 读回 `<Unsupported type="code"/>`、裸文本多行合并单段（条形错位=「一直不稳定」根因），唯一稳定载体=三列表格（m2 §2.13 模板已同步换表格，quality 仓）。G51「进度 OR █」代理检测曾被无关「进度」字样误满足，致 300121 图表被静默删除仍 55/55。
- **新增 `colorize_bars()`**：表格行内 `░{2,}`→`<Mark color="grey">`（未透支余量段）、`▓{2,}`→`<Mark bold color="red">`（透支段）。实测 grey Mark 在 TableCell 内存活（测试档 OTPHpXwLFMPX 验后删）。源报告保持纯文本 █░▓（单色语义分明），颜色只在发布层。
- **模板改三列两行**（用户设计）：差值并入实际营收行——未透支 `█×a+░×(s−a)` 总长=SGR 行直读余量；透支 `█×s+▓×(a−s)` 总长超出 SGR 行直读超载。刻度规则 M=max(SGR,|实际|)=10 格。
- 验证：300121 v24 发布读回 `█<Mark color="grey">░░░░░░░░░</Mark>` 完整落档；55 gate 全过；回归 exit 0。

## 2026-08-20 新增发布侧 UI 转换器 md_to_smartcanvas.py

- **新增 `scripts/md_to_smartcanvas.py`**：发布版 md → 腾讯智能文档 MDX。四层增强：①全量 `**X**`→`<Mark bold>`（组件路径根治全角标点侧翼失效——SGR 字面星号根因）；②`**未来事件**`/`**历史事件**` 区块→Callout（⏳ light_blue/blue vs ✅ light_grey/grey，事件禁 table）；③决策短行（综合评级/主推荐动作，≤120 字符）→`<Paragraph light_yellow>`；④风险行（止损/破位/致命/fatal）→`<Mark bold color="red">`（列表只红加粗段保留 bullet）。borderColor 白名单硬校验（非白名单静默回退 green）。
- **高亮密度预算（用户实时纠偏）**：满屏高亮=没有高亮；PARA_HIGHLIGHT_KEYS 仅 2 键 + 120 字符上限，分析长段不加底色靠结论句加粗。
- 管线定位：report.md → strip_src_for_publish.py → 本脚本 → mcporter create_smartcanvas_by_mdx。UI 增强全部在转换层，源报告零格式改动（gate 免疫，300121 改后 55/55 实证）。规范全文见 stock-analysis-quality `references/report-ui-guide.md`。

## 2026-08-20 修 parity 回放时钟泄漏（300394 定时炸弹）

- **现象**：`parity/test_parity_gate.py` 300394 FAIL——`2026-08-19 中报披露`事件 golden=future / 回放=historical，historical 列表整体位移。stash 实证与当日改动无关（先于本次存在，golden 08-18 刷新后次日起必炸）。
- **根因**：`_patch_project_datetime` 只 patch 项目模块级 `datetime`/`date` 名，而 `runner._build_timeline` 用**函数内局部** `from datetime import datetime`——从 `sys.modules['datetime']` 取属性，模块属性 patch 覆盖不到 → 回放用真实时钟，日历越过事件日即翻转 future↔historical。
- **修复**：patch 清单头部追加 `mock.patch.object(datetime模块, 'datetime'/'date', frozen类)` 两行。三票 golden 均 byte-match（golden 本就是冻结时钟正确产物，无需刷新 golden、不动 runner）。
- **教训**：时间冻结 mock 必须**同时**覆盖「模块级绑定名」与「datetime 模块自身属性」两条解析路径；含未来日期事件（中报披露日）的语料在 golden 生成次日起即触发泄漏路径。

## 2026-08-20 Phase 3 改 JIT 模块加载 + snapshot_view CLI（plan buzzing-wandering-lemur）

- **`scripts/snapshot_view.py` 新增**：snapshot 七视图直出 CLI（kline/cash_flow/income/mainfina/news/events/holder + --list + --raw 任意路径兜底）。VIEW_PATHS 与 `financial-data-routing/report_views.py` 的挂载点一一对应（单一真相源=report_views.attach_report_views）。写报告取数唯一入口，替代 LLM 手写提取脚本（token 审计：手写脚本 stdout 浪费 ~20%）。
- **SKILL.md Phase 3 双改**：① 模块 JIT 加载——写某模块章节前才 Read 该模块文件（替代「Phase 3 开始全量 Read 13 文件」，后段模块推迟 100+ 轮暴露）；m11-gates.md 延迟到首次 verify FAIL 时才读（verify 输出自带失败原因）。② 数据读取规范——snapshot_view 命令清单 + 「视图没有的字段才 --raw，禁绕过 CLI 手写 json.load 提取脚本」。E8 实验证伪了 m*.md 拆分方案（可外移行仅 1-15%），JIT 是零内容改动的替代。
- 契约登记与 parity golden 刷新详见 financial-data-routing 仓同日条目（改动主体在彼仓 runner/report_views）。

## 2026-08-20 token_audit.py 会话 token 事后审计 + SKILL.md Phase 6 归档规范

- **`scripts/token_audit.py` 新增**：复盘用事后审计（分析会话零负担——记录的活交给引擎，哲学同 report_view 投影层）。双口径：per-request 真实 usage（JSONL assistant.usage 累计，input/cache_read/output 分列）+ 内容块静态加权（chars×存活轮数=context 压力归因）。维度=Phase（P0/P2/P3/P4/P5，由工具调用序列确定性推断）×类别（模块文件mXX/视图/Skill加载/runner/手写提取stdout/websearch/LLM输出）。
- **5 项新管线检查项固化进脚本**：模块 JIT（Read 轮次跨度）/ m11 延迟 / 视图直读计数 / 无手写提取（json.load+snapshot 正则，stdout chars+加权压力量化）/ 模块文件占比 vs 基线 32.3%（瑞丰 300243 旧路径）。
- **首测 002859 半程**：JIT ✅（跨度 87 轮）/ m11 ✅ / 视图 ✅（5 次 22.8K chars）/ 模块占比 ✅（27.3%<32.3%）；❌ 手写提取 36 处 / stdout 48.7K chars / 压力 13.1%——审计抓到真执行偏差（视图覆盖字段仍被 json.load 直读），旧 ~20% 浪费主要残留在手。
- **SKILL.md 新增 Phase 6**：报告归档后 `token_audit.py --latest --stock <code>` 一条命令，产出 `~/analysis_report/token_audits/<code>-<日期>.md`。

## 2026-08-20 gate FAIL 自解释 + any 两级探查 + token_audit v2（plan buzzing-wandering-lemur）

- **`lib/gate_definitions.py` +GATE_HINTS 字典**（14 高频 gate：G1/G16/G30/G45/G47/G48/G51/G53/G55/G58/G59/G61/G62/G63）：各 check_g* docstring 提炼（败因+修法+误伤防），不新造语义；`verify_gates._build_action_required` FAIL 时注入 `💡 Gxx 修法`。动因：002859 审计抓到 gate_definitions 全文 178K 被读入一次（G63 FAIL 排障）≈ 全部模块文件之和。冒烟：G63 反例 FAIL→hint→照抄真值→PASS 闭环。
- **`SKILL.md` Phase 4 规范**：FAIL 修法看 verify hint → 不足读 m11-gates.md（20.3K）→ **禁 Read gate_definitions.py**；Phase 3 命令清单扩 14 视图 + any 扁平小节示例；Phase 2 模式A 调用顺序图精简（原图含已退役 cninfo PDF 步骤与过时 4-subagent 编排，实测 runner fetch_for_mode 单命令全量并发）。
- **`snapshot_view.py` +7 printer + any 两级探查**：`any <scene或路径> [--depth N]` 键树渲染（默认1，扁平小节建议2）；视图未挂载时报错自带 any 兜底路径。
- **`token_audit.py` v2**：手写分级（路径∈14 视图挂载点=❌违规 / 视图外=info 建议 any）；复合命令（snapshot_view+json.load 并存）归「复合」不再误计手写；新检查项 gate 源码零读入（Read gate_definitions→❌）+ 视图覆盖率>80%；审计回放 002859 原会话验证分类变准（视图内 48/视图外 18/gate 读 1——历史事实，分类变准≠消失）。
- **回归**：run_regression.sh exit 0（契约层 13+7+16 tests + parity 3票 + 运行时层 55门×3票 漏报=0）。

## 2026-08-25 compute_self_score 覆盖分母 profile 感知（600089 模式B会话）

- **`lib/gate_definitions.py` compute_self_score**：data_coverage 分母原固定 `_EXPECTED_SCENES`（全量 11 scene），profile_quick（模式B runner 只拉 s2+s4）数学上限 ≈64 分，c70 的 `self_score>=80` 出口契约结构性不可达（update_checklist 实测 exit 1）。修复：`profile=="profile_quick"` 时分母收缩为 `_QUICK_EXPECTED_SCENES`（s2_quote_kline + s4_technical，与 runner fetch_for_mode 模式B场景集对齐）；full profile 分母不变。dimensions.total 同步随分母。
- **验证**：600089 模式B报告 sidecar self_score 64→100，c70 打勾通过；正例（quick 两 scene has_data=True）+ 反例（full 分母不变）已验。回归 run_regression.sh exit 0（契约层全绿 + parity 3票 + 运行时层 55门×3票 漏报=0）。

## 2026-08-26 模式B v2 深度重构：G65-G70 + full/ 存档 + token_audit B 接入 + 盲测 PASS（plan lexical-marinating-lamport）

**P5 盲测终局（两层）**：LLM 全流程层（12 份 as-of 报告，12/12 gate 100/100）——HIGH 15d **4/5=80% ✅ ≥70% 验收线**（5d 80%/10d 100%）；MED 15d 3/4=75%（如实标注不进门禁）；NEUTRAL 0/3（诚实输出区，±2% 容差对高波股偏苛，已知局限）。引擎层（20 as-of 快照全量）HIGH 15d 11/13=84.6%。miss 归因：002008@0804（前 10 天 +11% 后回落——「冲高减仓」动作建议恰好覆盖）、300243@0723 5d miss 后 10d/15d 兑现（印证 15d 视野设计）。

- **`lib/gate_definitions.py` +6 gates（G65-G70，B_ONLY_GATES 双保险）**：①`B_ONLY_GATES` 清单→profile_full 排除+profile_quick 追加；②每 check_gNN 顶部 `mode != "B"` 短路。**五方注册同步**（GATE_REGISTRY/ALL_GATES/GATE_CHECKERS/GATE_DESCS/GATE_WEIGHTS，漏则 import 崩）。G65 forecast block 对拍（direction/confidence/p=±0.03 双刻度/胜率同源引用；NEUTRAL 不对拍 p 但区间必现）；G66 多周期状态表（≥3 周期词+resonance 原词+**行级反义对拍**——周期状态行内禁 up↔down 反义词除非行内有背离词）；G67 量价分档键值如实；G68 分级止损（首列档位行 `60m|日|周|月 MA*` 档价 ±1%+ATR 行+凯利 ±0.01——kelly=0.0 中性股也须写数值）；G69 筹码资金结构三态分母（`_scene_has_data`：缺席/degraded/failed 不计分母，as-of 批 fund_flow/valuation/chip 全降级→need 收缩至 margin 1，300243 四维全降级→need=0 PASS）；G70 大盘 verdict 对拍。`_QUICK_EXPECTED_SCENES` +s3_fund_flow+market_context（结构性必在场；valuation best-effort 不进分母 failed 不误扣）。全部反例 FAIL/正例 PASS 两极验证。
- **`scripts/backtest_score.py`（新）**：读报告 forecast block → 拉 T+1~今天日K → 5/10/15d 方向命中（bull/bear 符号、neutral=|ret|≤预期区间半宽缺席 ±2%；insufficient_history/failed 不计分母）→ `--aggregate` 按置信层汇总（isinstance list/dict 两态，单份 dict 不再炸）。
- **`scripts/token_audit.py` B 接入（零 LLM 成本）**：VIEW_NAMES/VIEW_TO_MODULE +short_term/market_context/fund_flow 条目（不扩则 B 合法视图调用误判手写假阳性）；Phase 推断 B 规则；B 模块占比单列基线（m3/m6/m36/m37，不与 A 32.3% 混比）。**用户拍板：模式 B 报告 c70 后必跑 token 审计（推翻 2026-08-25 旧指令，memory 已同步）**。P5 批审计 `~/analysis_report/token_audits/blindtest-P5-20260826-1947.md`（覆盖率 41.9%）——**归因结论：开发会话（1210 轮含 gate 调试）不代表 B 常规流程；datapack 模式（一次投影 N 票全字段）比逐票视图更省 token，是审计口径未覆盖的合法形态，列给用户 review**。
- **`scripts/lib/data_snapshot.py`**：`__init__(stock_code, as_of=None)` 加法式参数（构造期分片：缓存路径/staleness 基准/存档日期三处随 as-of）；`save_full_archive()` full/ 合并存档（场景级 merge，旧档为底本次覆盖同名键）；`detect_prior_data()` 复用诊断。
- **`scripts/snapshot_view.py`**：+VIEW_PATHS short_term/market_context/fund_flow；`build_short_term_view` presence-gated（short_term_enrich 缺席 no-op）。**未扩展 build_technical_view（3 份 parity golden 面）**。
- **`scripts/lib/capstone_panorama.py`**：`panorama(data)` 读 `data.get("mode")` → B 用短期定性维度清单替换 qual_required（forecast block/多周期共振/止损表/凯利）。
- **`scripts/generate_checklist.py`**：PHASE_STEPS["B"] 幽灵步清理（c62 m9→m36/m37、c12 自算→确认预计算、c13 分时→60min 信号）；B runner 命令补重定向；detect_mode 词表 v2（见 routing 仓条目）。`precheck.py`/`question_to_data_map.json` mode 感知（B core=[s2,s4,s3]；资金流 API 修正 stock_individual_fund_flow）。
- **`regression-tests/test_full_archive.py`（新，入回归）**：5 断言——full/ 全量性/同日 B 复用 stderr+场景复制/B 存档=A∪B/cleanup 后 full/ 完好/90 天旧档识别。
- **`scripts/lib/data_contracts.py`**：+market_context/intraday_60min 契约（mode=[B] 起步）；valuation_snapshot/s_margin 翻转 [A,B]；m36/m37 消费方注册（`^m\d+$` 合规）。
- 数据层引擎/场景/存档细节见 financial-data-routing 仓同日条目；模块文档 m36/m37 见 stock-analysis-quality 仓。A 零扰动：parity 3 票 byte-parity 绿贯穿全程（P1/P2/P3/P4/P6 五个回归跑点 exit 0）。

## 2026-08-27 parity 工具化 + 收单三态测试固化（000657 回归会话产品化；用户指令：禁手写一次性脚本）

- **`regression-tests/parity/refresh_golden.py`（新工具）**：把「撞 parity FAIL → diff-scope 证明 → 离线外科刷新 golden」标准动作从会话手写脚本固化为一条命令。`--diff-scope [--expect-prefix $<路径>]...` 逐路径深比 golden vs 当前代码回放（冻结时钟+封 socket+both_nan 短路复用 test_parity_gate 单一实现），前缀白名单越界即 exit 1；`--refresh` 离线回放重算写回 *.gz（不联网不重 fetch）+ 写回自验 byte-parity。零代码参数自动遍历 corpus 全票。test_parity_gate 漂移断言消息追加工具指路（失败点即见修法）。
- **`test_s10_checklist_cached.py`（新契约测试，已接线 run_regression.sh）**：收单 `check_data_completeness` 三态语义两极固化——ok/cached→True、failed/键缺失→False、macro_data 判定点同族覆盖。防 cached 漏计 bug 类复发（本次 financial-data-routing 仓修复的行为面）。

## 2026-08-27 新增 test_market_context_order.py + strip invariant 测试去环境耦合（market_context 排序契约修复批）

- **test_market_context_order.py**（新，接线 run_regression.sh）：固化 market_context 排序契约两极——desc 存储→`index_sh.last` 必取最新值、`classify_regime` 反转喂入 trend_up 正例 + 直喂 desc 的 naive 值必不同（反例面）、industry_name 缺失时 board/board_fund_flow 键必挂载 degraded、board ok 信封形状（pt 码择优/最新首/closes desc/latest_period）。零网络：mock westock_client.call/kline + sys.modules akshare 桩。
- **test_src_hidden_style.py 断言收窄**：旧 `test_real_report_structure_invariant` 采样公共路径 `/tmp/analysis_report.md` 当「规范真实语料」——被中科曙光(603019)会话报告复写后，其正文非 src 模板占位注释 `<!-- PART-B -->` 造成脆断 FAIL（strip 职责只剥 src 隐藏注记，模板注释不在职责面）。修正为仓库内固化 fixture（fixtures/strip_publish_sample.md）+ 断言收窄至 [src:] 两式零残留 + 显式断言模板注释原样保留（职责边界自证）。回归全绿 exit 0，parity 3 票 byte-parity 零漂移。

## 2026-08-27 Gate 引擎执法精度修复批：G30#3 概率读表列 / G59 候选∪级联 / G16 主体归因豁免（plan peaceful-tinkering-rabbit；688630 三轮迭代触发）

触发：芯碁微装 688630 全量分析三轮迭代暴露 5 类 gate 执法缺陷，专家评审定案 B/C/D′/F/E（A 撤回、G64-lookbehind 撤回、D/24字窗口否决改 D′）。目标=引擎语义对齐 m5/m6 模板已文档化的写作契约，消灭三类真阳性误伤。**准入门槛=全量本地语料回测 100%**（170 份唯一文本 / 140 份配真实快照，md5 去重，monkeypatch 旧新对照）；**终局复验=真补丁引擎 vs pre-fix worktree 分进程逐票对拍**。

- **`_g30_find_scenarios` 表优先（Fix B）**：情景矩阵表「概率」列 ≥3 行全可解析（新增 `_g30_prob_cell_to_float`，容忍裸数字/约/%/全角％）→ 直取表值；概率列缺失/部分不可解析 → 回退行首声明正则（旧报告兼容，含 688308「情景（概率）」合并列形态）。根治两类：①裸数字概率列 probs=[0,0,0]→#3 假 FAIL；②声明+表格行双吃重复计数（8/170 实锤返回 6 情景）。`capstone_panorama._top_scenario` 删孪生内联正则改**函数内 lazy import** 共享实现（模块级反向 import 会循环；其唯一消费方 panorama_advisory #7 软建议，gate verdict 零波及）。
- **`check_g59` 候选∪级联锚定（Fix C）**：`_G59_ANCHOR_PATTERNS` 三级（①编号+估值同标题→②估值结论/估值判定标题→③裸 5.3 兜底），复用 `_module_section` 层级感知切片，任一锚定切片含复合判定词即 PASS。根治 m4「### 5.3 机构动向」劫持与「#### 7.5.3」子节号误匹配。结构保证 new-FAIL ⊆ old-FAIL（old-PASS 的首个裸 5.3 切片必在候选集内）。**执行中修正**：①③ 的 `[^\d]*` 会跨行（`\n` 属非数字字符类）→「### 模块五
无 5.3 结论段」被 ③ 泄漏锚定，单测抓住后改 `[^\d\n]*`——语义更贴旧引擎，回归面更小。
- **`check_g16` 前方最近主体 token 归因（Fix D′）**：新增 `_G16_CL_TOKENS`/`_G16_OTHER_SUBJECT_TOKENS`/`_g16_nearest_subject`——行内数字归**前方最近**主体 token（中文财务行文主体在数字前），前方无主体才看后方；最近者属 CL 族或无主体→保守执法。数字端点必须 `m.start(1)~m.start(1)+len(m.group(1))`（纯数字组，勿用含「亿」的 m.end()——前向距离被人为缩短，分号句实测踩坑）。消灭 publish 稿剥 [src:] 后「在手订单 8 亿/净现金 35 亿/经营现金流 3.2 亿」与 CL 同行误判编造（6 份真实 publish 实锤）；编造照抓（CL 归因的 12 亿两代皆 FAIL）。
- **F+E 文案层（零行为变更）**：G30#2 reason 精确化（指明反方列加在情景表勿加 Layer1 矩阵）；GATE_HINTS G16 改写（防御性 [src:] 教条退役→归因豁免语义）/G30 补概率读表列/G59 级联语义/**新增 G64 key**（主力=特大单+大单口径纪律、「特大单」含触发词「大单」的子串陷阱、主力-guard 整行跳过宽松区）；m11-gates.md 两行镜像同步（quality 仓 4324178）。
- **测试资产**：test_g30_label_format.py +TestCase（裸数字/约全角容忍/合并列回退/部分解析回退+执法保持/_top_scenario 共享）15 测试全绿；test_m5_gates.py CheckG59 +6（劫持修复/7.5.3 不劫持/002025 形态/改号执法 FAIL/真缺失 FAIL/无锚豁免+正文 5.3 不泄漏）；test_g16_subject_attribution.py（新）8 判例（统一 grounding 行单变量隔离）；SECTION_PROBES +3（G59 劫持 True、G16 订单豁免 True、G16 编造 False，4→7 段）。

**终局对拍（真补丁 vs pre-fix worktree 分进程）**：170 份唯一文本逐票——**新 FAIL（回归）=0** ✅；误伤修复 7 处全部 old-FAIL→new-PASS（G16×5：沃尔核材002130/瑞华泰688323/蓝特688127/凯盛600552/芯碁微装688630 publish；G59×2：rp_7.md、answer.md 劫持草稿。长光华芯688048 publish 两代皆无 CL 快照配对→G16 均不评估，一致非回归）；probsΔ=8（炬光/太辰光/晶方 主稿+发布稿双吃 6→3 根治）。688630 归档 sidecar 前后仅 timestamp 差异（55 过/100 分不动，干净报告零波及）。全量回归 exit 0（61 门×3 票 + 7 段探针漏报=0）。

**known-limits**：① G64 主力-guard 整行跳过=已知宽松区（数值在但口径词缺失不执法）；② D′ 双族前方同现保守：「订单金额是合同负债两倍达 12 亿」12 归因 CL 仍 FAIL（宁紧勿松，判例⑦钉死）；③ G59 多 5.3 节取文档序、688059 无结论子节形态恒豁免、603019/000657 裸 5.3 走 ③ 级锚；④ G30#4 不查概率列（概率存在性已由 #3 求和执法，避免双重执法）；⑤ C 级联②级锚（估值结论/估值判定标题）对改号报告扩执法面——唯一收紧点，判例④钉死为预期行为。

## 2026-08-30 G28 杜邦 gate 重设计：闭合校验 → 纯快照完整性

- **为什么**：旧 G28 读 `dupont._closure_check`（残差<0.25pp + 金融豁免），而 Sina ROE 口径随报告期切换（Q1=自算平均自闭合；中报/年报=披露加权值），恒等反算在披露期不成立 → 7 票中报季系统性误 FAIL（锡业股份 000960 RCA 起点）。用户裁决：gate 只管「拉到+存对」（status ok + 核心四字段非 None），面板值为权威，不自算。金融股无需 gate 豁免（字段在场即 PASS；三因子 N/A 是模块层事，m2 读 `data._profile`）。
- **改动**：`check_g28` 重写（纯快照完整性）；GATE_DESCS/GATE_REGISTRY 述求同步（weight/owner/data_dim 不变）；data_contracts dupont 条目加双源 note + scene fallback 行；新增 `regression-tests/test_g28_dupont.py`（gate 两极/编排两极/reshape/max_retries=0 单次/runner 源码契约防漂移）挂载 run_regression.sh。
- **兼容证明**：67 份真实归档重放（25 配对+41 report-only+000960）G28 翻转恰 7 份全 FAIL→PASS（预期变更面）；parity 冻结票 000988/002008/300394 与 600183_modeB 金票 old=new（EXPECTED 零改）；旧快照 `_closure_check` 残留不读（加法式无害）。
