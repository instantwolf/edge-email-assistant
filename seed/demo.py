#!/usr/bin/env python3
"""Manually triggered demo seeds, one scenario at a time.

Each scenario in demo_scenarios.json is a self-contained set of emails and/or
calendar events that showcases one capability. Demo data uses its own namespace
(the IOT26-DEMO label and [IOT26-DEMO] event prefix) so it stays separate from
the eval's IOT26-SEED ground truth.

Subcommands: list, seed <id> [--send], clean <id|all>. Run `list` for the scenario catalog and prompts.
"""
import argparse
import base64
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_token import get_token, urlopen  # noqa: E402

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
GCAL = "https://www.googleapis.com/calendar/v3"
TZ = "Europe/Vienna"
SPEC = json.loads((Path(__file__).parent / "demo_scenarios.json").read_text())
LABEL = SPEC["label"]                 # IOT26-DEMO
EVENT_PREFIX = SPEC["event_prefix"]   # [IOT26-DEMO]
DEFAULT_URL = "http://localhost:5678"


def api(token, url, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


def ensure_label(token, name):
    for lb in api(token, f"{GMAIL}/labels").get("labels", []):
        if lb["name"] == name:
            return lb["id"]
    lb = api(token, f"{GMAIL}/labels", {
        "name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"})
    return lb["id"]


def find(scenario_id):
    s = next((x for x in SPEC["scenarios"] if x["id"] == scenario_id), None)
    if not s:
        sys.exit(f"unknown scenario '{scenario_id}'. Try: python3 seed/demo.py list")
    return s


def cmd_list(_args):
    print(f"Demo scenarios (label {LABEL}):\n")
    for s in SPEC["scenarios"]:
        n_emails, n_events = len(s.get("emails", [])), len(s.get("events", []))
        print(f"  {s['id']:<10} {s['title']}")
        print(f"             shows: {s['shows']}")
        print(f"             seeds: {n_emails} email(s), {n_events} event(s) | prompts: {len(s['prompts'])}")
        for p in s["prompts"]:
            print(f"               > {p}")
        print()


def cmd_seed(args):
    s = find(args.scenario)
    gm = get_token("GmailOAuth000001")
    base_id = ensure_label(gm, LABEL)
    sub_id = ensure_label(gm, f"{LABEL}-{s['id']}")
    now = datetime.now(timezone.utc)
    me = api(gm, f"{GMAIL}/profile")["emailAddress"]

    for e in s.get("emails", []):
        msg = EmailMessage()
        msg["From"] = e["from"]
        msg["To"] = me
        msg["Subject"] = e["subject"]
        msg["Date"] = format_datetime(now - timedelta(hours=e["age_hours"]))
        msg.set_content(e["body"])
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        labels = ["INBOX", base_id, sub_id] + (["UNREAD"] if e.get("unread") else [])
        api(gm, f"{GMAIL}/messages?internalDateSource=dateHeader", {"raw": raw, "labelIds": labels})
        print(f"  email  : {e['subject']!r} (from {e['from'].split('<')[0].strip()})")

    if s.get("events"):
        gc = get_token("GCalOAuth0000001")
        today = datetime.now().date()
        for ev in s["events"]:
            day = today + timedelta(days=ev["day_offset"])
            api(gc, f"{GCAL}/calendars/primary/events", {
                "summary": f"{EVENT_PREFIX} {ev['title']}",
                "description": f"IOT26-DEMO:{s['id']}\n{ev.get('description', '')}",
                "start": {"dateTime": f"{day}T{ev['start']}:00", "timeZone": TZ},
                "end": {"dateTime": f"{day}T{ev['end']}:00", "timeZone": TZ}})
            print(f"  event  : {ev['title']!r} on {day} {ev['start']}-{ev['end']}")

    print(f"\nseeded scenario '{s['id']}' - {s['title']}")
    print("prompts to run:")
    for p in s["prompts"]:
        print(f"  > {p}")
    print(f"expected: {s['expect']}")

    if args.send:
        session = args.session or f"demo-{s['id']}"
        print(f"\n--send: firing prompts at {args.base_url} (session '{session}')...")
        for p in s["prompts"]:
            body = json.dumps({"sessionId": session, "message": p}).encode()
            req = urllib.request.Request(f"{args.base_url}/webhook/assistant", data=body,
                                         headers={"Content-Type": "application/json"})
            t0 = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=args.timeout) as r:
                    out = json.loads(r.read() or b"{}").get("output", "")
                print(f"\n> {p}\n  ({time.monotonic()-t0:.1f}s) {out}")
            except Exception as ex:  # noqa: BLE001
                print(f"\n> {p}\n  FAILED: {ex!r}")
    print(f"\nclean up with: python3 seed/demo.py clean {s['id']}   (or 'clean all')")


def cmd_clean(args):
    which = args.scenario
    gm = get_token("GmailOAuth000001")
    label_q = LABEL.lower() if which == "all" else f"{LABEL.lower()}-{which}"
    msgs = api(gm, f"{GMAIL}/messages?q=label:{label_q}").get("messages", [])
    for m in msgs:
        api(gm, f"{GMAIL}/messages/{m['id']}/trash", method="POST", payload={})
    print(f"trashed {len(msgs)} demo email(s) (label {label_q})")

    gc = get_token("GCalOAuth0000001")
    # Scope to a near-term window (demo events are always within days of now).
    # singleEvents=true expands recurring events, so a wide window would fill the
    # 250-result page with recurring instances and push the demo events off it.
    now = datetime.now(timezone.utc)
    win = {"timeMin": (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "timeMax": (now + timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "maxResults": "250", "singleEvents": "true"}
    q = "&".join(f"{k}={v}" for k, v in win.items())
    events = api(gc, f"{GCAL}/calendars/primary/events?{q}").get("items", [])
    tag = None if which == "all" else f"IOT26-DEMO:{which}"
    n = 0
    for ev in events:
        if not (ev.get("summary", "").startswith(EVENT_PREFIX)):
            continue
        if tag and tag not in ev.get("description", ""):
            continue
        api(gc, f"{GCAL}/calendars/primary/events/{ev['id']}", method="DELETE")
        n += 1
    print(f"deleted {n} demo event(s)" + ("" if which == "all" else f" for '{which}'"))


def main():
    ap = argparse.ArgumentParser(description="Manually triggered partial demo seeds.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list scenarios and their prompts")
    ps = sub.add_parser("seed", help="seed one scenario")
    ps.add_argument("scenario")
    ps.add_argument("--send", action="store_true", help="also POST the prompts to the webhook")
    ps.add_argument("--session", default=None, help="sessionId for --send (default demo-<id>)")
    ps.add_argument("--base-url", default=DEFAULT_URL)
    ps.add_argument("--timeout", type=int, default=300)
    pc = sub.add_parser("clean", help="remove a scenario's data (or 'all')")
    pc.add_argument("scenario", help="scenario id, or 'all'")
    args = ap.parse_args()
    {"list": cmd_list, "seed": cmd_seed, "clean": cmd_clean}[args.cmd](args)


if __name__ == "__main__":
    main()
