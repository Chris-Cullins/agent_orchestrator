
# SDLC Agents Orchestrator — Complete Guide (Markdown Edition)

A minimal, file-driven orchestration pattern to run SDLC agents 24/7 without rewriting them.  
Each agent run writes a **Run Report** JSON file that the orchestrator monitors to trigger the next step.

---

## Table of Contents

1. [What You Get](#what-you-get)
2. [Quick Start](#quick-start)
3. [Minimal Agent Contract (v0)](#minimal-agent-contract-v0)
4. [Workflow & Agent Types](#workflow--agent-types)
5. [orchestrator.py — Guided Walkthrough](#orchestratorpy--guided-walkthrough)
6. [Swap In Your Real `codex exec`](#swap-in-your-real-codex-exec)
7. [Reliability & Scale](#reliability--scale)
8. [Security & Governance](#security--governance)
9. [Extending the PoC](#extending-the-poc)
10. [TL;DR](#tldr)
11. [Appendix A: File Layout](#appendix-a-file-layout)
12. [Appendix B: Sample Run Report JSON](#appendix-b-sample-run-report-json)

---

## What You Get

- **A production orchestrator** that loads `src/agent_orchestrator/workflows/workflow.yaml`, invokes the configured wrapper, and reacts to **Run Report** files.
- **Prompt templates** for the agents you listed (planner, coding, e2e, manual testing, docs, code review, PR manager).
- **A single completion contract**: every step writes `<run_id>__<step_id>.json` to `<repo>/.agents/runs/<run_id>/reports/`.
- **Guaranteed per-run scaffolding** under `<repo>/.agents/runs/<run_id>/`—reports, logs, artifacts, optional `manual_inputs/`, and `run_state.json` for resume support.
- **GitHub issue workflow handoffs**: when you export `ISSUE_NUMBER`, the orchestrator writes `artifacts/gh_issue_<ISSUE_NUMBER>.md` and injects `ISSUE_MARKDOWN_PATH`, `ISSUE_MARKDOWN_DIR`, and `ISSUE_MARKDOWN_FILENAME` for downstream steps.

---

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .

# Optional: confirm your wrappers are reachable or set explicit binaries
codex --version  # For Codex runs (optional)
claude --version # For Claude runs (optional)
# export CODEX_EXEC_BIN=/absolute/path/to/codex
# export CLAUDE_CLI_BIN=/absolute/path/to/claude

python -m agent_orchestrator.cli run \
  --repo /absolute/path/to/your/target/repo \
  --workflow src/agent_orchestrator/workflows/workflow_pr_review_fix.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py
```

If you skip the editable install, prefix orchestrator commands with `PYTHONPATH=src` so Python resolves the package.

Each run creates `<target-repo>/.agents/runs/<run_id>/` with `reports/`, `logs/`, `artifacts/`, and (when you pass `--pause-for-human-input`) a `manual_inputs/` directory plus the persisted `run_state.json` used by `--start-at-step` resumes.

---

## Minimal Agent Contract (v0)

**Goal:** make orchestration happen by monitoring a single file the agent writes when done.

**Completion signal (required):**

- Path: `<repo>/.agents/runs/<run_id>/reports/<run_id>__<step_id>.json`
- Schema: `schemas/run_report.schema.json` (JSON Schema draft 2020-12)
- Required fields: `schema, run_id, step_id, agent, status, started_at, ended_at`
- `status`: `"COMPLETED"` or `"FAILED"`
- `started_at` / `ended_at` must be timezone-aware ISO 8601 UTC strings—call `src/agent_orchestrator/time_utils.utc_now()` to stay compatible with Python 3.13+
- Optional loop-back flag: set `"gate_failure": true` to trigger `loop_back_to` targets when a quality gate fails; leave it false or omit it to continue downstream steps.

**Optional log marker (for CI logs/humans):**
```
<<<RUN_REPORT_JSON
{ ...same JSON as the file... }
RUN_REPORT_JSON>>>
```

**Validation guardrails:** The orchestrator and bundled wrappers now reject run reports that keep placeholder artifact or log entries (for example, "<REPLACE ME>"). Always emit concrete artifact paths and log summaries before marking a step complete.

**Optional schema validation:** The `schemas/run_report.schema.json` file provides a formal JSON Schema definition for run reports. While the orchestrator does not require schema validation at runtime (it relies on placeholder detection and field presence checks), teams can optionally validate run reports against the schema using standard JSON Schema validators:

```bash
# Example using Python jsonschema library
pip install jsonschema
python -c "
import json
from jsonschema import validate
schema = json.load(open('schemas/run_report.schema.json'))
report = json.load(open('<path-to-run-report>.json'))
validate(instance=report, schema=schema)
print('Valid!')
"
```

This is useful for CI pipelines, custom tooling, or debugging malformed reports.

**Recommended env to pass into agents:**
- `RUN_ID`, `STEP_ID`, `REPO_DIR`, `REPORT_PATH`, `ARTIFACTS_DIR`
- GitHub issue workflows also receive `ISSUE_NUMBER`, `ISSUE_MARKDOWN_PATH`, `ISSUE_MARKDOWN_DIR`, and `ISSUE_MARKDOWN_FILENAME` so planners, coders, and docs can link to the generated Markdown snapshot.

**Idempotency:** agents should be safe to re‑run; dedupe with `run_id + step_id`.

### Repository-Level Prompt Overrides

Override any built-in prompt by dropping a file with the same name under `.agents/prompts/` inside the target repository. The orchestrator now resolves prompts by checking repository-specific overrides first and falls back to `src/agent_orchestrator/prompts/` only when no override exists. This lets teams customize tone, guardrails, and acceptance criteria without forking the orchestrator or editing workflow YAML.

---

## Workflow & Agent Types

The default DAG fans out and converges like this:

```
plan → code → e2e → manual → docs ┐
                                 └→ pr
                      manual → review ┘
```

**`src/agent_orchestrator/workflows/workflow.yaml` (excerpt):**
```yaml
name: default
description: Minimal SDLC pipeline with chained agents
steps:
  - id: plan
    agent: work_planner
    prompt: prompts/01_planning.md
    needs: []
    next_on_success: [code]

  - id: code
    agent: coding
    prompt: prompts/02_coding.md
    needs: [plan]
    next_on_success: [e2e]

  - id: e2e
    agent: e2e_test_writer
    prompt: prompts/03_e2e.md
    needs: [code]
    gates:
      - ci.tests: passed
    next_on_success: [manual]

  - id: manual
    agent: manual_testing
    prompt: prompts/04_manual.md
    needs: [e2e]
    human_in_the_loop: true
    next_on_success: [docs, review]

  - id: docs
    agent: docs_updater
    prompt: prompts/05_docs.md
    needs: [manual]
    next_on_success: [pr]

  - id: review
    agent: code_review
    prompt: prompts/06_code_review.md
    needs: [manual]
    next_on_success: [pr]

  - id: pr
    agent: pr_manager
    prompt: prompts/07_pr_manager.md
    needs: [docs, review]
    merge_conditions:
      - all_checks_passed
      - approval_count>=1
    next_on_success: []
```

Prompt templates live under `prompts/*.md` and each ends with the same instruction: **write the Run Report to `${REPORT_PATH}`**.

---

## orchestrator.py — Guided Walkthrough

**Big picture:** a tiny scheduler that loads a DAG, launches steps async, and advances when it sees Run Reports on disk.

### Run directory layout
```python
self._run_dir = repo_dir / ".agents" / "runs" / run_id
self._reports_dir = self._run_dir / "reports"
self._logs_dir = self._run_dir / "logs"
self._artifacts_dir = self._run_dir / "artifacts"
self._manual_inputs_dir = self._run_dir / "manual_inputs"
```

### Data classes
```python
class Step:          # static config from YAML
  id, agent, prompt, needs, loop_back_to, next_on_success, gates, human_in_the_loop

class StepRuntime:   # dynamic state while running
  status="PENDING" | RUNNING | COMPLETED | FAILED | SKIPPED
  attempts: int
  iteration_count: int
  report_path: Optional[str]
```

### Orchestrator lifecycle

**`__init__(repo_dir, workflow_path)`**
- Loads YAML into `Step` objects and builds `self.step_index`
- Creates a short `run_id`
- Initializes per-step runtime state
- Creates `<repo>/.agents/runs/<run_id>/` with `reports/`, `logs/`, `artifacts/`, optional `manual_inputs/`, and `run_state.json`

**`_load_workflow(path)`**
- Parses YAML and constructs typed steps
- Returns the workflow dict with `steps` replaced by `Step` instances

**`_deps_satisfied(step_id)`**
- True only if **all** `needs` are `COMPLETED`

**`_gates_open(step_id)`**
- PoC returns `True`; in production, check CI, approvals, security, etc.

**`_runnable_steps()`**
- Returns steps that are `PENDING` + deps satisfied + gates open

**`_launch(step_id)`**
- Marks step `RUNNING`, increments attempts
- Computes `report_path = <repo>/.agents/runs/<run_id>/reports/<run_id>__<step_id>.json`
- `subprocess.Popen` invokes the wrapper (configurable via CLI):
  ```bash
  python -m agent_orchestrator.cli run \
    --repo <repo_dir> \
    --workflow <workflow_path> \
    --wrapper <wrapper_path>
  ```
- Non‑blocking; multiple independent steps can run concurrently

**`_collect_reports()`**
- For each `RUNNING` step, if `report_path` exists, read it
- If JSON `status` is `COMPLETED` or `FAILED`, update runtime
- On `FAILED` and `attempts < 2`, mark back to `PENDING` to retry once

**`run()`**
- Loop:
  1. Launch `_runnable_steps()`
  2. `_collect_reports()`
  3. (Fan‑out happens naturally via `needs` + `next_on_success`)
  4. Sleep 0.5s to avoid busy loop
  5. Exit when all steps are `COMPLETED`/`SKIPPED`

**Improved terminal condition (suggested):**
```python
all_done = all(st.status in {"COMPLETED", "SKIPPED"} for st in self.state.values())
any_failed = any(st.status == "FAILED" for st in self.state.values())
nothing_left = not self._runnable_steps() and not any(st.status == "RUNNING" for st in self.state.values())
if all_done or (any_failed and nothing_left):
    break
```

### Runtime feel (typical log)
```
[orchestrator] run_id=3f2c9a1b repo=/path/to/target_repo
[orchestrator] starting workflow
[orchestrator] launching step=plan agent=work_planner
[orchestrator] step=plan finished status=COMPLETED
...
[orchestrator] launching step=pr agent=pr_manager
[orchestrator] step=pr finished status=COMPLETED
[orchestrator] workflow completed
```

---

## Using Production AI Agent Wrappers

Point the orchestrator at `src/agent_orchestrator/wrappers/codex_wrapper.py` or `src/agent_orchestrator/wrappers/claude_wrapper.py` for production-ready AI agent integration.
It shells out to `codex exec`, forwards extra CLI arguments, streams logs, and guarantees a compliant run
report even when the agent forgets to emit one. Example:

```bash
python -m agent_orchestrator.cli run \
  --repo /path/to/repo \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --wrapper-arg --profile \
  --wrapper-arg prod
```

Always pass the full or relative path to the wrapper script—the CLI does not search inside `src/agent_orchestrator/wrappers/` for you.

Useful overrides:
- Pass `--wrapper-arg --codex-bin` or export `CODEX_EXEC_BIN` to choose a custom Codex binary (Claude wrapper honors `--wrapper-arg --claude-bin` and `CLAUDE_CLI_BIN`).
- Add `--wrapper-arg --timeout` to cap wrapper runtime in seconds.
- Add `--wrapper-arg --working-dir /alt/path` to change the Codex working directory (defaults to the repo checkout).
- Use multiple `--wrapper-arg` values to forward additional Codex/Claude CLI options after the wrapper-managed flags.
- Combine with orchestrator flags such as `--max-iterations`, `--max-attempts`, and `--pause-for-human-input` when you need tighter control.

The wrapper passes `RUN_ID`, `STEP_ID`, `REPO_DIR`, `REPORT_PATH`, and `ARTIFACTS_DIR` env vars to the subprocess
and looks for `<<<RUN_REPORT_JSON ... RUN_REPORT_JSON>>>` markers in stdout; if absent it synthesizes
a report so the rest of the workflow can continue.

---

## Reliability & Scale

- **Per-run isolation**: every launch receives a unique `run_id` and dedicated `.agents/runs/<run_id>/` directory so retries never clobber prior attempts.
- **Retries & loop-back caps**: configurable `--max-attempts` retries failed steps, and `--max-iterations` guards against infinite loop-backs when gates fail.
- **Run report ingestion**: transient JSON parse failures are retried automatically and ultimately surface a `RunReportError` with the full path for investigation.
- **Wrapper safety valves**: Codex/Claude wrappers expose `--timeout`, `--working-dir`, and binary override flags to keep external processes predictable.
- **Resume support**: `run_state.json` persists in each run directory so `--start-at-step` can rewind a specific step without losing upstream progress.
- **Concurrent readiness**: the orchestrator launches any dependency-satisfied steps immediately, so parallel branches progress in lockstep without manual scheduling.
- **Operator alerts**: optional SMTP notifications (configured in `config/email_notifications.yaml`) announce step failures and human-input pauses with run IDs, attempts, and recent log excerpts.

---

## Security & Governance

- **Branch protection**: only PR Manager merges to protected branches after gates.
- **Least privilege**: short‑lived tokens; no long‑lived PATs in prompts.
- **Sandboxing**: containerize agent runs with CPU/memory caps & network policies.
- **Policy engine**: block merges if sensitive paths change or if SBOM/license checks fail.
- **Human approval**: require ≥1 approval for risky diffs (size, sensitive areas).

---

## Extending the PoC

- Replace polling with **webhooks/queues** (Git provider checks, Redis Streams/NATS).
- Persist runs/reports to Postgres; store artifacts in S3/GCS.
- Add **gates**: CI green, approval thresholds, SAST/DAST, preview deploy health.
- Add **pause/resume** for `human_in_the_loop` steps (Slack/Jira signal drops a `manual_result.json`).
- Multi‑repo, multi‑branch scheduling with quotas and budgets.

---

## TL;DR

- Keep **agents simple**; don’t rewrite them.
- Standardize a tiny **Run Report** JSON they write on completion.
- Drive everything with a **DAG + gates** from a tiny orchestrator.

---

## Appendix A: File Layout

```
agent_orchestrator/
├── schemas/
│   └── run_report.schema.json   # JSON Schema for run report validation
├── src/agent_orchestrator/
│   ├── cli.py
│   ├── orchestrator.py
│   ├── runner.py
│   ├── workflow.py
│   ├── reporting.py
│   ├── time_utils.py
│   ├── gating.py
│   ├── state.py
│   ├── prompts/
│   ├── workflows/
│   └── wrappers/
│       ├── claude_wrapper.py
│       └── codex_wrapper.py
├── tests/
├── AGENTS.md
├── config/
│   └── email_notifications.yaml
├── PLAN.md
├── README.md
├── requirements.txt
└── sdlc_agents_orchestrator_guide.md

target-repo/
└── .agents/
    └── runs/<run_id>/
        ├── reports/
        ├── logs/
        ├── artifacts/
        ├── manual_inputs/  # created when --pause-for-human-input is enabled
        └── run_state.json
```

---

## Appendix B: Sample Run Report JSON

```json
{
  "schema": "run_report@v0",
  "run_id": "3f2c9a1b",
  "step_id": "code",
  "agent": "coding",
  "status": "COMPLETED",
  "started_at": "2025-09-30T12:00:00Z",
  "ended_at":   "2025-09-30T12:05:42Z",
  "artifacts": [
    "path/to/branch-or-diff",
    "target_repo/.agents/runs/3f2c9a1b/artifacts/code/diff.patch"
  ],
  "metrics": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_ms": 342000
  },
  "logs": [
    "Simulated agent run completed."
  ],
  "next_suggested_steps": []
}
```
