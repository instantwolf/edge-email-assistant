# Assistant Console — Web UI

A self-contained web front-end for the Email & Calendar Assistant. It gives the
agent a chat interface (covers features F1–F6), lets you **verify** the agent's
actions against live Google state, and turns the evaluation CSVs and resource
metrics into browsable charts.

> **Isolation:** everything lives under `FrontEnd/`. This folder does **not**
> modify `docker-compose.yml`, the workflow, prompts, seed, eval, or metrics.
> The backend runs as a host process and only *reads* from the running stack.

## Requirements

- The main stack already running (`docker compose up -d` + `brew services start ollama`).
- Python 3.9+ — **no pip or npm install needed** (Python standard library only;
  the frontend is plain HTML/CSS/JS with no build step).

## Run

```bash
./FrontEnd/run.sh                 # then open http://localhost:8080
```

**Windows:** `.sh` isn't executable in PowerShell. Run the server directly, or use
the bundled PowerShell port `FrontEnd\run.ps1` (`-Live` for live Google data):

```powershell
$env:ENABLE_TRUTH=1; python -X utf8 FrontEnd\server.py   # direct (drop the env var to keep live data off)
.\FrontEnd\run.ps1 -Live                                 # or the .ps1 wrapper
```

### Enabling live Google data (Workspace + chat drawer)

Off by default. Turn it on any of three ways — pick per taste:

```bash
./FrontEnd/run.sh --live          # flag — this run only
ENABLE_TRUTH=1 ./FrontEnd/run.sh  # env var — this run only
echo 'ENABLE_TRUTH=1' > FrontEnd/run.env   # persistent — always on (gitignored)
```

`run.env` is a gitignored file `run.sh` sources on startup, so it's the way to
make live data stick without typing a flag each time. A `--live` flag or inline
env var still works alongside it.

### Environment overrides (all optional)

| Var | Default | Meaning |
|---|---|---|
| `PORT` | `8080` | UI port |
| `N8N_URL` | `.env` `N8N_PUBLIC_URL` / `http://localhost:5678` | n8n base URL (point at a cloud VM for edge-vs-cloud) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL |
| `ENABLE_TRUTH` | off | `1` enables live Gmail/Calendar/Tasks reads (or use `--live`) |

The chat endpoint requires the **"Email & Calendar Assistant" workflow to be
active** in n8n (otherwise the webhook is unregistered — the UI surfaces this as
an error with a hint).

## Pages

- **Chat** — session sidebar read from the Postgres chat-memory table (click a
  session to restore its transcript = live proof of persistent memory), Markdown
  replies with a per-message latency/status/model footer, a live elapsed-time
  "thinking…" indicator with cancel, error rows for failures, and quick-action
  chips for the flagship queries. Optional **Ground-truth drawer** shows the real
  Gmail/Calendar/Tasks state next to the chat so "I saved 3 tasks" can be checked
  against what Google actually has.
- **Workspace** — a full dashboard of the live data the agent operates on, in
  three panels: **Inbox** (Gmail — sender avatars, unread emphasis, relative
  dates, click a message to read its full body), **Agenda** (Calendar — events
  grouped by day, `[IOT26]` seeded events tagged), and **Tasks** (Google Tasks —
  due-date badges coloured by urgency, notes). Read-only; needs `ENABLE_TRUTH=1`.
- **Eval** — browse runs from `eval/results/`, expand each interaction's output,
  read the scoring notes, and check two or more runs to compare latency per
  interaction (edge vs cloud, across the 5-model matrix — see
  `eval/results/model_comparison.md`).
- **Metrics** — CPU/memory time-series from `metrics/*.csv` (both the container
  `docker stats` format and the host `ps`-based sampler format).
- **Status** — health of n8n / Ollama / Postgres, installed vs loaded Ollama
  models, and a weekly **OAuth re-authorization reminder** (7-day Testing-mode
  token expiry).

## How it integrates (read-only)

| Feature | Source | Access |
|---|---|---|
| Chat | `POST {N8N_URL}/webhook/assistant` | HTTP proxy (adds timing + error capture) |
| Sessions / transcripts | `n8n_chat_histories` table | `docker exec <pg> psql` (read-only `SELECT`) |
| Health | n8n `/healthz`, Ollama `/api/tags`+`/api/ps`, Postgres | HTTP + `docker exec` |
| Eval | `../eval/results/*.{jsonl,csv,md}` | file read |
| Metrics | `../metrics/*.csv` | file read |
| Ground truth *(opt-in)* | Gmail/Calendar/Tasks APIs | mints a token from the n8n-stored refresh token, same mechanism as `seed/google_token.py` |

### A note on the ground-truth panel

It is **off by default**. When enabled (`ENABLE_TRUTH=1`) the backend reuses the
Google OAuth refresh tokens you already authorized inside n8n (exactly what
`seed/google_token.py` does) to make **read-only** Gmail/Calendar/Tasks calls.
No tokens are written to disk by this UI. Leave it off if you don't want the UI
touching Google.

## Architecture

```
Browser ──▶ FrontEnd/server.py (stdlib http, :8080)
              ├─ serves FrontEnd/public/ (SPA)
              ├─ /api/chat        → proxies n8n webhook (+ latency, error capture)
              ├─ /api/sessions    → Postgres chat memory (docker exec psql)
              ├─ /api/health      → n8n / Ollama / Postgres probes
              ├─ /api/eval/*      → reads ../eval/results
              ├─ /api/metrics/*   → reads ../metrics
              └─ /api/truth/*     → live Google reads (opt-in)
```

## Optional workflow enhancements (not required, not applied here)

Two small changes to `workflows/email_calendar_assistant.json` would enrich the
UI but touch files outside this folder, so they are intentionally left for the
project owner:

1. Return `{output, executionId, startedAt, finishedAt}` from a *Respond to
   Webhook* node → server-side timing + deep links to n8n executions.
2. Make the Ollama model expression `={{ $json.body.model || 'gemma4:12b-it-qat' }}`
   → a live model switcher across the evaluated models.
