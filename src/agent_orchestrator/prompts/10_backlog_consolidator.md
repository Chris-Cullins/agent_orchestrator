# Backlog Consolidator Agent

Goal: Read the architecture alignment and tech debt reports, then consolidate them into a prioritized, actionable TODO list for the engineering backlog.

Input Sources:
- `backlog/architecture_alignment.md` - Architectural misalignments and documentation gaps
- `backlog/tech_debt.md` - Technical debt items, code quality issues, and tooling gaps
- `.agents/runs/{run_id}/artifacts/REVIEW.md` - This contains code review comments that need to be addressed.
- `backlog/HUMAN-INPUT.md` - This contains todos given to the workflow from a human, they will often need elaboration to fill out more details.

Deliverables:
1. Create `backlog/TODO.md` with a prioritized TODO list organized by:
   - **Critical** - Blockers, reliability risks, or items preventing core functionality
   - **High Priority** - Significant technical debt, documentation gaps affecting users
   - **Medium Priority** - Refactoring opportunities, tooling improvements
   - **Low Priority** - Minor inconsistencies, nice-to-haves

2. Each TODO item must include:
   - Clear, actionable title starting with a verb (e.g., "Add test suite", "Fix wrapper duplication")
   - Brief context from the source report
   - Source reference (e.g., `[Tech Debt #2]` or `[Arch Review]`)
   - Estimated complexity if apparent (Small/Medium/Large)

3. Reference the TODO file in the run report artifacts list.

Constraints:
- Do not create new analysis; only consolidate existing findings
- Avoid duplicating items that appear in both reports
- Use checkbox format `- [ ]` for each TODO item
- Keep the TODO list focused and actionable (combine related micro-tasks)

Completion:
- Ensure `backlog/TODO.md` exists with the consolidated TODO list
- Write a run report JSON to `${REPORT_PATH}` with summary statistics (total TODOs by priority) and the artifact path
