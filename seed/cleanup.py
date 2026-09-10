#!/usr/bin/env python3
"""Trash all project artifacts from the connected personal Google account:
seeded mails (label IOT26-SEED), [IOT26-TEST] mails, [IOT26 calendar events,
and IOT26 tasks — plus the study-v3 campaign's own artifacts, which carry the
[ST3] prefix (events, tasks, sent mails), so a run starts from a clean account.

Eval-run tasks have arbitrary titles, so they're left alone by default; use
--list-tasks to inspect them and --delete-task "title" to remove one.
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_token import get_token, urlopen  # noqa: E402

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
GCAL = "https://www.googleapis.com/calendar/v3"
GTASKS = "https://tasks.googleapis.com/tasks/v1"
# Title prefixes that mark project artifacts: the pilot's and the study-v3 campaign's.
TAGS = ("IOT26", "ST3")


def api(token, url, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


def gmail_ids(token, query):
    ids, page = [], None
    while True:
        q = urllib.parse.urlencode({"q": query, **({"pageToken": page} if page else {})})
        resp = api(token, f"{GMAIL}/messages?{q}")
        ids += [m["id"] for m in resp.get("messages", [])]
        page = resp.get("nextPageToken")
        if not page:
            return ids


def clean_gmail():
    token = get_token("GmailOAuth000001")
    ids = (set(gmail_ids(token, "label:iot26-seed"))
           | set(gmail_ids(token, 'subject:"[IOT26-TEST]"'))
           | set(gmail_ids(token, 'subject:"[ST3]"'))
           # bounces from eval replies to synthetic .example addresses
           | set(gmail_ids(token, 'from:mailer-daemon newer_than:7d'))
           | set(gmail_ids(token, '"edu-klu.example" from:postmaster newer_than:7d')))
    for mid in ids:
        api(token, f"{GMAIL}/messages/{mid}/trash", {})
    print(f"gmail: trashed {len(ids)} messages (seeds, test mails, bounces)")


def clean_calendar():
    token = get_token("GCalOAuth0000001")
    # Wide window: leftovers from earlier campaigns must not survive a reset (a
    # [IOT26] event from 2026-07-15 outlived the old 30-day window until 2026-09-10).
    tmin = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat().replace("+00:00", "Z")
    tmax = (datetime.now(timezone.utc) + timedelta(days=400)).isoformat().replace("+00:00", "Z")
    items = []
    for tag in TAGS:
        q = urllib.parse.urlencode({"q": tag, "timeMin": tmin, "timeMax": tmax, "maxResults": 250})
        items += api(token, f"{GCAL}/calendars/primary/events?{q}").get("items", [])
    n = 0
    for ev in {e["id"]: e for e in items}.values():
        if any(ev.get("summary", "").startswith(f"[{tag}") for tag in TAGS):
            api(token, f"{GCAL}/calendars/primary/events/{ev['id']}", method="DELETE")
            n += 1
    print(f"calendar: deleted {n} events")


def clean_tasks(list_only=False, delete_title=None):
    token = get_token("GTasksOAuth00001")
    items = api(token, f"{GTASKS}/lists/@default/tasks?showCompleted=true&maxResults=100").get("items", [])
    n = 0
    for t in items:
        title = t.get("title", "")
        if list_only:
            print(f"  task: {title!r} due={t.get('due', '-')}")
        elif any(tag in title for tag in TAGS) or (delete_title and title == delete_title):
            api(token, f"{GTASKS}/lists/@default/tasks/{t['id']}", method="DELETE")
            n += 1
    if not list_only:
        print(f"tasks: deleted {n} tasks")


if __name__ == "__main__":
    if "--list-tasks" in sys.argv:
        clean_tasks(list_only=True)
        sys.exit(0)
    delete_title = None
    if "--delete-task" in sys.argv:
        delete_title = sys.argv[sys.argv.index("--delete-task") + 1]
    clean_gmail()
    clean_calendar()
    clean_tasks(delete_title=delete_title)
