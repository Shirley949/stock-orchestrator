# retired/ — 已退役脚本归档（retain deprecated）

2026-09-03 退役（v4 收口轮，任务书 v4.1 铁律 3）：发布链转换/剥离逻辑并入
`/home/ubuntu/tdx-publish-v4/tdx_publish.py`（fence 状态机 + ADR-A~F），规则真相源见其
`rules.md` 归位表。本目录脚本**仅存不跑**（实战发布通过后另行清理）；依赖它们的历史
契约测试已同步改指向（`regression-tests/test_src_hidden_style.py` strip 节移交
tdx_publish self-test `n11_strip_adrb`，行数不变断言由 ADR-B 内容断言取代）。
