
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

- **A tiny orchestrator** that reads `src/agent_orchestrator/workflows/workflow.yaml`, launches a wrapper (your `codex exec` shim), and watches for **Run Report** files.
- **Prompt templates** for the agents you listed (planner, coding, e2e, manual testing, docs, code review, PR manager).
- **A single completion contract**: agents write `run_report.json` files to the repo under `./.agents/run_reports/`.
- **A working demo repo** so you can run end‑to‑end immediately.

---

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the orchestrator against the demo repo and default workflow
python -m agent_orchestrator run --repo ./demo_repo --workflow ./src/agent_orchestrator/workflows/workflow.yaml
```

You should see steps run in order and `*.json` appear in `demo_repo/.agents/run_reports/`.

---

## Minimal Agent Contract (v0)

**Goal:** make orchestration happen by monitoring a single file the agent writes when done.

**Completion signal (required):**

- Path: `<repo>/.agents/run_reports/<run_id>__<step_id>.json`  
- Schema: `schemas/run_report.schema.json`  
- Required fields: `schema, run_id, step_id, agent, status, started_at, ended_at`  
- `status`: `"COMPLETED"` or `"FAILED"`

**Optional log marker (for CI logs/humans):**
```
<<<RUN_REPORT_JSON
{ ...same JSON as the file... }
RUN_REPORT_JSON>>>
```

**Validation guardrails:** The orchestrator and bundled wrappers now reject run reports that keep placeholder artifact or log entries (for example, "<REPLACE ME>"). Always emit concrete artifact paths and log summaries before marking a step complete.

**Recommended env to pass into agents:**
- `RUN_ID`, `STEP_ID`, `REPO_DIR`, `REPORT_PATH`

**Idempotency:** agents should be safe to re‑run; dedupe with `run_id + step_id`.

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

### Module constant
```python
REPORTS_DIR = ".agents/run_reports"
```

### Data classes
```python
class Step:          # static config from YAML
  id, agent, prompt, needs, next_on_success, gates, human_in_the_loop

class StepRuntime:   # dynamic state while running
  status="PENDING" | RUNNING | COMPLETED | FAILED | SKIPPED
  attempts: int
  report_path: Optional[str]
```

### Orchestrator lifecycle

**`__init__(repo_dir, workflow_path)`**
- Loads YAML into `Step` objects, builds `self.step_index`
- Creates a short `run_id`
- Initializes per‑step runtime state
- Ensures `<repo>/.agents/run_reports` exists

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
- Computes `report_path = <repo>/.agents/run_reports/<run_id>__<step_id>.json`
- `subprocess.Popen` invokes the wrapper (configurable via CLI):
  ```bash
  python -m agent_orchestrator run \
    --repo <repo_dir> \
    --workflow <workflow_path> \
    --wrapper <wrapper_path
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
[orchestrator] run_id=3f2c9a1b repo=/path/to/demo_repo
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
python -m agent_orchestrator run \
  --repo /path/to/repo \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --wrapper-arg --profile \
  --wrapper-arg prod
```

Provide either the absolute path or a repository-relative path to the wrapper; the CLI does not scan `src/agent_orchestrator/wrappers/` automatically.

Useful flags:
- `--codex-bin` / `CODEX_EXEC_BIN` to pick the binary.
- `--timeout` to cap runtime.
- `--working-dir` to override the cwd (defaults to the repo).
- Repeat `--wrapper-arg` to pass additional arguments through to `codex exec`.

The wrapper passes `RUN_ID`, `STEP_ID`, `REPO_DIR`, and `REPORT_PATH` env vars to the subprocess
and looks for `<<<RUN_REPORT_JSON ... RUN_REPORT_JSON>>>` markers in stdout; if absent it synthesizes
a report so the rest of the workflow can continue.

---

## Reliability & Scale

- **Idempotency**: name work dirs/branches with `run_id__step_id`; skip if report exists & completed.
- **Retries**: exponential backoff + cap attempts; surface reasons on failure.
- **Concurrency**: per‑repo limits; global WIP; fair scheduling.
- **Timeouts**: hard caps per step; collect partial logs on cancel.
- **Compensation**: trigger follow‑up workflows for rollbacks or fixes when late gates fail.
- **Observability**: structure logs; add OpenTelemetry spans around each step.

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
src/
  agent_orchestrator/
    __init__.py
    __main__.py
    cli.py
    orchestrator.py
    runner.py
    workflow.py
    reporting.py
    gating.py
    state.py
    wrappers/
      claude_wrapper.py
      codex_wrapper.py
      mock_wrapper.py
README.md
pyproject.toml
requirements.txt
sdlc_agents_poc/
  orchestrator.py
  src/agent_orchestrator/workflows/workflow.yaml
  schemas/
    run_report.schema.json
  prompts/
    01_planning.md
    02_coding.md
    03_e2e.md
    04_manual.md
    05_docs.md
    06_code_review.md
    07_pr_manager.md
  docs/
    AGENT_CONTRACT.md
    ARCHITECTURE.md
  demo_repo/
    .agents/
      run_reports/
      artifacts/
    README.md
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
    "demo_repo/.agents/artifacts/3f2c9a1b__code/artifact.txt"
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
