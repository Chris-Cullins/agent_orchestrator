from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, IO, List, Optional, Sequence

from .models import Step


class ExecutionTemplate:
    """Build a subprocess command from a format string."""

    def __init__(self, template: str):
        self.template = template

    def build(self, context: Dict[str, object]) -> List[str]:
        rendered = self.template.format(**{k: str(v) for k, v in context.items()})
        return shlex.split(rendered)


@dataclass
class StepLaunch:
    step_id: str
    attempt: int
    process: subprocess.Popen
    report_path: Path
    log_path: Path
    log_handle: IO[str]

    def close_log(self) -> None:
        if not self.log_handle.closed:
            self.log_handle.close()


class StepRunner:
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
