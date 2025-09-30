from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable

import yaml

from .models import Step, Workflow


class WorkflowLoadError(Exception):
    """Raised when a workflow file is invalid."""


def load_workflow(path: Path) -> Workflow:
    if not path.exists():
        raise WorkflowLoadError(f"Workflow file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}

    if "steps" not in payload or not isinstance(payload["steps"], Iterable):
        raise WorkflowLoadError("Workflow file must declare a 'steps' list")

    steps: Dict[str, Step] = {}
    for step_idx, raw_step in enumerate(payload["steps"], start=1):
        if not isinstance(raw_step, dict):
            raise WorkflowLoadError(f"Workflow step #{step_idx} must be a mapping")
        step_id = raw_step.get("id")
        if not step_id:
            raise WorkflowLoadError(f"Workflow step #{step_idx} is missing 'id'")
        if step_id in steps:
            raise WorkflowLoadError(f"Duplicate step id detected: {step_id}")
        prompt = raw_step.get("prompt")
        agent = raw_step.get("agent")
        if not prompt or not agent:
            raise WorkflowLoadError(f"Step '{step_id}' must declare both 'prompt' and 'agent'")

        step = Step(
            id=step_id,
            agent=agent,
            prompt=raw_step["prompt"],
            needs=list(raw_step.get("needs", [])),
            next_on_success=list(raw_step.get("next_on_success", [])),
            gates=list(raw_step.get("gates", [])),
            human_in_the_loop=bool(raw_step.get("human_in_the_loop", False)),
            metadata=dict(raw_step.get("metadata", {})),
        )
        steps[step_id] = step

    _validate_edges(steps)

    return Workflow(
        name=str(payload.get("name", "unnamed")),
        description=str(payload.get("description", "")),
        steps=steps,
    )


def _validate_edges(steps: Dict[str, Step]) -> None:
    for step in steps.values():
        for dep in step.needs:
            if dep not in steps:
                raise WorkflowLoadError(f"Step '{step.id}' has unknown dependency '{dep}'")
        for nxt in step.next_on_success:
            if nxt not in steps:
                raise WorkflowLoadError(f"Step '{step.id}' references unknown next step '{nxt}'")

