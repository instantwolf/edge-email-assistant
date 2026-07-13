# Measured Performance Metrics per Model — Edge Deployment

Hardware: Apple M2 Pro, 16 GiB unified memory. LLM runtime: **native Ollama 0.31.1** (Metal GPU).
Orchestration: n8n 2.28.6 + PostgreSQL 16 in Docker (3 CPUs / 2.4 GiB allocated).
Workload: 12-interaction script via production webhook; resources sampled every 2 s.
Latency = wall clock webhook request → response (n8n + LLM turns + Google API).
The v2.1 series was **refreshed 2026-07-06** under the current workflow with **single-model residency enforced** (`run_model_eval.sh` unloads any other model before each run, so no stray model contends for the 16 GiB host).

Two configuration series:
- **v2**: numCtx 4096 (Ollama default), default temperature — initial matrix
- **v2.1**: numCtx 8192, temperature 0.2 — after the #12 context-overflow fix

Raw data: `eval/results/<tag>_*.csv|.jsonl`, `metrics/*_<tag>.csv`.
Regenerate with `python3 eval/make_performance_metrics.py`. Date: 2026-07-06.

## Latency — v2 config (min / median / mean / p90 / max, seconds)

| Model | latency (s) | HTTP ok |
|---|---|---|
| llama3.2:1b | 0.4 / 2.2 / 3.1 / 6.6 / 7.8 | 10/12 |
| smollm2:1.7b | 0.3 / 8.6 / 86.4 / 300.0 / 300.0 | 6/12 |
| llama3.2:3b | 0.9 / 9.4 / 7.5 / 10.8 / 12.7 | 12/12 |
| qwen3:4b-instruct | 0.4 / 8.7 / 9.3 / 18.6 / 19.8 | 11/12 |
| gemma4:12b-it-qat | 9.0 / 36.3 / 52.4 / 137.8 / 146.6 | 12/12 |

## Latency — v2.1 config (current) (min / median / mean / p90 / max, seconds)

| Model | latency (s) | HTTP ok |
|---|---|---|
| llama3.2:1b | 0.4 / 3.0 / 8.9 / 6.9 / 72.3 | 12/12 |
| smollm2:1.7b | 0.3 / 10.9 / 18.8 / 48.4 / 48.7 | 12/12 |
| llama3.2:3b | 1.1 / 9.6 / 8.9 / 15.4 / 16.6 | 12/12 |
| qwen3:4b-instruct | 0.4 / 10.3 / 9.9 / 20.7 / 22.8 | 12/12 |
| gemma4:12b-it-qat | 8.2 / 33.3 / 47.4 / 113.4 / 129.7 | 12/12 |

## Latency by category — v2.1 config (mean, seconds)

| Category | llama3.2:1b | smollm2:1.7b | llama3.2:3b | qwen3:4b-instruct | gemma4:12b-it-qat |
|---|---|---|---|---|---|
| simple | 1.8 | 4.3 | 11.6 | 2.5 | 13.2 |
| datetime | 0.7 | 0.3 | 1.1 | 0.4 | 8.7 |
| single-tool | 20.7 | 28.3 | 10.4 | 18.1 | 56.1 |
| multi-tool | 6.9 | 48.4 | 13.3 | 17.8 | 113.4 |
| task-extract | 6.0 | 7.4 | 16.6 | 11.7 | 129.7 |
| memory | 2.7 | 23.7 | 4.7 | 1.6 | 14.7 |
| memory-action | 1.2 | 22.0 | 2.5 | 1.6 | 25.1 |
| create-event | 3.2 | 1.8 | 4.1 | 8.8 | 26.7 |

## Model loading & generation (native Ollama, warm-up)

| Model | Disk | Cold load | Generation |
|---|---|---|---|
| llama3.2:1b | 1.3 GB | 1.5 s | 136.3 tok/s |
| smollm2:1.7b | 1.8 GB | 1.6 s | 77.4 tok/s |
| llama3.2:3b | 2.0 GB | 2.6 s | 63.2 tok/s |
| qwen3:4b-instruct | 2.6 GB | 2.8 s | 52.8 tok/s |
| gemma4:12b-it-qat | 7.2 GB | 10.3 s | 18.1 tok/s |

## Resource utilization during the v2.1 runs

| Model | Ollama CPU mean/peak (host %) | Ollama peak RSS (GiB) | n8n CPU peak / mem peak |
|---|---|---|---|
| llama3.2:1b | 5 / 60 | 1.8 | 78% / 556 MiB |
| smollm2:1.7b | 6 / 29 | 4.3 | 16% / 550 MiB |
| llama3.2:3b | 7 / 56 | 3.9 | 14% / 508 MiB |
| qwen3:4b-instruct | 6 / 50 | 3.7 | 27% / 513 MiB |
| gemma4:12b-it-qat | 4 / 72 | 7.6 | 93% / 516 MiB |

Notes: Ollama CPU% sums all ollama processes via `ps` (100% = one core); generation
runs on the Metal GPU which `ps` cannot see. RSS = weights + KV cache (larger under
v2.1's 8k context). Correctness/hallucination: `model_comparison.md`; config-behavior
analysis: `config_impact.md`.
