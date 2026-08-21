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
