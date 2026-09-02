#!/usr/bin/env python3
"""Campaign state capture — the effect axis's raw input (study-v3 task 2.4).

    python3 eval/campaign_state.py pre  <tag>
    python3 eval/campaign_state.py post <tag>

Successor to `eval_state.py`, which was written for the pilot and captures too
little for the campaign: events without `end` or `description`, sent mail
without a body. The study's effect differ asserts spec'd fields on the created
objects, so a field the capture never fetched would be scored as a field the
agent never set — a harness bug wearing the costume of a silent failure.

Two rules make that impossible rather than unlikely:

  1. **Fetch whole resources**, never a projection.
  2. **Stamp every record `{"_capture": "full"}`.** The Google APIs omit unset
     optional fields entirely, so key-presence cannot distinguish "the agent
     did not set it" from "we never asked for it". The marker is explicit, and
     the differ sets aside any trial whose records lack it
     (`study-v3/phase2-harness/lib/effects.py::check_capture`).

This script stays deliberately dumb: it fetches and marks, and interprets
nothing. Flattening a Gmail MIME tree into "what the mail said" is
interpretation, and it lives once on the study side (`effects.adapt_sent_email`
accepts the raw message), so the capture and the scorer cannot drift.

Output: `eval/results/<tag>_created.json`

    {"tag", "pre_counts", "captured_at",
     "created": {"calendar_event": [...], "task": [...], "sent_email": [...]}}

Per-interaction attribution happens study-side (`effects.attribute()`) against
the interaction windows `run_interactions.py` writes, so the choice between
"snapshot around every interaction" and "snapshot once and window by the
object's own creation stamp" stays a scheduling decision, not a data format.
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "seed"))
from google_token import get_token, urlopen  # noqa: E402

GCAL = "https://www.googleapis.com/calendar/v3"
GTASKS = "https://tasks.googleapis.com/tasks/v1"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
STATE_DIR = Path(__file__).resolve().parent / ".tmp"
RESULTS = Path(__file__).resolve().parent / "results"

# Wide enough for any campaign-resolvable date. The pre/post id diff does the
# real filtering; the window only bounds API cost.
WINDOW = {"timeMin": "2026-08-01T00:00:00Z", "timeMax": "2027-03-01T00:00:00Z",
          "maxResults": 250}

MARKER = {"_capture": "full"}


def api(token, url):
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    with urlopen(req) as r:
        body = r.read()
        return json.loads(body) if body else {}


def list_events(token):
    q = urllib.parse.urlencode(WINDOW)
    return api(token, f"{GCAL}/calendars/primary/events?{q}").get("items", [])


def list_tasks(token):
    return api(token, f"{GTASKS}/lists/@default/tasks"
                      "?showCompleted=true&showHidden=true&maxResults=100"
               ).get("items", [])


def list_sent(token):
    q = urllib.parse.quote("in:sent newer_than:2d")
    return api(token, f"{GMAIL}/messages?q={q}&maxResults=200").get(
        "messages", [])


def fetch_message(token, mid):
    """Full message — headers *and* body. `format=metadata` (what the pilot
    used) cannot carry a body, and the body is where generated-content
    propositions are asserted."""
    return api(token, f"{GMAIL}/messages/{mid}?format=full")


def tokens():
    return (get_token("GCalOAuth0000001"), get_token("GTasksOAuth00001"),
            get_token("GmailOAuth000001"))


def main():
    if len(sys.argv) < 3:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    mode, tag = sys.argv[1], sys.argv[2]
    gc, gt, gm = tokens()

    if mode == "pre":
        state = {"events": [e["id"] for e in list_events(gc)],
                 "tasks": [t["id"] for t in list_tasks(gt)],
                 "sent": [m["id"] for m in list_sent(gm)],
                 "at": datetime.now(timezone.utc).isoformat()}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / f"campaign_state_{tag}.json").write_text(
            json.dumps(state), encoding="utf-8")
        print(f"pre [{tag}]: {len(state['events'])} events, "
              f"{len(state['tasks'])} tasks, {len(state['sent'])} sent")
        return 0

    if mode != "post":
        print(f"unknown mode {mode!r}", file=sys.stderr)
        return 2

    pre_path = STATE_DIR / f"campaign_state_{tag}.json"
    pre = json.loads(pre_path.read_text(encoding="utf-8"))

    events = [dict(e, **MARKER) for e in list_events(gc)
              if e["id"] not in set(pre["events"])]
    tasks = [dict(t, **MARKER) for t in list_tasks(gt)
             if t["id"] not in set(pre["tasks"])]
    sent = [dict(fetch_message(gm, m["id"]), **MARKER)
            for m in list_sent(gm) if m["id"] not in set(pre["sent"])]

    # Loud, not silent: the differ needs these for interaction attribution.
    missing = ([f"event {e['id']}" for e in events if "created" not in e]
               + [f"task {t['id']}" for t in tasks if "updated" not in t]
               + [f"message {m['id']}" for m in sent
                  if "internalDate" not in m])
    if missing:
        print(f"WARNING: {len(missing)} created objects lack a creation "
              f"timestamp: {missing[:5]}", file=sys.stderr)

    out = {"tag": tag,
           "captured_at": datetime.now(timezone.utc).isoformat(),
           "pre_at": pre.get("at"),
           "pre_counts": {k: len(v) for k, v in pre.items()
                          if isinstance(v, list)},
           "created": {"calendar_event": events, "task": tasks,
                       "sent_email": sent}}
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{tag}_created.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"post [{tag}]: {len(events)} events, {len(tasks)} tasks, "
          f"{len(sent)} sent -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
