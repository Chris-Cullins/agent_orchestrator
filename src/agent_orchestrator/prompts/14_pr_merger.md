# PR Merger Agent

Goal: Merge approved PRs and clean up branches.

Tasks:
1. Read the list of fixed PRs from `.agents/pr_reviews/fixes.json`
   - If file doesn't exist, fail gracefully with helpful error message
   - Validate JSON schema before processing
2. For each PR that was fixed:
   - Verify PR status: `gh pr view <PR_NUMBER> --json state,mergeable,statusCheckRollup`
   - Check if PR is mergeable and all checks have passed
   - If mergeable:
     - Merge the PR: `gh pr merge <PR_NUMBER> --squash --delete-branch --auto`
     - Or if auto-merge not available:
       ```bash
       # Merge PR and delete branch
       gh pr merge <PR_NUMBER> --squash
       BRANCH_NAME=$(gh pr view <PR_NUMBER> --json headRefName --jq '.headRefName')
       git push origin --delete "$BRANCH_NAME"
       ```
   - If not mergeable:
     - Log the reason and skip
     - Post a comment: `gh pr comment <PR_NUMBER> --body "Cannot auto-merge: <reason>"`

Deliverables:
- Merged PRs with deleted branches
- Summary in `.agents/pr_reviews/merged.json` with:
  - Successfully merged PRs
  - Failed merges with reasons
  - Deleted branches

Completion:
- Write a run report JSON to `${REPORT_PATH}` with merge summary.
