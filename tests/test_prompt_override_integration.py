"""
Integration test for prompt override feature.
Tests that .agents/prompts/ overrides work in a realistic workflow scenario.
"""
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_orchestrator.models import Step, Workflow
from agent_orchestrator.orchestrator import Orchestrator
from agent_orchestrator.reporting import RunReportReader
from agent_orchestrator.runner import ExecutionTemplate, StepRunner
from agent_orchestrator.state import RunStatePersister


class PromptOverrideIntegrationTest(unittest.TestCase):
    """Integration test for prompt override feature with a complete workflow setup."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

        # Setup repository directory (simulating a target repo)
        self.repo_dir = self.tmp_dir / "target_repo"
        self.repo_dir.mkdir()

        # Setup workflow directory (simulating orchestrator installation)
        self.workflow_root = self.tmp_dir / "orchestrator" / "workflows"
        self.workflow_root.mkdir(parents=True)

        # Create prompts directory alongside workflows
        self.default_prompts_dir = self.workflow_root.parent / "prompts"
        self.default_prompts_dir.mkdir()

        # Create default prompts
        self.planning_prompt = self.default_prompts_dir / "planning.md"
        self.planning_prompt.write_text(
            "# Planning Agent\nYou are a default planning agent.\n"
            "Create a development plan.",
            encoding="utf-8"
        )

        self.coding_prompt = self.default_prompts_dir / "coding.md"
        self.coding_prompt.write_text(
            "# Coding Agent\nYou are a default coding agent.\n"
            "Implement the code.",
            encoding="utf-8"
        )

        # Create a test workflow
        self.workflow = Workflow(
            name="test_workflow",
            description="Test workflow for prompt overrides",
            steps={
                "planning": Step(
                    id="planning",
                    agent="planner",
                    prompt="../prompts/planning.md",
                ),
                "coding": Step(
                    id="coding",
                    agent="coder",
                    prompt="../prompts/coding.md",
                    needs=["planning"],
                ),
            },
        )

        # Setup orchestrator
        self.state_file = self.tmp_dir / "state.json"
        self.runner = StepRunner(
            execution_template=ExecutionTemplate("echo test"),
            repo_dir=self.repo_dir,
            logs_dir=self.tmp_dir / "logs",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_workflow_uses_default_prompts_without_overrides(self) -> None:
        """Test that workflow uses default prompts when no overrides exist."""
        orchestrator = Orchestrator(
            workflow=self.workflow,
            workflow_root=self.workflow_root,
            repo_dir=self.repo_dir,
            report_reader=RunReportReader(),
            state_persister=RunStatePersister(self.state_file),
            runner=self.runner,
            logger=logging.getLogger(__name__),
        )

        # Resolve prompts for both steps
        planning_resolved = orchestrator._resolve_prompt_path("../prompts/planning.md")
        coding_resolved = orchestrator._resolve_prompt_path("../prompts/coding.md")

        # Should use default prompts
        self.assertEqual(planning_resolved, self.planning_prompt)
        self.assertEqual(coding_resolved, self.coding_prompt)

        # Verify content is from default prompts
        self.assertIn("default planning agent", planning_resolved.read_text())
        self.assertIn("default coding agent", coding_resolved.read_text())

    def test_workflow_uses_override_prompts_when_present(self) -> None:
        """Test that workflow uses override prompts from .agents/prompts/ when they exist."""
        # Create override prompts in target repo
        override_dir = self.repo_dir / ".agents" / "prompts"
        override_dir.mkdir(parents=True)

        override_planning = override_dir / "planning.md"
        override_planning.write_text(
            "# Custom Planning Agent\nYou are a CUSTOM planning agent for THIS repo.\n"
            "Follow project-specific guidelines.",
            encoding="utf-8"
        )

        override_coding = override_dir / "coding.md"
        override_coding.write_text(
            "# Custom Coding Agent\nYou are a CUSTOM coding agent for THIS repo.\n"
            "Use project-specific code style.",
            encoding="utf-8"
        )

        orchestrator = Orchestrator(
            workflow=self.workflow,
            workflow_root=self.workflow_root,
            repo_dir=self.repo_dir,
            report_reader=RunReportReader(),
            state_persister=RunStatePersister(self.state_file),
            runner=self.runner,
            logger=logging.getLogger(__name__),
        )

        # Resolve prompts for both steps
        planning_resolved = orchestrator._resolve_prompt_path("../prompts/planning.md")
        coding_resolved = orchestrator._resolve_prompt_path("../prompts/coding.md")

        # Should use override prompts
        self.assertEqual(planning_resolved, override_planning)
        self.assertEqual(coding_resolved, override_coding)

        # Verify content is from override prompts
        self.assertIn("CUSTOM planning agent", planning_resolved.read_text())
        self.assertIn("CUSTOM coding agent", coding_resolved.read_text())

    def test_workflow_uses_selective_overrides(self) -> None:
        """Test that workflow can use mix of default and override prompts."""
        # Create only one override prompt
        override_dir = self.repo_dir / ".agents" / "prompts"
        override_dir.mkdir(parents=True)

        override_planning = override_dir / "planning.md"
        override_planning.write_text(
            "# Custom Planning Agent\nOverride for planning only.",
            encoding="utf-8"
        )
        # Note: No override for coding.md

        orchestrator = Orchestrator(
            workflow=self.workflow,
            workflow_root=self.workflow_root,
            repo_dir=self.repo_dir,
            report_reader=RunReportReader(),
            state_persister=RunStatePersister(self.state_file),
            runner=self.runner,
            logger=logging.getLogger(__name__),
        )

        # Resolve prompts
        planning_resolved = orchestrator._resolve_prompt_path("../prompts/planning.md")
        coding_resolved = orchestrator._resolve_prompt_path("../prompts/coding.md")

        # Planning should use override, coding should use default
        self.assertEqual(planning_resolved, override_planning)
        self.assertEqual(coding_resolved, self.coding_prompt)

        self.assertIn("Override for planning only", planning_resolved.read_text())
        self.assertIn("default coding agent", coding_resolved.read_text())


if __name__ == "__main__":
    unittest.main()
