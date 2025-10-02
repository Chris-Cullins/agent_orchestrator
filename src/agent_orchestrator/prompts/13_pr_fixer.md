# PR Fixer Agent

Goal: Fix issues identified in PR review comments and commit changes back to the PR branch.

**IMPORTANT SAFETY NOTES:**
- This agent makes automated commits and pushes to PR branches
- Always verify the current branch state before checkout to prevent race conditions
- Review all changes carefully before committing
- Consider using a dry-run mode or requiring human approval for critical changes

Tasks:
1. Read TODO items from `${ARTIFACTS_DIR}/pr_reviews/todos.json`
   - If file doesn't exist, fail gracefully with helpful error message
   - Validate JSON schema before processing
2. For each PR with TODOs:
   - Verify current git state: `git status --porcelain` (should be clean)
   - Use `gh pr view <PR_NUMBER> --json headRefName --jq '.headRefName'` to get the branch name
   - Checkout the PR branch: `git fetch origin && git checkout <branch_name>`
   - For each TODO item:
     - Read the relevant file and understand the context
     - Implement the fix based on the review comment
     - Test the change if applicable
   - Stage and commit all changes with a descriptive message referencing the review comments
   - **HUMAN VERIFICATION**: Pause here if `--pause-for-human-input` is enabled
   - Push changes back to the PR branch: `git push origin <branch_name>`
   - Post a comment on the PR indicating fixes have been applied: `gh pr comment <PR_NUMBER> --body "Applied fixes for review comments"`

Deliverables:
- Code changes committed to each PR branch
- Comments on PRs indicating fixes applied
- Summary in `${ARTIFACTS_DIR}/pr_reviews/fixes.json` with:
  - PRs fixed
  - Number of TODOs addressed per PR
  - Commit SHAs

Completion:
- Write a run report JSON to `${REPORT_PATH}` with fix summary.
- Return to main branch: `git checkout main`
