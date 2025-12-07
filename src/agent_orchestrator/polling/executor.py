"""Trigger executor for running scripts when polls match."""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from .models import OnMatchConfig, TriggerEvent

_LOG = logging.getLogger(__name__)


class TriggerExecutor:
    """Executes bash scripts when triggers fire."""

    def __init__(self, workdir: Optional[Path] = None):
        """Initialize the executor.

        Args:
            workdir: Working directory for script execution.
                     Defaults to current directory.
        """
        self._workdir = workdir or Path.cwd()

    def execute(self, event: TriggerEvent, config: OnMatchConfig) -> int:
        """Execute the trigger script with environment variables.

        The script receives these environment variables:
        - POLL_SOURCE_TYPE: e.g., "github_issues"
        - POLL_ITEM_ID: e.g., "42"
        - POLL_ITEM_URL: Full URL to item
        - POLL_REPO: Repository (for GitHub)
        - ISSUE_NUMBER: Same as POLL_ITEM_ID (for GitHub compatibility)
        - Any additional vars from config.env

        Args:
            event: The trigger event with item details.
            config: OnMatchConfig with script path and extra env vars.

        Returns:
            Exit code from the script (0 = success).
        """
        script_path = Path(config.script)

        # Resolve relative paths against workdir
        if not script_path.is_absolute():
            script_path = self._workdir / script_path

        if not script_path.exists():
            _LOG.error(f"Script not found: {script_path}")
            return 1

        # Build environment
        env = os.environ.copy()

        # Add standard poll variables
        env["POLL_SOURCE_TYPE"] = event.source_type
        env["POLL_ITEM_ID"] = event.item_id
        env["POLL_ITEM_URL"] = event.item_url

        # Add source-specific variables
        if event.source_type == "github_issues":
            env["ISSUE_NUMBER"] = event.item_id
            if "repo" in event.metadata:
                env["POLL_REPO"] = event.metadata["repo"]
            if "title" in event.metadata:
                env["POLL_ISSUE_TITLE"] = event.metadata["title"]

        # Add user-configured variables
        env.update(config.env)

        _LOG.info(f"Executing trigger script: {script_path}")
        _LOG.debug(f"Environment: POLL_SOURCE_TYPE={event.source_type}, POLL_ITEM_ID={event.item_id}")

        try:
            result = subprocess.run(
                ["bash", str(script_path)],
                cwd=str(self._workdir),
                env=env,
            )
            return result.returncode
        except Exception as e:
            _LOG.error(f"Failed to execute script: {e}")
            return 1
