"""FastAPI web server for the agent orchestrator dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..daily_stats import DailyStats, DailyStatsTracker
from ..workflow import load_workflow, WorkflowLoadError

_LOG = logging.getLogger(__name__)


class StartRunRequest(BaseModel):
    """Request model for starting a new workflow run."""
    workflow: str  # Path to workflow YAML (relative to orchestrator src)
    wrapper: str  # Path to wrapper script (relative to orchestrator src)
    repo: Optional[str] = None  # Target repo (defaults to current)
    issue_number: Optional[str] = None
    git_worktree: bool = False
    git_worktree_branch: Optional[str] = None
    daily_cost_limit: Optional[float] = None
    cost_limit_action: str = "warn"
    max_attempts: int = 2
    max_iterations: int = 4
    env_vars: Optional[Dict[str, str]] = None
    start_at_step: Optional[str] = None


class ActiveRun:
    """Tracks an active run launched from the web UI."""
    def __init__(self, run_id: str, process: subprocess.Popen, log_path: Path):
        self.run_id = run_id
        self.process = process
        self.log_path = log_path
        self.started_at = datetime.now(timezone.utc).isoformat()


# Track active runs launched from web UI
_active_runs: Dict[str, ActiveRun] = {}


def create_app(repo_dir: Path) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Agent Orchestrator Dashboard",
        description="Monitor agent runs and cost analytics",
        version="1.0.0",
    )

    # Store repo_dir in app state
    app.state.repo_dir = repo_dir
    app.state.stats_tracker = DailyStatsTracker(repo_dir)

    # Setup templates and static files
    web_dir = Path(__file__).parent
    templates = Jinja2Templates(directory=web_dir / "templates")
    app.mount("/static", StaticFiles(directory=web_dir / "static"), name="static")

    # Register template filters
    templates.env.filters["format_cost"] = format_cost
    templates.env.filters["format_tokens"] = format_tokens
    templates.env.filters["format_duration"] = format_duration
    templates.env.filters["status_emoji"] = status_emoji
    templates.env.filters["status_class"] = status_class

    # Dashboard home page
    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Dashboard home page with today's stats and recent runs."""
        tracker: DailyStatsTracker = app.state.stats_tracker
        today_stats = tracker.get_daily_stats()

        # Get recent runs (last 10)
        recent_runs = get_recent_runs(today_stats)

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "stats": today_stats,
                "recent_runs": recent_runs,
                "page_title": "Dashboard",
            },
        )

    # Cost analytics page
    @app.get("/analytics", response_class=HTMLResponse)
    async def analytics(request: Request, days: int = 7):
        """Cost analytics page with historical data."""
        tracker: DailyStatsTracker = app.state.stats_tracker
        stats_list = get_stats_range(tracker, days)

        # Prepare chart data
        chart_data = prepare_chart_data(stats_list)

        # Get today's stats for model breakdown
        today_stats = tracker.get_daily_stats()

        # Get cost breakdown by step ID
        cost_by_step = get_cost_by_step(stats_list)

        return templates.TemplateResponse(
            "analytics.html",
            {
                "request": request,
                "stats_list": stats_list,
                "chart_data": json.dumps(chart_data),
                "today_stats": today_stats,
                "cost_by_step": cost_by_step,
                "selected_days": days,
                "page_title": "Cost Analytics",
            },
        )

    # Run explorer page
    @app.get("/runs", response_class=HTMLResponse)
    async def runs_list(request: Request, days: int = 7):
        """Run explorer - list of all runs."""
        tracker: DailyStatsTracker = app.state.stats_tracker
        all_runs = get_all_runs(tracker, days)

        return templates.TemplateResponse(
            "runs.html",
            {
                "request": request,
                "runs": all_runs,
                "selected_days": days,
                "page_title": "Run Explorer",
            },
        )

    # New run page - MUST be before /runs/{run_id} to avoid route conflict
    @app.get("/runs/new", response_class=HTMLResponse)
    async def new_run_page(request: Request):
        """Page for starting a new workflow run."""
        workflows = discover_workflows(app.state.repo_dir)
        wrappers = discover_wrappers(app.state.repo_dir)

        return templates.TemplateResponse(
            "new_run.html",
            {
                "request": request,
                "workflows": workflows,
                "wrappers": wrappers,
                "repo_dir": str(app.state.repo_dir),
                "page_title": "New Run",
            },
        )

    # Live run page - MUST be before /runs/{run_id} to avoid route conflict
    @app.get("/runs/{run_id}/live", response_class=HTMLResponse)
    async def live_run_page(request: Request, run_id: str):
        """Live view of a running workflow."""
        repo_dir: Path = app.state.repo_dir
        tracker: DailyStatsTracker = app.state.stats_tracker

        # Check if it's an active run
        is_active = run_id in _active_runs
        run_info = None
        steps = []

        if not is_active:
            # Try to get info from stats
            run_info = get_run_info(tracker, run_id)
            if run_info:
                steps = get_run_steps(repo_dir, run_id, tracker)

        return templates.TemplateResponse(
            "run_live.html",
            {
                "request": request,
                "run_id": run_id,
                "is_active": is_active,
                "run_info": run_info,
                "steps": steps,
                "page_title": f"Live: {run_id[:8]}",
            },
        )

    # Run detail page
    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_detail(request: Request, run_id: str):
        """Run detail page showing steps and metrics."""
        repo_dir: Path = app.state.repo_dir
        tracker: DailyStatsTracker = app.state.stats_tracker

        # Get run info from stats
        run_info = get_run_info(tracker, run_id)
        if not run_info:
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": f"Run {run_id} not found",
                    "page_title": "Error",
                },
                status_code=404,
            )

        # Get step details from run state if available
        steps = get_run_steps(repo_dir, run_id, tracker)

        return templates.TemplateResponse(
            "run_detail.html",
            {
                "request": request,
                "run_id": run_id,
                "run_info": run_info,
                "steps": steps,
                "page_title": f"Run {run_id[:8]}",
            },
        )

    # API endpoints for HTMX
    @app.get("/api/stats/today")
    async def api_today_stats():
        """Get today's stats as JSON."""
        tracker: DailyStatsTracker = app.state.stats_tracker
        return tracker.get_daily_stats().to_dict()

    @app.get("/api/stats/range")
    async def api_stats_range(days: int = 7):
        """Get stats for a date range."""
        tracker: DailyStatsTracker = app.state.stats_tracker
        stats_list = get_stats_range(tracker, days)
        return [s.to_dict() for s in stats_list]

    @app.get("/api/runs")
    async def api_runs(days: int = 7):
        """Get all runs for date range."""
        tracker: DailyStatsTracker = app.state.stats_tracker
        return get_all_runs(tracker, days)

    # ============================================================
    # New Run UI - Workflow Discovery and Execution
    # ============================================================

    @app.get("/api/workflows")
    async def api_list_workflows():
        """List available workflows with their metadata."""
        workflows = discover_workflows(app.state.repo_dir)
        return workflows

    @app.get("/api/wrappers")
    async def api_list_wrappers():
        """List available wrapper scripts."""
        wrappers = discover_wrappers(app.state.repo_dir)
        return wrappers

    @app.get("/api/workflow/{workflow_path:path}/steps")
    async def api_workflow_steps(workflow_path: str):
        """Get steps for a specific workflow (for resume step selection)."""
        orchestrator_src = Path(__file__).parent.parent
        full_path = orchestrator_src / workflow_path
        if not full_path.exists():
            return {"error": f"Workflow not found: {workflow_path}"}
        try:
            workflow = load_workflow(full_path)
            return {
                "name": workflow.name,
                "description": workflow.description,
                "steps": [
                    {
                        "id": step.id,
                        "agent": step.agent,
                        "needs": step.needs,
                        "human_in_the_loop": step.human_in_the_loop,
                    }
                    for step in workflow.steps.values()
                ]
            }
        except WorkflowLoadError as e:
            return {"error": str(e)}

    @app.post("/api/runs/start")
    async def api_start_run(request_body: StartRunRequest):
        """Start a new workflow run asynchronously."""
        repo_dir: Path = app.state.repo_dir
        orchestrator_src = Path(__file__).parent.parent

        # Build the command
        cmd = [
            sys.executable, "-m", "agent_orchestrator.cli", "run",
            "--repo", str(request_body.repo or repo_dir),
            "--workflow", str(orchestrator_src / request_body.workflow),
            "--wrapper", str(orchestrator_src / request_body.wrapper),
            "--max-attempts", str(request_body.max_attempts),
            "--max-iterations", str(request_body.max_iterations),
            "--cost-limit-action", request_body.cost_limit_action,
        ]

        if request_body.issue_number:
            cmd.extend(["--issue-number", request_body.issue_number])

        if request_body.git_worktree:
            cmd.append("--git-worktree")
            if request_body.git_worktree_branch:
                cmd.extend(["--git-worktree-branch", request_body.git_worktree_branch])

        if request_body.daily_cost_limit:
            cmd.extend(["--daily-cost-limit", str(request_body.daily_cost_limit)])

        if request_body.start_at_step:
            cmd.extend(["--start-at-step", request_body.start_at_step])

        if request_body.env_vars:
            for key, value in request_body.env_vars.items():
                cmd.extend(["--env", f"{key}={value}"])

        # Generate run ID for tracking
        run_id = uuid.uuid4().hex[:8]

        # Setup logging
        logs_dir = repo_dir / ".agents" / "web_runs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / f"{run_id}.log"

        _LOG.info("Starting workflow run %s: %s", run_id, " ".join(cmd))

        # Launch subprocess
        try:
            with open(log_path, "w") as log_file:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=str(repo_dir),
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )

            _active_runs[run_id] = ActiveRun(run_id, process, log_path)

            return {
                "success": True,
                "run_id": run_id,
                "message": f"Run started with ID {run_id}",
                "log_url": f"/runs/{run_id}/live",
            }
        except Exception as e:
            _LOG.exception("Failed to start run")
            return {
                "success": False,
                "error": str(e),
            }

    @app.get("/api/runs/{run_id}/status")
    async def api_run_status(run_id: str):
        """Get status of an active run."""
        if run_id in _active_runs:
            active = _active_runs[run_id]
            poll = active.process.poll()
            return {
                "active": True,
                "running": poll is None,
                "exit_code": poll,
                "started_at": active.started_at,
            }

        # Check if run exists in stats
        tracker: DailyStatsTracker = app.state.stats_tracker
        run_info = get_run_info(tracker, run_id)
        if run_info:
            return {
                "active": False,
                "running": False,
                "status": run_info.get("status", "UNKNOWN"),
                "started_at": run_info.get("started_at"),
                "ended_at": run_info.get("ended_at"),
            }

        return {"error": "Run not found"}

    @app.get("/api/runs/{run_id}/stream")
    async def api_run_stream(run_id: str):
        """Stream run output via Server-Sent Events."""
        async def generate():
            # Check if this is an active web run
            if run_id in _active_runs:
                log_path = _active_runs[run_id].log_path
            else:
                # Look for log in web_runs directory
                log_path = app.state.repo_dir / ".agents" / "web_runs" / f"{run_id}.log"

            if not log_path.exists():
                yield f"data: {json.dumps({'type': 'error', 'message': 'Log file not found'})}\n\n"
                return

            last_pos = 0
            while True:
                try:
                    with open(log_path, "r") as f:
                        f.seek(last_pos)
                        new_content = f.read()
                        if new_content:
                            last_pos = f.tell()
                            # Send each line as a separate event
                            for line in new_content.splitlines():
                                yield f"data: {json.dumps({'type': 'output', 'line': line})}\n\n"

                    # Check if run is still active
                    if run_id in _active_runs:
                        poll = _active_runs[run_id].process.poll()
                        if poll is not None:
                            yield f"data: {json.dumps({'type': 'complete', 'exit_code': poll})}\n\n"
                            # Clean up
                            del _active_runs[run_id]
                            return
                    else:
                        # Run not active - send any remaining content and exit
                        await asyncio.sleep(0.5)
                        with open(log_path, "r") as f:
                            f.seek(last_pos)
                            remaining = f.read()
                            if remaining:
                                for line in remaining.splitlines():
                                    yield f"data: {json.dumps({'type': 'output', 'line': line})}\n\n"
                        yield f"data: {json.dumps({'type': 'complete', 'exit_code': 0})}\n\n"
                        return

                    await asyncio.sleep(0.3)  # Poll interval
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                    return

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    @app.post("/api/runs/{run_id}/stop")
    async def api_stop_run(run_id: str):
        """Stop a running workflow."""
        if run_id not in _active_runs:
            return {"success": False, "error": "Run not found or not active"}

        active = _active_runs[run_id]
        try:
            active.process.terminate()
            # Wait a bit for graceful shutdown
            try:
                active.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                active.process.kill()

            del _active_runs[run_id]
            return {"success": True, "message": "Run stopped"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    return app


def discover_workflows(repo_dir: Path) -> List[Dict[str, Any]]:
    """Discover available workflow files."""
    workflows = []
    orchestrator_src = Path(__file__).parent.parent
    workflows_dir = orchestrator_src / "workflows"

    if workflows_dir.exists():
        for yaml_file in sorted(workflows_dir.glob("*.yaml")):
            try:
                workflow = load_workflow(yaml_file)
                workflows.append({
                    "path": str(yaml_file.relative_to(orchestrator_src)),
                    "name": workflow.name,
                    "description": workflow.description,
                    "filename": yaml_file.name,
                    "step_count": len(workflow.steps),
                })
            except WorkflowLoadError:
                # Include even if we can't parse it
                workflows.append({
                    "path": str(yaml_file.relative_to(orchestrator_src)),
                    "name": yaml_file.stem,
                    "description": "(Failed to parse)",
                    "filename": yaml_file.name,
                    "step_count": 0,
                })

    return workflows


def discover_wrappers(repo_dir: Path) -> List[Dict[str, Any]]:
    """Discover available wrapper scripts."""
    wrappers = []
    orchestrator_src = Path(__file__).parent.parent
    wrappers_dir = orchestrator_src / "wrappers"

    if wrappers_dir.exists():
        for py_file in sorted(wrappers_dir.glob("*_wrapper.py")):
            wrappers.append({
                "path": str(py_file.relative_to(orchestrator_src)),
                "name": py_file.stem.replace("_wrapper", "").replace("_", " ").title(),
                "filename": py_file.name,
            })

    return wrappers


# Helper functions


def format_cost(value: float) -> str:
    """Format cost in USD."""
    if value < 0.01:
        return f"${value:.4f}"
    return f"${value:.2f}"


def format_tokens(value: int) -> str:
    """Format token count with K/M suffixes."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def format_duration(ms: int) -> str:
    """Format duration from milliseconds."""
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60
    return f"{hours:.1f}h"


def status_emoji(status: str) -> str:
    """Get emoji for status."""
    status = status.upper()
    return {
        "COMPLETED": "✅",
        "FAILED": "❌",
        "RUNNING": "⏳",
        "PENDING": "⏸️",
        "SKIPPED": "⏭️",
        "WAITING_ON_HUMAN": "👤",
    }.get(status, "❓")


def status_class(status: str) -> str:
    """Get CSS class for status."""
    status = status.upper()
    return {
        "COMPLETED": "status-success",
        "FAILED": "status-error",
        "RUNNING": "status-running",
        "PENDING": "status-pending",
        "SKIPPED": "status-skipped",
        "WAITING_ON_HUMAN": "status-waiting",
    }.get(status, "")


def get_recent_runs(stats: DailyStats, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent runs from stats."""
    runs = []
    for run_id, run_info in stats.runs.items():
        runs.append(
            {
                "run_id": run_id,
                "workflow_name": run_info.get("workflow_name", "unknown"),
                "status": run_info.get("status", "UNKNOWN"),
                "total_cost_usd": run_info.get("total_cost_usd", 0.0),
                "steps_completed": run_info.get("steps_completed", 0),
                "steps_failed": run_info.get("steps_failed", 0),
                "started_at": run_info.get("started_at", ""),
                "ended_at": run_info.get("ended_at", ""),
            }
        )
    # Sort by started_at descending
    runs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return runs[:limit]


def get_stats_range(tracker: DailyStatsTracker, days: int) -> List[DailyStats]:
    """Get stats for the last N days."""
    stats_list = []
    today = datetime.now(timezone.utc).date()
    for i in range(days):
        target_date = today - timedelta(days=i)
        stats = tracker.get_daily_stats(target_date)
        stats_list.append(stats)
    # Reverse to get chronological order
    stats_list.reverse()
    return stats_list


def prepare_chart_data(stats_list: List[DailyStats]) -> Dict[str, Any]:
    """Prepare data for charts."""
    dates = []
    costs = []
    runs = []
    tokens_input = []
    tokens_output = []

    for stats in stats_list:
        dates.append(stats.date)
        costs.append(round(stats.total_cost_usd, 4))
        runs.append(stats.total_runs)
        tokens_input.append(stats.total_input_tokens)
        tokens_output.append(stats.total_output_tokens)

    return {
        "dates": dates,
        "costs": costs,
        "runs": runs,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
    }


def get_cost_by_step(stats_list: List[DailyStats]) -> Dict[str, float]:
    """Aggregate cost by step ID across all stats."""
    cost_by_step: Dict[str, float] = {}

    for stats in stats_list:
        for step in stats.steps:
            step_id = step.get("step_id", "unknown")
            cost = step.get("cost_usd", 0.0)
            cost_by_step[step_id] = cost_by_step.get(step_id, 0.0) + cost

    # Sort by cost descending
    sorted_steps = dict(
        sorted(cost_by_step.items(), key=lambda x: x[1], reverse=True)
    )
    return sorted_steps


def get_all_runs(tracker: DailyStatsTracker, days: int) -> List[Dict[str, Any]]:
    """Get all runs for the last N days."""
    all_runs = []
    today = datetime.now(timezone.utc).date()

    for i in range(days):
        target_date = today - timedelta(days=i)
        stats = tracker.get_daily_stats(target_date)
        for run_id, run_info in stats.runs.items():
            all_runs.append(
                {
                    "run_id": run_id,
                    "date": stats.date,
                    "workflow_name": run_info.get("workflow_name", "unknown"),
                    "status": run_info.get("status", "UNKNOWN"),
                    "total_cost_usd": run_info.get("total_cost_usd", 0.0),
                    "steps_completed": run_info.get("steps_completed", 0),
                    "steps_failed": run_info.get("steps_failed", 0),
                    "started_at": run_info.get("started_at", ""),
                    "ended_at": run_info.get("ended_at", ""),
                }
            )

    # Sort by started_at descending
    all_runs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return all_runs


def get_run_info(
    tracker: DailyStatsTracker, run_id: str, days: int = 30
) -> Optional[Dict[str, Any]]:
    """Find run info across recent days."""
    today = datetime.now(timezone.utc).date()

    for i in range(days):
        target_date = today - timedelta(days=i)
        stats = tracker.get_daily_stats(target_date)
        if run_id in stats.runs:
            run_info = stats.runs[run_id].copy()
            run_info["date"] = stats.date
            return run_info

    return None


def get_run_steps(
    repo_dir: Path, run_id: str, tracker: DailyStatsTracker, days: int = 30
) -> List[Dict[str, Any]]:
    """Get steps for a run from daily stats."""
    steps = []
    today = datetime.now(timezone.utc).date()

    for i in range(days):
        target_date = today - timedelta(days=i)
        stats = tracker.get_daily_stats(target_date)
        for step in stats.steps:
            if step.get("run_id") == run_id:
                steps.append(step)

    # Sort by timestamp
    steps.sort(key=lambda x: x.get("timestamp", ""))
    return steps
