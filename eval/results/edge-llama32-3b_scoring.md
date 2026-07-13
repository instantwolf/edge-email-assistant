# Scoring: edge-llama32-3b (2026-07-06, run 20260706T091119Z)

Setup: llama3.2:3b, native Ollama (M2 Pro/Metal), v2 prompt, 15 seeded emails + 3 seeded events.
Side effects verified against the Google APIs (pre/post state diff) — NOT against agent claims.

**Latency: 12/12 HTTP ok | min 0.9 s / median 9.5 s / max 12.7 s**

| # | Category | Latency | Verdict | Notes |
|---|---|---|---|---|
| 1 | simple | 9.9 s | ok (minor) | capability answer over-focused on tasks |
| 2 | simple | 7.4 s | correct | |
| 3 | datetime | 0.9 s | correct | answered from injected date, no tool turn |
| 4 | single-tool (read) | 10.5 s | correct | summaries match seeded ground truth |
| 5 | single-tool (read) | 9.4 s | correct | unread senders/subjects match seeds |
| 6 | single-tool (read) | 10.8 s | partially correct | all events found; grouped under wrong weekday headers |
| 7 | multi-tool | 12.7 s | partially correct | emails summarized ✓; **no meetings scheduled** (0 events created) |
| 8 | task-extract | 9.5 s | **hallucinated action** | claims 3 tasks saved; **0 tasks created** (API-verified) |
| 9 | memory | 2.3 s | **format failure** | raw tool-call JSON emitted as the answer |
| 10 | memory-action | 3.1 s | **hallucinated action** | claims reply sent to Anna; **sent folder empty** (API-verified) |
| 11 | create-event | 3.2 s | partially correct | event really created ✓ but on Wednesday instead of Friday |
| 12 | single-tool (read) | 10.5 s | correct | lists real open tasks |

**Aggregate:** 5 correct / 3 partially correct / 2 hallucinated actions / 1 format failure / 1 minor.
Read operations: reliable. Write operations: **0 of 4 write intents fully correct** —
the model either skips the tool and claims success (8, 10), executes with wrong
arguments (11: wrong day), or silently drops half the request (7).

Key finding for the report: **llama3.2:3b's hallucination problem is concentrated on
actions, not facts** — summaries were accurate, but "I did X" statements were false
in 2 of 4 cases. Latency is interactive (sub-13 s); correctness is the trade-off.
Follow-up runs (llama3.2:1b, smollm2:1.7b, qwen3:4b-instruct, gemma4:12b-it-qat) are
aggregated in `model_comparison.md` and `performance_metrics.md`.
