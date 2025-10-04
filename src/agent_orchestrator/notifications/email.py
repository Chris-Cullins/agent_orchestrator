from __future__ import annotations

import contextlib
import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import yaml

from . import NotificationService, RunContext, StepNotification


DEFAULT_CONFIG_RELATIVE_PATH = Path("config/email_notifications.yaml")


class EmailConfigError(ValueError):
    """Raised when the email notification configuration is invalid."""


@dataclass
class SMTPSettings:
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    use_tls: bool = True
    timeout: Optional[float] = 30.0


@dataclass
class EmailNotificationConfig:
    enabled: bool = False
    sender: Optional[str] = None
    recipients: List[str] = field(default_factory=list)
    smtp: Optional[SMTPSettings] = None
    subject_prefix: str = "[Agent Orchestrator]"

    def require_transport(self) -> None:
        if not self.enabled:
            return
        if not self.sender:
            raise EmailConfigError("Email notifications enabled but 'sender' is missing")
        if not self.recipients:
            raise EmailConfigError("Email notifications enabled but 'recipients' list is empty")
        if not self.smtp:
            raise EmailConfigError("Email notifications enabled but SMTP settings are missing")


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise EmailConfigError("Email notification configuration must be a mapping")
    return data


def _parse_smtp_settings(data: dict) -> SMTPSettings:
    if "host" not in data:
        raise EmailConfigError("SMTP configuration missing 'host'")
    if "port" not in data:
        raise EmailConfigError("SMTP configuration missing 'port'")
    host = data["host"]
    port = data["port"]
    if not isinstance(host, str) or not host.strip():
        raise EmailConfigError("SMTP 'host' must be a non-empty string")
    if not isinstance(port, int):
        raise EmailConfigError("SMTP 'port' must be an integer")
    username = data.get("username")
    password = data.get("password")
    if username is not None and not isinstance(username, str):
        raise EmailConfigError("SMTP 'username' must be a string when provided")
    if password is not None and not isinstance(password, str):
        raise EmailConfigError("SMTP 'password' must be a string when provided")
    use_tls = data.get("use_tls", True)
    if not isinstance(use_tls, bool):
        raise EmailConfigError("SMTP 'use_tls' must be a boolean")
    timeout = data.get("timeout", 30.0)
    if timeout is not None and not isinstance(timeout, (int, float)):
        raise EmailConfigError("SMTP 'timeout' must be numeric or null")
    return SMTPSettings(
        host=host.strip(),
        port=port,
        username=username.strip() if isinstance(username, str) and username.strip() else None,
        password=password if isinstance(password, str) and password else None,
        use_tls=use_tls,
        timeout=float(timeout) if timeout is not None else None,
    )


def load_email_notification_config(
    repo_dir: Path,
    *,
    config_path: Optional[Path] = None,
) -> EmailNotificationConfig:
    """Load the email notification configuration from disk.

    If the configuration file is missing, notifications are disabled by default.
    """

    path = (config_path or (repo_dir / DEFAULT_CONFIG_RELATIVE_PATH)).resolve()
    if not path.exists():
        return EmailNotificationConfig(enabled=False)

    config_data = _load_yaml(path)
    enabled = bool(config_data.get("enabled", False))

    sender = config_data.get("sender")
    if sender is not None and not isinstance(sender, str):
        raise EmailConfigError("'sender' must be a string")

    recipients_field = config_data.get("recipients")
    recipients: List[str] = []
    if recipients_field is not None:
        if not isinstance(recipients_field, Iterable) or isinstance(recipients_field, (str, bytes)):
            raise EmailConfigError("'recipients' must be a list of email addresses")
        for value in recipients_field:
            if not isinstance(value, str) or not value.strip():
                raise EmailConfigError("Each recipient must be a non-empty string")
            recipients.append(value.strip())

    smtp_config = config_data.get("smtp")
    smtp_settings = _parse_smtp_settings(smtp_config) if smtp_config else None

    subject_prefix = config_data.get("subject_prefix", "[Agent Orchestrator]")
    if not isinstance(subject_prefix, str):
        raise EmailConfigError("'subject_prefix' must be a string")

    config = EmailNotificationConfig(
        enabled=enabled,
        sender=sender.strip() if isinstance(sender, str) and sender.strip() else sender,
        recipients=recipients,
        smtp=smtp_settings,
        subject_prefix=subject_prefix.strip() or "[Agent Orchestrator]",
    )
    config.require_transport()
    return config


class _SMTPConnection(contextlib.AbstractContextManager):
    def __init__(self, settings: SMTPSettings) -> None:
        self._settings = settings
        self._client: Optional[smtplib.SMTP] = None

    def __enter__(self) -> smtplib.SMTP:
        timeout = self._settings.timeout if self._settings.timeout and self._settings.timeout > 0 else None
        client = smtplib.SMTP(self._settings.host, self._settings.port, timeout=timeout)
        if self._settings.use_tls:
            client.starttls()
        if self._settings.username and self._settings.password:
            client.login(self._settings.username, self._settings.password)
        self._client = client
        return client

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if not self._client:
            return
        try:
            self._client.quit()
        except Exception:  # pragma: no cover - defensive cleanup
            try:
                self._client.close()
            except Exception:
                pass
        finally:
            self._client = None


class EmailNotificationService(NotificationService):
    """Send workflow notifications via email using SMTP."""

    def __init__(
        self,
        config: EmailNotificationConfig,
        *,
        transport_factory: Optional[Callable[[SMTPSettings], contextlib.AbstractContextManager[smtplib.SMTP]]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._config = config
        self._transport_factory = transport_factory or (lambda settings: _SMTPConnection(settings))
        self._logger = logger or logging.getLogger(__name__)
        self._active = False
        self._current_context: Optional[RunContext] = None

    def start(self, context: RunContext) -> None:
        self._current_context = context
        if not self._config.enabled:
            self._logger.info("Email notifications disabled for run_id=%s", context.run_id)
            return
        self._active = True
        self._logger.info(
            "Email notifications enabled for run_id=%s recipients=%s",
            context.run_id,
            ",".join(self._config.recipients),
        )

    def stop(self) -> None:
        self._active = False
        self._current_context = None

    def notify_failure(self, notification: StepNotification) -> None:
        if not self._should_send():
            return
        subject = f"{self._config.subject_prefix} Step failed: {notification.step_id}"
        body = self._build_failure_body(notification)
        self._send(subject, body)

    def notify_human_input(self, notification: StepNotification) -> None:
        if not self._should_send():
            return
        subject = f"{self._config.subject_prefix} Step paused for input: {notification.step_id}"
        body = self._build_human_input_body(notification)
        self._send(subject, body)

    def _should_send(self) -> bool:
        if not self._active:
            return False
        if not self._config.enabled or not self._config.smtp:
            return False
        if not self._config.recipients:
            return False
        return True

    def _send(self, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        if self._config.sender:
            msg["From"] = self._config.sender
        msg["To"] = ", ".join(self._config.recipients)
        msg.set_content(body)

        try:
            with self._transport_factory(self._config.smtp) as client:
                client.send_message(msg)
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.exception("Failed to send notification email: %s", exc)

    def _build_failure_body(self, notification: StepNotification) -> str:
        lines = [
            f"Workflow: {notification.workflow_name}",
            f"Run ID: {notification.run_id}",
            f"Step: {notification.step_id}",
            f"Attempt: {notification.attempt}",
            f"Status: {notification.status.value}",
        ]
        if notification.last_error:
            lines.append("")
            lines.append("Error Summary:")
            lines.append(notification.last_error)
        if notification.logs:
            lines.append("")
            lines.append("Recent Logs:")
            lines.extend(notification.logs[:10])
        if notification.report_path:
            lines.append("")
            lines.append(f"Run report: {notification.report_path}")
        return "\n".join(lines)

    def _build_human_input_body(self, notification: StepNotification) -> str:
        lines = [
            f"Workflow: {notification.workflow_name}",
            f"Run ID: {notification.run_id}",
            f"Step: {notification.step_id}",
            f"Attempt: {notification.attempt}",
            "",
            "The workflow is waiting for manual input to proceed.",
        ]
        if notification.manual_input_path:
            lines.append(f"Provide input at: {notification.manual_input_path}")
        if notification.report_path:
            lines.append(f"Latest run report: {notification.report_path}")
        if notification.logs:
            lines.append("")
            lines.append("Recent Logs:")
            lines.extend(notification.logs[:10])
        return "\n".join(lines)


def build_email_notification_service(
    repo_dir: Path,
    *,
    logger: Optional[logging.Logger] = None,
    config_path: Optional[Path] = None,
) -> NotificationService:
    """Construct the notification service for a repository."""

    config = load_email_notification_config(repo_dir, config_path=config_path)
    return EmailNotificationService(config, logger=logger)


__all__ = [
    "EmailNotificationService",
    "EmailNotificationConfig",
    "EmailConfigError",
    "SMTPSettings",
    "build_email_notification_service",
    "load_email_notification_config",
]
