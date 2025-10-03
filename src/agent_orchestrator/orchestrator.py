from __future__ import annotations

import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from .gating import GateEvaluator, AlwaysOpenGateEvaluator, CompositeGateEvaluator
from .models import RunState, Step, StepRuntime, StepStatus, Workflow, utc_now
from .reporting import RunReportError, RunReportReader
from .runner import ExecutionTemplate, StepLaunch, StepRunner
from .state import RunStatePersister


class Orchestrator:
    def __init__(
        self,
        workflow: Workflow,
        workflow_root: Path,
        repo_dir: Path,
        report_reader: RunReportReader,
        state_persister: RunStatePersister,
        runner: StepRunner,
        gate_evaluator: Optional[GateEvaluator] = None,
        poll_interval: float = 1.0,
        max_attempts: int = 2,
        pause_for_human_input: bool = False,
        logger: Optional[logging.Logger] = None,
        run_id: Optional[str] = None,
        start_at_step: Optional[str] = None,
    ) -> None:
        self._workflow = workflow
        self._workflow_root = workflow_root
        self._repo_dir = repo_dir
        self._report_reader = report_reader
        self._state_persister = state_persister
        self._runner = runner
        self._gate_evaluator = (
            gate_evaluator
            if gate_evaluator
            else CompositeGateEvaluator(AlwaysOpenGateEvaluator())
        )
        self._poll_interval = poll_interval
        self._max_attempts = max(1, max_attempts)
        self._pause_for_human = pause_for_human_input
        self._log = logger or logging.getLogger(__name__)

        # Try to load existing state if resuming
        existing_state = state_persister.load() if start_at_step else None

        if existing_state and start_at_step:
            # Resume from existing state
            run_id = existing_state["run_id"]
            self._state = self._load_state_from_dict(existing_state, workflow)
            self._reset_steps_from(start_at_step, workflow)
            self._log.info(
                "Resuming run_id=%s from step=%s",
                run_id,
                start_at_step,
            )
        else:
            # Start a new run
            run_id = run_id or uuid.uuid4().hex[:8]

        # Create run-specific directory structure under .agents/runs/<run_id>/
        self._run_dir = repo_dir / ".agents" / "runs" / run_id
        self._reports_dir = self._run_dir / "reports"
        self._logs_dir = self._run_dir / "logs"
        self._artifacts_dir = self._run_dir / "artifacts"
        self._manual_inputs_dir = self._run_dir / "manual_inputs"

        # Create all run-specific directories
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        if self._pause_for_human:
            self._manual_inputs_dir.mkdir(parents=True, exist_ok=True)

        # Update state persister to use run-specific state file
        state_persister.set_path(self._run_dir / "run_state.json")

        # Initialize or update state with run-specific directories
        if not (existing_state and start_at_step):
            self._state = RunState(
                run_id=run_id,
                workflow_name=workflow.name,
                repo_dir=repo_dir,
                reports_dir=self._reports_dir,
                manual_inputs_dir=self._manual_inputs_dir,
                steps={step_id: StepRuntime() for step_id in workflow.steps},
            )

        self._active_processes: Dict[str, StepLaunch] = {}

    @property
    def run_id(self) -> str:
        return self._state.run_id

    def run(self) -> None:
        self._log.info(
            "workflow=%s run_id=%s repo=%s",
            self._workflow.name,
            self._state.run_id,
            self._repo_dir,
        )
        try:
            while True:
                progress = False
                progress |= self._launch_ready_steps()
                progress |= self._collect_reports()
                progress |= self._check_manual_steps()

                self._persist_state()

                if self._all_steps_finished():
                    self._log.info("workflow complete run_id=%s", self._state.run_id)
                    break
                if self._has_terminal_failure():
                    self._log.error("workflow failed run_id=%s", self._state.run_id)
                    break
                if not progress:
                    time.sleep(self._poll_interval)
        finally:
            self._cleanup_processes()
            self._persist_state()

    def _launch_ready_steps(self) -> bool:
        launched = False
        for step_id, step in self._workflow.steps.items():
            runtime = self._state.steps[step_id]
            if runtime.status != StepStatus.PENDING:
                continue
            if step_id in self._active_processes:
                continue
            if not self._dependencies_satisfied(step):
                continue
            if not self._gates_open(step):
                continue

            report_path = self._reports_dir / f"{self._state.run_id}__{step.id}.json"
            manual_input_path = (
                self._manual_inputs_dir / f"{self._state.run_id}__{step.id}.json"
                if step.human_in_the_loop and self._pause_for_human
                else None
            )

            prompt_path = self._resolve_prompt_path(step.prompt)

            runtime.status = StepStatus.RUNNING
            runtime.attempts += 1
            runtime.started_at = utc_now()
            runtime.report_path = report_path
            runtime.manual_input_path = manual_input_path

            try:
                launch = self._runner.launch(
                    step=step,
                    run_id=self._state.run_id,
                    report_path=report_path,
                    prompt_path=prompt_path,
                    manual_input_path=manual_input_path,
                    attempt=runtime.attempts,
                    artifacts_dir=self._artifacts_dir,
                    logs_dir=self._logs_dir,
                )
            except Exception as exc:  # pragma: no cover
                runtime.status = StepStatus.FAILED
                runtime.last_error = str(exc)
                runtime.ended_at = utc_now()
                self._log.exception("failed to launch step=%s", step_id)
                continue

            self._log.info(
                "launched step=%s agent=%s attempt=%s", step.id, step.agent, runtime.attempts
            )
            self._active_processes[step_id] = launch
            launched = True
        return launched

    def _collect_reports(self) -> bool:
        progressed = False
        to_remove = []
        for step_id, launch in list(self._active_processes.items()):
            runtime = self._state.steps[step_id]
            process_finished = launch.process.poll() is not None

            if launch.report_path.exists():
                try:
                    report = self._report_reader.read(launch.report_path)
                except RunReportError as exc:
                    # If process is still running, the report may be incomplete - wait
                    if not process_finished:
                        continue
                    # Process finished but report is invalid - fail the step
                    runtime.last_error = str(exc)
                    runtime.status = StepStatus.FAILED
                    runtime.ended_at = utc_now()
                    self._log.error("invalid run report step=%s error=%s", step_id, exc)
                    to_remove.append(step_id)
                    progressed = True
                    continue

                runtime.ended_at = report.ended_at
                runtime.artifacts = report.artifacts
                runtime.metrics = report.metrics
                runtime.logs = report.logs

                if report.status == "COMPLETED":
                    if runtime.manual_input_path and self._pause_for_human:
                        runtime.status = StepStatus.WAITING_ON_HUMAN
                        self._log.info("awaiting human input step=%s", step_id)
                    else:
                        runtime.status = StepStatus.COMPLETED
                        self._log.info("step completed step=%s", step_id)
                else:
                    runtime.status = StepStatus.FAILED
                    runtime.last_error = ", ".join(report.logs[-3:]) if report.logs else "Agent reported failure"
                    self._log.warning("step failed step=%s logs=%s", step_id, runtime.last_error)

                to_remove.append(step_id)
                progressed = True
            elif process_finished:
                runtime.status = StepStatus.FAILED
                runtime.ended_at = utc_now()
                runtime.last_error = (
                    f"Agent process exited with code {launch.process.returncode} without writing a run report"
                )
                self._log.error("step failed without report step=%s", step_id)
                to_remove.append(step_id)
                progressed = True

        for step_id in to_remove:
            launch = self._active_processes.pop(step_id)
            launch.close_log()
            runtime = self._state.steps[step_id]
            if runtime.status == StepStatus.FAILED and runtime.attempts < self._max_attempts:
                runtime.status = StepStatus.PENDING
                runtime.last_error = runtime.last_error or "retry scheduled"
                runtime.report_path = None
                runtime.started_at = None
                runtime.ended_at = None
                self._log.info("retrying step=%s next_attempt=%s", step_id, runtime.attempts + 1)

        return progressed

    def _check_manual_steps(self) -> bool:
        if not self._pause_for_human:
            return False

        progressed = False
        for step_id, runtime in self._state.steps.items():
            if runtime.status != StepStatus.WAITING_ON_HUMAN:
                continue
            if not runtime.manual_input_path:
                continue
            if runtime.manual_input_path.exists():
                runtime.status = StepStatus.COMPLETED
                runtime.ended_at = runtime.ended_at or utc_now()
                progressed = True
                self._log.info("manual input received step=%s", step_id)
        return progressed

    def _dependencies_satisfied(self, step: Step) -> bool:
        return all(
            self._state.steps[dep].status in {StepStatus.COMPLETED, StepStatus.SKIPPED}
            for dep in step.needs
        )

    def _gates_open(self, step: Step) -> bool:
        for gate in step.gates:
            if not self._gate_evaluator.evaluate(step, gate):
                self._log.info("gate blocked step=%s gate=%s", step.id, gate)
                return False
        return True

    def _resolve_prompt_path(self, prompt: str) -> Path:
        candidate = Path(prompt)
        if candidate.is_absolute() and candidate.exists():
            return candidate

        # Check for local prompt override in target repo first
        prompt_filename = Path(prompt).name
        local_override = (self._repo_dir / ".agents" / "prompts" / prompt_filename).resolve()
        if local_override.exists():
            self._log.info("Using local prompt override: %s", local_override)
            return local_override

        relative_to_workflow = (self._workflow_root / prompt).resolve()
        if relative_to_workflow.exists():
            return relative_to_workflow
        relative_to_repo = (self._repo_dir / prompt).resolve()
        if relative_to_repo.exists():
            return relative_to_repo
        raise FileNotFoundError(f"Prompt file not found for '{prompt}'")

    def _load_state_from_dict(self, state_dict: dict, workflow: Workflow) -> RunState:
        """Load RunState from a dictionary, reconstructing StepRuntime objects."""
        steps_data = state_dict.get("steps", {})
        steps = {}
        for step_id in workflow.steps:
            if step_id in steps_data:
                step_data = steps_data[step_id]
                steps[step_id] = StepRuntime(
                    status=StepStatus[step_data["status"]],
                    attempts=step_data["attempts"],
                    report_path=Path(step_data["report_path"]) if step_data.get("report_path") else None,
                    started_at=step_data.get("started_at"),
                    ended_at=step_data.get("ended_at"),
                    last_error=step_data.get("last_error"),
                    artifacts=step_data.get("artifacts", []),
                    metrics=step_data.get("metrics", {}),
                    logs=step_data.get("logs", []),
                    manual_input_path=Path(step_data["manual_input_path"]) if step_data.get("manual_input_path") else None,
                )
            else:
                steps[step_id] = StepRuntime()

        return RunState(
            run_id=state_dict["run_id"],
            workflow_name=state_dict["workflow_name"],
            repo_dir=Path(state_dict["repo_dir"]),
            reports_dir=Path(state_dict["reports_dir"]),
            manual_inputs_dir=Path(state_dict["manual_inputs_dir"]),
            created_at=state_dict.get("created_at", utc_now()),
            steps=steps,
        )

    def _reset_steps_from(self, start_step: str, workflow: Workflow) -> None:
        """Reset the specified step and all steps that depend on it (transitively)."""
        if start_step not in workflow.steps:
            raise ValueError(f"Step '{start_step}' not found in workflow")

        # Find all steps that need to be reset (start_step + all downstream dependencies)
        to_reset = {start_step}
        changed = True
        while changed:
            changed = False
            for step_id, step in workflow.steps.items():
                if step_id not in to_reset and any(dep in to_reset for dep in step.needs):
                    to_reset.add(step_id)
                    changed = True

        # Reset all identified steps to PENDING
        for step_id in to_reset:
            self._state.steps[step_id] = StepRuntime()
            self._log.info("Reset step=%s to PENDING", step_id)

    def _persist_state(self) -> None:
        self._state_persister.save(self._state)

    def _all_steps_finished(self) -> bool:
        return all(
            runtime.status in {StepStatus.COMPLETED, StepStatus.SKIPPED}
            for runtime in self._state.steps.values()
        )

    def _has_terminal_failure(self) -> bool:
        return any(
            runtime.status == StepStatus.FAILED and runtime.attempts >= self._max_attempts
            for runtime in self._state.steps.values()
        )

    def _cleanup_processes(self) -> None:
        for launch in self._active_processes.values():
            if launch.process.poll() is None:
                launch.process.terminate()
            launch.close_log()
        self._active_processes.clear()


def build_default_runner(
    repo_dir: Path,
    wrapper: Path,
    default_env: Optional[dict[str, str]] = None,
    default_args: Optional[list[str]] = None,
    logs_dir: Optional[Path] = None,
    workdir: Optional[Path] = None,
) -> StepRunner:
    template = ExecutionTemplate(
        "{python} {wrapper} --run-id {run_id} --step-id {step_id} --agent {agent} "
        "--prompt {prompt} --repo {repo} --report {report}"
    )
    return StepRunner(
        execution_template=template,
        repo_dir=repo_dir,
        logs_dir=logs_dir or (repo_dir / ".agents" / "logs"),
        workdir=workdir or repo_dir,
        template_context={"python": sys.executable, "wrapper": wrapper},
        default_env=default_env,
        default_args=default_args,
    )
