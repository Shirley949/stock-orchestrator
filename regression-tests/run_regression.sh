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
#        · gate_fixture_test  29-gate 漏报=0 总闸
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
GATE_FIXTURES="/home/ubuntu/gate-audit-20260704/fixtures"

echo "==================== stock-analysis 回归 ===================="

echo "[① 契约层] verify_data_contracts.py"
python3 "$SCRIPTS/verify_data_contracts.py" --quiet
echo "[① 契约层] test_data_contracts.py"
python3 "$HERE/test_data_contracts.py" 2>&1 | tail -3
echo "[① 契约层] test_overseas_derivation.py"
python3 "$HERE/test_overseas_derivation.py" 2>&1 | tail -3
echo "[① 契约层] test_westock_integration.py（westock_client + fetcher reshape）"
python3 -m pytest "$ROUTING/test_westock_integration.py" -q 2>&1 | tail -2
echo "[① 契约层] test_lhb_northbound_processor.py（LHB/北向 processed 纯函数四情境）"
python3 "$HERE/test_lhb_northbound_processor.py" 2>&1 | tail -3

if [ -d "$GATE_FIXTURES" ]; then
  echo
  echo "[② 运行时层] gate-audit fixtures 在线，串跑："
  cd "$GATE_FIXTURES/.."
  echo "  · gate_fixture_test (29-gate 漏报=0)"
  python3 fixtures/gate_fixture_test.py 2>&1 | grep -E "漏报.*共" | tail -1
  echo "  · test_gate_throttled"
  python3 -m unittest fixtures.test_gate_throttled 2>&1 | tail -2
else
  echo
  echo "[② 运行时层] 跳过：$GATE_FIXTURES 不存在（仅跑契约层）"
fi

echo
echo "==================== ✅ 回归全绿 ===================="
