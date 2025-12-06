"""Run state persistence for workflow resumability.

This module provides the RunStatePersister class for saving and loading
workflow execution state to/from JSON files. This enables:
    - Resuming interrupted workflow runs
    - Debugging failed runs by inspecting state
    - Monitoring run progress via state file
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import RunState


class RunStatePersister:
    """Persist workflow run state to a JSON file for resumability.

    The persister handles saving RunState to disk after each orchestrator
    iteration and loading it for run resumption. State files are written
    atomically to the configured path.

    Attributes:
        path: Current file path for state persistence.
    """

    def __init__(self, path: Path) -> None:
        """Initialize the persister with a file path.

        Args:
            path: Path where state JSON will be saved. Parent directories
                are created if they don't exist.
        """
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: RunState) -> None:
        """Save run state to the configured path.

        Args:
            state: RunState to serialize and persist.
        """
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2)

    def load(self) -> Optional[dict]:
        """Load run state from the configured path.

        Returns:
            Dictionary representation of RunState if file exists, None otherwise.
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
        """Update the path where state will be saved.

        Args:
            path: New file path for state persistence.
        """
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
