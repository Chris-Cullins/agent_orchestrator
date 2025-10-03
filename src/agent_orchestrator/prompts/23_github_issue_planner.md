# GitHub Issue Work Planner Agent

Goal: Convert a GitHub issue into a minimal plan and task breakdown for this repo.

Input:
- Read the GitHub issue file `${ARTIFACTS_DIR}/gh_issue_*.md` (there should be exactly one)
- This file contains the full issue details including title, description, labels, and metadata

Task:
1. Locate and read the `${ARTIFACTS_DIR}/gh_issue_*.md` file
2. Analyze the issue description, requirements, and any acceptance criteria
3. Break down the work into concrete, actionable tasks
4. Create a development plan with clear milestones

Deliverables:
1. `PLAN.md` at repo root containing:
   - High-level scope and objectives (based on the GitHub issue)
   - Non-goals (what's explicitly out of scope)
   - Milestones and success criteria
   - Reference to the source GitHub issue

2. `tasks.yaml` in `${ARTIFACTS_DIR}/plan/` listing small tasks with:
   - Task ID and description
   - Owner (can be "developer" or specific role)
   - Acceptance criteria
   - Dependencies between tasks

3. Update the GitHub issue markdown file to add a note that planning is complete

Format for PLAN.md:
```markdown
# Development Plan for Issue #${ISSUE_NUMBER}

**Source:** GitHub Issue #${ISSUE_NUMBER} - ${ISSUE_TITLE}

## Scope
${HIGH_LEVEL_DESCRIPTION}

## Non-Goals
- Items explicitly out of scope

## Milestones
1. Milestone 1
2. Milestone 2

## Success Criteria
- Criteria for completion
```

Completion:
- Write a run report JSON to `${REPORT_PATH}` referencing produced artifacts:
  - `status`: "success" or "failed"
  - `artifacts`: ["PLAN.md", "${ARTIFACTS_DIR}/plan/tasks.yaml"]
  - `source_issue`: issue number
