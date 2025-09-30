from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now() -> str:
    """Return an ISO-8601 timestamp with UTC timezone."""
    return datetime.utcnow().strftime(ISO_FORMAT)


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_ON_HUMAN = "WAITING_ON_HUMAN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class Step:
    """Static workflow definition for a single agent step."""

    id: str
    agent: str
    prompt: str
    needs: List[str] = field(default_factory=list)
    next_on_success: List[str] = field(default_factory=list)
    gates: List[str] = field(default_factory=list)
    human_in_the_loop: bool = False
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Workflow:
    name: str
    description: str
    steps: Dict[str, Step]

    def entry_steps(self) -> List[str]:
        return [step_id for step_id, step in self.steps.items() if not step.needs]


@dataclass
class RunReport:
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
    raw: Dict[str, object] = field(default_factory=dict)


@dataclass
class StepRuntime:
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    report_path: Optional[Path] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    last_error: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    metrics: Dict[str, object] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    manual_input_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status.value,
            "attempts": self.attempts,
            "report_path": str(self.report_path) if self.report_path else None,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "last_error": self.last_error,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "logs": self.logs,
            "manual_input_path": str(self.manual_input_path) if self.manual_input_path else None,
        }


@dataclass
class RunState:
    run_id: str
    workflow_name: str
    repo_dir: Path
    reports_dir: Path
    manual_inputs_dir: Path
    created_at: str = field(default_factory=utc_now)
    steps: Dict[str, StepRuntime] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
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
