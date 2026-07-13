#!/usr/bin/env bash
# Sample the native Ollama processes (CPU%, RSS) on the macOS host into a CSV.
# Complements collect_stats.sh, which only sees Docker containers.
# Usage: ./metrics/collect_host_stats.sh [out.csv] [interval_seconds]
set -u
OUT=${1:-metrics/host_stats_$(date +%Y%m%d_%H%M%S).csv}
INT=${2:-2}
echo "ts,pid,cpu_perc,rss_mb,command" > "$OUT"
echo "sampling native ollama processes every ${INT}s -> $OUT (Ctrl-C to stop)"
while true; do
  ps -Ao pid,pcpu,rss,comm | awk -v ts="$(date +%s)" \
    'tolower($4) ~ /ollama/ { printf "%s,%s,%s,%.1f,%s\n", ts, $1, $2, $3/1024, $4 }' >> "$OUT"
  sleep "$INT"
done
