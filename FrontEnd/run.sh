#!/usr/bin/env bash
# Start the Assistant Console (stdlib only — no pip/npm install needed).
#
# Live Google data (the Workspace page + the chat ground-truth drawer) is OFF by
# default. Turn it on with any ONE of these:
#   ./FrontEnd/run.sh --live               # flag — this run only
#   ENABLE_TRUTH=1 ./FrontEnd/run.sh       # env var — this run only
#   echo 'ENABLE_TRUTH=1' > FrontEnd/run.env   # persistent — always on (gitignored)
#
# Other overrides (env vars): PORT (default 8080), N8N_URL, OLLAMA_URL.
set -euo pipefail
cd "$(dirname "$0")/.."

# Persistent local config, if present (gitignored). Values here are the baseline;
# a --live flag or an inline env var on this command still take effect below.
if [ -f FrontEnd/run.env ]; then
  set -a; . FrontEnd/run.env; set +a
fi

# Convenience flags
for arg in "$@"; do
  case "$arg" in
    --live|--truth) export ENABLE_TRUTH=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

exec python3 FrontEnd/server.py
