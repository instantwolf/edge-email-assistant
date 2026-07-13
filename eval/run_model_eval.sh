#!/usr/bin/env bash
# Full eval protocol for one model: reset ground truth, clear chat memory, switch
# the workflow's model, warm up, sample resources, run all interactions, then
# diff-verify and clean up side effects.
#
#   ./eval/run_model_eval.sh <ollama-model> <tag> [per-request-timeout-s] [num-predict]
#   ./eval/run_model_eval.sh gemma4:12b-it-qat edge-gemma4-np256 300 256   # with generation cap
set -euo pipefail
MODEL=$1
TAG=$2
TIMEOUT=${3:-300}
NUM_PREDICT=${4:-}   # per-request generation cap (body.numPredict); empty = unlimited
cd "$(dirname "$0")/.."

echo "== [$TAG] reset ground truth =="
python3 seed/cleanup.py
python3 seed/seed_mailbox.py >/dev/null
echo "== [$TAG] clear chat memory =="
docker compose exec -T postgres psql -U agent -d agent_memory \
  -c 'TRUNCATE n8n_chat_histories;' >/dev/null 2>&1 || true

echo "== [$TAG] switch workflow model to $MODEL =="
python3 - "$MODEL" <<'PY'
import json, sys
p = "workflows/email_calendar_assistant.json"
d = json.load(open(p))
for n in d["nodes"]:
    if n["name"] == "Ollama Chat Model":
        n["parameters"]["model"] = sys.argv[1]
json.dump(d, open("/tmp/wf_eval.json", "w"))
PY
docker compose cp /tmp/wf_eval.json n8n:/tmp/wf.json >/dev/null
docker compose exec -T n8n n8n import:workflow --input=/tmp/wf.json >/dev/null 2>&1
docker compose exec -T n8n n8n update:workflow --id=EmailCalAssist01 --active=true >/dev/null 2>&1
docker compose restart n8n >/dev/null 2>&1
sleep 8
for i in $(seq 1 30); do
  curl -sf -o /dev/null --max-time 2 http://localhost:5678/healthz && break; sleep 1
done
sleep 3

# On a 16 GiB host a second resident model (e.g. one left warm by keepAlive) starves
# RAM and skews latency/resource numbers. Unload all so warm-up cold-loads only $MODEL.
echo "== [$TAG] enforce single loaded model (unload any others) =="
for m in $(ollama ps | awk 'NR>1{print $1}'); do
  echo "   unloading resident model: $m"; ollama stop "$m" >/dev/null 2>&1 || true
done

echo "== [$TAG] warm-up / model load =="
# Persist cold-load seconds + generation tok/s per run (they differ by hardware) so
# the report reads them per machine, not from a constant. -> metrics/warmup_<tag>.csv
WARM=$(curl -s --max-time 300 http://localhost:11434/api/generate \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"Say OK.\",\"stream\":false,\"keep_alive\":\"1h\",\"options\":{\"num_ctx\":8192}}" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d['load_duration']/1e9:.2f},{d['eval_count']/(d['eval_duration']/1e9):.1f}\")")
echo "load ${WARM%,*}s | gen ${WARM#*,} tok/s"
mkdir -p metrics
printf 'load_s,gen_tok_s\n%s\n' "$WARM" > "metrics/warmup_${TAG}.csv"

python3 eval/eval_state.py pre "$TAG"

./metrics/collect_stats.sh "metrics/stats_${TAG}.csv" 2 >/dev/null 2>&1 &
DPID=$!
./metrics/collect_host_stats.sh "metrics/host_stats_${TAG}.csv" 2 >/dev/null 2>&1 &
HPID=$!

echo "== [$TAG] interaction run =="
# Branch instead of an array so this stays safe under `set -u` on bash 3.2 (macOS).
if [ -n "$NUM_PREDICT" ]; then
  echo "   (generation cap num_predict=$NUM_PREDICT)"
  python3 eval/run_interactions.py --tag "$TAG" --timeout "$TIMEOUT" --num-predict "$NUM_PREDICT" || true
else
  python3 eval/run_interactions.py --tag "$TAG" --timeout "$TIMEOUT" || true
fi

kill "$DPID" "$HPID" 2>/dev/null || true
echo "== [$TAG] side effects (API-verified) =="
python3 eval/eval_state.py post "$TAG"
# unload the tested model so it doesn't squat on GPU memory
ollama stop "$MODEL" >/dev/null 2>&1 || true
# the eval deployed a model-switched copy; put the repo default back
echo "== [$TAG] restore default workflow =="
docker compose cp workflows/email_calendar_assistant.json n8n:/tmp/wf_restore.json >/dev/null
docker compose exec -T n8n n8n import:workflow --input=/tmp/wf_restore.json >/dev/null 2>&1
docker compose exec -T n8n n8n update:workflow --id=EmailCalAssist01 --active=true >/dev/null 2>&1
docker compose restart n8n >/dev/null 2>&1
echo "== [$TAG] done (model unloaded, default workflow restored) =="
