# PR Manager Agent

Goal: Open/refresh a PR, ensure labels, assign reviewers, and (optionally) self-merge when gates pass.
- Also, check if this work was to fix a github issue, and if so, make sure and mention it in the PR. 

Deliverables:
- PR metadata file `${ARTIFACTS_DIR}/pr/metadata.json` with title, body, labels, reviewers.
- Create the PR with the 'gh' cli utility

Completion:
- Write a run report JSON to `${REPORT_PATH}` with PR details.
