# Flake Analyzer Agent

Goal: Analyze identified flaky tests to determine root causes and classify failure patterns.

## Input

Read the CI analysis report from the previous step:
- `.agents/flaky_tests/ci_analysis.json` - List of flaky tests with failure data

## Deliverables

- Detailed analysis report in `.agents/flaky_tests/flake_patterns.json` containing:
  - Classification of each flaky test by root cause category
  - Specific failure patterns (timing issues, race conditions, data dependencies, etc.)
  - Recommendations for fixes (e.g., add waits, fix selectors, isolate state)
  - Priority ranking (high/medium/low) based on impact and fix difficulty
- Pattern analysis in `.agents/flaky_tests/patterns.md` with:
  - Common anti-patterns found across tests
  - Shared failure characteristics
  - Suggested refactoring approaches

## Root Cause Categories

Classify flaky tests into these categories:

1. **Timing Issues**
   - Fixed sleeps instead of dynamic waits
   - Race conditions between events
   - Async operations not properly awaited
   - Network request timing dependencies

2. **State Management**
   - Shared state between tests
   - Missing setup/teardown
   - Database not properly reset
   - Cache pollution

3. **Selector Brittleness**
   - CSS selectors that match multiple elements
   - XPath expressions dependent on dynamic content
   - IDs or classes that change
   - Reliance on text content that varies

4. **Environmental Dependencies**
   - Tests that depend on specific screen resolution
   - Browser-specific behavior
   - OS-specific file paths or timing
   - Network conditions or external services

5. **Non-Deterministic Logic**
   - Random data without seeding
   - Date/time dependencies without mocking
   - Iteration order assumptions
   - Unordered async operations

6. **Infrastructure Issues**
   - Resource exhaustion (memory, CPU, disk)
   - CI runner inconsistencies
   - Network timeouts
   - Third-party service flakiness

## Analysis Process

For each flaky test:
1. Review error messages and stack traces
2. Examine the test code and identify potential issues
3. Check for common anti-patterns in the test category
4. Analyze failure frequency and conditions
5. Assign a root cause category and confidence level
6. Provide specific fix recommendations
7. Estimate fix difficulty (easy/medium/hard)

## Constraints

- Analyze test source code to understand implementation
- Cross-reference error patterns across multiple tests
- Provide actionable, specific recommendations (not generic advice)
- Flag tests that may require deep investigation
- Identify tests that share common problems for batch fixes

## Completion

Write a run report JSON to `${REPORT_PATH}` with:
```json
{
  "status": "success",
  "tests_analyzed": 15,
  "patterns_identified": {
    "timing_issues": 6,
    "state_management": 4,
    "selector_brittleness": 3,
    "environmental": 1,
    "non_deterministic": 1
  },
  "high_priority_fixes": 4,
  "artifacts": [
    ".agents/flaky_tests/flake_patterns.json",
    ".agents/flaky_tests/patterns.md"
  ],
  "notes": "Identified 3 tests sharing the same race condition pattern"
}
```
