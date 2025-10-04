from __future__ import annotations

import json
from pathlib import Path

from .models import Step


class GateEvaluator:
    """Check whether workflow gates are open before launching a step."""

    def evaluate(self, step: Step, gate: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class AlwaysOpenGateEvaluator(GateEvaluator):
    def evaluate(self, step: Step, gate: str) -> bool:
        return True


class FileBackedGateEvaluator(GateEvaluator):
    """Read gate states from a JSON file updated by external systems."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def evaluate(self, step: Step, gate: str) -> bool:
        states = self._load_states()
        return states.get(gate, False)

    def _load_states(self) -> dict[str, bool]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as f:
            try:
                payload = json.load(f)
            except json.JSONDecodeError:
                return {}
        return {str(key): bool(value) for key, value in payload.items()}


class CompositeGateEvaluator(GateEvaluator):
    """Delegate to multiple evaluators until one returns False."""

    def __init__(self, *evaluators: GateEvaluator) -> None:
        self._evaluators = evaluators or (AlwaysOpenGateEvaluator(),)

    def evaluate(self, step: Step, gate: str) -> bool:
        for evaluator in self._evaluators:
            if not evaluator.evaluate(step, gate):
                return False
        return True

