# Test Quarantine Manager Agent

Goal: Quarantine tests that remain flaky after rewriting attempts, preventing them from blocking CI while tracking them for future resolution.

## Input

Read from previous steps:
- `.agents/runs/{run_id}/artifacts/flaky_tests/rewrites.json` - Tests that were rewritten and tests flagged for review
- `.agents/runs/{run_id}/artifacts/flaky_tests/flake_patterns.json` - Original flakiness analysis

## Deliverables

- Quarantine configuration applied to stubborn tests:
  - Mark tests with `.skip()` or `.todo()` in test files
  - OR move tests to separate quarantine suite (e.g., `tests/quarantine/`)
  - OR update test framework config to skip specific tests
- Quarantine tracking file in `.agents/runs/{run_id}/artifacts/flaky_tests/quarantine.json` containing:
  - List of quarantined tests with metadata
  - Reason for quarantine
  - Original failure rate and patterns
  - Links to related issues/tickets
  - Quarantine date and review schedule
- GitHub issues created for each quarantined test (or update existing)
- Summary report in `.agents/runs/{run_id}/artifacts/flaky_tests/quarantine_summary.md`

## Quarantine Criteria

Quarantine a test if:
- It was flagged for human review due to complexity
- Rewriting failed to reduce flakiness below 1%
- The test requires architectural changes to the application
- The test depends on external factors outside our control
- Fix attempts have been exhausted (test was rewritten but still fails intermittently)

## Quarantine Strategy

Choose the appropriate quarantine method based on test framework:

### Jest/Vitest
```javascript
test.skip('flaky test name', () => {
  // test body
});
// Or add to jest.config.js testPathIgnorePatterns
```

### Playwright/Cypress
```javascript
test.skip('flaky test name', () => {
  // test body
});
// Or use test.fixme() for known broken tests
```

### PyTest
```python
@pytest.mark.skip(reason="Quarantined: intermittent failure - Issue #123")
def test_flaky():
    # test body
```

### RSpec
```ruby
xit 'flaky test name' do
  # test body
end
# Or use :skip metadata
```

## Tracking and Documentation

For each quarantined test, create/update:

1. **Quarantine record** in `.agents/runs/{run_id}/artifacts/flaky_tests/quarantine.json`:
```json
{
  "test_name": "e2e/checkout.spec.ts > checkout flow > completes payment",
  "file": "e2e/checkout.spec.ts",
  "quarantined_at": "2025-10-01T12:34:56Z",
  "reason": "Race condition in payment provider mock - requires app refactor",
  "failure_rate": "15%",
  "root_cause": "timing_issue",
  "issue_url": "https://github.com/org/repo/issues/456",
  "review_date": "2025-11-01",
  "attempts": [
    "Added waits for payment confirmation",
    "Increased timeout to 10s",
    "Still fails intermittently on CI"
  ]
}
```

2. **GitHub Issue** with:
   - Title: `[Flaky Test] Test name`
   - Labels: `flaky-test`, `quarantined`, priority label
   - Description with:
     - Test location and purpose
     - Failure patterns and frequency
     - Root cause analysis
     - Fix attempts made
     - Recommended next steps
     - Links to CI failures and analysis reports

3. **Test code comment**:
```javascript
// QUARANTINED: 2025-10-01
// Reason: Race condition in payment provider mock
// Issue: https://github.com/org/repo/issues/456
// Review: 2025-11-01
test.skip('completes payment', () => {
  // ...
});
```

## Review Schedule

Set review dates based on quarantine reason:
- **Infrastructure issues**: 7 days (may resolve with CI updates)
- **External dependencies**: 14 days (may resolve with API fixes)
- **Architectural changes needed**: 30 days (requires planning)
- **Unknown root cause**: 14 days (requires investigation)

## CI Configuration

Update CI configuration to:
- Exclude quarantined tests from required checks
- Run quarantined tests in separate optional job
- Report on quarantine status in CI summary
- Alert if quarantine queue grows beyond threshold (e.g., > 10 tests)

## Constraints

- Don't delete test code - quarantine is temporary
- Maintain test coverage metrics excluding quarantined tests
- Ensure quarantine doesn't mask real regressions
- Set up periodic review process (monthly quarantine review)
- Track quarantine velocity: tests entering vs. exiting quarantine

## Notifications

- Create Slack/email notification for team about quarantined tests
- Include summary of what was quarantined and why
- Provide links to issues and analysis reports
- Suggest owners for follow-up based on code ownership

## Completion

Write a run report JSON to `${REPORT_PATH}` with:
```json
{
  "status": "success",
  "tests_quarantined": 4,
  "quarantine_method": "test.skip with tracking issues",
  "issues_created": [
    "https://github.com/org/repo/issues/456",
    "https://github.com/org/repo/issues/457",
    "https://github.com/org/repo/issues/458",
    "https://github.com/org/repo/issues/459"
  ],
  "tests_fixed": 11,
  "total_flaky_tests_resolved": 11,
  "artifacts": [
    ".agents/runs/{run_id}/artifacts/flaky_tests/quarantine.json",
    ".agents/runs/{run_id}/artifacts/flaky_tests/quarantine_summary.md"
  ],
  "notes": "4 tests quarantined pending architectural changes. 11 tests successfully fixed and verified stable.",
  "next_review_date": "2025-11-01"
}
```

## Success Metrics

Track and report:
- Total tests analyzed: X
- Tests fixed: Y
- Tests quarantined: Z
- Estimated CI stability improvement: W% (based on failure rate reduction)
- Recommended next actions for the team
