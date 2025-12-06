"""Notification services for workflow events.

This package provides interfaces and implementations for sending notifications
about workflow events such as step failures and human input requests.

Available implementations:
    - NullNotificationService: No-op implementation (default)
    - EmailNotificationService: SMTP-based email notifications (in email submodule)

Usage:
    >>> from agent_orchestrator.notifications import NotificationService
    >>> from agent_orchestrator.notifications.email import build_email_notification_service
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..models import StepStatus


@dataclass
class RunContext:
    """Contextual information about a workflow run for notifications.

    Passed to NotificationService.start() to provide run-level context
    that may be included in notifications.

    Attributes:
        run_id: Unique identifier for the workflow run.
        workflow_name: Name of the executing workflow.
        repo_dir: Path to the target repository.
    """

    run_id: str
    workflow_name: str
    repo_dir: Path


@dataclass
class StepNotification:
    """Structured payload for step-level notification events.

    Contains all relevant information about a step event that
    notification services may want to include in messages.

    Attributes:
        run_id: Unique identifier for the workflow run.
        workflow_name: Name of the executing workflow.
        step_id: Identifier of the step that triggered the event.
        attempt: Current attempt number for the step.
        status: Current step status.
        trigger: Event type that triggered the notification (e.g., "failure").
        manual_input_path: Path where manual input is expected (if applicable).
        report_path: Path to the step's run report (if available).
        logs: Recent log messages from the step.
        last_error: Most recent error message (if failed).
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
    """Abstract interface for workflow notification services.

    Notification services are started at the beginning of a workflow run
    and stopped at the end. During execution, they receive notifications
    for step failures and human input requests.
    """

    def start(self, context: RunContext) -> None:  # pragma: no cover - interface only
        """Initialize the notification service for a workflow run.

        Args:
            context: Run-level context information.
        """
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interface only
        """Clean up and stop the notification service."""
        raise NotImplementedError

    def notify_failure(self, notification: StepNotification) -> None:  # pragma: no cover - interface only
        """Send a notification about a step failure.

        Args:
            notification: Details about the failed step.
        """
        raise NotImplementedError

    def notify_human_input(self, notification: StepNotification) -> None:  # pragma: no cover - interface only
        """Send a notification about a step awaiting human input.

        Args:
            notification: Details about the step awaiting input.
        """
        raise NotImplementedError


class NullNotificationService(NotificationService):
    """No-op notification service that discards all notifications.

    Used as the default when no notification service is configured.
    """

    def start(self, context: RunContext) -> None:
        """No-op: does nothing."""
        return None

    def stop(self) -> None:
        """No-op: does nothing."""
        return None

    def notify_failure(self, notification: StepNotification) -> None:
        """No-op: discards the notification."""
        return None

    def notify_human_input(self, notification: StepNotification) -> None:
        """No-op: discards the notification."""
        return None


__all__ = [
    "NotificationService",
    "NullNotificationService",
    "RunContext",
    "StepNotification",
]
