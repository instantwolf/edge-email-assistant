# Running on Windows (RTX 3080 demo machine)

The stack is hybrid, the same as on macOS: n8n and PostgreSQL run in Docker, while Ollama
runs natively on the host for GPU access. On Windows that means CUDA on the RTX 3080 —
gemma4:12b fits in 10 GB VRAM and runs about 3–4× faster than on the M2. n8n reaches Ollama
over `http://host.docker.internal:11434`.

Installing Ollama and pulling models is not enough on its own: n8n also needs the workflow
imported and active and the three Google OAuth credentials signed in. The fast path below
reuses the Mac's n8n volume, so you skip re-importing and re-authorizing.

This page covers only the Windows-specific shell differences. The full setup walkthrough is
`README.md` ("Run it (macOS / Linux)"), backed by `n8nsetup.md`; the Docker, Python, and
`curl` commands there are cross-platform, and only the shell wrappers differ.

## Prerequisites
- **Docker Desktop** (WSL2 backend) — running
- **Python 3** on PATH (`python --version`) — the FrontEnd is stdlib-only, no `pip install`
- **Ollama for Windows** — https://ollama.com/download
- **Git Bash or WSL** *only if* you plan to run the `.sh` eval/seed runners (not needed just to run the demo)

## Bring these two files over from the Mac (they are gitignored — not in the repo)
- **`.env`** — holds `N8N_ENCRYPTION_KEY` + DB/owner passwords
- **`n8n_data_backup.tgz`** — the n8n volume snapshot (workflow, credentials, Google tokens)

> The `N8N_ENCRYPTION_KEY` in `.env` must be the same one used when the backup was created,
> or the stored Google OAuth tokens become undecryptable. Copying the Mac's `.env` verbatim
> guarantees this.

## 1. Ollama (native, CUDA)
Install the Windows build, then pull the models (`ollama pull` fetches the models;
`docker compose up` fetches the container images separately):
```powershell
ollama pull gemma4:12b-it-qat      # the working model (7.2 GB Q4 -> fits 10 GB VRAM)
```
After the first request, confirm GPU offload:
```powershell
ollama ps                          # PROCESSOR column should read 100% GPU
```

## 2. `.env`
Put the Mac's `.env` in the project root. (Fresh instead of restoring? `copy .env.example .env`,
set `POSTGRES_PASSWORD`, and generate `N8N_ENCRYPTION_KEY` — e.g. `openssl rand -hex 24` in Git Bash.)

## 3. n8n state — choose ONE

### Option A — restore the volume (recommended: reuses workflow + credentials + OAuth)
Run this before the first `docker compose up`:
```powershell
docker volume create iotprojectmpc_n8n_data
docker run --rm -v iotprojectmpc_n8n_data:/data -v "${PWD}:/backup" alpine tar xzf /backup/n8n_data_backup.tgz -C /data
```
> The volume name is `<project>_n8n_data`, where `<project>` is the folder name, lowercased
> (Docker Compose v2). If your Windows folder isn't `IotProjectMPC`, either rename it, set
> `COMPOSE_PROJECT_NAME=iotprojectmpc` in `.env`, or check the real name with `docker volume ls`
> after a first `up`. If PowerShell mangles `${PWD}`, use the absolute path in the `-v` mount.

### Option B — fresh setup (no backup)
Follow `n8nsetup.md` → "Fresh n8n": create the owner account, import credentials + workflow,
activate it, then complete the three "Sign in with Google" clicks. Those commands are
`docker` / `curl` / `python` — run the heredoc-style ones from **Git Bash**.

## 4. Start the containers
```powershell
docker compose up -d               # n8n + postgres (images auto-pulled)
docker compose ps                  # both should be Up / healthy
```

## 5. Verify + smoke test
n8n editor: http://localhost:5678 (login from `.env`). Then hit the agent:
```powershell
curl -s -X POST http://localhost:5678/webhook/assistant -H "Content-Type: application/json" -d '{\"sessionId\":\"win\",\"message\":\"What day is it today?\"}'
```
- Sensible answer → the whole chain (n8n → Ollama → response) works.
- `404 ... not registered` → the workflow is inactive. Activate it:
  ```powershell
  docker compose exec n8n n8n update:workflow --id=EmailCalAssist01 --active=true
  docker compose restart n8n
  ```
- Hangs / connection refused to `:11434` → see Troubleshooting (Ollama reachability).

## 6. Google tokens (7-day expiry)
Testing-mode refresh tokens expire after **7 days**. If the restored backup is older than
that (or a Gmail/Calendar/Tasks call returns a "re-authorize" error), redo the three
"Sign in with Google" clicks in the n8n editor (Credentials). **Do this right before the demo**
regardless, and refresh `n8n_data_backup.tgz` afterward if you want a current snapshot.

## 7. FrontEnd (Assistant Console)
`FrontEnd/run.sh` just runs `python3 FrontEnd/server.py`; on Windows call Python directly:
```powershell
python FrontEnd\server.py                                  # -> http://localhost:8080
$env:ENABLE_TRUTH=1; python FrontEnd\server.py             # + live Google ground-truth panel
```
Overrides via env vars: `PORT` (default 8080), `N8N_URL`, `OLLAMA_URL`.

## 8. (Optional) Seed demo data
For deterministic "today's emails" during the demo, with the stack up and tokens valid:
```powershell
python seed\seed_mailbox.py        # inserts 15 synthetic emails + 3 calendar events
python seed\cleanup.py             # remove them afterward
```

## Troubleshooting (Windows-specific)

| Symptom | Cause | Fix |
|---|---|---|
| Agent hangs; container can't reach `:11434` | Ollama bound to host-loopback, not visible to the container | Set a system env var **`OLLAMA_HOST=0.0.0.0`**, restart Ollama. Verify from the container: `docker compose exec n8n node -e "fetch('http://host.docker.internal:11434/api/tags').then(r=>r.text()).then(console.log)"` |
| Restore did nothing / n8n is empty | Volume name mismatch (project = folder name, lowercased) | `docker volume ls`, restore into the actual `<project>_n8n_data`, or set `COMPOSE_PROJECT_NAME=iotprojectmpc` |
| Credentials present but Google calls fail | Stored OAuth tokens expired (>7 days) or `N8N_ENCRYPTION_KEY` mismatch | Re-authorize in n8n; confirm `.env` key matches the backup's |
| `POST /webhook/assistant` → 404 not registered | Workflow inactive (common after import/restart) | `update:workflow --active=true` + `restart n8n` (step 5) |
| Empty/failed calendar reads or writes | The calendar nodes target `GOOGLE_ACCOUNT_EMAIL`; n8n rejects the `primary` alias | Set `GOOGLE_ACCOUNT_EMAIL` in `.env` to your test account's address, then restart n8n |
| `.sh` scripts won't run | No POSIX shell | Use **Git Bash** or WSL; or run the underlying `.py` with `python` directly |

Recovery and daily-start details are in `n8nsetup.md`.
