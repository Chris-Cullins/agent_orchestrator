"""
Data models for workflow orchestration.

This module defines the core data structures used throughout the orchestrator:
- Workflow and step definitions for static configuration
- Runtime state tracking for execution progress
- Run reports for agent communication

All dataclasses use field defaults and factory functions to support
JSON serialization and state persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .time_utils import ISO_FORMAT, utc_now


class StepStatus(str, Enum):
    """
    Possible states for a workflow step during execution.

    Attributes:
        PENDING: Step has not yet started.
        RUNNING: Step is currently executing.
        WAITING_ON_HUMAN: Step completed but awaiting manual input.
        COMPLETED: Step finished successfully.
        FAILED: Step failed after exhausting retries.
        SKIPPED: Step was skipped (e.g., conditional execution).
    """
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_ON_HUMAN = "WAITING_ON_HUMAN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class LoopConfig:
    """
    Configuration for iterating a step over a collection of items.

    Defines how a step should loop over items, with configurable item sources,
    exit conditions, and variable naming for the loop context.

    Exactly one item source must be specified: items, items_from_step,
    or items_from_artifact.

    Attributes:
        items: Static list of items to iterate over.
        items_from_step: ID of a dependency step whose output provides items.
        items_from_artifact: Path to a JSON artifact file containing items.
        max_iterations: Optional limit on the number of iterations.
        until_condition: Optional expression for early termination (not yet implemented).
        item_var: Environment variable name for the current item. Defaults to "item".
        index_var: Environment variable name for the current index. Defaults to "index".
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
    """
    Static workflow definition for a single agent step.

    Represents a step in a workflow DAG, defining which agent runs,
    its dependencies, gates, and execution parameters.

    Attributes:
        id: Unique identifier for this step within the workflow.
        agent: Name of the agent type to execute this step.
        prompt: Path to the prompt file for this step.
        needs: List of step IDs that must complete before this step runs.
        next_on_success: List of step IDs to trigger after successful completion.
        gates: List of gate names that must be open before step can run.
        loop_back_to: Step ID to return to on gate failure (iterative refinement).
        human_in_the_loop: Whether step requires manual approval to complete.
        metadata: Arbitrary key-value pairs for step-specific configuration.
        loop: Optional loop configuration for iterating over collections.
        model: LLM model to use (e.g., "opus", "sonnet", "haiku").
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
    """
    Complete workflow definition containing all steps.

    Represents a directed acyclic graph (DAG) of steps that can be
    executed by the orchestrator.

    Attributes:
        name: Human-readable name for the workflow.
        description: Brief description of workflow purpose.
        steps: Dictionary mapping step IDs to Step definitions.
    """

    name: str
    description: str
    steps: Dict[str, Step]

    def entry_steps(self) -> List[str]:
        """
        Return IDs of steps with no dependencies (DAG entry points).

        Returns:
            List of step IDs that have empty needs lists.
        """
        return [step_id for step_id, step in self.steps.items() if not step.needs]


@dataclass
class MemoryUpdate:
    """
    A single memory update to be written to an AGENTS.md file.

    Memory updates allow agents to persist learned knowledge for future runs.
    Updates are scoped to directories and organized by section.

    Attributes:
        scope: Relative path to target directory (e.g., "src/api" or "." for root).
        section: Section name in AGENTS.md (e.g., "Gotchas", "Patterns").
        entry: Content to add as a bullet point in the section.
    """

    scope: str
    section: str
    entry: str


@dataclass
class RunReport:
    """
    Structured report emitted by agents upon step completion.

    Run reports communicate step outcomes, artifacts, metrics, and
    any memory updates back to the orchestrator.

    Attributes:
        schema: Report schema version (e.g., "run_report@v0").
        run_id: ID of the workflow run this report belongs to.
        step_id: ID of the step that produced this report.
        agent: Name of the agent that executed the step.
        status: Completion status ("COMPLETED" or "FAILED").
        started_at: ISO 8601 timestamp when step execution began.
        ended_at: ISO 8601 timestamp when step execution ended.
        artifacts: List of relative paths to created/modified files.
        metrics: Key-value pairs of execution metrics.
        logs: List of log messages summarizing work performed.
        next_suggested_steps: Optional hints for workflow progression.
        gate_failure: If True, triggers loop-back to configured step.
        memory_updates: List of memory entries to persist to AGENTS.md files.
        raw: Original parsed JSON payload for extension fields.
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
    """
    Mutable runtime state for a workflow step during execution.

    Tracks execution progress, retry counts, loop state, and results
    for a single step. Updated throughout the step lifecycle.

    Attributes:
        status: Current execution state of the step.
        attempts: Number of execution attempts made (including retries).
        iteration_count: Number of loop-back iterations for this step.
        report_path: Path to the run report file once created.
        started_at: ISO 8601 timestamp when current attempt started.
        ended_at: ISO 8601 timestamp when current attempt ended.
        last_error: Error message from most recent failure.
        artifacts: List of artifact paths from completed run report.
        metrics: Metrics from completed run report.
        logs: Log messages from completed run report.
        manual_input_path: Path where human input should be placed.
        blocked_by_loop: Step ID this step is waiting on during loop-back.
        notified_failure: Whether failure notification has been sent.
        notified_human_input: Whether human-input notification has been sent.
        loop_index: Current iteration index when step has loop config.
        loop_items: List of items being iterated over.
        loop_completed: Whether all loop iterations have finished.
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
        """
        Convert runtime state to a JSON-serializable dictionary.

        Returns:
            Dictionary representation suitable for persistence.
        """
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
    """
    Complete state of a workflow run for persistence and resumption.

    Captures all information needed to resume a workflow run after
    interruption, including step runtime states and directory paths.

    Attributes:
        run_id: Unique identifier for this run.
        workflow_name: Name of the workflow being executed.
        repo_dir: Path to the target repository.
        reports_dir: Directory for agent run report files.
        manual_inputs_dir: Directory for human-in-the-loop input files.
        created_at: ISO 8601 timestamp when run was created.
        steps: Dictionary mapping step IDs to their runtime states.
    """

    run_id: str
    workflow_name: str
    repo_dir: Path
    reports_dir: Path
    manual_inputs_dir: Path
    created_at: str = field(default_factory=utc_now)
    steps: Dict[str, StepRuntime] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """
        Convert run state to a JSON-serializable dictionary.

        Returns:
            Dictionary representation suitable for persistence.
        """
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
