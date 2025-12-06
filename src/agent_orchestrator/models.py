"""Data models for workflow definitions and execution state.

This module defines the core data structures used throughout the agent orchestrator:
    - Step definitions and workflow configuration
    - Execution state and runtime tracking
    - Run reports and memory updates

All dataclasses are designed for JSON serialization via their `to_dict()` methods
where applicable, enabling state persistence and resumability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .time_utils import ISO_FORMAT, utc_now


class StepStatus(str, Enum):
    """Execution status for a workflow step.

    Attributes:
        PENDING: Step is waiting to be launched.
        RUNNING: Step's agent process is currently executing.
        WAITING_ON_HUMAN: Step completed but awaits manual input.
        COMPLETED: Step finished successfully.
        FAILED: Step failed after exhausting retry attempts.
        SKIPPED: Step was skipped (e.g., by gate evaluation).
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_ON_HUMAN = "WAITING_ON_HUMAN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class LoopConfig:
    """Configuration for iterating a step over a collection of items.

    Loop items can be sourced from:
        - Static list in workflow YAML (items)
        - Output from a previous step (items_from_step)
        - Artifact file path (items_from_artifact)

    The current item and index are passed to agents via LOOP_* environment
    variables using the configured item_var and index_var names.

    Attributes:
        items: Static list of items to iterate over.
        items_from_step: Step ID whose first artifact contains items.
        items_from_artifact: Path to JSON artifact containing items.
        max_iterations: Maximum loop iterations (safety limit).
        until_condition: Expression for dynamic exit (not yet implemented).
        item_var: Environment variable name for current item (default: "item").
        index_var: Environment variable name for current index (default: "index").
    """

    items: Optional[List[Any]] = None
    items_from_step: Optional[str] = None
    items_from_artifact: Optional[str] = None
    max_iterations: Optional[int] = None
    until_condition: Optional[str] = None
    item_var: str = "item"
    index_var: str = "index"


@dataclass
class Step:
    """Static workflow definition for a single agent step.

    A step defines what agent runs, with what prompt, and how it connects
    to other steps in the workflow graph. Steps are immutable once loaded
    from workflow YAML.

    Attributes:
        id: Unique identifier for the step within the workflow.
        agent: Agent type identifier (e.g., "backlog_miner", "dev_architect").
        prompt: Path to the prompt file (absolute or relative to workflow).
        needs: List of step IDs that must complete before this step runs.
        next_on_success: List of step IDs to trigger after success (not used).
        gates: List of gate names that must evaluate to open.
        loop_back_to: Step ID to return to on gate failure.
        human_in_the_loop: If True, pause for manual input after completion.
        metadata: Arbitrary key-value metadata for the step.
        loop: Optional loop configuration for iterating over collections.
        model: Optional LLM model override (e.g., "opus", "sonnet", "haiku").
    """

    id: str
    agent: str
    prompt: str
    needs: List[str] = field(default_factory=list)
    next_on_success: List[str] = field(default_factory=list)
    gates: List[str] = field(default_factory=list)
    loop_back_to: Optional[str] = None
    human_in_the_loop: bool = False
    metadata: Dict[str, str] = field(default_factory=dict)
    loop: Optional[LoopConfig] = None
    model: Optional[str] = None


@dataclass
class Workflow:
    """Complete workflow definition containing ordered steps.

    Attributes:
        name: Human-readable workflow name.
        description: Brief description of what the workflow accomplishes.
        steps: Dictionary mapping step IDs to Step definitions.
    """

    name: str
    description: str
    steps: Dict[str, Step]

    def entry_steps(self) -> List[str]:
        """Return step IDs that have no dependencies (workflow entry points)."""
        return [step_id for step_id, step in self.steps.items() if not step.needs]


@dataclass
class MemoryUpdate:
    """A single memory update to be written to an AGENTS.md file.

    Memory updates allow agents to persist learned knowledge that will be
    injected into future agent prompts via the AGENTS.md system.

    Attributes:
        scope: Relative path to target directory (e.g., "src/api" or ".").
        section: Section name in AGENTS.md (e.g., "Gotchas", "Patterns").
        entry: The content to add to the specified section.
    """

    scope: str
    section: str
    entry: str


@dataclass
class RunReport:
    """Agent run report containing execution results and outputs.

    Run reports are JSON files written by agents at the end of their execution.
    The orchestrator parses these to determine step success/failure and collect
    artifacts.

    Attributes:
        schema: Report format version (e.g., "run_report@v0").
        run_id: Unique identifier for the orchestration run.
        step_id: Identifier of the step that produced this report.
        agent: Agent type that executed.
        status: Execution result ("COMPLETED" or "FAILED").
        started_at: ISO 8601 timestamp when step started.
        ended_at: ISO 8601 timestamp when step ended.
        artifacts: List of relative paths to output files.
        metrics: Key-value performance metrics.
        logs: List of log messages from the agent.
        next_suggested_steps: Suggested follow-up steps (informational).
        gate_failure: If True, triggers loop-back to loop_back_to step.
        memory_updates: List of AGENTS.md updates to persist.
        raw: Original parsed JSON for extension fields.
    """
    schema: str
    run_id: str
    step_id: str
    agent: str
    status: str
    started_at: str
    ended_at: str
    artifacts: List[str] = field(default_factory=list)
    metrics: Dict[str, str] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    next_suggested_steps: List[str] = field(default_factory=list)
    gate_failure: bool = False
    memory_updates: List[MemoryUpdate] = field(default_factory=list)
    raw: Dict[str, object] = field(default_factory=dict)


@dataclass
class StepRuntime:
    """Mutable execution state for a single step during a workflow run.

    This tracks all runtime information for a step: its current status,
    attempt count, output artifacts, and loop iteration state. Unlike Step
    (which is immutable), StepRuntime is updated throughout execution.

    Attributes:
        status: Current execution status (PENDING, RUNNING, etc.).
        attempts: Number of execution attempts made.
        iteration_count: Loop-back iteration counter.
        report_path: Path to the agent's run report JSON.
        started_at: ISO 8601 timestamp when execution started.
        ended_at: ISO 8601 timestamp when execution ended.
        last_error: Most recent error message if failed.
        artifacts: List of output artifact paths from the agent.
        metrics: Performance metrics from the run report.
        logs: Log messages from the agent.
        manual_input_path: Path where manual input file is expected.
        blocked_by_loop: Step ID blocking this step during loop-back.
        notified_failure: Whether failure notification was sent.
        notified_human_input: Whether human input notification was sent.
        loop_index: Current iteration index in loop execution.
        loop_items: List of items being iterated over.
        loop_completed: Whether loop has finished all iterations.
    """

    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    iteration_count: int = 0
    report_path: Optional[Path] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    last_error: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    metrics: Dict[str, object] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    manual_input_path: Optional[Path] = None
    blocked_by_loop: Optional[str] = None
    notified_failure: bool = False
    notified_human_input: bool = False
    loop_index: int = 0
    loop_items: Optional[List[Any]] = None
    loop_completed: bool = False

    def to_dict(self) -> Dict[str, object]:
        """Serialize step runtime state to a dictionary for JSON persistence."""
        return {
            "status": self.status.value,
            "attempts": self.attempts,
            "iteration_count": self.iteration_count,
            "report_path": str(self.report_path) if self.report_path else None,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "last_error": self.last_error,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "logs": self.logs,
            "manual_input_path": str(self.manual_input_path) if self.manual_input_path else None,
            "blocked_by_loop": self.blocked_by_loop,
            "notified_failure": self.notified_failure,
            "notified_human_input": self.notified_human_input,
            "loop_index": self.loop_index,
            "loop_items": self.loop_items,
            "loop_completed": self.loop_completed,
        }


@dataclass
class RunState:
    """Complete execution state for a workflow run.

    RunState captures the full state of an orchestration run, enabling
    persistence to disk and resumption after interruption. It contains
    metadata about the run plus StepRuntime for each workflow step.

    Attributes:
        run_id: Unique identifier for this run.
        workflow_name: Name of the workflow being executed.
        repo_dir: Target repository directory.
        reports_dir: Directory for agent run report files.
        manual_inputs_dir: Directory for human-in-the-loop input files.
        created_at: ISO 8601 timestamp when run was created.
        steps: Dictionary mapping step IDs to their runtime state.
    """

    run_id: str
    workflow_name: str
    repo_dir: Path
    reports_dir: Path
    manual_inputs_dir: Path
    created_at: str = field(default_factory=utc_now)
    steps: Dict[str, StepRuntime] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """Serialize run state to a dictionary for JSON persistence."""
        return {
            "run_id": self.run_id,
            "workflow_name": self.workflow_name,
            "repo_dir": str(self.repo_dir),
            "reports_dir": str(self.reports_dir),
            "manual_inputs_dir": str(self.manual_inputs_dir),
            "created_at": self.created_at,
            "updated_at": utc_now(),
            "steps": {step_id: runtime.to_dict() for step_id, runtime in self.steps.items()},
        }
