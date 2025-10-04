import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from agent_orchestrator.cli import run_from_args
from agent_orchestrator.git_worktree import GitWorktreeManager, persist_worktree_outputs


class GitWorktreeManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.repo_dir = Path(self._tmp.name)
        self._run_git("init")
        self._run_git("config", "user.email", "agent@example.com")
        self._run_git("config", "user.name", "Agent Orchestrator")
        (self.repo_dir / "README.md").write_text("hello", encoding="utf-8")
        self._run_git("add", "README.md")
        self._run_git("commit", "-m", "initial commit")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_create_persist_and_remove_worktree(self) -> None:
        manager = GitWorktreeManager(self.repo_dir)
        handle = manager.create()

        self.assertTrue(handle.path.exists(), "worktree directory should exist")
        self.assertTrue(handle.branch.startswith("agents/run-"))

        artifact_dir = handle.path / ".agents" / "runs" / handle.run_id / "reports"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        sample_report = artifact_dir / "report.json"
        sample_report.write_text("{}", encoding="utf-8")

        destination = persist_worktree_outputs(handle.path, manager.repo_root, handle.run_id)
        copied_report = destination / "reports" / "report.json"
        self.assertTrue(copied_report.exists(), "artifacts should be copied to primary repo")

        manager.remove(handle)
        self.assertFalse(handle.path.exists(), "worktree directory should be removed")

        branches = self._run_git("branch").stdout
        self.assertNotIn(handle.branch, branches)


class GitWorktreeCleanupTests(unittest.TestCase):
    def test_cli_cleanup_handles_shutil_error(self) -> None:
        with TemporaryDirectory() as tmp_repo:
            repo_path = Path(tmp_repo)
            workflow_path = repo_path / "workflow.yaml"
            workflow_path.write_text("name: workflow\n", encoding="utf-8")
            expected_workflow_path = workflow_path.resolve()

            args = SimpleNamespace(
                repo=str(repo_path),
                workflow=str(workflow_path),
                schema=None,
                git_worktree=True,
                git_worktree_root=None,
                git_worktree_ref=None,
                git_worktree_branch=None,
                git_worktree_keep=False,
                workdir=None,
                gate_state_file=None,
                logs_dir=None,
                env=None,
                wrapper=None,
                command_template=None,
                wrapper_arg=[],
                issue_number=None,
                start_at_step=None,
                poll_interval=0.01,
                max_attempts=1,
                max_iterations=1,
                pause_for_human_input=False,
            )

            handle = SimpleNamespace(
                path=repo_path / "worktree",
                branch="agents/run-test",
                root_repo=repo_path,
                run_id="test-run",
            )
            handle.path.mkdir(parents=True, exist_ok=True)

            workflow = mock.MagicMock()
            workflow.name = "workflow"
            workflow.steps = {}

            runner = mock.MagicMock()

            with (
                mock.patch("agent_orchestrator.cli.load_workflow", return_value=workflow) as load_workflow,
                mock.patch("agent_orchestrator.cli.build_runner", return_value=runner) as build_runner,
                mock.patch("agent_orchestrator.cli.Orchestrator") as orchestrator_cls,
                mock.patch("agent_orchestrator.cli.GitWorktreeManager") as manager_cls,
                mock.patch(
                    "agent_orchestrator.cli.persist_worktree_outputs",
                    side_effect=shutil.Error("copy failed"),
                ) as persist_outputs,
            ):

                orchestrator_instance = mock.MagicMock()
                orchestrator_instance.run_id = "orchestrator-run"
                orchestrator_cls.return_value = orchestrator_instance

                manager_instance = mock.MagicMock()
                manager_instance.repo_root = repo_path
                manager_instance.create.return_value = handle
                manager_cls.return_value = manager_instance

                run_from_args(args)

                load_workflow.assert_called_once_with(expected_workflow_path)
                build_runner.assert_called_once()
                orchestrator_instance.run.assert_called_once()
                persist_outputs.assert_called_once()
                manager_instance.remove.assert_called_once_with(handle)


if __name__ == "__main__":
    unittest.main()
