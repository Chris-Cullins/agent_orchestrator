"""Gate evaluation for conditional workflow step execution.

This module provides gate evaluators that control when workflow steps
are allowed to execute. Gates enable external systems to pause or block
step execution until certain conditions are met.

Implementations:
    - AlwaysOpenGateEvaluator: Allows all steps (default)
    - FileBackedGateEvaluator: Reads gate state from a JSON file
    - CompositeGateEvaluator: Combines multiple evaluators (AND logic)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .models import Step


class GateEvaluator:
    """Abstract base class for step gate evaluation.

    Gate evaluators determine whether a step is allowed to execute based on
    its declared gates. Each gate is a named condition that must evaluate
    to True for the step to proceed.
    """

    def evaluate(self, step: Step, gate: str) -> bool:  # pragma: no cover - interface
        """Evaluate whether a gate is open for a step.

        Args:
            step: The step attempting to execute.
            gate: Name of the gate to evaluate.

        Returns:
            True if the gate is open and step can proceed, False otherwise.
        """
        raise NotImplementedError


class AlwaysOpenGateEvaluator(GateEvaluator):
    """Gate evaluator that always returns True (all gates open)."""

    def evaluate(self, step: Step, gate: str) -> bool:
        """Return True for all gates, allowing all steps to proceed."""
        return True


class FileBackedGateEvaluator(GateEvaluator):
    """Gate evaluator that reads state from a JSON file.

    The JSON file should contain a mapping of gate names to boolean values.
    Gates not present in the file are treated as closed (False).
    """

    def __init__(self, path: Path) -> None:
        """Initialize with path to gate state JSON file.

        Args:
            path: Path to JSON file mapping gate names to booleans.
        """
        self._path = path

    def evaluate(self, step: Step, gate: str) -> bool:
        """Check if gate is open according to the state file.

        Args:
            step: The step attempting to execute.
            gate: Name of the gate to evaluate.

        Returns:
            True if gate is present and True in file, False otherwise.
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
    """Gate evaluator that combines multiple evaluators with AND logic.

    All child evaluators must return True for a gate to be considered open.
    """

    def __init__(self, *evaluators: GateEvaluator) -> None:
        """Initialize with one or more child evaluators.

        Args:
            evaluators: GateEvaluator instances to combine. Defaults to
                AlwaysOpenGateEvaluator if none provided.
        """
        self._evaluators = evaluators or (AlwaysOpenGateEvaluator(),)

    def evaluate(self, step: Step, gate: str) -> bool:
        """Check if gate is open according to all child evaluators.

        Args:
            step: The step attempting to execute.
            gate: Name of the gate to evaluate.

        Returns:
            True only if all child evaluators return True.
        """
        for evaluator in self._evaluators:
            if not evaluator.evaluate(step, gate):
                return False
        return True

