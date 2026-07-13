# Edge Latency: where the seconds go, and why the obvious fix backfires

**Scope:** edge deployment — Apple M2 Pro, 16 GiB, **native Ollama/Metal**, default model
**gemma4:12b-it-qat**. n8n 2.28.6 + Postgres 16 in Docker. Date: 2026-07-06.
This decomposes the single end-to-end latencies in `performance_metrics.md` and tests the
most obvious tuning lever end-to-end. It changed our mental model twice; the conclusions
below are ranked on measurement, not intuition.

## TL;DR

1. **Within one LLM turn, latency is generation-bound** — prefill is only ~21% and Ollama's
   prefix cache is already reused across turns (no work to do there).
2. **The queries that actually hurt are turn-count-bound, not generation-length-bound.** The
   flagship multi-tool query takes ~180 s because the agent runs *many* prefill+generate
   turns to do several sequential writes at ~13 tok/s — not because any one generation is huge.
3. **The obvious fix — capping generated tokens (`num_predict`) — is refuted.** A tight cap
   (256) crushes the tail (max 177→52 s) but **destroys write reliability (4/4 → 0/4 writes)**
   by truncating tool-call JSON; a loose cap (512) keeps writes but **recovers no latency**.
4. **Write reliability is the binding constraint.** gemma4 is the default *only* because it
   writes correctly; any lever that trades writes for latency just yields "slow qwen3."
5. **Net:** the median is already fine (~44 s; simple/date queries 8–16 s). The tail is a
   fundamental turn-count × slow-generation limit on 16 GiB Metal — closable only by a
   **batching tool** (engineering) or **faster inference** (hardware/model), not by tuning.

Reproduce: `eval/latency_budget.py` (per-turn probe, no Google writes) and three full
`eval/run_model_eval.sh` runs (tags `edge-gemma4-baseline`, `-np512`, `-np256`).

## 1. Within a turn: generation-bound, prefill already cached

`eval/latency_budget.py` replays the flagship loop straight against Ollama `/api/chat` with
the production 7-tool schema and realistic tool results, recording prefill
(`prompt_eval_*`) and generation (`eval_*`) per turn. gemma4, num_ctx 8192, unlimited gen:

| turn | step | prefill tok | prefill s | gen tok | gen s | gen tok/s |
|---|---|---|---|---|---|---|
| 1 | read_emails call | 839 | 4.2 | 153 | 10.5 | 14.5 |
| 2 | list_events call | 1439 | 5.8 | 63 | 4.6 | 13.7 |
| 3 | final answer | 1676 | 1.5 | 362 | 28.6 | 12.7 |
| | **sum** | | **11.5 s (21%)** | | **43.7 s (79%)** | |

Generation is **79%** of per-turn LLM time and runs at a hardware-fixed ~13 tok/s on Metal.
qwen3:4b shows the same shape (25% / 75%), just 3× faster generation — the pattern is
architectural, not model-specific.

Two hypothesised levers were **measured away**:

- **Prefix cache is already hit.** Same prompt sent twice (2nd larger); Ollama reports the
  full token count even when serving the prefix from KV cache, so *duration* is the truth:
  gemma4 **1607 tok / 15.1 s** (cold) → **1626 tok / 0.68 s** (warm prefix) = **22× faster**
  → the system+tools prefix is reused across the agent loop (`keepAlive: 1h`). Prefill stays
  cheap even as context grows. No work here.
- **num_ctx 4096 vs 8192 is a no-op on compute** in a warm probe (prefill 11.4 vs 11.5 s;
  gen 42.8 vs 43.7 s). The 38→50 s rise seen in `config_impact.md` at 8k is therefore
  **KV-cache memory** (RAM pressure on the 16 GiB host + larger real payloads that actually
  fill the window), not per-token cost.

## 2. The generation cap: tested across the frontier, and refuted

Three full 12-interaction runs (reseed → deploy → warm → run → **Google-API pre/post diff**
→ cleanup), identical except the per-turn generation cap; runtime left untuned to isolate it.

| Config | median | mean | p90 | max | #7 multi-tool | #8 task-extract | **writes (of 4, API-verified)** |
|---|---|---|---|---|---|---|---|
| baseline (∞) | 43.9 s | 50.6 s | 108.6 s | 177.6 s | 177.6 s | 108.6 s | **4/4 ✓** |
| num_predict 512 | 44.3 s | 53.1 s | 65.3 s | 182.4 s | 182.4 s | 108.4 s | **3/4** (lost #7 events; variance) |
| num_predict 256 | 38.0 s | 32.2 s | 49.5 s | **52.4 s** | **22.8 s** | 51.4 s | **0/4 ✗** |

- **256 crushes the tail but severs every write.** gemma4 emits 150–250 tokens of preamble
  before a tool call (§1), so a 256-token turn budget truncates the tool-call JSON;
  multi-write requests never finish. The −70% max and 177→23 s on #7 are **the agent loop
  aborting early, not running faster**.
- **512 confirms it.** Give the loop room and writes return (3/4) — but the tail returns to
  baseline: task-extract #8 is **108.6 → 108.4 s**, identical. No single turn exceeds 512
  tokens, so the cap never bites the thing that makes the tail long.

## 3. Synthesis: the tail is turn-count-bound; reliability is the constraint

§1 and §2 reconcile cleanly: **within a turn** generation dominates, but the **tail** is made
of *many* such turns. The 177 s multi-tool query is the agentic loop —
read → list → create_event → create_event → answer — each a full prefill+generate at
13 tok/s. A per-turn token cap is the wrong tool for a turn-count problem: it can only shorten
the tail by truncating the tool calls that constitute the turns, which is exactly why it
destroys writes.

And **write reliability is the whole reason gemma4 is the default** (baseline scored 4/4 here,
above its documented 3/4). A lever that trades writes for latency converts it into a slow
version of qwen3 (which is faster *and* 0/4). So the cap is kept as a per-request knob for
experiments but **must not be a default**.

The result is a genuine **latency ⟷ reliability frontier**, not a tuning oversight: on
16 GiB Metal, reliable multi-write agentic latency is bounded by (turns × slow generation).

## 4. Levers, ranked on measurement

| Lever | Attacks | Edge impact (measured) | Autonomy cost | Status |
|---|---|---|---|---|
| Tuned Ollama runtime — flash-attn + `q8_0` KV | KV memory (the real 8k tax + 12B instability) | frees RAM; latency ~neutral | none | shipped — validate for **memory**, not speed |
| Batching tool (create N events/tasks per call) | the **turn-count tail** | the only structural cut to the tail | low | ⬜ candidate engineering |
| Turn reduction via prompt/tool design | agent iterations on multi-write | limited — the writes *are* the turns | low | ⬜ measure vs writes |
| Per-request `num_ctx` (workflow) | KV memory on small-payload queries | negligible for flagship; helps big payloads | none | shipped (default 8192) |
| Prompt brevity (8-line + temp 0.2) | generated tokens | already cut read answers ~3× | none | shipped (v2.1) |
| Prefix caching | repeated prefill | **already hit** — no work | none | confirmed working |
| ~~`num_predict` cap~~ | ~~per-turn generation~~ | **refuted (§2): breaks writes or no gain** | breaks writes | knob kept, **default off** |

## 5. Reproduce

```bash
# per-turn budget + prefix-cache verdict (safe: talks to Ollama only, no Google writes)
python3 eval/latency_budget.py --model gemma4:12b-it-qat --num-ctx 8192 --compare-ctx 4096

# the frontier (full protocol, reseeds + API-verifies + cleans up; needs fresh OAuth)
./eval/run_model_eval.sh gemma4:12b-it-qat edge-gemma4-baseline 300
./eval/run_model_eval.sh gemma4:12b-it-qat edge-gemma4-np512   300 512
./eval/run_model_eval.sh gemma4:12b-it-qat edge-gemma4-np256   300 256
```

Artifacts: `eval/results/edge-gemma4-{baseline,np512,np256}_*.{csv,jsonl}` +
`*_sideeffects.json` (API-verified writes); per-turn CSVs `latency_budget_*.csv`;
resource samples `metrics/{stats,host_stats}_edge-gemma4-*.csv`.
