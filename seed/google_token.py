#!/usr/bin/env python3
"""Mint a fresh Google access token from the OAuth credentials stored in n8n.

Reuses the refresh tokens created by signing in through the n8n UI, so seeding
and cleanup scripts don't need a separate OAuth client. Requires the docker
stack to be up; prints the token to stdout.

Credential IDs: GmailOAuth000001 (Gmail), GCalOAuth0000001 (Calendar),
GTasksOAuth00001 (Tasks).
"""
import json
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def _ssl_context():
    """CA bundle fallback for python.org macOS builds without installed certs."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    if Path("/etc/ssl/cert.pem").exists():
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


SSL_CTX = _ssl_context()


def urlopen(req, **kwargs):
    return urllib.request.urlopen(req, context=SSL_CTX, **kwargs)


EXPORT_CMD = (
    "n8n export:credentials --all --decrypted --output=/tmp/dc.json >/dev/null 2>&1"
    " && cat /tmp/dc.json && rm -f /tmp/dc.json"
)


def get_token(cred_id: str) -> str:
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "n8n", "sh", "-c", EXPORT_CMD],
        check=True, capture_output=True, text=True,
    ).stdout
    creds = json.loads(out)
    cred = next((c for c in creds if c["id"] == cred_id), None)
    if cred is None:
        raise SystemExit(f"credential {cred_id} not found in n8n")
    data = cred["data"]
    tok = data.get("oauthTokenData") or {}
    refresh_token = tok.get("refresh_token")
    if not refresh_token:
        # fall back to the stored access token (may be expired)
        access = tok.get("access_token")
        if access:
            return access
        raise SystemExit(f"credential {cred_id} has no tokens - sign in via n8n UI first")
    body = urllib.parse.urlencode({
        "client_id": data["clientId"],
        "client_secret": data["clientSecret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    with urlopen(req) as resp:
        return json.load(resp)["access_token"]


if __name__ == "__main__":
    cred = sys.argv[1] if len(sys.argv) > 1 else "GmailOAuth000001"
    print(get_token(cred))
