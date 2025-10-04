import logging

from agent_orchestrator.models import Step, Workflow, StepStatus
from agent_orchestrator.orchestrator import Orchestrator
from agent_orchestrator.reporting import RunReportReader
from agent_orchestrator.runner import ExecutionTemplate, StepRunner
from agent_orchestrator.state import RunStatePersister


def build_step(step_id: str, agent: str, prompt: str, needs=None) -> Step:
    return Step(id=step_id, agent=agent, prompt=prompt, needs=needs or [])


def test_step_runner_injects_issue_markdown_env(monkeypatch, tmp_path):
    monkeypatch.delenv("ISSUE_MARKDOWN_PATH", raising=False)
    monkeypatch.delenv("ISSUE_MARKDOWN_DIR", raising=False)
    monkeypatch.delenv("ISSUE_MARKDOWN_FILENAME", raising=False)

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    logs_dir = tmp_path / "logs"
    runner = StepRunner(
        execution_template=ExecutionTemplate("echo test"),
        repo_dir=repo_dir,
        logs_dir=logs_dir,
        default_env={"ISSUE_NUMBER": "88"},
    )

    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("# prompt", encoding="utf-8")
    report_path = tmp_path / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    artifacts_dir = repo_dir / ".agents" / "runs" / "testrun" / "artifacts"
    artifacts_dir.mkdir(parents=True)

    captured_env = {}

    class DummyProcess:
        def poll(self):
            return 0

    def fake_popen(command, cwd, env, stdout, stderr, text):
        nonlocal captured_env
        captured_env = env
        return DummyProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    step = build_step("fetch_github_issue", "github_issue_fetcher", "prompt.md")
    launch = runner.launch(
        step=step,
        run_id="testrun",
        report_path=report_path,
        prompt_path=prompt_path,
        attempt=1,
        artifacts_dir=artifacts_dir,
    )

    launch.close_log()

    expected_path = artifacts_dir / "gh_issue_88.md"
    assert captured_env["ISSUE_MARKDOWN_PATH"] == str(expected_path)
    assert captured_env["ISSUE_MARKDOWN_DIR"] == str(expected_path.parent)
    assert captured_env["ISSUE_MARKDOWN_FILENAME"] == "gh_issue_88.md"


def test_planner_receives_issue_artifact_path(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    workflow_root = tmp_path / "workflows"
    workflow_root.mkdir()

    fetch_prompt = workflow_root / "fetch.md"
    fetch_prompt.write_text("# fetch", encoding="utf-8")
    plan_prompt = workflow_root / "plan.md"
    plan_prompt.write_text("# plan", encoding="utf-8")

    workflow = Workflow(
        name="github_issue_pipeline",
        description="",
        steps={
            "fetch_github_issue": build_step("fetch_github_issue", "github_issue_fetcher", "fetch.md"),
            "github_issue_plan": build_step("github_issue_plan", "dev_architect", "plan.md", needs=["fetch_github_issue"]),
        },
    )

    runner = StepRunner(
        execution_template=ExecutionTemplate("echo test"),
        repo_dir=repo_dir,
        logs_dir=tmp_path / "logs",
        default_env={"ISSUE_NUMBER": "77"},
    )

    orchestrator = Orchestrator(
        workflow=workflow,
        workflow_root=workflow_root,
        repo_dir=repo_dir,
        report_reader=RunReportReader(),
        state_persister=RunStatePersister(tmp_path / "state.json"),
        runner=runner,
        logger=logging.getLogger(__name__),
    )

    issue_path = orchestrator._artifacts_dir / "gh_issue_77.md"
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    issue_path.write_text("contents", encoding="utf-8")
    issue_relative = issue_path.relative_to(repo_dir)

    fetch_runtime = orchestrator._state.steps["fetch_github_issue"]
    fetch_runtime.status = StepStatus.COMPLETED
    fetch_runtime.artifacts = [str(issue_relative)]

    env = orchestrator._collect_dependency_artifacts(workflow.steps["github_issue_plan"])

    expected_absolute = issue_path
    assert env["DEP_FETCH_GITHUB_ISSUE_ARTIFACT_0"] == str(expected_absolute)
    assert env["DEP_FETCH_GITHUB_ISSUE_ARTIFACTS"] == str(expected_absolute)
    assert env["ISSUE_MARKDOWN_PATH"] == str(expected_absolute)
    assert env["ISSUE_MARKDOWN_DIR"] == str(expected_absolute.parent)
    assert env["ISSUE_MARKDOWN_FILENAME"] == expected_absolute.name
    assert expected_absolute.is_file()
    assert str(orchestrator._artifacts_dir) in str(expected_absolute)
