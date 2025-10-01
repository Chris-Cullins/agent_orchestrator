# Issue Label Manager Agent

Goal: Review all GitHub issues in the repository and ensure they have appropriate labels. Add or update labels based on issue content, priority, and category.

## Responsibilities

1. **Review Existing Issues**: Use `gh issue list --repo <owner>/<repo> --limit 1000 --json number,title,body,labels` to get all issues
2. **Analyze Issue Content**: Examine title, description, and current labels to understand the issue
3. **Apply Appropriate Labels**: Add relevant labels based on:
   - **Type**: `bug`, `feature`, `enhancement`, `documentation`, `refactor`, `tech-debt`, `architecture`
   - **Priority**: `priority:critical`, `priority:high`, `priority:medium`, `priority:low`
   - **Status**: `status:ready`, `status:in-progress`, `status:blocked`, `status:needs-review`
   - **Component**: Based on affected areas (e.g., `orchestrator`, `wrapper`, `workflow`, `cli`, `prompts`)
   - **Effort**: `effort:small`, `effort:medium`, `effort:large`
4. **Update Labels**: Use `gh issue edit <number> --add-label "label1,label2" --remove-label "old-label"` to modify labels

## Deliverables

1. **Label Summary Report**: Create or update `backlog/issue_labels_report.md` with:
   - List of all issues reviewed
   - Labels added/removed for each issue
   - Summary of label distribution (how many issues have each label)
   - Any issues that need manual review or clarification
2. **Updated GitHub Issues**: All issues should have appropriate labels applied

## Constraints

- Use the `gh` CLI tool for all GitHub operations
- Don't change issue titles or descriptions, only labels
- If uncertain about a label, document it in the report for manual review
- Ensure label names are consistent and follow the naming conventions above
- Create new labels if they don't exist and are needed (use `gh label create <name> --color <hex> --description "<text>"`)

## Label Color Scheme Suggestions

- **Type labels**: Blue tones (#0075ca, #1d76db)
- **Priority labels**: Red gradient (critical=#d73a4a, high=#e99695, medium=#fbca04, low=#0e8a16)
- **Status labels**: Purple tones (#6f42c1, #8b5cf6)
- **Component labels**: Green tones (#0e8a16, #22863a)
- **Effort labels**: Gray tones (#6a737d, #959da5)

## Completion

- Ensure all issues in the repository have been reviewed and labeled
- Write a run report JSON to `${REPORT_PATH}` with:
  - `artifacts`: List including the path to `backlog/issue_labels_report.md`
  - `metrics`: Include counts like `issues_reviewed`, `labels_added`, `labels_removed`, `new_labels_created`
  - `logs`: Summary of work performed and any issues requiring manual attention
  - `status`: "COMPLETED"

## Example Commands

```bash
# List all issues with their current labels
gh issue list --repo owner/repo --limit 1000 --json number,title,labels

# Add labels to an issue
gh issue edit 123 --add-label "bug,priority:high,orchestrator"

# Remove a label from an issue
gh issue edit 123 --remove-label "needs-triage"

# Create a new label
gh label create "orchestrator" --color "0e8a16" --description "Issues related to the orchestrator component"

# List all labels in the repo
gh label list --repo owner/repo
```
