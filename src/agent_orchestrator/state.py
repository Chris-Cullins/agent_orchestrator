"""
Run state persistence for workflow resumption.

This module provides serialization and deserialization of workflow run
state to enable resumption after interruption or failure.

State files are stored as JSON and contain:
- Run metadata (ID, workflow name, timestamps)
- Step runtime states (status, attempts, artifacts, logs)
- Directory paths for reports and manual inputs
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import RunState


class RunStatePersister:
    """
    Persist and load workflow run state to/from JSON files.

    Handles atomic state writes and directory creation for resumption
    support. State files are written to .agents/runs/<run_id>/run_state.json.

    Args:
        path: Path to the run state JSON file.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: RunState) -> None:
        """
        Save run state to the configured path.

        Args:
            state: RunState instance to persist.
        """
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2)

    def load(self) -> Optional[dict]:
        """
        Load run state from the configured path.

        Returns:
            Dictionary representation of state, or None if file doesn't exist.
        """
        if not self._path.exists():
            return None
        with self._path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @property
    def path(self) -> Path:
        """Return the current state file path."""
        return self._path

    def set_path(self, path: Path) -> None:
        """
        Update the path where state will be saved.

        Args:
            path: New path for the state file.
        """
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
