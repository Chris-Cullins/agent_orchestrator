"""Tests for loop-back functionality in the orchestrator."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, List
from unittest.mock import Mock, patch

import pytest

from agent_orchestrator.models import Step, Workflow, StepStatus, RunReport
from agent_orchestrator.orchestrator import Orchestrator
from agent_orchestrator.reporting import RunReportReader
from agent_orchestrator.runner import StepRunner, ExecutionTemplate
from agent_orchestrator.state import RunStatePersister


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository directory."""
    repo = tmp_path / "repo"
    repo.mkdir()
    prompts_dir = repo / "prompts"
    prompts_dir.mkdir()
    for name in ["code.md", "review.md", "prep.md", "fix.md", "gate.md"]:
        (prompts_dir / name).write_text("stub", encoding="utf-8")
    return repo


@pytest.fixture
def mock_runner(tmp_path: Path) -> StepRunner:
    """Create a mock runner that doesn't actually execute anything."""
    template = ExecutionTemplate("echo {step_id}")
    return StepRunner(
        execution_template=template,
        repo_dir=tmp_path / "repo",
        logs_dir=tmp_path / "logs",
        workdir=tmp_path / "repo",
    )


@pytest.fixture
def report_reader() -> RunReportReader:
    """Create a report reader without schema validation."""
    return RunReportReader()


@pytest.fixture
def state_persister(tmp_path: Path) -> RunStatePersister:
    """Create a state persister for test runs."""
    state_file = tmp_path / "state.json"
    return RunStatePersister(state_file)


def create_workflow_with_loopback() -> Workflow:
    """Create a test workflow with loop-back capability."""
    return Workflow(
        name="test_loopback",
        description="Workflow to test loop-back",
        steps={
            "step_a": Step(
                id="step_a",
                agent="coder",
                prompt="prompts/code.md",
                needs=[],
            ),
            "step_b": Step(
                id="step_b",
                agent="reviewer",
                prompt="prompts/review.md",
                needs=["step_a"],
                loop_back_to="step_a",
            ),
        },
    )


def write_report(
    report_path: Path,
    run_id: str,
    step_id: str,
    agent: str,
    status: str = "COMPLETED",
    gate_failure: bool = False,
) -> None:
    """Helper to write a run report."""
    report = {
        "schema": "run_report_v1",
        "run_id": run_id,
        "step_id": step_id,
        "agent": agent,
        "status": status,
        "started_at": "2025-01-01T00:00:00Z",
        "ended_at": "2025-01-01T00:01:00Z",
        "artifacts": [],
        "metrics": {},
        "logs": [],
        "gate_failure": gate_failure,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w") as f:
        json.dump(report, f)


def test_loopback_on_gate_failure(temp_repo: Path, report_reader: RunReportReader, state_persister: RunStatePersister):
    """Test that gate failure triggers loop-back."""
    workflow = create_workflow_with_loopback()
    
    # Mock the runner to track launches
    launches: List[str] = []
    
    def mock_launch(step, **kwargs):
        launches.append(step.id)
        launch = Mock()
        launch.process = Mock()
        launch.process.poll = Mock(return_value=None)  # Process running
        launch.report_path = kwargs["report_path"]
        launch.close_log = Mock()
        
        # Write report after a short delay to simulate agent work
        def write_delayed_report():
            time.sleep(0.1)
            gate_failure = step.id == "step_b" and launches.count("step_b") == 1
            write_report(
                kwargs["report_path"],
                kwargs["run_id"],
                step.id,
                step.agent,
                status="COMPLETED",
                gate_failure=gate_failure,
            )
            launch.process.poll = Mock(return_value=0)  # Process finished
        
        import threading
        threading.Thread(target=write_delayed_report, daemon=True).start()
        return launch
    
    mock_runner = Mock(spec=StepRunner)
    mock_runner.launch = Mock(side_effect=mock_launch)
    
    orchestrator = Orchestrator(
        workflow=workflow,
        workflow_root=temp_repo,
        repo_dir=temp_repo,
        report_reader=report_reader,
        state_persister=state_persister,
        runner=mock_runner,
        poll_interval=0.1,
        max_attempts=2,
        max_iterations=3,
        logger=logging.getLogger(__name__),
    )
    
    # Run in a separate thread with timeout
    import threading
    run_thread = threading.Thread(target=orchestrator.run, daemon=True)
    run_thread.start()
    run_thread.join(timeout=5.0)
    
    # Verify loop-back occurred
    assert "step_a" in launches
    assert "step_b" in launches
    assert launches.count("step_a") >= 2, "step_a should run at least twice due to loop-back"
    assert launches.count("step_b") >= 2, "step_b should run at least twice"


def test_loopback_blocks_when_not_a_direct_dependency(
    temp_repo: Path, report_reader: RunReportReader, state_persister: RunStatePersister
):
    """Ensure loop-back waits for target step even if not a declared dependency."""
    workflow = Workflow(
        name="loopback_blocker",
        description="",
        steps={
            "prep": Step(
                id="prep",
                agent="prepper",
                prompt="prompts/prep.md",
                needs=[],
            ),
            "fix": Step(
                id="fix",
                agent="coder",
                prompt="prompts/fix.md",
                needs=["prep"],
            ),
            "gate": Step(
                id="gate",
                agent="reviewer",
                prompt="prompts/gate.md",
                needs=["prep"],  # Does not depend on "fix"
                loop_back_to="fix",
            ),
        },
    )

    launches: List[str] = []

    def mock_launch(step, **kwargs):
        launches.append(step.id)
        launch = Mock()
        launch.process = Mock()
        launch.process.poll = Mock(return_value=None)
        launch.report_path = kwargs["report_path"]
        launch.close_log = Mock()

        def write_delayed_report() -> None:
            time.sleep(0.05)
            gate_failure = step.id == "gate" and launches.count("gate") == 1
            write_report(
                kwargs["report_path"],
                kwargs["run_id"],
                step.id,
                step.agent,
                status="COMPLETED",
                gate_failure=gate_failure,
            )
            launch.process.poll = Mock(return_value=0)

        import threading

        threading.Thread(target=write_delayed_report, daemon=True).start()
        return launch

    mock_runner = Mock(spec=StepRunner)
    mock_runner.launch = Mock(side_effect=mock_launch)

    orchestrator = Orchestrator(
        workflow=workflow,
        workflow_root=temp_repo,
        repo_dir=temp_repo,
        report_reader=report_reader,
        state_persister=state_persister,
        runner=mock_runner,
        poll_interval=0.05,
        max_attempts=2,
        max_iterations=3,
        logger=logging.getLogger(__name__),
    )

    import threading

    run_thread = threading.Thread(target=orchestrator.run, daemon=True)
    run_thread.start()
    run_thread.join(timeout=3.0)

    gate_runs = [idx for idx, step_id in enumerate(launches) if step_id == "gate"]
    fix_runs = [idx for idx, step_id in enumerate(launches) if step_id == "fix"]

    assert len(gate_runs) >= 2, "gate step should run twice"
    assert len(fix_runs) >= 2, "fix step should re-run before second gate run"
    assert fix_runs[1] < gate_runs[1], "loop-back should rerun fix before gate"
    assert orchestrator._state.steps["gate"].blocked_by_loop is None


def test_max_iterations_enforced(temp_repo: Path, report_reader: RunReportReader, state_persister: RunStatePersister):
    """Test that max iterations limit is enforced."""
    workflow = create_workflow_with_loopback()
    
    max_iterations = 2
    launches: List[str] = []
    
    def mock_launch(step, **kwargs):
        launches.append(step.id)
        launch = Mock()
        launch.process = Mock()
        launch.process.poll = Mock(return_value=None)
        launch.report_path = kwargs["report_path"]
        launch.close_log = Mock()
        
        def write_delayed_report():
            time.sleep(0.05)
            # Always fail gate for step_b to trigger loop-back
            gate_failure = step.id == "step_b"
            write_report(
                kwargs["report_path"],
                kwargs["run_id"],
                step.id,
                step.agent,
                status="COMPLETED",
                gate_failure=gate_failure,
            )
            launch.process.poll = Mock(return_value=0)
        
        import threading
        threading.Thread(target=write_delayed_report, daemon=True).start()
        return launch
    
    mock_runner = Mock(spec=StepRunner)
    mock_runner.launch = Mock(side_effect=mock_launch)
    
    orchestrator = Orchestrator(
        workflow=workflow,
        workflow_root=temp_repo,
        repo_dir=temp_repo,
        report_reader=report_reader,
        state_persister=state_persister,
        runner=mock_runner,
        poll_interval=0.05,
        max_attempts=2,
        max_iterations=max_iterations,
        logger=logging.getLogger(__name__),
    )
    
    # Run with timeout
    import threading
    run_thread = threading.Thread(target=orchestrator.run, daemon=True)
    run_thread.start()
    run_thread.join(timeout=3.0)
    
    # Verify iteration limit was hit
    step_b_runtime = orchestrator._state.steps["step_b"]
    assert step_b_runtime.status == StepStatus.FAILED
    assert step_b_runtime.iteration_count >= max_iterations
    assert step_b_runtime.last_error is not None
    assert "max iterations" in step_b_runtime.last_error.lower()


def test_iteration_count_increments(temp_repo: Path, report_reader: RunReportReader, state_persister: RunStatePersister):
    """Test that iteration_count increments correctly during loop-back."""
    workflow = create_workflow_with_loopback()
    
    launches: List[str] = []
    
    def mock_launch(step, **kwargs):
        launches.append(step.id)
        launch = Mock()
        launch.process = Mock()
        launch.process.poll = Mock(return_value=None)
        launch.report_path = kwargs["report_path"]
        launch.close_log = Mock()
        
        def write_delayed_report():
            time.sleep(0.05)
            # Fail gate only on first step_b run
            gate_failure = step.id == "step_b" and launches.count("step_b") == 1
            write_report(
                kwargs["report_path"],
                kwargs["run_id"],
                step.id,
                step.agent,
                status="COMPLETED",
                gate_failure=gate_failure,
            )
            launch.process.poll = Mock(return_value=0)
        
        import threading
        threading.Thread(target=write_delayed_report, daemon=True).start()
        return launch
    
    mock_runner = Mock(spec=StepRunner)
    mock_runner.launch = Mock(side_effect=mock_launch)
    
    orchestrator = Orchestrator(
        workflow=workflow,
        workflow_root=temp_repo,
        repo_dir=temp_repo,
        report_reader=report_reader,
        state_persister=state_persister,
        runner=mock_runner,
        poll_interval=0.05,
        max_attempts=2,
        max_iterations=4,
        logger=logging.getLogger(__name__),
    )
    
    # Run with timeout
    import threading
    run_thread = threading.Thread(target=orchestrator.run, daemon=True)
    run_thread.start()
    run_thread.join(timeout=3.0)
    
    # Verify iteration count
    step_b_runtime = orchestrator._state.steps["step_b"]
    assert step_b_runtime.iteration_count >= 1, "iteration_count should increment after loop-back"


def test_loopback_resets_attempts_between_iterations(
    temp_repo: Path, report_reader: RunReportReader, state_persister: RunStatePersister
):
    """Ensure gate retries get fresh attempt counters for each loop iteration."""
    workflow = create_workflow_with_loopback()

    launches: List[str] = []
    step_b_attempts: List[int] = []
    target_failures = 3

    def mock_launch(step, **kwargs):
        launches.append(step.id)
        if step.id == "step_b":
            step_b_attempts.append(kwargs["attempt"])

        launch = Mock()
        launch.process = Mock()
        launch.process.poll = Mock(return_value=None)
        launch.report_path = kwargs["report_path"]
        launch.close_log = Mock()

        def write_delayed_report() -> None:
            time.sleep(0.05)
            gate_failure = step.id == "step_b"
            write_report(
                kwargs["report_path"],
                kwargs["run_id"],
                step.id,
                step.agent,
                status="COMPLETED",
                gate_failure=gate_failure,
            )
            launch.process.poll = Mock(return_value=0)

        import threading

        threading.Thread(target=write_delayed_report, daemon=True).start()
        return launch

    mock_runner = Mock(spec=StepRunner)
    mock_runner.launch = Mock(side_effect=mock_launch)

    orchestrator = Orchestrator(
        workflow=workflow,
        workflow_root=temp_repo,
        repo_dir=temp_repo,
        report_reader=report_reader,
        state_persister=state_persister,
        runner=mock_runner,
        poll_interval=0.05,
        max_attempts=1,
        max_iterations=target_failures,
        logger=logging.getLogger(__name__),
    )

    import threading

    run_thread = threading.Thread(target=orchestrator.run, daemon=True)
    run_thread.start()
    run_thread.join(timeout=5.0)
    assert not run_thread.is_alive(), "orchestrator.run did not finish"

    assert len(step_b_attempts) == target_failures + 1
    assert all(attempt == 1 for attempt in step_b_attempts)


def test_loopback_without_gate_failure(temp_repo: Path, report_reader: RunReportReader, state_persister: RunStatePersister):
    """Test that workflow completes normally without gate failure."""
    workflow = create_workflow_with_loopback()
    
    launches: List[str] = []
    
    def mock_launch(step, **kwargs):
        launches.append(step.id)
        launch = Mock()
        launch.process = Mock()
        launch.process.poll = Mock(return_value=None)
        launch.report_path = kwargs["report_path"]
        launch.close_log = Mock()
        
        def write_delayed_report():
            time.sleep(0.05)
            # Never trigger gate failure
            write_report(
                kwargs["report_path"],
                kwargs["run_id"],
                step.id,
                step.agent,
                status="COMPLETED",
                gate_failure=False,
            )
            launch.process.poll = Mock(return_value=0)
        
        import threading
        threading.Thread(target=write_delayed_report, daemon=True).start()
        return launch
    
    mock_runner = Mock(spec=StepRunner)
    mock_runner.launch = Mock(side_effect=mock_launch)
    
    orchestrator = Orchestrator(
        workflow=workflow,
        workflow_root=temp_repo,
        repo_dir=temp_repo,
        report_reader=report_reader,
        state_persister=state_persister,
        runner=mock_runner,
        poll_interval=0.05,
        max_attempts=2,
        max_iterations=4,
        logger=logging.getLogger(__name__),
    )
    
    # Run with timeout
    import threading
    run_thread = threading.Thread(target=orchestrator.run, daemon=True)
    run_thread.start()
    run_thread.join(timeout=2.0)
    
    # Verify workflow completed successfully
    assert launches.count("step_a") == 1, "step_a should run only once"
    assert launches.count("step_b") == 1, "step_b should run only once"
    
    step_a_runtime = orchestrator._state.steps["step_a"]
    step_b_runtime = orchestrator._state.steps["step_b"]
    assert step_a_runtime.status == StepStatus.COMPLETED
    assert step_b_runtime.status == StepStatus.COMPLETED
    assert step_b_runtime.iteration_count == 0, "No loop-back should occur"


def test_report_reader_parses_gate_failure():
    """Test that RunReportReader correctly parses gate_failure field."""
    reader = RunReportReader()
    
    report_data = {
        "schema": "run_report_v1",
        "run_id": "test-123",
        "step_id": "step_a",
        "agent": "test_agent",
        "status": "COMPLETED",
        "started_at": "2025-01-01T00:00:00Z",
        "ended_at": "2025-01-01T00:01:00Z",
        "gate_failure": True,
    }
    
    temp_path = Path("/tmp/test_report.json")
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    with temp_path.open("w") as f:
        json.dump(report_data, f)
    
    try:
        report = reader.read(temp_path)
        assert report.gate_failure is True
    finally:
        temp_path.unlink(missing_ok=True)


def test_report_reader_gate_failure_defaults_to_false():
    """Test that gate_failure defaults to False when not present."""
    reader = RunReportReader()
    
    report_data = {
        "schema": "run_report_v1",
        "run_id": "test-123",
        "step_id": "step_a",
        "agent": "test_agent",
        "status": "COMPLETED",
        "started_at": "2025-01-01T00:00:00Z",
        "ended_at": "2025-01-01T00:01:00Z",
    }
    
    temp_path = Path("/tmp/test_report_no_gate.json")
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    with temp_path.open("w") as f:
        json.dump(report_data, f)
    
    try:
        report = reader.read(temp_path)
        assert report.gate_failure is False
    finally:
        temp_path.unlink(missing_ok=True)
