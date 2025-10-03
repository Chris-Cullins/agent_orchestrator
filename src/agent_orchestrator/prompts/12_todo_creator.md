# TODO Creator Agent

Goal: Extract review comments from PRs and create actionable TODO items.

Tasks:
1. Look at all open PRs on the target github repo:
   - Use `gh api repos/{owner}/{repo}/pulls/<PR_NUMBER>/comments` to fetch all existing review comments
   - Collect all comments with their context (file, line, body)
   - Parse review comments to identify actionable items
   - Create TODO entries for each issue that needs to be fixed
2. Organize TODOs by:
   - PR number
   - File and line number (if applicable)
   - Priority (critical, high, medium, low)
   - Category (bug, style, security, performance, documentation, testing)

Deliverables:
- `${ARTIFACTS_DIR}/pr_reviews/todos.json` containing structured TODO items:
  ```json
  {
    "pr_<number>": [
      {
        "id": "todo_1",
        "pr_number": 123,
        "file": "path/to/file.py",
        "line": 45,
        "priority": "high",
        "category": "bug",
        "description": "Fix null pointer issue...",
        "comment_url": "https://github.com/..."
      }
    ]
  }
  ```

Completion:
- Write a run report JSON to `${REPORT_PATH}` with TODO creation summary.
