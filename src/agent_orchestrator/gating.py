"""
Gate evaluation for conditional step execution.

This module provides gate evaluators that control whether workflow steps
can run based on external conditions (e.g., CI/CD status, manual approvals).

Gates are named conditions referenced by steps. A step only runs when all
its gates evaluate to open (True).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .models import Step


class GateEvaluator:
    """
    Abstract base class for workflow gate evaluation.

    Subclasses implement evaluate() to determine if a gate is open.
    """

    def evaluate(self, step: Step, gate: str) -> bool:  # pragma: no cover - interface
        """
        Evaluate whether a gate is open for a step.

        Args:
            step: The step requesting evaluation.
            gate: Name of the gate to evaluate.

        Returns:
            True if gate is open, False if blocked.
        """
        raise NotImplementedError


class AlwaysOpenGateEvaluator(GateEvaluator):
    """Gate evaluator that always returns True (all gates open)."""

    def evaluate(self, step: Step, gate: str) -> bool:
        """Always returns True, allowing the step to proceed."""
        return True


class FileBackedGateEvaluator(GateEvaluator):
    """
    Gate evaluator that reads state from a JSON file.

    Useful for integration with external systems (CI/CD, manual approvals)
    that update a shared gate state file.

    The JSON file should map gate names to boolean states:
    {"ci.tests: passed": true, "review: approved": false}

    Args:
        path: Path to the gate state JSON file.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def evaluate(self, step: Step, gate: str) -> bool:
        """
        Check gate state from file. Returns False if gate not found.

        Args:
            step: The step requesting evaluation.
            gate: Name of the gate to check.

        Returns:
            Boolean state of the gate, or False if not present.
        """
        states = self._load_states()
        return states.get(gate, False)

    def _load_states(self) -> Dict[str, bool]:
        """Load gate states from the JSON file."""
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as f:
            try:
                payload = json.load(f)
            except json.JSONDecodeError:
                return {}
        return {str(key): bool(value) for key, value in payload.items()}


class CompositeGateEvaluator(GateEvaluator):
    """
    Gate evaluator that delegates to multiple evaluators.

    Evaluates gates against all child evaluators. A gate is only open
    if ALL evaluators return True (logical AND).

    Args:
        *evaluators: Variable number of GateEvaluator instances.
    """

    def __init__(self, *evaluators: GateEvaluator) -> None:
        self._evaluators = evaluators or (AlwaysOpenGateEvaluator(),)

    def evaluate(self, step: Step, gate: str) -> bool:
        """
        Evaluate gate against all child evaluators.

        Args:
            step: The step requesting evaluation.
            gate: Name of the gate to evaluate.

        Returns:
            True only if all evaluators return True.
        """
        for evaluator in self._evaluators:
            if not evaluator.evaluate(step, gate):
                return False
        return True

