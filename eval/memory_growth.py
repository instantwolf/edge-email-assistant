#!/usr/bin/env python3
"""Memory-growth experiment over one long single-session conversation.

The agent is fed numbered facts ("Remember item N: ...") and probed for recall
at intervals. Each turn records end-to-end latency, the response, and the size
of the Postgres chat history (rows + table bytes). This exposes both the
latency-vs-history trend and the recall horizon: the n8n memory node forwards
only the last `contextWindowLength` interactions (default 5) even though
Postgres stores everything.

    python3 eval/memory_growth.py --tag memgrow-gemma4 [--turns 24] [--path assistant]
"""
import argparse
import csv
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FACTS = [
    "the blue box contains 17 screws",
    "the server room code is 4711",
    "Anna's office is room S.2.42",
    "the standup moved to 09:30",
    "the WiFi password is fedora-lampshade",
    "the invoice number is 4711",
    "the dentist is on Thursday at 16:15",
    "the library book is due in 3 days",
    "the project deadline is Friday 15:00",
    "the GPU machine has an RTX 3080",
    "the coffee machine needs descaling",
    "the backup runs at 02:00 nightly",
    "the meeting room projector needs HDMI",
    "the train to Vienna leaves at 07:12",
    "the license renewal costs 89 euros",
    "the docker volume is called n8n_data",
    "the printer toner is cyan-low",
    "the conference CFP closes July 20",
    "the parking spot is number 23",
    "the team lunch is at the Mensa",
]


def probe_indices(turns):
    return {8, 16, turns}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--turns", type=int, default=24)
    ap.add_argument("--base-url", default="http://localhost:5678")
    ap.add_argument("--path", default="assistant")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    session = f"{args.tag}-session"
    probes = probe_indices(args.turns)
    rows = []
    fact_i = 0

    for turn in range(1, args.turns + 1):
        if turn in probes:
            if turn == args.turns:
                msg = "Without using any tools: how many items did I ask you to remember, and what was item 1?"
                kind = "probe-final"
            else:
                msg = "Without using any tools: what exactly was item 1?"
                kind = "probe"
        else:
            fact = FACTS[fact_i % len(FACTS)]
            fact_i += 1
            msg = f"Remember item {fact_i}: {fact}. Reply with only: OK {fact_i}"
            kind = "fact"

        payload = json.dumps({"sessionId": session, "message": msg}).encode()
        req = urllib.request.Request(f"{args.base_url}/webhook/{args.path}", data=payload,
                                     headers={"Content-Type": "application/json"})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as resp:
                out = json.loads(resp.read() or b"{}").get("output", "")
                status = resp.status
        except Exception as e:
            out, status = repr(e), 0
        latency = time.monotonic() - t0

        q = (f"SELECT count(*) || ',' || pg_total_relation_size('n8n_chat_histories') "
             f"FROM n8n_chat_histories WHERE session_id = '{session}';")
        try:
            db = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "agent",
                                 "-d", "agent_memory", "-tA", "-c", q],
                                capture_output=True, text=True, timeout=30).stdout.strip()
            hist_rows, table_bytes = db.split(",") if "," in db else ("", "")
        except Exception:
            hist_rows, table_bytes = "", ""

        rows.append({"turn": turn, "kind": kind, "latency_s": round(latency, 2), "http": status,
                     "history_rows": hist_rows, "table_bytes": table_bytes,
                     "response": out[:400]})
        print(f"[{turn:>2}] {kind:<11} {latency:6.1f}s http={status} hist={hist_rows} | {out[:70].replace(chr(10),' ')}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_csv = Path(__file__).parent / "results" / f"{args.tag}_{stamp}.csv"
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    facts_lat = [r["latency_s"] for r in rows if r["kind"] == "fact"]
    print(f"\nfact-turn latency: first5 avg {sum(facts_lat[:5])/5:.1f}s | last5 avg {sum(facts_lat[-5:])/5:.1f}s")
    print(f"results: {out_csv}")


if __name__ == "__main__":
    main()
