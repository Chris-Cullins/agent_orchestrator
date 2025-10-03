# PR Merger Agent

Goal: Merge approved PRs and clean up branches.

Tasks:
1. Read the list of fixed PRs from `${ARTIFACTS_DIR}/pr_reviews/fixes.json`
   - If file doesn't exist, fail gracefully with helpful error message
   - Validate JSON schema before processing
2. For each PR that was fixed:
   - Fetch complete PR metadata: `gh pr view <PR_NUMBER> --json state,mergeable,mergeStateStatus,statusCheckRollup,headRefName,baseRefName,headRefOid`
   - Check if the PR is mergeable and all checks have passed
   - If mergeable:
     - Merge the PR: `gh pr merge <PR_NUMBER> --squash --delete-branch --auto`
     - Or if auto-merge is not available:
       ```bash
       # Merge PR and delete branch
       gh pr merge <PR_NUMBER> --squash
       BRANCH_NAME=$(gh pr view <PR_NUMBER> --json headRefName --jq '.headRefName')
       git push origin --delete "$BRANCH_NAME"
       ```
   - If not mergeable because `mergeStateStatus` is `DRAFT`, `BLOCKED`, or checks failed:
     - Fallback to previously documented behavior: log the reason, comment with the blocking issue, and skip.
   - If not mergeable because `mergeStateStatus` is `CONFLICTING` or `DIRTY` due to an out-of-date branch:
     - Attempt to self-resolve and merge instead of skipping.
     - Prepare a clean workspace (new git worktree or temporary branch) so the default branch stays untouched.
     - Update local refs: `git fetch origin <baseRefName> <headRefName>`
     - Check out the head branch (e.g., `git checkout -B pr-<PR_NUMBER>-merge <headRefName> origin/<headRefName>`)
     - Merge the latest base into the PR branch: `git merge origin/<baseRefName>`
     - If conflicts arise, resolve them inside the workspace (edit files, use tests, etc.) until `git status` is clean.
       - Prefer minimal, targeted conflict resolution; if unsure, consult the PR description and surrounding context.
       - Re-run `git status` to confirm no unresolved conflicts remain.
     - Once resolved, commit the merge with a descriptive message (e.g., `git commit -am "Resolve merge conflicts for PR <PR_NUMBER>"`).
     - Push the updated branch: `git push origin HEAD:<headRefName>`
     - Re-check mergeability via `gh pr view ...`. If now mergeable, proceed with the merge step above.
     - If the merge is still blocked after attempting auto-resolution, log the reason and comment on the PR explaining why manual intervention is required.

Deliverables:
- Merged PRs with deleted branches
- Summary in `${ARTIFACTS_DIR}/pr_reviews/merged.json` with:
  - Successfully merged PRs
  - Failed merges with reasons
  - Deleted branches

Completion:
- Write a run report JSON to `${REPORT_PATH}` with merge summary.
