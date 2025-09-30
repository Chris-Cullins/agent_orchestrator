
# SDLC Agents Orchestrator — PoC

This is a minimal, file-driven proof-of-concept for chaining SDLC agents that run 24/7.
Each step is executed by a thin wrapper that simulates your `codex exec` command and
emits a **run report** JSON to `.agents/run_reports`. The orchestrator monitors those
reports and triggers downstream steps defined in `workflow.yaml`.

> Replace the simulation in `scripts/codex_exec_wrapper.py` with your actual `codex exec`
> invocation to integrate with your real agents.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the orchestrator against the demo repo and default workflow
python orchestrator.py --repo ./demo_repo --workflow ./workflow.yaml
```

You should see the orchestrator launch steps (`plan` → `code` → `e2e` → `manual` → `docs` and `review` → `pr`), and
consecutive `*.json` run reports appear in `demo_repo/.agents/run_reports/`.

## How it works

- `workflow.yaml`: declares a DAG of steps. Each step specifies an `agent` and a `prompt` file.
- `orchestrator.py`: reads the workflow, computes which steps are runnable, spawns the wrapper, and
  polls `.agents/run_reports/` for completion (success/failure). It retries transient failures
  and fans-out to downstream steps when all dependencies are satisfied.
- `scripts/codex_exec_wrapper.py`: a minimal shim that **simulates** your agent run and writes a
  `run_report.json` completion signal plus an `artifact.txt` for demonstration.

### Minimal Agent Contract (v0)

At run completion, each agent **must** write a JSON report (see `schemas/run_report.schema.json`) to:

```
<repo>/.agents/run_reports/<run_id>__<step_id>.json
```

And (optionally) echo the same JSON block to STDOUT wrapped in markers, which the wrapper can forward:

```
<<<RUN_REPORT_JSON
{ ... JSON ... }
RUN_REPORT_JSON>>>
```

The orchestrator only needs the file on disk. The rest is for observability/CI logs.

## Next steps

- Swap the wrapper’s simulation with your `codex exec` CLI.
- Point `repo` at a real repository (on a local checkout or in a container volume).
- Wire in Git provider webhooks for gates (e.g., CI statuses, PR approvals) in place of the current no-op gates.
- Push run events to a durable queue (e.g., Redis Streams, SQS, NATS) and persist run state (e.g., Postgres) for scale.
