#!/usr/bin/env bash
# Run the full eval protocol (eval/run_model_eval.sh) for every model in RUNS.
# Fastest models first so a broken pipeline surfaces quickly.
#
# Needs the docker stack up (n8n + postgres), native Ollama on :11434, every RUNS
# model pulled, and the 3 Google OAuth creds signed in within the last 7 days.
# See eval/README.md for the full checklist.
#
#   ./eval/run_all_models.sh                  # tags <MACHINE>-<model>-r2, MACHINE=edge
#   MACHINE=rtx3080 ./eval/run_all_models.sh  # separate tag namespace per box
set -euo pipefail
cd "$(dirname "$0")/.."

# Set MACHINE per box so runs on different machines don't collide. Tag = <MACHINE>-<short>-r2.
MACHINE="${MACHINE:-edge}"

# Columns: "<ollama-model> <short-name> <per-request-timeout-s>".
# smollm2 capped at 120s (it produces 300s runaways); gemma4 needs 300s for its
# legitimate tail. Add a model by adding a line.
RUNS=(
  "llama3.2:1b        llama32-1b    120"
  "llama3.2:3b        llama32-3b    120"
  "qwen3:4b-instruct  qwen3-4b      120"
  "smollm2:1.7b       smollm2-17b   120"
  "gemma4:12b-it-qat  gemma4-12b    300"
  # Add more here with the EXACT Ollama tags you pulled (check `ollama list`).
  # Everything runs in Ollama (GGUF); Ollama has no FP8, Q8_0 is its 8-bit quant.
  # "gemma-e4b:q4      gemmae4b-q4   120"
  # "gemma-e4b:q8_0    gemmae4b-q8   120"
)

echo "== preflight: verify all models are pulled (MACHINE=$MACHINE) =="
have=$(ollama list | awk 'NR>1{print $1}')
missing=""
for r in "${RUNS[@]}"; do
  set -- $r
  echo "$have" | grep -qx "$1" || missing="$missing $1"
done
if [ -n "$missing" ]; then
  echo "ERROR: models not pulled:$missing" >&2
  echo "Pull them first, e.g.:  for m in$missing; do ollama pull \"\$m\"; done" >&2
  exit 1
fi
echo "all present."

# Record UTC start/stop per run so tool_selection.py windows can be regenerated.
WINDOWS="eval/results/run_windows_${MACHINE}.txt"
: > "$WINDOWS"

for r in "${RUNS[@]}"; do
  set -- $r
  MODEL=$1; SHORT=$2; TO=$3
  TAG="${MACHINE}-${SHORT}-r2"
  start=$(date -u +"%Y-%m-%d %H:%M:%S")
  echo "######## $MODEL  ($TAG, timeout ${TO}s)  start $start UTC ########"
  ./eval/run_model_eval.sh "$MODEL" "$TAG" "$TO"
  stop=$(date -u +"%Y-%m-%d %H:%M:%S")
  echo "$TAG | $MODEL | $start | $stop" >> "$WINDOWS"
  echo "######## $MODEL done ($start -> $stop UTC) ########"
done

echo
echo "== ALL RUNS DONE ($MACHINE). Regenerate the derived docs: =="
echo "  python3 eval/make_performance_metrics.py --machine $MACHINE --hardware '<HW string>'"
echo "  ./eval/make_plots.py"
echo "  python3 eval/tool_selection.py             # update its RUNS windows from $WINDOWS first"
echo "Run windows recorded in $WINDOWS"
