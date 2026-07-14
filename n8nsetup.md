## n8n Setup & Login — Cheat Sheet

The condensed reference for the n8n-specific pieces: where secrets live, the fresh-setup
commands, the Google sign-in, and token backup/restore. The full end-to-end walkthrough is
the root `README.md` ("Run it" section); come here when you already know the flow.

### Where secrets live
- **`.env`** (repo root, gitignored — template: `.env.example`):
  - `N8N_OWNER_EMAIL` / `N8N_OWNER_PASSWORD` — n8n editor login
  - `N8N_ENCRYPTION_KEY` — encrypts credentials stored inside n8n. **Never change it once credentials exist**, and reuse the same key when moving/restoring the n8n volume.
  - `POSTGRES_USER/PASSWORD/DB` — chat-memory database
  - optional: `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` — enables pre-filling the Google credentials on restore (see below)
- **Google OAuth Client ID/Secret**: Google Cloud Console → APIs & Services → Credentials (OAuth client "n8n")

### Daily start & login
```bash
brew services start ollama    # native LLM runtime (Metal)
docker compose up -d          # n8n + postgres
```
n8n editor: http://localhost:5678 — log in with `N8N_OWNER_EMAIL` / `N8N_OWNER_PASSWORD` from `.env`.

### Fresh n8n (first run or after a Docker wipe)
1. **Owner account** (same login as in `.env`):
   ```bash
   source .env
   curl -X POST http://localhost:5678/rest/owner/setup -H 'Content-Type: application/json' \
     -d "{\"email\":\"$N8N_OWNER_EMAIL\",\"firstName\":\"Wolfgang\",\"lastName\":\"Prett\",\"password\":\"$N8N_OWNER_PASSWORD\"}"
   ```
2. **Import credentials + workflow** (IDs must match the workflow references — don't rename):
   ```bash
   source .env
   cat > /tmp/n8n_creds.json <<EOF
   [
     {"id":"OllamaLocal00001","name":"Ollama local","type":"ollamaApi","data":{"baseUrl":"http://host.docker.internal:11434"}},
     {"id":"PgMemory00000001","name":"Postgres memory","type":"postgres","data":{"host":"postgres","port":5432,"database":"$POSTGRES_DB","user":"$POSTGRES_USER","password":"$POSTGRES_PASSWORD","ssl":"disable","sshTunnel":false}},
     {"id":"GmailOAuth000001","name":"Gmail (test account)","type":"gmailOAuth2","data":{"clientId":"$GOOGLE_OAUTH_CLIENT_ID","clientSecret":"$GOOGLE_OAUTH_CLIENT_SECRET"}},
     {"id":"GCalOAuth0000001","name":"Google Calendar (test account)","type":"googleCalendarOAuth2Api","data":{"clientId":"$GOOGLE_OAUTH_CLIENT_ID","clientSecret":"$GOOGLE_OAUTH_CLIENT_SECRET"}},
     {"id":"GTasksOAuth00001","name":"Google Tasks (test account)","type":"googleTasksOAuth2Api","data":{"clientId":"$GOOGLE_OAUTH_CLIENT_ID","clientSecret":"$GOOGLE_OAUTH_CLIENT_SECRET"}}
   ]
   EOF
   docker compose cp /tmp/n8n_creds.json n8n:/tmp/creds.json && rm /tmp/n8n_creds.json
   docker compose exec n8n n8n import:credentials --input=/tmp/creds.json
   docker compose cp workflows/email_calendar_assistant.json n8n:/tmp/wf.json
   docker compose exec n8n n8n import:workflow --input=/tmp/wf.json
   docker compose exec n8n n8n update:workflow --id=EmailCalAssist01 --active=true
   docker compose restart n8n
   ```
3. **Connect Google** (manual, ~2 min — a real browser consent is required):
   n8n → Overview → Credentials → open **each of the 3 Google entries**
   (`Gmail (test account)`, `Google Calendar (test account)`, `Google Tasks (test account)`) →
   (paste Client ID/Secret if not pre-filled from `.env`) → **Sign in with Google** →
   "unverified app" warning → Advanced → continue → allow all → **Save**.

   > ⚠️ This is **not** a one-time step. While the OAuth consent screen is in **Testing**
   > mode, Google refresh tokens **expire after 7 days** — after which every ground-truth
   > widget fails with `HTTP Error 400: Bad Request — re-authorize Google in n8n`. Redo
   > this same step to re-authorize (see [Recurring chore](#recurring-chore) for the
   > permanent fix). Do it right before any eval run or demo.
4. **Test:**
   ```bash
   curl -X POST http://localhost:5678/webhook/assistant -H 'Content-Type: application/json' \
     -d '{"sessionId":"t1","message":"What day is it today?"}'
   ```

### Token backup (avoids re-sign-in after Docker wipes)
After signing in, snapshot the n8n volume (tokens inside are encrypted with `N8N_ENCRYPTION_KEY`):
```bash
docker run --rm -v iotprojectmpc_n8n_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/n8n_data_backup.tgz -C /data .        # keep OUT of git
```
Restore into a fresh volume (before `docker compose up`):
```bash
docker volume create iotprojectmpc_n8n_data
docker run --rm -v iotprojectmpc_n8n_data:/data -v "$PWD":/backup alpine \
  tar xzf /backup/n8n_data_backup.tgz -C /data
```

### Recurring chore
OAuth consent screen is in **Testing** mode → Google refresh tokens **expire every 7 days**.
Symptom once expired: the frontend ground-truth widgets all fail with
`token refresh failed for GmailOAuth000001: HTTP Error 400: Bad Request — re-authorize Google in n8n`.

**Re-authorize (weekly, and always right before eval runs or the demo):**
n8n → Overview → **Credentials** → open **each of the 3 Google entries** → **Sign in with
Google** → Advanced → continue → allow all → **Save**. Then reload the frontend (no restart
needed — it reads the refreshed token from n8n).

**Permanent fix (recommended):** publish the OAuth app so tokens stop expiring —
Google Cloud Console → APIs & Services → **OAuth consent screen** → **Publish app**
("In production"). For your own account this removes the 7-day expiry; you'll just bypass an
"unverified app" warning on the next consent.