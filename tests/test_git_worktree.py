import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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

        artifact_dir = handle.path / ".agents" / "run_reports"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        sample_report = artifact_dir / "report.json"
        sample_report.write_text("{}", encoding="utf-8")

        destination = persist_worktree_outputs(handle.path, manager.repo_root, handle.run_id)
        copied_report = destination / "run_reports" / "report.json"
        self.assertTrue(copied_report.exists(), "artifacts should be copied to primary repo")

        manager.remove(handle)
        self.assertFalse(handle.path.exists(), "worktree directory should be removed")

        branches = self._run_git("branch").stdout
        self.assertNotIn(handle.branch, branches)


if __name__ == "__main__":
    unittest.main()
