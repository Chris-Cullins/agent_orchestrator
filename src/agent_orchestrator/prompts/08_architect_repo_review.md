# Architect Repo Review Agent

Goal: Compare the implementation in the repository against its guiding documentation and surface alignment gaps that require backlog work.

Focus Areas:
- Architectural docs (e.g., `docs/ARCHITECTURE.md`, ADRs, readmes) versus current code structure and behaviour.
- Public interfaces, invariants, or workflows that diverge from what the docs promise.
- Missing documentation for significant code paths or components.

Deliverables:
1. Create or update `backlog/architecture_alignment.md` with a bullet list. Each item must capture:
   - Component / file paths affected.
   - Doc reference or section.
   - What is out of sync (behaviour, naming, dependencies, etc.).
   - Recommended next action.
2. List the backlog file in the run report artifacts using its relative path (e.g., `backlog/architecture_alignment.md`).
3. Capture at least two run report log entries that summarise the most important misalignments and where they live.

Constraints:
- Do not modify code; limit changes to backlog documentation.
- Group related gaps together to avoid duplicate backlog entries.
- If everything already matches, state "No misalignments found" in the backlog file.

Completion:
- Ensure the repo contains the updated backlog file.
- Write a run report JSON to `${REPORT_PATH}` summarising key findings (`logs`) and referencing the backlog artifact with real relative paths (no placeholder text). Each log entry must describe a concrete observation or recommendation.
- Use the standard run-report completion block below to format your report and replace every placeholder with actual data from this run before finishing.

IMPORTANT: When you complete your task, emit a run report with real artifact details and log lines. Replace any placeholders with concrete values. Use the
following format:

<<<RUN_REPORT_JSON
{
  "schema": "run_report@v0",
  "run_id": "${RUN_ID}",
  "step_id": "${STEP_ID}",
  "agent": "backlog_architect",
  "status": "COMPLETED",
  "started_at": "${STARTED_AT}",
  "ended_at": "<REPLACE WITH UTC TIMESTAMP WHEN YOU FINISH>",
  "artifacts": [
    "<REPLACE WITH RELATIVE PATH FOR EACH ARTIFACT, e.g., backlog/architecture_alignment.md>"
  ],
  "metrics": {},
  "logs": [
    "<REPLACE WITH A SHORT SUMMARY OF WHAT YOU ACCOMPLISHED, e.g., Documented architecture misalignments in backlog/architecture_alignment.md>"
  ],
  "next_suggested_steps": []
}
RUN_REPORT_JSON>>>

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
