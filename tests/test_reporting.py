import json
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_orchestrator.reporting import RunReportError, RunReportReader


class RunReportReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.report_path = Path(self._tmp.name) / "report.json"
        self.payload = {
            "schema": "run_report@v0",
            "run_id": "run123",
            "step_id": "stepA",
            "agent": "agent",
            "status": "COMPLETED",
            "started_at": "2024-01-01T00:00:00Z",
            "ended_at": "2024-01-01T00:00:10Z",
            "artifacts": ["artifact.txt"],
            "metrics": {"duration": "10s"},
            "logs": ["step finished"],
            "next_suggested_steps": [],
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_reads_report_after_partial_write(self) -> None:
        self.report_path.write_text("{\n  \"schema\":", encoding="utf-8")
        reader = RunReportReader(retry_attempts=5, retry_delay=0.01)

        def complete_write() -> None:
            time.sleep(0.02)
            self.report_path.write_text(json.dumps(self.payload), encoding="utf-8")

        finisher = threading.Thread(target=complete_write)
        finisher.start()
        report = reader.read(self.report_path)
        finisher.join()

        self.assertEqual("COMPLETED", report.status)
        self.assertEqual(self.payload["run_id"], report.run_id)
        self.assertEqual(self.payload["artifacts"], report.artifacts)

    def test_raises_error_when_json_stays_invalid(self) -> None:
        self.report_path.write_text("{\n  \"schema\":", encoding="utf-8")
        reader = RunReportReader(retry_attempts=2, retry_delay=0.01)

        with self.assertRaises(RunReportError) as ctx:
            reader.read(self.report_path)

        self.assertIn("invalid JSON", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
