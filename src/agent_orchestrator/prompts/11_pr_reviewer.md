# PR Reviewer Agent

Goal: Fetch all existing review comments from open PRs in the repository.

Tasks:
1. Initialize working directory: `mkdir -p ${ARTIFACTS_DIR}/pr_reviews`
2. Use `gh pr list --state open` to get all open PRs
   - If `gh` command fails, report error and provide troubleshooting guidance
3. For each open PR:
   - Use `gh pr view <PR_NUMBER>` to get PR details
   - Use `gh api repos/{owner}/{repo}/pulls/<PR_NUMBER>/comments` to fetch all existing review comments
   - Collect all comments with their context (file, line, body)

Deliverables:
- Summary report in `${ARTIFACTS_DIR}/pr_reviews/summary.json` with:
  - List of reviewed PRs
  - All existing review comments per PR
  - File paths and line numbers for each comment

Completion:
- Write a run report JSON to `${REPORT_PATH}` with collected comments summary.
