# Work Planner Agent

Goal: Convert the input issue/goal into a minimal plan and task breakdown for this repo.

Deliverables:
1. `PLAN.md` at repo root: high-level scope, non-goals, milestones.
2. `tasks.yaml` in `.agents/plan/` listing small tasks with owners and acceptance criteria.

Constraints:
- Keep tasks independently runnable within ~30 minutes each.
- Prefer additive changes over refactors unless required.

Completion:
- Write a run report JSON to `${REPORT_PATH}` referencing produced artifacts.
