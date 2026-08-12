# REFACTOR_LOG — stock-orchestrator/scripts/lib 层改动动机

> 配套原则：skills 文档（schema/模块/scenario）只写「正确使用指南」，本文件集中记录 lib 层
> 改动的 **why**（动机 / 取舍 / 实测推翻）。runner/forecast 口径改动动机在
> `financial-data-routing/REFACTOR_LOG.md`。

---

## 2026-08-09 新鲜度阈值统一 180d（120 → 180）

### 动机
用户拍板「删掉所有的 120d，统一口径 180d」：事件层时间线（大事提醒）已定 180d 硬截断，而
staleness 告警（financial/季度不定期）与 G33 北向 freshness 仍用 120，两套口径并存易混淆。
且 120 本身就是已定位 bug（[[staleness-threshold-120-bug]]：Q1→中报间歇期约 150 天，120 阈值
系统性误报 10 条）。

### 变更
- `quality_checks.py:152,159`：financial + 季度/不定期 `return 120` → `180`（覆盖财报间歇期）
- `gate_definitions.py:1638`：G33 northbound freshness `>120d` → `>180d`（SOFT warning 上浮线）
- 文档同步：`m11-gates.md` G33 行；事件层 plan 内 P9 单期 fallback 120d → 180d
- REFACTOR_LOG 历史条目（lhb>90d/nb>120d）不改写——那是当时真实设计，新口径记录在本条

### 验证
回归 exit 0（改 `.py` 必跑）；grep 全仓 120d 天数残留 = 0（120 仅剩 EVENT_TYPE_CODE 码值，非天数）。

---

## 2026-07-21 Gate 数值新鲜度框架（plan Step 5：helper + G30#1 + G37/G38）

### 动机
户数 stale-value bug（snapshot 2026Q1=128685，报告却写旧值"10.12万"=101200）暴露：
C/D 类字段（户数/close/macro/dividend）要么无任何 gate（ppi/m2/dividend — C 类），
要么被 G30#1/G1 名义覆盖但只查"9 选 1 关键词"、不查**数值新鲜度**（D 类）。全库唯一的数值
对齐模板是 G16（合同负债），未泛化。`compute_staleness()` 已实现却从未接进任何 gate。

### 改动
- **共享 helper**（`gate_definitions.py`）：
  - `_extract_latest_value(data, envelope_path, value_key=None)`：从 latest_period 信封取标量 value；
    支持 dividend 兄弟键回退（`quote.dividend_latest_period`，因 dividend_history 保持 list 不破坏 m5 消费）；
    真空（latest_period None/缺失/非数值）→ None（gate 走豁免）。
  - `_check_value_freshness(report, snap_value, metric_kws, scales=(1,1e4,1e8), tol=0.15)`：
    复刻 G16 多精度范式 + 泛化任意字段。行带 `[src:]` → grounded（溯源豁免，精确值交 G21/G24）；
    多精度换算（"12.87万"→×1e4=128700 ≈ snap 128685）；多行任一对齐即 PASS；剥千分位逗号正则
    `\d[\d,]*\.?\d*`（修"128,685"被 `\d+\.?\d*` 误切为 128/685 的 bug）。
- **G30 #1 升级**（`_g30_run`）：从"9 选 1 关键词覆盖"升级为"数值对齐"。新增
  `_G30_VALUE_FIELDS` 注册表 + `_g30_value_freshness_findings(data, cov)`，仅"mentioned but stale"
  才 FAIL（precondition `any(kw in cov)` 排除"未提"，避免报告故意省略字段被误 FAIL）。
  首注册字段：股东户数（`s8_a_share.data.shareholder_count`，★ bug 原案）。
- **G37 宏观数据有效性**（NEW，SOFT weight 1）：PMI/PPI/M2 latest_period 覆盖率 ≥ 2/3。
- **G38 分红有效性**（NEW，SOFT weight 1）：每股股利数值对齐（scales 1.0=每股 / 0.1=每10股换算）
  OR [src:]；不分红公司真空豁免。
- 注册：G37/G38 → GATE_CHECKERS / GATE_WEIGHTS(=1) / ALL_GATES / SOFT_GATES / profile_full
  （**不进 profile_quick**——当日技术面模式不需要宏观/分红）。门数 29 → 34。
- 测试：`test_freshness_helper.py`（helper 18 case，含★ 户数 stale bug case）+
  `test_freshness_gate.py`（gate 级 19 case：G30#1 户数 stale + G37 presence + G38 数值 + 注册完整性）。

### 数据驱动的范围裁定（实测推翻 plan 原设）
plan §5.3 原设 G37/G38 做 pmi/ppi/m2/dividend **数值新鲜度**。实测（2026-07-21 akshare）推翻：
- **PPI/M2 数值校验必误判**：`当月`=104.1 / `M2-数量`=绝对量（亿元），但报告多引「同比%」
  派生指标（akshare 另列 `当月同比增长` / `-同比增长`，非 latest_period.value）。强数值校验
  会把"报告引同比%、snap 存指数"判 stale → 误 FAIL。→ 仅查 presence。
- **PMI 数值校验无效**：报告虽直引指数 50.x，但 PMI 窄带波动（49–52），stale vs fresh 值偏差
  常 <5%，落 tol=0.15 内被判"对齐"——靠数值根本判不了 stale（50.3 当月 vs 50.1 上月无法区分）。
  → G37 退为纯 presence（宏观是市场级数据、同日全量刷新，presence 即新鲜度；stale 靠报告引
  「月份/季度」标注，m35 已要求）。
- **dividend 数值校验有效**：每股股利 0.12 vs 旧值 0.05 偏差 58%，远超 tol，可判 stale。
  scales=(1.0, 0.1) 覆盖"每股 0.12 元"与"每10股派 1.2 元"两种主流口径；"股息率%"是派生 %
  指标（≠每股股利绝对值），用关键词排除（不含"股息"），避免误判。

**原则贯彻**（[[verify-before-claiming-only-source]]）：下否定结论 / 定 gate 范围前穷尽实测，
不靠臆测——PMI 窄带、PPI/M2 派生口径是实测发现，非假设。

### 验证
- 回归 exit 0（契约层 23 scenes 0 error + test_freshness_helper 18/18 + test_freshness_gate 19/19）。
- ★ bug 原案 gate 级复现：`_g30_run` 合成报告"股东户数 10.12万" + snap 128685 → #1 FAIL
  （`#1 数值新鲜度 FAIL — 股东户数 stale/未对齐(snapshot=128,685)`）；fresh 值 128,685 / 12.87万 PASS。
- G37 presence：< 2/3 FAIL（akshare 限流兜底）；G38 真空（不分红）PASS、stale 值 0.05 FAIL。

### 后续（plan Step 5 剩余，未做）
- G1 close 数值新鲜度维度（plan §5.2；**close 已在 G30#1 `_G30_VALUE_FIELDS` 覆盖**，G1 是否重复加待定）。
- ~~G16/G7/G27 双兜底 latent bug 修复（CLAUDE.md 硬规则，plan §5.4）~~ → **G7/G27 已修（见下）**，
  G16 早修（`_extract_contract_liab` data→data_full，memory [[gate-path-parity-and-asset-safety]]）。
- G32/G33 信号族 freshness 维度（lhb 2219d stale_signal，plan §5.5）→ **裁定归 Step 4 capstone 渲染层**
  （G34 stale_disclosure=PASS 先例：stale-but-valid 数据不过载 bool gate，新鲜度由 latest_period 信封
  sort_key + capstone `_render_signal_scene` 「⚠️历史数据·非近期」标记承载，m6/m7 不据此调仓位）。
- ~~G30#1 `_G30_VALUE_FIELDS` 扩 close（plan §5.2，PMI 已裁定不做见上）~~ → **已扩**（见下）。

---

## 2026-07-21 G7/G27 双兜底硬规则修复（plan Step 5.4）

### 动机
CLAUDE.md always-loaded 硬规则：读三表 / derived（financial_abstract / financial_indicators）须
`section.get("data", section.get("data_full", []))` 双兜底——THS/EM 主路径填 `.data`、Sina 填 `.data_full`，
**单读任一键 = 静默 never-match**（gate 不报错不崩溃，只是检查永不命中、退化纯文本，极难发现）。

### 改动
- **G7 `check_g7`**：原 `_snapshot_get(...financial_abstract.data_full)` 单键 → 改读 financial_abstract
  dict 后 `fa_section.get("data", fa_section.get("data_full", []))`。镜像 G8 `cf_section` 范式。
- **G27 `check_g27`**：原 `fi.get("data_full")` 单键 → `fi.get("data", fi.get("data_full"))`。
  （income_statement 读早是双兜底，仅 indicators 读违例。）改前 THS/EM 主路径 fi_rows=None →
  ROE 检查恒 false-fail。

### 验证
- smoke：G7/G27 在 `.data`(THS/EM) / `.data_full`(Sina) / 混路径（一表.data+另一表.data_full）三场景
  行为一致；G27 无 ROE 负向 FAIL。
- 回归 exit 0（双兜底改动加法式，不破坏既有 18+19 freshness 测试与 23 scene 契约）。

### 与 [[gate-path-parity-and-asset-safety]] 的关系
memory 记 2026-07-14 RCA 已修 G9（镜像 G6/G27）+ G16 + asset_safety 桥接。本次补上 G7/G27 两处
当时遗漏的单键读——硬规则第三次违例排查（G7 是新发现，G27 indicators 读是 G9 修复时的漏网）。

---

## 2026-07-21 G30#1 `_G30_VALUE_FIELDS` 扩 close（plan Step 5.2）

### 动机
close（daily_kline 收盘价）是报告引用最频繁的数字，stale 风险高（引旧收盘价做技术判断=误导）。
户数 stale-value 兜底已上线，同一 `_G30_VALUE_FIELDS` 注册表机制零成本扩 close。

### 改动
- `_G30_VALUE_FIELDS` 加 `("现价/收盘价", "s2_quote_kline.data.daily_kline", ["现价","收盘价","最新价"])`。
- finding 消息格式智能：`_fmt` 整数→`,.0f`（户数"128,685"）/ 小数→`,.2f`（close"54.07"），不丢精度。

### 验证
- smoke：close fresh(54.07) PASS / stale(40.00 偏差 35%) FAIL（消息含"54.07"）/ 不提 PASS / [src:] 豁免 /
  与户数 stale 共存（双字段独立判定，不互相干扰）。
- test_freshness_gate.py +4 case（TestG30CloseStaleValue），共 23 case；回归 exit 0。
- 边界：日内小波动（54.07 vs 55.0，1.7%）落 tol 0.15 内判对齐 ✓；目标价行（无"现价"词）不误触。

---

## 2026-07-21 data_contracts.py 注册 latest_period + snapshot_schema.md 两族范式章节（plan Step 6.1/6.2）

### 动机
Step 3（runner 各 scene 产出 latest_period）+ Step 5（gate 消费）落地后，契约注册表与 schema 文档
须反映终态——否则 data_contracts 与 snapshot_schema.md 两处真相源 drift（契约 S1 的立身之本是
「单一真相源绑死获取层与消费层」）。

### 改动
- **data_contracts.py**：8 scene 注册 latest_period produces + 字段级 consumer（标真实 gate）：
  - 字段级 consumer（gate 实读 latest_period.value）：s8 户数→G30、s2 close→G30、s6 pmi/ppi/m2→G37、
    valuation dividend→G38
  - 父路径覆盖（produce note 记 freshness 归属，不挂 phantom）：s1 三表（G6/G16/G27 待升级）、
    s5 news（m4 待升级）、lhb/northbound processed（freshness 归 capstone Step 4，G32/G33 只读 status）
  - **consensus defer**：顶层 `data.latest_period` + `data.annual_latest_period` + `data.company_guidance`
    无父覆盖、消费归 Step 4 capstone 未实现 → 暂不注册（避免 phantom consumer / orphan）
- **snapshot_schema.md**：新增「latest_period 信封（统一最新期范式，两族）」章节——
  - 信封 8 字段定义（raw_date/period_type/period_label/sort_key/as_of/data_class/value/summary）
  - 序列族路径表（10 条，data.<series>.latest_period，actual desc）
  - 信号族路径表（2 条，data.processed.latest_period，豁免 sort-normalize 不豁免 freshness）
  - 真空（None→gate PASS）vs stale-but-non-null（sort_key 过旧→capstone 标记）语义

### 契约机制利用（_path_matches 三关系）
子路径 latest_period（如 `daily_kline.latest_period`）自动被已注册父 produce 的 consumer 覆盖 →
零 orphan；兄弟键（s8 户数 vs `.processed`、dividend_latest_period vs `dividend_history`）需显式
consumer（G30/G38）。schema_coverage（注册表⇔schema.md 双向）由新增章节清零——warn 反降 46→43
（文档化顺带消解相邻 coverage warn）。

### 验证
- verify_data_contracts：23 scenes | **0 error** | 43 warn（改前 46；latest_period finding 清零）。
- test_data_contracts.py（真实注册表零报错 + 已知暴露面锁定）通过；全量回归 exit 0。

---

## 2026-07-21 capstone panorama freshness 渲染（plan Step 4：写作期见最新值）

### 动机
Gate 层（L6）是「被动兜底」（报告写完才查 stale），PRIMARY freshness 机制应是「写作期主动」——
LLM 写报告时 helper 草稿直接把最新值摆到眼前，根本不会引旧值。plan §4.1 改动 E/F + §2.4.3 F4。
户数 bug 原案的根因之一：panorama **完全不抽 s8 户数**，LLM 写作期看不到 128685，只能凭记忆/旧值
写「10.12万」。本次补上 freshness-critical 渲染（户数 + company_guidance + consensus annual + 信号族 stale 标记）。

### 改动（capstone_panorama.py）
- **`_stale_marker(lp, threshold)` helper**（新增）：latest_period 信封 days_old > threshold →
  「⚠️历史数据·非近期(距今N天)」。复用 latest_extract.days_old（叶工具，无循环依赖）。
- **panorama() 抽值**：新增 `values["shareholder_count"]`（s8 latest_period 信封，★ bug 原案）、
  `values["outlook"]`（company_guidance.latest_period + consensus annual[最近预测年]）；lhb/northbound
  values 各加 `latest_period` 字段。
- **`_render_shareholder_count`**（新增）：「股东户数（最新期 {period_label}）：{value:,} 户（环比{chg}%）。
  {summary}」——LLM 写作期直见 128,685 + 环比+27.1% + 散户 warning，不会引旧值。
- **`_render_outlook`**（新增）：业绩预告 summary + consensus annual[最近年] EPS/净利/同比；
  company_guidance stale（is_forward_looking=False）→ 标「⚠️覆盖期已实际化，无前瞻增量，参考实际财报」，
  防 LLM 把过期预告当 forward earnings 锚。
- **`_render_lhb`/`_render_northbound` 升级**：行首加 period_label（2026-07-08 / 2026Q2）+ 末尾 stale 标记
  （lhb>90d / nb>120d）。fresh 信号无标记，旧信号显眼降权。
- **THEME_RENDERERS 注册** +2（shareholder_count 插财务质量后、outlook 插估值后）。

### 数据驱动验证（fresh 603667 stdout，非 cache——见 [[verify-freshness-not-stale-cache]]）
- 户数：`股东户数（最新期 2026-03-31）：128,685 户（环比+27.1%）。⚠️散户涌入(warning)...` ✓
- 前瞻：`业绩预告（2023-01-31）：2022年报预增 33.59%~53.83% ⚠️覆盖期已实际化，无前瞻增量...；一致预期2026：EPS 0.37，净利 1.43亿(同比56.47%)` ✓（guidance stale 正确标记 + annual[2026] 最近预测年）
- lhb：`（2026-07-08）...（signal=hot_money_speculative...）` 无 stale（12d<90d）✓
- northbound：`（2026Q2）...外资持股0.83%...` 无 stale（20d<120d）✓
- present 维度 10/10 全覆盖，gap 空。

### 与 plan 的关系
完成 plan §4.1 改动 E（户数）+ F（lhb/nb stale）+ §2.4.3 F4（capstone 抽 consensus annual +
company_guidance.latest_period）。剩余 §4.1 改动 A（values 分区重组，结构 polish）/ B 补 segment/
peer/tech_capital 渲染器（反片面覆盖，非 freshness 核心）/ C-D（定性槽位+flags 前移，polish）/ G（ROE
dict-order——实测 fi 本就 newest_first，cols[0]=最新当前正确，无须改）。Freshness 核心闭环。

### 验证
- 回归 exit 0（capstone 改动加法式，不影响契约层 23 scene + freshness 18+23 测试）。
- panorama CLI 渲染实测（上）四类 freshness 行全正确。

---

## 2026-07-21 verify_gates 引擎上浮 gate reasons（freshness 反馈回路闭环）

### 动机
10 票实测 keystone（603667 户数 stale）阶段 4 暴露的可观测性断链：`_g30_run` 富返回
`{passed, failed, reasons}`——其中 reasons 含「#1 数值新鲜度 FAIL — 股东户数 stale/未对齐
(snapshot=128,685)」——但 `check_g30` wrapper `_g30_run(...)["passed"]` **显式丢弃 reasons 只返
bool**，verify_gates 引擎 line 127 `ok = checker(...)` 也只取 bool。结果：freshness gate 正确判
FAIL，但报告作者从 sidecar/action_required 只看到泛化「G30: 综合研判完整性」，**不知是哪个值
stale**——反馈回路断裂，作者可能重建整个 capstone 却漏掉那个 stale 数字。

实测确认 `_g30_run` reasons 全库**无生产消费者**（仅 check_g30 丢弃 + 单测），是死计算。
freshness 框架若 gate 抓到 stale 却不告知作者哪个字段，等于「检测但不通报」的安全网，价值折半。

### 改动（精准 4 处，向后兼容）
- **`gate_definitions.check_g30`**：`return _g30_run(...)["passed"]`（bool）→ `return _g30_run(...)`
  （富 dict）。GATE_CHECKERS 唯一消费者是 verify_gates:114，无其他调用点，改返回类型安全。
- **`verify_gates.py` 引擎执行块**：`ok = checker(...)` → 兼容 bool 与 dict 返回——dict 取
  `passed`(bool) + `reasons`(list) 上浮到 detail item（`if gate_reasons: detail["reasons"]=...`）。
  bool gate 零影响（gate_reasons=[] 不写 key）。
- **`_build_action_required` helper**（新增）：失败 gate 的 action_required 从「desc 单行」升级为
  「desc → 逐条 reason」（`G30: ... → #1 数值新鲜度 FAIL — 股东户数 stale`），作者一眼定位。
- **`print_report`**：失败 gate 行下缩进打印 `↳ {reason}`，stdout 同样可见。

### 通用性
引擎层改动，**所有未来返 dict 的 gate 都自动获益**（G16/G17 等可后续升级返 reasons）。
非 freshness 专属——是 gate 可观测性的基础设施补全。

### 验证
- keystone 复跑：stale 报告（户数 10.12万）+ fresh snap（128685）→ action_required 现含
  `G30 → #1 数值新鲜度 FAIL — 股东户数 stale/未对齐(snapshot=128,685)`（改前只有泛化 desc）。
- PASS gate（无 stale）detail 不含 reasons key（`if gate_reasons:` 守卫 + _g30_run passed 时
  reasons=[]），sidecar 结构对 PASS 报告不变。
- 回归 exit 0（23 scene 0 error + freshness 18+23 测试 + 全契约层绿）；改返回类型未破坏
  test_g30_label_format（其调 `_g30_run` 非 check_g30）/ test_freshness_gate（同）。

### 与 plan 的关系
plan 未显式列此项（验证期发现的可观测性缺陷）。属 freshness 框架「检测→通报」闭环的必要补全，
否则 Step 5 gate 层价值打折。记录于此备查，非 plan 新增 Step。




## 2026-07-21 财务质量三源 + s11_peer 加 latest_period 信封（plan Step 3/4 财务质量维度补全）

### 动机
用户三次提醒：杜邦/ROE/财务质量是时序敏感数据（季末 0331/0630/0930），s11_peer 也按时间拉取。
审计发现财务质量三源（financial_indicators / financial_abstract / dupont）**均无 latest_period 信封**——
ROE/净利率无 freshness 追踪，报告可引旧季度 ROE 而无人抓（同户数 bug 类）。income_statement 已有信封，
但 ROE 主源（indicators/abstract）+ 杜邦三因子（dupont）是缺口。s11_peer 同样缺报告期捕获。

### 改动
**生产层（runner.py）：**
- 新增 `_wide_format_latest_envelope(periods, data_full, metric_keys)`：wide 格式（指标为行·期为列）
  财务 section 的信封构造器。periods 须已 desc（abstract `sorted(reverse=True)`/indicators
  `sorted(key=_period_key, reverse=True)`——排序本就正确，只是缺信封）。
- financial_abstract：latest_period = {ROE/净利率/毛利率/扣非} @ periods[0]
- financial_indicators：latest_period = {加权ROE/摊薄ROE/周转} @ periods[0]
- dupont：latest_period = {ROE/净利率/周转/权益乘数} @ data.period（单期 dict，period_type=day 对齐三表）
- s11_peer：`_core_metrics_from_detail` 加 report_period（jiankuang date '2026一季报'）；
  新增 `_jk_report_date` 中文报告期→季末 YYYYMMDD 映射；fetch_peer_comparison 加 scene 级
  latest_period（target 报告期驱动，value=target 核心5）+ target_report_period 字段。
  横截面非序列——不排序，但捕获报告期 + 标新鲜（target/peer 期次不一致渲染层可见）。

**消费层（capstone_panorama.py）：**
- 新增 `_render_quality`：财务质量三源（indicators 加权ROE+周转 / dupont 三因子分解 /
  abstract 毛利率+净利率），Q1/中报/三季标「单季·未年化」（`_q_caveat` helper，防 LLM 把单季
  ROE 当全年盈利能力）。升级旧 fi 抽取（cols[0] dict-order → latest_period 信封）。
- 新增 `_render_peer`：同业对比 target + peers 核心6 + 报告期；status=missing→提示先跑 peer 模式
  （防 G30#1 反片面遗漏）。
- `_render_income` 删 ROE 残留（现归 _render_quality，避免重复 + None%）。
- THEME_RENDERERS 注册 quality + peer（QUANT_THEMES 10 主题现全覆盖）。

### 验证（fresh stdout，非离线注入）
- live `runner.py A 603667`：三源信封全 ✅ @ 2026-03-31（indicators ROE 1.03% / abstract
  ROE+净利率4.38%+毛利率19.76% / dupont ROE 1.03%=净利率×周转×权益乘数；三源 ROE 跨源一致 1.03%）。
- capstone fresh 渲染：成长性 / 财务质量（单季·未年化）/ 杜邦分解 / 盈利能力 / 同业对比 全带期次。
- 回归 exit 0（freshness 18+23 + segment 46 + 全契约层绿）。
- s11_peer OK/degraded/missing 三分支格式离线验证（目标6字段全显，竞品按有值显）。

### 设计决策
- **period_type=day**（财务三源）对齐 income_statement + plan 2.2 表；s11_peer 用 quarter（label
  '2026一季报' 更直观）。sort_key quarter 用 day28（to_sort_key 设计，跨形态可比，3天偏移无碍）。
- **单季·未年化 caveat**：用户核心关切。ROE 1.03%@Q1 是单季值，renderer + interpretation_flags
  双重提示，防误读为全年盈利能力低。
- **加法式**：不改原 data_full/periods/排序，只加 latest_period 字段 + s11_peer report_period。
  消费者（m2/G6/G27）旧路径不断。
