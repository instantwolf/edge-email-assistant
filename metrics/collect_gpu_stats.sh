#!/usr/bin/env bash
# GPU sampler for Apple Silicon; neither docker stats nor ps can see the Metal GPU.
# Needs sudo (powermetrics is root-only). Run it in one terminal while replaying
# interactions in another, then Ctrl-C:
#
#   sudo ./metrics/collect_gpu_stats.sh <tag>
#   # -> metrics/gpu_stats_<tag>.csv   (ts,gpu_active_pct,gpu_freq_mhz,gpu_power_mw)
#
# `ollama ps` is a cheaper no-sudo check that the model is GPU-resident.
set -euo pipefail

TAG="${1:?usage: sudo $0 <tag>}"
OUT="$(cd "$(dirname "$0")" && pwd)/gpu_stats_${TAG}.csv"
INTERVAL_MS=1000

echo "ts,gpu_active_pct,gpu_freq_mhz,gpu_power_mw" > "$OUT"
echo "sampling GPU every ${INTERVAL_MS} ms -> $OUT (Ctrl-C to stop)"

powermetrics --samplers gpu_power -i "$INTERVAL_MS" 2>/dev/null | \
while IFS= read -r line; do
  case "$line" in
    *"GPU HW active residency"*)
      pct=$(echo "$line" | sed -E 's/.*: *([0-9.]+)%.*/\1/') ;;
    *"GPU HW active frequency"*)
      freq=$(echo "$line" | sed -E 's/.*: *([0-9]+) MHz.*/\1/') ;;
    *"GPU Power"*)
      mw=$(echo "$line" | sed -E 's/.*: *([0-9]+) mW.*/\1/')
      echo "$(date +%s),${pct:-},${freq:-},${mw:-}" >> "$OUT" ;;
  esac
done
