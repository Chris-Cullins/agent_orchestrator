# GitHub Issue #39: Fix backlog_miner run report placeholder data

**State:** OPEN
**Created:** 2025-10-02T01:48:13Z
**Updated:** 2025-10-02T01:48:13Z

## Labels
- None

## Assignees
- None

## Milestone
None

## Description
## Issue

The backlog_miner workflow's run reports contain placeholder/example data instead of actual artifact paths and logs. This makes it difficult to verify what the agent actually accomplished.

## Example

From `.agents/runs/1bd17b80/run_state.json`:

```json
"architect_repo_review": {
  "status": "COMPLETED",
  "attempts": 1,
  "report_path": "/home/chris/src/agent_orchestrator/.agents/runs/1bd17b80/reports/1bd17b80__architect_repo_review.json",
  "started_at": "2025-10-02T01:44:23.693498Z",
  "ended_at": "2025-10-02T01:44:23.720817Z",
  "last_error": null,
  "artifacts": [
    "list",
    "of",
    "created",
    "file",
    "paths"
  ],
  "metrics": {
    "duration_ms": 14089
  },
  "logs": [
    "summary",
    "of",
    "what",
    "you",
    "accomplished"
  ],
  "manual_input_path": null
}
```

## Expected

The `artifacts` and `logs` arrays should contain actual file paths and log messages, such as:

```json
"artifacts": [
  "backlog/architecture_alignment.md",
  "backlog/tech_debt.md"
],
"logs": [
  "Analyzed repository structure and identified 12 architectural improvements",
  "Created architecture alignment document in backlog/"
]
```

## Impact

- Unable to verify agent's actual work from run reports
- Difficult to debug workflow issues
- Can't track which files were created or modified

## Steps to Reproduce

1. Run the backlog_miner workflow: `python3 -m agent_orchestrator.cli run --repo . --workflow src/agent_orchestrator/workflows/workflow_backlog_miner.yaml --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py`
2. Examine the run report JSON files in `.agents/runs/<run_id>/reports/`
3. Observe placeholder data in `artifacts` and `logs` fields

## Root Cause

Likely the prompts for the backlog_miner steps (08_architect_repo_review.md, 09_tech_debt_miner.md) contain example/placeholder data in the run report format section, and the agent is copying that verbatim instead of replacing it with actual values.

## Proposed Fix

Update the relevant prompts to:
1. Make it clear that the example values should be replaced with actual data
2. Provide clearer instructions on what should be included in artifacts and logs arrays
3. Consider adding schema validation to reject placeholder values

---

_Planning complete by dev_architect (Run 4fdaa837). See PLAN.md and .agents/runs/4fdaa837/artifacts/plan/tasks.yaml for details._

_Planning updated by dev_architect (Run 3a4cdc47). See PLAN.md and .agents/runs/3a4cdc47/artifacts/plan/tasks.yaml for details._
