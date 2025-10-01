# CI History Miner Agent

Goal: Mine CI/CD pipeline history to identify intermittent test failures and collect failure patterns.

## Deliverables

- Analysis report in `.agents/flaky_tests/ci_analysis.json` containing:
  - List of tests with intermittent failures (passed sometimes, failed other times)
  - Failure frequency and rate for each test
  - Recent failure timestamps and commit SHAs
  - Error messages and stack traces from failures
  - Environmental context (OS, browser, runner, etc.)
- Summary report in `.agents/flaky_tests/summary.md` with:
  - Top 10 most flaky tests
  - Flakiness trends over time
  - Potential patterns (time-based, environment-specific, etc.)

## Data Sources

Analyze the following sources for test failures:
1. **Git repository**: Search commit history for test-related commits and reverts
2. **CI logs**: Parse logs in `.github/workflows/`, `.circleci/`, `jenkins/`, etc.
3. **Test reports**: Look for JUnit XML, JSON test reports, or test runner output
4. **Issue tracker**: Search GitHub issues/PRs for test flakiness mentions
5. **Local test runs**: Check for local test result artifacts

## Analysis Criteria

A test is considered "flaky" if:
- It has both passed and failed runs on the same commit
- Failure rate is between 1% and 95% (not consistently failing)
- Same test name appears in multiple failure reports with different outcomes
- Test was re-run and succeeded after initial failure

## Constraints

- Look back at least 30 days of CI history (or last 100 builds)
- Focus on actual test failures, not infrastructure issues
- Capture full context: test name, file path, error message, stack trace
- Rate limit API calls to CI providers (e.g., GitHub Actions, CircleCI)
- If no CI history is accessible, document limitations in report

## Completion

Write a run report JSON to `${REPORT_PATH}` with:
```json
{
  "status": "success",
  "flaky_tests_found": 15,
  "total_test_runs_analyzed": 450,
  "analysis_period_days": 30,
  "artifacts": [
    ".agents/flaky_tests/ci_analysis.json",
    ".agents/flaky_tests/summary.md"
  ],
  "notes": "Analyzed GitHub Actions workflow runs for main branch"
}
```
