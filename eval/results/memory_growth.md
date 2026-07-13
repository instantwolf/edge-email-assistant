# Memory Growth Analysis

**Experiment (2026-07-06):** one 24-turn conversation in a single session
(`eval/memory_growth.py`, model gemma4:12b-it-qat, v2.1 config). Turns 1–7, 9–15, 17–23
feed numbered facts ("Remember item N: …"); turns 8, 16, 24 are recall probes.
Per turn: end-to-end latency + Postgres chat-history size.
Data: `memgrow-gemma4-12b_20260706T111415Z.csv`, plot: `plots/memory_growth.png`.

## Results

| Aspect | Observation |
|---|---|
| Latency vs history length | **Flat.** Fact turns oscillate 6–15 s independent of history (first-5 avg 14.3 s incl. semi-cold start; last-5 avg 7.8 s). No growth trend. |
| Storage growth | **Linear**, 2 rows/turn → 48 rows after 24 turns. Postgres stores the full transcript. |
| Recall at turn 8 | Item 1 (turn 1) **already forgotten**: "You haven't provided item 1 in our conversation yet." |
| Recall at turn 16 | Same: "Item 1 was not mentioned in our conversation." |
| Final probe (turn 24) | "You asked me to remember **5 items (17, 18, 19, 20, 21)**" — the model literally sees exactly the last 5 interactions. |
| Probe latency | Probes cost 28–33 s vs 6–15 s for facts — longer generated answers, not longer context. |

## Interpretation

1. The n8n **Postgres Chat Memory node defaults to `contextWindowLength = 5`**: the full
   history is *persisted*, but only the last 5 interactions are passed to the model.
   The final probe's answer ("5 items: 17–21") is a perfect empirical fingerprint of
   this window.
2. **Consequence — bounded latency, bounded recall.** Latency does not grow with
   conversation length precisely *because* recall is capped. "Persistent memory"
   (course requirement) is satisfied at the storage layer (sessions survive restarts,
   transcripts are fully recoverable from Postgres), while *functional* memory is a
   5-interaction sliding window.
3. **The trade-off is tunable**: raising `contextWindowLength` buys longer recall and
   costs prefill tokens per turn (~linear in window size) — on a 12B at ~200 tok/s
   prefill, each additional remembered exchange costs roughly 0.3–1 s per turn, and the
   8192-token context (v2.1) caps how far the window can be raised before overflow
   (the interaction-#12 context-overflow incident).
4. For the report: this reframes "memory growth" from "does latency degrade?" (no) to
   "where did the architecture spend the memory budget?" — storage grows unbounded,
   context stays constant, recall horizon is the sacrifice.
