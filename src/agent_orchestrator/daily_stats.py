"""
Daily statistics tracking for cost management and reporting.

Tracks token usage, costs, and work completed across all runs for a given day.
Stores data in .agents/daily_stats/YYYY-MM-DD.json
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .time_utils import utc_now


# Model pricing per 1K tokens (as of 2024)
MODEL_PRICING = {
    "opus": {"input": 0.015, "output": 0.075},
    "sonnet": {"input": 0.003, "output": 0.015},
    "haiku": {"input": 0.00025, "output": 0.00125},
    # Aliases
    "claude-opus-4": {"input": 0.015, "output": 0.075},
    "claude-sonnet-4": {"input": 0.003, "output": 0.015},
    "claude-haiku-3": {"input": 0.00025, "output": 0.00125},
}

DEFAULT_PRICING = {"input": 0.015, "output": 0.075}  # Assume opus if unknown


@dataclass
class StepStats:
    """Statistics for a single step execution."""

    run_id: str
    step_id: str
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    status: str
    timestamp: str
    workflow_name: str = ""


@dataclass
class DailyStats:
    """Aggregated statistics for a single day."""

    date: str  # YYYY-MM-DD
    total_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: int = 0
    cost_by_model: Dict[str, float] = field(default_factory=dict)
    tokens_by_model: Dict[str, Dict[str, int]] = field(default_factory=dict)
    runs: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # run_id -> run info
    steps: List[Dict[str, Any]] = field(default_factory=list)  # All step records

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "total_runs": self.total_runs,
            "completed_runs": self.completed_runs,
            "failed_runs": self.failed_runs,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_duration_ms": self.total_duration_ms,
            "cost_by_model": {k: round(v, 4) for k, v in self.cost_by_model.items()},
            "tokens_by_model": self.tokens_by_model,
            "runs": self.runs,
            "steps": self.steps,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyStats":
        return cls(
            date=data.get("date", ""),
            total_runs=data.get("total_runs", 0),
            completed_runs=data.get("completed_runs", 0),
            failed_runs=data.get("failed_runs", 0),
            total_steps=data.get("total_steps", 0),
            completed_steps=data.get("completed_steps", 0),
            failed_steps=data.get("failed_steps", 0),
            total_input_tokens=data.get("total_input_tokens", 0),
            total_output_tokens=data.get("total_output_tokens", 0),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            total_duration_ms=data.get("total_duration_ms", 0),
            cost_by_model=data.get("cost_by_model", {}),
            tokens_by_model=data.get("tokens_by_model", {}),
            runs=data.get("runs", {}),
            steps=data.get("steps", []),
        )


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate cost based on token counts and model."""
    pricing = MODEL_PRICING.get(model.lower(), DEFAULT_PRICING)
    input_cost = (input_tokens / 1000) * pricing["input"]
    output_cost = (output_tokens / 1000) * pricing["output"]
    return input_cost + output_cost


class DailyStatsTracker:
    """
    Tracks daily statistics across all workflow runs.

    Statistics are stored in .agents/daily_stats/YYYY-MM-DD.json
    """

    def __init__(
        self,
        repo_dir: Path,
        logger: Optional[logging.Logger] = None,
    ):
        self._repo_dir = repo_dir
        self._stats_dir = repo_dir / ".agents" / "daily_stats"
        self._log = logger or logging.getLogger(__name__)
        self._stats_dir.mkdir(parents=True, exist_ok=True)

    def _get_stats_file(self, for_date: Optional[date] = None) -> Path:
        """Get the stats file path for a given date."""
        if for_date is None:
            for_date = datetime.now(timezone.utc).date()
        return self._stats_dir / f"{for_date.isoformat()}.json"

    def _load_stats(self, for_date: Optional[date] = None) -> DailyStats:
        """Load stats for a given date, or create new if not exists."""
        stats_file = self._get_stats_file(for_date)
        if stats_file.exists():
            try:
                data = json.loads(stats_file.read_text(encoding="utf-8"))
                return DailyStats.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                self._log.warning("Failed to load daily stats: %s", e)

        date_str = (for_date or datetime.now(timezone.utc).date()).isoformat()
        return DailyStats(date=date_str)

    def _save_stats(self, stats: DailyStats) -> None:
        """Save stats to file."""
        stats_file = self._get_stats_file(date.fromisoformat(stats.date))
        stats_file.write_text(
            json.dumps(stats.to_dict(), indent=2),
            encoding="utf-8",
        )

    def record_step(
        self,
        run_id: str,
        step_id: str,
        agent: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
        status: str,
        workflow_name: str = "",
        actual_cost_usd: Optional[float] = None,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> float:
        """
        Record a step execution and return the cost.

        Args:
            actual_cost_usd: If provided, use this cost instead of calculating.
                             This is typically the cost reported by Claude CLI.
            cache_creation_input_tokens: Tokens used for cache creation.
            cache_read_input_tokens: Tokens read from cache.

        Returns the cost in USD for this step.
        """
        stats = self._load_stats()
        # Use actual cost if provided, otherwise calculate
        if actual_cost_usd is not None:
            cost = actual_cost_usd
        else:
            cost = calculate_cost(input_tokens, output_tokens, model)

        # Update totals
        stats.total_steps += 1
        if status.upper() == "COMPLETED":
            stats.completed_steps += 1
        else:
            stats.failed_steps += 1

        stats.total_input_tokens += input_tokens
        stats.total_output_tokens += output_tokens
        stats.total_cost_usd += cost
        stats.total_duration_ms += duration_ms

        # Update per-model stats
        model_lower = model.lower()
        stats.cost_by_model[model_lower] = (
            stats.cost_by_model.get(model_lower, 0.0) + cost
        )
        if model_lower not in stats.tokens_by_model:
            stats.tokens_by_model[model_lower] = {"input": 0, "output": 0}
        stats.tokens_by_model[model_lower]["input"] += input_tokens
        stats.tokens_by_model[model_lower]["output"] += output_tokens

        # Record step details
        step_record = {
            "run_id": run_id,
            "step_id": step_id,
            "agent": agent,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
            "cost_usd": round(cost, 4),
            "cost_source": "actual" if actual_cost_usd is not None else "estimated",
            "duration_ms": duration_ms,
            "status": status,
            "timestamp": utc_now(),
            "workflow_name": workflow_name,
        }
        stats.steps.append(step_record)

        # Update run tracking
        if run_id not in stats.runs:
            stats.runs[run_id] = {
                "workflow_name": workflow_name,
                "started_at": utc_now(),
                "status": "RUNNING",
                "total_cost_usd": 0.0,
                "steps_completed": 0,
                "steps_failed": 0,
            }
        stats.runs[run_id]["total_cost_usd"] += cost
        if status.upper() == "COMPLETED":
            stats.runs[run_id]["steps_completed"] += 1
        else:
            stats.runs[run_id]["steps_failed"] += 1

        self._save_stats(stats)
        self._log.debug(
            "Recorded step: run=%s step=%s model=%s cost=$%.4f",
            run_id,
            step_id,
            model,
            cost,
        )
        return cost

    def record_run_start(self, run_id: str, workflow_name: str) -> None:
        """Record the start of a new run."""
        stats = self._load_stats()
        stats.total_runs += 1

        if run_id not in stats.runs:
            stats.runs[run_id] = {
                "workflow_name": workflow_name,
                "started_at": utc_now(),
                "status": "RUNNING",
                "total_cost_usd": 0.0,
                "steps_completed": 0,
                "steps_failed": 0,
            }

        self._save_stats(stats)
        self._log.info("Recorded run start: run=%s workflow=%s", run_id, workflow_name)

    def record_run_end(self, run_id: str, status: str) -> None:
        """Record the end of a run."""
        stats = self._load_stats()

        if status.upper() == "COMPLETED":
            stats.completed_runs += 1
        else:
            stats.failed_runs += 1

        if run_id in stats.runs:
            stats.runs[run_id]["status"] = status
            stats.runs[run_id]["ended_at"] = utc_now()

        self._save_stats(stats)
        self._log.info("Recorded run end: run=%s status=%s", run_id, status)

    def get_daily_cost(self, for_date: Optional[date] = None) -> float:
        """Get total cost for a given date."""
        stats = self._load_stats(for_date)
        return stats.total_cost_usd

    def get_daily_stats(self, for_date: Optional[date] = None) -> DailyStats:
        """Get full stats for a given date."""
        return self._load_stats(for_date)

    def check_daily_limit(self, limit_usd: float) -> tuple[bool, float, float]:
        """
        Check if daily spending is within limit.

        Returns: (within_limit, current_cost, limit)
        """
        current_cost = self.get_daily_cost()
        within_limit = current_cost < limit_usd
        return within_limit, current_cost, limit_usd

    def generate_summary(self, for_date: Optional[date] = None) -> str:
        """Generate a human-readable summary for the day."""
        stats = self._load_stats(for_date)

        lines = [
            f"Daily Stats Summary: {stats.date}",
            "=" * 50,
            "",
            "RUNS",
            f"  Total: {stats.total_runs}",
            f"  Completed: {stats.completed_runs}",
            f"  Failed: {stats.failed_runs}",
            "",
            "STEPS",
            f"  Total: {stats.total_steps}",
            f"  Completed: {stats.completed_steps}",
            f"  Failed: {stats.failed_steps}",
            "",
            "TOKENS",
            f"  Input: {stats.total_input_tokens:,}",
            f"  Output: {stats.total_output_tokens:,}",
            f"  Total: {stats.total_input_tokens + stats.total_output_tokens:,}",
            "",
            "COST",
            f"  Total: ${stats.total_cost_usd:.4f}",
        ]

        if stats.cost_by_model:
            lines.append("")
            lines.append("COST BY MODEL")
            for model, cost in sorted(
                stats.cost_by_model.items(), key=lambda x: x[1], reverse=True
            ):
                tokens = stats.tokens_by_model.get(model, {})
                total_tokens = tokens.get("input", 0) + tokens.get("output", 0)
                lines.append(f"  {model}: ${cost:.4f} ({total_tokens:,} tokens)")

        if stats.runs:
            lines.append("")
            lines.append("RUNS DETAIL")
            for run_id, run_info in stats.runs.items():
                status = run_info.get("status", "UNKNOWN")
                cost = run_info.get("total_cost_usd", 0)
                workflow = run_info.get("workflow_name", "unknown")
                steps_ok = run_info.get("steps_completed", 0)
                steps_fail = run_info.get("steps_failed", 0)
                lines.append(
                    f"  {run_id}: {workflow} [{status}] "
                    f"${cost:.4f} ({steps_ok} ok, {steps_fail} failed)"
                )

        duration_min = stats.total_duration_ms / 1000 / 60
        lines.extend(
            [
                "",
                "TIME",
                f"  Total Duration: {duration_min:.1f} minutes",
                "",
                "=" * 50,
            ]
        )

        return "\n".join(lines)


def get_stats_for_date_range(
    repo_dir: Path,
    start_date: date,
    end_date: date,
    logger: Optional[logging.Logger] = None,
) -> List[DailyStats]:
    """Get stats for a range of dates."""
    tracker = DailyStatsTracker(repo_dir, logger)
    stats_list = []
    current = start_date
    while current <= end_date:
        stats = tracker.get_daily_stats(current)
        if stats.total_runs > 0:  # Only include days with activity
            stats_list.append(stats)
        current = date(
            current.year,
            current.month,
            current.day + 1 if current.day < 28 else 1,
        )
        # Handle month rollover properly
        from datetime import timedelta

        current = start_date + timedelta(days=(current - start_date).days + 1)
        if current > end_date:
            break
    return stats_list
