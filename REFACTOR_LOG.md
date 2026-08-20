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
