"""Tests for tiered model routing feature."""

import os
import tempfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_orchestrator.models import Step
from agent_orchestrator.workflow import load_workflow
from agent_orchestrator.runner import ExecutionTemplate, StepRunner
from agent_orchestrator.wrappers.claude_wrapper import get_model as claude_get_model


class TestStepModelField:
    """Tests for the model field on Step."""

    def test_step_model_defaults_to_none(self):
        step = Step(id="test", agent="coding", prompt="test.md")
        assert step.model is None

    def test_step_model_can_be_set(self):
        step = Step(id="test", agent="coding", prompt="test.md", model="haiku")
        assert step.model == "haiku"


class TestWorkflowModelParsing:
    """Tests for parsing model from workflow YAML."""

    def test_workflow_parses_model_from_step(self, tmp_path):
        workflow_content = """
name: test_workflow
description: Test workflow with model routing
steps:
  - id: planning
    agent: dev_architect
    prompt: prompts/planning.md
    model: opus

  - id: coding
    agent: coding
    prompt: prompts/coding.md
    model: sonnet
    needs: [planning]

  - id: review
    agent: code_review
    prompt: prompts/review.md
    model: haiku
    needs: [coding]
"""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(workflow_content)

        # Create the prompt files so validation passes
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "planning.md").write_text("Plan the work")
        (prompts_dir / "coding.md").write_text("Write the code")
        (prompts_dir / "review.md").write_text("Review the code")

        workflow = load_workflow(workflow_file)

        assert workflow.steps["planning"].model == "opus"
        assert workflow.steps["coding"].model == "sonnet"
        assert workflow.steps["review"].model == "haiku"

    def test_workflow_model_is_optional(self, tmp_path):
        workflow_content = """
name: test_workflow
description: Test workflow without model specified
steps:
  - id: coding
    agent: coding
    prompt: prompts/coding.md
"""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(workflow_content)

        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "coding.md").write_text("Write the code")

        workflow = load_workflow(workflow_file)

        assert workflow.steps["coding"].model is None


class TestClaudeWrapperModelResolution:
    """Tests for Claude wrapper model resolution."""

    def test_get_model_uses_step_model_env_first(self):
        args = Namespace(model="sonnet")
        with patch.dict(os.environ, {"STEP_MODEL": "haiku"}):
            result = claude_get_model(args)
        assert result == "haiku"

    def test_get_model_uses_arg_when_no_env(self):
        args = Namespace(model="sonnet")
        # Ensure STEP_MODEL is not set
        env = os.environ.copy()
        env.pop("STEP_MODEL", None)
        with patch.dict(os.environ, env, clear=True):
            result = claude_get_model(args)
        assert result == "sonnet"

    def test_get_model_uses_default_when_nothing_set(self):
        args = Namespace(model=None)
        env = os.environ.copy()
        env.pop("STEP_MODEL", None)
        with patch.dict(os.environ, env, clear=True):
            result = claude_get_model(args)
        assert result == "opus"


class TestRunnerModelEnv:
    """Tests for runner passing STEP_MODEL environment variable."""

    def test_runner_sets_step_model_env_when_model_specified(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        step = Step(
            id="test_step",
            agent="coding",
            prompt="test.md",
            model="haiku",
        )

        template = ExecutionTemplate("echo {step_id}")
        runner = StepRunner(
            execution_template=template,
            repo_dir=tmp_path,
            logs_dir=logs_dir,
        )

        # Create a dummy prompt file
        prompt_path = tmp_path / "test.md"
        prompt_path.write_text("Test prompt")

        report_path = tmp_path / "report.json"

        launch = runner.launch(
            step=step,
            run_id="test-run",
            report_path=report_path,
            prompt_path=prompt_path,
        )

        # The process should have STEP_MODEL in its environment
        # We can't directly check the env of a running process easily,
        # but we can verify the launch succeeded
        assert launch.step_id == "test_step"

        # Clean up
        launch.process.wait()
        launch.close_log()

    def test_runner_does_not_set_step_model_when_not_specified(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        step = Step(
            id="test_step",
            agent="coding",
            prompt="test.md",
            # model is not set
        )

        template = ExecutionTemplate("echo {step_id}")
        runner = StepRunner(
            execution_template=template,
            repo_dir=tmp_path,
            logs_dir=logs_dir,
        )

        prompt_path = tmp_path / "test.md"
        prompt_path.write_text("Test prompt")

        report_path = tmp_path / "report.json"

        launch = runner.launch(
            step=step,
            run_id="test-run",
            report_path=report_path,
            prompt_path=prompt_path,
        )

        assert launch.step_id == "test_step"

        launch.process.wait()
        launch.close_log()


class TestRunnerModelEnvIntegration:
    """Integration test that verifies STEP_MODEL is actually passed to subprocess."""

    def test_step_model_is_passed_to_subprocess(self, tmp_path):
        """Verify that STEP_MODEL env var is actually set in the subprocess."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        step = Step(
            id="test_step",
            agent="coding",
            prompt="test.md",
            model="haiku",
        )

        # Use a command that outputs the STEP_MODEL env var
        template = ExecutionTemplate("sh -c 'echo STEP_MODEL=$STEP_MODEL'")
        runner = StepRunner(
            execution_template=template,
            repo_dir=tmp_path,
            logs_dir=logs_dir,
        )

        prompt_path = tmp_path / "test.md"
        prompt_path.write_text("Test prompt")
        report_path = tmp_path / "report.json"

        launch = runner.launch(
            step=step,
            run_id="test-run",
            report_path=report_path,
            prompt_path=prompt_path,
        )

        launch.process.wait()
        launch.close_log()

        # Read the log file to see what was output
        log_content = launch.log_path.read_text()
        assert "STEP_MODEL=haiku" in log_content
