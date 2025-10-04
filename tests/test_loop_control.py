"""Tests for loop control structure in workflows."""
from pathlib import Path

import pytest
import yaml

from agent_orchestrator.workflow import load_workflow, WorkflowLoadError
from agent_orchestrator.models import LoopConfig


def test_workflow_with_static_loop_items(tmp_path: Path):
    """Test loading a workflow with static loop items."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with static loop",
        "steps": [
            {
                "id": "process_items",
                "agent": "processor",
                "prompt": "prompts/process.md",
                "needs": [],
                "loop": {
                    "items": ["item1", "item2", "item3"],
                    "item_var": "current_item",
                    "index_var": "idx",
                },
            },
        ],
    }

    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)

    workflow = load_workflow(workflow_file)

    assert workflow.name == "test_workflow"
    assert "process_items" in workflow.steps
    step = workflow.steps["process_items"]
    assert step.loop is not None
    assert step.loop.items == ["item1", "item2", "item3"]
    assert step.loop.item_var == "current_item"
    assert step.loop.index_var == "idx"


def test_workflow_with_loop_from_step(tmp_path: Path):
    """Test loading a workflow with loop items from another step."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with loop from step",
        "steps": [
            {
                "id": "generate_items",
                "agent": "generator",
                "prompt": "prompts/generate.md",
                "needs": [],
            },
            {
                "id": "process_items",
                "agent": "processor",
                "prompt": "prompts/process.md",
                "needs": ["generate_items"],
                "loop": {
                    "items_from_step": "generate_items",
                },
            },
        ],
    }

    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)

    workflow = load_workflow(workflow_file)

    assert "process_items" in workflow.steps
    step = workflow.steps["process_items"]
    assert step.loop is not None
    assert step.loop.items_from_step == "generate_items"
    assert step.loop.items is None


def test_workflow_with_loop_from_artifact(tmp_path: Path):
    """Test loading a workflow with loop items from an artifact file."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with loop from artifact",
        "steps": [
            {
                "id": "process_items",
                "agent": "processor",
                "prompt": "prompts/process.md",
                "needs": [],
                "loop": {
                    "items_from_artifact": "artifacts/items.json",
                },
            },
        ],
    }

    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)

    workflow = load_workflow(workflow_file)

    assert "process_items" in workflow.steps
    step = workflow.steps["process_items"]
    assert step.loop is not None
    assert step.loop.items_from_artifact == "artifacts/items.json"


def test_workflow_with_loop_max_iterations(tmp_path: Path):
    """Test loading a workflow with max_iterations constraint."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with max iterations",
        "steps": [
            {
                "id": "process_items",
                "agent": "processor",
                "prompt": "prompts/process.md",
                "needs": [],
                "loop": {
                    "items": ["item1", "item2", "item3", "item4", "item5"],
                    "max_iterations": 3,
                },
            },
        ],
    }

    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)

    workflow = load_workflow(workflow_file)

    step = workflow.steps["process_items"]
    assert step.loop is not None
    assert step.loop.max_iterations == 3


def test_workflow_loop_missing_dependency(tmp_path: Path):
    """Test that loop referencing missing step raises error."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with invalid loop reference",
        "steps": [
            {
                "id": "process_items",
                "agent": "processor",
                "prompt": "prompts/process.md",
                "needs": [],
                "loop": {
                    "items_from_step": "nonexistent_step",
                },
            },
        ],
    }

    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)

    with pytest.raises(WorkflowLoadError, match="unknown step"):
        load_workflow(workflow_file)


def test_workflow_loop_not_in_needs(tmp_path: Path):
    """Test that loop step reference must be in needs list."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with loop step not in needs",
        "steps": [
            {
                "id": "generate_items",
                "agent": "generator",
                "prompt": "prompts/generate.md",
                "needs": [],
            },
            {
                "id": "process_items",
                "agent": "processor",
                "prompt": "prompts/process.md",
                "needs": [],  # Missing generate_items
                "loop": {
                    "items_from_step": "generate_items",
                },
            },
        ],
    }

    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)

    with pytest.raises(WorkflowLoadError, match="not in its needs list"):
        load_workflow(workflow_file)


def test_workflow_loop_multiple_sources_error(tmp_path: Path):
    """Test that specifying multiple loop sources raises error."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with multiple loop sources",
        "steps": [
            {
                "id": "process_items",
                "agent": "processor",
                "prompt": "prompts/process.md",
                "needs": [],
                "loop": {
                    "items": ["item1", "item2"],
                    "items_from_artifact": "artifacts/items.json",
                },
            },
        ],
    }

    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)

    with pytest.raises(WorkflowLoadError, match="exactly one of"):
        load_workflow(workflow_file)


def test_workflow_loop_no_source_error(tmp_path: Path):
    """Test that loop without any source raises error."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with no loop source",
        "steps": [
            {
                "id": "process_items",
                "agent": "processor",
                "prompt": "prompts/process.md",
                "needs": [],
                "loop": {
                    "item_var": "item",
                },
            },
        ],
    }

    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)

    with pytest.raises(WorkflowLoadError, match="exactly one of"):
        load_workflow(workflow_file)


def test_workflow_loop_invalid_items_type(tmp_path: Path):
    """Test that non-list items raises error."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with invalid items type",
        "steps": [
            {
                "id": "process_items",
                "agent": "processor",
                "prompt": "prompts/process.md",
                "needs": [],
                "loop": {
                    "items": "not a list",
                },
            },
        ],
    }

    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)

    with pytest.raises(WorkflowLoadError, match="must be a list"):
        load_workflow(workflow_file)


def test_loop_config_defaults():
    """Test LoopConfig default values."""
    config = LoopConfig(items=["a", "b", "c"])
    assert config.item_var == "item"
    assert config.index_var == "index"
    assert config.max_iterations is None
    assert config.until_condition is None
