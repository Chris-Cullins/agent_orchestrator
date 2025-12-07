import json
import shutil
import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from agent_orchestrator.cli import run_from_args
from agent_orchestrator.git_worktree import (
    GitWorktreeManager,
    persist_worktree_outputs,
    consolidate_worktree_daily_stats,
)


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
                skip_cleanup=True,
                poll_interval=0.01,
                max_attempts=1,
                max_iterations=1,
                pause_for_human_input=False,
                daily_cost_limit=None,
                cost_limit_action="warn",
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


class ConsolidateWorktreeDailyStatsTests(unittest.TestCase):
    """Tests for consolidate_worktree_daily_stats function."""

    def test_consolidate_worktree_stats_merges_into_main_repo(self) -> None:
        """Test that worktree stats are correctly merged into main repo stats."""
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            main_repo = tmp_path / "main"
            worktree = tmp_path / "worktree"

            main_repo.mkdir()
            worktree.mkdir()

            # Create worktree daily stats
            today = datetime.now(timezone.utc).date().isoformat()
            wt_stats_dir = worktree / ".agents" / "daily_stats"
            wt_stats_dir.mkdir(parents=True)

            worktree_data = {
                "date": today,
                "total_runs": 1,
                "completed_runs": 1,
                "failed_runs": 0,
                "total_steps": 2,
                "completed_steps": 2,
                "failed_steps": 0,
                "total_input_tokens": 5000,
                "total_output_tokens": 2000,
                "total_cost_usd": 1.50,
                "total_duration_ms": 10000,
                "cost_by_model": {"opus": 1.50},
                "tokens_by_model": {"opus": {"input": 5000, "output": 2000}},
                "runs": {
                    "run-wt-123": {
                        "workflow_name": "worktree_workflow",
                        "status": "COMPLETED",
                        "total_cost_usd": 1.50,
                        "steps_completed": 2,
                        "steps_failed": 0,
                    }
                },
                "steps": [
                    {
                        "run_id": "run-wt-123",
                        "step_id": "step-1",
                        "agent": "coding",
                        "model": "opus",
                        "input_tokens": 3000,
                        "output_tokens": 1000,
                        "cost_usd": 0.80,
                        "duration_ms": 5000,
                        "status": "COMPLETED",
                        "timestamp": "2024-01-15T10:00:00Z",
                    },
                    {
                        "run_id": "run-wt-123",
                        "step_id": "step-2",
                        "agent": "review",
                        "model": "opus",
                        "input_tokens": 2000,
                        "output_tokens": 1000,
                        "cost_usd": 0.70,
                        "duration_ms": 5000,
                        "status": "COMPLETED",
                        "timestamp": "2024-01-15T10:01:00Z",
                    },
                ],
            }
            (wt_stats_dir / f"{today}.json").write_text(
                json.dumps(worktree_data), encoding="utf-8"
            )

            # Consolidate into main repo
            result = consolidate_worktree_daily_stats(worktree, main_repo)

            self.assertTrue(result, "Should return True when stats are consolidated")

            # Verify main repo has the stats
            main_stats_file = main_repo / ".agents" / "daily_stats" / f"{today}.json"
            self.assertTrue(main_stats_file.exists(), "Main repo should have stats file")

            main_data = json.loads(main_stats_file.read_text())
            self.assertEqual(main_data["total_runs"], 1)
            self.assertIn("run-wt-123", main_data["runs"])
            self.assertEqual(len(main_data["steps"]), 2)

    def test_consolidate_returns_false_when_no_stats_dir(self) -> None:
        """Test that consolidation returns False when worktree has no stats."""
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            main_repo = tmp_path / "main"
            worktree = tmp_path / "worktree"

            main_repo.mkdir()
            worktree.mkdir()

            # No stats dir in worktree
            result = consolidate_worktree_daily_stats(worktree, main_repo)

            self.assertFalse(result, "Should return False when no stats directory")

    def test_consolidate_returns_false_when_no_today_stats(self) -> None:
        """Test that consolidation returns False when no stats for today."""
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            main_repo = tmp_path / "main"
            worktree = tmp_path / "worktree"

            main_repo.mkdir()
            worktree.mkdir()

            # Create stats dir but with old stats file
            wt_stats_dir = worktree / ".agents" / "daily_stats"
            wt_stats_dir.mkdir(parents=True)
            (wt_stats_dir / "2020-01-01.json").write_text("{}", encoding="utf-8")

            result = consolidate_worktree_daily_stats(worktree, main_repo)

            self.assertFalse(result, "Should return False when no stats for today")


class PersistWorktreeOutputsWithStatsTests(unittest.TestCase):
    """Tests for persist_worktree_outputs including stats consolidation."""

    def test_persist_outputs_also_consolidates_stats(self) -> None:
        """Test that persist_worktree_outputs consolidates daily stats."""
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            main_repo = tmp_path / "main"
            worktree = tmp_path / "worktree"
            run_id = "test-run-123"

            main_repo.mkdir()
            worktree.mkdir()

            # Create run artifacts in worktree
            run_dir = worktree / ".agents" / "runs" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "report.json").write_text("{}", encoding="utf-8")

            # Create worktree daily stats
            today = datetime.now(timezone.utc).date().isoformat()
            wt_stats_dir = worktree / ".agents" / "daily_stats"
            wt_stats_dir.mkdir(parents=True)

            worktree_stats = {
                "date": today,
                "total_runs": 1,
                "completed_runs": 1,
                "runs": {
                    run_id: {
                        "workflow_name": "test",
                        "status": "COMPLETED",
                        "total_cost_usd": 0.50,
                    }
                },
                "steps": [
                    {
                        "run_id": run_id,
                        "step_id": "step-1",
                        "agent": "test",
                        "model": "opus",
                        "input_tokens": 1000,
                        "output_tokens": 500,
                        "cost_usd": 0.50,
                        "duration_ms": 1000,
                        "status": "COMPLETED",
                        "timestamp": "2024-01-15T10:00:00Z",
                    }
                ],
            }
            (wt_stats_dir / f"{today}.json").write_text(
                json.dumps(worktree_stats), encoding="utf-8"
            )

            # Persist outputs
            persist_worktree_outputs(worktree, main_repo, run_id)

            # Verify run artifacts were copied
            copied_report = main_repo / ".agents" / "runs" / run_id / "report.json"
            self.assertTrue(copied_report.exists(), "Run artifacts should be copied")

            # Verify stats were consolidated
            main_stats_file = main_repo / ".agents" / "daily_stats" / f"{today}.json"
            self.assertTrue(main_stats_file.exists(), "Stats should be consolidated")

            main_data = json.loads(main_stats_file.read_text())
            self.assertIn(run_id, main_data["runs"])


if __name__ == "__main__":
    unittest.main()
