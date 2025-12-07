"""Data models for the polling service."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class TriggerEvent:
    """Represents an item that matched polling criteria."""

    source_type: str  # "github_issues", "jira", etc.
    item_id: str  # Issue number, ticket ID, etc.
    item_url: str  # Link to the item
    metadata: Dict[str, Any] = field(default_factory=dict)  # Source-specific data


@dataclass
class OnMatchConfig:
    """What to execute when a match is found."""

    script: str  # Path to bash script
    env: Dict[str, str] = field(default_factory=dict)  # Additional env vars to pass


@dataclass
class FilterConfig:
    """Filter configuration for poll sources."""

    labels: List[str] = field(default_factory=list)  # Labels that must be present
    exclude_labels: List[str] = field(default_factory=list)  # Labels that must NOT be present
    state: str = "open"  # "open" or "closed"


@dataclass
class PollSourceConfig:
    """Configuration for a single poll source."""

    type: str  # "github_issues"
    on_match: OnMatchConfig  # What to do when match found
    repo: Optional[str] = None  # For GitHub: "owner/repo"
    filter: FilterConfig = field(default_factory=FilterConfig)
    processed_label: str = "agent-processing"  # Label to add after processing


@dataclass
class PollConfig:
    """Top-level poll configuration."""

    sources: List[PollSourceConfig] = field(default_factory=list)


class PollConfigError(Exception):
    """Raised when poll configuration is invalid."""

    pass


def load_poll_config(path: Path) -> PollConfig:
    """Load and validate poll configuration from YAML file."""
    if not path.exists():
        raise PollConfigError(f"Poll config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise PollConfigError(f"Empty poll config file: {path}")

    if "sources" not in raw:
        raise PollConfigError("Poll config must contain 'sources' list")

    sources = []
    for i, source_raw in enumerate(raw["sources"]):
        if "type" not in source_raw:
            raise PollConfigError(f"Source {i} missing required 'type' field")
        if "on_match" not in source_raw:
            raise PollConfigError(f"Source {i} missing required 'on_match' field")

        on_match_raw = source_raw["on_match"]
        if "script" not in on_match_raw:
            raise PollConfigError(f"Source {i} on_match missing required 'script' field")

        on_match = OnMatchConfig(
            script=on_match_raw["script"],
            env=on_match_raw.get("env", {}),
        )

        filter_raw = source_raw.get("filter", {})
        filter_config = FilterConfig(
            labels=filter_raw.get("labels", []),
            exclude_labels=filter_raw.get("exclude_labels", []),
            state=filter_raw.get("state", "open"),
        )

        source = PollSourceConfig(
            type=source_raw["type"],
            repo=source_raw.get("repo"),
            filter=filter_config,
            processed_label=source_raw.get("processed_label", "agent-processing"),
            on_match=on_match,
        )
        sources.append(source)

    return PollConfig(sources=sources)
