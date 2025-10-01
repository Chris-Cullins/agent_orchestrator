# PR Merger Agent

Goal: Merge approved PRs and clean up branches.

Tasks:
1. Read the list of fixed PRs from `.agents/pr_reviews/fixes.json`
2. For each PR that was fixed:
   - Verify PR status: `gh pr view <PR_NUMBER> --json state,mergeable,statusCheckRollup`
   - Check if PR is mergeable and all checks have passed
   - If mergeable:
     - Merge the PR: `gh pr merge <PR_NUMBER> --squash --delete-branch --auto`
     - Or if auto-merge not available: `gh pr merge <PR_NUMBER> --squash && gh pr view <PR_NUMBER> --json headRefName --jq '.headRefName' | xargs git push origin --delete`
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
