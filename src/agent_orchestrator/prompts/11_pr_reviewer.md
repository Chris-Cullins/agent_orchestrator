# PR Reviewer Agent

Goal: Review all open PRs in the repository and provide detailed feedback as comments.

Tasks:
1. Use `gh pr list --state open` to get all open PRs
2. For each open PR:
   - Use `gh pr view <PR_NUMBER>` to get PR details
   - Use `gh pr diff <PR_NUMBER>` to review the changes
   - Analyze the code for:
     - Code quality and best practices
     - Potential bugs or edge cases
     - Security vulnerabilities
     - Performance issues
     - Documentation gaps
     - Test coverage
   - Post review comments using `gh pr review <PR_NUMBER> --comment --body "<comment>"`
   - For specific line comments, use `gh pr comment <PR_NUMBER> --body "<comment>"`

Deliverables:
- Review comments posted on each open PR
- Summary report in `.agents/pr_reviews/summary.json` with:
  - List of reviewed PRs
  - Number of comments per PR
  - Key issues identified

Completion:
- Write a run report JSON to `${REPORT_PATH}` with review summary.
