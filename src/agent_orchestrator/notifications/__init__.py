from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..models import StepStatus


@dataclass
class RunContext:
    """Contextual information about a workflow run."""

    run_id: str
    workflow_name: str
    repo_dir: Path


@dataclass
class StepNotification:
    """Structured payload describing a step-level event."""

    run_id: str
    workflow_name: str
    step_id: str
    attempt: int
    status: StepStatus
    trigger: str
    manual_input_path: Optional[Path]
    report_path: Optional[Path]
    logs: List[str]
    last_error: Optional[str]


class NotificationService:
    """Abstract interface for workflow notifications."""

    def start(self, context: RunContext) -> None:  # pragma: no cover - interface only
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interface only
        raise NotImplementedError

    def notify_failure(self, notification: StepNotification) -> None:  # pragma: no cover - interface only
        raise NotImplementedError

    def notify_human_input(self, notification: StepNotification) -> None:  # pragma: no cover - interface only
        raise NotImplementedError


class NullNotificationService(NotificationService):
    """Notification service that performs no actions (default behaviour)."""

    def start(self, context: RunContext) -> None:
        return None

    def stop(self) -> None:
        return None

    def notify_failure(self, notification: StepNotification) -> None:
        return None

    def notify_human_input(self, notification: StepNotification) -> None:
        return None


__all__ = [
    "NotificationService",
    "NullNotificationService",
    "RunContext",
    "StepNotification",
]
