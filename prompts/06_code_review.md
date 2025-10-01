# Code Review Agent

Goal: Perform a first-pass code review and annotate risks.

Deliverables:
- `REVIEW.md` in `.agents/review/` with:
  - Summary of changes
  - Risk areas
  - Specific comments with file/line references
  - Suggested follow-ups

Completion:
- Write a run report JSON to `${REPORT_PATH}` with review findings.
