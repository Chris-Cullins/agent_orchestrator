"""Run directory cleanup utilities for managing retention of run artifacts."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from .run_archive import RunArchive, extract_run_metadata

_LOG = logging.getLogger(__name__)

# Default retention settings
DEFAULT_MAX_AGE_HOURS = 48
DEFAULT_MAX_RUNS = 10


@dataclass
class RunInfo:
    """Information about a single run directory."""

    run_id: str
    path: Path
    created_at: datetime
    has_failed_step: bool

    @property
    def age(self) -> timedelta:
        """Return the age of the run from the current time."""
        return datetime.now(timezone.utc) - self.created_at


def parse_run_state(run_dir: Path) -> tuple[Optional[datetime], bool]:
    """Parse run_state.json to extract creation time and failure status.

    Args:
        run_dir: Path to the run directory

    Returns:
        Tuple of (created_at datetime, has_failed_step bool).
        If state file is missing or invalid, falls back to directory mtime.
    """
    state_file = run_dir / "run_state.json"
    has_failed_step = False
    created_at = None

    if state_file.exists():
        try:
            with state_file.open("r", encoding="utf-8") as f:
                state_data = json.load(f)

            # Extract created_at timestamp
            created_at_str = state_data.get("created_at")
            if created_at_str:
                # Parse ISO format timestamp (e.g., "2024-01-15T10:00:00.000000Z")
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Check if any step has FAILED status
            steps = state_data.get("steps", {})
            for step_runtime in steps.values():
                if step_runtime.get("status") == "FAILED":
                    has_failed_step = True
                    break

        except (json.JSONDecodeError, OSError) as exc:
            _LOG.debug("Failed to parse run state at %s: %s", state_file, exc)

    # Fall back to directory mtime if created_at not found
    if created_at is None:
        try:
            mtime = run_dir.stat().st_mtime
            created_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
        except OSError:
            created_at = datetime.now(timezone.utc)

    return created_at, has_failed_step


def enumerate_runs(runs_dir: Path) -> List[RunInfo]:
    """Enumerate all run directories and return their info.

    Args:
        runs_dir: Path to the .agents/runs directory

    Returns:
        List of RunInfo objects for all valid run directories
    """
    runs: List[RunInfo] = []

    if not runs_dir.exists():
        return runs

    for entry in runs_dir.iterdir():
        if not entry.is_dir():
            continue

        # Skip any hidden directories or special entries
        if entry.name.startswith("."):
            continue

        run_id = entry.name
        created_at, has_failed_step = parse_run_state(entry)

        runs.append(
            RunInfo(
                run_id=run_id,
                path=entry,
                created_at=created_at,
                has_failed_step=has_failed_step,
            )
        )

    return runs


def _is_run_active(run_dir: Path) -> bool:
    """Check if a run appears to be currently active.

    Detects active runs by checking for running status in run_state.json.
    """
    state_file = run_dir / "run_state.json"
    if not state_file.exists():
        return False

    try:
        with state_file.open("r", encoding="utf-8") as f:
            state_data = json.load(f)

        steps = state_data.get("steps", {})
        for step_runtime in steps.values():
            status = step_runtime.get("status")
            if status in ("RUNNING", "WAITING_ON_HUMAN"):
                return True

    except (json.JSONDecodeError, OSError):
        pass

    return False


def cleanup_old_runs(
    runs_dir: Path,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    archive: Optional[RunArchive] = None,
    daily_stats_dir: Optional[Path] = None,
) -> List[str]:
    """Remove runs older than the specified age, excluding failed runs.

    Args:
        runs_dir: Path to the .agents/runs directory
        max_age_hours: Maximum age in hours before a run is eligible for deletion
        archive: Optional RunArchive instance to save run metadata before deletion
        daily_stats_dir: Optional path to daily stats for cost lookup

    Returns:
        List of deleted run_ids
    """
    deleted: List[str] = []
    runs = enumerate_runs(runs_dir)
    max_age = timedelta(hours=max_age_hours)

    for run in runs:
        # Skip failed runs - preserve for debugging
        if run.has_failed_step:
            _LOG.debug("Preserving failed run: %s", run.run_id)
            continue

        # Skip active runs
        if _is_run_active(run.path):
            _LOG.debug("Skipping active run: %s", run.run_id)
            continue

        # Check age
        if run.age > max_age:
            try:
                # Archive run metadata before deletion
                if archive:
                    metadata = extract_run_metadata(run.path, daily_stats_dir)
                    archive.archive_run(**metadata)

                shutil.rmtree(run.path)
                deleted.append(run.run_id)
                _LOG.info(
                    "Deleted old run %s (age: %.1f hours)",
                    run.run_id,
                    run.age.total_seconds() / 3600,
                )
            except OSError as exc:
                _LOG.warning("Failed to delete run %s: %s", run.run_id, exc)

    if deleted:
        _LOG.info("Time-based cleanup removed %d run(s)", len(deleted))

    return deleted


def enforce_run_limit(
    runs_dir: Path,
    max_runs: int = DEFAULT_MAX_RUNS,
    archive: Optional[RunArchive] = None,
    daily_stats_dir: Optional[Path] = None,
) -> List[str]:
    """Enforce maximum run count by removing oldest runs.

    Unlike time-based cleanup, this will delete even failed runs when
    the limit is exceeded to make room for new runs.

    Args:
        runs_dir: Path to the .agents/runs directory
        max_runs: Maximum number of run directories to keep
        archive: Optional RunArchive instance to save run metadata before deletion
        daily_stats_dir: Optional path to daily stats for cost lookup

    Returns:
        List of deleted run_ids
    """
    deleted: List[str] = []
    runs = enumerate_runs(runs_dir)

    # Filter out active runs - never delete those
    deletable_runs = [r for r in runs if not _is_run_active(r.path)]

    # Sort by created_at (oldest first)
    deletable_runs.sort(key=lambda r: r.created_at)

    # Calculate how many to delete
    total_count = len(runs)
    delete_count = total_count - max_runs

    if delete_count <= 0:
        return deleted

    _LOG.info(
        "Run count (%d) exceeds limit (%d), removing %d oldest run(s)",
        total_count,
        max_runs,
        delete_count,
    )

    for run in deletable_runs[:delete_count]:
        try:
            # Archive run metadata before deletion
            if archive:
                metadata = extract_run_metadata(run.path, daily_stats_dir)
                archive.archive_run(**metadata)

            shutil.rmtree(run.path)
            deleted.append(run.run_id)
            _LOG.info(
                "Deleted run %s to enforce limit (created: %s%s)",
                run.run_id,
                run.created_at.isoformat(),
                ", was failed" if run.has_failed_step else "",
            )
        except OSError as exc:
            _LOG.warning("Failed to delete run %s: %s", run.run_id, exc)

    if deleted:
        _LOG.info("Count-based cleanup removed %d run(s)", len(deleted))

    return deleted


def cleanup_runs(
    repo_path: Path,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    max_runs: int = DEFAULT_MAX_RUNS,
    enable_archive: bool = True,
) -> List[str]:
    """Main entry point for run cleanup.

    Performs cleanup in two phases:
    1. Time-based: Remove runs older than max_age_hours (excluding failed runs)
    2. Count-based: If still over max_runs, remove oldest (including failed)

    Before deleting, run metadata is archived to a SQLite database for
    historical tracking.

    Args:
        repo_path: Path to the repository root
        max_age_hours: Maximum age in hours for time-based cleanup
        max_runs: Maximum number of runs to keep
        enable_archive: Whether to archive run metadata before deletion

    Returns:
        Combined list of all deleted run_ids
    """
    runs_dir = repo_path / ".agents" / "runs"
    daily_stats_dir = repo_path / ".agents" / "daily_stats"

    if not runs_dir.exists():
        _LOG.debug("No runs directory at %s, skipping cleanup", runs_dir)
        return []

    # Create archive for preserving run metadata
    archive = RunArchive(repo_path) if enable_archive else None

    deleted: List[str] = []

    # Phase 1: Time-based cleanup
    deleted.extend(cleanup_old_runs(runs_dir, max_age_hours, archive, daily_stats_dir))

    # Phase 2: Count-based cleanup
    deleted.extend(enforce_run_limit(runs_dir, max_runs, archive, daily_stats_dir))

    if deleted:
        _LOG.info("Run cleanup complete: removed %d run(s)", len(deleted))

    return deleted
