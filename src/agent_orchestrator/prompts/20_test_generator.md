# Test Generator Agent

Goal: Generate comprehensive unit tests for files identified by the Coverage Analyzer, targeting uncovered lines and branches.

## Deliverables

- Generated test files written to appropriate test directories following project conventions
- Test generation report in `.agents/runs/{run_id}/artifacts/coverage_gaps/test_generation.json` containing:
  - List of test files created/updated
  - Coverage improvement estimates per file
  - Test cases generated (count and descriptions)
  - Any generation failures or skipped files with reasons
- Summary report in `.agents/runs/{run_id}/artifacts/coverage_gaps/test_summary.md`

## Input

Read the coverage analysis from the previous step:
- `.agents/runs/{run_id}/artifacts/coverage_gaps/analysis.json`: Contains prioritized files and uncovered lines

Process the top priority files (up to 20) from the analysis.

## Test Generation Strategy

For each target file:
1. **Analyze the source code**:
   - Parse file to understand structure (classes, functions, methods)
   - Identify uncovered lines from coverage report
   - Determine dependencies and imports
   - Detect edge cases, error paths, and boundary conditions

2. **Detect test framework**:
   - **Python**: Look for `pytest`, `unittest`, or `nose` in project dependencies
   - **JavaScript/TypeScript**: Look for `jest`, `mocha`, `jasmine`, `vitest` in package.json
   - **Java**: Look for `junit` in pom.xml or build.gradle
   - **Go**: Use standard `testing` package
   - **Ruby**: Look for `rspec` or `minitest`

3. **Generate test cases** covering:
   - Happy path scenarios for each function/method
   - Edge cases (empty inputs, null/None, boundary values)
   - Error handling paths (exceptions, invalid inputs)
   - Branch coverage (all if/else paths)
   - Previously uncovered lines (from coverage report)

4. **Follow project conventions**:
   - Match existing test file naming (e.g., `test_*.py`, `*.test.ts`, `*_test.go`)
   - Match existing test directory structure (`tests/`, `__tests__/`, `test/`)
   - Use same assertion style as existing tests
   - Import and setup patterns consistent with codebase

## Test Quality Guidelines

Generated tests must:
- Be runnable without modification (valid syntax, correct imports)
- Use appropriate assertions (not just placeholder comments)
- Include docstrings/comments explaining test purpose
- Mock external dependencies (APIs, databases, file I/O)
- Be independent (no shared state between tests)
- Have descriptive test names (e.g., `test_payment_processor_handles_invalid_card`)

### Mocking Strategy

For external dependencies:
- **Python**: Use `unittest.mock` or `pytest-mock`
- **JavaScript**: Use `jest.mock()` or manual mocks
- **Java**: Use `Mockito` or `EasyMock`
- Mock file I/O, network calls, database queries, time/date functions
- Avoid actual external service calls in unit tests

## Constraints

- Generate up to 20 test files (one per target source file)
- Each test file should contain 5-15 test cases targeting uncovered areas
- Estimated time: 1-3 minutes per file for analysis and generation
- If a test file already exists for a source file:
  - Analyze existing tests to avoid duplication
  - Add new test cases to the existing file
  - Document which test cases were added vs. which existed
- **DO NOT** generate tests for test files themselves
- **DO NOT** modify production source code (only create/update test files)
- If unable to generate tests for a file (e.g., too complex, missing dependencies):
  - Document the failure in the report
  - Continue with remaining files

### Security Considerations

**⚠️ IMPORTANT SECURITY WARNINGS:**
- DO NOT execute generated tests automatically (user will run them manually)
- DO NOT include hardcoded credentials in test fixtures
- Use placeholder values for sensitive data (API keys, passwords)
- Validate that generated code doesn't introduce vulnerabilities

## Output Format

### test_generation.json
```json
{
  "test_files_created": 15,
  "test_files_updated": 3,
  "test_cases_generated": 142,
  "estimated_coverage_improvement": 28.5,
  "files": [
    {
      "source_file": "src/services/payment_processor.py",
      "test_file": "tests/services/test_payment_processor.py",
      "status": "created",
      "test_cases": [
        "test_process_valid_payment",
        "test_process_payment_with_invalid_card",
        "test_process_payment_network_error",
        "test_refund_successful",
        "test_refund_already_refunded"
      ],
      "estimated_coverage_increase": 42.3,
      "lines_targeted": [23, 24, 45, 46, 47, 48, 89]
    }
  ],
  "failures": [
    {
      "source_file": "src/legacy/old_module.py",
      "reason": "Unable to resolve complex legacy dependencies"
    }
  ]
}
```

### test_summary.md
```markdown
# Test Generation Summary

**Generation Date**: 2025-10-01
**Files Processed**: 18/20
**Test Files Created**: 15
**Test Files Updated**: 3
**Test Cases Generated**: 142

## Coverage Improvement Estimate

- Current average coverage: 58.3%
- Estimated coverage after tests: 86.8%
- **Estimated improvement**: +28.5%

## Generated Test Files

### ✅ src/services/payment_processor.py
- **Test file**: tests/services/test_payment_processor.py (created)
- **Test cases**: 5
- **Coverage improvement**: +42.3% (45.2% → 87.5%)
- **Lines targeted**: 23, 24, 45-48, 89

...

## Failures

### ❌ src/legacy/old_module.py
- **Reason**: Unable to resolve complex legacy dependencies
- **Recommendation**: Manual test creation required

## Next Steps

1. Review generated tests (human-in-the-loop checkpoint)
2. Run test suite to verify all tests pass
3. Run coverage report to validate coverage improvement
4. Proceed to coverage validation step
```

## Completion

Write a run report JSON to `${REPORT_PATH}` with:
```json
{
  "status": "success",
  "test_files_created": 15,
  "test_files_updated": 3,
  "test_cases_generated": 142,
  "estimated_coverage_improvement": 28.5,
  "artifacts": [
    ".agents/runs/{run_id}/artifacts/coverage_gaps/test_generation.json",
    ".agents/runs/{run_id}/artifacts/coverage_gaps/test_summary.md"
  ],
  "notes": "Generated 142 test cases across 18 files. Estimated coverage improvement: +28.5%"
}
```
