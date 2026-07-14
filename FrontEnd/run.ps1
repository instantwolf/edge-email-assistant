# Start the Assistant Console (stdlib only -- no pip/npm install needed).
#
# Live Google data (the Workspace page + the chat ground-truth drawer) is OFF by
# default. Turn it on with any ONE of these:
#   .\FrontEnd\run.ps1 -Live                     # flag -- this run only
#   $env:ENABLE_TRUTH=1; .\FrontEnd\run.ps1      # env var -- this run only
#   'ENABLE_TRUTH=1' | Set-Content FrontEnd\run.env   # persistent -- always on (gitignored)
#
# Other overrides (env vars): PORT (default 8080), N8N_URL, OLLAMA_URL.
param(
    [switch]$Live,
    [switch]$Help
)
$ErrorActionPreference = 'Stop'

# Move to repo root (parent of this script's folder).
Set-Location (Join-Path $PSScriptRoot '..')

if ($Help) {
    Get-Content $PSCommandPath | Select-Object -Skip 1 -First 9
    exit 0
}

# Persistent local config, if present (gitignored). KEY=VALUE lines; a -Live flag
# or an inline env var on this command still take effect below.
$envFile = 'FrontEnd\run.env'
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*([^#=]+)=(.*)$') {
            Set-Item -Path "Env:$($Matches[1].Trim())" -Value $Matches[2].Trim()
        }
    }
}

if ($Live) { $env:ENABLE_TRUTH = '1' }

# Prefer the Windows launcher (py); fall back to python.
$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
& $python -X utf8 FrontEnd\server.py
