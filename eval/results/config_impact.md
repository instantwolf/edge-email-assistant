# Configuration Impact: v2 → v2.1 (full 5-model re-run series)

**Question:** how did the v2.1 configuration change (numCtx 4096→8192 + temperature
default→0.2) affect latency and *behavior*? Both series use the identical 12-interaction
protocol with reseeded ground truth and API-verified side effects; v2.1 runs are tagged
`*-r2`. Plot: `plots/config_impact_latency.png`.

> **Correction (2026-07-06 refresh).** The v2.1 latency figures in the table below were
> measured **before single-model residency was enforced**, so they include contention from a
> stray resident model on the 16 GiB host. Re-measured under enforced single-model
> (`model_comparison.md`, `performance_metrics.md`), **gemma4's v2.1 median is 33.3 s, not
> 49.5 s** — and the isolated numCtx probe (`latency_budget.md`) shows 4k ≈ 8k on compute.
> So finding #4's "8k context costs ~30 % latency" was **mostly memory contention, not the KV
> cache**: at 8k *without* a stray model, gemma4 (33.3 s) is even faster than the v2 4k run
> (38.1 s). The behavioural findings below (write correctness, date resolution) are unaffected.

## Completion & latency

| Model | ok v2 → v2.1 | median v2 → v2.1 | Write side effects v2.1 (API-verified) |
|---|---|---|---|
| llama3.2:1b | 10/12 → **12/12** | 2.3 → 3.3 s | 2 events created, **both on wrong days** (today instead of Tue/Fri); 0 tasks |
| smollm2:1.7b | 6/12 → 9/12 | 10.1 → 10.3 s¹ | none (both series) — verdict unchanged: not agent-capable |
| llama3.2:3b | 12/12 → 12/12 | 9.5 → 9.0 s | event Thu (wrong day), task with **empty title**, **real email sent to a hallucinated recipient** (see below) |
| qwen3:4b-instruct | 11/12 → **12/12** | 10.0 → 9.7 s | event on Jul 16 labeled "Friday" (wrong), 0 tasks |
| gemma4:12b-it-qat | 12/12 → 12/12 | 38.1 → **49.5 s** | event **Friday ✓** (2/2 across series), **4 tasks, all titles/dates correct**; reply not sent (honest failure after failed retrieval) |

¹ smollm2 re-run used a 120 s per-request cap (vs 300 s) after three 300 s runaways in v2.

## Attribution: which knob did what

**numCtx 8192 → completion.** Every hard failure in the v2 series that we could trace was
a context overflow (`exceed_context_size_error`). With 8 k context: 1b 10→12, smollm2 6→9,
qwen3 11→12. Cost: larger KV cache (higher RSS; the 12B pays ~30 % median latency,
38→50 s). Small models barely pay because their absolute memory footprint is small.

**temperature 0.2 → conciseness, not correctness.** gemma4's read answers dropped to
a third of their length and doubled in speed (#4: 68→24 s, 612→205 chars; #7: 147→71 s)
— it finally obeys the 8-line cap. But determinism did **not** fix semantic failures:
qwen3 still fabricated three scheduled meetings in its memory answer at temp 0.2, still
mislabeled Jul 16 as "Friday"; 1b/3b still put events on wrong days. **Sampling noise was
never the cause of hallucination — capability is.**

**Behavior shifts are two-sided.** gemma4-r2 extracted 4 correct tasks (vs 2) but failed
to retrieve Anna's email (honest failure; r1 found it and replied) — lower temperature
narrows search-query diversity, which can hurt retrieval. Run-to-run variance remains
the dominant factor for write outcomes in models ≤4B.

## Finding: cross-context recipient reuse on a live SMTP path

In `edge-llama32-3b-r2`, the agent **sent a real, delivered email** titled "IoT Project
Update" to `you@example.com`. Initial classification as a "hallucinated
recipient" was **wrong**: the address had been provided by the user **in an earlier
manual test prompt** (outside the eval protocol). Its residue in the real mailbox
(sent mail/thread on the shared personal account) is how the eval agent encountered it —
and it then reused that address to satisfy a *different* request (the seeded Sabine
"status update" scenario), which the current conversation never authorized.

Two distinct lessons:

1. **Evaluation hygiene:** on a personal account, manual testing between runs leaks
   artifacts into the "sealed" eval world (this run's #7 also summarized a bounce from a
   previous run before cleanup learned to remove those). Ground-truth isolation on a
   shared mailbox is best-effort — a documented limitation of the keep-personal-account
   decision (§3.3 of the plan).
2. **Deployment guardrail still applies:** the agent chose a send target from unrelated
   context rather than the current request. Whether the address is invented or merely
   out-of-context, the mitigation is identical — recipient allowlists enforced at the
   tool level (not the prompt level), confirm-before-send flows, or draft-only mode.
   And only API-level verification caught it at all.

## Consequences for the evaluation series

- The **v2.1 series (`*-r2`) is now complete for all five models** and is the series the
  FrontEnd eval browser should be read against; the v2 series remains as the
  configuration-comparison baseline.
- `performance_metrics.md` now carries both series (regenerable via
  `eval/make_performance_metrics.py`); plots regenerable via `eval/make_plots.py`.
- Ranking unchanged in both series: gemma4:12b is the only reliable actor; qwen3:4b the
  best small model; smollm2 unusable. The config fix changed *completion*, not *ranking*.
