import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_orchestrator.models import Step, Workflow
from agent_orchestrator.orchestrator import Orchestrator
from agent_orchestrator.reporting import RunReportReader
from agent_orchestrator.runner import ExecutionTemplate, StepRunner
from agent_orchestrator.state import RunStatePersister


class PromptResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.repo_dir = Path(self._tmp.name) / "repo"
        self.repo_dir.mkdir()

        self.workflow_root = Path(self._tmp.name) / "workflows"
        self.workflow_root.mkdir()

        # Create default prompt in workflow directory
        self.default_prompt = self.workflow_root / "test_prompt.md"
        self.default_prompt.write_text("# Default Prompt\nThis is the default prompt.", encoding="utf-8")

        # Create simple workflow
        self.workflow = Workflow(
            name="test",
            description="test workflow",
            steps={
                "step1": Step(
                    id="step1",
                    agent="test_agent",
                    prompt="test_prompt.md",
                )
            },
        )

        # Setup orchestrator components
        self.state_file = Path(self._tmp.name) / "state.json"
        self.runner = StepRunner(
            execution_template=ExecutionTemplate("echo test"),
            repo_dir=self.repo_dir,
            logs_dir=Path(self._tmp.name) / "logs",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_uses_default_prompt_when_no_override_exists(self) -> None:
        orchestrator = Orchestrator(
            workflow=self.workflow,
            workflow_root=self.workflow_root,
            repo_dir=self.repo_dir,
            report_reader=RunReportReader(),
            state_persister=RunStatePersister(self.state_file),
            runner=self.runner,
            logger=logging.getLogger(__name__),
        )

        resolved = orchestrator._resolve_prompt_path("test_prompt.md")
        self.assertEqual(resolved, self.default_prompt)

    def test_uses_local_override_when_exists(self) -> None:
        # Create local override
        override_dir = self.repo_dir / ".agents" / "prompts"
        override_dir.mkdir(parents=True)
        override_prompt = override_dir / "test_prompt.md"
        override_prompt.write_text("# Override Prompt\nThis is the override prompt.", encoding="utf-8")

        orchestrator = Orchestrator(
            workflow=self.workflow,
            workflow_root=self.workflow_root,
            repo_dir=self.repo_dir,
            report_reader=RunReportReader(),
            state_persister=RunStatePersister(self.state_file),
            runner=self.runner,
            logger=logging.getLogger(__name__),
        )

        resolved = orchestrator._resolve_prompt_path("test_prompt.md")
        self.assertEqual(resolved, override_prompt)

    def test_uses_local_override_with_subdirectory_prompt_path(self) -> None:
        # Create default prompt in subdirectory
        subdir = self.workflow_root / "prompts"
        subdir.mkdir()
        default_prompt = subdir / "nested_prompt.md"
        default_prompt.write_text("# Default Nested Prompt", encoding="utf-8")

        # Create local override (only filename, no subdirectory)
        override_dir = self.repo_dir / ".agents" / "prompts"
        override_dir.mkdir(parents=True)
        override_prompt = override_dir / "nested_prompt.md"
        override_prompt.write_text("# Override Nested Prompt", encoding="utf-8")

        orchestrator = Orchestrator(
            workflow=self.workflow,
            workflow_root=self.workflow_root,
            repo_dir=self.repo_dir,
            report_reader=RunReportReader(),
            state_persister=RunStatePersister(self.state_file),
            runner=self.runner,
            logger=logging.getLogger(__name__),
        )

        resolved = orchestrator._resolve_prompt_path("prompts/nested_prompt.md")
        self.assertEqual(resolved, override_prompt)

    def test_uses_absolute_path_when_provided(self) -> None:
        # Create absolute path prompt
        abs_prompt = Path(self._tmp.name) / "absolute_prompt.md"
        abs_prompt.write_text("# Absolute Prompt", encoding="utf-8")

        orchestrator = Orchestrator(
            workflow=self.workflow,
            workflow_root=self.workflow_root,
            repo_dir=self.repo_dir,
            report_reader=RunReportReader(),
            state_persister=RunStatePersister(self.state_file),
            runner=self.runner,
            logger=logging.getLogger(__name__),
        )

        resolved = orchestrator._resolve_prompt_path(str(abs_prompt))
        self.assertEqual(resolved, abs_prompt)

    def test_raises_error_when_prompt_not_found(self) -> None:
        orchestrator = Orchestrator(
            workflow=self.workflow,
            workflow_root=self.workflow_root,
            repo_dir=self.repo_dir,
            report_reader=RunReportReader(),
            state_persister=RunStatePersister(self.state_file),
            runner=self.runner,
            logger=logging.getLogger(__name__),
        )

        with self.assertRaises(FileNotFoundError) as ctx:
            orchestrator._resolve_prompt_path("nonexistent.md")

        self.assertIn("Prompt file not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
