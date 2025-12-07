# AGENTS.md

## Gotchas
- Without `pip install -e .`, prefix commands with `PYTHONPATH=src`
- Repo path must be absolute or runs hang silently with no logs
- GitHub Issue Workflow: when `ISSUE_NUMBER` is set, orchestrator auto-injects `ISSUE_MARKDOWN_PATH`, `ISSUE_MARKDOWN_DIR`, `ISSUE_MARKDOWN_FILENAME` pointing at `.agents/runs/<run_id>/artifacts/gh_issue_<ISSUE_NUMBER>.md`
- Run reports with placeholder text are rejected (`PlaceholderContentError`)
- Artifacts in run reports must be relative paths from repo root, not absolute
- Step retries reset `started_at`, `ended_at`, and `report_path` to None
- `loop_back_to` increments `iteration_count`, capped by `max_iterations` (default 4)
- `loop_back_to` target must be an ancestor step in the DAG
- Step IDs are used as filesystem paths - avoid special characters
- Local prompt overrides: place file at `.agents/prompts/<filename>` in target repo
- Codex wrapper uses positional prompt arg; Claude wrapper uses stdin (`--print` mode)
