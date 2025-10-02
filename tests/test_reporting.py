from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agent_orchestrator.models import ISO_FORMAT, utc_now
from agent_orchestrator.reporting import RunReportError, RunReportReader


def _write_report(tmp_path, **overrides):
    payload = {
        "schema": "run_report@v0",
        "run_id": "test_run",
        "step_id": "step_one",
        "agent": "tester",
        "status": "COMPLETED",
        "started_at": "2025-01-01T00:00:00.000000Z",
        "ended_at": "2025-01-01T00:10:00.000000Z",
        "artifacts": ["backlog/example.md"],
        "metrics": {"duration_ms": 600000},
        "logs": ["Documented findings"],
        "next_suggested_steps": [],
    }
    payload.update(overrides)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_run_report_reader_rejects_placeholder_artifacts(tmp_path):
    report_path = _write_report(
        tmp_path,
        artifacts=["list", "of", "created", "file", "paths"],
    )

    reader = RunReportReader()

    with pytest.raises(RunReportError) as exc:
        reader.read(report_path)

    assert "placeholder artifact" in str(exc.value)


def test_run_report_reader_rejects_placeholder_logs(tmp_path):
    report_path = _write_report(
        tmp_path,
        logs=["summary", "of", "what", "you", "accomplished"],
    )

    reader = RunReportReader()

    with pytest.raises(RunReportError) as exc:
        reader.read(report_path)

    assert "placeholder logs" in str(exc.value)


def test_run_report_reader_rejects_missing_logs(tmp_path):
    report_path = _write_report(
        tmp_path,
        logs=[],
    )

    reader = RunReportReader()

    with pytest.raises(RunReportError) as exc:
        reader.read(report_path)

    assert "log entry" in str(exc.value)


def test_run_report_reader_rejects_placeholder_ended_at(tmp_path):
    report_path = _write_report(
        tmp_path,
        ended_at="<REPLACE WITH UTC TIMESTAMP WHEN YOU FINISH>",
    )

    reader = RunReportReader()

    with pytest.raises(RunReportError) as exc:
        reader.read(report_path)

    assert "placeholder ended_at" in str(exc.value)


def test_run_report_reader_accepts_valid_report(tmp_path):
    report_path = _write_report(
        tmp_path,
        artifacts=["backlog/architecture_alignment.md"],
        logs=["Captured architecture misalignments in backlog"],
        ended_at="2025-01-01T00:15:00.000000Z",
    )

    reader = RunReportReader()
    report = reader.read(report_path)

    assert report.artifacts == ["backlog/architecture_alignment.md"]
    assert report.logs == ["Captured architecture misalignments in backlog"]


def test_utc_now_returns_utc_timestamp():
    timestamp = utc_now()

    assert timestamp.endswith("Z")
    datetime.strptime(timestamp, ISO_FORMAT)

    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert dt.tzinfo == timezone.utc
