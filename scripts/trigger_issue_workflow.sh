#!/bin/bash
# Trigger script for issue workflow
# Called by the polling service when an issue matches criteria
#
# Environment variables provided by the poller:
#   POLL_SOURCE_TYPE - Source type (e.g., "github_issues")
#   POLL_ITEM_ID     - Item identifier (e.g., issue number)
#   POLL_ITEM_URL    - Full URL to the item
#   POLL_REPO        - Repository (for GitHub)
#   ISSUE_NUMBER     - Same as POLL_ITEM_ID (GitHub-specific)
#
# Additional variables from poll config on_match.env:
#   WORKFLOW         - Path to workflow file
#   WRAPPER          - Path to wrapper script
#   DAILY_COST_LIMIT - Cost limit for the run

set -e

echo "Triggering workflow for issue #${ISSUE_NUMBER}"
echo "  Source: ${POLL_SOURCE_TYPE}"
echo "  URL: ${POLL_ITEM_URL}"
echo "  Workflow: ${WORKFLOW}"

python3 -m agent_orchestrator.cli run \
  --repo . \
  --workflow "${WORKFLOW}" \
  --wrapper "${WRAPPER}" \
  --issue-number "${ISSUE_NUMBER}" \
  --git-worktree \
  --git-worktree-branch "feat/issue-${ISSUE_NUMBER}" \
  --daily-cost-limit "${DAILY_COST_LIMIT:-50.00}" \
  --cost-limit-action warn \
  --log-level INFO
