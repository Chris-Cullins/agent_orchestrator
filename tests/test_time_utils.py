from datetime import datetime, timezone

from agent_orchestrator.time_utils import utc_now


def test_utc_now_returns_timezone_aware_iso_string():
    timestamp = utc_now()

    assert timestamp.endswith("Z"), "timestamp must use Z (UTC) suffix"

    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc
