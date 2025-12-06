"""Agent subprocess launcher for executing workflow steps.

This module handles the launching of agent processes as subprocesses,
managing their environment, logging, and lifecycle. It provides:
    - ExecutionTemplate: Command-line templating for agent invocation
    - StepLaunch: Handle to a running agent subprocess
    - StepRunner: Factory for launching agent steps with proper environment

Example:
    >>> from agent_orchestrator.runner import StepRunner, ExecutionTemplate
    >>> template = ExecutionTemplate("{python} {wrapper} --step {step_id}")
    >>> runner = StepRunner(template, repo_dir=Path("/repo"), logs_dir=Path("/logs"))
    >>> launch = runner.launch(step, run_id="abc123", report_path=Path("/report.json"))
"""
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, IO, List, Optional, Sequence

from .models import Step


class ExecutionTemplate:
    """Command-line template for building agent subprocess invocations.

    Templates use Python format string syntax with named placeholders.
    Common placeholders include: {python}, {wrapper}, {run_id}, {step_id},
    {agent}, {prompt}, {repo}, {report}.

    Attributes:
        template: Format string with named placeholders.
    """

    def __init__(self, template: str):
        """Initialize with a format string template.

        Args:
            template: Format string with named placeholders for substitution.
        """
        self.template = template

    def build(self, context: Dict[str, object]) -> List[str]:
        """Build a command argument list from the template and context.

        Args:
            context: Dictionary mapping placeholder names to values.

        Returns:
            List of command-line arguments, shell-split from the rendered template.
        """
        rendered = self.template.format(**{k: str(v) for k, v in context.items()})
        return shlex.split(rendered)


@dataclass
class StepLaunch:
    """Handle to a running agent subprocess.

    Encapsulates all information needed to monitor and collect results
    from a launched agent step.

    Attributes:
        step_id: Identifier of the launched step.
        attempt: Attempt number for this step execution.
        process: Popen handle to the running subprocess.
        report_path: Path where the agent will write its run report.
        log_path: Path to the subprocess output log file.
        log_handle: Open file handle for log output.
    """

    step_id: str
    attempt: int
    process: subprocess.Popen
    report_path: Path
    log_path: Path
    log_handle: IO[str]

    def close_log(self) -> None:
        """Close the log file handle if still open."""
        if not self.log_handle.closed:
            self.log_handle.close()


class StepRunner:
    """Factory for launching agent steps as subprocesses.

    StepRunner configures the environment and command line for agent
    invocations, then spawns them as background processes. Each launch
    returns a StepLaunch handle for monitoring and result collection.
    """
    def __init__(
        self,
        execution_template: ExecutionTemplate,
        repo_dir: Path,
        logs_dir: Path,
        workdir: Optional[Path] = None,
        template_context: Optional[Dict[str, object]] = None,
        default_env: Optional[Dict[str, str]] = None,
        default_args: Optional[Sequence[str]] = None,
    ) -> None:
        """Initialize the step runner with execution configuration.

        Args:
            execution_template: Template for building subprocess commands.
            repo_dir: Target repository directory for agent operations.
            logs_dir: Directory for subprocess log files.
            workdir: Working directory for subprocesses. Defaults to repo_dir.
            template_context: Base context values for template rendering.
            default_env: Environment variables to set for all steps.
            default_args: Additional CLI arguments appended to all commands.
        """
        self._template = execution_template
        self._repo_dir = repo_dir
        self._logs_dir = logs_dir
        self._workdir = workdir or repo_dir
        self._base_context = template_context or {}
        self._default_env = default_env or {}
        self._default_args = list(default_args) if default_args else []
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    def launch(
        self,
        step: Step,
        run_id: str,
        report_path: Path,
        prompt_path: Path,
        manual_input_path: Optional[Path] = None,
        extra_env: Optional[Dict[str, str]] = None,
        attempt: int = 1,
        artifacts_dir: Optional[Path] = None,
        logs_dir: Optional[Path] = None,
    ) -> StepLaunch:
        """Launch an agent subprocess for the given step.

        Builds the command line from the execution template, configures
        the subprocess environment with step-specific variables, and
        starts the agent process.

        Standard environment variables set for agents:
            - RUN_ID, STEP_ID, AGENT_ID: Identifiers
            - REPO_DIR, PROMPT_PATH, REPORT_PATH: Paths
            - ARTIFACTS_DIR: Directory for output artifacts
            - STEP_ATTEMPT: Current attempt number
            - STEP_MODEL: LLM model override (if specified)
            - ISSUE_MARKDOWN_*: GitHub issue paths (if ISSUE_NUMBER set)

        Args:
            step: Step definition to execute.
            run_id: Unique identifier for this orchestration run.
            report_path: Path where agent should write its run report.
            prompt_path: Resolved path to the prompt file.
            manual_input_path: Optional path for human-in-the-loop input.
            extra_env: Additional environment variables for this step.
            attempt: Attempt number (1-indexed).
            artifacts_dir: Directory for step artifacts.
            logs_dir: Override log directory for this launch.

        Returns:
            StepLaunch handle for monitoring the subprocess.
        """
        context = {
            **self._base_context,
            "repo": self._repo_dir,
            "step_id": step.id,
            "agent": step.agent,
            "prompt": prompt_path,
            "report": report_path,
            "run_id": run_id,
            "attempt": attempt,
            "manual_input": manual_input_path or "",
        }
        command = self._template.build(context)
        if self._default_args:
            command.extend(str(arg) for arg in self._default_args)

        effective_logs_dir = logs_dir or self._logs_dir
        effective_logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = effective_logs_dir / f"{run_id}__{step.id}__attempt{attempt}.log"
        log_file = log_path.open("w", encoding="utf-8")

        env = os.environ.copy()
        env.update(self._default_env)
        step_env = {
            "RUN_ID": run_id,
            "STEP_ID": step.id,
            "AGENT_ID": step.agent,
            "REPO_DIR": str(self._repo_dir),
            "PROMPT_PATH": str(prompt_path),
            "REPORT_PATH": str(report_path),
            "MANUAL_RESULT_PATH": str(manual_input_path) if manual_input_path else "",
            "STEP_ATTEMPT": str(attempt),
            "ARTIFACTS_DIR": str(artifacts_dir) if artifacts_dir else str(self._repo_dir / ".agents" / "artifacts"),
        }
        # Add model to environment if specified in the step
        if step.model:
            step_env["STEP_MODEL"] = step.model
        env.update(step_env)
        if extra_env:
            env.update(extra_env)

        issue_number = env.get("ISSUE_NUMBER")
        artifacts_dir_value = env.get("ARTIFACTS_DIR")
        if issue_number and artifacts_dir_value:
            issue_filename = f"gh_issue_{issue_number}.md"
            issue_path = Path(artifacts_dir_value) / issue_filename
            env.setdefault("ISSUE_MARKDOWN_FILENAME", issue_filename)
            env.setdefault("ISSUE_MARKDOWN_DIR", str(issue_path.parent))
            env.setdefault("ISSUE_MARKDOWN_PATH", str(issue_path))

        process = subprocess.Popen(
            command,
            cwd=str(self._workdir),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

        return StepLaunch(
            step_id=step.id,
            attempt=attempt,
            process=process,
            report_path=report_path,
            log_path=log_path,
            log_handle=log_file,
        )
