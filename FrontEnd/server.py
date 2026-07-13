#!/usr/bin/env python3
"""Assistant Console — backend for the Email & Calendar Assistant web UI.

Self-contained companion to the main project. Lives entirely under FrontEnd/ and
does NOT modify the rest of the repo: it runs as a host process, talks to the
already-running stack over localhost, and reads Postgres chat memory via
`docker exec` (read-only). Nothing here writes to n8n, Postgres, or Google unless
the ground-truth panel is explicitly enabled (ENABLE_TRUTH=1).

Dependencies: none — Python 3.9+ standard library only.

Run:
    python3 FrontEnd/server.py            # serves http://localhost:8080

Environment (all optional):
    PORT            HTTP port for this UI            (default 8080)
    N8N_URL         n8n base URL                     (default from repo .env / http://localhost:5678)
    OLLAMA_URL      Ollama base URL                  (default http://localhost:11434)
    ENABLE_TRUTH    "1" to enable live Google reads  (default off — see README)
"""
import base64
import json
import os
import re
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
PUBLIC = HERE / "public"
EVAL_RESULTS = REPO_ROOT / "eval" / "results"
METRICS_DIR = REPO_ROOT / "metrics"

SESSION_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
RUN_STEM_RE = re.compile(r"^(?P<tag>.+)_(?P<ts>\d{8}T\d{6}Z)$")
FILE_RE = re.compile(r"^(?P<tag>.+)_(?P<ts>\d{8}T\d{6}Z)\.(?P<ext>jsonl|csv)$")

# Credential ids used by the workflow (see n8nsetup.md). Reused for the truth panel.
GOOGLE_CREDS = {"emails": "GmailOAuth000001", "events": "GCalOAuth0000001", "tasks": "GTasksOAuth00001"}


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_env():
    env = {}
    f = REPO_ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.split("#", 1)[0].strip()
    return env


ENV = load_env()
N8N_URL = (os.environ.get("N8N_URL") or ENV.get("N8N_PUBLIC_URL") or "http://localhost:5678").rstrip("/")
OLLAMA_URL = (os.environ.get("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
PG_USER = ENV.get("POSTGRES_USER", "agent")
PG_DB = ENV.get("POSTGRES_DB", "agent_memory")
ENABLE_TRUTH = os.environ.get("ENABLE_TRUTH", "") == "1"
PORT = int(os.environ.get("PORT", "8080"))

_container_cache = {}


def container_id(service):
    """Resolve a compose service to its container id (cached)."""
    if service in _container_cache:
        return _container_cache[service]
    cid = ""
    try:
        cid = subprocess.run(
            ["docker", "compose", "ps", "-q", service],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        cid = cid[0] if cid else ""
    except Exception:
        cid = ""
    if not cid:  # fallback: name match on running containers
        try:
            names = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=10,
            ).stdout.splitlines()
            cid = next((n for n in names if service in n), "")
        except Exception:
            cid = ""
    _container_cache[service] = cid
    return cid


# --------------------------------------------------------------------------- #
# HTTP helpers to the stack
# --------------------------------------------------------------------------- #
def _ssl_context():
    """CA-bundle fallback for python.org macOS builds (mirrors seed/google_token.py)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    if Path("/etc/ssl/cert.pem").exists():
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


SSL_CTX = _ssl_context()


def http_json(method, url, payload=None, timeout=10):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        raw = resp.read()
        body = json.loads(raw) if raw else {}
        return resp.status, body


def psql(sql, timeout=15):
    """Run a read-only query in the postgres container; return raw rows (| separated)."""
    cid = container_id("postgres")
    if not cid:
        raise RuntimeError("postgres container not found (is the stack up?)")
    out = subprocess.run(
        ["docker", "exec", cid, "psql", "-U", PG_USER, "-d", PG_DB,
         "-t", "-A", "-F", "\x1f", "-c", sql],
        capture_output=True, text=True, timeout=timeout,
    )
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "psql failed").strip())
    return [r for r in out.stdout.splitlines() if r != ""]


# --------------------------------------------------------------------------- #
# API endpoints
# --------------------------------------------------------------------------- #
def api_health():
    out = {"n8n": {}, "ollama": {}, "postgres": {}}

    t = time.monotonic()
    try:
        st, _ = http_json("GET", f"{N8N_URL}/healthz", timeout=4)
        out["n8n"] = {"up": st == 200, "latency_ms": round((time.monotonic() - t) * 1000), "url": N8N_URL}
    except Exception as e:
        out["n8n"] = {"up": False, "error": str(e), "url": N8N_URL}

    t = time.monotonic()
    try:
        _, tags = http_json("GET", f"{OLLAMA_URL}/api/tags", timeout=4)
        models = [m["model"] for m in tags.get("models", [])]
        loaded = []
        try:
            _, ps = http_json("GET", f"{OLLAMA_URL}/api/ps", timeout=4)
            loaded = [m["model"] for m in ps.get("models", [])]
        except Exception:
            pass
        out["ollama"] = {"up": True, "latency_ms": round((time.monotonic() - t) * 1000),
                         "models": models, "loaded": loaded, "url": OLLAMA_URL}
    except Exception as e:
        out["ollama"] = {"up": False, "error": str(e), "url": OLLAMA_URL}

    t = time.monotonic()
    try:
        psql("select 1")
        out["postgres"] = {"up": True, "latency_ms": round((time.monotonic() - t) * 1000), "db": PG_DB}
    except Exception as e:
        out["postgres"] = {"up": False, "error": str(e), "db": PG_DB}

    out["truth_enabled"] = ENABLE_TRUTH
    return 200, out


def api_chat(body):
    session_id = str(body.get("sessionId") or "default")
    message = str(body.get("message") or "")
    if not message.strip():
        return 400, {"error": "message is required"}
    payload = {"sessionId": session_id, "message": message}
    t = time.monotonic()
    try:
        req = urllib.request.Request(
            f"{N8N_URL}/webhook/assistant",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read()
            latency = round(time.monotonic() - t, 2)
            try:
                data = json.loads(raw) if raw else {}
                output = data.get("output", "") if isinstance(data, dict) else str(data)
            except Exception:
                output = raw.decode(errors="replace")
            return 200, {"output": output, "latency_s": latency, "status": resp.status, "error": None}
    except urllib.error.HTTPError as e:
        latency = round(time.monotonic() - t, 2)
        detail = e.read().decode(errors="replace")[:600]
        hint = ("webhook not registered — activate the 'Email & Calendar Assistant' "
                "workflow in n8n") if e.code == 404 else ""
        return 200, {"output": "", "latency_s": latency, "status": e.code,
                     "error": (hint + " | " if hint else "") + detail}
    except Exception as e:
        latency = round(time.monotonic() - t, 2)
        return 200, {"output": "", "latency_s": latency, "status": 0, "error": repr(e)}


def api_sessions():
    try:
        rows = psql(
            "select session_id, count(*), max(id) from n8n_chat_histories "
            "group by session_id order by max(id) desc"
        )
    except Exception as e:
        return 200, {"error": str(e), "sessions": []}
    sessions = []
    for r in rows:
        parts = r.split("\x1f")
        if len(parts) < 3:
            continue
        sid, cnt, maxid = parts[0], parts[1], parts[2]
        sessions.append({
            "sessionId": sid, "messages": int(cnt), "seq": int(maxid),
            "kind": "eval" if sid.startswith("eval") else "web",
        })
    return 200, {"sessions": sessions}


def api_session_transcript(sid):
    if not SESSION_RE.match(sid):
        return 400, {"error": "invalid session id"}
    try:
        rows = psql(
            "select message::text from n8n_chat_histories "
            f"where session_id = '{sid}' order by id"
        )
    except Exception as e:
        return 200, {"error": str(e), "messages": []}
    msgs = []
    for r in rows:
        try:
            m = json.loads(r)
            role = "user" if m.get("type") == "human" else "assistant"
            msgs.append({"role": role, "content": m.get("content", "")})
        except Exception:
            continue
    return 200, {"sessionId": sid, "messages": msgs}


def _read_run_file(stem):
    """Return list of interaction dicts for a run stem, preferring jsonl."""
    jl = EVAL_RESULTS / f"{stem}.jsonl"
    if jl.exists():
        items = []
        for line in jl.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass
        return items
    csvf = EVAL_RESULTS / f"{stem}.csv"
    if csvf.exists():
        import csv as _csv
        with csvf.open() as f:
            return [dict(row) for row in _csv.DictReader(f)]
    return []


def _run_summary(items):
    lat = []
    ok = 0
    for it in items:
        try:
            lat.append(float(it.get("latency_s", 0)))
        except Exception:
            pass
        v = it.get("ok")
        if v in (True, "True", "true", "1", 1):
            ok += 1
    lat.sort()
    stats = {"n": len(items), "ok": ok}
    if lat:
        stats.update({"min": lat[0], "median": lat[len(lat) // 2], "max": lat[-1]})
    return stats


def api_eval_runs():
    if not EVAL_RESULTS.exists():
        return 200, {"runs": []}
    stems = {}
    for f in EVAL_RESULTS.iterdir():
        m = FILE_RE.match(f.name)
        if m:
            stems.setdefault(f"{m['tag']}_{m['ts']}", m["tag"])
    runs = []
    for stem, tag in sorted(stems.items(), key=lambda kv: kv[0], reverse=True):
        m = RUN_STEM_RE.match(stem)
        ts = m["ts"] if m else ""
        items = _read_run_file(stem)
        runs.append({
            "id": stem, "tag": tag, "timestamp": ts,
            "hasScoring": (EVAL_RESULTS / f"{tag}_scoring.md").exists(),
            **_run_summary(items),
        })
    return 200, {"runs": runs}


def api_eval_run(stem):
    if not RUN_STEM_RE.match(stem):
        return 400, {"error": "invalid run id"}
    items = _read_run_file(stem)
    if not items:
        return 404, {"error": "run not found"}
    tag = RUN_STEM_RE.match(stem)["tag"]
    scoring = None
    sf = EVAL_RESULTS / f"{tag}_scoring.md"
    if sf.exists():
        scoring = sf.read_text()
    return 200, {"id": stem, "tag": tag, "summary": _run_summary(items),
                 "interactions": items, "scoring": scoring}


def _parse_metric_csv(path):
    import csv as _csv
    with path.open() as f:
        reader = _csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)
    kind = "container" if "container" in headers else ("host" if "command" in headers else "unknown")
    return kind, headers, rows


def api_metrics_files():
    if not METRICS_DIR.exists():
        return 200, {"files": []}
    files = []
    for f in sorted(METRICS_DIR.glob("*.csv")):
        try:
            kind, headers, rows = _parse_metric_csv(f)
            files.append({"name": f.name, "kind": kind, "rows": len(rows), "headers": headers})
        except Exception:
            files.append({"name": f.name, "kind": "unknown", "rows": 0, "headers": []})
    return 200, {"files": files}


def api_metrics_file(name):
    if "/" in name or ".." in name or not name.endswith(".csv"):
        return 400, {"error": "invalid file"}
    path = METRICS_DIR / name
    if not path.exists():
        return 404, {"error": "not found"}
    kind, headers, rows = _parse_metric_csv(path)
    return 200, {"name": name, "kind": kind, "headers": headers, "rows": rows}


# --------------------------------------------------------------------------- #
# Ground truth (opt-in; reuses n8n-stored Google refresh tokens like seed/)
# --------------------------------------------------------------------------- #
_token_lock = threading.Lock()
_token_cache = {}          # cred_id -> (access_token, expires_at_monotonic)
_TOKEN_TTL = 50 * 60       # refresh comfortably before Google's ~1h access-token expiry


def _export_credentials():
    """Decrypt all n8n credentials via the CLI. Uses a unique temp file per call."""
    cid = container_id("n8n")
    if not cid:
        raise RuntimeError("n8n container not found (is the stack up?)")
    export = ('f=$(mktemp) && n8n export:credentials --all --decrypted --output="$f" '
              '>/dev/null 2>&1 && cat "$f" && rm -f "$f"')
    out = subprocess.run(["docker", "exec", cid, "sh", "-c", export],
                         capture_output=True, text=True, timeout=30).stdout
    if not out.strip():
        raise RuntimeError("credential export returned no data")
    return json.loads(out)


def _access_token_from_cred(cred):
    data = cred["data"]
    tok = data.get("oauthTokenData") or {}
    if not tok.get("refresh_token"):
        if tok.get("access_token"):
            return tok["access_token"]
        raise RuntimeError("no tokens — sign in via n8n first")
    body = urllib.parse.urlencode({
        "client_id": data["clientId"], "client_secret": data["clientSecret"],
        "refresh_token": tok["refresh_token"], "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as r:
        return json.load(r)["access_token"]


def _google_token(cred_id):
    """Return a cached Google access token for a credential id.

    Serialized + cached so concurrent Workspace panels share ONE credential
    export instead of racing three `docker exec` calls over the same file (which
    intermittently yields empty output -> 'Expecting value: line 1 column 1').
    A single export refreshes and caches all Google tokens at once.
    """
    now = time.monotonic()
    with _token_lock:
        hit = _token_cache.get(cred_id)
        if hit and hit[1] > now:
            return hit[0]
        creds = _export_credentials()
        wanted = set(GOOGLE_CREDS.values())
        last_err = None
        for cred in creds:
            if cred.get("id") in wanted:
                try:
                    _token_cache[cred["id"]] = (_access_token_from_cred(cred), now + _TOKEN_TTL)
                except Exception as e:
                    last_err = e
        hit = _token_cache.get(cred_id)
        if hit:
            return hit[0]
        if not any(c.get("id") == cred_id for c in creds):
            raise RuntimeError(f"credential {cred_id} not found in n8n")
        raise RuntimeError(f"token refresh failed for {cred_id}: {last_err} — re-authorize Google in n8n")


def _g_get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as r:
        return json.load(r)


def _b64url(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _gmail_plaintext(payload):
    """Extract a readable plain-text body from a Gmail message payload."""
    def walk(p, want):
        if p.get("mimeType") == want and p.get("body", {}).get("data"):
            return _b64url(p["body"]["data"])
        for sub in p.get("parts", []) or []:
            r = walk(sub, want)
            if r:
                return r
        return ""
    txt = walk(payload, "text/plain")
    if not txt:
        html = walk(payload, "text/html")
        if html:
            txt = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", html, flags=re.I)
            txt = re.sub(r"<[^>]+>", " ", txt)
            txt = re.sub(r"[ \t]+", " ", txt)
    return txt.strip()


def api_truth(kind):
    if not ENABLE_TRUTH:
        return 403, {"error": "ground-truth panel disabled. Start with ENABLE_TRUTH=1 to enable "
                              "live Google reads (uses the OAuth tokens stored in n8n)."}
    if kind not in GOOGLE_CREDS:
        return 404, {"error": "unknown kind"}
    try:
        token = _google_token(GOOGLE_CREDS[kind])
        if kind == "emails":
            lst = _g_get("https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=15", token)
            items = []
            for ref in lst.get("messages", [])[:15]:
                msg = _g_get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{ref['id']}"
                             "?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date", token)
                hdr = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                items.append({"id": ref["id"], "from": hdr.get("From", ""),
                              "subject": hdr.get("Subject", "(no subject)"),
                              "unread": "UNREAD" in msg.get("labelIds", []),
                              "date": msg.get("internalDate", ""), "snippet": msg.get("snippet", "")})
            return 200, {"kind": kind, "items": items}
        if kind == "events":
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
            data = _g_get("https://www.googleapis.com/calendar/v3/calendars/primary/events"
                          f"?timeMin={now}&singleEvents=true&orderBy=startTime&maxResults=25", token)
            items = [{"summary": e.get("summary", "(untitled)"),
                      "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", ""),
                      "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date", ""),
                      "allDay": "date" in e.get("start", {}),
                      "location": e.get("location", "")}
                     for e in data.get("items", [])]
            return 200, {"kind": kind, "items": items}
        if kind == "tasks":
            data = _g_get("https://tasks.googleapis.com/tasks/v1/lists/@default/tasks?showCompleted=false&maxResults=20", token)
            items = [{"title": t.get("title", ""), "due": t.get("due", ""),
                      "notes": t.get("notes", ""), "status": t.get("status", "")}
                     for t in data.get("items", [])]
            return 200, {"kind": kind, "items": items}
    except Exception as e:
        return 200, {"kind": kind, "items": [], "error": str(e)}


def api_truth_message(msg_id):
    if not ENABLE_TRUTH:
        return 403, {"error": "ground-truth panel disabled (ENABLE_TRUTH=1)"}
    if not re.match(r"^[A-Za-z0-9_-]+$", msg_id):
        return 400, {"error": "invalid message id"}
    try:
        token = _google_token(GOOGLE_CREDS["emails"])
        msg = _g_get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=full", token)
        hdr = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = _gmail_plaintext(msg.get("payload", {})) or msg.get("snippet", "")
        return 200, {"id": msg_id, "from": hdr.get("From", ""), "subject": hdr.get("Subject", ""),
                     "date": hdr.get("Date", ""), "body": body[:8000]}
    except Exception as e:
        return 200, {"id": msg_id, "body": "", "error": str(e)}


# --------------------------------------------------------------------------- #
# HTTP server
# --------------------------------------------------------------------------- #
ROUTES_GET = {
    "/api/health": lambda h, m: api_health(),
    "/api/sessions": lambda h, m: api_sessions(),
    "/api/eval/runs": lambda h, m: api_eval_runs(),
    "/api/metrics/files": lambda h, m: api_metrics_files(),
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quieter console
        pass

    def _send(self, status, obj):
        payload = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _static(self, path):
        rel = path.lstrip("/") or "index.html"
        target = (PUBLIC / rel).resolve()
        if not str(target).startswith(str(PUBLIC)) or not target.is_file():
            target = PUBLIC / "index.html"  # SPA fallback
        ctype = {
            ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
            ".svg": "image/svg+xml", ".json": "application/json",
        }.get(target.suffix, "application/octet-stream")
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path in ROUTES_GET:
                return self._send(*ROUTES_GET[path](self, None))
            if path.startswith("/api/sessions/"):
                return self._send(*api_session_transcript(urllib.parse.unquote(path.split("/", 3)[3])))
            if path.startswith("/api/eval/runs/"):
                return self._send(*api_eval_run(urllib.parse.unquote(path.split("/", 4)[4])))
            if path.startswith("/api/metrics/files/"):
                return self._send(*api_metrics_file(urllib.parse.unquote(path.split("/", 4)[4])))
            if path.startswith("/api/truth/message/"):
                return self._send(*api_truth_message(urllib.parse.unquote(path.split("/", 4)[4])))
            if path.startswith("/api/truth/"):
                return self._send(*api_truth(path.split("/", 3)[3]))
            if path.startswith("/api/"):
                return self._send(404, {"error": "unknown endpoint"})
            return self._static(path)
        except BrokenPipeError:
            pass
        except Exception as e:
            self._send(500, {"error": repr(e)})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw else {}
        except Exception:
            return self._send(400, {"error": "invalid JSON body"})
        try:
            if parsed.path == "/api/chat":
                return self._send(*api_chat(body))
            return self._send(404, {"error": "unknown endpoint"})
        except Exception as e:
            self._send(500, {"error": repr(e)})


def main():
    print("┌─ Assistant Console ─────────────────────────────────")
    print(f"│ UI        http://localhost:{PORT}")
    print(f"│ n8n       {N8N_URL}")
    print(f"│ ollama    {OLLAMA_URL}")
    print(f"│ postgres  db={PG_DB} (via docker exec)")
    print(f"│ truth     {'ENABLED' if ENABLE_TRUTH else 'disabled (set ENABLE_TRUTH=1)'}")
    print("└─────────────────────────────────────────────────────")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
