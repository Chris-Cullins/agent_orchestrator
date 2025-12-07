"""Poll source implementations."""

from .base import PollSource
from .github_issues import GitHubIssuePollSource

__all__ = ["PollSource", "GitHubIssuePollSource"]
