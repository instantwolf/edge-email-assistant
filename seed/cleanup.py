#!/usr/bin/env python3
"""Trash this project's artifacts from the connected Google account, and prove
that none survived.

**This is a personal account, not a throwaway.** At the time of writing it holds
747 personal calendar events and 97 personal tasks across five task lists
alongside the study's objects. Every deletion here is therefore scoped to a
*bracketed project tag* in the object's own title — `[IOT26` (the pilot) or
`[ST3` (the study-v3 campaign). Nothing untagged is ever touched, and no filter
is ever widened to "everything in the window". Keep it that way.

What it removes: seeded mails (label IOT26-SEED), `[IOT26-TEST]` and `[ST3]`
mails, bounce notifications from the synthetic `.example` recipients, tagged
calendar events, and tagged tasks in every task list.

    python3 cleanup.py                # clean, then verify
    python3 cleanup.py --dry-run      # report what would go; change nothing
    python3 cleanup.py --list-tasks   # inspect tasks, all lists
    python3 cleanup.py --delete-task "exact title"

Exit status is 1 if a tagged object is still present after the clean, because a
run that starts on a dirty account reads objects it did not create and scores
them as its own. `campaign_run.py` treats `reset-account` as critical, so that
non-zero stops the run rather than contaminating it.

Four defects this file used to have, all found on 2026-09-12 when a tagged task
outlived a reset, and all of them the kind that only bite once nobody is
watching (i.e. somewhere inside a 142-run campaign):

  1. `showHidden` was not requested, and Google hides *completed* tasks. The
     capture in `eval/campaign_state.py` asked for it, this file did not, so the
     same list returned 52 objects there and 2 here. A study task that ever
     reached `completed` was invisible to cleanup permanently.
  2. Nothing was paginated. Tasks stopped at 100 and calendar at 250, and
     neither followed `nextPageToken`; the excess was silently left behind.
  3. Only the `@default` task list was swept, though the account has five.
  4. The calendar was searched with the free-text `q` parameter, which trusts
     Google to tokenize a bracketed tag the way we assume. It now sweeps the
     window and matches locally, which is what the assertion actually needs.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_token import get_token, urlopen  # noqa: E402

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
GCAL = "https://www.googleapis.com/calendar/v3"
GTASKS = "https://tasks.googleapis.com/tasks/v1"

# Bracket-anchored so a personal object merely containing the letters "ST3"
# cannot match. Mid-title placement still matches, because a model does not
# always put the tag first even when the intent says to.
TAGS = ("IOT26", "ST3")
TAG_MARKS = tuple(f"[{t}" for t in TAGS)

# Leftovers from earlier campaigns must not survive a reset: a [IOT26] event
# from 2026-07-15 outlived the old 30-day window until 2026-09-10.
WINDOW_DAYS = 400


def is_project(title):
    return any(mark in (title or "") for mark in TAG_MARKS)


def api(token, url, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


def delete(token, url):
    """One retry: a transient 5xx here would otherwise leave a survivor and
    fail the verification, stopping a campaign for a blip."""
    for attempt in (1, 2):
        try:
            api(token, url, method="DELETE")
            return True
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            code = getattr(exc, "code", None)
            if code in (404, 410):      # already gone is the goal state
                return True
            if attempt == 2:
                print(f"  ! delete failed ({code or type(exc).__name__}): {url}")
                return False
            time.sleep(2)


def paged(token, url, key="items"):
    """Every listing here is paginated; none of them used to be."""
    out, page = [], None
    while True:
        sep = "&" if "?" in url else "?"
        full = f"{url}{sep}pageToken={page}" if page else url
        resp = api(token, full)
        out += resp.get(key, [])
        page = resp.get("nextPageToken")
        if not page:
            return out


# ------------------------------------------------------------------ gmail

def gmail_ids(token, query):
    q = urllib.parse.urlencode({"q": query})
    return [m["id"] for m in paged(token, f"{GMAIL}/messages?{q}", "messages")]


def find_gmail_project(token):
    """Objects this project put there. A survivor here is fatal: the inbox is
    what the read-then-write intents read."""
    return (set(gmail_ids(token, "label:iot26-seed"))
            | set(gmail_ids(token, 'subject:"[IOT26-TEST]"'))
            | set(gmail_ids(token, 'subject:"[ST3]"')))


def find_gmail_bounces(token):
    """Bounces from eval replies to the synthetic .example addresses. Cleaned
    like everything else, but *not* fatal to verification: they are delivered
    asynchronously, so one arriving between the trash and the re-list would
    otherwise fail a verify and stop a campaign for a piece of mail that no
    run created."""
    return (set(gmail_ids(token, "from:mailer-daemon newer_than:7d"))
            | set(gmail_ids(token,
                            '"edu-klu.example" from:postmaster newer_than:7d')))


def find_gmail(token):
    return find_gmail_project(token) | find_gmail_bounces(token)


def clean_gmail(dry_run=False):
    token = get_token("GmailOAuth000001")
    ids = find_gmail(token)
    if dry_run:
        print(f"gmail: would trash {len(ids)} messages")
        return len(ids)
    for mid in ids:
        api(token, f"{GMAIL}/messages/{mid}/trash", {})
    print(f"gmail: trashed {len(ids)} messages (seeds, test mails, bounces)")
    return len(ids)


# --------------------------------------------------------------- calendar

def find_events(token):
    """Sweep the window and match locally — see defect 4 in the module docstring."""
    now = datetime.now(timezone.utc)
    q = urllib.parse.urlencode({
        "timeMin": (now - timedelta(days=WINDOW_DAYS)).isoformat().replace("+00:00", "Z"),
        "timeMax": (now + timedelta(days=WINDOW_DAYS)).isoformat().replace("+00:00", "Z"),
        "maxResults": 250,
    })
    events = paged(token, f"{GCAL}/calendars/primary/events?{q}")
    return [e for e in events if is_project(e.get("summary", ""))]


def clean_calendar(dry_run=False):
    token = get_token("GCalOAuth0000001")
    hits = find_events(token)
    if dry_run:
        print(f"calendar: would delete {len(hits)} events")
        for e in hits:
            start = (e.get("start") or {})
            print(f"    {e.get('summary', '')[:58]:<58} "
                  f"{start.get('dateTime') or start.get('date') or '-'}")
        return len(hits)
    n = sum(1 for e in hits
            if delete(token, f"{GCAL}/calendars/primary/events/{e['id']}"))
    print(f"calendar: deleted {n} of {len(hits)} tagged events")
    return n


# ------------------------------------------------------------------ tasks

def task_lists(token):
    return paged(token, f"{GTASKS}/users/@me/lists")


def list_tasks_in(token, list_id):
    """showHidden is the one that matters: completed tasks are hidden, and
    without it they are invisible here forever (defect 1)."""
    return paged(token, f"{GTASKS}/lists/{list_id}/tasks"
                        "?showCompleted=true&showHidden=true&maxResults=100")


def find_tasks(token, delete_title=None):
    hits = []
    for tl in task_lists(token):
        for t in list_tasks_in(token, tl["id"]):
            title = t.get("title", "")
            if is_project(title) or (delete_title and title == delete_title):
                hits.append((tl, t))
    return hits


def clean_tasks(list_only=False, delete_title=None, dry_run=False):
    token = get_token("GTasksOAuth00001")
    if list_only:
        for tl in task_lists(token):
            items = list_tasks_in(token, tl["id"])
            print(f"  list {tl['title']!r}: {len(items)} tasks")
            for t in items:
                mark = "*" if is_project(t.get("title", "")) else " "
                print(f"   {mark} {t.get('title', '')!r} "
                      f"due={t.get('due', '-')} status={t.get('status', '-')}")
        return 0
    hits = find_tasks(token, delete_title)
    if dry_run:
        print(f"tasks: would delete {len(hits)} tasks")
        for tl, t in hits:
            print(f"    {t.get('title', '')[:58]:<58} "
                  f"[{tl['title']}] status={t.get('status', '-')}")
        return len(hits)
    n = sum(1 for tl, t in hits
            if delete(token, f"{GTASKS}/lists/{tl['id']}/tasks/{t['id']}"))
    print(f"tasks: deleted {n} of {len(hits)} tagged tasks")
    return n


# ----------------------------------------------------------- verification

def verify():
    """Re-list after the clean. Anything tagged that is still present is a
    survivor, and a survivor is the whole reason this file was rewritten."""
    survivors = []
    gmail_token = get_token("GmailOAuth000001")
    survivors += [f"gmail message {mid}"
                  for mid in find_gmail_project(gmail_token)]
    late = find_gmail_bounces(gmail_token)
    if late:
        print(f"note: {len(late)} bounce message(s) arrived after the trash; "
              f"the next reset takes them (not a failure)")
    survivors += [f"event {e.get('summary', '')!r}"
                  for e in find_events(get_token("GCalOAuth0000001"))]
    survivors += [f"task {t.get('title', '')!r} in {tl['title']!r}"
                  for tl, t in find_tasks(get_token("GTasksOAuth00001"))]
    if survivors:
        print(f"\nVERIFY FAILED — {len(survivors)} tagged object(s) survived:")
        for s in survivors[:20]:
            print(f"    {s}")
        return 1
    print("\nverify: no tagged object remains (gmail, calendar, tasks)")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--list-tasks" in argv:
        clean_tasks(list_only=True)
        sys.exit(0)
    dry = "--dry-run" in argv
    title = (argv[argv.index("--delete-task") + 1]
             if "--delete-task" in argv else None)

    clean_gmail(dry_run=dry)
    clean_calendar(dry_run=dry)
    clean_tasks(delete_title=title, dry_run=dry)
    if dry:
        print("\ndry run: nothing was deleted")
        sys.exit(0)
    sys.exit(verify())
