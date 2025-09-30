from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Dict, Optional

from .gating import CompositeGateEvaluator, AlwaysOpenGateEvaluator, FileBackedGateEvaluator
from .orchestrator import Orchestrator, build_default_runner
from .reporting import RunReportReader
from .runner import ExecutionTemplate, StepRunner
from .state import RunStatePersister
from .workflow import WorkflowLoadError, load_workflow


def parse_env(env_pairs: Optional[list[str]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not env_pairs:
        return result
    for item in env_pairs:
        if "=" not in item:
            raise argparse.ArgumentTypeError(f"Invalid env override '{item}', expected KEY=VALUE")
        key, value = item.split("=", 1)
        result[key] = value
    return result


def build_runner(
    repo_dir: Path,
    wrapper: Optional[str],
    command_template: Optional[str],
    logs_dir: Optional[Path],
    workdir: Optional[Path],
    base_env: Dict[str, str],
    wrapper_args: list[str],
) -> StepRunner:
    logs_dir = logs_dir or (repo_dir / ".agents" / "logs")
    workdir = workdir or repo_dir

    if command_template:
        template = ExecutionTemplate(command_template)
        return StepRunner(
            execution_template=template,
            repo_dir=repo_dir,
            logs_dir=logs_dir,
            workdir=workdir,
            default_env=base_env,
            default_args=wrapper_args,
        )

    if not wrapper:
        raise ValueError("Either --command-template or --wrapper must be provided")

    wrapper_path = Path(wrapper).expanduser().resolve()
    if not wrapper_path.exists():
        raise FileNotFoundError(f"Wrapper script not found: {wrapper_path}")

    return build_default_runner(
        repo_dir=repo_dir,
        wrapper=wrapper_path,
        default_env=base_env,
        default_args=wrapper_args,
    )


def run_from_args(args: argparse.Namespace) -> None:
    repo_dir = Path(args.repo).expanduser().resolve()
    workflow_path = Path(args.workflow).expanduser().resolve()
    workflow_root = workflow_path.parent

    try:
        workflow = load_workflow(workflow_path)
    except WorkflowLoadError as exc:
        raise SystemExit(f"Workflow error: {exc}") from exc

    gate_evaluator = CompositeGateEvaluator(AlwaysOpenGateEvaluator())
    if args.gate_state_file:
        gate_evaluator = CompositeGateEvaluator(
            AlwaysOpenGateEvaluator(),
            FileBackedGateEvaluator(Path(args.gate_state_file).expanduser().resolve()),
        )

    try:
        report_reader = RunReportReader(Path(args.schema).expanduser().resolve()) if args.schema else RunReportReader()
    except Exception as exc:
        raise SystemExit(f"Failed to load run report schema: {exc}") from exc

    state_file = Path(args.state_file)
    if not state_file.is_absolute():
        state_file = repo_dir / state_file
    state_persister = RunStatePersister(state_file)

    base_env = parse_env(args.env)
    try:
        runner = build_runner(
            repo_dir=repo_dir,
            wrapper=args.wrapper,
            command_template=args.command_template,
            logs_dir=Path(args.logs_dir).expanduser().resolve() if args.logs_dir else None,
            workdir=Path(args.workdir).expanduser().resolve() if args.workdir else None,
            base_env=base_env,
            wrapper_args=args.wrapper_arg,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc

    orchestrator = Orchestrator(
        workflow=workflow,
        workflow_root=workflow_root,
        repo_dir=repo_dir,
        report_reader=report_reader,
        state_persister=state_persister,
        runner=runner,
        gate_evaluator=gate_evaluator,
        poll_interval=args.poll_interval,
        max_attempts=args.max_attempts,
        pause_for_human_input=args.pause_for_human_input,
        logger=logging.getLogger("agent_orchestrator"),
    )
    orchestrator.run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-orchestrator", description="File-driven SDLC agent orchestrator")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")

    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run a workflow")
    run_parser.add_argument("--repo", required=True, help="Path to the target repository")
    run_parser.add_argument("--workflow", required=True, help="Workflow YAML definition")
    run_parser.add_argument("--schema", help="Path to run report JSON schema for validation")
    run_parser.add_argument("--wrapper", help="Path to codex exec wrapper script")
    run_parser.add_argument(
        "--command-template",
        help="Custom command template for launching agents (format placeholders: {run_id}, {step_id}, {agent}, {prompt}, {repo}, {report})",
    )
    run_parser.add_argument("--poll-interval", type=float, default=1.0, help="Run report poll interval in seconds")
    run_parser.add_argument("--max-attempts", type=int, default=2, help="Max attempts per step before marking failed")
    run_parser.add_argument(
        "--gate-state-file",
        help="Optional JSON file that lists gate statuses, e.g. {'ci.tests: passed': true}",
    )
    run_parser.add_argument(
        "--state-file",
        default=".agents/run_state.json",
        help="Where to persist run state (default: .agents/run_state.json relative to repo)",
    )
    run_parser.add_argument(
        "--pause-for-human-input",
        action="store_true",
        help="Wait for manual_result.json before completing human-in-the-loop steps",
    )
    run_parser.add_argument("--logs-dir", help="Directory for agent stdout/stderr logs")
    run_parser.add_argument(
        "--wrapper-arg",
        action="append",
        default=[],
        help="Additional arguments appended to the wrapper command",
    )
    run_parser.add_argument("--workdir", help="Working directory for agent processes (default: repo path)")
    run_parser.add_argument(
        "--env",
        nargs="*",
        help="Environment variables to inject into agent runs (format KEY=VALUE)",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    if args.command == "run":
        run_from_args(args)
    else:  # pragma: no cover - defensive
        parser.error(f"Unknown command {args.command}")


if __name__ == "__main__":
    main()

