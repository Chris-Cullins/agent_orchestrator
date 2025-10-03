from pathlib import Path
from datetime import datetime, timezone

from agent_orchestrator.models import RunState


def _parse_utc(timestamp: str) -> datetime:
    """Helper to parse orchestrator timestamps into aware datetimes."""
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def test_run_state_timestamps_are_timezone_aware():
    state = RunState(
        run_id="run-123",
        workflow_name="demo",
        repo_dir=Path("/tmp/repo"),
        reports_dir=Path("/tmp/reports"),
        manual_inputs_dir=Path("/tmp/manual"),
    )

    data = state.to_dict()

    created_at = _parse_utc(data["created_at"])
    updated_at = _parse_utc(data["updated_at"])

    assert created_at.tzinfo == timezone.utc
    assert updated_at.tzinfo == timezone.utc
    assert updated_at >= created_at
