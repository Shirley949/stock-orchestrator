#!/usr/bin/env bash
# cleanup_stale_cache.sh — 清理非今日的 snapshot/probe/westock cache，避免旧数据干扰测试
#
# 动机（memory [[verify-freshness-not-stale-cache]]）：skill-snapshots 是 DataSnapshot.save() 的
# raw fetch 缓存（按日期分文件），跨日陈旧。验证 latest_period/freshness 时若误读旧 cache 文件
# （而非 runner fresh stdout），会用过期事实下错误结论——曾导致 plan edge case 误判
# （300408 lhb / 002203 northbound 都是基于旧 cache 的伪问题）。
#
# 用法:
#   bash cleanup_stale_cache.sh           # 清非今日 snapshot/probe/westock cache
#   bash cleanup_stale_cache.sh --pdfs    # 额外清 em_research_pdfs（研报 PDF，静态历史，按需重下）
#
# 保留: 当日（${TODAY}）cache 文件——runner 同日复用避免重拉触发富途/新浪 IP 限流。
# 建议: 跑回归 / 10 票实测 / freshness 验证前先跑此脚本。
set -euo pipefail

TODAY=$(date +%Y%m%d)                                 # snapshot/westock 文件名 YYYYMMDD
TODAY_DASH=$(date +%Y-%m-%d)                          # probe 文件名 YYYY-MM-DD
CACHE="${HOME}/.cache"

echo "[$(date '+%F %T')] 清理非今日 cache (today=$TODAY / probe=$TODAY_DASH)"

# 通用清理：某目录下 *.json，保留 *_${TODAY_PATTERN} 的今日文件
clean_dir() {
  local dir="$1" today_pattern="$2" label="$3"
  local kept=0 removed=0
  shopt -s nullglob
  for f in "$dir"/*.json; do
    case "$f" in
      *${today_pattern}*) kept=$((kept+1)) ;;   # 今日保留
      *) rm -f "$f"; removed=$((removed+1)) ;;
    esac
  done
  shopt -u nullglob
  echo "  $label: 删 $removed 个非今日 | 保留 $kept 个今日"
}

clean_dir "$CACHE/skill-snapshots"  "_${TODAY}.json"   "skill-snapshots"
clean_dir "$CACHE/skill-probes"     "/${TODAY_DASH}.json" "skill-probes"
clean_dir "$CACHE/westock_api_cache" "/${TODAY}.json"   "westock_api_cache"

# full/ 合并存档白名单（模式B v2 §2.5）：A/B 每次运行的全量数据存档，"不删"是用户硬指令。
# 上方 clean_dir 的 "$dir"/*.json 只匹配顶层文件，full/ 子目录天然不中——此处显式声明 +
# 清点留痕，防未来有人改成 find -delete / globstar 时误伤。
if [ -d "$CACHE/skill-snapshots/full" ]; then
  n=$(ls "$CACHE/skill-snapshots/full"/*.json 2>/dev/null | wc -l)
  echo "  skill-snapshots/full: 白名单保留 $n 个存档（A/B 全量数据持久层，永不清理）"
fi

# 可选：研报 PDF（静态历史文档，cninfo 重下较慢）
if [ "${1:-}" = "--pdfs" ]; then
  if [ -d "$CACHE/em_research_pdfs" ]; then
    n=$(find "$CACHE/em_research_pdfs" -name '*.pdf' 2>/dev/null | wc -l)
    rm -f "$CACHE/em_research_pdfs"/*.pdf
    echo "  em_research_pdfs: 删 $n 个研报 PDF（--pdfs）"
  fi
fi

echo "✓ 清理完成。今日 fresh cache 保留（验证永远用 runner stdout，不读这些 cache 文件）。"
