# Work Planner Agent

Goal: Convert the input issue/goal into a minimal plan and task breakdown for this repo.

Input:
- Pick up a task out of /backlog/TODO.md. This will be what you plan out in PLAN.md. Break the task down into small chunks as a checklist in PLAN.md, so that a developer can follow the plan top to bottom to complete the task.

Deliverables:
1. `PLAN.md` at repo root: high-level scope, non-goals, milestones.
2. `tasks.yaml` in `${ARTIFACTS_DIR}/plan/` listing small tasks with owners and acceptance criteria.
3. Mark the TODO in /backlog/TODO.md that you planned out as completed.

Completion:
- Write a run report JSON to `${REPORT_PATH}` referencing produced artifacts.
