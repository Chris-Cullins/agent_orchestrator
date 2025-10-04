# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Allow systemd installer to run without the external `flock` binary and refresh locking message formatting.
- GitHub issue fetcher now writes issue markdown files to artifacts directory instead of repository root (Issue #56)
  - Updated `src/agent_orchestrator/prompts/22_github_issue_fetcher.md` to write to `${ARTIFACTS_DIR}/gh_issue_${ISSUE_NUMBER}.md`
  - Updated `src/agent_orchestrator/prompts/23_github_issue_planner.md` to read from `${ARTIFACTS_DIR}/gh_issue_*.md`
  - Removed all legacy `gh_issue_*.md` files from repository root
  - Cleanup step already handles removing temporary issue files from repository root

### Added
- Email notification service for failure and human-input pause events (Issue #55)
  - Added `agent_orchestrator.notifications` package with SMTP-backed `EmailNotificationService`
  - Orchestrator now starts/stops the notification service and dispatches structured payloads on failure/pause transitions
  - CLI validates `config/email_notifications.yaml` and exits when enabled configs are incomplete
  - Documented configuration workflow in `README.md`, `AGENTS.md`, and `sdlc_agents_orchestrator_guide.md`
  - Added regression coverage in `tests/test_email_notifications.py` and `tests/test_notification_integration.py`
- **Loop-back functionality for iterative workflow refinement** (Issue #47)
  - Steps can now send work back to previous steps when quality gates fail
  - Added `loop_back_to` field to Step model for defining loop-back targets
  - Added `gate_failure` boolean field to RunReport for triggering loop-backs
  - Added `iteration_count` field to StepRuntime to track loop iterations
  - Added `--max-iterations` CLI parameter (default: 4) to prevent infinite loops
  - Loop-back mechanism automatically resets target step and all downstream dependencies
  - When max iterations reached, step is marked as FAILED with descriptive error message
  - Updated workflow loader to parse and validate `loop_back_to` references
  - Added comprehensive test suite in `tests/test_loopback.py` and `tests/test_workflow_loopback.py`
  - Created example workflow `workflows/workflow_code_review_loop.yaml` demonstrating the feature
  - Added extensive documentation in README.md explaining loop-back usage and best practices
  - Use case: Code review finding P0/P1 issues can automatically loop back to coding step
- Repository-level prompt overrides: Orchestrator now checks `.agents/prompts/` in the target repository for custom prompt files before falling back to default prompts
  - Updated `src/agent_orchestrator/orchestrator.py` to implement prompt override resolution
  - Added comprehensive unit tests in `tests/test_prompt_resolution.py`
  - Added integration tests in `tests/test_prompt_override_integration.py`
  - Enables per-repository customization of agent behavior without modifying orchestrator codebase or workflow definitions
- User-level systemd automation for recurring workflows (Issue #57)
  - Added `src/agent_orchestrator/scripts/install_systemd_timer.sh` to generate service/timer units and helper scripts with safe locking, log handling, and uninstall support
  - Documented CLI requirements, installer usage, and troubleshooting in README under "Automate Recurring Runs with systemd timers"
  - Added regression coverage in `tests/test_systemd_install_script.py` to verify unit generation, idempotency, and uninstall flows
- Regression coverage for GitHub-issue artifact propagation
  - Added `tests/test_issue_artifact_flow.py` to assert the runner injects `ISSUE_MARKDOWN_*` helpers and planners receive artifact paths from dependency env vars

### Fixed
- Remove hardcoded macOS-specific PATH injection from wrapper modules to improve cross-platform compatibility
  - Removed `/opt/homebrew/bin` PATH injection from `src/agent_orchestrator/wrappers/claude_wrapper.py`
  - Removed `/opt/homebrew/bin` and `/opt/homebrew/Cellar/node/24.5.0/bin` PATH injections from `src/agent_orchestrator/wrappers/codex_wrapper.py`
  - Wrappers now rely on system PATH without modification; users should configure their PATH environment or use `--claude-bin`/`--codex-bin` flags or `CLAUDE_CLI_BIN`/`CODEX_EXEC_BIN` environment variables for custom binary locations
- Harden run report ingestion to retry transient JSON parse failures and surface consistent `RunReportError`s.
  - Updated `src/agent_orchestrator/reporting.py`
  - Added regression coverage in `tests/test_reporting.py`
- Fix git worktree cleanup to import `shutil` and ensure artifact persistence failures no longer raise `NameError`.
  - Updated `src/agent_orchestrator/cli.py`
  - Added coverage for cleanup fallbacks in `tests/test_git_worktree.py`
- Centralize timezone-aware timestamp generation with `datetime.now(timezone.utc)` for Python 3.13+ compatibility
  - Added `src/agent_orchestrator/time_utils.py`
  - Updated `src/agent_orchestrator/models.py`
  - Updated `src/agent_orchestrator/wrappers/claude_wrapper.py`
  - Updated `src/agent_orchestrator/wrappers/codex_wrapper.py`
  - Added regression tests `tests/test_time_utils.py` and `tests/test_models.py`
- Update wrapper file references in documentation
  - Fixed all references from `codex_exec_wrapper.py` to `codex_wrapper.py` in `README.md`
  - Fixed all references from `real_codex_wrapper.py` to `codex_wrapper.py` in `README.md`
  - Updated wrapper paths and filenames in `sdlc_agents_orchestrator_guide.md`
  - Added wrapper selection guidance section in `README.md` explaining when to use each wrapper
  - **BREAKING CHANGE**: All CLI examples now use full paths to wrapper scripts (e.g., `src/agent_orchestrator/wrappers/codex_wrapper.py`)
  - Added "Wrapper Path Resolution" section documenting how the CLI resolves wrapper paths
- Prevent backlog_miner run reports from persisting placeholder artifact/log content
  - Enhanced run report prompt block to demand concrete data and reject instructional text
  - Added shared run report normalisation/validation and wrapper guardrails for Codex/Claude flows
  - Tightened backlog_miner prompts and regression tests to cover placeholder rejection
- Ensure `08_architect_repo_review.md` ends with the canonical run-report completion block so backlog architect runs emit concrete reports
  - Appended the standard run-report instructions to `src/agent_orchestrator/prompts/08_architect_repo_review.md`
  - Added regression coverage in `tests/test_prompts_architect_repo_review.py`

### Changed
- Refreshed operator documentation (`README.md`, `AGENTS.md`, `sdlc_agents_orchestrator_guide.md`) to highlight `python -m agent_orchestrator.cli run`, wrapper binary overrides (`CODEX_EXEC_BIN` / `CLAUDE_CLI_BIN`), and the per-run `.agents/runs/<run_id>/` scaffolding (reports/logs/artifacts/manual_inputs/run_state.json) now guaranteed by the orchestrator.
- Issue #20 traceability: README quick start, AGENTS Playbook, and the full orchestrator guide now clarify manual launch steps, resume expectations, and `.agents/runs/<run_id>/manual_inputs/` usage when `--pause-for-human-input` is set.
- GitHub issue workflows now write `gh_issue_<ISSUE_NUMBER>.md` into the active run's artifacts directory, expose the path via new `ISSUE_MARKDOWN_*` env vars, and instruct downstream prompts/documentation to read from there while cleaning up legacy root-level files.

### Migration Guide
If you have existing scripts or commands using the old wrapper references:
- Change `--wrapper codex_exec_wrapper.py` → `--wrapper src/agent_orchestrator/wrappers/codex_wrapper.py`
- Change `--wrapper claude_wrapper.py` → `--wrapper src/agent_orchestrator/wrappers/claude_wrapper.py`
- The CLI requires full or relative paths to wrapper scripts; it does not search in default directories
