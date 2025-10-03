# Coverage Analyzer Agent

Goal: Identify files with low test coverage and detect coverage regressions in recent diffs to prioritize test generation.

## Deliverables

- Coverage analysis report in `.agents/runs/{run_id}/artifacts/coverage_gaps/analysis.json` containing:
  - List of files with coverage below threshold (default: 70%)
  - Coverage metrics per file: line coverage %, branch coverage %, uncovered lines
  - Diff coverage analysis: files with coverage delta < 0 in recent changes
  - Priority ranking based on:
    - Code complexity (cyclomatic complexity)
    - File change frequency (git history)
    - Critical path indicators (main/core modules)
- Summary report in `.agents/runs/{run_id}/artifacts/coverage_gaps/summary.md` with:
  - Top 20 files needing coverage improvement
  - Diff coverage violations (recent PRs/commits with negative coverage delta)
  - Suggested test targets with rationale

## Data Sources

Analyze the following sources for coverage data:
1. **Coverage reports**: Look for coverage files in common formats:
   - `.coverage` (Python coverage.py)
   - `coverage.xml` or `coverage.json` (Python)
   - `coverage/lcov.info` (JavaScript/TypeScript)
   - `coverage/coverage-final.json` (JavaScript Jest)
   - `target/site/jacoco/jacoco.xml` (Java JaCoCo)
   - `coverage/cobertura-coverage.xml` (Various)
2. **Git diff**: Compare coverage between HEAD and target branch (default: main)
3. **Code complexity**: Analyze cyclomatic complexity using language-specific tools
4. **Git history**: Determine file change frequency to prioritize volatile files

### Coverage Tool Detection

Detect which coverage tools are in use by checking for:
1. **Python**: `pytest.ini`, `setup.cfg`, `.coveragerc`, `pyproject.toml` with pytest/coverage config
2. **JavaScript/TypeScript**: `jest.config.js`, `package.json` with jest, `.nycrc`, `nyc` config
3. **Java**: `pom.xml` with JaCoCo plugin, `build.gradle` with jacoco
4. **Go**: `go test -cover` is standard
5. **Ruby**: `.simplecov` or Gemfile with simplecov

**If no coverage tool is configured**: Document this in the report and recommend setting up coverage tooling.

## Analysis Criteria

A file needs coverage improvement if:
- Current line coverage < 70% (configurable threshold)
- Diff coverage delta < 0% (coverage decreased in recent changes)
- Uncovered lines > 50 and coverage < 80%
- High complexity (cyclomatic complexity > 10) with coverage < 80%
- Frequently modified (>5 commits in last 30 days) with coverage < 75%

### Priority Scoring

Calculate priority score (0-100) for each file using weighted factors:
```
priority_score = (
  (100 - coverage_percent) * 0.4 +
  (min(complexity, 20) / 20 * 100) * 0.3 +
  (min(change_frequency, 10) / 10 * 100) * 0.2 +
  (is_core_module ? 100 : 0) * 0.1
)
```

Sort files by priority score descending and target top 20.

## Constraints

- Look back at git history for last 30 days for change frequency
- For diff coverage, compare HEAD against configured base branch (default: main)
- Calculate complexity for functions/methods with >10 lines
- Focus on source code files, ignore test files (exclude `test_*`, `*_test.*`, `*.spec.*`, `*.test.*`)
- **API Rate Limiting**: If using external APIs (GitHub, etc.), respect rate limits
- Generate coverage reports if not present (run tests with coverage enabled):
  - Python: `pytest --cov=. --cov-report=json --cov-report=xml`
  - JavaScript: `npm test -- --coverage` or `jest --coverage`
  - Java: `mvn test` (if jacoco configured) or `gradle test jacocoTestReport`

### Security and Path Handling

**⚠️ IMPORTANT SECURITY WARNINGS:**
- DO NOT include absolute paths in reports (use relative paths from repo root)
- DO NOT execute arbitrary code from untested files
- When running coverage commands, validate project structure first
- Redact any credentials that may appear in coverage output

## Output Format

### analysis.json
```json
{
  "threshold": 70,
  "base_branch": "main",
  "total_files_analyzed": 150,
  "files_below_threshold": 42,
  "diff_coverage_violations": 5,
  "files": [
    {
      "path": "src/services/payment_processor.py",
      "line_coverage_percent": 45.2,
      "branch_coverage_percent": 38.1,
      "uncovered_lines": [23, 24, 45-67, 89],
      "total_lines": 230,
      "complexity": 15,
      "change_frequency": 8,
      "is_core_module": true,
      "priority_score": 87.5,
      "diff_coverage_delta": -5.2
    }
  ]
}
```

### summary.md
```markdown
# Coverage Gap Analysis

**Analysis Date**: 2025-10-01
**Base Branch**: main
**Coverage Threshold**: 70%

## Summary Statistics
- Total files analyzed: 150
- Files below threshold: 42
- Diff coverage violations: 5

## Top 20 Priority Files for Test Generation

1. **src/services/payment_processor.py** (Priority: 87.5)
   - Current coverage: 45.2%
   - Uncovered lines: 67
   - Complexity: 15 (high)
   - Recent changes: 8 commits
   - **Diff coverage**: -5.2% ⚠️

...
```

## Completion

Write a run report JSON to `${REPORT_PATH}` with:
```json
{
  "status": "success",
  "files_below_threshold": 42,
  "diff_coverage_violations": 5,
  "top_priority_files": 20,
  "artifacts": [
    ".agents/runs/{run_id}/artifacts/coverage_gaps/analysis.json",
    ".agents/runs/{run_id}/artifacts/coverage_gaps/summary.md"
  ],
  "notes": "Found 5 files with negative diff coverage. Prioritized 20 files for test generation."
}
```
