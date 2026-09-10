# 工程范式分册（时序新鲜度黄金范式 + 信号信封 + 读三表双兜底 + 事件原则 + 断言纪律）

> **何时读**：改 pipeline、新增/修改 scene·gate·信封·时序信号处理、读三表/derived 数据之前（CLAUDE.md 触发分册索引·卷1）。`_research/` 前缀=不自动加载，经索引按需 Read。

## Gate/Helper 读三表范式（硬规则）

> 读 income/balance/cash 三表（及任何**因数据源不同而 `.data` / `.data_full` 键不同**的 scene）时，**必须**双兜底，二选一写法：
>
> - gate/helper 内：`section.get("data", section.get("data_full", []))`
> - 跨路径点分：`_snapshot_get(data, "...data") or _snapshot_get(data, "...data_full")`
>
> **为什么是硬规则：** 三表写入键名因源不同——THS/EM 主路径只填 `.data`，Sina 路径只填 `.data_full`。**单读任一键 = 隐蔽 never-match bug**：gate 不报错、不崩溃，只是快照检查永不命中、静默退化成纯文本匹配，极难发现。
>
> 新增任何读三表/derived 的 gate/helper，**第一步就双兜底**。参考实现：`check_g6`（`gate_definitions.py`）、`_compute_asset_safety`（`runner.py`）。

## 时间序列新鲜度黄金范式（硬规则）

> 任何**带时间维度**的数据（财报/资金流/K线/榜单/快照）写入 snapshot 时，**必须**套这套范式。核心：消费方读到的 `rows[0]` 永远是最新期；**真·空(`never_*`)与拉取失败(`failed`)必须可区分**；gate 只读 `status` 即判三态，不查非零。

### 5 条硬约定
1. **desc 排序**：除 `daily_kline` 历史(asc)外，所有时序 `rows[0]=最新`；用 `ensure_newest_first(df, date_col)`（`quality_checks.py:113`）兜底，**别信源端顺序**。
2. **latest_period 信封**：时序套 `_attach_series_latest_period`（序列族 `runner.py:478`）/ `make_latest_envelope`（信号族 processed 层 `latest_extract.py:114`）；真空(`never_*`)→`latest_period=None`→gate 自动 PASS。
3. **三态语义**：`never_*`/`event_only`/降级→`status="ok"`；`fetch_failed`→`status="failed"`；空 DataFrame 用 `fetch_with_fallback(..., empty_is_ok=True)`（`scripts/lib/data_snapshot.py:420`）与 failed 区分。**gate 只看 status，不查非零**。
4. **加法式**：不动原 `periods`/`data_full`，只**加** `processed` + `latest_period`（向后兼容）。
5. **双键兜底**：读时序用 `latest_value_from_section(section, field)`（`data`→`data_full`，`latest_extract.py:159`），禁单读一键（见上「读三表范式」）。

### 黄金模板（按数据形态选）

| 形态 | 模板（file:line） | 套用例 |
|------|-------------------|--------|
| **序列族**（逐日/逐期行） | 源端 desc + `_attach_series_latest_period(env,"日期",[字段],period_type="day")`（`runner.py:478`）+ 真空→None | s1 三表、margin |
| **wide 族**（指标×期矩阵） | `_wide_format_latest_envelope`（`runner.py:162`），`period_type=year/month` | financial_indicators、esg |
| **事件/榜单族** | `detail_dates sorted(reverse=True)` + 90天窗 + `make_latest_envelope(period_type="event")` + 三态 | lhb、disclosure、company_guidance |
| **单日快照族** | `make_latest_envelope(date,"day","actual",value)` + `days_old` 新鲜度 | valuation、chip |

### Staleness gate（`quality_checks.py`）
- `get_staleness_threshold`(:138)：KLINE=5 / financial=180（统一 180d 口径）/ macro=60 / 默认=7；**历史事件型 API（龙虎榜榜单、披露日历）=10000（恒不拒）**——"旧=不活跃/无事件的有效结论，非脏缓存"。
- `should_reject_cache`(:165)：KLINE>30 拒 / financial<4行 拒 / 其它>365 拒；历史事件型恒不拒。
- **新增历史事件型 API 必须同时加入 `get_staleness_threshold` + `should_reject_cache` 的豁免**，否则 `fetch_with_fallback` 误判 stale→`all_failed`，把「真·无数据」误标成拉取失败。

### 关键 helper 索引
- `latest_extract.py`：`make_latest_envelope`(:114) / `latest_value_from_section`(:159 双键) / `days_old`(:185) / `to_sort_key`(:41) / `compute_as_of`(:36)
- `quality_checks.py`：`ensure_newest_first`(:113) / `compute_staleness`(:125) / `get_staleness_threshold`(:138) / `should_reject_cache`(:165)
- `scripts/lib/data_snapshot.py`：`fetch_with_fallback(empty_is_ok=)`(:420) / `_is_data_stale`(:296) / `_check_staleness`(:956)

> **新增带时间维度的 scene/数据**：第一步选形态→套上表模板→加 latest_period 信封→gate 用三态 status。参考实现：s1 三表（序列族冠军）、lhb（事件族 + Historical 豁免）。

## 信号信封范式（硬规则）

> 稀疏·编码·事件型数据（**非纯时序**：龙虎榜席位/北向持仓/股东户数信号/大事提醒 timeline 码）写入 snapshot 时，**必须**套这套范式。与「黄金范式」正交——黄金管**时序新鲜度**，本范式管**编码信号 + 分桶**；两者叠加（信封内复用黄金的 `latest_period` + 三态 `status`）。

### 硬约定
1. **加法式 `processed` 层**：不动 raw（原始 dict/`data_full`/`notice_types` 原样保留），只**加** `processed` + `latest_period`（向后兼容，零破坏现有消费者）。
2. **三态 `status`**：语义同黄金范式第 3 条（`ok` 含真空/降级、`failed`=拉取失败，gate 只读 `status`）。
3. **`signals[]{code,name,severity,evidence,action}`**（severity∈critical/warning/info）+ **`signal_type` 标量**（向后兼容）。
4. **分桶（按需）**：双向事件分 `risk` + `catalyst` 桶（事件层 timeline.risk / timeline.catalyst）；单向用 `signals[]`（= 全部信号，始终保留向后兼容）。
5. **`summary` 一等公民**：人类可读结论（「⚠️股东减持12条·高危」「游资活跃」「外资重仓」），gate/报告直读，非衍生。
6. **`latest_period`**：同黄金范式第 2 条信封规则，复用 `make_latest_envelope`。

### 防御纵深（raw∩processed 交叉校验）
> gate 除校验「报告是否 surface」外，还做 **raw∩processed 交叉校验**：raw 有事件 X（大事提醒含减持行）但 `processed.timeline` 无对应事件 → 报「引擎 bug / 管道断裂」。独立于管道自觉，抓引擎漏算。

**参考实现：** lhb/北向（`signals[]`+aggregates）/ s8 股东户数（signals+trend+inflection）/ 重大事件（`processed.timeline` 单一交接：events/future/historical + fatal_events + risk/catalyst 分桶，`runner._process_material_signals`）。

## 信号/事件体系设计原则（硬规则）

> **① 门禁分级：** gate 强制 surface 时，**只强制致命/漏报致命信号**（事件层 fatal 码：330 非标审计/360 立案调查/430 破产清算/230·240 退市·ST/270 重大违法；关税 fatal）；参考/info/利好只 surface **不门禁强制**（漏报利好不致命）。防过度门禁误伤干净票/真空票。
>
> **② 官方结构化分类器优先于 regex/关键词：** 有官方结构化分类器（东财大事提醒 `EVENT_TYPE_CODE` 45 类 / company_guidance `predict_type` / 交易所行业分类）时，作 **PRIMARY** 事件/类别检测源；regex / 关键词 / news 扫描**仅作上下文辅证，不作检测源**。**为什么硬规则：** regex 误匹配会**造假事件**——实测 `share_change` 误中「机构资金抢筹」、`financing` 误中「融资余额十连降」。官方源零失真、对称、可枚举；有官方源时 regex 必让位。
>
> **③ 对称一等公民：** 建「风险/负面」检测体系时，考虑对称「利好/正面」是否也该一等公民（独立桶/register/打分），即使门禁强制力度不同（见 ①）。

## 断言必验 + 全链路自测（硬规则）

> **断空必验 schema**：任何「某字段/scene/数据 空、缺失、未实现、无覆盖」的结论，**落码或写入结论前必须附真实结构 dump**，不能靠记忆/臆测的 key 读：
> ```bash
> python3 -c "import json;d=json.load(open('<snapshot>'));print(list(d['<scene>']['data'].keys()))"
> ```
> **为什么是硬规则**：按臆测 key 读结构 → 静默 never-match → 假阳性结论。读错 key 的典型形态：`balance_statement`≠`balance_sheet`、`items[].revenue`≠`items[].metrics.rev`、adapter 实存却判「未实现」。`data_contracts.py`（CONFIRMED 标注）是 schema 单一真相源——断空前先查。**适用全局**：不止股票，任何「我以为某字段不存在/为空」的断言，先 dump 真实结构再下结论。

> **改 pipeline 代码先全链路自测（fetch→store→read→consume）**：改数据拉取/加工/gate/报告消费代码后，**回归前**对每条改动跑完整四段链——
> **fetch（真实拉取，非构造 mock）→ store（写入 snapshot）→ read（消费方按真实路径读出）→ consume（gate/报告关键词真正命中）**。
> **为什么**：单测只覆盖单一调用形态，漏掉「只在特定调用路径才崩」的脆弱点。典型脆点：① 覆盖判定用 `len(list)>0`，但 list 对每期都产一条（值全 None 也在）→「期存在但无值」误判 ok；② 分支内局部变量遮蔽 → except 吞错、静默丢字段。

> **计数勿硬编码（文档原则）**：CLAUDE/AGENTS/回归描述里**不要**硬编码会变的计数（scene 数、gate 数、API 数、模块数）。用**计数无关**措辞或指向单一真相源：scene 数 = `len(SCENES)`（`data_contracts.py`）、gate 集 = `gate_definitions.py` 的 `check_g*`。硬编码计数 = 定时炸弹。

> **websearch = 发现非验证（设计原则）**：混用 API 数据与 websearch 时——**抓取的 API 数据是权威上游**；websearch 是**发现**工具（找出 code/存在性），不是**验证**工具（确认对应关系/数值正确）。websearch 归属 LLM 编排循环（非确定性/慢/限流），**不进确定性代码守卫**；数据取空时→写显式告警交还 LLM 决策，而非代码自动 websearch。
