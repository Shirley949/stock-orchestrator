# 腾讯文档发布 SOP（卷2 · v4.1 自 ~/tdx-publish-v4/SOP.md 迁入，获 git 版本控制）

> **何时读**：**Phase 5 首步**——报告完稿 + verify_gates PASS 之后、执行本卷五步闸之前（CLAUDE.md 触发分册索引·卷2）。**禁在报告完稿前预读**（Phase 2-4 等待窗读了也会被 compact 挤出，发布时须重读=零收益）。规则真相源=`~/tdx-publish-v4/tdx_publish.py` rules 表 + `rules.md` 归位表；本卷只写流程入口。

> **何时读**：**Phase 5 首步**——报告完稿 + verify_gates PASS 之后、执行本卷五步闸之前（CLAUDE.md 触发分册索引·卷2）。**禁在报告完稿前预读**（Phase 2-4 等待窗读了也会被 compact 挤出，发布时须重读=零收益）。规则真相源=`tdx_publish.py` rules 表 + `rules.md` 归位表；本卷只写流程入口。

## 腾讯文档 Skill

| Skill | 路径 | 职责 |
|-------|------|------|
| **腾讯文档** | `~/.agents/skills/tencent-docs/SKILL.md` | 腾讯文档在线操作（创建/编辑/读取/搜索文档、智能表格、PPT、思维导图等） |

- 涉及"保存到腾讯文档"、"新建文档"、"云文档"等操作时加载
- 默认使用 smartcanvas（MDX 格式，排版美观）
- 通过 `mcporter call "tencent-docs" "<工具名>"` 调用
- Skill 文件通过 Read 工具按需读取，不复制

## 腾讯文档发布 SOP（规则已代码化，以 `tdx_publish.py v4.1.3` 为准——升级脚本必须同步改本行版本号并跑 `self-test`）

脚本：`python3 /home/ubuntu/tdx-publish-v4/tdx_publish.py`（`--version` 查版本；规则真相源=其 rules 表 + rules.md 归位表；本节只写流程）。
前置条件：gate 全过、verify_gates 已跑（指针行时序属发布前置，不归脚本）。

1. `tdx_publish.py prepare report.md -o out/` — 非零退出=禁止上传，先看 `out/prep-report.json`（FAIL 项带行号+修法，照抄修法改源报告；禁手工绕闸）。title ≤33 字符否则 L14 FAIL（服务端实测：33 字符过、37 字符炸；[彩排] 前缀计入长度=OQ5）。
2. `manage.search_file` 查重（写重试=重复档）→ `create_smartcanvas_by_mdx`，参数走 `~/.claude/scripts/mcporter_call.py --json-file` 唯一形态，**mdx 内容必须直接内嵌进 JSON 值**——`--json-file`/`--stdin` 分支不展开 `@path`（脚本源码 json.load 直透，传路径会得到空壳档）；仅 kv 形态展开 `@file`（此时文件必须无尾换行），但 kv 形态会吞整数参数。
3. `tdx_publish.py read-all <file_id> -o out/readback.json` — 全量翻页+token 回跳自动中止+读重试≤2。
4. `tdx_publish.py verify out/readback.json --source out/x.publish.mdx --prep out/prep-report.json` — 必须绿灯（needle 命中/泄漏计数等式/Unsupported==fence/无回跳/块数下限）。
5. 删除用 `manage.delete_file`（或 delete_space_node），验证看 `query_file_info.status=="trash"`（read 仍可读属设计；trash 档退出 search 索引）。

铁律：脚本零 MCP 写操作，create/update/delete 永不进脚本；源报告永不修改；gate/验证关键文本禁入 code fence（黑洞，verify 靠占位计数覆盖）；黄底 ≤5 处；find 有索引延迟只作辅助。
已知边界：服务端 mdx2record 报错与 MCP 行为漂移脚本消不掉——verify 兜底前者，每次发布会话先跑 smoke/彩排兜底后者（漂移会先在 verify 计数等式上炸成 FAIL）。
再审计触发条件（仅此二者开新一轮，否则不开）：**verify 连续 2 次 FAIL**，或出现**不认识的 mdx2record/MCP 报错签名**。vendor skill（tencent-docs）更新后：必跑 `tdx_publish.py self-test` + 一次彩排档全链，绿了才发正式档。
