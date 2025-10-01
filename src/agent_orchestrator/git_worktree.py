from __future__ import annotations

import logging
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

__all__ = [
    "GitWorktreeError",
    "GitWorktreeHandle",
    "GitWorktreeManager",
    "persist_worktree_outputs",
]


class GitWorktreeError(RuntimeError):
    """Raised when git worktree operations fail."""


@dataclass
class GitWorktreeHandle:
    """Metadata about a managed git worktree."""

    root_repo: Path
    path: Path
    branch: str
    base_ref: str
    run_id: str
    created_branch: bool = True


class GitWorktreeManager:
    """Create and clean up git worktrees for orchestrator runs."""

    def __init__(self, repo_dir: Path, git_executable: str = "git") -> None:
        self._logger = logging.getLogger(__name__)
        self._git = git_executable
        self._repo_dir = self._resolve_repo_root(repo_dir)

    @property
    def repo_root(self) -> Path:
        return self._repo_dir

    def create(
        self,
        root: Optional[Path] = None,
        ref: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> GitWorktreeHandle:
        repo_root = self._repo_dir
        worktree_root = self._resolve_root_directory(root)
        run_id = uuid.uuid4().hex[:8]
        branch_name = branch or f"agents/run-{run_id}"
        worktree_path = (worktree_root / branch_name.replace("/", "__")).resolve()

        if worktree_path.exists():
            raise GitWorktreeError(f"Worktree path already exists: {worktree_path}")
        if self._branch_exists(branch_name):
            raise GitWorktreeError(f"Git branch '{branch_name}' already exists")

        base_ref = ref or "HEAD"
        self._run_git(
            "worktree",
            "add",
            "-b",
            branch_name,
            str(worktree_path),
            base_ref,
        )

        return GitWorktreeHandle(
            root_repo=repo_root,
            path=worktree_path,
            branch=branch_name,
            base_ref=base_ref,
            run_id=run_id,
            created_branch=True,
        )

    def remove(
        self,
        handle: GitWorktreeHandle,
        *,
        force: bool = True,
        delete_branch: bool = True,
    ) -> None:
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(handle.path))
        self._run_git(*args)

        if delete_branch and handle.created_branch:
            branch_args = ["branch", "-D" if force else "-d", handle.branch]
            try:
                self._run_git(*branch_args)
            except GitWorktreeError as exc:
                self._logger.warning("Failed to delete branch %s: %s", handle.branch, exc)

    def _branch_exists(self, branch: str) -> bool:
        result = subprocess.run(
            [self._git, "-C", str(self._repo_dir), "rev-parse", "--verify", "--quiet", branch],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _resolve_root_directory(self, root: Optional[Path]) -> Path:
        if root is None:
            return (self._repo_dir / ".agents" / "worktrees").resolve()
        candidate = root.expanduser()
        if not candidate.is_absolute():
            candidate = (self._repo_dir / candidate).resolve()
        return candidate

    def _resolve_repo_root(self, repo_dir: Path) -> Path:
        repo_dir = repo_dir.expanduser().resolve()
        try:
            result = subprocess.run(
                [self._git, "-C", str(repo_dir), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else "unknown error"
            raise GitWorktreeError(f"{repo_dir} is not a git repository: {stderr}") from exc
        return Path(result.stdout.strip()).resolve()

    def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self._git, "-C", str(self._repo_dir), *args],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            stdout = exc.stdout.strip() if exc.stdout else ""
            details = stderr or stdout or str(exc)
            raise GitWorktreeError(f"git {' '.join(args)} failed: {details}") from exc


def persist_worktree_outputs(worktree_path: Path, repo_root: Path, run_id: str) -> Path:
    """Copy worktree .agents artifacts into the primary repository."""

    source_dir = worktree_path / ".agents"
    destination_root = repo_root.expanduser().resolve() / ".agents" / "runs"
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / run_id
    if not source_dir.exists():
        return destination
    shutil.copytree(source_dir, destination, dirs_exist_ok=True)
    return destination
