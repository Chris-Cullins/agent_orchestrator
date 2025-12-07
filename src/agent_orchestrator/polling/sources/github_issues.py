"""GitHub Issues poll source implementation."""

import json
import logging
import os
import subprocess
from typing import List

from .base import PollSource
from ..models import PollSourceConfig, TriggerEvent

_LOG = logging.getLogger(__name__)


class GitHubIssuePollSource(PollSource):
    """Polls GitHub issues using the gh CLI."""

    def poll(self, config: PollSourceConfig) -> List[TriggerEvent]:
        """Poll GitHub for issues matching the filter criteria.

        Uses gh CLI to list issues with specified labels, then filters out
        any issues that already have the processed_label.

        Args:
            config: Poll source configuration.

        Returns:
            List of TriggerEvent objects for unprocessed matching issues.
        """
        repo = self._get_repo(config)
        if not repo:
            _LOG.error("No repository specified and GITHUB_REPOSITORY not set")
            return []

        # Build gh command to list issues
        cmd = [
            "gh", "issue", "list",
            "--repo", repo,
            "--state", config.filter.state,
            "--json", "number,title,url,labels",
        ]

        # Add label filters (gh CLI does AND logic for multiple --label flags)
        for label in config.filter.labels:
            cmd.extend(["--label", label])

        _LOG.debug(f"Running command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            _LOG.error(f"Failed to list GitHub issues: {e.stderr}")
            return []

        try:
            issues = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            _LOG.error(f"Failed to parse gh output: {e}")
            return []

        events = []
        for issue in issues:
            issue_labels = {label["name"] for label in issue.get("labels", [])}

            # Skip if already processed
            if config.processed_label in issue_labels:
                _LOG.debug(f"Skipping issue #{issue['number']}: already has {config.processed_label}")
                continue

            # Skip if has any excluded labels
            excluded = issue_labels & set(config.filter.exclude_labels)
            if excluded:
                _LOG.debug(f"Skipping issue #{issue['number']}: has excluded labels {excluded}")
                continue

            event = TriggerEvent(
                source_type="github_issues",
                item_id=str(issue["number"]),
                item_url=issue["url"],
                metadata={
                    "title": issue["title"],
                    "labels": [label["name"] for label in issue.get("labels", [])],
                    "repo": repo,
                },
            )
            events.append(event)
            _LOG.info(f"Found matching issue: #{issue['number']} - {issue['title']}")

        return events

    def mark_processed(self, event: TriggerEvent, config: PollSourceConfig) -> None:
        """Mark an issue as processed by adding the processed_label.

        Args:
            event: The trigger event to mark.
            config: Poll source configuration.
        """
        repo = event.metadata.get("repo") or self._get_repo(config)
        if not repo:
            _LOG.error("Cannot mark processed: no repository specified")
            return

        cmd = [
            "gh", "issue", "edit",
            event.item_id,
            "--repo", repo,
            "--add-label", config.processed_label,
        ]

        _LOG.debug(f"Running command: {' '.join(cmd)}")

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            _LOG.info(f"Marked issue #{event.item_id} with label '{config.processed_label}'")
        except subprocess.CalledProcessError as e:
            _LOG.error(f"Failed to add label to issue #{event.item_id}: {e.stderr}")

    def _get_repo(self, config: PollSourceConfig) -> str:
        """Get the repository from config or environment."""
        if config.repo:
            return config.repo
        return os.environ.get("GITHUB_REPOSITORY", "")
