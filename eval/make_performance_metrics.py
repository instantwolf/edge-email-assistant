#!/usr/bin/env python3
"""Regenerate eval/results/performance_metrics.md (or _<machine>.md) from raw run data.

Machine-parameterized: pass --machine <name> to report a box other than the M2 edge
baseline. Result tags are <machine>-<short>-r2; cold-load + gen tok/s are read per run
from metrics/warmup_<tag>.csv (written by run_model_eval.sh) since they differ by
hardware, falling back to the edge baseline constants when no file is present.

Run from repo root:
  python3 eval/make_performance_metrics.py                       # edge (M2) default
  python3 eval/make_performance_metrics.py --machine rtx3080 --hardware "Win11, RTX 3080 10GB, CUDA"

Add a model = add one line to MODELS (+ pull it + run it in run_all_models.sh).
"""
import argparse
import csv
import glob
import statistics as st
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
METRICS = Path(__file__).parent.parent / "metrics"
MACHINE = "edge"   # set from --machine in main(); tags are <MACHINE>-<short>[-r2]

# (label, short, disk GB, fallback cold-load s, fallback gen tok/s)
# Fallbacks are the M2/edge baseline; a metrics/warmup_<tag>.csv from any real run
# overrides them per machine.
MODELS = [
    ("llama3.2:1b",       "llama32-1b",  1.3,  1.5, 136.3),
    ("smollm2:1.7b",      "smollm2-17b", 1.8,  1.6,  77.4),
    ("llama3.2:3b",       "llama32-3b",  2.0,  2.6,  63.2),
    ("qwen3:4b-instruct", "qwen3-4b",    2.6,  2.8,  52.8),
    ("gemma4:12b-it-qat", "gemma4-12b",  7.2, 10.3,  18.1),
    # ("gemma-e4b:q4",    "gemmae4b-q4", 0.0,  0.0,   0.0),   # uncomment when pulled + run
    # ("gemma-e4b:q8_0",  "gemmae4b-q8", 0.0,  0.0,   0.0),
]
CATEGORIES = ["simple", "datetime", "single-tool", "multi-tool",
              "task-extract", "memory", "memory-action", "create-event"]


def tag_v2(short):
    return f"{MACHINE}-{short}"


def tag_v21(short):
    return f"{MACHINE}-{short}-r2"


def rows_for(tag):
    files = sorted(glob.glob(str(RESULTS / f"{tag}_2*.csv")))
    return list(csv.DictReader(open(files[-1]))) if files else []


def lat_stats(rows):
    lat = sorted(float(r["latency_s"]) for r in rows)
    ok = sum(1 for r in rows if r["ok"] == "True")
    p90 = lat[max(0, round(0.9 * len(lat)) - 1)]
    return (f"{lat[0]:.1f} / {st.median(lat):.1f} / {st.mean(lat):.1f} / {p90:.1f} / {lat[-1]:.1f}",
            f"{ok}/{len(rows)}")


def mem_to_mib(s):
    s = s.strip()
    for suf, f in (("GiB", 1024), ("MiB", 1), ("KiB", 1 / 1024), ("GB", 953.7), ("MB", 0.9537)):
        if s.endswith(suf):
            return float(s[: -len(suf)]) * f
    return 0.0


def host_stats(tag):
    f = METRICS / f"host_stats_{tag}.csv"
    if not f.exists():
        return None
    per_ts = {}
    for r in csv.DictReader(open(f)):
        t = per_ts.setdefault(r["ts"], {"cpu": 0.0, "rss": 0.0})
        t["cpu"] += float(r["cpu_perc"]); t["rss"] += float(r["rss_mb"])
    if not per_ts:
        return None
    cpus = [v["cpu"] for v in per_ts.values()]
    rss = [v["rss"] for v in per_ts.values()]
    return st.mean(cpus), max(cpus), max(rss) / 1024


def docker_stats(tag):
    f = METRICS / f"stats_{tag}.csv"
    if not f.exists():
        return None
    n8n = [r for r in csv.DictReader(open(f)) if "n8n" in r["container"]]
    if not n8n:
        return None
    return max(float(r["cpu_perc"].rstrip("%")) for r in n8n), max(mem_to_mib(r["mem_used"]) for r in n8n)


def warmup(short, fb_load, fb_tok):
    """Cold-load s + gen tok/s from the per-run warm-up file, else the fallback constants."""
    f = METRICS / f"warmup_{tag_v21(short)}.csv"
    if f.exists():
        rows = list(csv.DictReader(open(f)))
        if rows:
            return float(rows[0]["load_s"]), float(rows[0]["gen_tok_s"])
    return fb_load, fb_tok


def latency_table(use_v21, title):
    out = [f"\n## Latency — {title} (min / median / mean / p90 / max, seconds)\n",
           "| Model | latency (s) | HTTP ok |", "|---|---|---|"]
    for label, short, *_ in MODELS:
        rows = rows_for(tag_v21(short) if use_v21 else tag_v2(short))
        if not rows:
            out.append(f"| {label} | (no run) | — |")
            continue
        stats, ok = lat_stats(rows)
        out.append(f"| {label} | {stats} | {ok} |")
    return out


def category_table(title):
    out = [f"\n## Latency by category — {title} (mean, seconds)\n"]
    names = [m[0] for m in MODELS]
    out.append("| Category | " + " | ".join(names) + " |")
    out.append("|---|" + "---|" * len(names))
    percat = {}
    for label, short, *_ in MODELS:
        for r in rows_for(tag_v21(short)):
            percat.setdefault(r["category"], {}).setdefault(label, []).append(float(r["latency_s"]))
    for cat in CATEGORIES:
        vals = [f"{st.mean(percat[cat][n]):.1f}" if n in percat.get(cat, {}) else "—" for n in names]
        out.append(f"| {cat} | " + " | ".join(vals) + " |")
    return out


def main():
    global MACHINE
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", default="edge", help="tag prefix / box name (default edge = M2)")
    ap.add_argument("--hardware", default=None, help="hardware string for the header (non-edge)")
    args = ap.parse_args()
    MACHINE = args.machine

    if MACHINE == "edge":
        lines = ["# Measured Performance Metrics per Model — Edge Deployment\n",
             "Hardware: Apple M2 Pro, 16 GiB unified memory. LLM runtime: **native Ollama 0.31.1** (Metal GPU).",
             "Orchestration: n8n 2.28.6 + PostgreSQL 16 in Docker (3 CPUs / 2.4 GiB allocated).",
             "Workload: 12-interaction script via production webhook; resources sampled every 2 s.",
             "Latency = wall clock webhook request → response (n8n + LLM turns + Google API).",
             "The v2.1 series was **refreshed 2026-07-06** under the current workflow with "
             "**single-model residency enforced** (`run_model_eval.sh` unloads any other model "
             "before each run, so no stray model contends for the 16 GiB host).",
             "",
             "Two configuration series:",
             "- **v2**: numCtx 4096 (Ollama default), default temperature — initial matrix",
             "- **v2.1**: numCtx 8192, temperature 0.2 — after the #12 context-overflow fix",
             "",
             "Raw data: `eval/results/<tag>_*.csv|.jsonl`, `metrics/*_<tag>.csv`.",
             "Regenerate with `python3 eval/make_performance_metrics.py`. Date: 2026-07-06."]
        show_v2 = True
        out = RESULTS / "performance_metrics.md"
    else:
        hw = args.hardware or "(set --hardware)"
        lines = [f"# Measured Performance Metrics per Model — {MACHINE}\n",
             f"Hardware: {hw}. LLM runtime: **native Ollama** (GPU).",
             "Orchestration: n8n 2.28.6 + PostgreSQL 16 in Docker.",
             "Workload: 12-interaction script via production webhook; resources sampled every 2 s.",
             "Latency = wall clock webhook request → response (n8n + LLM turns + Google API).",
             "Config: v2.1 (numCtx 8192, temperature 0.2), single-model residency enforced.",
             "",
             f"Raw data: `eval/results/{MACHINE}-*-r2_*.csv`, `metrics/*_{MACHINE}-*.csv`.",
             f"Regenerate with `python3 eval/make_performance_metrics.py --machine {MACHINE}`."]
        show_v2 = False
        out = RESULTS / f"performance_metrics_{MACHINE}.md"

    if show_v2:
        lines += latency_table(False, "v2 config")
    lines += latency_table(True, "v2.1 config (current)")
    lines += category_table("v2.1 config")

    lines += ["\n## Model loading & generation (native Ollama, warm-up)\n",
          "| Model | Disk | Cold load | Generation |", "|---|---|---|---|"]
    for label, short, disk, fb_load, fb_tok in MODELS:
        load, tps = warmup(short, fb_load, fb_tok)
        lines.append(f"| {label} | {disk} GB | {load} s | {tps} tok/s |")

    lines += ["\n## Resource utilization during the v2.1 runs\n",
          "| Model | Ollama CPU mean/peak (host %) | Ollama peak RSS (GiB) | n8n CPU peak / mem peak |",
          "|---|---|---|---|"]
    for label, short, *_ in MODELS:
        h = host_stats(tag_v21(short)) or host_stats(tag_v2(short))
        d = docker_stats(tag_v21(short)) or docker_stats(tag_v2(short))
        hcol = f"{h[0]:.0f} / {h[1]:.0f}" if h else "n/a"
        rcol = f"{h[2]:.1f}" if h else "n/a"
        dcol = f"{d[0]:.0f}% / {d[1]:.0f} MiB" if d else "n/a"
        lines.append(f"| {label} | {hcol} | {rcol} | {dcol} |")

    lines += ["\nNotes: Ollama CPU% sums all ollama processes via `ps` (100% = one core); generation",
          "runs on the Metal GPU which `ps` cannot see. RSS = weights + KV cache (larger under",
          "v2.1's 8k context). Correctness/hallucination: `model_comparison.md`; config-behavior",
          "analysis: `config_impact.md`."]

    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
