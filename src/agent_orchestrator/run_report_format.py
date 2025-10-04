"""Utilities for rendering and validating run report guidance."""

from __future__ import annotations

from collections.abc import Iterable
from textwrap import dedent
from typing import Any

RUN_REPORT_START = "<<<RUN_REPORT_JSON"
RUN_REPORT_END = "RUN_REPORT_JSON>>>"

_PLACEHOLDER_ARTIFACT_PHRASES = (
    "list of created file paths",
    "replace with actual artifact",
    "relative path to each created file",
    "relative path to the artifact you produced",
    "replace with relative path for each artifact",
    "replace with the relative path to each artifact",
)

_PLACEHOLDER_LOG_PHRASES = (
    "summary of what you accomplished",
    "replace with actual log entry",
    "concise summary of work performed",
    "concise bullet summarizing work",
    "replace with a concise summary",
    "replace with a short summary of what you accomplished",
)

_PLACEHOLDER_ENDED_AT_PHRASES = (
    "replace with utc timestamp when you finish",
    "insert completion timestamp",
)


def build_run_report_instructions(
    run_id: str,
    step_id: str,
    agent: str,
    started_at: str,
) -> str:
    """Return the guidance block embedded into wrapper prompts."""

    return dedent(
        f"""IMPORTANT: When you complete your task, emit a run report with real artifact details and log lines. Replace any placeholders with concrete values. Use the
following format:

{RUN_REPORT_START}
{{
  "schema": "run_report@v0",
  "run_id": "{run_id}",
  "step_id": "{step_id}",
  "agent": "{agent}",
  "status": "COMPLETED",
  "started_at": "{started_at}",
  "ended_at": "<REPLACE WITH UTC TIMESTAMP WHEN YOU FINISH>",
  "artifacts": [
    "<REPLACE WITH RELATIVE PATH FOR EACH ARTIFACT, e.g., backlog/architecture_alignment.md>"
  ],
  "metrics": {{}},
  "logs": [
    "<REPLACE WITH A SHORT SUMMARY OF WHAT YOU ACCOMPLISHED, e.g., Documented architecture misalignments in backlog/architecture_alignment.md>"
  ],
  "next_suggested_steps": []
}}
{RUN_REPORT_END}

Guidelines:
- Provide relative repository paths for every artifact you created or updated. If
  there are no artifacts, leave the array empty and note that in the logs.
- Add at least one concise log entry summarising the substantive actions you
  took. Never leave placeholder text such as "summary of what you accomplished".
- Replace the placeholder ended_at value with the actual completion timestamp in
  UTC (format: YYYY-MM-DDTHH:MM:SS.mmmmmmZ).
- Replace the example artifact and log entries with the real data from this run.
  Never leave instructional text in your report.
- The orchestrator will reject run reports that retain placeholder content in
  the artifacts, logs, or ended_at fields, or that omit log entries entirely.
"""
    )


def contains_placeholder_artifacts(values: Iterable[str]) -> bool:
    """Return True when the artifacts list still contains placeholder text."""

    normalised = [value.strip().lower() for value in values if value.strip()]
    return _matches_placeholder(normalised, _PLACEHOLDER_ARTIFACT_PHRASES)


def contains_placeholder_logs(values: Iterable[str]) -> bool:
    """Return True when the logs list still contains placeholder text."""

    normalised = [value.strip().lower() for value in values if value.strip()]
    return _matches_placeholder(normalised, _PLACEHOLDER_LOG_PHRASES)


def ended_at_looks_placeholder(value: str) -> bool:
    """Return True when the ended_at field still contains placeholder text."""

    return _matches_placeholder([value.strip().lower()], _PLACEHOLDER_ENDED_AT_PHRASES)


class PlaceholderContentError(ValueError):
    """Raised when a run report payload still contains placeholder content."""


def normalize_run_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *payload* with normalised lists and validated content."""

    normalised = dict(payload)

    artifacts = _normalise_string_list(normalised.get("artifacts"))
    logs = _normalise_string_list(normalised.get("logs"))
    ended_at_value = str(normalised.get("ended_at", "")).strip()

    if contains_placeholder_artifacts(artifacts):
        raise PlaceholderContentError(
            "placeholder artifact entries detected; replace them with real relative paths"
        )

    if contains_placeholder_logs(logs):
        raise PlaceholderContentError(
            "placeholder logs detected; describe what you actually accomplished"
        )

    if not logs:
        raise PlaceholderContentError("at least one log entry is required in the run report")

    if not ended_at_value:
        raise PlaceholderContentError("missing ended_at timestamp; provide the completion time")

    if ended_at_looks_placeholder(ended_at_value):
        raise PlaceholderContentError(
            "placeholder ended_at timestamp detected; record the real completion time"
        )

    normalised["artifacts"] = artifacts
    normalised["logs"] = logs
    normalised["ended_at"] = ended_at_value

    return normalised


def _matches_placeholder(values: Iterable[str], phrases: Iterable[str]) -> bool:
    """Helper that checks whether any placeholder phrase is present."""

    if not values:
        return False

    joined = " ".join(values)
    for phrase in phrases:
        phrase = phrase.strip().lower()
        if not phrase:
            continue
        if any(value == phrase for value in values):
            return True
        if phrase in joined:
            return True
    return False


def _normalise_string_list(value: Any) -> list[str]:
    """Return *value* coerced into a list of non-empty strings."""

    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]

    cleaned: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return cleaned
