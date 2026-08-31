#!/usr/bin/env bash
# run_regression.sh —— stock-analysis 改完代码的「一键回归」（单一入口）
#
# 跑两层、任一失败即非零退出：
#   ① 契约层（恒跑，自包含）：data_contracts ⇔ consumers 双向闭合
#        · verify_data_contracts.py  真实注册表 0 error（orphan/brokenConsumer=hard）
#        · test_data_contracts.py    CI 健全性 + 真实注册表零 error + 已知暴露面锁定
#        · test_overseas_derivation.py
#        · test_lhb_northbound_processor.py  LHB/北向 processed 纯函数四情境（never_listed/event_only/fetch_failed/正常）
#   ② 运行时层（gate-audit 工作区存在时跑）：runner/westock_client/gate 的离线回归
#        · test_westock_integration（westock_client 解析 + 三 fetcher reshape 形状）
#        · gate_fixture_test  全 Gate 漏报=0 总闸（gate 集 = gate_definitions.py 的 check_g*）
#
# ▶ 何时跑：改了 stock-analysis 任何 .py（runner/westock_client/gate_definitions/
#   data_contracts/verify_data_contracts/各 fetcher）之后。CLAUDE.md / AGENTS.md
#   已把此命令列为「改完代码必跑」。
#
# 注：估值/预测/资金流由 westock 腾讯源 + akshare baidu 提供。gate-audit fixtures
#   在线时，其 fetcher 测试需用 westock reshape 形状（test_westock_integration 已覆盖）。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$HERE/../scripts"
ROUTING="$HERE/../../financial-data-routing"
GATE_FIXTURES="$HERE/fixtures"

echo "==================== stock-analysis 回归 ===================="

echo "[① 契约层] verify_data_contracts.py"
python3 "$SCRIPTS/verify_data_contracts.py" --quiet
echo "[① 契约层] test_data_contracts.py"
python3 "$HERE/test_data_contracts.py" 2>&1 | tail -3
echo "[① 契约层] test_overseas_derivation.py"
python3 "$HERE/test_overseas_derivation.py" 2>&1 | tail -3
echo "[① 契约层] test_segment_dimensions.py（三维主营构成 + 海外五态 + 跨维信号 + G34/35/36/G17/G22）"
python3 "$HERE/test_segment_dimensions.py" 2>&1 | tail -3
echo "[① 契约层] test_westock_integration.py（westock_client + fetcher reshape）"
python3 -m pytest "$ROUTING/test_westock_integration.py" -q 2>&1 | tail -2
echo "[① 契约层] test_dongcai_client.py（东财 client 三态+缓存命中/中毒双判+重试+URL 拼接）"
python3 "$ROUTING/test_dongcai_client.py" 2>&1 | tail -3
echo "[① 契约层] test_sina_client.py（S8 sina_client：行情 GBK 快照解析+杜邦 SSR HTML 切期/_profile/_dupont_is_empty 冻结响应 golden）"
python3 "$ROUTING/test_sina_client.py" 2>&1 | tail -1
echo "[① 契约层] test_g28_dupont.py（G28 纯快照完整性两极+东财 fallback 编排/reshape/max_retries=0 单次+runner 源码契约）"
python3 "$HERE/test_g28_dupont.py" 2>&1 | tail -3
echo "[① 契约层] test_report_views_kline.py（kline 视图内存态类型回归+except 加法式保 raw）"
python3 "$ROUTING/test_report_views_kline.py" 2>&1 | tail -3
echo "[① 契约层] test_lixinger_client.py（S8 lixinger_client：EV/EBITDA 快照+分位箱 gzip 路径+三态短路 冻结响应 golden）"
python3 "$ROUTING/test_lixinger_client.py" 2>&1 | tail -1
echo "[① 契约层] test_lhb_northbound_processor.py（LHB/北向 processed 纯函数四情境）"
python3 "$HERE/test_lhb_northbound_processor.py" 2>&1 | tail -3
echo "[① 契约层] test_g1_g14_dual_segment.py（G1/G14 四段 Gate：技术面完整性+TD 数据驱动+三态+禁编造）"
python3 "$HERE/test_g1_g14_dual_segment.py" 2>&1 | tail -3
echo "[① 契约层] test_g30_label_format.py（G30 表格 label 加粗口径对齐+#2/#3/#6 拦截）"
python3 "$HERE/test_g30_label_format.py" 2>&1 | tail -3
echo "[① 契约层] test_b_head_g71.py（b_head 头块视图：18 票语料回放+分支/幂等 + G71 两极四项）"
python3 "$HERE/test_b_head_g71.py" 2>&1 | tail -3
echo "[① 契约层] test_section_locator.py（章节定位器：候选迭代+切片验签 劫持免疫+零回归边界）"
python3 "$HERE/test_section_locator.py" 2>&1 | tail -3
echo "[① 契约层] test_freshness_helper.py（latest_period 数值对齐公共地基+户数 stale bug case）"
python3 "$HERE/test_freshness_helper.py" 2>&1 | tail -3
echo "[① 契约层] test_freshness_gate.py（G30#1 户数 stale + G37 宏观 presence + G38 分红有效性）"
python3 "$HERE/test_freshness_gate.py" 2>&1 | tail -3
echo "[① 契约层] test_checklist_consistency.py（checklist 分母一致：generate N == c-tag 数；100% 可达；mapping c_map_N 可打勾）"
python3 "$HERE/test_checklist_consistency.py" 2>&1 | grep -E '^(OK|FAILED|Ran|AssertionError|ERROR)' | tail -3
echo "[① 契约层] test_token_audit.py（表计 v2 语义自检：去重/result-only/挂载前缀分层/写回目标同一/排除正交）"
python3 "$HERE/test_token_audit.py" 2>&1 | tail -3
echo "[① 契约层] test_snapshot_view_field.py（--field 外科投影六语义+footer/截断指针+炸弹双帽）"
python3 "$HERE/test_snapshot_view_field.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_peer_pipeline.py（peer handoff：G15 weight3+never-run FAIL+fallback emit 四态+capstone 富字段+m6/m1 锚点）"
python3 "$HERE/test_peer_pipeline.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_g16_subject_attribution.py（G16 行内数字前方最近主体归因豁免 两极）"
python3 "$HERE/test_g16_subject_attribution.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_latest_extract.py（latest_period 信封/双键兜底/days_old 新鲜度 helper 族）"
python3 "$HERE/test_latest_extract.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_g48_shareholder_programs.py（G48 待执行-FIRST 增减持计划 SOFT gate 三态+反编造）"
python3 "$HERE/test_g48_shareholder_programs.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_m5_gates.py（m5 G58分位必写/G59结论verdict/G45目标价src/G21 m5计数 四 gate 三态+反编造）"
python3 "$HERE/test_m5_gates.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_m6_gates.py（m6 G60 定性三行结构化锚点+反捏造 三态+限证据全景子节防误伤）"
python3 "$HERE/test_m6_gates.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_f2f3_collection.py（第3批 F2/F3 族清扫 11 门收集化+G63 阻力词表 两极直调）"
python3 "$HERE/test_f2f3_collection.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_doc_src_paths.py（第4批 R10 verify_doc_src_paths：dot-split 镜像 G21 语义+两极扫描+CLI exit）"
python3 "$HERE/test_doc_src_paths.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_r8_mechanism.py（第4批 R8 机制档：precheck exit3/verify_gates 快照硬闸/update_checklist 未知 cid 两极）"
python3 "$HERE/test_r8_mechanism.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_src_hidden_style.py（src 写法契约：gate 对注释包裹等价+G62 tally 禁区+strip_for_publish 发布剥离）"
python3 "$HERE/test_src_hidden_style.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_event_fetch.py（事件层 timeline：dedup 三元组保真+KEEP 截断+by_code 投影闭合+三态 离线纯函数）"
python3 "$HERE/test_event_fetch.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_full_archive.py（模式B full/ 存档：全量性+同日复用+A∪B合并+cleanup白名单+90天旧档识别）"
python3 "$HERE/test_full_archive.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_s10_checklist_cached.py（收单三态语义两极：ok/cached→True，failed/缺失→False）"
python3 "$HERE/test_s10_checklist_cached.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] test_market_context_order.py（market_context 排序契约两极：desc存储→最新消费+board键必挂载+统一信封）"
python3 "$HERE/test_market_context_order.py" 2>&1 | grep -E '^(OK|FAILED|Ran)' | tail -3
echo "[① 契约层] parity/test_parity_gate.py（P5 纯处理段：3票 frozen 回放 确定性+==golden byte-parity+封socket纯度证明）"
python3 "$HERE/parity/test_parity_gate.py" 2>&1 | grep -E '^(\[parity\]|OK|FAILED|Ran|ERROR)' | tail -5

if [ -d "$GATE_FIXTURES" ]; then
  echo
  echo "[② 运行时层] D3 surfacing fixtures 在线，串跑："
  echo "  · gate_fixture_test (P6-D3 全 Gate 漏报=0 总闸；冻结池=parity/corpus scene 键输出)"
  python3 "$GATE_FIXTURES/gate_fixture_test.py" 2>&1 | grep -E "漏报.*共" | tail -1
  if [ -f "$GATE_FIXTURES/test_gate_throttled.py" ]; then
    echo "  · test_gate_throttled"
    (cd "$GATE_FIXTURES/.." && python3 -m unittest fixtures.test_gate_throttled 2>&1 | tail -2)
  fi
else
  echo
  echo "[② 运行时层] 跳过：$GATE_FIXTURES 不存在（仅跑契约层）"
fi

echo
echo "==================== ✅ 回归全绿 ===================="
