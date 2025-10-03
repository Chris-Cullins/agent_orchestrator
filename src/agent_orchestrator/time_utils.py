"""Shared helpers for working with timezone-aware timestamps."""

from __future__ import annotations

from datetime import datetime, timezone

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now() -> str:
    """Return the current UTC time formatted using ISO 8601 with a trailing Z."""
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)
