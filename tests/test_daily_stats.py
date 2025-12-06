"""Tests for daily stats tracking."""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from agent_orchestrator.daily_stats import (
    DailyStats,
    DailyStatsTracker,
    calculate_cost,
    MODEL_PRICING,
)


class TestCalculateCost:
    """Tests for cost calculation."""

    def test_calculate_cost_opus(self):
        # 1000 input tokens @ $0.015/1K = $0.015
        # 1000 output tokens @ $0.075/1K = $0.075
        cost = calculate_cost(1000, 1000, "opus")
        assert cost == pytest.approx(0.09, rel=0.01)

    def test_calculate_cost_sonnet(self):
        # 1000 input tokens @ $0.003/1K = $0.003
        # 1000 output tokens @ $0.015/1K = $0.015
        cost = calculate_cost(1000, 1000, "sonnet")
        assert cost == pytest.approx(0.018, rel=0.01)

    def test_calculate_cost_haiku(self):
        # 1000 input tokens @ $0.00025/1K = $0.00025
        # 1000 output tokens @ $0.00125/1K = $0.00125
        cost = calculate_cost(1000, 1000, "haiku")
        assert cost == pytest.approx(0.0015, rel=0.01)

    def test_calculate_cost_unknown_model_uses_opus_pricing(self):
        cost = calculate_cost(1000, 1000, "unknown_model")
        expected = calculate_cost(1000, 1000, "opus")
        assert cost == expected


class TestDailyStats:
    """Tests for DailyStats dataclass."""

    def test_to_dict(self):
        stats = DailyStats(
            date="2024-01-15",
            total_runs=5,
            completed_runs=3,
            failed_runs=2,
            total_steps=20,
            total_cost_usd=1.2345,
        )
        data = stats.to_dict()
        assert data["date"] == "2024-01-15"
        assert data["total_runs"] == 5
        assert data["total_cost_usd"] == 1.2345

    def test_from_dict(self):
        data = {
            "date": "2024-01-15",
            "total_runs": 5,
            "completed_runs": 3,
            "failed_runs": 2,
            "total_steps": 20,
            "total_cost_usd": 1.5,
        }
        stats = DailyStats.from_dict(data)
        assert stats.date == "2024-01-15"
        assert stats.total_runs == 5
        assert stats.total_cost_usd == 1.5


class TestDailyStatsTracker:
    """Tests for DailyStatsTracker."""

    def test_record_step(self, tmp_path):
        tracker = DailyStatsTracker(tmp_path)

        cost = tracker.record_step(
            run_id="run-123",
            step_id="step-1",
            agent="coding",
            model="haiku",
            input_tokens=1000,
            output_tokens=500,
            duration_ms=5000,
            status="COMPLETED",
            workflow_name="test_workflow",
        )

        assert cost > 0

        stats = tracker.get_daily_stats()
        assert stats.total_steps == 1
        assert stats.completed_steps == 1
        assert stats.total_input_tokens == 1000
        assert stats.total_output_tokens == 500
        assert stats.total_cost_usd > 0

    def test_record_multiple_steps(self, tmp_path):
        tracker = DailyStatsTracker(tmp_path)

        tracker.record_step(
            run_id="run-123",
            step_id="step-1",
            agent="coding",
            model="opus",
            input_tokens=1000,
            output_tokens=500,
            duration_ms=5000,
            status="COMPLETED",
        )
        tracker.record_step(
            run_id="run-123",
            step_id="step-2",
            agent="review",
            model="haiku",
            input_tokens=2000,
            output_tokens=300,
            duration_ms=3000,
            status="COMPLETED",
        )

        stats = tracker.get_daily_stats()
        assert stats.total_steps == 2
        assert stats.total_input_tokens == 3000
        assert stats.total_output_tokens == 800
        assert "opus" in stats.cost_by_model
        assert "haiku" in stats.cost_by_model

    def test_record_run_lifecycle(self, tmp_path):
        tracker = DailyStatsTracker(tmp_path)

        tracker.record_run_start("run-123", "test_workflow")
        stats = tracker.get_daily_stats()
        assert stats.total_runs == 1
        assert "run-123" in stats.runs
        assert stats.runs["run-123"]["status"] == "RUNNING"

        tracker.record_run_end("run-123", "COMPLETED")
        stats = tracker.get_daily_stats()
        assert stats.completed_runs == 1
        assert stats.runs["run-123"]["status"] == "COMPLETED"

    def test_check_daily_limit_within(self, tmp_path):
        tracker = DailyStatsTracker(tmp_path)

        within, current, limit = tracker.check_daily_limit(10.0)
        assert within is True
        assert current == 0.0
        assert limit == 10.0

    def test_check_daily_limit_exceeded(self, tmp_path):
        tracker = DailyStatsTracker(tmp_path)

        # Record a step with significant cost
        tracker.record_step(
            run_id="run-123",
            step_id="step-1",
            agent="coding",
            model="opus",
            input_tokens=100000,  # 100K tokens
            output_tokens=50000,   # 50K tokens
            duration_ms=5000,
            status="COMPLETED",
        )

        # This should exceed a small limit
        within, current, limit = tracker.check_daily_limit(0.01)
        assert within is False
        assert current > 0.01

    def test_generate_summary(self, tmp_path):
        tracker = DailyStatsTracker(tmp_path)

        tracker.record_run_start("run-123", "test_workflow")
        tracker.record_step(
            run_id="run-123",
            step_id="step-1",
            agent="coding",
            model="sonnet",
            input_tokens=1000,
            output_tokens=500,
            duration_ms=5000,
            status="COMPLETED",
            workflow_name="test_workflow",
        )
        tracker.record_run_end("run-123", "COMPLETED")

        summary = tracker.generate_summary()
        assert "Daily Stats Summary" in summary
        assert "Total: 1" in summary  # Total runs
        assert "sonnet" in summary

    def test_stats_persisted_to_file(self, tmp_path):
        tracker1 = DailyStatsTracker(tmp_path)
        tracker1.record_step(
            run_id="run-123",
            step_id="step-1",
            agent="coding",
            model="haiku",
            input_tokens=1000,
            output_tokens=500,
            duration_ms=5000,
            status="COMPLETED",
        )

        # Create new tracker instance - should load persisted data
        tracker2 = DailyStatsTracker(tmp_path)
        stats = tracker2.get_daily_stats()
        assert stats.total_steps == 1
        assert stats.total_input_tokens == 1000

    def test_stats_file_location(self, tmp_path):
        tracker = DailyStatsTracker(tmp_path)
        tracker.record_run_start("run-123", "test")

        today = datetime.now(timezone.utc).date().isoformat()
        stats_file = tmp_path / ".agents" / "daily_stats" / f"{today}.json"
        assert stats_file.exists()

        data = json.loads(stats_file.read_text())
        assert data["date"] == today


class TestDailyStatsTrackerActualCost:
    """Tests for actual cost tracking from Claude CLI."""

    def test_actual_cost_used_when_provided(self, tmp_path):
        """When actual_cost_usd is provided, it should be used instead of calculated cost."""
        tracker = DailyStatsTracker(tmp_path)

        # Record with actual cost from Claude CLI
        cost = tracker.record_step(
            run_id="run-123",
            step_id="step-1",
            agent="coding",
            model="opus",
            input_tokens=1000,
            output_tokens=500,
            duration_ms=5000,
            status="COMPLETED",
            actual_cost_usd=0.50,  # Actual cost from Claude CLI
        )

        # Should return the actual cost, not calculated
        assert cost == 0.50

        stats = tracker.get_daily_stats()
        assert stats.total_cost_usd == 0.50
        # Check step record has cost_source
        assert stats.steps[0]["cost_source"] == "actual"

    def test_calculated_cost_when_no_actual(self, tmp_path):
        """When actual_cost_usd is None, cost should be calculated."""
        tracker = DailyStatsTracker(tmp_path)

        cost = tracker.record_step(
            run_id="run-123",
            step_id="step-1",
            agent="coding",
            model="haiku",
            input_tokens=1000,
            output_tokens=500,
            duration_ms=5000,
            status="COMPLETED",
            actual_cost_usd=None,  # No actual cost, use calculated
        )

        # Should be calculated cost
        expected = calculate_cost(1000, 500, "haiku")
        assert cost == expected

        stats = tracker.get_daily_stats()
        assert stats.steps[0]["cost_source"] == "estimated"

    def test_cache_tokens_recorded(self, tmp_path):
        """Cache tokens should be recorded in step details."""
        tracker = DailyStatsTracker(tmp_path)

        tracker.record_step(
            run_id="run-123",
            step_id="step-1",
            agent="coding",
            model="opus",
            input_tokens=100,
            output_tokens=50,
            duration_ms=5000,
            status="COMPLETED",
            actual_cost_usd=0.75,
            cache_creation_input_tokens=15000,
            cache_read_input_tokens=5000,
        )

        stats = tracker.get_daily_stats()
        step = stats.steps[0]
        assert step["cache_creation_input_tokens"] == 15000
        assert step["cache_read_input_tokens"] == 5000


class TestDailyStatsTrackerFailedSteps:
    """Tests for tracking failed steps."""

    def test_failed_step_recorded(self, tmp_path):
        tracker = DailyStatsTracker(tmp_path)

        tracker.record_step(
            run_id="run-123",
            step_id="step-1",
            agent="coding",
            model="opus",
            input_tokens=1000,
            output_tokens=100,
            duration_ms=5000,
            status="FAILED",
        )

        stats = tracker.get_daily_stats()
        assert stats.total_steps == 1
        assert stats.completed_steps == 0
        assert stats.failed_steps == 1

    def test_failed_run_recorded(self, tmp_path):
        tracker = DailyStatsTracker(tmp_path)

        tracker.record_run_start("run-123", "test")
        tracker.record_run_end("run-123", "FAILED")

        stats = tracker.get_daily_stats()
        assert stats.total_runs == 1
        assert stats.completed_runs == 0
        assert stats.failed_runs == 1
