# Model Evaluation — how to reproduce it

The evaluation compares five local SLMs on the **same** agent workflow, on **edge**
hardware, over a fixed 12-interaction script, with every write side effect **verified
against the Google APIs** (never against the agent's own claims). This is the reference for
reproducing it end to end on any machine; for the base stack setup it defers to the root
`README.md`.


## Test-machines

The reference latency numbers are Apple M2 Pro / 16 GiB / native Metal; the presentation runs on a Win11 + RTX 3080 (10 GB) machine, which cuts gemma4's latency ~3–4× (see [WINDOWS.md](WINDOWS.md)). We assume this is due to compound memory exceeding the 16GB capacity on the MacBook which implies 


## What gets measured

- **Latency** per interaction (wall clock, webhook request → response) → `results/performance_metrics.md`
- **Correctness / hallucination** vs. seeded ground truth → `results/model_comparison.md`
- **Tool-selection behaviour** (which tools actually fired) → `results/tool_selection.md`
- **Resource use** (CPU / RSS, host + containers) sampled every 2 s → `metrics/*.csv`
- **Side effects** (events/tasks created, mails sent), API-verified → `results/<tag>_sideeffects.json`

Models: `llama3.2:1b`, `smollm2:1.7b`, `llama3.2:3b`, `qwen3:4b-instruct`, `gemma4:12b-it-qat`.
Config series **v2.1** (current): `numCtx 8192`, `temperature 0.2` (workflow defaults).

## Prerequisites (one-time)

1. **Stack up.** `docker compose up -d` (n8n + Postgres) and native Ollama on `:11434`
   (`brew services start ollama`). See the root `README.md` ("Run it (macOS / Linux)").
2. **Models pulled.** `run_all_models.sh` fails fast and lists any missing; to pull all:
   ```bash
   for m in llama3.2:1b smollm2:1.7b llama3.2:3b qwen3:4b-instruct gemma4:12b-it-qat; do
     ollama pull "$m"; done
   ```
3. **Google account connected.** A Google account with the Gmail, Calendar, and Tasks APIs
   enabled and the three n8n OAuth credentials signed in (root `README.md`, "Create the
   Google Cloud project + OAuth client"). The scripts mint tokens from those credentials via
   `seed/google_token.py`, so
   **no separate OAuth client is needed** — but Testing-mode refresh tokens expire after
   **7 days**, so re-authorize the three credentials right before an eval run.
   > **Account-specific field:** the workflow's `list_events` / `create_event` nodes hold a
   > concrete **calendar ID** (a Google address, e.g. `you@gmail.com`). n8n's Google Calendar
   > node does **not** accept the `primary` alias — it validates the ID and rejects it — so
   > set these two nodes to your account's calendar ID (your Google address). Seeding and
   > verification use the API `primary` alias directly, which resolves to the same calendar.
4. **Python 3** (stdlib only; `certifi` optional — `google_token.py` falls back to the
   system CA bundle).

## Reproduce the whole matrix (one command)

```bash
./eval/run_all_models.sh
```

Runtime ≈ 30–50 min (dominated by `gemma4:12b`; `smollm2` is capped at 120 s/request
because it produces runaways). Fastest models run first, so a broken pipeline surfaces in
~2 min.

> **Single-model residency.** On the 16 GiB host only **one** model may be resident at a
> time — a second (e.g. left warm by another call's `keepAlive`) starves RAM and skews the
> numbers. The runner enforces this: before each warm-up it unloads every other resident
> model (`ollama stop`). Check with `ollama ps` (should show exactly one during a run). Do
> not issue manual model calls while the matrix is running, or you reintroduce a stray.

Each model, the runner (`eval/run_model_eval.sh`) automatically:

1. resets ground truth — `seed/cleanup.py` then `seed/seed_mailbox.py` (15 emails
   backdated so "today" is deterministic + 3 calendar events on `primary`);
2. clears Postgres chat memory;
3. switches the workflow's Ollama model, re-imports, activates, restarts n8n;
4. warms the model (records cold-load + tok/s);
5. snapshots Google state (`eval_state.py pre`), starts the resource samplers;
6. runs `eval/interactions.json` via the production webhook (`run_interactions.py`);
7. verifies + **cleans up** side effects (`eval_state.py post` — diffs the Google APIs,
   deletes eval-created events/tasks, trashes `*.example` test mails);
8. unloads the model and restores the repo-default workflow.

### One model only

```bash
./eval/run_model_eval.sh gemma4:12b-it-qat edge-gemma4-12b-r2 300
#                        <model>            <tag>              <timeout> [num_predict]
```

## Regenerate the derived docs from the raw runs

```bash
python3 eval/make_performance_metrics.py   # -> results/performance_metrics.md (latency + resources)
./eval/make_plots.py                       # -> results/plots/*.png
python3 eval/tool_selection.py             # -> results/tool_selection.md
```

`make_performance_metrics.py` reads the **latest** CSV per tag, so re-running a model
refreshes its numbers automatically. `tool_selection.py` matches n8n executions by UTC
time window — update its `RUNS` windows from `results/run_windows_<machine>.txt` (written by
`run_all_models.sh`) before regenerating. `model_comparison.md` and `config_impact.md`
carry hand-scored correctness/hallucination analysis and are updated from each run's
`*_sideeffects.json` + `*.jsonl` transcripts.

## Extending

### Add a model to the comparison
1. `ollama pull <tag>` — everything runs in Ollama (GGUF). Ollama has **no FP8**; its 8-bit
   quant is `Q8_0`. Confirm the exact tag with `ollama list`.
2. **Smoke-test tool support first** (1 min) — some models (phi3, tinyllama, gemma:2b) can't
   call tools in Ollama and fail every write. A quick `/api/chat` with the tool schema tells you.
3. Add a line to `RUNS` in `run_all_models.sh` (`<ollama-model> <short> <timeout>`) and to
   `MODELS` in `make_performance_metrics.py` (`label, short, disk_GB, load_s, tok_s` — the last
   two are just fallbacks; the actual warm-up is read from `metrics/warmup_<tag>.csv`).
4. Run, then regenerate the docs and hand-score correctness in `model_comparison.md`.
   *(Comparing quants of one model — e.g. Q8_0 vs Q4 — is a quantization-impact study; note it
   alongside `config_impact.md`.)*

### Benchmark another machine (laptop / desktop / RTX 3080)
Runs are namespaced by `MACHINE` so different boxes don't collide:
```bash
MACHINE=rtx3080 ./eval/run_all_models.sh                     # tags rtx3080-<model>-r2
python3 eval/make_performance_metrics.py --machine rtx3080 \
        --hardware "Win11, RTX 3080 10 GB, CUDA"             # -> performance_metrics_rtx3080.md
```
Set up each box like any deployment (`WINDOWS.md` for the Windows/CUDA machine); adjust
per-model timeouts for slower/faster hardware. Then compare `performance_metrics_<machine>.md`
across boxes — that cross-machine table is the edge-vs-hardware result.

**GPU sampling** (neither `docker stats` nor `ps` sees the GPU): run alongside the eval —
`metrics/collect_gpu_stats.sh <tag>` on macOS (powermetrics, needs sudo) or
`metrics/collect_gpu_stats_nvidia.sh <tag>` on NVIDIA/CUDA boxes (util %, VRAM, watts, temp).
On Windows, run the `.sh` scripts under Git Bash / WSL.

## Reproducibility caveats (documented, not bugs)

- **Small models are non-deterministic even at temp 0.2** — write outcomes for models ≤4B
  vary run to run (a documented finding, `config_impact.md`). Latency medians are stable;
  individual write successes are not. Expect the *ranking* to reproduce, not every cell.
- **Shared personal account** (project decision §3.3): manual testing between runs can leak
  artifacts into the "sealed" eval world, and `in:sent newer_than:1d` catches non-eval
  sends. Ground-truth isolation is best-effort; only API-level verification is trusted.
- **Hardware sets the absolute latencies.** The numbers here are Apple M2 Pro / 16 GiB /
  native Metal. The relative model ranking transfers; the seconds do not.
