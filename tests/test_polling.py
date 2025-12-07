"""Tests for the polling service module."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent_orchestrator.polling import (
    FilterConfig,
    GitHubIssuePollSource,
    OnMatchConfig,
    PollConfig,
    PollConfigError,
    PollSourceConfig,
    TriggerEvent,
    TriggerExecutor,
    get_poll_source,
    load_poll_config,
)


class TestPollConfig:
    """Tests for poll config loading and validation."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        """Test loading a valid poll configuration."""
        config_file = tmp_path / "poll_config.yaml"
        config_file.write_text("""
sources:
  - type: github_issues
    repo: owner/repo
    filter:
      labels:
        - ready-for-agent
      exclude_labels:
        - wip
      state: open
    processed_label: agent-processing
    on_match:
      script: ./scripts/trigger.sh
      env:
        WORKFLOW: workflow.yaml
""")

        config = load_poll_config(config_file)

        assert len(config.sources) == 1
        source = config.sources[0]
        assert source.type == "github_issues"
        assert source.repo == "owner/repo"
        assert source.filter.labels == ["ready-for-agent"]
        assert source.filter.exclude_labels == ["wip"]
        assert source.filter.state == "open"
        assert source.processed_label == "agent-processing"
        assert source.on_match.script == "./scripts/trigger.sh"
        assert source.on_match.env == {"WORKFLOW": "workflow.yaml"}

    def test_load_minimal_config(self, tmp_path: Path) -> None:
        """Test loading a minimal poll configuration."""
        config_file = tmp_path / "poll_config.yaml"
        config_file.write_text("""
sources:
  - type: github_issues
    on_match:
      script: ./trigger.sh
""")

        config = load_poll_config(config_file)

        assert len(config.sources) == 1
        source = config.sources[0]
        assert source.type == "github_issues"
        assert source.repo is None
        assert source.filter.labels == []
        assert source.filter.state == "open"
        assert source.processed_label == "agent-processing"
        assert source.on_match.env == {}

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Test error when config file doesn't exist."""
        with pytest.raises(PollConfigError, match="not found"):
            load_poll_config(tmp_path / "nonexistent.yaml")

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Test error when config file is empty."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        with pytest.raises(PollConfigError, match="Empty"):
            load_poll_config(config_file)

    def test_load_missing_sources(self, tmp_path: Path) -> None:
        """Test error when sources key is missing."""
        config_file = tmp_path / "no_sources.yaml"
        config_file.write_text("other_key: value")

        with pytest.raises(PollConfigError, match="must contain 'sources'"):
            load_poll_config(config_file)

    def test_load_missing_type(self, tmp_path: Path) -> None:
        """Test error when source type is missing."""
        config_file = tmp_path / "no_type.yaml"
        config_file.write_text("""
sources:
  - on_match:
      script: ./trigger.sh
""")

        with pytest.raises(PollConfigError, match="missing required 'type'"):
            load_poll_config(config_file)

    def test_load_missing_on_match(self, tmp_path: Path) -> None:
        """Test error when on_match is missing."""
        config_file = tmp_path / "no_on_match.yaml"
        config_file.write_text("""
sources:
  - type: github_issues
""")

        with pytest.raises(PollConfigError, match="missing required 'on_match'"):
            load_poll_config(config_file)


class TestPollSourceRegistry:
    """Tests for the poll source registry."""

    def test_get_github_issues_source(self) -> None:
        """Test getting the GitHub issues poll source."""
        source = get_poll_source("github_issues")
        assert isinstance(source, GitHubIssuePollSource)

    def test_get_unknown_source(self) -> None:
        """Test error when requesting unknown source type."""
        with pytest.raises(ValueError, match="Unknown poll source"):
            get_poll_source("unknown_source")


class TestGitHubIssuePollSource:
    """Tests for GitHub issue polling."""

    def test_poll_returns_matching_issues(self) -> None:
        """Test that poll returns issues matching the filter criteria."""
        source = GitHubIssuePollSource()
        config = PollSourceConfig(
            type="github_issues",
            repo="owner/repo",
            filter=FilterConfig(labels=["ready-for-agent"]),
            processed_label="agent-processing",
            on_match=OnMatchConfig(script="./trigger.sh"),
        )

        gh_output = json.dumps([
            {
                "number": 42,
                "title": "Test issue",
                "url": "https://github.com/owner/repo/issues/42",
                "labels": [{"name": "ready-for-agent"}],
            }
        ])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=gh_output, returncode=0)
            events = source.poll(config)

        assert len(events) == 1
        assert events[0].item_id == "42"
        assert events[0].source_type == "github_issues"
        assert events[0].metadata["title"] == "Test issue"

    def test_poll_filters_already_processed(self) -> None:
        """Test that poll filters out already processed issues."""
        source = GitHubIssuePollSource()
        config = PollSourceConfig(
            type="github_issues",
            repo="owner/repo",
            filter=FilterConfig(labels=["ready-for-agent"]),
            processed_label="agent-processing",
            on_match=OnMatchConfig(script="./trigger.sh"),
        )

        gh_output = json.dumps([
            {
                "number": 42,
                "title": "Already processed",
                "url": "https://github.com/owner/repo/issues/42",
                "labels": [
                    {"name": "ready-for-agent"},
                    {"name": "agent-processing"},  # Already processed
                ],
            }
        ])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=gh_output, returncode=0)
            events = source.poll(config)

        assert len(events) == 0

    def test_poll_filters_excluded_labels(self) -> None:
        """Test that poll filters out issues with excluded labels."""
        source = GitHubIssuePollSource()
        config = PollSourceConfig(
            type="github_issues",
            repo="owner/repo",
            filter=FilterConfig(
                labels=["ready-for-agent"],
                exclude_labels=["wip"],
            ),
            processed_label="agent-processing",
            on_match=OnMatchConfig(script="./trigger.sh"),
        )

        gh_output = json.dumps([
            {
                "number": 42,
                "title": "Work in progress",
                "url": "https://github.com/owner/repo/issues/42",
                "labels": [
                    {"name": "ready-for-agent"},
                    {"name": "wip"},  # Excluded
                ],
            }
        ])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=gh_output, returncode=0)
            events = source.poll(config)

        assert len(events) == 0

    def test_poll_uses_env_repo(self) -> None:
        """Test that poll uses GITHUB_REPOSITORY env var when repo not specified."""
        source = GitHubIssuePollSource()
        config = PollSourceConfig(
            type="github_issues",
            repo=None,  # Not specified
            filter=FilterConfig(),
            processed_label="agent-processing",
            on_match=OnMatchConfig(script="./trigger.sh"),
        )

        gh_output = json.dumps([])

        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "env/repo"}):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=gh_output, returncode=0)
                source.poll(config)

        call_args = mock_run.call_args[0][0]
        assert "--repo" in call_args
        assert "env/repo" in call_args

    def test_poll_returns_empty_on_no_repo(self) -> None:
        """Test that poll returns empty list when no repo specified."""
        source = GitHubIssuePollSource()
        config = PollSourceConfig(
            type="github_issues",
            repo=None,
            filter=FilterConfig(),
            processed_label="agent-processing",
            on_match=OnMatchConfig(script="./trigger.sh"),
        )

        with patch.dict("os.environ", {}, clear=True):
            events = source.poll(config)

        assert events == []

    def test_mark_processed_adds_label(self) -> None:
        """Test that mark_processed adds the processed label."""
        source = GitHubIssuePollSource()
        config = PollSourceConfig(
            type="github_issues",
            repo="owner/repo",
            filter=FilterConfig(),
            processed_label="agent-processing",
            on_match=OnMatchConfig(script="./trigger.sh"),
        )
        event = TriggerEvent(
            source_type="github_issues",
            item_id="42",
            item_url="https://github.com/owner/repo/issues/42",
            metadata={"repo": "owner/repo"},
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            source.mark_processed(event, config)

        call_args = mock_run.call_args[0][0]
        assert "gh" in call_args
        assert "issue" in call_args
        assert "edit" in call_args
        assert "42" in call_args
        assert "--add-label" in call_args
        assert "agent-processing" in call_args


class TestTriggerExecutor:
    """Tests for trigger script execution."""

    def test_execute_runs_script(self, tmp_path: Path) -> None:
        """Test that execute runs the trigger script."""
        script = tmp_path / "trigger.sh"
        script.write_text("#!/bin/bash\necho 'triggered'")
        script.chmod(0o755)

        executor = TriggerExecutor(workdir=tmp_path)
        event = TriggerEvent(
            source_type="github_issues",
            item_id="42",
            item_url="https://github.com/owner/repo/issues/42",
            metadata={"repo": "owner/repo", "title": "Test"},
        )
        config = OnMatchConfig(script=str(script))

        exit_code = executor.execute(event, config)

        assert exit_code == 0

    def test_execute_passes_environment(self, tmp_path: Path) -> None:
        """Test that execute passes environment variables to script."""
        script = tmp_path / "trigger.sh"
        script.write_text("""#!/bin/bash
echo "ISSUE=$ISSUE_NUMBER"
echo "URL=$POLL_ITEM_URL"
echo "CUSTOM=$CUSTOM_VAR"
""")
        script.chmod(0o755)

        executor = TriggerExecutor(workdir=tmp_path)
        event = TriggerEvent(
            source_type="github_issues",
            item_id="42",
            item_url="https://github.com/owner/repo/issues/42",
            metadata={"repo": "owner/repo"},
        )
        config = OnMatchConfig(script=str(script), env={"CUSTOM_VAR": "custom_value"})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            executor.execute(event, config)

        call_kwargs = mock_run.call_args[1]
        env = call_kwargs["env"]
        assert env["ISSUE_NUMBER"] == "42"
        assert env["POLL_ITEM_URL"] == "https://github.com/owner/repo/issues/42"
        assert env["POLL_SOURCE_TYPE"] == "github_issues"
        assert env["CUSTOM_VAR"] == "custom_value"

    def test_execute_returns_exit_code(self, tmp_path: Path) -> None:
        """Test that execute returns the script's exit code."""
        script = tmp_path / "fail.sh"
        script.write_text("#!/bin/bash\nexit 1")
        script.chmod(0o755)

        executor = TriggerExecutor(workdir=tmp_path)
        event = TriggerEvent(
            source_type="github_issues",
            item_id="42",
            item_url="https://example.com",
        )
        config = OnMatchConfig(script=str(script))

        exit_code = executor.execute(event, config)

        assert exit_code == 1

    def test_execute_missing_script(self, tmp_path: Path) -> None:
        """Test that execute returns error code for missing script."""
        executor = TriggerExecutor(workdir=tmp_path)
        event = TriggerEvent(
            source_type="github_issues",
            item_id="42",
            item_url="https://example.com",
        )
        config = OnMatchConfig(script="nonexistent.sh")

        exit_code = executor.execute(event, config)

        assert exit_code == 1

    def test_execute_resolves_relative_path(self, tmp_path: Path) -> None:
        """Test that execute resolves relative script paths against workdir."""
        subdir = tmp_path / "scripts"
        subdir.mkdir()
        script = subdir / "trigger.sh"
        script.write_text("#!/bin/bash\necho 'ok'")
        script.chmod(0o755)

        executor = TriggerExecutor(workdir=tmp_path)
        event = TriggerEvent(
            source_type="github_issues",
            item_id="42",
            item_url="https://example.com",
        )
        config = OnMatchConfig(script="scripts/trigger.sh")

        exit_code = executor.execute(event, config)

        assert exit_code == 0
