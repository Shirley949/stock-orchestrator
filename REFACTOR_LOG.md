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
