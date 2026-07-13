#!/usr/bin/env bash
# Sample per-container CPU/memory via `docker stats` into a CSV until killed.
# Usage: ./metrics/collect_stats.sh [out.csv] [interval_seconds]
set -u
OUT=${1:-metrics/stats_$(date +%Y%m%d_%H%M%S).csv}
INT=${2:-2}
echo "ts,container,cpu_perc,mem_used,mem_limit,mem_perc" > "$OUT"
echo "sampling docker stats every ${INT}s -> $OUT (Ctrl-C to stop)"
while true; do
  docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}' \
    | awk -v ts="$(date +%s)" -F',' '{ split($3, m, " / "); print ts "," $1 "," $2 "," m[1] "," m[2] "," $4 }' \
    >> "$OUT"
  sleep "$INT"
done
