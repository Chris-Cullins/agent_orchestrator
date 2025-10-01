# Cleanup Step

## Objective
Clean up all temporary files and artifacts created during this workflow run to prepare for the next execution.

## Tasks

1. **Remove temporary workflow files:**
   - Delete `PLAN.md` (planning document from step 1)
   - Delete the tasks.yaml file from this run.
   - Delete any left over REVIEW.md file from the code review step.
   - Delete any other temporary files created during the workflow
   - Look for files with temporary naming patterns (e.g., `.tmp`, `.bak`, etc.)

2. **Clean up test artifacts:**
   - Remove temporary test data or fixtures if created
   - Clean up any test output files or logs

3. **Verify cleanup:**
   - Run `git status` to ensure only intended changes remain
   - List any files that were removed

## Important Notes
- Do NOT remove files that are part of the actual implementation
- Do NOT remove the code changes, tests, or documentation updates
- Only remove temporary/intermediate files created for orchestration purposes
- Be careful not to delete files tracked in version control unless they were specifically created as temporary files

## Success Criteria
- All temporary workflow files removed
- Working directory is clean except for the actual implementation changes
- Ready for next workflow execution
