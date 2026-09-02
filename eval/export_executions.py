#!/usr/bin/env python3
"""Export n8n per-node execution data for one run (study-v3 task 2.4).

    python3 eval/export_executions.py <tag> [--since-id N]

The observation axis is read from n8n's per-node data — calls with arguments,
tool response status and error, per-node timestamps and durations, turn count,
raw generations, token usage (`study-v3/phase2-harness/lib/observation.py`).
n8n keeps that data in a SQLite file inside its Docker volume, so this copies
the file out after a run and records how many executions it holds.

**Why a copy and not the API:** the pilot archive was recovered exactly this
way, the decoder that reads it is already written and tested against it, and
this needs no API key, no n8n UI step, and no per-host setup. The cost is that
a copy of a live SQLite file can be torn, so the `-wal` and `-shm` sidecars are
copied too and the export is verified by opening it and counting rows. A
verification failure is reported, not swallowed.

**Run this before the next model switch.** `run_model_eval.sh` restarts n8n
between models, and n8n prunes execution data on boot unless retention is
disabled — the compose file now sets `EXECUTIONS_DATA_PRUNE=false` for exactly
this reason, but the export is still ordered before the restart so a
misconfigured host loses one run's traces rather than the campaign's.
"""
import argparse
import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"
CONTAINER_DB = "/home/node/.n8n/database.sqlite"


def compose_cp(remote, local):
    cmd = ["docker", "compose", "cp", f"n8n:{remote}", str(local)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or "").strip()


def export(tag, since_id=None):
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{tag}_executions.sqlite"
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="n8nexport-"))

    ok, err = compose_cp(CONTAINER_DB, tmp / "database.sqlite")
    if not ok:
        print(f"FAILED to copy {CONTAINER_DB}: {err}", file=sys.stderr)
        return None
    for sidecar in ("-wal", "-shm"):          # may legitimately not exist
        compose_cp(CONTAINER_DB + sidecar, tmp / f"database.sqlite{sidecar}")

    # Verify by opening it: a torn copy fails here rather than in Phase 4.
    try:
        db = sqlite3.connect(tmp / "database.sqlite")
        total = db.execute("SELECT count(*) FROM execution_entity").fetchone()[0]
        with_data = db.execute(
            "SELECT count(*) FROM execution_entity e JOIN execution_data d "
            "ON d.executionId = e.id").fetchone()[0]
        newest = db.execute(
            "SELECT max(id) FROM execution_entity").fetchone()[0]
        db.close()
    except sqlite3.DatabaseError as ex:
        print(f"FAILED to verify the exported database: {ex}", file=sys.stderr)
        return None

    shutil.copy2(tmp / "database.sqlite", out)
    meta = {"tag": tag, "exported_at": datetime.now(timezone.utc).isoformat(),
            "executions": total, "with_execution_data": with_data,
            "max_execution_id": newest, "since_id": since_id}
    if since_id is not None:
        meta["new_executions"] = max(0, (newest or 0) - since_id)
    (RESULTS / f"{tag}_executions.json").write_text(json.dumps(meta, indent=1))

    if with_data < total:
        print(f"WARNING: {total - with_data} executions have no execution "
              f"data — check EXECUTIONS_DATA_SAVE_ON_* and "
              f"EXECUTIONS_DATA_PRUNE", file=sys.stderr)
    print(f"exported [{tag}]: {total} executions ({with_data} with node data, "
          f"max id {newest}) -> {out}")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--since-id", type=int, default=None,
                    help="highest execution id before this run, to report how "
                         "many the run produced")
    args = ap.parse_args()
    return 0 if export(args.tag, args.since_id) else 1


if __name__ == "__main__":
    sys.exit(main())
