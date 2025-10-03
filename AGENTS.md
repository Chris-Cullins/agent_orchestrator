# AGENTS Playbook

This guide captures the exact steps we need to run the SDLC agent orchestrator without trial and error.

## 1. Environment Prep (do once per machine)
- Clone the repo and enter it:
  ```bash
  git clone <repo-url>
  cd agent_orchestrator
  ```
- Create and activate a virtualenv:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate  # Windows: .venv\Scripts\activate
  ```
- Install dependencies and the package in editable mode:
  ```bash
  pip install -r requirements.txt
  pip install -e .
  ```
- Verify your agent binaries are available (match the wrapper you plan to use):
  ```bash
  codex --version  # Codex wrapper
  claude --version # Claude wrapper
  ```

## 2. Command Template You Will Use Every Time
Use this pattern to launch any workflow. Substitute the workflow path and extra flags as needed.
```bash
python -m agent_orchestrator.cli run \
  --repo /absolute/path/to/target/repo \
  --workflow src/agent_orchestrator/workflows/<workflow-file>.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py
```

Tips:
- If you did not run `pip install -e .`, prefix the command with `PYTHONPATH=src`.
- Set a custom wrapper binary with `--wrapper-arg --codex-bin` / `--wrapper-arg --claude-bin` or by exporting `CODEX_EXEC_BIN` / `CLAUDE_CLI_BIN`.
- Swap the `--wrapper` path to `src/agent_orchestrator/wrappers/claude_wrapper.py` (or another wrapper) when you are not using Codex.
- Add `--log-level DEBUG` when you want full logs in the terminal.
- Confirm the CLI entry point anytime with `PYTHONPATH=src python -m agent_orchestrator.cli --help` (verified October 2025).

## 3. One-Liner Favorites
- **PR review + fixes (our main workflow):**
  ```bash
  python -m agent_orchestrator.cli run \
    --repo /absolute/path/to/target/repo \
    --workflow src/agent_orchestrator/workflows/workflow_pr_review_fix.yaml \
    --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py
  ```
- **Full SDLC pipeline:** change `workflow_pr_review_fix.yaml` to `workflow.yaml`.
- **Bug backlog miner:** swap the workflow file for `workflow_backlog_miner.yaml`.
- **Quick loopback smoke test (local repo only):** use `lightweight_workflow.yaml`.
- **Single GitHub issue (requires `ISSUE_NUMBER`):**
  ```bash
  python -m agent_orchestrator.cli run \
    --repo /absolute/path/to/target/repo \
    --workflow src/agent_orchestrator/workflows/workflow_github_issue.yaml \
    --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
    --env ISSUE_NUMBER=<issue-id>
  ```

## 4. High-Value Flags (mix and match)
- Resume a failed run from a specific step:
  ```bash
  --start-at-step code_review
  ```
- Create an isolated git worktree for the run:
  ```bash
  --git-worktree --git-worktree-ref main --git-worktree-keep
  ```
- Inject environment variables into the agent process:
  ```bash
  --env NAME=value --env OTHER=value
  ```
  - The GitHub issue workflow must receive `ISSUE_NUMBER=<issue-id>` via this flag or an exported environment variable before launch.
- Let humans approve steps manually:
  ```bash
  --pause-for-human-input
  ```
- Override polling cadence or retry count:
  ```bash
  --poll-interval 1.5 --max-attempts 3
  ```

## 5. After the Run
The orchestrator writes everything under `.agents/` inside the target repo:
- `runs/<run_id>/reports/` – JSON run reports per step.
- `runs/<run_id>/logs/` – stdout and stderr for each attempt (attempt number is in the filename).
- `runs/<run_id>/artifacts/` – Files agents stored via `$ARTIFACTS_DIR` (diffs, summaries, patches, etc.).
- `runs/<run_id>/run_state.json` – Workflow progress (needed for `--start-at-step`).
- `runs/<run_id>/manual_inputs/` – Created only when you use `--pause-for-human-input` so operators know where to drop approvals.
Check the per-run `logs/` directory first if something looks off. Run `ls .agents/runs` to confirm the latest `run_id` before tailing logs.

## 6. Troubleshooting Checklist
- `ModuleNotFoundError: agent_orchestrator`: you skipped `pip install -e .`; either install it or prefix commands with `PYTHONPATH=src`.
- `codex: command not found`: install/auth your Codex CLI and ensure it is on `PATH`, or pass `--wrapper-arg --codex-bin /path/to/binary`.
- Runs hang with no logs: confirm the repo path is absolute and accessible, and that the wrapper has permissions to write to `.agents/`.
- Need to rerun clean: delete `.agents/runs/<run_id>/run_state.json` (or clear the run folder) before launching again, or supply a fresh `--run-id` by clearing `.agents/` for that repo.

Keep this file updated whenever we add new wrappers, workflows, or run habits.
