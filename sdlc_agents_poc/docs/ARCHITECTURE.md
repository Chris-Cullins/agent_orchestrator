
# Architecture Notes

This PoC favors **choreography over orchestration** while keeping a tiny central loop:
- Agents *publish* completion events by writing run reports.
- The orchestrator *subscribes* by polling the run_reports directory and computing what’s next from the DAG.

In a production version:
- Replace polling with **webhooks / queues** (e.g., Git provider webhooks, Redis Streams/NATS/Kafka).
- Persist run state and history to a database. Store artifacts in object storage with content hashes.
- Surface status via a UI. Attach OpenTelemetry spans around steps.
- Replace the simulated wrapper with your **`codex exec`** runner in a container with resource limits, timeouts, and ephemeral credentials.

## Core entities
- **Workflow**: a named DAG of steps (YAML), versioned.
- **Run**: a single execution of a workflow with `run_id`.
- **Step**: typed unit of work (`agent`, `prompt`, `needs`, `gates`).
- **RunReport**: completion signal JSON with status + artifacts.

## Common gates to wire later
- CI checks green (unit/e2e/static analysis).
- Code review approvals ≥ threshold.
- Security scan passes (SAST/DAST/license).
- Preview deploy health checks.
