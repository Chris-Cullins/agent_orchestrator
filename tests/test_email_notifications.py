from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from agent_orchestrator.models import StepStatus
from agent_orchestrator.notifications import RunContext, StepNotification
from agent_orchestrator.notifications.email import (
    EmailConfigError,
    EmailNotificationConfig,
    EmailNotificationService,
    SMTPSettings,
    build_email_notification_service,
    load_email_notification_config,
)


def test_load_config_missing_file_defaults_disabled(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    config = load_email_notification_config(repo_dir)

    assert config.enabled is False
    assert config.smtp is None
    assert config.recipients == []


def test_load_config_invalid_recipients_raises(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    config_dir = repo_dir / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "email_notifications.yaml").write_text(
        "enabled: true\nsender: 'ops@example.com'\nrecipients: 'not-a-list'\nsmtp:\n  host: example\n  port: 25\n",
        encoding="utf-8",
    )

    with pytest.raises(EmailConfigError):
        load_email_notification_config(repo_dir)


class DummyTransport:
    def __init__(self, store: list[str | object]) -> None:
        self.store = store

    def __enter__(self) -> DummyTransport:
        return self

    def send_message(self, message) -> None:  # type: ignore[override]
        self.store.append(message)

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - no cleanup needed
        self.store.append("closed")
        return False


def test_email_service_sends_failure_notification(tmp_path: Path) -> None:
    smtp = SMTPSettings(host="smtp.example.com", port=25, use_tls=False)
    config = EmailNotificationConfig(
        enabled=True,
        sender="orchestrator@example.com",
        recipients=["dev@example.com"],
        smtp=smtp,
        subject_prefix="[Test]",
    )
    sent: list[object] = []
    service = EmailNotificationService(
        config,
        transport_factory=lambda settings: DummyTransport(sent),
    )

    service.start(RunContext(run_id="abc123", workflow_name="demo", repo_dir=tmp_path))
    notification = StepNotification(
        run_id="abc123",
        workflow_name="demo",
        step_id="code",
        attempt=1,
        status=StepStatus.FAILED,
        trigger="failure",
        manual_input_path=None,
        report_path=tmp_path / "report.json",
        logs=["Example log line"],
        last_error="Compilation failed",
    )

    service.notify_failure(notification)

    assert len(sent) == 2  # message + "closed"
    message = sent[0]
    assert message["Subject"] == "[Test] Step failed: code"
    assert "Compilation failed" in message.get_content()


def test_email_service_disabled_skips_transport(tmp_path: Path) -> None:
    config = EmailNotificationConfig(enabled=False)
    transport = Mock()
    service = EmailNotificationService(config, transport_factory=lambda settings: transport)

    service.start(RunContext(run_id="abc123", workflow_name="demo", repo_dir=tmp_path))
    notification = StepNotification(
        run_id="abc123",
        workflow_name="demo",
        step_id="code",
        attempt=1,
        status=StepStatus.FAILED,
        trigger="failure",
        manual_input_path=None,
        report_path=None,
        logs=[],
        last_error=None,
    )

    service.notify_failure(notification)

    transport.assert_not_called()


def test_build_notification_service_returns_instance(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    service = build_email_notification_service(repo_dir)

    assert isinstance(service, EmailNotificationService)
