#!/usr/bin/env python3
"""Point the workflow's Ollama node at a model and redeploy it.

    python3 eval/switch_model.py llama3.2:3b

Extracted from the inline heredoc in `run_model_eval.sh` so the campaign
orchestrator (study-v3 `phase2-harness/campaign_run.py`) can call it on
Windows too, where the `.sh` runners need Git Bash or WSL.

**The campaign does not normally use this.** `run_interactions.py` sends
`body.model`, so the model is chosen per request and n8n is never restarted —
which matters because n8n prunes execution data on boot and the observation
axis lives in that data. This path exists as the fallback for a host whose
node ignores the per-request override; either way the orchestrator's
`verify-model` step asserts what Ollama actually has resident (§17 excludes a
run on model-switch assertion failure).
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "email_calendar_assistant.json"
WORKFLOW_ID = "EmailCalAssist01"
NODE = "Ollama Chat Model"


def run(cmd, **kw):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise SystemExit(f"failed: {' '.join(cmd)}\n{(r.stderr or '').strip()}")
    return r


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: switch_model.py <ollama-model>")
    model = sys.argv[1]

    doc = json.loads(WORKFLOW.read_text())
    nodes = [n for n in doc["nodes"] if n["name"] == NODE]
    if not nodes:
        raise SystemExit(f"no {NODE!r} node in {WORKFLOW}")
    for n in nodes:
        n["parameters"]["model"] = model

    tmp = pathlib.Path("/tmp/wf_campaign.json")
    tmp.write_text(json.dumps(doc))
    run(["docker", "compose", "cp", str(tmp), "n8n:/tmp/wf.json"])
    run(["docker", "compose", "exec", "-T", "n8n",
         "n8n", "import:workflow", "--input=/tmp/wf.json"])
    run(["docker", "compose", "exec", "-T", "n8n",
         "n8n", "update:workflow", f"--id={WORKFLOW_ID}", "--active=true"])
    print(f"workflow model -> {model}")


if __name__ == "__main__":
    main()
