"""Tests for workflow loading with loop_back_to field."""
from pathlib import Path

import pytest
import yaml

from agent_orchestrator.workflow import load_workflow, WorkflowLoadError


def test_workflow_with_valid_loop_back_to(tmp_path: Path):
    """Test loading a workflow with valid loop_back_to field."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with loop-back",
        "steps": [
            {
                "id": "step_a",
                "agent": "coder",
                "prompt": "prompts/code.md",
                "needs": [],
            },
            {
                "id": "step_b",
                "agent": "reviewer",
                "prompt": "prompts/review.md",
                "needs": ["step_a"],
                "loop_back_to": "step_a",
            },
        ],
    }
    
    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)
    
    workflow = load_workflow(workflow_file)
    
    assert workflow.name == "test_workflow"
    assert "step_a" in workflow.steps
    assert "step_b" in workflow.steps
    assert workflow.steps["step_b"].loop_back_to == "step_a"
    assert workflow.steps["step_a"].loop_back_to is None


def test_workflow_with_invalid_loop_back_to(tmp_path: Path):
    """Test that invalid loop_back_to raises WorkflowLoadError."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow with invalid loop-back",
        "steps": [
            {
                "id": "step_a",
                "agent": "coder",
                "prompt": "prompts/code.md",
                "needs": [],
            },
            {
                "id": "step_b",
                "agent": "reviewer",
                "prompt": "prompts/review.md",
                "needs": ["step_a"],
                "loop_back_to": "nonexistent_step",
            },
        ],
    }
    
    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)
    
    with pytest.raises(WorkflowLoadError, match="unknown loop_back_to target"):
        load_workflow(workflow_file)


def test_workflow_without_loop_back_to(tmp_path: Path):
    """Test loading a workflow without loop_back_to field (backward compatibility)."""
    workflow_data = {
        "name": "test_workflow",
        "description": "Test workflow without loop-back",
        "steps": [
            {
                "id": "step_a",
                "agent": "coder",
                "prompt": "prompts/code.md",
                "needs": [],
            },
            {
                "id": "step_b",
                "agent": "reviewer",
                "prompt": "prompts/review.md",
                "needs": ["step_a"],
            },
        ],
    }
    
    workflow_file = tmp_path / "workflow.yaml"
    with workflow_file.open("w") as f:
        yaml.dump(workflow_data, f)
    
    workflow = load_workflow(workflow_file)
    
    assert workflow.steps["step_a"].loop_back_to is None
    assert workflow.steps["step_b"].loop_back_to is None
