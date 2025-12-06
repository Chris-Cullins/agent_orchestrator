#!/usr/bin/env python3
"""
Custom wrapper for the Claude CLI.
This adapts the orchestrator's expected interface to the real claude command.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from agent_orchestrator.memory import MemoryManager
from agent_orchestrator.time_utils import utc_now
from agent_orchestrator.run_report_format import (
    RUN_REPORT_END,
    RUN_REPORT_START,
    PlaceholderContentError,
    build_run_report_instructions,
    build_memory_update_instructions,
    normalize_run_report_payload,
)
from agent_orchestrator.daily_stats import calculate_cost, DailyStatsTracker


def parse_args(argv: Optional[list[str]] = None) -> Tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Wrapper that adapts orchestrator interface to Claude CLI."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--claude-bin",
        default=os.environ.get("CLAUDE_CLI_BIN", "claude"),
        help="Path to claude binary (default: claude or CLAUDE_CLI_BIN env)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3600.0,  # 1 hour default
        help="Maximum seconds to wait for claude to finish",
    )
    parser.add_argument(
        "--working-dir",
        default=None,
        help="Override working directory for claude (defaults to repo)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Claude model to use (default: opus, can be overridden by STEP_MODEL env var)",
    )

    return parser.parse_known_args(argv)


def get_model(args: argparse.Namespace) -> str:
    """Determine which model to use with priority: STEP_MODEL env > --model arg > default."""
    # Priority 1: STEP_MODEL environment variable (set by orchestrator from workflow)
    step_model = os.environ.get("STEP_MODEL")
    if step_model:
        return step_model
    # Priority 2: --model command line argument
    if args.model:
        return args.model
    # Priority 3: Default
    return "opus"


def build_claude_command(
    args: argparse.Namespace,
    forwarded: list[str],
    started_at: str,
    model: str,
) -> tuple[list[str], str]:
    """Build the claude command and create the prompt content."""

    # Read the prompt file
    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {args.prompt}")

    with open(prompt_path, 'r', encoding='utf-8') as f:
        prompt_content = f.read()

    # Replace {run_id} placeholder with actual run_id
    prompt_content = prompt_content.replace("{run_id}", args.run_id)

    # Read repository memories
    repo_path = Path(args.repo)
    memory_manager = MemoryManager(repo_dir=repo_path)
    memory_context = memory_manager.read_memories(repo_path)
    memory_section = memory_context.to_prompt_section()

    # Enhance the prompt with context about the task
    enhanced_prompt = f"""You are an AI agent named "{args.agent}" working on a software development task.

Repository: {args.repo}
Run ID: {args.run_id}
Step ID: {args.step_id}

{memory_section}

Your task instructions:
{prompt_content}

{build_run_report_instructions(args.run_id, args.step_id, args.agent, started_at)}

{build_memory_update_instructions()}

Please proceed with the task and ensure you include the run report at the end.
"""

    # Build the command - Claude uses -p for print mode (non-interactive)
    command = [
        args.claude_bin,
        "--print",  # Non-interactive output mode
        "--model", model,  # Specify model (resolved from env/arg/default)
        "--dangerously-skip-permissions",  # Skip permission checks for automation
        "--add-dir", args.repo,  # Allow access to repository directory
    ]
    
    # Add any forwarded arguments
    if forwarded:
        command.extend(forwarded)
    
    return command, enhanced_prompt


def extract_run_report(text: str) -> Optional[Dict[str, Any]]:
    """Extract run report from Claude output."""
    start = text.rfind(RUN_REPORT_START)
    end = text.rfind(RUN_REPORT_END)
    if start == -1 or end == -1 or end <= start:
        return None
    payload = text[start + len(RUN_REPORT_START) : end].strip()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def extract_token_usage(stdout: str, stderr: str) -> Dict[str, int]:
    """
    Extract token usage from Claude CLI output.

    Claude CLI may output token usage in various formats. This function
    attempts to parse common patterns.

    Returns dict with 'input_tokens' and 'output_tokens' keys.
    """
    combined = stdout + "\n" + stderr
    result = {"input_tokens": 0, "output_tokens": 0}

    # Pattern 1: "Input tokens: 1234" / "Output tokens: 5678"
    input_match = re.search(r"[Ii]nput\s*tokens?[:\s]+(\d+)", combined)
    output_match = re.search(r"[Oo]utput\s*tokens?[:\s]+(\d+)", combined)

    if input_match:
        result["input_tokens"] = int(input_match.group(1))
    if output_match:
        result["output_tokens"] = int(output_match.group(1))

    # Pattern 2: "tokens: 1234 in, 5678 out" or "1234 input / 5678 output"
    if result["input_tokens"] == 0 and result["output_tokens"] == 0:
        pattern = r"(\d+)\s*(?:in|input)[^0-9]*(\d+)\s*(?:out|output)"
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            result["input_tokens"] = int(match.group(1))
            result["output_tokens"] = int(match.group(2))

    # Pattern 3: JSON format {"input_tokens": 1234, "output_tokens": 5678}
    if result["input_tokens"] == 0 and result["output_tokens"] == 0:
        json_pattern = r'\{[^}]*"input_tokens"\s*:\s*(\d+)[^}]*"output_tokens"\s*:\s*(\d+)[^}]*\}'
        match = re.search(json_pattern, combined)
        if match:
            result["input_tokens"] = int(match.group(1))
            result["output_tokens"] = int(match.group(2))

    # Pattern 4: Total tokens only - estimate split (60% input, 40% output)
    if result["input_tokens"] == 0 and result["output_tokens"] == 0:
        total_match = re.search(r"[Tt]otal\s*tokens?[:\s]+(\d+)", combined)
        if total_match:
            total = int(total_match.group(1))
            result["input_tokens"] = int(total * 0.6)
            result["output_tokens"] = int(total * 0.4)

    # Fallback: Estimate based on prompt/response length if no token info found
    # (rough estimate: ~4 chars per token for English text)
    if result["input_tokens"] == 0 and result["output_tokens"] == 0:
        # We'll estimate in the main function where we have access to the prompt
        pass

    return result


def estimate_tokens_from_text(text: str) -> int:
    """Rough estimate of token count from text length (~4 chars per token)."""
    return max(1, len(text) // 4)


def synthesize_report(
    run_id: str,
    step_id: str,
    agent: str,
    status: str,
    started_at: str,
    logs: list[str],
    duration_ms: int,
    artifacts: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Create a synthetic run report when Claude doesn't provide one."""
    return {
        "schema": "run_report@v0",
        "run_id": run_id,
        "step_id": step_id,
        "agent": agent,
        "status": status,
        "started_at": started_at,
        "ended_at": utc_now(),
        "artifacts": artifacts or [],
        "metrics": {
            "duration_ms": duration_ms,
        },
        "logs": logs,
        "next_suggested_steps": [],
    }


def main(argv: Optional[list[str]] = None) -> int:
    args, forwarded = parse_args(argv)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    started_at = utc_now()

    # Resolve which model to use (priority: STEP_MODEL env > --model arg > default)
    model = get_model(args)

    try:
        command, enhanced_prompt = build_claude_command(args, forwarded, started_at, model)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Set up environment
    env = os.environ.copy()
    env.update({
        "RUN_ID": args.run_id,
        "STEP_ID": args.step_id,
        "AGENT_ID": args.agent,
        "REPO_DIR": args.repo,
        "PROMPT_PATH": args.prompt,
        "REPORT_PATH": args.report,
    })

    cwd = args.working_dir or args.repo
    start_time = time.monotonic()

    print(f"Running Claude CLI for agent '{args.agent}' in {cwd}")
    print(f"Command: {' '.join(command[:-1])} '[PROMPT]'")
    print(f"Model: {model}")

    try:
        result = subprocess.run(
            command,
            input=enhanced_prompt,  # Pass prompt via stdin
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logs = [f"Claude CLI timed out after {args.timeout}s", str(exc)]
        report = synthesize_report(
            run_id=args.run_id,
            step_id=args.step_id,
            agent=args.agent,
            status="FAILED",
            started_at=started_at,
            logs=logs,
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )
        _emit_report(report, report_path)
        print("\\n".join(logs), file=sys.stderr)
        return 1

    duration_ms = int((time.monotonic() - start_time) * 1000)

    # Output the results
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)

    # Extract token usage from output
    token_usage = extract_token_usage(result.stdout or "", result.stderr or "")

    # If no tokens found in output, estimate from prompt/response length
    if token_usage["input_tokens"] == 0:
        token_usage["input_tokens"] = estimate_tokens_from_text(enhanced_prompt)
    if token_usage["output_tokens"] == 0 and result.stdout:
        token_usage["output_tokens"] = estimate_tokens_from_text(result.stdout)

    # Calculate cost
    step_cost = calculate_cost(
        token_usage["input_tokens"],
        token_usage["output_tokens"],
        model,
    )

    # Try to extract run report from output
    report_payload = extract_run_report(result.stdout or "")
    if report_payload is None:
        # No run report found, synthesize one
        status = "COMPLETED" if result.returncode == 0 else "FAILED"
        combined_logs = []
        if result.stdout:
            combined_logs.extend(line for line in result.stdout.splitlines() if line.strip())
        if result.stderr:
            combined_logs.extend(line for line in result.stderr.splitlines() if line.strip())
        
        # Try to detect artifacts by looking for created files
        artifacts = []
        repo_path = Path(args.repo)
        if repo_path.exists():
            # Look for common artifact patterns
            for pattern in ["PLAN.md", "backlog/*.md", ".agents/**/*.json", "CHANGELOG.md"]:
                for file_path in repo_path.glob(pattern):
                    if file_path.is_file():
                        artifacts.append(str(file_path.relative_to(repo_path)))
        
        report_payload = synthesize_report(
            run_id=args.run_id,
            step_id=args.step_id,
            agent=args.agent,
            status=status,
            started_at=started_at,
            logs=combined_logs[-20:] if combined_logs else [f"Agent {args.agent} execution completed"],
            duration_ms=duration_ms,
            artifacts=artifacts,
        )
    else:
        # Ensure required fields are present
        report_payload.setdefault("schema", "run_report@v0")
        report_payload.setdefault("run_id", args.run_id)
        report_payload.setdefault("step_id", args.step_id)
        report_payload.setdefault("agent", args.agent)
        report_payload.setdefault("started_at", started_at)
        report_payload.setdefault("ended_at", utc_now())
        report_payload.setdefault("artifacts", [])
        report_payload.setdefault("metrics", {})
        report_payload.setdefault("logs", [])
        report_payload.setdefault("next_suggested_steps", [])

    metrics = report_payload.setdefault("metrics", {})
    metrics.setdefault("duration_ms", duration_ms)
    # Add token and cost metrics
    metrics["input_tokens"] = token_usage["input_tokens"]
    metrics["output_tokens"] = token_usage["output_tokens"]
    metrics["total_tokens"] = token_usage["input_tokens"] + token_usage["output_tokens"]
    metrics["cost_usd"] = round(step_cost, 6)
    metrics["model"] = model
    report_payload["status"] = str(report_payload.get("status", "COMPLETED")).upper()

    # Record to daily stats tracker
    try:
        repo_path = Path(args.repo)
        tracker = DailyStatsTracker(repo_path)
        tracker.record_step(
            run_id=args.run_id,
            step_id=args.step_id,
            agent=args.agent,
            model=model,
            input_tokens=token_usage["input_tokens"],
            output_tokens=token_usage["output_tokens"],
            duration_ms=duration_ms,
            status=report_payload["status"],
            workflow_name=os.environ.get("WORKFLOW_NAME", ""),
        )
        print(f"Cost: ${step_cost:.4f} ({token_usage['input_tokens']} in / {token_usage['output_tokens']} out tokens)")
    except Exception as e:
        # Don't fail the step if stats tracking fails
        print(f"Warning: Failed to record daily stats: {e}", file=sys.stderr)

    try:
        report_payload = normalize_run_report_payload(report_payload)
    except PlaceholderContentError as exc:
        error = (
            "Run report rejected because it still contains placeholder content. "
            f"{exc}"
        )
        print(error, file=sys.stderr)
        report_payload = synthesize_report(
            run_id=args.run_id,
            step_id=args.step_id,
            agent=args.agent,
            status="FAILED",
            started_at=started_at,
            logs=[
                error,
                "Update the artifacts and logs with concrete values before finishing the step.",
            ],
            duration_ms=duration_ms,
            artifacts=[],
        )
        report_payload = normalize_run_report_payload(report_payload)
        _emit_report(report_payload, report_path)
        return 1

    _emit_report(report_payload, report_path)
    return result.returncode


def _emit_report(report: Dict[str, Any], path: Path) -> None:
    """Emit the run report to both stdout and file."""
    print(f"\\n{RUN_REPORT_START}")
    print(json.dumps(report, indent=2))
    print(RUN_REPORT_END)
    
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
