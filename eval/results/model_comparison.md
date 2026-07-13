# Model Comparison — Edge (M2 Pro 16 GiB, native Ollama/Metal), 2026-07-06

Protocol per model: reset seeded ground truth (15 emails, 3 events) → clear chat memory →
switch workflow model → **unload any other model (single-model residency)** → warm-up →
12-interaction script (`eval/interactions.json`) with resource sampling → **side effects
verified via Google API pre/post diff** (never via agent claims) → artifacts cleaned.
Runner: `eval/run_model_eval.sh` (reproduce the matrix with `eval/run_all_models.sh`; see
`eval/README.md`).

> **This is the refreshed v2.1 series (2026-07-06):** current workflow, `numCtx 8192` +
> `temperature 0.2`, **single-model residency enforced** so no stray model contends for the
> 16 GiB host. Latency figures below are this refreshed run; qualitative rows (language
> quality, failure modes) are model-intrinsic and carry over — they reproduced.

## 1. Performance metrics (refreshed, single-model)

| Metric | llama3.2:1b | smollm2:1.7b | llama3.2:3b | qwen3:4b-instruct | gemma4:12b-it-qat |
|---|---|---|---|---|---|
| Disk size | 1.3 GB | 1.8 GB | 2.0 GB | 2.6 GB | 7.2 GB |
| Model load (cold) | 1.5 s | 1.6 s | 2.6 s | 2.8 s | 10.3 s |
| Generation speed | 136 tok/s | 77 tok/s | 63 tok/s | 53 tok/s | 18 tok/s |
| Latency min | 0.4 s | 0.3 s | 1.1 s | 0.4 s | 8.2 s |
| Latency median | 3.0 s | 10.9 s | 9.6 s | 10.3 s | 33.3 s |
| Latency max | 72.3 s | 48.7 s | 16.6 s | 22.8 s | 129.7 s |
| Run completion (HTTP ok) | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |

All five completed 12/12 this run (smollm2 previously produced 300 s runaways; capped at
120 s/request it finished, but see §2 — completion ≠ correctness). llama3.2:1b's 72 s max is
a single multi-tool outlier against a 3.0 s median.

## 2. Hallucination / correctness metrics (API-verified)

4 write intents per run: schedule meetings (#7), save tasks (#8), send reply (#10), create event (#11).

| Metric | llama3.2:1b | smollm2:1.7b | llama3.2:3b | qwen3:4b-instruct | gemma4:12b-it-qat |
|---|---|---|---|---|---|
| **Correct writes (of 4 intents)** | **0** | **0** | **0** | **1** | **3** |
| Events created / of them correct | 3 / 0 | 0 / 0 | 2 / 0 | 1 / 0 | 1 / 1 |
| Tasks created / of them correct | 0 / 0 | 0 / 0 | 1 / 0 (empty title) | 1 / 1 | 3 / 3 |
| Correct reply sent (#10) | no | no | no | no | **yes** (anna.mayer@…example) |
| Fabricated content (invented events) | 1 ("Google Tasks" event) | 0 | 0 | 0 | 0 |
| Wrong-parameter writes (e.g. wrong day) | 2 | 0 | 2 | 1 | 0 |
| "Friday" (=Jul 10) resolved to… | Tue Jul 7 | — | Thu Jul 9 | Thu Jul 9 | **Fri Jul 10 ✓** |
| Read accuracy vs seeded ground truth | low (mixed fabrication) | unusable | good | good | excellent |

Only gemma4 resolved "Friday" correctly and produced correct artifacts (event on the right
day, 3 well-formed tasks with due-times in the title, the reply sent to the correct
`.example` recipient). It missed #7's meetings-as-events (variance on the multi-write
flagship — it filed one as a task instead). Every model ≤4B produced wrong-day or junk
writes; qwen3's single correct task is its only clean write.

## 3. Language quality (subjective 1–5, from full transcripts — carried over, reproduced)

| Model | Score | Notes |
|---|---|---|
| llama3.2:1b | 2/5 | Rambling; tool-call JSON leaks into replies; echoes prompt scaffolding |
| smollm2:1.7b | 1/5 | `<tool_response>` template debris, unhelpful refusals ("cannot be answered") |
| llama3.2:3b | 3.5/5 | Mostly clear and structured; occasional meta-chatter and one JSON leak |
| qwen3:4b-instruct | 4.5/5 | Clean structure, concise, correct weekday labels, honest hedging |
| gemma4:12b-it-qat | 5/5 | Best formatting, complete and precise, honest about pending actions |

## Conclusions

1. **Speed and correctness trade off hard on 16 GiB edge hardware.** Only gemma4:12b acts
   reliably (3/4 correct writes, 0 fabricated actions) but at a 33 s median. Models ≤4B are
   1–13× faster yet effectively fail the write intents (wrong day, empty title, junk events).
2. **Hallucination concentrates on actions, not facts**: summaries were largely accurate
   while "I scheduled it" claims were false. Verifying against the Google APIs (not agent
   claims) is essential — it is what caught the small models' fake successes.
3. **Relative-date resolution is systematically broken in small models**: three sub-12B
   models put "Friday" on Tuesday or Thursday; only the 12B got Jul 10.
4. **Course-recommended ≠ agent-capable**: phi3/tinyllama/gemma:2b can't call tools at all;
   smollm2 completes the loop but writes nothing usable.
5. **Single-model residency matters on 16 GiB.** With it enforced, gemma4's median is 33 s
   (vs 38–50 s in earlier contended runs) — a stray resident model was inflating latency.
6. **Decision:** development default **gemma4:12b-it-qat** (reliability); **qwen3:4b-instruct**
   the documented low-latency alternative (~10 s median, best sub-12B quality, honest
   failures). Both are one `model` field away in the workflow.

---

## Addendum — configuration history (v2 → v2.1) and single-model refresh

Config **v2.1** = numCtx 8192 (fixes the #12 context overflow) + temperature 0.2.
**v3 prompt** = v2 + "never claim an action without a confirming tool result".

| Run | Config | ok | median | max | API-verified writes |
|---|---|---|---|---|---|
| qwen3 r1 | v2, 4k ctx | 11/12 | 10.0 s | 19.8 s | event **Thu** (wrong), 0 tasks; 2 false claims |
| qwen3 v3 | v2.1 + v3 prompt | 12/12 | 7.3 s | 18.8 s | event **Fri ✓**; false tool-action claims eliminated |
| gemma4 r1 | v2, 4k ctx | 12/12 | 38.1 s | 146.6 s | event **Fri ✓**, 2 tasks ✓, reply ✓ |
| gemma4 r2 | v2.1 (contended) | 12/12 | 49.5 s | 162.6 s | event **Fri ✓**, 4 tasks ✓, no send |
| **gemma4 (refresh)** | **v2.1, single-model** | **12/12** | **33.3 s** | **129.7 s** | event **Fri ✓**, 3 tasks ✓, reply ✓ |
| **qwen3 (refresh)** | **v2.1, single-model** | **12/12** | **10.3 s** | **22.8 s** | event **Thu** (wrong), 1 task ✓ |

Aggregated findings:
1. **The #12 failure was infrastructure, not model**: with numCtx 8192, all five complete 12/12.
2. **gemma4 write reliability is consistent, not lucky**: "Friday" correct in every run;
   real writes (tasks + reply + event) every run.
3. **The v3 action-honesty rule** eliminates false *tool-action* claims but not cross-turn
   *memory* fabrication (it cites conversation, not tool results).
4. **Config/latency trade-offs are measurable**: 8k context enlarges the KV cache; a stray
   second resident model inflates latency further (gemma4 49.5 → 33.3 s once enforced single).
