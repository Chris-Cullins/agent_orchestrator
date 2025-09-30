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
2. Mention the backlog file in the run report artifacts list.

Constraints:
- Do not modify code; limit changes to backlog documentation.
- Group related gaps together to avoid duplicate backlog entries.
- If everything already matches, state "No misalignments found" in the backlog file.

Completion:
- Ensure the repo contains the updated backlog file.
- Write a run report JSON to `${REPORT_PATH}` summarising key findings (`logs`) and referencing the backlog artifact.
