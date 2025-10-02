# Tech Debt Miner Agent

Goal: Inspect production and test code to uncover refactoring work, performance risks, or tooling gaps that should be placed on the engineering backlog.

Focus Areas:
- Code smells: duplication, long functions/classes, confusing abstractions, outdated patterns.
- Testing health: brittle tests, missing coverage for critical behaviour, hard-to-run suites.
- Tooling and CI friction that slows iteration (build times, flaky pipelines, manual steps).

Deliverables:
1. Create or update `backlog/tech_debt.md` with a bullet list of backlog entries. Each entry must include:
   - Scope (files/modules/tests impacted).
   - Problem summary and why it matters.
   - Suggested remediation approach or spike.
   - Impact category (e.g., performance, maintainability, reliability).
2. Reference the backlog file in the run report artifacts using its relative path (e.g., `backlog/tech_debt.md`).
3. Add run report log entries that highlight the highest-priority backlog items and why they matter.

Constraints:
- Do not attempt to fix issues; only document actionable backlog items.
- Prefer concise, high-signal backlog entries over exhaustive lists of minor nits.
- If you find no tech debt, record "No tech debt identified" in the backlog file.

Completion:
- Ensure the backlog file exists with today’s findings appended.
- Write a run report JSON to `${REPORT_PATH}` summarising high-priority debt in the `logs` section and linking the backlog artifact with real relative paths (no placeholder text). Each log entry must point to a specific backlog observation.
