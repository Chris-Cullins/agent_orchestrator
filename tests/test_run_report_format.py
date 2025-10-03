from __future__ import annotations

import pytest

from agent_orchestrator.run_report_format import (
    PlaceholderContentError,
    normalize_run_report_payload,
)


def test_normalize_run_report_payload_accepts_valid_content():
    payload = {
        "artifacts": "backlog/architecture_alignment.md",
        "logs": [" Documented misalignment between docs and implementation "],
        "ended_at": "2025-01-01T00:00:00.000000Z",
        "status": "completed",
    }

    result = normalize_run_report_payload(payload)

    assert result["artifacts"] == ["backlog/architecture_alignment.md"]
    assert result["logs"] == ["Documented misalignment between docs and implementation"]
    assert result["ended_at"] == "2025-01-01T00:00:00.000000Z"


def test_normalize_run_report_payload_rejects_empty_logs():
    payload = {
        "artifacts": ["backlog/tech_debt.md"],
        "logs": [],
        "ended_at": "2025-01-01T00:00:00.000000Z",
    }

    with pytest.raises(PlaceholderContentError) as exc:
        normalize_run_report_payload(payload)

    assert "log entry" in str(exc.value)


def test_normalize_run_report_payload_rejects_placeholder_artifacts():
    payload = {
        "artifacts": ["list", "of", "created", "file", "paths"],
        "logs": ["Captured tech debt"],
        "ended_at": "2025-01-01T00:00:00.000000Z",
    }

    with pytest.raises(PlaceholderContentError) as exc:
        normalize_run_report_payload(payload)

    assert "placeholder artifact" in str(exc.value)


def test_normalize_run_report_payload_rejects_placeholder_ended_at():
    payload = {
        "artifacts": ["backlog/tech_debt.md"],
        "logs": ["Captured tech debt"],
        "ended_at": "<REPLACE WITH UTC TIMESTAMP WHEN YOU FINISH>",
    }

    with pytest.raises(PlaceholderContentError) as exc:
        normalize_run_report_payload(payload)

    assert "placeholder ended_at" in str(exc.value)
