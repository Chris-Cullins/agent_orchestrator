# TODO Creator Agent

Goal: Extract review comments from PRs and create actionable TODO items.

Tasks:
1. Read the summary from `.agents/pr_reviews/summary.json`
   - If file doesn't exist, fail gracefully with helpful error message
   - Validate JSON schema before processing
   - Handle missing or malformed data gracefully
2. For each PR that was reviewed:
   - Use `gh pr view <PR_NUMBER> --comments` to get all comments
   - Parse review comments to identify actionable items
   - Create TODO entries for each issue that needs to be fixed
3. Organize TODOs by:
   - PR number
   - File and line number (if applicable)
   - Priority (critical, high, medium, low)
   - Category (bug, style, security, performance, documentation, testing)

Deliverables:
- `.agents/pr_reviews/todos.json` containing structured TODO items:
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
