from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

RUN_REPORT_START = "<<<RUN_REPORT_JSON"
RUN_REPORT_END = "RUN_REPORT_JSON>>>"
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_timestamp() -> str:
    return datetime.utcnow().strftime(ISO_FORMAT)


def parse_args(argv: Optional[list[str]] = None) -> Tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Wrapper that invokes `codex exec` and ensures a run report is written."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--codex-bin",
        default=os.environ.get("CODEX_EXEC_BIN", "codex"),
        help="Path to codex binary (default: codex or CODEX_EXEC_BIN env)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Maximum seconds to wait for codex exec to finish",
    )
    parser.add_argument(
        "--working-dir",
        default=None,
        help="Override working directory for codex exec (defaults to repo)",
    )

    return parser.parse_known_args(argv)


def build_codex_command(args: argparse.Namespace, forwarded: list[str]) -> list[str]:
    command = [
        args.codex_bin,
        "exec",
        "--agent",
        args.agent,
        "--prompt",
        args.prompt,
        "--repo",
        args.repo,
    ]
    command.extend(forwarded)
    return command


def extract_run_report(text: str) -> Optional[Dict[str, Any]]:
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


def synthesize_report(
    run_id: str,
    step_id: str,
    agent: str,
    status: str,
    started_at: str,
    logs: list[str],
    duration_ms: int,
) -> Dict[str, Any]:
    return {
        "schema": "run_report@v0",
        "run_id": run_id,
        "step_id": step_id,
        "agent": agent,
        "status": status,
        "started_at": started_at,
        "ended_at": utc_timestamp(),
        "artifacts": [],
        "metrics": {
            "duration_ms": duration_ms,
        },
        "logs": logs,
        "next_suggested_steps": [],
    }


def ensure_report_fields(report: Dict[str, Any], run_id: str, step_id: str, agent: str, started_at: str) -> Dict[str, Any]:
    report.setdefault("schema", "run_report@v0")
    report.setdefault("run_id", run_id)
    report.setdefault("step_id", step_id)
    report.setdefault("agent", agent)
    report.setdefault("started_at", started_at)
    report.setdefault("ended_at", utc_timestamp())
    report["status"] = str(report.get("status", "COMPLETED")).upper()
    report.setdefault("artifacts", [])
    report.setdefault("metrics", {})
    report.setdefault("logs", [])
    report.setdefault("next_suggested_steps", [])
    return report


def main(argv: Optional[list[str]] = None) -> int:
    args, forwarded = parse_args(argv)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    command = build_codex_command(args, forwarded)
    env = os.environ.copy()
    env.setdefault("RUN_ID", args.run_id)
    env.setdefault("STEP_ID", args.step_id)
    env.setdefault("AGENT_ID", args.agent)
    env.setdefault("REPO_DIR", args.repo)
    env.setdefault("PROMPT_PATH", args.prompt)
    env.setdefault("REPORT_PATH", args.report)

    cwd = args.working_dir or args.repo

    started_at = utc_timestamp()
    start_time = time.monotonic()

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logs = [f"codex exec timed out after {args.timeout}s", str(exc)]
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
        print("\n".join(logs), file=sys.stderr)
        return 1

    duration_ms = int((time.monotonic() - start_time) * 1000)

    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)

    report_payload = extract_run_report(result.stdout or "")
    if report_payload is None:
        status = "COMPLETED" if result.returncode == 0 else "FAILED"
        combined_logs = []
        if result.stdout:
            combined_logs.extend(line for line in result.stdout.splitlines() if line.strip())
        if result.stderr:
            combined_logs.extend(line for line in result.stderr.splitlines() if line.strip())
        report_payload = synthesize_report(
            run_id=args.run_id,
            step_id=args.step_id,
            agent=args.agent,
            status=status,
            started_at=started_at,
            logs=combined_logs[-20:],  # keep last few lines
            duration_ms=duration_ms,
        )
    else:
        report_payload = ensure_report_fields(report_payload, args.run_id, args.step_id, args.agent, started_at)
        metrics = report_payload.setdefault("metrics", {})
        metrics.setdefault("duration_ms", duration_ms)

    _emit_report(report_payload, report_path)

    return result.returncode


def _emit_report(report: Dict[str, Any], path: Path) -> None:
    print(RUN_REPORT_START)
    print(json.dumps(report, indent=2))
    print(RUN_REPORT_END)
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
