# 件⑦ 修复工单（验收官产出，禁顺手修——全部待派单）

分级：P1=机制/引擎（下批候选）；P2=判据文字与审计固化；P3=留观。

## P1 机制面

**T1 · C2 双账并存的措辞防误读**（低成本高价值）
- 现象：`c2_compact_inject.py` 进度行「已写 6/16」=勾选账，三态行 `present`=磁盘账，两账并存。执行者与验收初读均曾误读为「待写却补跑」的自相矛盾（m25 案分支 ii 的诱因）。
- 工单：进度行标签改「已勾 6/16（勾选账，磁盘为准）」或三态行并列显示磁盘章名。
- 验收：改后 test_c2_inject.py 全绿 + 真实 compact 注入目检两账并读不歧义。

**T2 · 模型跳 mandated ④ 的机械阻抗**
- 现象：4b 两处实证（§四 append 后全报 gate 68/100 ✅ 即视④为已覆行；L407 `--check c62` 未跑 `--section` 直接勾）。两处均非 compact 恢复期，纯模型跟锚强度。
- 工单：checklist 步④模板输出尾注「本步 --section 未跑则⑤禁勾」（或 verify_gates --section 侧在 checklist 勾选缺失时输出警示行）；不做模型侧依赖修复。
- 验收：4a 同型诱导复跑，L407 型跳步在④未跑时被⑤拒绝（反例先炸）。

**T3 · 恢复步数判据「≤3」口径定义**
- 现象：4a 三例字面 11/13(中断)/4 步——含 `--list` 仪式与 gate 驱动外科补跑；预注册未定义计数口径，字面/操作读法分裂。
- 工单：判据 v3 增补定义（建议：恢复步数 = 恢复窗内**净新数据取数**调用数，`--list`/存在性仪式与 ④ 补跑不计，线 ≤3）；随 v3-r1 同批预注册。
- 验收：定义落字后以 4a 三例回放，口径唯一可计算。

## P2 判据/审计固化

**T4 · 判据 v3-r1 落地 + token_audit baked 符合性三列**（=件⑥第三节，待终裁后派单）

**T5 · 长度带二票定标**（=件⑥第四节 v3-r2，蓝晓票后执行，禁止提前）

**T6 · PreCompact 探针核验程序落点**
- 现象：探针日志焚前 ts 仅存于会话显示（秒级对拍 /compact 提交时刻成立），日志本体已焚=证据灭失；「读后焚」使核验链不可复现。
- 工单：preflight_precompact_logger 用毕流程改「核验行抄录 REFACTOR_LOG 后焚」；写入其 `--uninstall` 提示文案。

**T7 · token_audit websearch 桶更名**
- 现象：4b 写作会话零搜索工具调用（工具穷举 Skill1/Read21/Bash169/TaskCreate6/TaskUpdate9/Edit5），930c「websearch」实为快照预载 `web_research_findings`（9 items 全部 via Exa，runner P2 期行使）经视图消费的驻留量。命名误导归因。
- 工单：v5 构成行「websearch」→「websearch(预载)」或拆「runner期/会话内」两列；exa 分支记账口径注明在 runner 侧。

## P3 留观（不开工单，登记)

- T8 · capstone `src` 语义归属错位：+63.78 行 src 标 `consensus_forecast.data.annual`（合法路径 G21 过）语义应属 `s1_financial.mainfinadata`——gate 视野外，执行者已留观，转正式观察项。
- T9 · 3b(i) 分章相位相关检验对单体 Write 基线先天失效（n=1 写点）——蓝晓票按 v3-r2 附带判读处置一次后归档，不再重试。
