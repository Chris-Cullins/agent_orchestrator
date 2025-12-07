"""
Run archive database for preserving metadata of cleaned-up runs.

Stores run summaries in a lightweight SQLite database at .agents/run_archive.db
so historical run data survives retention cleanup.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .time_utils import utc_now

_LOG = logging.getLogger(__name__)

# Database schema version for future migrations
SCHEMA_VERSION = 1


@dataclass
class ArchivedRun:
    """Represents an archived run's metadata."""

    run_id: str
    workflow_name: str
    status: str
    created_at: str
    ended_at: Optional[str]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    steps_completed: int
    steps_failed: int
    work_summary: str
    archived_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "created_at": self.created_at,
            "ended_at": self.ended_at,
            "total_cost_usd": self.total_cost_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "work_summary": self.work_summary,
            "archived_at": self.archived_at,
        }


class RunArchive:
    """
    SQLite-based archive for run metadata.

    Stores run summaries that survive cleanup, allowing historical
    tracking of costs, runs, and work completed.
    """

    def __init__(self, repo_dir: Path, logger: Optional[logging.Logger] = None):
        self._repo_dir = repo_dir
        self._db_path = repo_dir / ".agents" / "run_archive.db"
        self._log = logger or logging.getLogger(__name__)
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Create the database and tables if they don't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()

            # Create schema version table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)

            # Check current version
            cursor.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            current_version = row[0] if row else 0

            if current_version < SCHEMA_VERSION:
                self._migrate(conn, current_version)

    def _migrate(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Run database migrations."""
        cursor = conn.cursor()

        if from_version < 1:
            # Initial schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS archived_runs (
                    run_id TEXT PRIMARY KEY,
                    workflow_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    ended_at TEXT,
                    total_cost_usd REAL DEFAULT 0.0,
                    total_input_tokens INTEGER DEFAULT 0,
                    total_output_tokens INTEGER DEFAULT 0,
                    steps_completed INTEGER DEFAULT 0,
                    steps_failed INTEGER DEFAULT 0,
                    work_summary TEXT DEFAULT '',
                    archived_at TEXT NOT NULL
                )
            """)

            # Index for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_archived_runs_created
                ON archived_runs(created_at DESC)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_archived_runs_workflow
                ON archived_runs(workflow_name)
            """)

            # Update schema version
            cursor.execute("DELETE FROM schema_version")
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))

            conn.commit()
            self._log.info("Initialized run archive database (schema v%d)", SCHEMA_VERSION)

    def archive_run(
        self,
        run_id: str,
        workflow_name: str,
        status: str,
        created_at: str,
        ended_at: Optional[str] = None,
        total_cost_usd: float = 0.0,
        total_input_tokens: int = 0,
        total_output_tokens: int = 0,
        steps_completed: int = 0,
        steps_failed: int = 0,
        work_summary: str = "",
    ) -> bool:
        """
        Archive a run's metadata.

        Returns True if the run was archived, False if it already exists.
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO archived_runs (
                        run_id, workflow_name, status, created_at, ended_at,
                        total_cost_usd, total_input_tokens, total_output_tokens,
                        steps_completed, steps_failed, work_summary, archived_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        workflow_name,
                        status,
                        created_at,
                        ended_at,
                        total_cost_usd,
                        total_input_tokens,
                        total_output_tokens,
                        steps_completed,
                        steps_failed,
                        work_summary,
                        utc_now(),
                    ),
                )
                conn.commit()

                if cursor.rowcount > 0:
                    self._log.info(
                        "Archived run %s: %s [%s] $%.4f",
                        run_id,
                        workflow_name,
                        status,
                        total_cost_usd,
                    )
                    return True
                return False

        except sqlite3.Error as e:
            self._log.error("Failed to archive run %s: %s", run_id, e)
            return False

    def get_archived_run(self, run_id: str) -> Optional[ArchivedRun]:
        """Get a single archived run by ID."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM archived_runs WHERE run_id = ?", (run_id,))
                row = cursor.fetchone()
                if row:
                    return ArchivedRun(**dict(row))
                return None
        except sqlite3.Error as e:
            self._log.error("Failed to get archived run %s: %s", run_id, e)
            return None

    def get_all_archived_runs(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        workflow_name: Optional[str] = None,
    ) -> List[ArchivedRun]:
        """
        Get archived runs with optional filtering.

        Args:
            limit: Maximum number of runs to return
            offset: Number of runs to skip (for pagination)
            workflow_name: Filter by workflow name
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                query = "SELECT * FROM archived_runs"
                params: List[Any] = []

                if workflow_name:
                    query += " WHERE workflow_name = ?"
                    params.append(workflow_name)

                query += " ORDER BY created_at DESC"

                if limit:
                    query += " LIMIT ?"
                    params.append(limit)
                    if offset:
                        query += " OFFSET ?"
                        params.append(offset)

                cursor.execute(query, params)
                return [ArchivedRun(**dict(row)) for row in cursor.fetchall()]

        except sqlite3.Error as e:
            self._log.error("Failed to get archived runs: %s", e)
            return []

    def get_archive_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics from the archive."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        COUNT(*) as total_runs,
                        SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_runs,
                        SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_runs,
                        SUM(total_cost_usd) as total_cost_usd,
                        SUM(total_input_tokens) as total_input_tokens,
                        SUM(total_output_tokens) as total_output_tokens,
                        SUM(steps_completed) as total_steps_completed,
                        SUM(steps_failed) as total_steps_failed
                    FROM archived_runs
                """)
                row = cursor.fetchone()

                return {
                    "total_runs": row[0] or 0,
                    "completed_runs": row[1] or 0,
                    "failed_runs": row[2] or 0,
                    "total_cost_usd": row[3] or 0.0,
                    "total_input_tokens": row[4] or 0,
                    "total_output_tokens": row[5] or 0,
                    "total_steps_completed": row[6] or 0,
                    "total_steps_failed": row[7] or 0,
                }

        except sqlite3.Error as e:
            self._log.error("Failed to get archive stats: %s", e)
            return {
                "total_runs": 0,
                "completed_runs": 0,
                "failed_runs": 0,
                "total_cost_usd": 0.0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_steps_completed": 0,
                "total_steps_failed": 0,
            }

    def is_archived(self, run_id: str) -> bool:
        """Check if a run is already archived."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM archived_runs WHERE run_id = ?", (run_id,))
                return cursor.fetchone() is not None
        except sqlite3.Error:
            return False


def extract_run_metadata(run_dir: Path, daily_stats_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Extract metadata from a run directory for archiving.

    Args:
        run_dir: Path to the run directory
        daily_stats_dir: Optional path to daily stats directory for cost lookup

    Returns:
        Dictionary with run metadata suitable for archiving
    """
    run_id = run_dir.name
    metadata: Dict[str, Any] = {
        "run_id": run_id,
        "workflow_name": "unknown",
        "status": "UNKNOWN",
        "created_at": utc_now(),
        "ended_at": None,
        "total_cost_usd": 0.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "steps_completed": 0,
        "steps_failed": 0,
        "work_summary": "",
    }

    # Read run_state.json
    state_file = run_dir / "run_state.json"
    if state_file.exists():
        try:
            with state_file.open("r", encoding="utf-8") as f:
                state_data = json.load(f)

            metadata["workflow_name"] = state_data.get("workflow_name", "unknown")
            metadata["created_at"] = state_data.get("created_at", metadata["created_at"])
            metadata["ended_at"] = state_data.get("updated_at")

            # Count steps and determine status
            steps = state_data.get("steps", {})
            completed_steps = []
            failed_steps = []

            for step_id, step_runtime in steps.items():
                step_status = step_runtime.get("status", "")
                if step_status == "COMPLETED":
                    metadata["steps_completed"] += 1
                    completed_steps.append(step_id)
                elif step_status == "FAILED":
                    metadata["steps_failed"] += 1
                    failed_steps.append(step_id)

                # Aggregate metrics if available
                metrics = step_runtime.get("metrics", {})
                if metrics:
                    metadata["total_input_tokens"] += metrics.get("input_tokens", 0)
                    metadata["total_output_tokens"] += metrics.get("output_tokens", 0)
                    metadata["total_cost_usd"] += metrics.get("cost_usd", 0.0)

            # Determine overall status
            if metadata["steps_failed"] > 0:
                metadata["status"] = "FAILED"
            elif metadata["steps_completed"] > 0:
                metadata["status"] = "COMPLETED"
            else:
                metadata["status"] = "UNKNOWN"

            # Generate work summary
            summary_parts = []
            if completed_steps:
                summary_parts.append(f"Completed: {', '.join(completed_steps[:5])}")
                if len(completed_steps) > 5:
                    summary_parts[-1] += f" (+{len(completed_steps) - 5} more)"
            if failed_steps:
                summary_parts.append(f"Failed: {', '.join(failed_steps[:3])}")
            metadata["work_summary"] = "; ".join(summary_parts)

        except (json.JSONDecodeError, OSError) as e:
            _LOG.warning("Failed to parse run state at %s: %s", state_file, e)

    # Try to get cost from daily stats if not in run_state
    if daily_stats_dir and metadata["total_cost_usd"] == 0:
        # Look for run in daily stats files
        try:
            for stats_file in sorted(daily_stats_dir.glob("*.json"), reverse=True):
                try:
                    with stats_file.open("r", encoding="utf-8") as f:
                        stats_data = json.load(f)
                    runs = stats_data.get("runs", {})
                    if run_id in runs:
                        run_info = runs[run_id]
                        metadata["total_cost_usd"] = run_info.get("total_cost_usd", 0.0)
                        # Also get step counts if we don't have them
                        if metadata["steps_completed"] == 0:
                            metadata["steps_completed"] = run_info.get("steps_completed", 0)
                        if metadata["steps_failed"] == 0:
                            metadata["steps_failed"] = run_info.get("steps_failed", 0)
                        break
                except (json.JSONDecodeError, OSError):
                    continue
        except OSError:
            pass

    return metadata
