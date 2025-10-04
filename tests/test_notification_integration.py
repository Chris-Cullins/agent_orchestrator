from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from agent_orchestrator.models import Step, StepStatus, Workflow
from agent_orchestrator.notifications import NotificationService
from agent_orchestrator.orchestrator import Orchestrator
from agent_orchestrator.reporting import RunReportReader
from agent_orchestrator.runner import StepRunner
from agent_orchestrator.state import RunStatePersister


@pytest.fixture
def repo_with_prompts(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "prompts").mkdir(parents=True)
    (repo / "prompts" / "step.md").write_text("prompt", encoding="utf-8")
    return repo


def _make_launch(report_path: Path) -> Mock:
    launch = Mock()
    launch.process = Mock()
    launch.process.poll = Mock(return_value=0)
    launch.process.returncode = 0
    launch.report_path = report_path
    launch.close_log = Mock()
    return launch


def test_failure_event_triggers_notification(repo_with_prompts: Path, tmp_path: Path) -> None:
    workflow = Workflow(
        name="demo",
        description="test",
        steps={
            "fail_step": Step(
                id="fail_step",
                agent="agent",
                prompt="prompts/step.md",
                needs=[],
            )
        },
    )

    report_reader = RunReportReader()
    state_persister = RunStatePersister(tmp_path / "state.json")

    runner = Mock(spec=StepRunner)

    def launch(step, **kwargs):
        report_path: Path = kwargs["report_path"]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "schema": "run_report@v0",
            "run_id": kwargs["run_id"],
            "step_id": step.id,
            "agent": step.agent,
            "status": "FAILED",
            "started_at": "2025-01-01T00:00:00Z",
            "ended_at": "2025-01-01T00:01:00Z",
            "artifacts": [],
            "metrics": {},
            "logs": ["Compilation failed"],
        }
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle)
        return _make_launch(report_path)

    runner.launch.side_effect = launch

    notification_service = Mock(spec=NotificationService)

    orchestrator = Orchestrator(
        workflow=workflow,
        workflow_root=repo_with_prompts,
        repo_dir=repo_with_prompts,
        report_reader=report_reader,
        state_persister=state_persister,
        runner=runner,
        max_attempts=1,
        notification_service=notification_service,
    )

    orchestrator.run()

    notification_service.notify_failure.assert_called_once()
    payload = notification_service.notify_failure.call_args.args[0]
    assert payload.step_id == "fail_step"
    assert payload.status == StepStatus.FAILED


def test_pause_event_triggers_notification(repo_with_prompts: Path, tmp_path: Path) -> None:
    step = Step(
        id="human_step",
        agent="agent",
        prompt="prompts/step.md",
        needs=[],
        human_in_the_loop=True,
    )
    workflow = Workflow(name="demo", description="test", steps={step.id: step})

    report_reader = RunReportReader()
    state_persister = RunStatePersister(tmp_path / "state.json")

    runner = Mock(spec=StepRunner)

    def launch(step, **kwargs):
        report_path: Path = kwargs["report_path"]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "schema": "run_report@v0",
            "run_id": kwargs["run_id"],
            "step_id": step.id,
            "agent": step.agent,
            "status": "COMPLETED",
            "started_at": "2025-01-01T00:00:00Z",
            "ended_at": "2025-01-01T00:01:00Z",
            "artifacts": [],
            "metrics": {},
            "logs": ["Waiting on approval"],
        }
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle)
        launch_obj = _make_launch(report_path)
        return launch_obj

    runner.launch.side_effect = launch

    notification_service = Mock(spec=NotificationService)

    def on_notify(notification):
        manual_path = notification.manual_input_path
        assert manual_path is not None
        manual_path.write_text("approved", encoding="utf-8")

    notification_service.notify_human_input.side_effect = on_notify

    orchestrator = Orchestrator(
        workflow=workflow,
        workflow_root=repo_with_prompts,
        repo_dir=repo_with_prompts,
        report_reader=report_reader,
        state_persister=state_persister,
        runner=runner,
        pause_for_human_input=True,
        notification_service=notification_service,
    )

    orchestrator.run()

    notification_service.notify_human_input.assert_called_once()
    payload = notification_service.notify_human_input.call_args.args[0]
    assert payload.step_id == "human_step"
    assert payload.status == StepStatus.WAITING_ON_HUMAN
