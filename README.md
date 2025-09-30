# SDLC Agents Orchestrator

A production-ready, file-driven orchestrator for chaining SDLC agents via run report files.

This package elevates the original PoC in `sdlc_agents_poc/` into a reusable CLI and Python
package that can launch real `codex exec` runs, watch for run reports, enforce DAG
dependencies, retry failures, and pause for human-in-the-loop steps.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the default workflow against the demo repo using the existing PoC wrapper
python -m agent_orchestrator run \
  --repo ./sdlc_agents_poc/demo_repo \
  --workflow ./sdlc_agents_poc/workflow.yaml \
  --wrapper ./sdlc_agents_poc/scripts/codex_exec_wrapper.py
```

As steps finish, run reports land in `<repo>/.agents/run_reports/` and live state is
captured in `<repo>/.agents/run_state.json`. Logs for each step are written to
`<repo>/.agents/logs/`.

### Running against real agents

Swap the wrapper out for your actual execution fabric by providing a command template.
Placeholders enclosed in braces are replaced at launch time.

```bash
python -m agent_orchestrator run \
  --repo /path/to/checkout \
  --workflow workflows/web-app.yaml \
  --command-template "codex exec --agent {agent} --prompt {prompt} --repo {repo} --report {report}"
```

### Gate and manual input integration

- Provide `--gate-state-file <path>` with a JSON object like `{ "ci.tests: passed": true }`
  to back workflow gates from CI, approvals, etc.
- Add `--pause-for-human-input` if you want human-in-the-loop steps to pause until a file is
  dropped at `<repo>/.agents/run_inputs/<run_id>__<step_id>.json`.


### Bundled `codex exec` wrapper

A production shim lives at `src/agent_orchestrator/wrappers/codex_exec_wrapper.py`. Point the orchestrator to it:

```bash
python -m agent_orchestrator --log-level INFO run \
  --repo /path/to/checkout \
  --workflow workflows/web-app.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_exec_wrapper.py \
  --wrapper-arg --profile \
  --wrapper-arg prod
```

Key flags:
- `--codex-bin` (or `CODEX_EXEC_BIN`) changes the binary name/path.
- `--timeout` aborts long-running executions.
- `--working-dir` overrides the subprocess cwd (defaults to the repo).
- Repeat `--wrapper-arg` to pass extra arguments to `codex exec`.

The wrapper streams stdout/stderr into the orchestrator log, parses any 
`<<<RUN_REPORT_JSON ... RUN_REPORT_JSON>>>` block, and always writes a compliant
report to `${REPORT_PATH}` so downstream orchestration keeps flowing.

## Project layout

- `src/agent_orchestrator/` — package code (orchestrator core, CLI, contracts).
- `README.md` — this guide.
- `requirements.txt` — runtime dependencies.
- `sdlc_agents_poc/` — original proof-of-concept kept for reference and demos.

See `sdlc_agents_orchestrator_guide.md` for a fully annotated walkthrough of the design
and contract.
