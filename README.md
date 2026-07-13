# Email and Calendar Assistant — Agentic AI on Edge utilizing Google-Cloud

## Summary 

A local-SLM AI agent that reads and summarizes email, drafts and sends replies, extracts
deadlines into tasks, and manages calendar events over the **Gmail**, **Google Calendar**,
and **Google Tasks** APIs, with PostgreSQL-backed conversational memory. The agent is an
**n8n workflow** you talk to over one HTTP webhook. **n8n and PostgreSQL are contained as docker container but Ollama is expected to be natively installed on the executing host (for performance reasons)**.
The local agent accesses the Endpoints via OAuth, to Create and Read Emails / Tasks and Events in Google Cloud:

| Tool | Google API | Purpose |
|---|---|---|
| `read_emails` | Gmail | fetch/filter inbox (Gmail search syntax) |
| `send_email` | Gmail | send a reply/new mail |
| `list_events` | Calendar | list events in a time range (agenda, availability) |
| `create_event` | Calendar | create an event |
| `create_task` | Tasks | save a deadline (time goes in the title — Tasks stores only a date) |
| `list_tasks` | Tasks | list open tasks |
| `current_datetime` | — | resolve relative dates ("today", "this Friday") |


## Infrastructure

It follows a short explanation of local components used in the project and delivered in this repository and the purpose it is used for:

- **n8n** (Docker image): Provides Webhook as Endpoint to access the Workflow; Connects the local agent, the predefined toolset (via MCP) and defines a short system prompt. Additionally a tool that injects the current timestamp to the agent to properly resolve inclomplete/relative time expressions (e.g. next Friday)

- **PostgreSQL** (Docker image) : Persisent Chat Memory - Stores the conversations keyed under a session-key in the database (fetched and loaded by frontend)

- **Agent** (separate installation - Plug&Play): The agent that is connected to the **n8n** workflow. It will determines which tools to call and try to execute the users request. 

## Prerequisites

| Tool | Function/Purpose | Comments/Ressources |
|---|---|---|
| **Docker Desktop** | runs n8n + PostgreSQL as containers | https://www.docker.com/products/docker-desktop — install and start it (`docker compose version` should work) |
| **Ollama** | the local LLM runtime; runs natively for GPU access | `brew install ollama` (macOS) or https://ollama.com/download; the models are pulled below |
| **Python 3** | seed/eval/demo scripts and the FrontEnd (stdlib only — no `pip install`) | verify `python3 --version` | 
| **Google (test) account + OAuth Client** | the mailbox/calendar/tasks the agent acts on  | Register at https://console.cloud.google.com/ |


## Chosen Model (development default): `gemma4:12b-it-qat`

Chosen for reliability after a five-model evaluation: it was the only model whose write
actions were **API-verified** (the API call was indeed successfully performed and the result is visible in Google Cloud, see [eval/results/model_comparison.md](eval/results/model_comparison.md) and
[performance_metrics.md](eval/results/performance_metrics.md)).
You can still switch the model per request ([Switching models](#switching-models)); how the other evaluated models compared is documented in the [model comparison](eval/results/model_comparison.md). 

> **Developer Note**: One key finding is that smaller Models (1-3B) struggled with tool-calling and request realization in our tests. Gemma 4 E4B might be another viable candidate that was not tested anymore, since the 12B Version in the Q4_0 variant delivered good performance and its memory requirements (6,7GB) do reside in between E4B SFP8 (8,9GB) and E4B Q4_0 (4,5GB). For further information in regards to capabilities and spec , please refer to: [Gemma 4 Model Overview](https://ai.google.dev/gemma/docs/core?hl=en)

## Repository structure

| Path | Content |
|---|---|
| `docker-compose.yml` | n8n + PostgreSQL  |
| `workflows/` | Exported n8n workflow JSON (the agent) |
| `seed/` | Seeding scripts + synthetic email/event/task definitions (ground truth) |
| `eval/` | Interaction script, per-model eval protocol, results + comparison tables |
| `metrics/` | Resource samplers (docker + native host) + collected CSVs |
| `FrontEnd/` | Assistant Console web UI (chat, verification, eval/metrics charts) — see `FrontEnd/README.md` |
| `n8nsetup.md` | n8n setup & login cheat sheet (secrets, restore, token backup) |
| `WINDOWS.md` | Running the stack on the Windows/RTX 3080 demo machine |



## Run it

All commands run from the repo root and use bash syntax — on Windows, run them in **Git Bash**
(PowerShell quotes differently). This is the fresh-install happy path; if you were handed an
`n8n_data_backup.tgz` (workflow + credentials + Google tokens, encrypted with the same
`N8N_ENCRYPTION_KEY`), restore it instead of doing Step 5 — see [n8nsetup.md](n8nsetup.md) →
"Token backup".

### 1. Clone the repo

```bash
git clone https://github.com/instantwolf/Assistant-MCP-IoT.git IotProjectMPC
cd IotProjectMPC
```

Keep the folder name `IotProjectMPC` so the Docker volume names (`iotprojectmpc_*`) match the backup/restore commands in [n8nsetup.md](n8nsetup.md). If you clone elsewhere, set `COMPOSE_PROJECT_NAME=iotprojectmpc` in `.env`.

### 2. Configure `.env`

Fill in these keys; everything else can stay at its default:

| Key | Explanation |
|---|---|
| `POSTGRES_PASSWORD` | password for the PostgreSQL chat-memory database |
| `N8N_ENCRYPTION_KEY` | key n8n uses to encrypt the credentials it stores; must stay constant once credentials exist (and when restoring the n8n volume) |
| `N8N_OWNER_EMAIL` / `N8N_OWNER_PASSWORD` | login for the n8n editor |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | authorize the agent's access to Gmail / Calendar / Tasks (from your Google Cloud OAuth client) |
| `GOOGLE_ACCOUNT_EMAIL` | the test account's Google address — used as the calendar ID the agent reads/writes; the workflow reads it from here, so no node editing needed |
| `TZ` | timezone used to resolve dates and timestamps |

`.env` must exist before Step 4 — `docker compose` reads it. `POSTGRES_USER`/`POSTGRES_DB` and
`N8N_PUBLIC_URL` can stay at their defaults. The LLM model is **not** set here; it lives in the
workflow (see [Where to change things](#where-to-change-things)).

### 3. Pull the model

With Ollama installed and running (see [Prerequisites](#prerequisites)):

```bash
ollama pull gemma4:12b-it-qat      # the working model
```

n8n reaches Ollama on the host at `http://host.docker.internal:11434` — already set in the
shipped "Ollama local" credential, so no change is needed.

### 4. Start the stack

```bash
docker compose up -d       # start n8n + postgres (pulls images on first run)
docker compose ps          # both should be Up; postgres healthy
```

PostgreSQL is internal-only (not published to the host).

### 5. Set up n8n

The owner account, the five credentials (Ollama, Postgres, Gmail, Calendar, Tasks — with the
fixed IDs the workflow expects), the workflow import, and activation are one copy-paste block:
[n8nsetup.md](n8nsetup.md) → **"Fresh n8n"** (run it in bash / Git Bash). It sources your
`.env`, so your secrets stay in one place.

Then finish the Google sign-in in the editor at http://localhost:5678 (log in with your
`N8N_OWNER_*`):

1. **Connect Google** — one real browser consent, required once: **Overview → Credentials** →
   open each of the three Google entries → **Sign in with Google** → accept the "unverified
   app" warning (**Advanced → continue**) → allow all scopes.
2. **Set the calendar ID** — put your test account's address in `GOOGLE_ACCOUNT_EMAIL` in
   `.env` (Step 2); the calendar nodes read it via `{{ $env.GOOGLE_ACCOUNT_EMAIL }}`, so no node
   editing is needed. Restart n8n after changing `.env`. (n8n rejects the `primary` alias — use
   the full address.)

> Testing-mode Google refresh tokens expire after **7 days** — redo the three "Sign in with
> Google" clicks weekly and right before demos/eval runs.

### 6. Verify

```bash
# whole chain: webhook -> agent -> Ollama -> response
curl -s -X POST http://localhost:5678/webhook/assistant -H 'Content-Type: application/json' \
  -d '{"sessionId":"t1","message":"What day is it today?"}'
```

A sensible JSON answer means it all works. If the webhook returns `404 … not registered`, the
workflow is inactive (typical after an n8n restart) — reactivate it:

```bash
docker compose exec n8n n8n update:workflow --id=EmailCalAssist01 --active=true && docker compose restart n8n
```

More health checks:

```bash
docker compose ps                          # n8n / postgres status
ollama ps                                  # which model is loaded (empty = none warm)
curl -s http://localhost:11434/api/tags    # models Ollama has pulled
docker compose logs -f n8n                 # follow n8n logs
```

### 7. Start the FrontEnd (GUI)

```bash
./FrontEnd/run.sh            # -> http://localhost:8080  (--live parameter activates gui display of cloud data)
```

A stdlib-only Python web console (chat, live data, eval/metrics charts) — no install. Details
in [FrontEnd/README.md](FrontEnd/README.md).


## Switching models

The model lives in the workflow's **Ollama Chat Model** node, not in `.env`. Pull it once
(`ollama pull <model>`), then switch either way:

- **Per request (no restart).** The node reads `body.model` and falls back to the default
  (`={{ $('Webhook').first().json.body.model || 'gemma4:12b-it-qat' }}`), so you can override
  it for one call:
  ```bash
  curl -s -X POST http://localhost:5678/webhook/assistant -H 'Content-Type: application/json' \
    -d '{"sessionId":"t1","message":"Summarize today'\''s emails.","model":"<model-you-pulled>"}'
  ```
- **Change the default.** Editor → **Ollama Chat Model** node → set **Model** → Save. Or edit
  the `model` field in `workflows/email_calendar_assistant.json`, re-import it (see
  [n8nsetup.md](n8nsetup.md)), and `docker compose restart n8n`.

Check what's actually loaded with `ollama ps`; the model comparison is in
[eval/results/model_comparison.md](eval/results/model_comparison.md).

## Where to change things

| To change | Where |
|---|---|
| **LLM model (default)** | `workflows/email_calendar_assistant.json` → **Ollama Chat Model** node → `model` field (`… \|\| 'gemma4:12b-it-qat'`); edit in the editor or re-import the JSON |
| **LLM model (single call)** | webhook request body `model` field (see [Switching models](#switching-models)) |
| **Model sampling params** | same node's `options`: `numCtx` (default 8192, overridable via body `numCtx`), `numPredict` (default −1, body `numPredict`), `temperature` (0.2), `keepAlive` (1h) |
| **Calendar ID** | `GOOGLE_ACCOUNT_EMAIL` in `.env` (the `list_events`/`create_event` nodes read it via `{{ $env.GOOGLE_ACCOUNT_EMAIL }}`); n8n rejects the `primary` alias |
| **Agent behaviour / system prompt** | `workflows/…json` → **AI Agent** node → `options.systemMessage` |
| **Ports / passwords / encryption key / timezone** | `.env`: n8n editor+webhook `5678` (published), Ollama `11434`, `POSTGRES_*`, `N8N_ENCRYPTION_KEY`, `N8N_OWNER_*`, `TZ`. FrontEnd port via `PORT` env var (default 8080) |
| **Seed ground-truth data** | `seed/emails.json` (15 emails), `seed/events.json` (3 events); loaded by `seed/seed_mailbox.py`, removed by `seed/cleanup.py` |
| **Demo scenarios** | `seed/demo_scenarios.json` (definitions), driven by `seed/demo.py` (`list` / `seed <id>` / `clean <id>`, self-documenting) |
| **Evaluation config** | `eval/run_all_models.sh`: the `RUNS` list (`<ollama-model> <short> <timeout-s>` per line), the `MACHINE` prefix (env var, default `edge`, namespaces result tags), and the per-model timeouts (smollm2 capped at 120 s, gemma4 given 300 s). Full protocol: [eval/README.md](eval/README.md) |
