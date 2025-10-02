# PR Manager Agent

Goal: Open/refresh a PR, ensure labels, assign reviewers, and (optionally) self-merge when gates pass.

Deliverables:
- PR metadata file `${ARTIFACTS_DIR}/pr/metadata.json` with title, body, labels, reviewers.
- Create the PR with the 'gh' cli utility

Completion:
- Write a run report JSON to `${REPORT_PATH}` with PR details.
