
# Agent Contract (v0)

**Goal:** Let the orchestrator trigger the next step by simply *monitoring a file the agent writes*.

## Completion signal
- Write a JSON file at: `<repo>/.agents/run_reports/<run_id>__<step_id>.json`
- Shape: `schemas/run_report.schema.json`

## Optional STDOUT marker
If your execution fabric exposes logs (CI, console), also print:

```
<<<RUN_REPORT_JSON
{ ...same JSON... }
RUN_REPORT_JSON>>>
```

The orchestrator does **not** depend on the STDOUT marker — it's just for humans and log collectors.

## Env passed to agents (recommended)
- `RUN_ID`: workflow run correlation id
- `STEP_ID`: current step id (e.g., `coding`)
- `REPO_DIR`: filesystem path to repo workspace
- `REPORT_PATH`: absolute path to write the completion JSON

## Idempotency
Agents should be safe to re-run. The orchestrator may retry a failed step once by default.
Use `run_id` + `step_id` to dedupe work (e.g., skip if artifact already exists).

## Human-in-the-loop steps
For steps with `human_in_the_loop: true`, the agent should output a checklist and wait for a
`manual_result.json` to appear (e.g., in `.agents/run_inputs/<run_id>__manual.json`) created by a human or bot.
This PoC doesn't implement the pause/resume yet; it's a stub to connect later to Slack/Jira.
