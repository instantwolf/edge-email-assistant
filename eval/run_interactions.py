#!/usr/bin/env python3
"""Replay the interaction script against the agent webhook and record timings.

    python3 eval/run_interactions.py --tag edge-llama32-1b
    python3 eval/run_interactions.py --tag cloud-phi3 --base-url http://VM_IP:5678

Results land in eval/results/ as a CSV summary and a JSONL of full responses.
Interactions sharing a sessionId run in file order, so memory-dependent prompts
see their prior context. Seed with seed/seed_mailbox.py first; on the personal
account, real inbox mail mixes in with the seeded mail.
"""
import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = "http://localhost:5678"
RESULTS_DIR = Path(__file__).parent / "results"


def call(base_url, session_id, message, timeout, path="assistant",
         model=None, num_ctx=None, num_predict=None):
    body = {"sessionId": session_id, "message": message}
    # Optional Ollama overrides read by the workflow node; omit any to keep its default.
    if model:
        body["model"] = model
    if num_ctx:
        body["numCtx"] = num_ctx
    if num_predict is not None:
        body["numPredict"] = num_predict
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base_url}/webhook/{path}", data=payload,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read() or b"{}")
            return time.monotonic() - t0, resp.status, body.get("output", ""), None
    except urllib.error.HTTPError as e:
        return time.monotonic() - t0, e.code, "", e.read().decode(errors="replace")[:500]
    except Exception as e:  # timeouts, connection errors
        return time.monotonic() - t0, 0, "", repr(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="run label, e.g. edge-llama32-1b")
    ap.add_argument("--base-url", default=DEFAULT_URL)
    ap.add_argument("--file", default=str(Path(__file__).parent / "interactions.json"))
    ap.add_argument("--limit", type=int, default=0, help="run only the first N interactions")
    ap.add_argument("--path", default="assistant", help="webhook path (e.g. assistant-mcp)")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--model", default=None,
                    help="per-request Ollama model override (body.model)")
    ap.add_argument("--num-ctx", type=int, default=None, dest="num_ctx",
                    help="per-request Ollama num_ctx override (body.numCtx), e.g. 4096")
    ap.add_argument("--num-predict", type=int, default=None, dest="num_predict",
                    help="per-request generated-token cap (body.numPredict), e.g. 256")
    args = ap.parse_args()

    interactions = json.loads(Path(args.file).read_text())
    if args.limit:
        interactions = interactions[: args.limit]

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = RESULTS_DIR / f"{args.tag}_{stamp}.csv"
    jsonl_path = RESULTS_DIR / f"{args.tag}_{stamp}.jsonl"

    rows = []
    with jsonl_path.open("w") as jf:
        for it in interactions:
            print(f"[{it['id']:>2}] {it['category']:<13} -> ", end="", flush=True)
            latency, status, output, error = call(
                args.base_url, it["sessionId"], it["message"], args.timeout, args.path,
                model=args.model, num_ctx=args.num_ctx, num_predict=args.num_predict)
            ok = status == 200 and not error
            print(f"{latency:6.1f}s  http={status}  {'ok' if ok else 'FAIL'}")
            row = {
                "id": it["id"], "category": it["category"], "sessionId": it["sessionId"],
                "latency_s": round(latency, 2), "http_status": status, "ok": ok,
                "response_chars": len(output),
            }
            rows.append(row)
            jf.write(json.dumps({**row, "message": it["message"],
                                 "model": args.model, "num_ctx": args.num_ctx,
                                 "num_predict": args.num_predict,
                                 "output": output, "error": error}) + "\n")

    with csv_path.open("w", newline="") as cf:
        w = csv.DictWriter(cf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n_ok = sum(r["ok"] for r in rows)
    lat = sorted(r["latency_s"] for r in rows)
    print(f"\n{n_ok}/{len(rows)} ok | latency min {lat[0]}s / median {lat[len(lat)//2]}s / max {lat[-1]}s")
    print(f"results: {csv_path}\n         {jsonl_path}")


if __name__ == "__main__":
    main()
