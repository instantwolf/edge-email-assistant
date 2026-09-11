#!/usr/bin/env python3
"""Campaign state capture — the effect axis's raw input (study-v3 task 2.4).

    python3 eval/campaign_state.py pre   <tag>
    python3 eval/campaign_state.py post  <tag>
    python3 eval/campaign_state.py clean <tag>

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

**`clean <tag>`** (added 2026-09-10) deletes exactly those objects again, by
id. The account-level reset (`seed/cleanup.py`) matches on the title prefix
`[IOT26`/`[ST3]`, so an object whose title never carried the prefix is
invisible to it: in the 2.6 tracer run a model created the task `Submit
intermediate report (due 2026-09-17 15:00)`, which outlived the reset and would
have sat in the account for the remaining campaign runs, in every later run's
reads. The capture is the precise reset, because it names what this run
created and nothing else. Idempotent — a 404/410 is an object already gone,
which is counted and reported rather than failed — so it can be re-run for any
tag whose capture is still on disk. It exits 1 on a token failure or on an
object it could not remove, having attempted every one; the tag-based reset
stays as the safety net either way.
"""
import json
import sys
import urllib.error
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

# An object `clean` was asked to remove and the API says is not there. Being
# already gone is the goal state, not a fault: the step is re-runnable, and the
# operator may have removed something by hand between the run and the clean.
GONE = (404, 410)


def api(token, url, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urlopen(req) as r:
        body = r.read()
        return json.loads(body) if body else {}


def paged(token, url, key="items"):
    """Follow `nextPageToken` to exhaustion.

    None of these listings used to paginate, and on 2026-09-12 that silently
    truncated a capture: the calendar returned 51 of 53 events with a
    `nextPageToken` set, **while `maxResults` was 250**. Google paginates on its
    own server-side sizing, not on the maximum you ask for, so a page token can
    appear on any response and asking for more per page does not prevent it.

    Two of the run's created events fell past that first page. They were
    therefore missing from the pre/post diff, which meant `clean` could not
    delete them (they outlived the run in the account) and — the damaging half —
    the effect differ never saw them either, so genuine writes would have scored
    `no-write`. The census could not catch it: it reconciles the capture against
    itself, and an object the capture never saw is invisible to both sides of
    that sum.
    """
    out, page = [], None
    while True:
        sep = "&" if "?" in url else "?"
        resp = api(token, f"{url}{sep}pageToken={page}" if page else url)
        out += resp.get(key, [])
        page = resp.get("nextPageToken")
        if not page:
            return out


def list_events(token):
    q = urllib.parse.urlencode(WINDOW)
    return paged(token, f"{GCAL}/calendars/primary/events?{q}")


def list_tasks(token):
    return paged(token, f"{GTASKS}/lists/@default/tasks"
                        "?showCompleted=true&showHidden=true&maxResults=100")


def list_sent(token):
    q = urllib.parse.quote("in:sent newer_than:2d")
    return paged(token, f"{GMAIL}/messages?q={q}&maxResults=200", "messages")


def fetch_message(token, mid):
    """Full message — headers *and* body. `format=metadata` (what the pilot
    used) cannot carry a body, and the body is where generated-content
    propositions are asserted."""
    return api(token, f"{GMAIL}/messages/{mid}?format=full")


def tokens():
    return (get_token("GCalOAuth0000001"), get_token("GTasksOAuth00001"),
            get_token("GmailOAuth000001"))


def remove(token, url, payload=None, method=None):
    """One removal. True if the object was there, False if it was already
    gone. Anything other than a 404/410 is the caller's problem."""
    try:
        api(token, url, payload, method)
        return True
    except urllib.error.HTTPError as ex:
        if ex.code in GONE:
            return False
        raise


def clean(tag):
    """Remove the objects listed in `<tag>_created.json`, by id.

    Calendar and Tasks are deleted; sent mail is trashed, for the same reason
    `seed/cleanup.py` trashes — that is what the granted Gmail scope allows.

    Every object is attempted even after one fails, because a step that exists
    to leave nothing behind must not stop at the first thing it cannot remove.
    """
    path = RESULTS / f"{tag}_created.json"
    try:
        created = json.loads(path.read_text(encoding="utf-8"))["created"]
    except (OSError, ValueError, KeyError) as ex:
        print(f"clean [{tag}]: no capture to clean at {path}: {ex}",
              file=sys.stderr)
        return 1
    try:
        gc, gt, gm = tokens()
    except (SystemExit, Exception) as ex:        # get_token raises SystemExit
        print(f"clean [{tag}]: token failure: {ex}", file=sys.stderr)
        return 1

    plan = [
        ("calendar_event", gc,
         lambda i: (f"{GCAL}/calendars/primary/events/{i}", None, "DELETE")),
        ("task", gt,
         lambda i: (f"{GTASKS}/lists/@default/tasks/{i}", None, "DELETE")),
        ("sent_email", gm,
         lambda i: (f"{GMAIL}/messages/{i}/trash", {}, "POST")),
    ]
    removed = {kind: 0 for kind, _token, _build in plan}
    already, failed = 0, []
    for kind, token, build in plan:
        for obj in created.get(kind) or []:
            oid = obj.get("id")
            if not oid:
                failed.append(f"{kind}: a captured record carries no id")
                continue
            try:
                if remove(token, *build(oid)):
                    removed[kind] += 1
                else:
                    already += 1
            except Exception as ex:                          # noqa: BLE001
                failed.append(f"{kind} {oid}: {ex}")

    print(f"clean [{tag}]: {removed['calendar_event']} events, "
          f"{removed['task']} tasks, {removed['sent_email']} mails removed "
          f"({already} already gone)")
    for line in failed:
        print(f"clean [{tag}]: FAILED {line}", file=sys.stderr)
    return 1 if failed else 0


def main():
    if len(sys.argv) < 3:
        print("\n".join(__doc__.strip().splitlines()[2:5]), file=sys.stderr)
        return 2
    mode, tag = sys.argv[1], sys.argv[2]

    # Ahead of the tokens: `clean` mints its own, so that a token failure there
    # is one reported line rather than a traceback out of a non-critical step.
    if mode == "clean":
        return clean(tag)

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
