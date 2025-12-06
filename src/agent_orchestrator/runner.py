"""
Step execution and process management for agent workflows.

This module provides the infrastructure for launching agent processes,
managing their lifecycle, and collecting their outputs. It handles
command building, environment setup, and log file management.
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
    """
    Build subprocess commands from a parameterized format string.

    Uses Python string formatting to substitute context values into
    a command template, then splits into shell-safe arguments.

    Example:
        >>> template = ExecutionTemplate("{python} {script} --arg {value}")
        >>> template.build({"python": "python3", "script": "run.py", "value": "test"})
        ['python3', 'run.py', '--arg', 'test']

    Args:
        template: Format string with {placeholder} syntax for substitution.
    """

    def __init__(self, template: str):
        self.template = template

    def build(self, context: Dict[str, object]) -> List[str]:
        """
        Render the template with context values and split into arguments.

        Args:
            context: Dictionary of placeholder names to values.

        Returns:
            List of command arguments suitable for subprocess.
        """
        rendered = self.template.format(**{k: str(v) for k, v in context.items()})
        return shlex.split(rendered)


@dataclass
class StepLaunch:
    """
    Handle to a launched step process and its associated resources.

    Created by StepRunner.launch() and used by the orchestrator to
    track active processes and collect their outputs.

    Attributes:
        step_id: ID of the step that was launched.
        attempt: Attempt number (1 for first try, 2+ for retries).
        process: Popen handle for the running subprocess.
        report_path: Path where the agent should write its run report.
        log_path: Path to the log file capturing stdout/stderr.
        log_handle: Open file handle for the log file.
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
    """
    Launch and manage agent processes for workflow steps.

    Handles command building, environment setup, log file creation,
    and process spawning for agent execution.

    Args:
        execution_template: Template for building agent commands.
        repo_dir: Path to the target repository.
        logs_dir: Directory for agent log files.
        workdir: Working directory for processes. Defaults to repo_dir.
        template_context: Base context values for command templates.
        default_env: Environment variables injected into all processes.
        default_args: Arguments appended to all commands.
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
        """
        Launch an agent process for a workflow step.

        Builds the command from the template, sets up environment variables
        including STEP_MODEL if configured, creates a log file, and spawns
        the subprocess.

        Args:
            step: Step definition to execute.
            run_id: Current workflow run ID.
            report_path: Path where agent should write its run report.
            prompt_path: Resolved path to the prompt file.
            manual_input_path: Path for human-in-the-loop input file.
            extra_env: Additional environment variables for this step.
            attempt: Current attempt number (1-indexed).
            artifacts_dir: Directory for agent artifacts.
            logs_dir: Override directory for log files.

        Returns:
            StepLaunch handle for tracking the spawned process.
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
