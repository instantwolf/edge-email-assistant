# Research — Small-Model Agentic Reliability

Literature backing for this project's evaluation approach. This folder collects the papers
behind the benchmark score matrices below, grouped by theme; the project itself (see the
[root README](../README.md)) is an instance of the research question: a local SLM agent
performing real Gmail / Calendar / Tasks write actions, verified against the Google APIs
rather than against the model's own claims.

## Core research question

> **Small-model agentic reliability** — how do small language models (SLMs, ~1B–14B) perform
> on **single and multi tool calls**, considering also **end-to-end honesty** (exclusion of
> hallucinated or fabricated actions), on **real productivity tasks** (email, calendar, tasks)?

Three dimensions follow from this question, and the matrices and paper groups below mirror them:

1. **Single-turn function calling** — can the model produce one correct call?
2. **Multi-turn / stateful / agentic tool calling** — can it chain calls across a conversation with state?
3. **Tool-use honesty** — does it fabricate calls or results it never executed?

## Related state of the art: function-calling / agent benchmarks

| Benchmark | What it is | Official resource |
|---|---|---|
| **BFCL** (Berkeley Function Calling Leaderboard) | The de-facto standard function-calling leaderboard from the UC Berkeley Gorilla team. v1/v2 grade **single-turn** calls via AST matching (name, arguments, ordering, abstention); v3 adds **multi-turn / multi-step** calling with **state-based evaluation** (the system state after execution is verified — the same principle as this project's API-diff); v4 extends to holistic agentic evaluation. | [gorilla.cs.berkeley.edu/leaderboard.html](https://gorilla.cs.berkeley.edu/leaderboard.html) · [BFCL v3 blog](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html) · [paper (PMLR v267)](https://proceedings.mlr.press/v267/patil25a.html) |
| **τ-bench** (Sierra) | Benchmark for **tool-agent-user interaction**: the agent talks to a simulated user while operating tools over a stateful database (retail / airline domains). Success is graded by comparing the **final database state** to an annotated goal state — never the agent's textual claim — and the **pass^k** metric measures reliability over repeated trials. Successor **τ²-bench** adds a dual-control telecom domain where user and agent both act. | [github.com/sierra-research/tau-bench](https://github.com/sierra-research/tau-bench) · [τ²-bench](https://github.com/sierra-research/tau2-bench) · [arXiv 2406.12045](https://arxiv.org/abs/2406.12045) |
| **ToolBench** (ToolLLM) | Large-scale tool-use benchmark and training corpus built from **16,000+ real-world REST APIs** (RapidAPI), with single- and multi-tool instructions and the ToolEval evaluator (LLM-as-judge — a known reliability caveat). Origin of the ToolLLaMA models. | [github.com/OpenBMB/ToolBench](https://github.com/OpenBMB/ToolBench) · [arXiv 2307.16789](https://arxiv.org/abs/2307.16789) |
| **AgentBench** (THUDM) | First broad **LLM-as-agent** benchmark: 8 interactive environments (OS, database, knowledge graph, card game, puzzles, household, web shopping, web browsing) testing multi-turn decision-making beyond pure function calling. Documented a large frontier-vs-open-weight gap. | [github.com/THUDM/AgentBench](https://github.com/THUDM/AgentBench) · [arXiv 2308.03688](https://arxiv.org/abs/2308.03688) |

Adjacent benchmarks that sharpen the picture (all in [`01-benchmarks-function-calling-agents/`](01-benchmarks-function-calling-agents/)):
**API-Bank** (single + retrieve-and-call over 2,138 APIs), **ToolSandbox** (stateful conversational
tool use with an LLM user simulator), **AppWorld** (9 apps / 457 APIs with **hash-based DB diffing**
that also catches unintended side effects), **ComplexFuncBench** (multi-step, constrained,
long-context calling).

## Score matrices — SLM results across the three dimensions

Compiled from the primary papers; every cell is traceable to a source. **How to read:**

- Scores are **not cross-comparable across benchmarks** (different metrics). Compare within a column.
- **BFCL is version-sensitive** — `(v1)`/`(v2)` mark versions; unmarked BFCL figures are **v3**. The live board is v4; none of these numbers are v4.
- `—` = not tested / no primary number. `*` = flagged provenance (third-party re-evaluation, figure-only, or aggregator — verify against the primary PDF in this folder before citing). Higher is better everywhere.

### Matrix 1 — BFCL: SLM scores

| Model | Params | Non-live (single-turn) | Live (single-turn) | Multi-turn (v3) | Overall | Source |
|---|---|---|---|---|---|---|
| **xLAM-2-1b-fc-r** | 1B | — | — | 43.12 | — | arXiv 2504.03601 (T1) |
| **xLAM-2-3b-fc-r** | 3B | 88.22 | 81.03 | 56.00 | 65.74 | 2504.03601 (MT); 2511.22138 (rest) |
| **xLAM-2-8b-fc-r** | 8B | — | — | 69.25 | — | arXiv 2504.03601 (T1) |
| **xLAM-1b-fc-r** | 1.35B | — | — | — | 78.94 (v1) / 75.43 (v2) | arXiv 2409.03215 |
| **xLAM-7b-fc-r** | 7B | — | — | — | 88.24 (v1) | arXiv 2409.03215 |
| **ToolACE-8B** | 8B | 87.54* | 78.59* | 7.75* | 58.42* | 2409.00920 (v2 SOTA); recompute: Tool Zero (EMNLP-F 2025) |
| **Hammer2.1-7B** | 7B | 88.65 | 75.11 | 23.50 | 61.83 | 2410.04587; recompute in 2505.00024 |
| **Hammer2.1-3B** | 3B | — | — | — | ~45.0* | 2410.04587 (figure-only) |
| **Tool-N1-7B** | 7B | 89.25 | 80.38 | — | — | arXiv 2505.00024 (T3) |
| **Tool-N1-14B** | 14B | 90.52 | 81.42 | — | — | arXiv 2505.00024 (T3) |
| **Magnet-14B-mDPO** | 14B | — | — | 37.88 | 68.01 | arXiv 2503.07826 (T2) |
| **Gorilla-OpenFunctions-v2** | ~7B | — | — | — | 79.1 | 2410.04587 (T1, as baseline) |
| **Qwen3-4B** (prompt) | 4B | 82.58 | 75.52 | 35.25 | 62.04 | arXiv 2511.22138 (T1) |
| **Qwen3-1.7B** (prompt) | 1.7B | — | — | 16.88 | 55.49 | arXiv 2511.22138 (T1) |
| **Qwen3-0.6B** (prompt) | 0.6B | — | — | 1.38 | 45.76 | arXiv 2511.22138 (T1) |
| *ref:* GPT-4o-2024-11-20 | — | 88.10 | 79.83 | 47.62 | 72.08 | Tool Zero (T3) |
| *ref:* GPT-4o-mini | — | — | — | — | 64.10 | Tool Zero (T3) |
| *ref:* GPT-3.5-Turbo-0125 | — | — | — | — | 53.91 | Tool Zero (T3) |
| *ref:* xLAM-2-70b-fc-r | 70B | — | — | 75.12 | 78.19 | arXiv 2504.03601 (T1) |

**Single→multi cliff (the headline pattern):** strong 7–8B models reach mid-to-high-80s on
single-turn AST but collapse on v3 multi-turn — ToolACE-8B 7.75\*, Hammer2.1-7B 23.50,
Qwen3-1.7B 16.88, Qwen3-0.6B 1.38. Only dedicated multi-turn training closes the gap
(xLAM-2-8b 69.25). Even GPT-4o sits at 47.62 multi-turn.

### Matrix 2 — Cross-benchmark SLM scores (non-BFCL)

All stateful / multi-turn / agentic except API-Bank (single + retrieve-and-call).

| Benchmark (version) | Metric | Model | Params | Score | Frontier ref | Source |
|---|---|---|---|---|---|---|
| **τ²-bench** | avg (airline / retail / telecom) | Simia-Tau (Qwen3-8B) | 8B | **49.3** (46.7 / 51.9 / —) | GPT-4.1 ~65; GPT-4o ~44 | arXiv 2511.01824 (T1) |
| τ²-bench | avg | Simia-tau-RL (Qwen3-8B) | 8B | — (49.0 / 52.9 / —) | — | arXiv 2511.01824 |
| τ²-bench | avg | xLAM-2-8B (baseline) | 8B | 44.7 | — | arXiv 2511.01824 (T1) |
| **ToolSandbox** | avg similarity (0–100) | Hermes-2-Pro-Mistral-7B | 7B | **31.4** (ST 63.3 / MT 18.3) | GPT-4o 73.0 | arXiv 2408.04682 (T5) |
| ToolSandbox | avg similarity | Mistral-7B-Instruct-v0.3 | 7B | 29.8 (ST 48.1 / MT 9.5) | — | arXiv 2408.04682 (T5) |
| ToolSandbox | avg similarity | Gorilla-Openfunctions-v2 | ~7B | 25.6 | — | arXiv 2408.04682 (T5) |
| **AppWorld** | TGC (Test-Normal / Test-Challenge) | FullCodeRefl + LLaMA-3-70B *(best open)* | 70B | 24.4 / 7.0 | GPT-4o ReAct 48.8 / 30.2 | arXiv 2407.18901 (T3) |
| AppWorld | TGC (Test-Normal) | Qwen3-8B (raw) | 8B | 5.4\* (3.0\* AWQ) | — | 2604.11465\* (secondary) |
| **ComplexFuncBench** | success rate | GLM-4-9B *(best <10B)* | 9B | **8.4** | Claude-3.5-Sonnet 61.0; GPT-4o 60.5 | arXiv 2501.10132 (T2) |
| **API-Bank** | Call acc / Total | Lynx (Alpaca-7B trained on API-Bank) | 7B | **49.87 / 39.58** | GPT-3.5 59.40 / 47.16 | arXiv 2304.08244 (T3) |
| API-Bank | Call acc | Alpaca-7B | 7B | 24.06 | — | arXiv 2304.08244 (T3) |
| API-Bank | Call acc | ChatGLM-6B | 6B | 23.62 | — | arXiv 2304.08244 (T3) |

### Matrix 3 — Tool-use honesty / hallucination

The dimension closest to "does the model fabricate actions it didn't perform" — and the one
with the **thinnest SLM coverage**; these benchmarks mostly evaluate the effect across model
families rather than publishing a 1B–14B leaderboard.

| Benchmark | Metric | SLM entry | Params | Score | Frontier ref | Source | Note |
|---|---|---|---|---|---|---|---|
| **ToolBeHonest (ToolBH)** | total honesty (/100) | Llama-3-8B | 8B | "> Llama-2-70B"* | Gemini-1.5-Pro 45.3; GPT-4o 37.0 | arXiv 2406.20015 | Exact SLM number not isolable from snapshot — pull from paper table |
| **SimpleToolHalluBench** | hallucination-vs-capability trade-off | (family-level) | — | — | — | arXiv 2510.22977 | Finding: stronger reasoning *increases* tool hallucination; no per-SLM leaderboard |
| **AgentHallu** | step-localization accuracy | (best judge model) | — | 41.1% overall; tool-use sub-category 11.6% | — | arXiv 2601.06818 | Judge-model eval, not SLM scoring; tool-use is the hardest sub-category |

Even the strongest frontier models score **well below 50/100** on ToolBH, and larger parameter
counts do **not** guarantee better honesty — the motivation for treating honesty as a separate axis.

### Matrix 4 — Tool-specialized SLMs & on-device / edge cost

TinyAgent uses **its own MacOS function-calling benchmark**, not BFCL — not comparable to Matrix 1.

| Model | Params | Headline metric | Score | Benchmark | Edge latency / memory | Source |
|---|---|---|---|---|---|---|
| **TinyAgent-1.1B** | 1.1B | success rate | 80.06% (80.35% @ 4-bit) | own MacOS FC | **2.9 s, 0.68 GB** (4-bit) | arXiv 2409.00608 (T2) |
| **TinyAgent-7B** | 7B | success rate | 84.95% | own MacOS FC | — | arXiv 2409.00608 (T2) |
| *ref:* GPT-4-Turbo | — | success rate | 79.08% | same task | 3.9 s | arXiv 2409.00608 (T2) |
| *ref:* GPT-3.5 | — | success rate | 65.04% | same task | — | arXiv 2409.00608 (T2) |
| xLAM-1b-fc-r ("tiny giant") | 1.35B | BFCL overall | 78.94 (v1) | BFCL | — | arXiv 2409.03215 |
| ToolACE-8B | 8B | BFCL (rivals GPT-4) | v2 SOTA | BFCL v2 | — | arXiv 2409.00920 |
| Hammer2.1-7B | 7B | BFCL overall | 61.83 | BFCL v3 | on-device focus (fig.) | arXiv 2410.04587 |
| Tool-N1-14B | 14B | BFCL (beats GPT-4o) | non-live 90.52 | BFCL v3 | — | arXiv 2505.00024 |
| Magnet-14B-mDPO | 14B | BFCL multi-turn | 37.88 | BFCL v3 | — | arXiv 2503.07826 |

**Provenance caveats (condensed):** BFCL version drift is the main trap — always cite version +
snapshot. Third-party recomputes are starred. τ-bench's official board is frozen (no 1B–14B
entries; SLM τ-scores exist only via τ²-bench). For xLAM-2-1b-fc-r, the model's own paper reports
43.12 multi-turn while the TinyLLM study reports 8.38 for the same model — a ~35-point
harness-sensitivity gap that is itself evidence of small-model tool-calling fragility.

## Papers in this folder

### [`01-benchmarks-function-calling-agents/`](01-benchmarks-function-calling-agents/) — how tool use is measured

| File | Paper |
|---|---|
| `bfcl_patil25a_pmlr-v267.pdf` | The Berkeley Function Calling Leaderboard (BFCL) — [PMLR v267](https://proceedings.mlr.press/v267/patil25a.html) |
| `2406.12045_tau-bench.pdf` | τ-bench: Tool-Agent-User Interaction in Real-World Domains — [arXiv](https://arxiv.org/abs/2406.12045) |
| `2506.07982_tau2-bench.pdf` | τ²-Bench: Conversational Agents in a Dual-Control Environment — [arXiv](https://arxiv.org/abs/2506.07982) |
| `2307.16789_toolllm-toolbench.pdf` | ToolLLM / ToolBench: Mastering 16000+ Real-world APIs — [arXiv](https://arxiv.org/abs/2307.16789) |
| `2308.03688_agentbench.pdf` | AgentBench: Evaluating LLMs as Agents — [arXiv](https://arxiv.org/abs/2308.03688) |
| `2304.08244_api-bank.pdf` | API-Bank: A Comprehensive Benchmark for Tool-Augmented LLMs — [arXiv](https://arxiv.org/abs/2304.08244) |
| `2408.04682_toolsandbox.pdf` | ToolSandbox: Stateful, Conversational, Interactive Evaluation — [arXiv](https://arxiv.org/abs/2408.04682) |
| `2407.18901_appworld.pdf` | AppWorld: A Controllable World of Apps and People — [arXiv](https://arxiv.org/abs/2407.18901) |
| `2501.10132_complexfuncbench.pdf` | ComplexFuncBench: Multi-Step & Constrained Function Calling — [arXiv](https://arxiv.org/abs/2501.10132) |

### [`02-honesty-hallucination/`](02-honesty-hallucination/) — the honesty axis

| File | Paper |
|---|---|
| `2406.20015_toolbehonest.pdf` | ToolBeHonest: Hallucination Diagnostic Benchmark for Tool-Augmented LLMs — [arXiv](https://arxiv.org/abs/2406.20015) |
| `2510.22977_reasoning-trap-simpletoolhallubench.pdf` | The Reasoning Trap (SimpleToolHalluBench): Enhancing Reasoning Amplifies Tool Hallucination — [arXiv](https://arxiv.org/abs/2510.22977) |
| `2601.06818_agenthallu.pdf` | AgentHallu: Automated Hallucination Attribution of LLM-based Agents — [arXiv](https://arxiv.org/abs/2601.06818) |

### [`03-slm-tool-models-edge/`](03-slm-tool-models-edge/) — small models built (or measured) for tool calling on the edge

| File | Paper |
|---|---|
| `2409.03215_xlam.pdf` | xLAM: A Family of Large Action Models — [arXiv](https://arxiv.org/abs/2409.03215) |
| `2406.18518_apigen.pdf` | APIGen: Verifiable & Diverse Function-Calling Datasets — [arXiv](https://arxiv.org/abs/2406.18518) |
| `2504.03601_apigen-mt-xlam2.pdf` | APIGen-MT / xLAM-2: Multi-Turn Data via Simulated Agent-Human Interplay — [arXiv](https://arxiv.org/abs/2504.03601) |
| `2409.00920_toolace.pdf` | ToolACE: Winning the Points of LLM Function Calling — [arXiv](https://arxiv.org/abs/2409.00920) |
| `2410.04587_hammer.pdf` | Hammer: Robust Function-Calling for On-Device LMs — [arXiv](https://arxiv.org/abs/2410.04587) |
| `2409.00608_tinyagent.pdf` | TinyAgent: Function Calling at the Edge — [arXiv](https://arxiv.org/abs/2409.00608) |
| `2505.00024_nemotron-tool-n1.pdf` | Nemotron-Research-Tool-N1: Tool-Using LMs with Reinforced Reasoning — [arXiv](https://arxiv.org/abs/2505.00024) |
| `2503.07826_magnet.pdf` | Magnet: Multi-turn Tool-use Data Synthesis & Distillation — [arXiv](https://arxiv.org/abs/2503.07826) |
| `2511.01824_simia-tau.pdf` | Simia-Tau: Simulating Environments for Agent Training — [arXiv](https://arxiv.org/abs/2511.01824) |
| `2511.22138_tinyllm.pdf` | TinyLLM: SLMs for Agentic Tasks on Edge Devices — [arXiv](https://arxiv.org/abs/2511.22138) |
| `2504.19277_small-models-big-tasks.pdf` | Small Models, Big Tasks: SLMs for Function Calling — [arXiv](https://arxiv.org/abs/2504.19277) |
