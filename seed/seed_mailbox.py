#!/usr/bin/env python3
"""Seed the connected Google account with synthetic emails and calendar events.

Emails from seed/emails.json are inserted via the Gmail API (not sent) with
backdated Date headers, so "today's emails" is deterministic; each gets the
IOT26-SEED label for cleanup. Events from seed/events.json go on the primary
calendar with the [IOT26] prefix.

    python3 seed/seed_mailbox.py [--force]   # --force reseeds over existing seeds

Cleanup: python3 seed/cleanup.py
"""
import base64
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_token import get_token, urlopen  # noqa: E402

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
GCAL = "https://www.googleapis.com/calendar/v3"
LABEL_NAME = "IOT26-SEED"
TZ = "Europe/Vienna"


def api(token, url, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


def ensure_label(token):
    labels = api(token, f"{GMAIL}/labels")["labels"]
    for lb in labels:
        if lb["name"] == LABEL_NAME:
            return lb["id"]
    lb = api(token, f"{GMAIL}/labels", {
        "name": LABEL_NAME,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    })
    return lb["id"]


def seed_emails(force=False):
    token = get_token("GmailOAuth000001")
    me = api(token, f"{GMAIL}/profile")["emailAddress"]
    existing = api(token, f"{GMAIL}/messages?q=label:{LABEL_NAME.lower()}&maxResults=1")
    if existing.get("resultSizeEstimate", 0) > 0 and not force:
        print(f"mailbox already contains {LABEL_NAME} mails - run seed/cleanup.py first (or --force)")
        return
    label_id = ensure_label(token)
    emails = json.loads((Path(__file__).parent / "emails.json").read_text())
    now = datetime.now(timezone.utc)
    for e in emails:
        msg = EmailMessage()
        msg["From"] = e["from"]
        msg["To"] = me
        msg["Subject"] = e["subject"]
        msg["Date"] = format_datetime(now - timedelta(hours=e["age_hours"]))
        msg.set_content(e["body"])
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        label_ids = ["INBOX", label_id] + (["UNREAD"] if e.get("unread") else [])
        api(token, f"{GMAIL}/messages?internalDateSource=dateHeader",
            {"raw": raw, "labelIds": label_ids})
        print(f"  inserted: {e['subject']!r} (age {e['age_hours']}h)")
    print(f"seeded {len(emails)} emails into {me}")


def seed_events():
    token = get_token("GCalOAuth0000001")
    events = json.loads((Path(__file__).parent / "events.json").read_text())
    today = datetime.now().date()
    for ev in events:
        day = today + timedelta(days=ev["day_offset"])
        api(token, f"{GCAL}/calendars/primary/events", {
            "summary": ev["title"],
            "description": ev.get("description", ""),
            "start": {"dateTime": f"{day}T{ev['start']}:00", "timeZone": TZ},
            "end": {"dateTime": f"{day}T{ev['end']}:00", "timeZone": TZ},
        })
        print(f"  created event: {ev['title']!r} on {day} {ev['start']}-{ev['end']}")
    print(f"seeded {len(events)} calendar events")


if __name__ == "__main__":
    force = "--force" in sys.argv
    seed_emails(force=force)
    seed_events()
