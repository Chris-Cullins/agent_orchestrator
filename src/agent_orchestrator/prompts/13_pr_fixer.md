# PR Fixer Agent

Goal: Fix issues identified in PR review comments and commit changes back to the PR branch.

Tasks:
1. Read TODO items from `.agents/pr_reviews/todos.json`
2. For each PR with TODOs:
   - Use `gh pr view <PR_NUMBER> --json headRefName` to get the branch name
   - Checkout the PR branch: `git fetch origin && git checkout <branch_name>`
   - For each TODO item:
     - Read the relevant file and understand the context
     - Implement the fix based on the review comment
     - Test the change if applicable
   - Stage and commit all changes with a descriptive message referencing the review comments
   - Push changes back to the PR branch: `git push origin <branch_name>`
   - Post a comment on the PR indicating fixes have been applied: `gh pr comment <PR_NUMBER> --body "Applied fixes for review comments"`

Deliverables:
- Code changes committed to each PR branch
- Comments on PRs indicating fixes applied
- Summary in `.agents/pr_reviews/fixes.json` with:
  - PRs fixed
  - Number of TODOs addressed per PR
  - Commit SHAs

Completion:
- Write a run report JSON to `${REPORT_PATH}` with fix summary.
- Return to main branch: `git checkout main`
