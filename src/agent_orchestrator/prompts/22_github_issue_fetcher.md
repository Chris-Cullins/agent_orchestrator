# GitHub Issue Fetcher Agent

Goal: Fetch a GitHub issue and save its content for downstream workflow processing.

Input:
- `ISSUE_NUMBER` environment variable containing the GitHub issue number to fetch
- Repository context from the current working directory

Task:
1. Use `gh issue view ${ISSUE_NUMBER} --json number,title,body,labels,assignees,milestone,state,createdAt,updatedAt` to fetch the issue details
2. Extract and format the issue information into a structured markdown file

Deliverables:
1. `gh_issue_${ISSUE_NUMBER}.md` in /backlog/ containing:
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
  - `output_file`: path to the generated markdown file
  - `issue_title`: the issue title
