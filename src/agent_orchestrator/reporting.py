from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import RunReport

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    Draft202012Validator = None


class RunReportError(Exception):
    """Raised when a run report cannot be loaded or validated."""


class RunReportReader:
    def __init__(self, schema_path: Optional[Path] = None) -> None:
        self._validator = None
        if schema_path:
            if Draft202012Validator is None:
                raise RunReportError("jsonschema must be installed to validate run reports")
            if not schema_path.exists():
                raise RunReportError(f"Run report schema not found: {schema_path}")
            with schema_path.open("r", encoding="utf-8") as f:
                schema = json.load(f)
            self._validator = Draft202012Validator(schema)

    def read(self, path: Path) -> RunReport:
        if not path.exists():
            raise RunReportError(f"Run report not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        if self._validator:
            self._validator.validate(payload)

        required = ["schema", "run_id", "step_id", "agent", "status", "started_at", "ended_at"]
        missing = [field for field in required if field not in payload]
        if missing:
            raise RunReportError(f"Run report {path} missing fields: {', '.join(missing)}")

        return RunReport(
            schema=str(payload["schema"]),
            run_id=str(payload["run_id"]),
            step_id=str(payload["step_id"]),
            agent=str(payload["agent"]),
            status=str(payload["status"]).upper(),
            started_at=str(payload["started_at"]),
            ended_at=str(payload["ended_at"]),
            artifacts=list(payload.get("artifacts", [])),
            metrics=dict(payload.get("metrics", {})),
            logs=list(payload.get("logs", [])),
            next_suggested_steps=list(payload.get("next_suggested_steps", [])),
            raw=payload,
        )

