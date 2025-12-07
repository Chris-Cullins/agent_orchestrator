"""Polling service for watching external sources and triggering workflows."""

from .executor import TriggerExecutor
from .models import (
    FilterConfig,
    OnMatchConfig,
    PollConfig,
    PollConfigError,
    PollSourceConfig,
    TriggerEvent,
    load_poll_config,
)
from .sources import GitHubIssuePollSource, PollSource

# Registry of available poll sources
POLL_SOURCES = {
    "github_issues": GitHubIssuePollSource,
    # Future: "jira": JiraPollSource,
}


def get_poll_source(source_type: str) -> PollSource:
    """Get a poll source instance by type.

    Args:
        source_type: The type of poll source (e.g., "github_issues").

    Returns:
        An instance of the appropriate PollSource subclass.

    Raises:
        ValueError: If the source type is not registered.
    """
    if source_type not in POLL_SOURCES:
        available = ", ".join(POLL_SOURCES.keys())
        raise ValueError(f"Unknown poll source: {source_type}. Available: {available}")
    return POLL_SOURCES[source_type]()


__all__ = [
    "FilterConfig",
    "GitHubIssuePollSource",
    "OnMatchConfig",
    "PollConfig",
    "PollConfigError",
    "PollSource",
    "PollSourceConfig",
    "TriggerEvent",
    "TriggerExecutor",
    "get_poll_source",
    "load_poll_config",
]
