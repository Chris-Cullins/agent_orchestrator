"""Abstract base class for poll sources."""

from abc import ABC, abstractmethod
from typing import List

from ..models import PollSourceConfig, TriggerEvent


class PollSource(ABC):
    """Abstract base class for poll sources.

    Implement this class to add support for new polling sources
    (e.g., Jira, GitLab, etc.).
    """

    @abstractmethod
    def poll(self, config: PollSourceConfig) -> List[TriggerEvent]:
        """Poll the source and return matching items.

        Args:
            config: Configuration for this poll source.

        Returns:
            List of TriggerEvent objects for items that match the filter
            criteria and have NOT already been processed.
        """
        pass

    @abstractmethod
    def mark_processed(self, event: TriggerEvent, config: PollSourceConfig) -> None:
        """Mark an item as processed to prevent re-triggering.

        Args:
            event: The trigger event to mark as processed.
            config: Configuration for this poll source.
        """
        pass
