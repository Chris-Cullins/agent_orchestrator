#!/usr/bin/env python3
"""
Wrapper for the Claude CLI that adapts the orchestrator interface.

This module bridges the orchestrator's step execution model to the Claude CLI,
handling:
- Prompt enhancement with context (memory, guidance, run report instructions)
- Token usage and cost extraction from CLI output
- Run report generation (extracting from output or synthesizing)
- Daily cost tracking via DailyStatsTracker

Usage:
    python claude_wrapper.py --run-id <id> --step-id <id> --agent <name> \\
        --prompt <file> --repo <path> --report <path>

Environment variables:
    STEP_MODEL: Override the model to use (highest priority)
    CLAUDE_CLI_BIN: Path to claude binary
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
from agent_orchestrator.guidance import GuidanceManager
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


# Status normalization mapping: prompts use "success"/"failed" but orchestrator expects "COMPLETED"/"FAILED"
_STATUS_ALIASES = {
    "SUCCESS": "COMPLETED",
    "OK": "COMPLETED",
    "DONE": "COMPLETED",
    "PASSED": "COMPLETED",
    "FAIL": "FAILED",
    "ERROR": "FAILED",
}


def normalize_status(status: str) -> str:
    """
    Normalize agent-reported status to orchestrator-expected values.

    Agents may report status as 'success' or 'failed' (per prompts),
    but the orchestrator expects 'COMPLETED' or 'FAILED'.

    Args:
        status: Status string from agent output.

    Returns:
        Normalized status ("COMPLETED", "FAILED", or original uppercase).
    """
    upper = str(status).upper()
    return _STATUS_ALIASES.get(upper, upper)


def parse_args(argv: Optional[list[str]] = None) -> Tuple[argparse.Namespace, list[str]]:
    """
    Parse command-line arguments for the wrapper.

    Args:
        argv: Command-line arguments. Defaults to sys.argv.

    Returns:
        Tuple of (parsed args, forwarded args for Claude CLI).
    """
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
    """
    Determine which model to use with priority ordering.

    Priority: STEP_MODEL env > --model arg > default ("opus").

    Args:
        args: Parsed command-line arguments.

    Returns:
        Model name to use for Claude CLI.
    """
    step_model = os.environ.get("STEP_MODEL")
    if step_model:
        return step_model
    if args.model:
        return args.model
    return "opus"


def build_claude_command(
    args: argparse.Namespace,
    forwarded: list[str],
    started_at: str,
    model: str,
) -> tuple[list[str], str]:
    """
    Build the claude CLI command and enhanced prompt content.

    Reads the prompt file, enhances it with memory and guidance context,
    and constructs the command-line arguments for Claude CLI.

    Args:
        args: Parsed command-line arguments.
        forwarded: Additional arguments to pass to Claude CLI.
        started_at: ISO 8601 timestamp for the run report.
        model: Model name to use.

    Returns:
        Tuple of (command list, enhanced prompt string).

    Raises:
        FileNotFoundError: If prompt file does not exist.
    """

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

    # Read architectural guidance (if present)
    guidance_manager = GuidanceManager(repo_dir=repo_path)
    guidance_context = guidance_manager.read_all_guidance()
    guidance_section = guidance_context.to_prompt_section()

    # Enhance the prompt with context about the task
    enhanced_prompt = f"""You are an AI agent named "{args.agent}" working on a software development task.

Repository: {args.repo}
Run ID: {args.run_id}
Step ID: {args.step_id}

{guidance_section}

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
        "--output-format", "stream-json",  # Get JSON output for token parsing
        "--verbose",  # Required for stream-json to include token/cost data
    ]

    # Add any forwarded arguments
    if forwarded:
        command.extend(forwarded)

    return command, enhanced_prompt


def extract_run_report(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract run report JSON from Claude output.

    Args:
        text: Full output text from Claude CLI.

    Returns:
        Parsed run report dictionary, or None if not found.
    """
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


def extract_stream_json_result(stdout: str) -> Optional[Dict[str, Any]]:
    """
    Extract the result object from Claude CLI stream-json verbose output.

    When running with --output-format stream-json --verbose, Claude CLI outputs
    JSONL with a final "result" line containing actual token counts and cost:

    {"type":"result","total_cost_usd":0.123,"usage":{"input_tokens":100,...}}

    Returns the parsed result dict or None if not found.
    """
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if data.get("type") == "result":
                return data
        except json.JSONDecodeError:
            continue
    return None


def extract_token_usage(stdout: str, stderr: str) -> Dict[str, Any]:
    """
    Extract token usage from Claude CLI output.

    First tries to parse stream-json verbose output for accurate data.
    Falls back to pattern matching for legacy output formats.

    Returns dict with 'input_tokens', 'output_tokens', and optionally
    'cache_creation_input_tokens', 'cache_read_input_tokens', 'cost_usd'.
    """
    result: Dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cost_usd": None,
    }

    # Try to get accurate data from stream-json verbose output
    stream_result = extract_stream_json_result(stdout)
    if stream_result:
        usage = stream_result.get("usage", {})
        result["input_tokens"] = usage.get("input_tokens", 0)
        result["output_tokens"] = usage.get("output_tokens", 0)
        result["cache_creation_input_tokens"] = usage.get("cache_creation_input_tokens", 0)
        result["cache_read_input_tokens"] = usage.get("cache_read_input_tokens", 0)
        # Claude CLI provides pre-calculated cost
        if "total_cost_usd" in stream_result:
            result["cost_usd"] = stream_result["total_cost_usd"]
        return result

    # Fallback: pattern matching for legacy/text output
    combined = stdout + "\n" + stderr

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
    """
    Create a synthetic run report when Claude doesn't provide one.

    Used as a fallback when the agent output doesn't contain a valid
    run report in the expected format.

    Args:
        run_id: Workflow run identifier.
        step_id: Step identifier.
        agent: Agent name.
        status: Completion status ("COMPLETED" or "FAILED").
        started_at: ISO 8601 start timestamp.
        logs: Log messages to include.
        duration_ms: Execution duration in milliseconds.
        artifacts: Optional list of artifact paths.

    Returns:
        Complete run report dictionary.
    """
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
    """
    Main entry point for the Claude CLI wrapper.

    Executes the Claude CLI with an enhanced prompt, extracts or synthesizes
    a run report, records cost metrics, and writes the report to disk.

    Args:
        argv: Command-line arguments. Defaults to sys.argv.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
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

    # Extract token usage from output (includes actual cost if available)
    token_usage = extract_token_usage(result.stdout or "", result.stderr or "")

    # If no tokens found in output, estimate from prompt/response length
    if token_usage["input_tokens"] == 0:
        token_usage["input_tokens"] = estimate_tokens_from_text(enhanced_prompt)
    if token_usage["output_tokens"] == 0 and result.stdout:
        token_usage["output_tokens"] = estimate_tokens_from_text(result.stdout)

    # Use actual cost from Claude CLI if available, otherwise calculate
    if token_usage.get("cost_usd") is not None:
        step_cost = token_usage["cost_usd"]
    else:
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
    metrics["cache_creation_input_tokens"] = token_usage.get("cache_creation_input_tokens", 0)
    metrics["cache_read_input_tokens"] = token_usage.get("cache_read_input_tokens", 0)
    total_tokens = (
        token_usage["input_tokens"]
        + token_usage["output_tokens"]
        + token_usage.get("cache_creation_input_tokens", 0)
        + token_usage.get("cache_read_input_tokens", 0)
    )
    metrics["total_tokens"] = total_tokens
    metrics["cost_usd"] = round(step_cost, 6)
    metrics["cost_source"] = "claude_cli" if token_usage.get("cost_usd") is not None else "estimated"
    metrics["model"] = model
    report_payload["status"] = normalize_status(report_payload.get("status", "COMPLETED"))

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
            actual_cost_usd=token_usage.get("cost_usd"),
            cache_creation_input_tokens=token_usage.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=token_usage.get("cache_read_input_tokens", 0),
        )
        cost_source = "actual" if token_usage.get("cost_usd") is not None else "estimated"
        cache_info = ""
        if token_usage.get("cache_creation_input_tokens", 0) or token_usage.get("cache_read_input_tokens", 0):
            cache_info = f", cache: {token_usage.get('cache_creation_input_tokens', 0)} created / {token_usage.get('cache_read_input_tokens', 0)} read"
        print(f"Cost: ${step_cost:.4f} ({cost_source}) - tokens: {token_usage['input_tokens']} in / {token_usage['output_tokens']} out{cache_info}")
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
