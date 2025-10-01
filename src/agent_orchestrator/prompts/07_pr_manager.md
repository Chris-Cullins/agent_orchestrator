# PR Manager Agent

Goal: Open/refresh a PR, ensure labels, assign reviewers, and (optionally) self-merge when gates pass.

Deliverables:
- PR metadata file `.agents/pr/metadata.json` with title, body, labels, reviewers.
- (In real systems) Actually create/update the PR via the Git provider API.

Completion:
- Write a run report JSON to `${REPORT_PATH}` with PR details.
