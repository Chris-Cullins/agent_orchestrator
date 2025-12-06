"""Workflow loading and validation from YAML files.

This module provides functions for loading workflow definitions from YAML,
validating their structure, and ensuring all step references are valid.

The workflow YAML format includes:
    - name: Workflow name
    - description: Brief description
    - steps: List of step definitions

Each step must define:
    - id: Unique step identifier
    - agent: Agent type to execute
    - prompt: Path to prompt file
    - needs: (optional) List of dependency step IDs
    - loop: (optional) Loop configuration for iteration
    - loop_back_to: (optional) Target step for gate failure loop-back
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from .models import LoopConfig, Step, Workflow


class WorkflowLoadError(Exception):
    """Raised when a workflow file cannot be loaded or is invalid.

    This exception is raised for:
        - Missing workflow files
        - Invalid YAML syntax
        - Missing required fields (id, agent, prompt)
        - Invalid step references (unknown dependencies, loop targets)
        - Invalid loop configurations
    """


def _parse_loop_config(loop_data: Any, step_id: str) -> LoopConfig:
    """Parse loop configuration from YAML data.

    Args:
        loop_data: Raw loop configuration from YAML.
        step_id: Step ID for error messages.

    Returns:
        Validated LoopConfig instance.

    Raises:
        WorkflowLoadError: If loop configuration is invalid.
    """
    if not isinstance(loop_data, dict):
        raise WorkflowLoadError(f"Step '{step_id}' has invalid loop config - must be a mapping")

    items = loop_data.get("items")
    items_from_step = loop_data.get("items_from_step")
    items_from_artifact = loop_data.get("items_from_artifact")

    # Validate that exactly one source is specified
    sources = [items, items_from_step, items_from_artifact]
    non_null_sources = [s for s in sources if s is not None]
    if len(non_null_sources) != 1:
        raise WorkflowLoadError(
            f"Step '{step_id}' loop config must specify exactly one of: "
            f"items, items_from_step, or items_from_artifact"
        )

    # Validate items is a list if provided
    if items is not None and not isinstance(items, list):
        raise WorkflowLoadError(f"Step '{step_id}' loop config 'items' must be a list")

    return LoopConfig(
        items=items,
        items_from_step=items_from_step,
        items_from_artifact=items_from_artifact,
        max_iterations=loop_data.get("max_iterations"),
        until_condition=loop_data.get("until_condition"),
        item_var=loop_data.get("item_var", "item"),
        index_var=loop_data.get("index_var", "index"),
    )


def load_workflow(path: Path) -> Workflow:
    """Load a workflow definition from a YAML file.

    Parses the workflow YAML, constructs Step objects for each defined step,
    and validates all step references (dependencies, loop targets).

    Args:
        path: Path to the workflow YAML file.

    Returns:
        Validated Workflow instance ready for execution.

    Raises:
        WorkflowLoadError: If the file is missing, malformed, or contains
            invalid step references.
    """
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

        # Parse loop configuration if present
        loop_config = None
        if "loop" in raw_step:
            loop_config = _parse_loop_config(raw_step["loop"], step_id)

        step = Step(
            id=step_id,
            agent=agent,
            prompt=raw_step["prompt"],
            needs=list(raw_step.get("needs", [])),
            next_on_success=list(raw_step.get("next_on_success", [])),
            gates=list(raw_step.get("gates", [])),
            loop_back_to=raw_step.get("loop_back_to"),
            human_in_the_loop=bool(raw_step.get("human_in_the_loop", False)),
            metadata=dict(raw_step.get("metadata", {})),
            loop=loop_config,
            model=raw_step.get("model"),  # Optional model override for this step
        )
        steps[step_id] = step

    _validate_edges(steps)

    return Workflow(
        name=str(payload.get("name", "unnamed")),
        description=str(payload.get("description", "")),
        steps=steps,
    )


def _validate_edges(steps: Dict[str, Step]) -> None:
    """Validate all step references point to existing steps.

    Checks that all step dependencies, next_on_success references,
    loop_back_to targets, and loop items_from_step references are valid.

    Args:
        steps: Dictionary mapping step IDs to Step definitions.

    Raises:
        WorkflowLoadError: If any step reference is invalid.
    """
    for step in steps.values():
        for dep in step.needs:
            if dep not in steps:
                raise WorkflowLoadError(f"Step '{step.id}' has unknown dependency '{dep}'")
        for nxt in step.next_on_success:
            if nxt not in steps:
                raise WorkflowLoadError(f"Step '{step.id}' references unknown next step '{nxt}'")
        if step.loop_back_to and step.loop_back_to not in steps:
            raise WorkflowLoadError(f"Step '{step.id}' has unknown loop_back_to target '{step.loop_back_to}'")
        if step.loop and step.loop.items_from_step:
            if step.loop.items_from_step not in steps:
                raise WorkflowLoadError(
                    f"Step '{step.id}' loop references unknown step '{step.loop.items_from_step}'"
                )
            if step.loop.items_from_step not in step.needs:
                raise WorkflowLoadError(
                    f"Step '{step.id}' loop references step '{step.loop.items_from_step}' "
                    f"which is not in its needs list"
                )

