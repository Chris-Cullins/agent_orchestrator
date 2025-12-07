"""Tests for run cleanup utilities."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from agent_orchestrator.run_cleanup import (
    DEFAULT_MAX_AGE_HOURS,
    RunInfo,
    cleanup_old_runs,
    cleanup_runs,
    enforce_run_limit,
    enumerate_runs,
    parse_run_state,
)


def _create_run_state(
    run_dir: Path,
    created_at: datetime,
    steps: Optional[dict] = None,
) -> None:
    """Helper to create a run_state.json file."""
    state = {
        "run_id": run_dir.name,
        "workflow_name": "test_workflow",
        "repo_dir": str(run_dir.parent.parent.parent),
        "reports_dir": str(run_dir / "reports"),
        "manual_inputs_dir": str(run_dir / "manual_inputs"),
        "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "updated_at": created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "steps": steps or {},
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_state.json").write_text(json.dumps(state, indent=2))


def _create_run_dir(
    runs_dir: Path,
    run_id: str,
    age_hours: float = 0,
    failed: bool = False,
    running: bool = False,
) -> Path:
    """Helper to create a run directory with state."""
    run_dir = runs_dir / run_id
    created_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)

    steps = {}
    if failed:
        steps = {
            "step1": {
                "status": "FAILED",
                "attempts": 1,
                "last_error": "Test failure",
            }
        }
    elif running:
        steps = {
            "step1": {
                "status": "RUNNING",
                "attempts": 1,
            }
        }

    _create_run_state(run_dir, created_at, steps)
    return run_dir


class TestParseRunState:
    """Tests for parse_run_state function."""

    def test_parse_valid_state(self, tmp_path):
        """Test parsing a valid run_state.json."""
        run_dir = tmp_path / "test-run"
        created = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        _create_run_state(run_dir, created, {"step1": {"status": "COMPLETED"}})

        created_at, has_failed = parse_run_state(run_dir)

        assert created_at.year == 2024
        assert created_at.month == 1
        assert created_at.day == 15
        assert has_failed is False

    def test_parse_failed_state(self, tmp_path):
        """Test detection of failed steps."""
        run_dir = tmp_path / "test-run"
        created = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        _create_run_state(run_dir, created, {"step1": {"status": "FAILED"}})

        created_at, has_failed = parse_run_state(run_dir)

        assert has_failed is True

    def test_parse_missing_state_file(self, tmp_path):
        """Test fallback to directory mtime when state file missing."""
        run_dir = tmp_path / "test-run"
        run_dir.mkdir(parents=True)
        # No run_state.json file

        created_at, has_failed = parse_run_state(run_dir)

        # Should use mtime and assume not failed
        assert created_at is not None
        assert has_failed is False

    def test_parse_invalid_json(self, tmp_path):
        """Test handling of malformed JSON."""
        run_dir = tmp_path / "test-run"
        run_dir.mkdir(parents=True)
        (run_dir / "run_state.json").write_text("{ invalid json }")

        created_at, has_failed = parse_run_state(run_dir)

        # Should fall back to mtime
        assert created_at is not None
        assert has_failed is False


class TestEnumerateRuns:
    """Tests for enumerate_runs function."""

    def test_empty_runs_dir(self, tmp_path):
        """Test with empty or nonexistent runs directory."""
        runs_dir = tmp_path / ".agents" / "runs"

        runs = enumerate_runs(runs_dir)

        assert runs == []

    def test_enumerate_multiple_runs(self, tmp_path):
        """Test enumeration of multiple run directories."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        _create_run_dir(runs_dir, "run-1", age_hours=1)
        _create_run_dir(runs_dir, "run-2", age_hours=24)
        _create_run_dir(runs_dir, "run-3", age_hours=2, failed=True)

        runs = enumerate_runs(runs_dir)

        assert len(runs) == 3
        run_ids = {r.run_id for r in runs}
        assert run_ids == {"run-1", "run-2", "run-3"}

    def test_skips_files(self, tmp_path):
        """Test that non-directory entries are skipped."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        _create_run_dir(runs_dir, "valid-run", age_hours=1)
        (runs_dir / "not-a-dir.txt").write_text("some file")

        runs = enumerate_runs(runs_dir)

        assert len(runs) == 1
        assert runs[0].run_id == "valid-run"

    def test_skips_hidden_dirs(self, tmp_path):
        """Test that hidden directories are skipped."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        _create_run_dir(runs_dir, "valid-run", age_hours=1)
        hidden = runs_dir / ".hidden-run"
        hidden.mkdir()

        runs = enumerate_runs(runs_dir)

        assert len(runs) == 1
        assert runs[0].run_id == "valid-run"


class TestCleanupOldRuns:
    """Tests for cleanup_old_runs function."""

    def test_deletes_old_runs(self, tmp_path):
        """Test deletion of runs older than max age."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        _create_run_dir(runs_dir, "old-run", age_hours=60)  # Older than 48h
        _create_run_dir(runs_dir, "new-run", age_hours=1)   # Fresh

        deleted = cleanup_old_runs(runs_dir, max_age_hours=DEFAULT_MAX_AGE_HOURS)

        assert deleted == ["old-run"]
        assert not (runs_dir / "old-run").exists()
        assert (runs_dir / "new-run").exists()

    def test_preserves_failed_runs(self, tmp_path):
        """Test that failed runs are preserved even if old."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        _create_run_dir(runs_dir, "old-failed", age_hours=100, failed=True)

        deleted = cleanup_old_runs(runs_dir, max_age_hours=DEFAULT_MAX_AGE_HOURS)

        assert deleted == []
        assert (runs_dir / "old-failed").exists()

    def test_preserves_active_runs(self, tmp_path):
        """Test that running jobs are not deleted."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        _create_run_dir(runs_dir, "active-run", age_hours=100, running=True)

        deleted = cleanup_old_runs(runs_dir, max_age_hours=DEFAULT_MAX_AGE_HOURS)

        assert deleted == []
        assert (runs_dir / "active-run").exists()

    def test_custom_max_age(self, tmp_path):
        """Test with custom max age setting."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        _create_run_dir(runs_dir, "medium-old", age_hours=10)

        # Should not delete with 48h default
        deleted1 = cleanup_old_runs(runs_dir, max_age_hours=48)
        assert deleted1 == []

        # Should delete with 5h limit
        deleted2 = cleanup_old_runs(runs_dir, max_age_hours=5)
        assert deleted2 == ["medium-old"]

    def test_empty_runs_dir(self, tmp_path):
        """Test cleanup on empty directory."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        deleted = cleanup_old_runs(runs_dir)

        assert deleted == []


class TestEnforceRunLimit:
    """Tests for enforce_run_limit function."""

    def test_no_deletion_under_limit(self, tmp_path):
        """Test that runs under limit are not deleted."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        for i in range(5):
            _create_run_dir(runs_dir, f"run-{i}", age_hours=i)

        deleted = enforce_run_limit(runs_dir, max_runs=10)

        assert deleted == []
        assert len(list(runs_dir.iterdir())) == 5

    def test_deletes_oldest_when_over_limit(self, tmp_path):
        """Test deletion of oldest runs when over limit."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        # Create 5 runs with different ages
        _create_run_dir(runs_dir, "oldest", age_hours=50)
        _create_run_dir(runs_dir, "second", age_hours=40)
        _create_run_dir(runs_dir, "third", age_hours=30)
        _create_run_dir(runs_dir, "fourth", age_hours=20)
        _create_run_dir(runs_dir, "newest", age_hours=10)

        deleted = enforce_run_limit(runs_dir, max_runs=3)

        # Should delete the 2 oldest
        assert set(deleted) == {"oldest", "second"}
        assert not (runs_dir / "oldest").exists()
        assert not (runs_dir / "second").exists()
        assert (runs_dir / "third").exists()
        assert (runs_dir / "fourth").exists()
        assert (runs_dir / "newest").exists()

    def test_deletes_failed_runs_when_over_limit(self, tmp_path):
        """Test that failed runs ARE deleted when enforcing count limit."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        _create_run_dir(runs_dir, "old-failed", age_hours=100, failed=True)
        _create_run_dir(runs_dir, "new-success", age_hours=1)
        _create_run_dir(runs_dir, "newer-success", age_hours=0.5)

        deleted = enforce_run_limit(runs_dir, max_runs=2)

        # Failed run should be deleted (it's oldest)
        assert deleted == ["old-failed"]
        assert not (runs_dir / "old-failed").exists()

    def test_preserves_active_runs(self, tmp_path):
        """Test that active runs are never deleted."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        _create_run_dir(runs_dir, "active", age_hours=100, running=True)
        _create_run_dir(runs_dir, "completed1", age_hours=50)
        _create_run_dir(runs_dir, "completed2", age_hours=1)

        deleted = enforce_run_limit(runs_dir, max_runs=2)

        # Active run preserved even though oldest
        assert deleted == ["completed1"]
        assert (runs_dir / "active").exists()

    def test_exactly_at_limit(self, tmp_path):
        """Test behavior when exactly at the limit."""
        runs_dir = tmp_path / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        for i in range(3):
            _create_run_dir(runs_dir, f"run-{i}", age_hours=i)

        deleted = enforce_run_limit(runs_dir, max_runs=3)

        assert deleted == []
        assert len(list(runs_dir.iterdir())) == 3


class TestCleanupRuns:
    """Tests for the main cleanup_runs entry point."""

    def test_combines_both_cleanups(self, tmp_path):
        """Test that both time-based and count-based cleanup run."""
        repo_dir = tmp_path
        runs_dir = repo_dir / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        # Create old runs (will be cleaned by time-based)
        _create_run_dir(runs_dir, "very-old", age_hours=100)

        # Create many recent runs (some will be cleaned by count-based)
        for i in range(12):
            _create_run_dir(runs_dir, f"recent-{i}", age_hours=i)

        deleted = cleanup_runs(repo_dir, max_age_hours=48, max_runs=10)

        # very-old should be deleted by time-based
        assert "very-old" in deleted

        # After time-based: 12 runs remain, count-based removes 2 more
        assert len(deleted) >= 3  # At least very-old + 2 oldest recent

    def test_nonexistent_runs_dir(self, tmp_path):
        """Test with no runs directory."""
        repo_dir = tmp_path
        # Don't create .agents/runs

        deleted = cleanup_runs(repo_dir)

        assert deleted == []

    def test_time_based_runs_first(self, tmp_path):
        """Test that time-based cleanup runs before count-based."""
        repo_dir = tmp_path
        runs_dir = repo_dir / ".agents" / "runs"
        runs_dir.mkdir(parents=True)

        # Create 12 runs, 2 are old
        _create_run_dir(runs_dir, "old-1", age_hours=100)
        _create_run_dir(runs_dir, "old-2", age_hours=80)
        for i in range(10):
            _create_run_dir(runs_dir, f"recent-{i}", age_hours=i)

        deleted = cleanup_runs(repo_dir, max_age_hours=48, max_runs=10)

        # Time-based should delete old-1, old-2
        # Then count-based: 10 runs remaining, at limit, no more deleted
        assert set(deleted) == {"old-1", "old-2"}
        remaining = list(runs_dir.iterdir())
        assert len(remaining) == 10


class TestRunInfo:
    """Tests for RunInfo dataclass."""

    def test_age_calculation(self):
        """Test that age property returns correct timedelta."""
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        info = RunInfo(
            run_id="test",
            path=Path("/fake"),
            created_at=one_hour_ago,
            has_failed_step=False,
        )

        # Age should be approximately 1 hour
        assert 0.9 < info.age.total_seconds() / 3600 < 1.1


class TestCliIntegration:
    """Tests for CLI integration of cleanup."""

    def test_skip_cleanup_flag_parsed(self):
        """Test that --skip-cleanup flag is recognized."""
        from agent_orchestrator.cli import build_parser

        parser = build_parser()
        args = parser.parse_args([
            "run",
            "--repo", "/tmp/test",
            "--workflow", "/tmp/workflow.yaml",
            "--wrapper", "/tmp/wrapper.py",
            "--skip-cleanup",
        ])

        assert args.skip_cleanup is True

    def test_skip_cleanup_default_false(self):
        """Test that skip_cleanup defaults to False."""
        from agent_orchestrator.cli import build_parser

        parser = build_parser()
        args = parser.parse_args([
            "run",
            "--repo", "/tmp/test",
            "--workflow", "/tmp/workflow.yaml",
            "--wrapper", "/tmp/wrapper.py",
        ])

        assert args.skip_cleanup is False
