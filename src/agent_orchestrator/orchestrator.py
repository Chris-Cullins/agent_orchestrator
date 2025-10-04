from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gating import GateEvaluator, AlwaysOpenGateEvaluator, CompositeGateEvaluator
from .models import RunState, Step, StepRuntime, StepStatus, Workflow, utc_now
from .notifications import (
    NotificationService,
    NullNotificationService,
    RunContext,
    StepNotification,
)
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
        max_iterations: int = 4,
        pause_for_human_input: bool = False,
        logger: Optional[logging.Logger] = None,
        run_id: Optional[str] = None,
        start_at_step: Optional[str] = None,
        notification_service: Optional[NotificationService] = None,
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
        self._max_iterations = max(1, max_iterations)
        self._pause_for_human = pause_for_human_input
        self._log = logger or logging.getLogger(__name__)
        self._notifications: NotificationService = notification_service or NullNotificationService()

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
        self._start_notifications()
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
            self._stop_notifications()

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

            # Initialize loop items if this step has a loop
            if step.loop and not self._initialize_loop_items(step, runtime):
                continue  # Loop items not ready yet

            # Check if loop is exhausted
            if step.loop and not self._should_continue_loop(step, runtime):
                runtime.status = StepStatus.COMPLETED
                runtime.loop_completed = True
                runtime.ended_at = utc_now()
                self._log.info(
                    "Loop completed for step=%s after %d iterations",
                    step_id,
                    runtime.loop_index,
                )
                continue

            report_path = self._reports_dir / f"{self._state.run_id}__{step.id}.json"
            manual_input_path = (
                self._manual_inputs_dir / f"{self._state.run_id}__{step.id}.json"
                if step.human_in_the_loop and self._pause_for_human
                else None
            )

            prompt_path = self._resolve_prompt_path(step.prompt)

            # Collect artifacts from dependency steps
            dep_artifacts_env = self._collect_dependency_artifacts(step)

            # Add loop context to environment
            loop_env = self._get_loop_context_env(step, runtime)
            dep_artifacts_env.update(loop_env)

            runtime.notified_failure = False
            runtime.notified_human_input = False
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
                    extra_env=dep_artifacts_env,
                )
            except Exception as exc:  # pragma: no cover
                runtime.status = StepStatus.FAILED
                runtime.last_error = str(exc)
                runtime.ended_at = utc_now()
                self._log.exception("failed to launch step=%s", step_id)
                continue

            log_msg = f"launched step=%s agent=%s attempt=%s"
            if step.loop:
                log_msg += f" loop_iteration={runtime.loop_index}/{len(runtime.loop_items)}"
            self._log.info(log_msg, step.id, step.agent, runtime.attempts)
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
                    self._notify_failure(step_id, runtime)
                    to_remove.append(step_id)
                    progressed = True
                    continue

                runtime.ended_at = report.ended_at
                runtime.artifacts = report.artifacts
                runtime.metrics = report.metrics
                runtime.logs = report.logs

                # Check for gate failure and handle loop-back
                step = self._workflow.steps[step_id]
                if report.gate_failure and step.loop_back_to:
                    if runtime.iteration_count < self._max_iterations:
                        self._log.info(
                            "gate failure detected step=%s iteration=%s/%s, looping back to step=%s",
                            step_id,
                            runtime.iteration_count + 1,
                            self._max_iterations,
                            step.loop_back_to,
                        )
                        self._handle_loop_back(step_id, step.loop_back_to)
                        to_remove.append(step_id)
                        progressed = True
                        continue
                    else:
                        self._log.error(
                            "max iterations reached step=%s iterations=%s, marking as failed",
                            step_id,
                            runtime.iteration_count,
                        )
                        runtime.status = StepStatus.FAILED
                        runtime.last_error = f"Gate failure after {runtime.iteration_count} iterations - max iterations reached"
                        self._notify_failure(step_id, runtime)
                        to_remove.append(step_id)
                        progressed = True
                        continue

                if report.status == "COMPLETED":
                    # Check if this is a looping step that needs to continue
                    if step.loop and self._should_continue_loop(step, runtime):
                        # Advance to next loop iteration
                        runtime.loop_index += 1
                        runtime.status = StepStatus.PENDING
                        runtime.report_path = None
                        runtime.started_at = None
                        runtime.ended_at = None
                        runtime.manual_input_path = None
                        self._log.info(
                            "Loop iteration completed for step=%s, advancing to iteration %d/%d",
                            step_id,
                            runtime.loop_index,
                            len(runtime.loop_items),
                        )
                    elif runtime.manual_input_path and self._pause_for_human:
                        runtime.status = StepStatus.WAITING_ON_HUMAN
                        runtime.notified_human_input = False
                        self._log.info("awaiting human input step=%s", step_id)
                        self._notify_human_input(step_id, runtime)
                    else:
                        runtime.status = StepStatus.COMPLETED
                        runtime.notified_human_input = False
                        if step.loop:
                            runtime.loop_completed = True
                            self._log.info(
                                "Loop fully completed for step=%s after %d iterations",
                                step_id,
                                runtime.loop_index,
                            )
                        else:
                            self._log.info("step completed step=%s", step_id)
                else:
                    runtime.status = StepStatus.FAILED
                    runtime.last_error = ", ".join(report.logs[-3:]) if report.logs else "Agent reported failure"
                    self._log.warning("step failed step=%s logs=%s", step_id, runtime.last_error)
                    self._notify_failure(step_id, runtime)

                to_remove.append(step_id)
                progressed = True
            elif process_finished:
                runtime.status = StepStatus.FAILED
                runtime.ended_at = utc_now()
                runtime.last_error = (
                    f"Agent process exited with code {launch.process.returncode} without writing a run report"
                )
                self._log.error("step failed without report step=%s", step_id)
                self._notify_failure(step_id, runtime)
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
                runtime.notified_failure = False
                runtime.notified_human_input = False
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
                runtime.notified_human_input = False
                progressed = True
                self._log.info("manual input received step=%s", step_id)
        return progressed

    def _dependencies_satisfied(self, step: Step) -> bool:
        if not all(
            self._state.steps[dep].status in {StepStatus.COMPLETED, StepStatus.SKIPPED}
            for dep in step.needs
        ):
            return False

        runtime = self._state.steps[step.id]
        if runtime.blocked_by_loop:
            target_runtime = self._state.steps.get(runtime.blocked_by_loop)
            if not target_runtime or target_runtime.status not in {
                StepStatus.COMPLETED,
                StepStatus.SKIPPED,
            }:
                return False
            runtime.blocked_by_loop = None
        return True

    def _gates_open(self, step: Step) -> bool:
        for gate in step.gates:
            if not self._gate_evaluator.evaluate(step, gate):
                self._log.info("gate blocked step=%s gate=%s", step.id, gate)
                return False
        return True

    def _collect_dependency_artifacts(self, step: Step) -> Dict[str, str]:
        """Collect artifacts from dependency steps and return as environment variables."""
        env: Dict[str, str] = {}
        issue_artifact: Optional[Path] = None
        for dep_id in step.needs:
            dep_runtime = self._state.steps.get(dep_id)
            if not dep_runtime or not dep_runtime.artifacts:
                continue

            # Add each artifact as DEP_<STEP_ID>_ARTIFACT_<INDEX>
            for idx, artifact in enumerate(dep_runtime.artifacts):
                # Convert artifact path to absolute path relative to repo
                artifact_path = Path(artifact)
                if not artifact_path.is_absolute():
                    artifact_path = (self._repo_dir / artifact_path).resolve()
                else:
                    artifact_path = artifact_path.resolve()

                env_key = f"DEP_{dep_id.upper()}_ARTIFACT_{idx}"
                env[env_key] = str(artifact_path)

                if (
                    issue_artifact is None
                    and artifact_path.name.startswith("gh_issue_")
                    and artifact_path.suffix == ".md"
                ):
                    issue_artifact = artifact_path

            # Also add a summary variable with all artifacts (comma-separated)
            if dep_runtime.artifacts:
                artifact_paths = [
                    str((self._repo_dir / Path(a)).resolve())
                    if not Path(a).is_absolute()
                    else str(Path(a).resolve())
                    for a in dep_runtime.artifacts
                ]
                env[f"DEP_{dep_id.upper()}_ARTIFACTS"] = ",".join(artifact_paths)

        if issue_artifact:
            env.setdefault("ISSUE_MARKDOWN_PATH", str(issue_artifact))
            env.setdefault("ISSUE_MARKDOWN_DIR", str(issue_artifact.parent))
            env.setdefault("ISSUE_MARKDOWN_FILENAME", issue_artifact.name)

        return env

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
                    iteration_count=step_data.get("iteration_count", 0),
                    report_path=Path(step_data["report_path"]) if step_data.get("report_path") else None,
                    started_at=step_data.get("started_at"),
                    ended_at=step_data.get("ended_at"),
                    last_error=step_data.get("last_error"),
                    artifacts=step_data.get("artifacts", []),
                    metrics=step_data.get("metrics", {}),
                    logs=step_data.get("logs", []),
                    manual_input_path=Path(step_data["manual_input_path"]) if step_data.get("manual_input_path") else None,
                    blocked_by_loop=step_data.get("blocked_by_loop"),
                    notified_failure=step_data.get("notified_failure", False),
                    notified_human_input=step_data.get("notified_human_input", False),
                    loop_index=step_data.get("loop_index", 0),
                    loop_items=step_data.get("loop_items"),
                    loop_completed=step_data.get("loop_completed", False),
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

    def _handle_loop_back(self, from_step: str, to_step: str) -> None:
        """Handle loop-back from one step to another by resetting target and downstream steps."""
        if to_step not in self._workflow.steps:
            self._log.error("Invalid loop_back_to target step=%s from step=%s", to_step, from_step)
            return

        # Increment iteration count for the step that triggered the loop-back
        from_runtime = self._state.steps[from_step]
        from_runtime.iteration_count += 1


        # Requeue the source step so it runs again after upstream steps rerun.
        from_runtime.status = StepStatus.PENDING
        from_runtime.report_path = None
        from_runtime.started_at = None
        from_runtime.ended_at = None
        from_runtime.last_error = None
        from_runtime.manual_input_path = None
        from_runtime.logs = []
        from_runtime.metrics = {}
        from_runtime.artifacts = []
        if from_step != to_step:
            from_runtime.blocked_by_loop = to_step
        else:
            from_runtime.blocked_by_loop = None
        self._log.info(
            "Requeued loop-back source step=%s iteration=%s",
            from_step,
            from_runtime.iteration_count,
        )

        # Find all steps between to_step and from_step (inclusive of to_step)
        # These are steps that need to be reset
        to_reset = {to_step}
        changed = True
        while changed:
            changed = False
            for step_id, step in self._workflow.steps.items():
                # Add steps that depend on steps we're resetting
                if step_id not in to_reset and any(dep in to_reset for dep in step.needs):
                    to_reset.add(step_id)
                    changed = True
                    # Stop if we reach the step that triggered the loop-back
                    if step_id == from_step:
                        break

        # Reset all identified steps to PENDING (except from_step)
        for step_id in to_reset:
            if step_id != from_step:
                # Preserve iteration count from original runtime if it was part of the loop
                old_iteration = self._state.steps[step_id].iteration_count
                self._state.steps[step_id] = StepRuntime()
                # If this is the target step, increment its iteration count
                if step_id == to_step:
                    self._state.steps[step_id].iteration_count = old_iteration
                self._log.info("Reset step=%s to PENDING for loop-back", step_id)

    def _initialize_loop_items(self, step: Step, runtime: StepRuntime) -> bool:
        """Initialize loop items for a step if it has a loop configuration.
        Returns True if initialization was successful, False if items are not yet available."""
        if not step.loop:
            return True  # No loop, nothing to initialize

        if runtime.loop_items is not None:
            return True  # Already initialized

        # Get items from configuration
        if step.loop.items is not None:
            runtime.loop_items = step.loop.items
            runtime.loop_index = 0
            self._log.info("Initialized loop for step=%s with %d items", step.id, len(runtime.loop_items))
            return True

        if step.loop.items_from_step:
            # Get items from a previous step's artifacts
            dep_step_id = step.loop.items_from_step
            dep_runtime = self._state.steps.get(dep_step_id)
            if not dep_runtime or dep_runtime.status != StepStatus.COMPLETED:
                return False  # Dependency not ready yet

            # Load items from the first artifact of the dependency step
            if not dep_runtime.artifacts:
                self._log.error(
                    "Loop source step=%s has no artifacts for step=%s",
                    dep_step_id,
                    step.id,
                )
                return False

            artifact_path = Path(dep_runtime.artifacts[0])
            if not artifact_path.is_absolute():
                artifact_path = self._repo_dir / artifact_path

            try:
                with artifact_path.open("r") as f:
                    data = json.load(f)
                    # Expect the artifact to contain a list or a dict with an "items" key
                    if isinstance(data, list):
                        runtime.loop_items = data
                    elif isinstance(data, dict) and "items" in data:
                        runtime.loop_items = data["items"]
                    else:
                        self._log.error(
                            "Loop artifact from step=%s has invalid format for step=%s",
                            dep_step_id,
                            step.id,
                        )
                        return False

                runtime.loop_index = 0
                self._log.info(
                    "Initialized loop for step=%s with %d items from step=%s",
                    step.id,
                    len(runtime.loop_items),
                    dep_step_id,
                )
                return True
            except (json.JSONDecodeError, IOError) as e:
                self._log.error(
                    "Failed to load loop items from step=%s for step=%s: %s",
                    dep_step_id,
                    step.id,
                    e,
                )
                return False

        if step.loop.items_from_artifact:
            # Load items from a specific artifact file
            artifact_path = Path(step.loop.items_from_artifact)
            if not artifact_path.is_absolute():
                artifact_path = self._repo_dir / artifact_path

            if not artifact_path.exists():
                return False  # Artifact not ready yet

            try:
                with artifact_path.open("r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        runtime.loop_items = data
                    elif isinstance(data, dict) and "items" in data:
                        runtime.loop_items = data["items"]
                    else:
                        self._log.error(
                            "Loop artifact has invalid format for step=%s", step.id
                        )
                        return False

                runtime.loop_index = 0
                self._log.info(
                    "Initialized loop for step=%s with %d items from artifact",
                    step.id,
                    len(runtime.loop_items),
                )
                return True
            except (json.JSONDecodeError, IOError) as e:
                self._log.error("Failed to load loop items for step=%s: %s", step.id, e)
                return False

        return False

    def _should_continue_loop(self, step: Step, runtime: StepRuntime) -> bool:
        """Check if a loop should continue to the next iteration."""
        if not step.loop or not runtime.loop_items:
            return False

        if runtime.loop_completed:
            return False

        # Check if we've processed all items
        if runtime.loop_index >= len(runtime.loop_items):
            return False

        # Check max_iterations if specified
        if step.loop.max_iterations is not None:
            if runtime.loop_index >= step.loop.max_iterations:
                return False

        # TODO: Implement until_condition evaluation when needed

        return True

    def _get_loop_context_env(self, step: Step, runtime: StepRuntime) -> Dict[str, str]:
        """Get environment variables for the current loop iteration."""
        if not step.loop or not runtime.loop_items:
            return {}

        if runtime.loop_index >= len(runtime.loop_items):
            return {}

        current_item = runtime.loop_items[runtime.loop_index]
        env = {
            f"LOOP_{step.loop.index_var.upper()}": str(runtime.loop_index),
            f"LOOP_{step.loop.item_var.upper()}": json.dumps(current_item),
        }

        return env

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

    def _start_notifications(self) -> None:
        try:
            context = RunContext(
                run_id=self._state.run_id,
                workflow_name=self._workflow.name,
                repo_dir=self._repo_dir,
            )
            self._notifications.start(context)
        except Exception:  # pragma: no cover - defensive logging
            self._log.exception(
                "failed to start notification service run_id=%s", self._state.run_id
            )

    def _stop_notifications(self) -> None:
        try:
            self._notifications.stop()
        except Exception:  # pragma: no cover - defensive logging
            self._log.exception(
                "failed to stop notification service run_id=%s", self._state.run_id
            )

    def _build_step_notification(
        self,
        step_id: str,
        runtime: StepRuntime,
        trigger: str,
    ) -> StepNotification:
        return StepNotification(
            run_id=self._state.run_id,
            workflow_name=self._workflow.name,
            step_id=step_id,
            attempt=runtime.attempts,
            status=runtime.status,
            trigger=trigger,
            manual_input_path=runtime.manual_input_path,
            report_path=runtime.report_path,
            logs=list(runtime.logs),
            last_error=runtime.last_error,
        )

    def _notify_failure(self, step_id: str, runtime: StepRuntime) -> None:
        if runtime.notified_failure or runtime.status != StepStatus.FAILED:
            return
        notification = self._build_step_notification(step_id, runtime, trigger="failure")
        try:
            self._notifications.notify_failure(notification)
            runtime.notified_failure = True
        except Exception:  # pragma: no cover - defensive logging
            self._log.exception("failed to dispatch failure notification step=%s", step_id)

    def _notify_human_input(self, step_id: str, runtime: StepRuntime) -> None:
        if runtime.notified_human_input or runtime.status != StepStatus.WAITING_ON_HUMAN:
            return
        notification = self._build_step_notification(step_id, runtime, trigger="human_input")
        try:
            self._notifications.notify_human_input(notification)
            runtime.notified_human_input = True
        except Exception:  # pragma: no cover - defensive logging
            self._log.exception("failed to dispatch human-input notification step=%s", step_id)


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
