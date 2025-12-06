"""
Git worktree management for isolated workflow execution.

This module provides git worktree creation and cleanup for running
workflows in isolated branches. Each workflow run can execute in
its own worktree, allowing parallel runs and preventing conflicts.

Features:
- Automatic worktree creation with unique branches
- Secure branch name validation
- Artifact persistence back to the main repository
- Cleanup of worktrees and branches after completion
"""

from __future__ import annotations

import logging
import re
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
    """
    Metadata about a managed git worktree.

    Attributes:
        root_repo: Path to the primary repository.
        path: Path to the worktree directory.
        branch: Name of the branch created for this worktree.
        base_ref: Git ref the worktree was created from.
        run_id: Short unique identifier for this run.
        created_branch: True if the branch was created by the manager.
    """

    root_repo: Path
    path: Path
    branch: str
    base_ref: str
    run_id: str
    created_branch: bool = True


class GitWorktreeManager:
    """
    Create and clean up git worktrees for orchestrator runs.

    Manages the lifecycle of git worktrees used for isolated workflow
    execution. Each worktree gets its own branch for commits.

    Args:
        repo_dir: Path to the git repository (or any directory within).
        git_executable: Path to git binary. Defaults to "git".
    """

    def __init__(self, repo_dir: Path, git_executable: str = "git") -> None:
        self._logger = logging.getLogger(__name__)
        self._git = git_executable
        self._repo_dir = self._resolve_repo_root(repo_dir)

    def _validate_branch_name(self, branch: str) -> None:
        """
        Validate branch name to prevent shell injection.

        Args:
            branch: Branch name to validate.

        Raises:
            GitWorktreeError: If branch name contains invalid characters.
        """
        if not re.match(r'^[a-zA-Z0-9/_-]+$', branch):
            raise GitWorktreeError(f"Invalid branch name: {branch}")
        if '..' in branch or branch.startswith('-'):
            raise GitWorktreeError(f"Branch name contains forbidden patterns: {branch}")

    @property
    def repo_root(self) -> Path:
        """Return the resolved path to the repository root."""
        return self._repo_dir

    def create(
        self,
        root: Optional[Path] = None,
        ref: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> GitWorktreeHandle:
        """
        Create a new git worktree for isolated execution.

        Args:
            root: Parent directory for the worktree. Defaults to .agents/worktrees.
            ref: Git ref to base the worktree on. Defaults to HEAD.
            branch: Branch name to create. Defaults to agents/run-<run_id>.

        Returns:
            GitWorktreeHandle with metadata about the created worktree.

        Raises:
            GitWorktreeError: If worktree creation fails.
        """
        repo_root = self._repo_dir
        worktree_root = self._resolve_root_directory(root)
        run_id = uuid.uuid4().hex[:8]
        branch_name = branch or f"agents/run-{run_id}"

        # Validate branch name for security
        self._validate_branch_name(branch_name)

        worktree_path = (worktree_root / branch_name.replace("/", "__")).resolve()

        # Validate path is within allowed boundaries
        try:
            worktree_path.relative_to(repo_root.parent)
        except ValueError:
            raise GitWorktreeError(f"Worktree path outside repository parent: {worktree_path}")

        base_ref = ref or "HEAD"
        # Let git handle existence checks atomically to avoid race conditions
        try:
            self._run_git(
                "worktree",
                "add",
                "-b",
                branch_name,
                str(worktree_path),
                base_ref,
            )
        except GitWorktreeError as exc:
            if "already exists" in str(exc).lower():
                raise GitWorktreeError(f"Worktree or branch already exists: {branch_name}") from exc
            raise

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
        """
        Remove a git worktree and optionally its branch.

        Args:
            handle: Handle from a previous create() call.
            force: Force removal even with local changes. Defaults to True.
            delete_branch: Delete the associated branch. Defaults to True.

        Raises:
            GitWorktreeError: If worktree removal fails.
        """
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
        """Check if a branch exists in the repository."""
        result = subprocess.run(
            [self._git, "-C", str(self._repo_dir), "rev-parse", "--verify", "--quiet", branch],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _resolve_root_directory(self, root: Optional[Path]) -> Path:
        """Resolve the parent directory for worktrees."""
        if root is None:
            return (self._repo_dir / ".agents" / "worktrees").resolve()
        candidate = root.expanduser()
        if not candidate.is_absolute():
            candidate = (self._repo_dir / candidate).resolve()
        return candidate

    def _resolve_repo_root(self, repo_dir: Path) -> Path:
        """Resolve the git repository root from any path within it."""
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
        """Execute a git command in the repository context."""
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
    """
    Copy worktree .agents artifacts into the primary repository.

    Preserves run artifacts (reports, logs, state) by copying them from
    the worktree to the main repository before worktree deletion.

    Args:
        worktree_path: Path to the worktree directory.
        repo_root: Path to the primary repository.
        run_id: Run identifier used for directory naming.

    Returns:
        Path to the destination directory in the primary repository.
    """
    source_run_dir = worktree_path / ".agents" / "runs" / run_id
    destination_root = repo_root.expanduser().resolve() / ".agents" / "runs"
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / run_id
    if not source_run_dir.exists():
        return destination
    shutil.copytree(source_run_dir, destination, dirs_exist_ok=True)
    return destination
