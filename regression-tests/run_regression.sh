#!/usr/bin/env bash
# run_regression.sh —— stock-analysis 改完代码的「一键回归」（单一入口）
#
# 跑两层、任一失败即非零退出：
#   ① 契约层（恒跑，自包含）：data_contracts ⇔ consumers 双向闭合
#        · verify_data_contracts.py  真实注册表 0 error（orphan/brokenConsumer=hard）
#        · test_data_contracts.py    CI 健全性 + 真实注册表零 error + 已知暴露面锁定
#   ② 运行时层（gate-audit 工作区存在时跑）：runner/futu_client/gate 的离线回归
#        · test_futu_call_api / test_futu_fetchers_regression / test_gate_throttled
#        · gate_fixture_test  28-gate 漏报=0 总闸
#
# ▶ 何时跑：改了 stock-analysis 任何 .py（runner/futu_client/gate_definitions/
#   data_contracts/verify_data_contracts/各 fetcher）之后。CLAUDE.md / AGENTS.md
#   已把此命令列为「改完代码必跑」。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$HERE/../scripts"
GATE_FIXTURES="/home/ubuntu/gate-audit-20260704/fixtures"

echo "==================== stock-analysis 回归 ===================="

echo "[① 契约层] verify_data_contracts.py"
python3 "$SCRIPTS/verify_data_contracts.py" --quiet
echo "[① 契约层] test_data_contracts.py"
python3 "$HERE/test_data_contracts.py" 2>&1 | tail -3
echo "[① 契约层] test_overseas_derivation.py"
python3 "$HERE/test_overseas_derivation.py" 2>&1 | tail -3

if [ -d "$GATE_FIXTURES" ]; then
  echo
  echo "[② 运行时层] gate-audit fixtures 在线，串跑："
  cd "$GATE_FIXTURES/.."
  echo "  · test_futu_call_api"
  python3 -m unittest fixtures.test_futu_call_api 2>&1 | tail -2
  echo "  · test_futu_fetchers_regression"
  python3 -m unittest fixtures.test_futu_fetchers_regression 2>&1 | tail -2
  echo "  · test_gate_throttled"
  python3 -m unittest fixtures.test_gate_throttled 2>&1 | tail -2
  echo "  · gate_fixture_test (28-gate 漏报=0)"
  python3 fixtures/gate_fixture_test.py 2>&1 | grep -E "漏报.*共" | tail -1
else
  echo
  echo "[② 运行时层] 跳过：$GATE_FIXTURES 不存在（仅跑契约层）"
fi

echo
echo "==================== ✅ 回归全绿 ===================="
