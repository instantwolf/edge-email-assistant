#!/usr/bin/env python3
"""Per-turn latency breakdown for the agent's LLM turns.

performance_metrics.md reports one end-to-end number per interaction. This
replays the multi-turn agent loop directly against Ollama's /api/chat (no n8n),
with the production tool schemas and canned tool results, and records prefill
vs generation tokens/seconds per turn. On edge hardware the context is
re-prefilled and grows every turn, so prefill x turns can rival generation. It
also checks whether Ollama reuses its KV cache for the stable system+tools
prefix, with an optional num_ctx A/B.

Needs only native Ollama on :11434; touches no Google or n8n state.

    python3 eval/latency_budget.py --model gemma4:12b-it-qat [--compare-ctx 4096]
"""
import argparse
import csv
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
NS = 1e9  # Ollama durations are nanoseconds


# The 7 agent tools as Ollama /api/chat schemas. Mirror
# workflows/email_calendar_assistant.json so the tool-block prefill cost matches
# production; edit this list to A/B a trimmed tool set.
TOOLS = [
    {"type": "function", "function": {
        "name": "current_datetime",
        "description": "Returns the precise current date and time (Europe/Vienna). "
                       "The current date is already provided in your context - only "
                       "call this if you need the exact minute.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_emails",
        "description": "Read emails from the Gmail inbox. Optionally filter with "
                       "search_query (Gmail search syntax).",
        "parameters": {"type": "object", "properties": {
            "search_query": {"type": "string", "description":
                "Gmail search query, e.g. newer_than:1d for the last day, is:unread "
                "for unread, from:alice@x.com. Empty string returns the most recent emails."}}}}},
    {"type": "function", "function": {
        "name": "send_email",
        "description": "Send an email via Gmail. Provide to, subject, and body.",
        "parameters": {"type": "object", "properties": {
            "to": {"type": "string", "description": "recipient email address"},
            "subject": {"type": "string", "description": "email subject line"},
            "body": {"type": "string", "description": "plain-text email body"}},
            "required": ["to", "subject", "body"]}}},
    {"type": "function", "function": {
        "name": "list_events",
        "description": "List calendar events between start and end (ISO datetimes). "
                       "Use to answer agenda questions and check availability.",
        "parameters": {"type": "object", "properties": {
            "start": {"type": "string", "description": "start of the time range, ISO datetime"},
            "end": {"type": "string", "description": "end of the time range, ISO datetime"}}}}},
    {"type": "function", "function": {
        "name": "create_event",
        "description": "Create a calendar event with title, start and end (ISO datetimes).",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "event title"},
            "start": {"type": "string", "description": "event start, ISO datetime e.g. 2026-07-06T15:00:00"},
            "end": {"type": "string", "description": "event end, ISO datetime"},
            "description": {"type": "string", "description": "optional event details"}},
            "required": ["title", "start", "end"]}}},
    {"type": "function", "function": {
        "name": "create_task",
        "description": "Save a task/deadline to Google Tasks with title, optional notes and due date.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description":
                "task title; include the due TIME in the title because Google Tasks stores only the date"},
            "notes": {"type": "string", "description": "details or source of the task"},
            "due_date": {"type": "string", "description": "due date in format YYYY-MM-DD"}},
            "required": ["title"]}}},
    {"type": "function", "function": {
        "name": "list_tasks",
        "description": "List open tasks from Google Tasks.",
        "parameters": {"type": "object", "properties": {}}}},
]

SYSTEM = (
    "You are an Email and Calendar Assistant managing the user's Google account "
    "(Gmail, Google Calendar, Google Tasks).\n\n"
    "Current date/time: Monday, 2026-07-06 09:00 (Europe/Vienna). Use this for all "
    "date reasoning (today, tomorrow, weekdays, deadlines).\n\n"
    "Rules:\n"
    "- Use tools to get real data. NEVER invent emails, events, or tasks. If a tool "
    "fails or returns nothing, say so plainly.\n"
    "- When summarizing emails: one line per email - sender, subject, gist.\n"
    "- When creating tasks: Google Tasks stores only the DATE of a deadline, so include "
    "the time in the task title, e.g. 'Submit report (due 15:00)'.\n"
    "- Before sending an email or creating/changing a calendar event, state in one "
    "sentence what you are doing.\n"
    "- Keep answers short: at most 8 lines, no filler."
)

# Realistic tool-result payloads. read_emails ~10 mails, list_tasks ~13 tasks
# (the payload that overflowed interaction #12 at num_ctx 4096).
_SENDERS = ["Anna Muller", "IT Helpdesk", "Sabine Klein", "Newsletter Weekly",
            "Markus Weber", "HR Team", "Project Bot", "Lisa Bauer", "Finance",
            "Conference 2026"]
EMAILS_RESULT = json.dumps([
    {"from": f"{s.lower().replace(' ', '.')}@example.com", "subject": subj,
     "snippet": ("Hi, " + subj + ". " + "Please review the attached details and reply "
                 "at your earliest convenience so we can proceed on schedule.")}
    for s, subj in zip(_SENDERS, [
        "Project sync Tuesday", "Password reset required by Fri 17:00",
        "Status update request", "This week in tech", "Budget review deadline Wed",
        "Onboarding tasks due 2026-07-10", "Nightly build failed",
        "Lunch Thursday?", "Invoice #4471 due 2026-07-15", "Early-bird ends soon"])])

TASKS_RESULT = json.dumps([
    {"id": f"task-{i:03d}", "title": t, "status": "needsAction",
     "updated": "2026-07-05T18:00:00Z", "notes": "carried over from inbox triage"}
    for i, t in enumerate([
        "Submit report (due 15:00)", "Renew SSL cert", "Book flights for conference",
        "Review PR #482", "Reply to Sabine", "Pay invoice #4471 (due 2026-07-15)",
        "Update project plan", "Prepare demo slides", "Call insurance",
        "Order new laptop charger", "File expense report", "Schedule dentist",
        "Read chapter 7"])])
EVENTS_RESULT = json.dumps([
    {"summary": "Standup", "start": "2026-07-06T09:30:00", "end": "2026-07-06T09:45:00"},
    {"summary": "1:1 with Markus", "start": "2026-07-07T11:00:00", "end": "2026-07-07T11:30:00"},
    {"summary": "Sprint review", "start": "2026-07-09T14:00:00", "end": "2026-07-09T15:00:00"}])


def chat(base_url, model, messages, num_ctx, keep_alive, tools=None, timeout=600,
         num_predict=-1):
    """One /api/chat call. Returns (assistant_message, metrics_dict)."""
    payload = {
        "model": model, "messages": messages, "stream": False,
        "keep_alive": keep_alive,
        "options": {"num_ctx": num_ctx, "temperature": 0.2, "num_predict": num_predict},
    }
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(
        f"{base_url}/api/chat", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read())
    pe_cnt = d.get("prompt_eval_count", 0)
    pe_dur = d.get("prompt_eval_duration", 0) / NS
    ev_cnt = d.get("eval_count", 0)
    ev_dur = d.get("eval_duration", 0) / NS
    return d.get("message", {}), {
        "prefill_tok": pe_cnt, "prefill_s": round(pe_dur, 3),
        "prefill_tok_s": round(pe_cnt / pe_dur) if pe_dur else 0,
        "gen_tok": ev_cnt, "gen_s": round(ev_dur, 3),
        "gen_tok_s": round(ev_cnt / ev_dur, 1) if ev_dur else 0,
        "load_s": round(d.get("load_duration", 0) / NS, 2),
        "total_s": round(d.get("total_duration", 0) / NS, 2),
    }


def turn_budget(base_url, model, num_ctx, keep_alive, num_predict=-1):
    """Replay the flagship multi-tool loop, canned tool results injected so the
    context sizes are deterministic. Returns a list of per-turn metric dicts."""
    tool_call = lambda name, args: {
        "role": "assistant", "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": args}}]}
    tool_result = lambda content: {"role": "tool", "content": content}

    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Summarize today's emails and schedule my meetings."}]
    turns = []

    # Turn 1: system + tools + user. Record the metrics, but ignore the model's
    # choice and inject a canned read_emails call so context sizes stay fixed.
    _, m = chat(base_url, model, msgs, num_ctx, keep_alive, tools=TOOLS, num_predict=num_predict)
    turns.append({"turn": 1, "step": "read_emails call", **m})

    # Turn 2: + emails result -> next tool call (list_events)
    msgs += [tool_call("read_emails", {"search_query": "newer_than:1d"}), tool_result(EMAILS_RESULT)]
    _, m = chat(base_url, model, msgs, num_ctx, keep_alive, tools=TOOLS, num_predict=num_predict)
    turns.append({"turn": 2, "step": "list_events call", **m})

    # Turn 3: + events result -> final answer (the big generation turn)
    msgs += [tool_call("list_events", {"start": "2026-07-06T00:00:00", "end": "2026-07-13T00:00:00"}),
             tool_result(EVENTS_RESULT)]
    _, m = chat(base_url, model, msgs, num_ctx, keep_alive, tools=TOOLS, num_predict=num_predict)
    turns.append({"turn": 3, "step": "final answer", **m})
    return turns


def cache_probe(base_url, model, num_ctx, keep_alive):
    """Prefix-cache test: a sizeable prompt, then the same prompt plus one short
    message. Ollama reports the full prompt token count even when it serves the
    shared prefix from KV cache, so the token count can't tell us apart -- the
    prefill duration can. A re-prefill costs about the first call's wall time; a
    cache reuse prefills the larger second prompt in a fraction of it."""
    base = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Here is context to remember:\n" + TASKS_RESULT
             + "\n" + EMAILS_RESULT + "\nAcknowledge with OK."}]
    _, a = chat(base_url, model, base, num_ctx, keep_alive)  # warm the prefix
    extended = base + [{"role": "assistant", "content": "OK."},
                       {"role": "user", "content": "Now list only the task titles."}]
    _, b = chat(base_url, model, extended, num_ctx, keep_alive)
    # Hit if the (larger) second prompt re-prefilled in well under the first's time.
    hit = b["prefill_s"] < a["prefill_s"] * 0.6 and b["prefill_tok"] >= a["prefill_tok"] * 0.8
    return {"first_prefill_tok": a["prefill_tok"], "first_prefill_s": a["prefill_s"],
            "second_prefill_tok": b["prefill_tok"], "second_prefill_s": b["prefill_s"],
            "cache_hit": hit}


def fmt_turns(turns):
    hdr = f"{'turn':>4}  {'step':<16}  {'prefill_tok':>11}  {'prefill_s':>9}  {'gen_tok':>7}  {'gen_s':>6}  {'gen_tok/s':>9}"
    lines = [hdr, "-" * len(hdr)]
    for t in turns:
        lines.append(f"{t['turn']:>4}  {t['step']:<16}  {t['prefill_tok']:>11}  "
                     f"{t['prefill_s']:>9}  {t['gen_tok']:>7}  {t['gen_s']:>6}  {t['gen_tok_s']:>9}")
    pf = sum(t["prefill_s"] for t in turns)
    gn = sum(t["gen_s"] for t in turns)
    lines.append("-" * len(hdr))
    lines.append(f"  SUM prefill {pf:.1f}s   generation {gn:.1f}s   "
                 f"prefill share {pf / (pf + gn) * 100:.0f}%")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:12b-it-qat")
    ap.add_argument("--base-url", default="http://localhost:11434")
    ap.add_argument("--num-ctx", type=int, default=8192, dest="num_ctx")
    ap.add_argument("--keep-alive", default="1h")
    ap.add_argument("--compare-ctx", type=int, default=None, dest="compare_ctx",
                    help="also run the turn budget at this num_ctx to quantify the KV tax")
    ap.add_argument("--num-predict", type=int, default=-1, dest="num_predict",
                    help="cap generated tokens per turn (-1 = unlimited); the generation lever")
    ap.add_argument("--tag", default=None, help="CSV filename tag (default: model)")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    tag = args.tag or args.model.replace(":", "-").replace("/", "-")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print(f"model={args.model}  num_ctx={args.num_ctx}  base={args.base_url}\n")

    print("== prefix-cache probe ==")
    cp = cache_probe(args.base_url, args.model, args.num_ctx, args.keep_alive)
    verdict = "HIT (prefix reused)" if cp["cache_hit"] else "MISS (re-prefilled)"
    print(f"  1st call prefill {cp['first_prefill_tok']} tok / {cp['first_prefill_s']}s "
          f"-> 2nd call prefill {cp['second_prefill_tok']} tok / {cp['second_prefill_s']}s "
          f"(bigger prompt)  => {verdict}\n")

    cap = args.num_predict
    cap_label = "unlimited" if cap < 0 else str(cap)
    print(f"== per-turn budget: flagship multi-tool, num_ctx={args.num_ctx}, "
          f"num_predict={cap_label} ==")
    turns = turn_budget(args.base_url, args.model, args.num_ctx, args.keep_alive, cap)
    print(fmt_turns(turns) + "\n")

    all_rows = [{"phase": f"budget-ctx{args.num_ctx}-np{cap}", **t} for t in turns]

    if args.compare_ctx:
        print(f"== per-turn budget: flagship multi-tool, num_ctx={args.compare_ctx} (A/B) ==")
        turns2 = turn_budget(args.base_url, args.model, args.compare_ctx, args.keep_alive, cap)
        print(fmt_turns(turns2) + "\n")
        all_rows += [{"phase": f"budget-ctx{args.compare_ctx}-np{cap}", **t} for t in turns2]

    csv_path = RESULTS_DIR / f"latency_budget_{tag}_{stamp}.csv"
    with csv_path.open("w", newline="") as cf:
        w = csv.DictWriter(cf, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    print(f"cache_hit={cp['cache_hit']}  ->  {csv_path}")


if __name__ == "__main__":
    main()
