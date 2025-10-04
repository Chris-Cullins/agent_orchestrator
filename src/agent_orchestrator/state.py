from __future__ import annotations

import json
from pathlib import Path

from .models import RunState


class RunStatePersister:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: RunState) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2)

    def load(self) -> dict | None:
        if not self._path.exists():
            return None
        with self._path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @property
    def path(self) -> Path:
        return self._path

    def set_path(self, path: Path) -> None:
        """Update the path where state will be saved."""
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
