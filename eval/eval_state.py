#!/usr/bin/env python3
"""Snapshot and diff-clean the Google account state around an eval run.

    python3 eval/eval_state.py pre  <tag>    # record current event/task IDs
    python3 eval/eval_state.py post <tag>    # diff, report side effects, clean up

Side effects come from the Google APIs, never from what the agent claims.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "seed"))
from google_token import get_token, urlopen  # noqa: E402

GCAL = "https://www.googleapis.com/calendar/v3"
GTASKS = "https://tasks.googleapis.com/tasks/v1"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
STATE = "/tmp/eval_state_{}.json"
WINDOW = {"timeMin": "2026-07-01T00:00:00Z", "timeMax": "2026-09-30T00:00:00Z", "maxResults": 250}


def api(token, url, method=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urlopen(req) as r:
        b = r.read()
        return json.loads(b) if b else {}


def list_events(token):
    query = urllib.parse.urlencode(WINDOW)
    return api(token, f"{GCAL}/calendars/primary/events?{query}").get("items", [])


def list_tasks(token):
    return api(token, f"{GTASKS}/lists/@default/tasks?showCompleted=true&maxResults=100").get("items", [])


def main():
    mode, tag = sys.argv[1], sys.argv[2]
    gc, gt, gm = get_token("GCalOAuth0000001"), get_token("GTasksOAuth00001"), get_token("GmailOAuth000001")

    if mode == "pre":
        state = {"events": [e["id"] for e in list_events(gc)],
                 "tasks": [t["id"] for t in list_tasks(gt)]}
        Path(STATE.format(tag)).write_text(json.dumps(state))
        print(f"pre-state [{tag}]: {len(state['events'])} events, {len(state['tasks'])} tasks")
        return

    pre = json.loads(Path(STATE.format(tag)).read_text())
    new_ev = [e for e in list_events(gc) if e["id"] not in pre["events"]]
    new_tk = [t for t in list_tasks(gt) if t["id"] not in pre["tasks"]]

    sent = []
    msgs = api(gm, f"{GMAIL}/messages?q=" + urllib.parse.quote("in:sent newer_than:1d")).get("messages", [])
    for m in msgs:
        detail = api(gm, f"{GMAIL}/messages/{m['id']}?format=metadata&metadataHeaders=To&metadataHeaders=Subject")
        headers = {x["name"]: x["value"] for x in detail["payload"]["headers"]}
        sent.append({"id": m["id"], "to": headers.get("To", ""), "subject": headers.get("Subject", "")})

    report = {"new_events": [{"summary": e.get("summary"), "start": e.get("start", {}).get("dateTime")} for e in new_ev],
              "new_tasks": [{"title": t.get("title"), "due": t.get("due")} for t in new_tk],
              "sent_mails": [{"to": s["to"], "subject": s["subject"]} for s in sent]}
    out = Path(__file__).parent / "results" / f"{tag}_sideeffects.json"
    out.write_text(json.dumps(report, indent=1))
    print(f"side effects [{tag}]: {len(new_ev)} events, {len(new_tk)} tasks, {len(sent)} sent")
    for e in report["new_events"]:
        print("  event:", e["summary"], e["start"])
    for t in report["new_tasks"]:
        print("  task:", t["title"], t.get("due"))
    for s in report["sent_mails"]:
        print("  sent:", s["to"], "|", s["subject"])

    # remove the events, tasks and mails this run created
    for e in new_ev:
        api(gc, f"{GCAL}/calendars/primary/events/{e['id']}", method="DELETE")
    for t in new_tk:
        api(gt, f"{GTASKS}/lists/@default/tasks/{t['id']}", method="DELETE")
    trashed = 0
    for s in sent:
        if ".example" in s["to"]:
            api(gm, f"{GMAIL}/messages/{s['id']}/trash", method="POST", payload={})
            trashed += 1
    print(f"cleaned: {len(new_ev)} events, {len(new_tk)} tasks, {trashed} sent mails trashed")


if __name__ == "__main__":
    main()
