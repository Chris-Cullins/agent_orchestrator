"""
Notification system for workflow events.

This package provides an abstract notification service interface and
implementations for sending alerts about workflow events such as
step failures and human-in-the-loop pauses.

The default implementation is NullNotificationService, which performs
no actions. The email submodule provides SMTP-based notifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..models import StepStatus


@dataclass
class RunContext:
    """
    Contextual information about a workflow run.

    Attributes:
        run_id: Unique identifier for the run.
        workflow_name: Name of the workflow being executed.
        repo_dir: Path to the target repository.
    """

    run_id: str
    workflow_name: str
    repo_dir: Path


@dataclass
class StepNotification:
    """
    Structured payload describing a step-level event.

    Attributes:
        run_id: ID of the workflow run.
        workflow_name: Name of the workflow.
        step_id: ID of the step that triggered the notification.
        attempt: Current attempt number for the step.
        status: Current status of the step.
        trigger: Event type (e.g., "failure", "human_input").
        manual_input_path: Path for human-in-the-loop input if applicable.
        report_path: Path to the step's run report.
        logs: Recent log messages from the step.
        last_error: Error message if step failed.
    """

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
    """
    Abstract interface for workflow notifications.

    Implementations handle sending alerts for workflow events
    such as failures and human-input-required pauses.
    """

    def start(self, context: RunContext) -> None:  # pragma: no cover - interface only
        """Initialize the service with run context."""
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interface only
        """Shut down the notification service."""
        raise NotImplementedError

    def notify_failure(self, notification: StepNotification) -> None:  # pragma: no cover - interface only
        """Send notification about a step failure."""
        raise NotImplementedError

    def notify_human_input(self, notification: StepNotification) -> None:  # pragma: no cover - interface only
        """Send notification that a step requires human input."""
        raise NotImplementedError


class NullNotificationService(NotificationService):
    """Notification service that performs no actions (default behavior)."""

    def start(self, context: RunContext) -> None:
        """No-op initialization."""
        return None

    def stop(self) -> None:
        """No-op shutdown."""
        return None

    def notify_failure(self, notification: StepNotification) -> None:
        """Silently ignore failure notifications."""
        return None

    def notify_human_input(self, notification: StepNotification) -> None:
        """Silently ignore human-input notifications."""
        return None


__all__ = [
    "NotificationService",
    "NullNotificationService",
    "RunContext",
    "StepNotification",
]
