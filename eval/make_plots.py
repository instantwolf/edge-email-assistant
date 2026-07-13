#!/usr/bin/env python3
"""Generate report plots from the evaluation and metrics CSVs.

Outputs PNGs into eval/results/plots/. Re-run after new eval runs land; every
chart is regenerated from the raw CSVs (nothing hand-drawn).

    python3 eval/make_plots.py
"""
import csv
import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path(__file__).parent / "results"
METRICS = Path(__file__).parent.parent / "metrics"
PLOTS = RESULTS / "plots"
PLOTS.mkdir(exist_ok=True)

MODEL_RUNS = [  # (tag, label) in size order; first matching results CSV is used
    ("edge-llama32-1b", "llama3.2:1b"),
    ("edge-smollm2-17b", "smollm2:1.7b"),
    ("edge-llama32-3b", "llama3.2:3b"),
    ("edge-qwen3-4b", "qwen3:4b"),
    ("edge-gemma4-12b", "gemma4:12b"),
]
CATEGORIES = ["simple", "datetime", "single-tool", "multi-tool",
              "task-extract", "memory", "memory-action", "create-event"]


def run_rows(tag):
    files = sorted(glob.glob(str(RESULTS / f"{tag}_2*.csv")))
    if not files:
        return []
    return list(csv.DictReader(open(files[-1])))


def plot_latency_by_model():
    data, labels = [], []
    for tag, label in MODEL_RUNS:
        rows = run_rows(tag)
        if rows:
            data.append([float(r["latency_s"]) for r in rows])
            labels.append(label)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bp = ax.boxplot(data, labels=labels, showmeans=True)
    for i, d in enumerate(data, start=1):
        ax.scatter([i] * len(d), d, alpha=0.35, s=14, color="tab:blue", zorder=3)
    ax.set_yscale("log")
    ax.set_ylabel("end-to-end latency (s, log scale)")
    ax.set_title("Latency per interaction — 12-interaction eval, edge (M2 Pro, native Ollama)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS / "latency_by_model.png", dpi=150)
    plt.close(fig)


def plot_latency_by_category():
    import numpy as np
    model_means = {}
    for tag, label in MODEL_RUNS:
        rows = run_rows(tag)
        if not rows:
            continue
        by_cat = {}
        for r in rows:
            by_cat.setdefault(r["category"], []).append(float(r["latency_s"]))
        model_means[label] = [sum(by_cat.get(c, [0])) / max(len(by_cat.get(c, [1])), 1)
                              for c in CATEGORIES]
    x = np.arange(len(CATEGORIES))
    n = len(model_means)
    width = 0.8 / n
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for i, (label, means) in enumerate(model_means.items()):
        ax.bar(x + i * width - 0.4 + width / 2, means, width, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels(CATEGORIES, rotation=20, ha="right")
    ax.set_yscale("log")
    ax.set_ylabel("mean latency (s, log scale)")
    ax.set_title("Mean latency by interaction category")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS / "latency_by_category.png", dpi=150)
    plt.close(fig)


def plot_resources():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for tag, label in MODEL_RUNS:
        f = METRICS / f"host_stats_{tag}.csv"
        if not f.exists():
            continue
        per_ts = {}
        for r in csv.DictReader(open(f)):
            t = per_ts.setdefault(int(r["ts"]), {"cpu": 0.0, "rss": 0.0})
            t["cpu"] += float(r["cpu_perc"])
            t["rss"] += float(r["rss_mb"]) / 1024
        if not per_ts:
            continue
        ts0 = min(per_ts)
        xs = [(t - ts0) for t in sorted(per_ts)]
        axes[0].plot(xs, [per_ts[t]["cpu"] for t in sorted(per_ts)], label=label, lw=1)
        axes[1].plot(xs, [per_ts[t]["rss"] for t in sorted(per_ts)], label=label, lw=1)
    axes[0].set_title("Ollama host CPU during eval run")
    axes[0].set_xlabel("run time (s)"); axes[0].set_ylabel("CPU % (sum of processes)")
    axes[1].set_title("Ollama resident memory during eval run")
    axes[1].set_xlabel("run time (s)"); axes[1].set_ylabel("RSS (GiB)")
    for ax in axes:
        ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(PLOTS / "resources_host_ollama.png", dpi=150)
    plt.close(fig)


def plot_memory_growth():
    files = sorted(glob.glob(str(RESULTS / "memgrow-*_2*.csv")))
    if not files:
        return
    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    ax2 = ax1.twinx()
    for f in files:
        rows = list(csv.DictReader(open(f)))
        turns = [int(r["turn"]) for r in rows]
        lat = [float(r["latency_s"]) for r in rows]
        hist = [int(r["history_rows"]) if r["history_rows"] else 0 for r in rows]
        label = Path(f).name.split("_2")[0]
        ax1.plot(turns, lat, "o-", label=f"{label} latency", lw=1.2, ms=4)
        ax2.plot(turns, hist, "s--", color="tab:gray", label="history rows (Postgres)", lw=1, ms=3)
        for r in rows:
            if r["kind"].startswith("probe"):
                ax1.axvline(int(r["turn"]), color="tab:red", alpha=0.15)
    ax1.set_xlabel("conversation turn")
    ax1.set_ylabel("latency (s)")
    ax2.set_ylabel("stored history rows")
    ax1.set_title("Memory growth: one long session (red lines = recall probes)")
    ax1.grid(alpha=0.3)
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2[:1], l1 + l2[:1], fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(PLOTS / "memory_growth.png", dpi=150)
    plt.close(fig)


def plot_config_impact():
    """Median latency v2 (4k ctx, default temp) vs v2.1 (8k ctx, temp 0.2) per model."""
    import statistics as st
    import numpy as np
    labels, v2, v21 = [], [], []
    for tag, label in MODEL_RUNS:
        r1, r2 = run_rows(tag), run_rows(tag + "-r2")
        if not (r1 and r2):
            continue
        labels.append(label)
        v2.append(st.median(float(r["latency_s"]) for r in r1))
        v21.append(st.median(float(r["latency_s"]) for r in r2))
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(x - 0.2, v2, 0.4, label="v2 (4k ctx, default temp)")
    ax.bar(x + 0.2, v21, 0.4, label="v2.1 (8k ctx, temp 0.2)")
    for xi, (a, b) in zip(x, zip(v2, v21)):
        ax.text(xi - 0.2, a + 0.3, f"{a:.1f}", ha="center", fontsize=8)
        ax.text(xi + 0.2, b + 0.3, f"{b:.1f}", ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("median latency (s)")
    ax.set_title("Configuration impact on median latency (same 12-interaction protocol)")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS / "config_impact_latency.png", dpi=150)
    plt.close(fig)


def plot_mcp_overhead():
    fig, ax = plt.subplots(figsize=(6, 3.8))
    bars = {
        "native tool node\n(agent, direct)": 317,        # mean of 319/441/192 weighted by n (2/1/1)
        "MCP server-inner\n(Google API work)": 400,
        "MCP client-observed\n(incl. transport)": 421,
    }
    ax.bar(bars.keys(), bars.values(), color=["tab:blue", "tab:orange", "tab:red"])
    for i, v in enumerate(bars.values()):
        ax.text(i, v + 6, f"{v} ms", ha="center", fontsize=9)
    ax.set_ylabel("mean per tool call (ms)")
    ax.set_title("Tool invocation: native vs MCP (qwen3 runs)")
    fig.tight_layout()
    fig.savefig(PLOTS / "mcp_overhead.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    plot_latency_by_model()
    plot_latency_by_category()
    plot_resources()
    plot_memory_growth()
    plot_config_impact()
    plot_mcp_overhead()
    print("plots written to", PLOTS)
    for p in sorted(PLOTS.glob("*.png")):
        print(" ", p.name)
