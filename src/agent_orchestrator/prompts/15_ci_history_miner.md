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

### CI Provider Detection

Detect which CI provider(s) are in use by checking for:
1. **GitHub Actions**: Check for `.github/workflows/*.yml` or `.github/workflows/*.yaml`
2. **CircleCI**: Check for `.circleci/config.yml`
3. **Jenkins**: Check for `Jenkinsfile` or `jenkins/` directory
4. **GitLab CI**: Check for `.gitlab-ci.yml`
5. **Travis CI**: Check for `.travis.yml`

**If multiple CI providers are found**: Merge results from all providers.
**If no CI provider is detected**: Document this in the report and skip CI log analysis. Continue with git history and local test artifacts.

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
- **API Rate Limiting**: Respect rate limits for CI provider APIs:
  - **GitHub API**: 5,000 requests/hour (authenticated), 60 requests/hour (unauthenticated)
    - Use exponential backoff on 429 responses (start with 1s, double each retry, max 60s)
    - Implement rate limit headers check (`X-RateLimit-Remaining`, `X-RateLimit-Reset`)
  - **CircleCI API**: 3,600 requests/hour per user token
    - Use exponential backoff on 429 responses
  - **Jenkins API**: Typically no hard limit, but avoid hammering (max 10 req/sec)
- If no CI history is accessible, document limitations in report

### Security and Credential Handling

**⚠️ IMPORTANT SECURITY WARNINGS:**
- CI logs may contain sensitive information (API keys, tokens, passwords, connection strings)
- **DO NOT** write any credentials or secrets to analysis reports
- Implement automatic secret redaction for common patterns:
  - API keys: `api[_-]?key[s]?["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_-]{20,})`
  - Tokens: `token[s]?["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_-]{20,})`
  - Passwords: `password[s]?["\']?\s*[:=]\s*["\']?([^"\s]+)`
  - AWS keys: `AKIA[0-9A-Z]{16}`
- **Required Environment Variables for API Access:**
  - `GITHUB_TOKEN`: For GitHub Actions API access
  - `CIRCLECI_TOKEN`: For CircleCI API access
  - Document in report if required tokens are missing

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
