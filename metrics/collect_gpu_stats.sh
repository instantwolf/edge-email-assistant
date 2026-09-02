#!/usr/bin/env bash
# GPU sampler for Apple Silicon; neither docker stats nor ps can see the Metal GPU.
# Needs sudo (powermetrics is root-only). Run it in one terminal while replaying
# interactions in another, then Ctrl-C:
#
#   sudo ./metrics/collect_gpu_stats.sh <tag>
#   # -> metrics/gpu_stats_<tag>.csv   (ts,gpu_active_pct,gpu_freq_mhz,gpu_power_mw,die_temp_c)
#
# study-v3 task 2.4 adds the `smc` sampler and a die_temp_c column: DESIGN.md
# §13 checks latency drift against run index AND die temperature, and if it is
# flat one sentence retires the thermal-throttling threat (§16). The NVIDIA
# sampler already reports temp_c. If a macOS build does not expose a die
# temperature, the column stays empty and the "empty" is the finding — the
# threat is then checked on latency-vs-run-index alone on this host, and that
# limitation is stated rather than papered over.
#
# `ollama ps` is a cheaper no-sudo check that the model is GPU-resident.
set -euo pipefail

TAG="${1:?usage: sudo $0 <tag>}"
OUT="$(cd "$(dirname "$0")" && pwd)/gpu_stats_${TAG}.csv"
INTERVAL_MS=1000

echo "ts,gpu_active_pct,gpu_freq_mhz,gpu_power_mw,die_temp_c" > "$OUT"
echo "sampling GPU every ${INTERVAL_MS} ms -> $OUT (Ctrl-C to stop)"

powermetrics --samplers gpu_power,smc -i "$INTERVAL_MS" 2>/dev/null | \
while IFS= read -r line; do
  case "$line" in
    *"GPU HW active residency"*)
      pct=$(echo "$line" | sed -E 's/.*: *([0-9.]+)%.*/\1/') ;;
    *"GPU HW active frequency"*)
      freq=$(echo "$line" | sed -E 's/.*: *([0-9]+) MHz.*/\1/') ;;
    *"die temperature"*|*"GPU die temperature"*)
      temp=$(echo "$line" | sed -E 's/.*: *([0-9.]+) C.*/\1/') ;;
    *"GPU Power"*)
      mw=$(echo "$line" | sed -E 's/.*: *([0-9]+) mW.*/\1/')
      echo "$(date +%s),${pct:-},${freq:-},${mw:-},${temp:-}" >> "$OUT" ;;
  esac
done
