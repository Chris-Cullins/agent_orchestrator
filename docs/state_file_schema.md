# Persisted State File Schema

## Overview

The agent orchestrator persists workflow execution state to enable resumption after interruptions, failures, or manual pauses. This document describes the JSON schema structure of the persisted state file (`run_state.json`) created by the `RunStatePersister` class.

## Purpose

The state file serves several critical operational functions:

- **Workflow Resumption**: Enables `--start-at-step` functionality to resume workflows from a specific step
- **Progress Tracking**: Provides visibility into which steps have completed, are in progress, or are pending
- **Failure Recovery**: Preserves execution history including error messages and attempt counts
- **Loop-Back Management**: Tracks iteration counts for steps involved in quality gate loops
- **Human-in-the-Loop**: Records manual input requirements and status

## File Location

The state file is persisted at:
```
<repo>/.agents/runs/<run_id>/run_state.json
```

Where:
- `<repo>` is the target repository directory
- `<run_id>` is a unique identifier for the workflow run (e.g., `f8c1a491`)

## Schema Structure

The state file contains a single JSON object with the following top-level fields:

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `run_id` | string | Yes | Unique identifier for this workflow run |
| `workflow_name` | string | Yes | Name of the workflow being executed (from workflow YAML) |
| `repo_dir` | string | Yes | Absolute path to the target repository |
| `reports_dir` | string | Yes | Absolute path to the directory containing run reports |
| `manual_inputs_dir` | string | Yes | Absolute path to the directory for human-in-the-loop input files |
| `created_at` | string | Yes | ISO 8601 timestamp when the run was created (UTC) |
| `updated_at` | string | Yes | ISO 8601 timestamp of the last state update (UTC) |
| `steps` | object | Yes | Map of step IDs to their runtime state (see below) |

### Step Runtime Object

The `steps` field is a mapping where:
- **Key**: Step ID (string) from the workflow definition
- **Value**: Step runtime object with the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | Yes | Current execution status (see Status Values below) |
| `attempts` | integer | Yes | Number of execution attempts for this step (starts at 0) |
| `iteration_count` | integer | Yes | Number of times this step has been executed due to loop-backs (starts at 0) |
| `report_path` | string\|null | Yes | Absolute path to the step's run report JSON file, or null if not yet executed |
| `started_at` | string\|null | Yes | ISO 8601 timestamp when step execution started (UTC), or null if not yet started |
| `ended_at` | string\|null | Yes | ISO 8601 timestamp when step execution ended (UTC), or null if not yet completed |
| `last_error` | string\|null | Yes | Error message from the most recent failure, or null if no errors |
| `artifacts` | array[string] | Yes | List of relative paths to artifacts produced by this step |
| `metrics` | object | Yes | Key-value pairs of metrics reported by the step agent |
| `logs` | array[string] | Yes | Log messages from the step's run report |
| `manual_input_path` | string\|null | Yes | Absolute path to the manual input file for human-in-the-loop steps, or null if not applicable |
| `blocked_by_loop` | string\|null | Yes | Step ID that caused a loop-back blocking this step, or null if not blocked |

### Status Values

The `status` field uses the `StepStatus` enum with the following possible values:

| Status | Description |
|--------|-------------|
| `PENDING` | Step has not yet started execution |
| `RUNNING` | Step is currently executing |
| `WAITING_ON_HUMAN` | Step requires human input before proceeding (human-in-the-loop) |
| `COMPLETED` | Step completed successfully |
| `FAILED` | Step failed after exhausting retry attempts or reaching max iterations |
| `SKIPPED` | Step was skipped due to workflow conditions |

## Example State Files

### Example 1: Workflow in Progress

```json
{
  "run_id": "f8c1a491",
  "workflow_name": "workflow",
  "repo_dir": "/Users/operator/projects/my-app",
  "reports_dir": "/Users/operator/projects/my-app/.agents/runs/f8c1a491/reports",
  "manual_inputs_dir": "/Users/operator/projects/my-app/.agents/runs/f8c1a491/manual_inputs",
  "created_at": "2025-01-15T14:30:00.123456Z",
  "updated_at": "2025-01-15T14:35:22.789012Z",
  "steps": {
    "planning": {
      "status": "COMPLETED",
      "attempts": 1,
      "iteration_count": 0,
      "report_path": "/Users/operator/projects/my-app/.agents/runs/f8c1a491/reports/f8c1a491__planning.json",
      "started_at": "2025-01-15T14:30:05.000000Z",
      "ended_at": "2025-01-15T14:32:18.000000Z",
      "last_error": null,
      "artifacts": ["PLAN.md", "tasks.yaml"],
      "metrics": {},
      "logs": [
        "Created development plan in PLAN.md",
        "Generated task breakdown in tasks.yaml"
      ],
      "manual_input_path": null,
      "blocked_by_loop": null
    },
    "coding": {
      "status": "RUNNING",
      "attempts": 1,
      "iteration_count": 0,
      "report_path": null,
      "started_at": "2025-01-15T14:32:25.000000Z",
      "ended_at": null,
      "last_error": null,
      "artifacts": [],
      "metrics": {},
      "logs": [],
      "manual_input_path": null,
      "blocked_by_loop": null
    },
    "code_review": {
      "status": "PENDING",
      "attempts": 0,
      "iteration_count": 0,
      "report_path": null,
      "started_at": null,
      "ended_at": null,
      "last_error": null,
      "artifacts": [],
      "metrics": {},
      "logs": [],
      "manual_input_path": null,
      "blocked_by_loop": null
    }
  }
}
```

### Example 2: Step with Loop-Back Iteration

```json
{
  "run_id": "a1b2c3d4",
  "workflow_name": "code_review_loop_workflow",
  "repo_dir": "/Users/operator/projects/api-service",
  "reports_dir": "/Users/operator/projects/api-service/.agents/runs/a1b2c3d4/reports",
  "manual_inputs_dir": "/Users/operator/projects/api-service/.agents/runs/a1b2c3d4/manual_inputs",
  "created_at": "2025-01-15T16:00:00.000000Z",
  "updated_at": "2025-01-15T16:25:30.000000Z",
  "steps": {
    "coding": {
      "status": "COMPLETED",
      "attempts": 1,
      "iteration_count": 2,
      "report_path": "/Users/operator/projects/api-service/.agents/runs/a1b2c3d4/reports/a1b2c3d4__coding.json",
      "started_at": "2025-01-15T16:20:00.000000Z",
      "ended_at": "2025-01-15T16:24:45.000000Z",
      "last_error": null,
      "artifacts": ["src/api/auth.py", "tests/test_auth.py"],
      "metrics": {},
      "logs": [
        "Implemented authentication endpoints",
        "Added unit tests with 95% coverage"
      ],
      "manual_input_path": null,
      "blocked_by_loop": null
    },
    "code_review": {
      "status": "RUNNING",
      "attempts": 1,
      "iteration_count": 2,
      "report_path": "/Users/operator/projects/api-service/.agents/runs/a1b2c3d4/reports/a1b2c3d4__code_review.json",
      "started_at": "2025-01-15T16:25:00.000000Z",
      "ended_at": null,
      "last_error": null,
      "artifacts": [],
      "metrics": {},
      "logs": [],
      "manual_input_path": null,
      "blocked_by_loop": null
    }
  }
}
```

### Example 3: Failed Step with Error

```json
{
  "run_id": "xyz789",
  "workflow_name": "workflow",
  "repo_dir": "/Users/operator/projects/web-app",
  "reports_dir": "/Users/operator/projects/web-app/.agents/runs/xyz789/reports",
  "manual_inputs_dir": "/Users/operator/projects/web-app/.agents/runs/xyz789/manual_inputs",
  "created_at": "2025-01-15T10:00:00.000000Z",
  "updated_at": "2025-01-15T10:15:45.000000Z",
  "steps": {
    "planning": {
      "status": "COMPLETED",
      "attempts": 1,
      "iteration_count": 0,
      "report_path": "/Users/operator/projects/web-app/.agents/runs/xyz789/reports/xyz789__planning.json",
      "started_at": "2025-01-15T10:00:05.000000Z",
      "ended_at": "2025-01-15T10:02:30.000000Z",
      "last_error": null,
      "artifacts": ["PLAN.md"],
      "metrics": {},
      "logs": ["Created development plan"],
      "manual_input_path": null,
      "blocked_by_loop": null
    },
    "coding": {
      "status": "FAILED",
      "attempts": 2,
      "iteration_count": 0,
      "report_path": "/Users/operator/projects/web-app/.agents/runs/xyz789/reports/xyz789__coding.json",
      "started_at": "2025-01-15T10:02:35.000000Z",
      "ended_at": "2025-01-15T10:15:45.000000Z",
      "last_error": "Agent process exited with code 1: SyntaxError in generated code",
      "artifacts": [],
      "metrics": {},
      "logs": [
        "Attempted to implement feature",
        "Syntax error in src/components/Header.tsx"
      ],
      "manual_input_path": null,
      "blocked_by_loop": null
    }
  }
}
```

### Example 4: Human-in-the-Loop Step

```json
{
  "run_id": "hij456",
  "workflow_name": "workflow",
  "repo_dir": "/Users/operator/projects/mobile-app",
  "reports_dir": "/Users/operator/projects/mobile-app/.agents/runs/hij456/reports",
  "manual_inputs_dir": "/Users/operator/projects/mobile-app/.agents/runs/hij456/manual_inputs",
  "created_at": "2025-01-15T12:00:00.000000Z",
  "updated_at": "2025-01-15T12:30:00.000000Z",
  "steps": {
    "code_review": {
      "status": "COMPLETED",
      "attempts": 1,
      "iteration_count": 0,
      "report_path": "/Users/operator/projects/mobile-app/.agents/runs/hij456/reports/hij456__code_review.json",
      "started_at": "2025-01-15T12:10:00.000000Z",
      "ended_at": "2025-01-15T12:15:30.000000Z",
      "last_error": null,
      "artifacts": ["code_review_report.md"],
      "metrics": {"issues_found": "3", "severity": "medium"},
      "logs": ["Found 3 medium-severity issues requiring review"],
      "manual_input_path": null,
      "blocked_by_loop": null
    },
    "manual_approval": {
      "status": "WAITING_ON_HUMAN",
      "attempts": 1,
      "iteration_count": 0,
      "report_path": null,
      "started_at": "2025-01-15T12:15:35.000000Z",
      "ended_at": null,
      "last_error": null,
      "artifacts": [],
      "metrics": {},
      "logs": [],
      "manual_input_path": "/Users/operator/projects/mobile-app/.agents/runs/hij456/manual_inputs/hij456__manual_approval.json",
      "blocked_by_loop": null
    }
  }
}
```

## Field Semantics and Usage

### Timestamps

All timestamp fields use ISO 8601 format in UTC timezone:
```
YYYY-MM-DDTHH:MM:SS.mmmmmmZ
```

Example: `2025-01-15T14:30:00.123456Z`

### Attempts vs. Iteration Count

These two counters serve different purposes:

- **`attempts`**: Counts retries for the same iteration due to transient failures (network issues, temporary errors). Controlled by `--max-attempts` CLI flag (default: 2).

- **`iteration_count`**: Counts how many times the step has been executed due to loop-back from quality gates. Controlled by `--max-iterations` CLI flag (default: 4).

Example:
```json
{
  "attempts": 2,
  "iteration_count": 3
}
```
This indicates the step is on its 3rd iteration (due to loop-backs) and the 2nd retry attempt within this iteration.

### Artifact Paths

The `artifacts` array contains relative paths from the repository root:
```json
{
  "artifacts": [
    "PLAN.md",
    "src/api/handlers.py",
    "tests/test_handlers.py"
  ]
}
```

Absolute paths can be constructed as: `{repo_dir}/{artifact_path}`

### Metrics

The `metrics` object contains arbitrary key-value pairs reported by agents:
```json
{
  "metrics": {
    "test_coverage": "87.5",
    "lines_changed": "245",
    "files_modified": "8"
  }
}
```

Note: All metric values are stored as strings in the state file, even if they represent numbers.

### Manual Input Path

For human-in-the-loop steps, `manual_input_path` specifies where the orchestrator expects a JSON file with human input:
```json
{
  "manual_input_path": "/path/to/repo/.agents/runs/abc123/manual_inputs/abc123__approval.json"
}
```

The orchestrator polls this location when `status` is `WAITING_ON_HUMAN`.

### Blocked by Loop

When a quality gate triggers a loop-back, downstream steps are marked with the step that caused the loop:
```json
{
  "blocked_by_loop": "code_review"
}
```

This indicates the step cannot proceed because `code_review` failed its quality gate and triggered a loop-back.

## Operational Workflows

### Resuming from a Specific Step

To resume a failed workflow from a specific step:

```bash
python -m agent_orchestrator.cli run \
  --repo /path/to/repo \
  --workflow workflow.yaml \
  --wrapper wrapper.py \
  --start-at-step coding
```

The orchestrator:
1. Loads the most recent `run_state.json` from `.agents/runs/`
2. Resets the specified step and all downstream dependents to `PENDING`
3. Preserves completed upstream steps
4. Resumes execution from the specified step

### Inspecting State for Debugging

To understand why a workflow stopped:

```bash
# View current state
cat .agents/runs/<run_id>/run_state.json | jq .

# Check specific step status
cat .agents/runs/<run_id>/run_state.json | jq '.steps.coding'

# Find failed steps
cat .agents/runs/<run_id>/run_state.json | jq '.steps | to_entries | map(select(.value.status == "FAILED"))'

# Check iteration counts for loop-back debugging
cat .agents/runs/<run_id>/run_state.json | jq '.steps | to_entries | map({key: .key, iterations: .value.iteration_count})'
```

### Understanding Loop-Back Behavior

When a step has `loop_back_to` defined and reports `gate_failure: true`:

1. The step completes with status `COMPLETED`
2. `iteration_count` is incremented on the loop-back target step and all downstream steps
3. The target step and dependents are reset to `PENDING`
4. If `iteration_count` reaches `--max-iterations`, the step fails with status `FAILED`

Example state progression:

**Iteration 1**: Code review finds issues
```json
{
  "coding": {"status": "COMPLETED", "iteration_count": 0},
  "code_review": {"status": "COMPLETED", "iteration_count": 0, "last_error": "Gate failure: found P0 issues"}
}
```

**Iteration 2**: Loop-back triggered
```json
{
  "coding": {"status": "PENDING", "iteration_count": 1},
  "code_review": {"status": "PENDING", "iteration_count": 1}
}
```

**Iteration 2**: Code review passes
```json
{
  "coding": {"status": "COMPLETED", "iteration_count": 1},
  "code_review": {"status": "COMPLETED", "iteration_count": 1}
}
```

## State Mutation Events

The state file is updated after these events:

1. **Workflow Start**: Initial state created with all steps set to `PENDING`
2. **Step Start**: Status changes to `RUNNING`, `started_at` timestamp set
3. **Step Completion**: Status changes to `COMPLETED`, `ended_at` timestamp set, artifacts and logs populated
4. **Step Failure**: Status changes to `FAILED`, `last_error` populated, `attempts` incremented
5. **Loop-Back Triggered**: Target step and dependents reset to `PENDING`, `iteration_count` incremented
6. **Human Input Required**: Status changes to `WAITING_ON_HUMAN`, `manual_input_path` set
7. **Manual Input Received**: Status changes from `WAITING_ON_HUMAN` to `RUNNING`

## Data Contracts

### RunState.to_dict()

Implementation: `src/agent_orchestrator/models.py:104-114`

Returns a dictionary with all top-level fields plus a dynamically generated `updated_at` timestamp.

### StepRuntime.to_dict()

Implementation: `src/agent_orchestrator/models.py:77-91`

Converts `StepRuntime` objects to dictionaries, serializing:
- Enums (status) to their string values
- Path objects to strings
- Preserving null values for optional fields

### RunStatePersister.save()

Implementation: `src/agent_orchestrator/state.py:15-17`

Saves state to disk with:
- 2-space indentation for readability
- UTF-8 encoding
- Atomic write operations (direct file write)

### RunStatePersister.load()

Implementation: `src/agent_orchestrator/state.py:19-23`

Loads state from disk, returning:
- Dictionary if file exists and is valid JSON
- `None` if file does not exist
- Raises exception on invalid JSON

## Best Practices for Operators

### Troubleshooting Stuck Workflows

1. **Check step status**: Look for `WAITING_ON_HUMAN` or `RUNNING` steps
2. **Review last_error**: Identify failure reasons
3. **Inspect iteration_count**: Detect loop-back issues
4. **Check timestamps**: Find steps that have been running too long

### Manual State Manipulation

**Warning**: Direct editing of `run_state.json` is discouraged. Instead:

- Use `--start-at-step` to resume workflows
- Delete the entire run directory to start fresh
- Create a new `--run-id` for clean runs

If you must edit manually:
- Validate JSON syntax before saving
- Preserve required fields
- Use correct status values from the enum
- Maintain timestamp format consistency

### State File Corruption Recovery

If the state file becomes corrupted:

1. **Backup the corrupted file**: `cp run_state.json run_state.json.bak`
2. **Attempt JSON repair**: Use `jq` or a JSON validator
3. **Start a new run**: Use `--run-id` to create a fresh run
4. **Report the issue**: Include the corrupted file in bug reports

## Version History

- **v1.0** (2025-01-15): Initial schema documentation
  - Documented all fields in `RunState` and `StepRuntime`
  - Added examples for common workflow states
  - Included operational guidance for operators

## Related Documentation

- **README.md**: General orchestrator usage and CLI reference
- **sdlc_agents_orchestrator_guide.md**: Detailed architecture and contracts
- **src/agent_orchestrator/models.py**: Source code for data models
- **src/agent_orchestrator/state.py**: Source code for persistence layer
