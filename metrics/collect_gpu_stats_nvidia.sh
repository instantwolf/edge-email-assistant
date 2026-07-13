#!/usr/bin/env bash
# GPU sampler for NVIDIA/CUDA machines (the Win11 + RTX 3080 demo box); the CUDA
# counterpart to collect_gpu_stats.sh, which is macOS-only. Queries the driver via
# nvidia-smi since neither docker stats nor ps can see the GPU.
#
# Run it in one terminal while a model is exercised in another, then Ctrl-C:
#   ./metrics/collect_gpu_stats_nvidia.sh <tag>
#   # -> metrics/gpu_stats_<tag>.csv  (ts,gpu_util_pct,mem_used_mb,power_w,temp_c)
#
# Works on Windows via Git Bash / WSL as long as nvidia-smi is on PATH.
set -euo pipefail

TAG="${1:?usage: $0 <tag>}"
OUT="$(cd "$(dirname "$0")" && pwd)/gpu_stats_${TAG}.csv"

command -v nvidia-smi >/dev/null 2>&1 || { echo "nvidia-smi not found on PATH" >&2; exit 1; }

echo "ts,gpu_util_pct,mem_used_mb,power_w,temp_c" > "$OUT"
echo "sampling nvidia-smi every 1s -> $OUT (Ctrl-C to stop)"

# -l 1: one CSV line per GPU per second; reformat each with a unix ts.
nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw,temperature.gpu \
           --format=csv,noheader,nounits -l 1 \
| while IFS=',' read -r util mem pow temp; do
    printf '%s,%s,%s,%s,%s\n' "$(date +%s)" "${util// /}" "${mem// /}" "${pow// /}" "${temp// /}" >> "$OUT"
  done
