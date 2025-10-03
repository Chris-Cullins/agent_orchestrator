# GitHub Issue Fetcher Agent

Goal: Fetch a GitHub issue and save its content for downstream workflow processing.

Input:
- `ISSUE_NUMBER` environment variable containing the GitHub issue number to fetch
- Repository context from the current working directory
- `ARTIFACTS_DIR` environment variable pointing at `.agents/runs/<run_id>/artifacts/`
- `ISSUE_MARKDOWN_PATH` and `ISSUE_MARKDOWN_DIR` convenience variables (already resolved by the orchestrator)

Task:
1. Resolve the issue markdown path (use `${ISSUE_MARKDOWN_PATH}` when set, otherwise fall back to `${ARTIFACTS_DIR}/gh_issue_${ISSUE_NUMBER}.md`) and ensure its directory exists:
   ```bash
   ISSUE_FILE="${ISSUE_MARKDOWN_PATH:-${ARTIFACTS_DIR}/gh_issue_${ISSUE_NUMBER}.md}"
   mkdir -p "$(dirname "${ISSUE_FILE}")"
   ```
2. Use `gh issue view ${ISSUE_NUMBER} --json number,title,body,labels,assignees,milestone,state,createdAt,updatedAt` to fetch the issue details
3. Extract and format the issue information into a structured markdown file written to `${ISSUE_FILE}`
4. Resolve the relative path for the run report using `${REPO_DIR}` (e.g., `python - <<'PY'`).

Deliverables:
1. `gh_issue_${ISSUE_NUMBER}.md` saved to `${ARTIFACTS_DIR}` containing:
   - Issue number and title
   - Issue state and creation/update timestamps
   - Labels, assignees, and milestone (if any)
   - Full issue body/description
   - Clear section headers for each component

Format the file like this:
```markdown
# GitHub Issue #${ISSUE_NUMBER}: ${TITLE}

**State:** ${STATE}
**Created:** ${CREATED_AT}
**Updated:** ${UPDATED_AT}

## Labels
- label1
- label2

## Assignees
- @user1
- @user2

## Milestone
${MILESTONE_NAME}

## Description
${BODY}
```

Completion:
- Write a run report JSON to `${REPORT_PATH}` with:
  - `status`: "success" or "failed"
  - `issue_number`: the issue number fetched
  - `output_file`: relative path (from `${REPO_DIR}`) to the generated markdown file inside `${ARTIFACTS_DIR}`
  - `artifacts`: ["${output_file}"] using the same relative path so downstream steps can locate the file
  - `issue_title`: the issue title
