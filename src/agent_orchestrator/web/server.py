"""FastAPI web server for the agent orchestrator dashboard."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..daily_stats import DailyStats, DailyStatsTracker

_LOG = logging.getLogger(__name__)


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

    return app


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
