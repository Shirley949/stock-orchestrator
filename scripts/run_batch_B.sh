#!/bin/bash
# run_batch_B.sh — 模式B 多票批跑固化（2026-10-09 Phase 6 批；原型 /tmp/batch_runner_B.sh 实战两轮全绿）
# 用法：run_batch_B.sh --label morning [--codes 603993,601138] [--dry-run] [--stop-on-fail]
# 退出码：0=全成功 1=参数/预检失败 2=部分失败 3=全失败
# 约束：/tmp 产物命名 run_batch_B_* / runner_snapshot_{code}_modeB.json（c2_compact_inject
#       消费面，禁改名）；合集目录名由 b_portfolio_sheet.py 生成（8 位日期尾，glob 消费方安全）。
set -uo pipefail

SKILL_ROOT="$HOME/.hermes/skills/stock-analysis/financial-data-routing"
RUNNER="$SKILL_ROOT/runner.py"
TODAY="$(date +%Y%m%d)"

declare -A POS=(
  [603993]="shares=2500,cost=17.32"
  [601138]="shares=700,cost=52.85"
  [603663]="shares=200,cost=29.63"
  [605376]="shares=300,cost=130.42"
  [600089]="shares=2200,cost=19.36"
  [002273]="shares=600,cost=24.42"
  [600378]="shares=500,cost=42.69"
  [002600]="shares=1200,cost=12.29"
  [300568]="shares=600,cost=15.72"
  [300502]="shares=100,cost=393.1"
  [301217]="shares=200,cost=98.67"
  [002202]="shares=1300,cost=22.72"
)
declare -A NAME=(
  [603993]="洛阳钼业"   [601138]="工业富联"  [603663]="三祥新材"
  [605376]="博迁新材"   [600089]="特变电工"  [002273]="水晶光电"
  [600378]="昊华科技"   [002600]="领益智造"  [300568]="星源材质"
  [300502]="新易盛"     [301217]="铜冠铜箔"  [002202]="金风科技"
)
CODES_ORDERED=(603993 601138 603663 605376 600089 002273 600378 002600 300568 300502 301217 002202)

LABEL="" CODES_ARG="" DRY_RUN=0 STOP_ON_FAIL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --label) LABEL="$2"; shift 2 ;;
    --codes) CODES_ARG="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --stop-on-fail) STOP_ON_FAIL=1; shift ;;
    *) echo "❌ 未知参数：$1（可用：--label --codes --dry-run --stop-on-fail）" >&2; exit 1 ;;
  esac
done

# ---- 参数预检 ----
[[ -z "$LABEL" ]] && { echo "❌ --label 必填（批次标签，如 morning/close）" >&2; exit 1; }
[[ "$LABEL" =~ [[:space:]] || ${#LABEL} -gt 16 ]] && { echo "❌ --label 禁空白且 ≤16 字符：'$LABEL'" >&2; exit 1; }
[[ -f "$RUNNER" ]] || { echo "❌ runner 缺失：$RUNNER" >&2; exit 1; }
python3 -m py_compile "$RUNNER" || { echo "❌ runner.py 语法预检失败" >&2; exit 1; }

CODES=()
if [[ -n "$CODES_ARG" ]]; then
  IFS=',' read -ra _parts <<< "$CODES_ARG"
  for c in "${_parts[@]}"; do
    [[ "$c" =~ ^[0-9]{6}$ ]] || { echo "❌ --codes 须 6 位码逗号分隔：'$c'" >&2; exit 1; }
    [[ -n "${POS[$c]+x}" ]] || { echo "❌ 码 $c 不在 12 票池（缺 POS 仓位）" >&2; exit 1; }
    CODES+=("$c")
  done
else
  CODES=("${CODES_ORDERED[@]}")
fi

RUNROOT="/tmp/run_batch_B_${LABEL}_${TODAY}"
mkdir -p "$RUNROOT"
MANIFEST="$RUNROOT/manifest.tsv"
CHECKLIST="$RUNROOT/batch_checklist.md"

# 盘后窗口（≥16:00）清当日根层 K线缓存分片——KLINE 缓存陪跑全天会使盘后重拉仍命中
# 盘中旧 K 线（kline_max 恒 T-1，盘后定格不可达；trap: engine#kline_cache:sameday_postclose_bar_miss）
if [ "$(date +%H)" -ge 16 ]; then
  for c in "${CODES[@]}"; do
    rm -f "$HOME/.cache/skill-snapshots/${c}_${TODAY}.json"
  done
  echo "[precheck] 盘后窗口：已清 ${#CODES[@]} 票当日根层缓存分片（KLINE 缓存陪跑防御）"
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "plan: ${#CODES[@]} 票 → full/ ${#CODES[@]} 份 /tmp/runner_snapshot_{code}_modeB.json"
  for c in "${CODES[@]}"; do
    echo "  $c ${NAME[$c]:-?} pos=${POS[$c]}"
  done
  exit 0
fi

# ---- 主循环 ----
printf "code\tname\trc\tsnap_ok\tfull_snapshot_path\tstderr_path\tduration_s\n" > "$MANIFEST"
OK=0; FAIL=0
T0_ALL=$(date +%s)
for c in "${CODES[@]}"; do
  nm="${NAME[$c]:-}"
  [[ -z "$nm" ]] && { echo "❌ $c 无 NAME 映射（RCA-1 守卫需中文名）" >&2; printf "%s\t%s\t%d\t%d\t%s\t%s\t%s\n" "$c" "?" 1 0 "-" "-" "-" >> "$MANIFEST"; FAIL=$((FAIL+1)); continue; }
  [[ "${POS[$c]:-}" =~ ^shares=[0-9]+,cost=[0-9.]+$ ]] || { echo "❌ $c POS 形态非法：${POS[$c]:-}" >&2; printf "%s\t%s\t%d\t%d\t%s\t%s\t%s\n" "$c" "$nm" 1 0 "-" "-" "-" >> "$MANIFEST"; FAIL=$((FAIL+1)); continue; }
  echo "=== RUN $c $nm $(date '+%T') ==="
  t0=$(date +%s)
  set +e
  timeout "${BATCH_TIMEOUT:-600}" python3 "$RUNNER" B "$c" \
    --expected-name "$nm" --position "${POS[$c]}" \
    > "/tmp/runner_snapshot_${c}_modeB.json" 2>"/tmp/runner_stderr_${c}_modeB.log"
  rc=$?
  t1=$(date +%s); dur=$((t1-t0))
  full="$HOME/.cache/skill-snapshots/full/${c}_${TODAY}.json"
  # 快照后检：json 可解析 + 三键在（execution_shell/t0_check/realtime_quote）→ rc=0 但半吊子快照仍记 FAIL
  snap_ok=0
  if [[ $rc -eq 0 ]] && python3 - "$full" <<'PYEOF' 2>/dev/null
import json, sys
s = json.load(open(sys.argv[1]))
d = s["s4_technical"]["data"]
assert "execution_shell" in d and "t0_check" in d
assert "realtime_quote" in s["s2_quote_kline"]["data"]
PYEOF
  then snap_ok=1; fi
  if [[ $rc -eq 0 && $snap_ok -eq 1 ]]; then
    OK=$((OK+1)); echo "=== DONE $c ok ${dur}s ==="
  else
    FAIL=$((FAIL+1)); echo "=== FAIL $c rc=$rc snap_ok=$snap_ok（stderr: /tmp/runner_stderr_${c}_modeB.log）==="
    [[ $STOP_ON_FAIL -eq 1 ]] && break
  fi
  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$c" "$nm" "$rc" "$snap_ok" \
    "$( [[ $snap_ok -eq 1 ]] && echo "$full" || echo '-' )" \
    "/tmp/runner_stderr_${c}_modeB.log" "$dur" >> "$MANIFEST"
done
T_ALL=$(( $(date +%s) - T0_ALL ))
echo "SUMMARY ok=$OK fail=$FAIL ${T_ALL}s" | tee -a "$MANIFEST"

# ---- G7 批次清单（机器填数据面 + 人工框报告面）----
FULL_LIST="$HOME/.cache/skill-snapshots/full"
{
  echo "# batch_checklist — $LABEL $TODAY"
  echo ""
  echo "## 数据面（机器勾）"
  while IFS=$'\t' read -r c nm rc sok fp ep dur; do
    [[ "$c" == "code" || "$c" == SUMMARY* ]] && continue
    [[ "$rc" == "0" && "$sok" == "1" ]] && mark="✅" || mark="❌"
    echo "- $mark $c $nm rc=$rc snap_ok=$sok ${dur}s"
  done < "$MANIFEST"
  echo ""
  echo "## 报告面（人工勾）"
  echo "- [ ] 12 份单票报告 verify_gates --profile quick 全 PASS（含新增 v3.1 适用性行）"
  echo "- [ ] b_portfolio_sheet.py 自检 cells=N 全对 exit 0"
  echo "- [ ] 合集 title ≤33 字符"
  echo "- [ ] tdx_publish.py prepare L14 PASS"
  echo "- [ ] token_audit.py <会话> --label $LABEL 已记账"
} > "$CHECKLIST"

[[ $FAIL -eq 0 ]] && exit 0
[[ $OK -eq 0 ]] && exit 3
exit 2
