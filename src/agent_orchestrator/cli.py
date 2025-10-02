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
from .git_worktree import (
    GitWorktreeError,
    GitWorktreeManager,
    persist_worktree_outputs,
)


_LOG = logging.getLogger(__name__)


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
        logs_dir=logs_dir,
        workdir=workdir,
    )


def run_from_args(args: argparse.Namespace) -> None:
    repo_dir = Path(args.repo).expanduser().resolve()
    run_repo_dir = repo_dir
    repo_root_for_outputs = repo_dir
    worktree_manager: Optional[GitWorktreeManager] = None
    worktree_handle = None
    run_id_override: Optional[str] = None
    workflow_path = Path(args.workflow).expanduser().resolve()
    workflow_root = workflow_path.parent

    try:
        workflow = load_workflow(workflow_path)
    except WorkflowLoadError as exc:
        raise SystemExit(f"Workflow error: {exc}") from exc

    if args.git_worktree:
        if args.workdir:
            raise SystemExit("--workdir cannot be used together with --git-worktree")

        worktree_manager = GitWorktreeManager(repo_dir)
        repo_root_for_outputs = worktree_manager.repo_root

        worktree_root: Optional[Path] = None
        if args.git_worktree_root:
            candidate = Path(args.git_worktree_root).expanduser()
            if not candidate.is_absolute():
                candidate = (repo_root_for_outputs / candidate).resolve()
            else:
                candidate = candidate.resolve()
            worktree_root = candidate

        try:
            worktree_handle = worktree_manager.create(
                root=worktree_root,
                ref=args.git_worktree_ref,
                branch=args.git_worktree_branch,
            )
        except GitWorktreeError as exc:
            raise SystemExit(f"Git worktree error: {exc}") from exc

        run_repo_dir = worktree_handle.path
        run_id_override = worktree_handle.run_id

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
        state_file = run_repo_dir / state_file
    state_persister = RunStatePersister(state_file)

    base_env = parse_env(args.env)
    if args.issue_number:
        base_env["ISSUE_NUMBER"] = args.issue_number
    resolved_logs_dir = Path(args.logs_dir).expanduser().resolve() if args.logs_dir else None
    if args.git_worktree and not resolved_logs_dir:
        resolved_logs_dir = repo_root_for_outputs / ".agents" / "logs"

    resolved_workdir = Path(args.workdir).expanduser().resolve() if args.workdir else None
    orchestrator: Optional[Orchestrator] = None
    try:
        try:
            runner = build_runner(
                repo_dir=run_repo_dir,
                wrapper=args.wrapper,
                command_template=args.command_template,
                logs_dir=resolved_logs_dir,
                workdir=resolved_workdir,
                base_env=base_env,
                wrapper_args=args.wrapper_arg,
            )
        except (ValueError, FileNotFoundError) as exc:
            raise SystemExit(str(exc)) from exc

        orchestrator = Orchestrator(
            workflow=workflow,
            workflow_root=workflow_root,
            repo_dir=run_repo_dir,
            report_reader=report_reader,
            state_persister=state_persister,
            runner=runner,
            gate_evaluator=gate_evaluator,
            poll_interval=args.poll_interval,
            max_attempts=args.max_attempts,
            pause_for_human_input=args.pause_for_human_input,
            logger=logging.getLogger("agent_orchestrator"),
            run_id=run_id_override,
            start_at_step=args.start_at_step,
        )

        orchestrator.run()
    finally:
        if worktree_manager and worktree_handle:
            run_id = orchestrator.run_id if orchestrator else worktree_handle.run_id
            if args.git_worktree_keep:
                _LOG.info(
                    "Git worktree preserved at %s (branch %s)",
                    worktree_handle.path,
                    worktree_handle.branch,
                )
            else:
                try:
                    destination = persist_worktree_outputs(
                        worktree_handle.path,
                        worktree_handle.root_repo,
                        run_id,
                    )
                    _LOG.info("Copied worktree artifacts to %s", destination)
                except (OSError, shutil.Error) as exc:  # pragma: no cover - defensive
                    _LOG.warning("Failed to persist worktree artifacts: %s", exc)

                try:
                    worktree_manager.remove(worktree_handle)
                except GitWorktreeError as exc:
                    raise SystemExit(f"Failed to remove git worktree: {exc}") from exc


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
    run_parser.add_argument(
        "--issue-number",
        help="GitHub issue number to fetch and process (automatically sets ISSUE_NUMBER env var)",
    )
    run_parser.add_argument(
        "--start-at-step",
        help="Resume a previous run starting at the specified step (resets that step and all downstream steps)",
    )

    worktree_group = run_parser.add_argument_group("git worktree automation")
    worktree_group.add_argument(
        "--git-worktree",
        action="store_true",
        help="Create an isolated git worktree for this run",
    )
    worktree_group.add_argument(
        "--git-worktree-ref",
        help="Git ref to base the worktree on (default: HEAD)",
    )
    worktree_group.add_argument(
        "--git-worktree-branch",
        help="Branch name to create for the worktree (default: agents/run-<id>)",
    )
    worktree_group.add_argument(
        "--git-worktree-root",
        help="Directory to place worktrees (default: <repo>/.agents/worktrees)",
    )
    worktree_group.add_argument(
        "--git-worktree-keep",
        action="store_true",
        help="Keep the worktree after the workflow finishes",
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
