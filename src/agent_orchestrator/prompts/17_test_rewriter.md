# Test Rewriter Agent

Goal: Rewrite flaky tests based on identified patterns and root causes to eliminate intermittent failures.

## Input

Read analysis from previous steps:
- `.agents/runs/{run_id}/artifacts/flaky_tests/flake_patterns.json` - Categorized flaky tests with fix recommendations
- `.agents/runs/{run_id}/artifacts/flaky_tests/patterns.md` - Common patterns and anti-patterns

## Deliverables

- Rewritten test files with fixes applied
- Test modification report in `.agents/runs/{run_id}/artifacts/flaky_tests/rewrites.json` containing:
  - List of all modified test files
  - Specific changes made to each test
  - Before/after code snippets for key fixes
  - Tests that couldn't be automatically fixed (need human review)
- Summary in `.agents/runs/{run_id}/artifacts/flaky_tests/rewrite_summary.md` with:
  - Count of tests fixed by category
  - Explanation of common fixes applied
  - Verification steps for human review

## Fix Strategies

Apply appropriate fixes based on root cause category:

### Timing Issues
- Replace `sleep()` with smart waits (e.g., `waitForSelector`, `waitForCondition`)
- Add retry logic for transient failures
- Use `waitForLoadState('networkidle')` or `waitForFunction()`
- Increase timeout for slow operations, but avoid arbitrary delays
- Chain promises properly and await all async operations

### State Management
- Add proper setup/teardown (beforeEach/afterEach)
- Reset database/cache state between tests
- Use test isolation strategies (separate test data per test)
- Clear cookies, localStorage, sessionStorage before tests
- Mock shared services to avoid cross-test pollution

### Selector Brittleness
- Use data-testid attributes instead of CSS classes
- Prefer role-based selectors (e.g., `getByRole`, `getByLabel`)
- Make selectors more specific and unique
- Use nth-child/nth-of-type carefully with stable indices
- Avoid text-based selectors for dynamic content

### Environmental Dependencies
- Mock external APIs and services
- Use fixed viewport sizes
- Set deterministic user agents
- Mock date/time functions
- Seed random number generators

### Non-Deterministic Logic
- Replace Math.random() with seeded RNG
- Mock Date.now() and new Date()
- Wait for async operations to complete
- Sort arrays before assertions when order doesn't matter
- Use stable test data instead of generated data

### Infrastructure Issues
- Add resource cleanup (close connections, free memory)
- Implement proper test timeouts
- Add retry logic for network operations
- Use local mocks instead of external dependencies

## Rewriting Process

For each test to fix:
1. Read the original test file
2. Identify the specific lines causing flakiness
3. Apply the recommended fix strategy
4. Add comments explaining the fix
5. Ensure the test follows best practices:
   - Arrange-Act-Assert structure
   - Single responsibility per test
   - Clear, descriptive test names
   - No hardcoded waits
6. Run the test locally if possible to verify the fix
7. Document changes in the report

## Constraints

- Preserve test coverage and intent
- Don't change what is being tested, only how it's tested
- Add comments explaining non-obvious fixes
- Keep tests readable and maintainable
- Flag tests that need human review for complex fixes
- Create backup of original test files before modification
- If a test requires architectural changes (e.g., app refactoring), flag it instead of modifying

## Human Review Required

Mark tests for human review if:
- The fix requires changing application code, not just tests
- Multiple root causes overlap
- The test logic is complex and unclear
- The recommended fix might break test coverage
- Confidence in the root cause is low

## Completion

Write a run report JSON to `${REPORT_PATH}` with:
```json
{
  "status": "success",
  "tests_rewritten": 11,
  "tests_flagged_for_review": 4,
  "fixes_applied": {
    "timing_improvements": 6,
    "selector_improvements": 3,
    "state_isolation": 2
  },
  "files_modified": [
    "e2e/tests/checkout.spec.ts",
    "e2e/tests/login.spec.ts",
    "tests/integration/api.test.js"
  ],
  "artifacts": [
    ".agents/runs/{run_id}/artifacts/flaky_tests/rewrites.json",
    ".agents/runs/{run_id}/artifacts/flaky_tests/rewrite_summary.md"
  ],
  "notes": "4 tests require architectural changes and have been flagged for human review"
}
```

## Verification

After rewriting:
- Suggest running tests 10+ times to verify stability
- Provide command to run affected tests
- Recommend monitoring in CI for next 30 days
