#!/usr/bin/env python3
"""Tool-selection behavior per evaluation run.

For each interaction, pull the tool nodes that actually executed from n8n's
execution database and score them against the expected set. Prints a per-model
matrix and writes eval/results/tool_selection.md.

Run from repo root: python3 eval/tool_selection.py
"""
import json
import subprocess
from pathlib import Path

# minimal tool set that counts as a correct answer, per interaction id
EXPECTED = {
    1: set(), 2: set(), 3: set(),               # no tool needed (date is injected)
    4: {"read_emails"}, 5: {"read_emails"},
    6: {"list_events"},
    7: {"read_emails", "create_event"},          # flagship: summarize + schedule
    8: {"read_emails", "create_task"},
    9: set(),                                    # answer from memory
    10: {"send_email"},
    11: {"create_event"},
    12: {"list_tasks"},
}
TOOL_NODES = ["read_emails", "send_email", "list_events", "create_event",
              "create_task", "list_tasks", "current_datetime", "google_tools_mcp"]

# tag -> (workflowId, startedAt window UTC); windows come from
# eval/results/run_windows.txt (written by run_all_models.sh).
RUNS = [
    ("edge-llama32-1b-r2",  "EmailCalAssist01",  "2026-07-06 21:24:56", "2026-07-06 21:27:45"),
    ("edge-llama32-3b-r2",  "EmailCalAssist01",  "2026-07-06 21:27:45", "2026-07-06 21:30:35"),
    ("edge-qwen3-4b-r2",    "EmailCalAssist01",  "2026-07-06 21:30:35", "2026-07-06 21:33:36"),
    ("edge-smollm2-17b-r2", "EmailCalAssist01",  "2026-07-06 21:33:36", "2026-07-06 21:38:23"),
    ("edge-gemma4-12b-r2",  "EmailCalAssist01",  "2026-07-06 21:38:23", "2026-07-06 21:49:10"),
]

NODE_SCRIPT = r"""
const { DatabaseSync } = require('node:sqlite');
const flatted = require(require.resolve('flatted', { paths: ['/usr/local/lib/node_modules/n8n'] }));
const db = new DatabaseSync('/home/node/.n8n/database.sqlite', { readOnly: true });
const [wf, from, to] = process.argv.slice(1);
const exs = db.prepare("SELECT id, status, \"startedAt\", \"stoppedAt\" FROM execution_entity WHERE \"workflowId\" = ? AND \"startedAt\" >= ? AND \"startedAt\" < ? ORDER BY id").all(wf, from, to);
const out = [];
for (const ex of exs) {
  const row = db.prepare('SELECT data FROM execution_data WHERE "executionId" = ?').get(ex.id);
  const dur = (new Date(ex.stoppedAt + 'Z') - new Date(ex.startedAt + 'Z')) / 1000;
  if (!row) { out.push({ id: ex.id, status: ex.status, dur, tools: [] }); continue; }
  let data; try { data = flatted.parse(row.data.toString()); } catch { continue; }
  const rd = data.resultData?.runData || {};
  out.push({ id: ex.id, status: ex.status, dur, tools: Object.keys(rd) });
}
console.log(JSON.stringify(out));
"""


def executions(wf, frm, to):
    r = subprocess.run(["docker", "compose", "exec", "-T", "n8n", "node", "-e", NODE_SCRIPT,
                        "--", wf, frm, to], capture_output=True, text=True, timeout=120)
    return json.loads(r.stdout.strip().splitlines()[-1])


def match_to_harness(exs, tag):
    """Match executions to interactions by comparing durations to the run CSV.

    Tolerant of stray executions (e.g. manual UI tests) that fell inside the
    window: for each harness latency, take the next execution in id order whose
    duration is within tolerance.
    """
    import csv
    import glob
    f = sorted(glob.glob(f"eval/results/{tag}_2*.csv"))[-1]
    latencies = [float(r["latency_s"]) for r in csv.DictReader(open(f))]
    matched, pool = [], list(exs)
    for lat in latencies:
        pick = next((e for e in pool if abs(e["dur"] - lat) <= 1.5), None)
        if pick is None:                       # timeouts (harness 300 s, exec keeps running)
            pick = next((e for e in pool if e["dur"] >= 290), None)
        matched.append(pick)
        if pick:
            pool.remove(pick)
    return matched


def score(expected, called):
    called = set(called)
    if not expected:
        return "clean" if not called - {"current_datetime"} else f"unneeded:{','.join(sorted(called - {'current_datetime'}))}"
    if expected <= called:
        extra = called - expected - {"current_datetime"}
        return "correct" + (f"+extra:{','.join(sorted(extra))}" if extra else "")
    if called & expected:
        return f"partial (missing {','.join(sorted(expected - called))})"
    if called - {"current_datetime"}:
        return f"wrong ({','.join(sorted(called - {'current_datetime'}))})"
    return "none called"


def main():
    lines = ["# Tool-Selection Behavior per Model (from n8n execution data)\n",
             "Called tools per interaction, scored against the minimal expected set.",
             "'clean' = no-tool interaction answered without tools; datetime calls are not penalized.",
             "Note: runs predate the v2.1 numCtx fix — #12 failures for qwen3 were context overflow, not selection.\n"]
    summary = {}
    for tag, wf, frm, to in RUNS:
        exs = executions(wf, frm, to)
        matched = match_to_harness(exs, tag)
        n_matched = sum(1 for m in matched if m)
        lines.append(f"\n## {tag}  ({len(exs)} executions in window, {n_matched}/12 matched to harness by duration)\n")
        lines.append("| # | expected | called | verdict |")
        lines.append("|---|---|---|---|")
        good = 0
        for i, ex in enumerate(matched, start=1):
            if ex is None:
                lines.append(f"| {i} | {', '.join(sorted(EXPECTED[i])) or '—'} | ? | unmatched (no execution recorded) |")
                continue
            called = [t for t in ex["tools"] if t in TOOL_NODES]
            verdict = score(EXPECTED[i], called)
            if ex["status"] != "success":
                verdict += " [workflow-error]"
            if verdict.startswith(("correct", "clean")):
                good += 1
            lines.append(f"| {i} | {', '.join(sorted(EXPECTED[i])) or '—'} | {', '.join(called) or '—'} | {verdict} |")
        summary[tag] = f"{good}/12"
        lines.append(f"\n**Selection score: {good}/12**")

    lines.append("\n## Summary\n")
    lines.append("| Model | correct/clean selections |")
    lines.append("|---|---|")
    for tag, s in summary.items():
        lines.append(f"| {tag} | {s} |")

    out = Path(__file__).parent / "results" / "tool_selection.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[-10:]))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
