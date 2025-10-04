from __future__ import annotations

import json
import time
from pathlib import Path

from .models import RunReport

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    Draft202012Validator = None


class RunReportError(Exception):
    """Raised when a run report cannot be loaded or validated."""


class RunReportReader:
    def __init__(
        self,
        schema_path: Path | None = None,
        *,
        retry_attempts: int = 3,
        retry_delay: float = 0.2,
    ) -> None:
        self._validator = None
        self._retry_attempts = max(1, int(retry_attempts))
        self._retry_delay = max(0.0, float(retry_delay))
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
        payload = None
        last_error: json.JSONDecodeError | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                with path.open("r", encoding="utf-8") as f:
                    payload = json.load(f)
                break
            except json.JSONDecodeError as exc:
                last_error = exc
                if attempt == self._retry_attempts:
                    message = (
                        f"Run report {path} contains invalid JSON after {self._retry_attempts} attempts: {exc}"
                    )
                    raise RunReportError(message) from exc
                if self._retry_delay:
                    time.sleep(self._retry_delay)
            except ValueError as exc:
                raise RunReportError(f"Run report {path} could not be parsed: {exc}") from exc
            except OSError as exc:
                raise RunReportError(f"Failed to read run report {path}: {exc}") from exc

        if payload is None:
            if last_error:
                raise RunReportError(f"Run report {path} could not be parsed: {last_error}") from last_error
            raise RunReportError(f"Run report {path} could not be read")

        if not isinstance(payload, dict):
            raise RunReportError(f"Run report {path} must be a JSON object, got {type(payload).__name__}")

        if self._validator:
            try:
                self._validator.validate(payload)
            except Exception as exc:  # pragma: no cover - depends on optional jsonschema
                raise RunReportError(f"Run report {path} failed schema validation: {exc}") from exc

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
            gate_failure=bool(payload.get("gate_failure", False)),
            raw=payload,
        )
