# LLM Cost Optimization Roadmap

This document outlines potential features to reduce LLM API costs when running agent orchestrator workflows.

---

## Implemented

### 1. Tiered Model Routing ✅
**Status:** Implemented in PR #75

Per-step model selection allowing different LLM models for different tasks.

```yaml
steps:
  - id: planning
    model: opus      # Complex reasoning
  - id: code_review
    model: haiku     # Simple checks - 80% cheaper
```

**Savings:** 50-80% on routine steps

---

### 2. Daily Cost Limits & Stats ✅
**Status:** Implemented

Daily spending limits with automatic tracking and reporting.

**Features:**
- Daily cost limit enforcement (`--daily-cost-limit 10.00`)
- Configurable actions: `warn`, `pause`, `fail`
- Per-step token and cost tracking in run reports
- Daily statistics stored in `.agents/daily_stats/YYYY-MM-DD.json`
- CLI command to view stats: `agent-orchestrator stats --repo .`
- Summary includes: runs, steps, tokens, cost by model

**Usage:**
```bash
# Run with daily limit
python -m agent_orchestrator.cli run \
  --repo /path/to/repo \
  --workflow workflow.yaml \
  --daily-cost-limit 10.00 \
  --cost-limit-action pause

# View daily stats
python -m agent_orchestrator.cli stats --repo /path/to/repo
python -m agent_orchestrator.cli stats --repo /path/to/repo --format json
python -m agent_orchestrator.cli stats --repo /path/to/repo --date 2024-01-15
```

**Savings:** Protection against runaway costs + visibility for optimization

---

## High-Impact (Recommended Next)

### 2. Diff-Only Context

Instead of sending entire files to the LLM, send only relevant context:
- Changed lines + N lines of surrounding context
- Relevant imports/dependencies
- Function signatures being modified

**Implementation:**
```python
# In wrapper, before building prompt:
def build_diff_context(repo_path: Path, max_context_lines: int = 50) -> str:
    """Extract only changed code with minimal context."""
    diff = subprocess.run(["git", "diff", "--unified=5"], capture_output=True)
    # Parse diff, extract relevant sections
    # Include import statements and function signatures
    return trimmed_context
```

**Configuration:**
```yaml
steps:
  - id: code_review
    context_mode: diff_only  # or "full_file" (default)
    context_lines: 10        # lines before/after changes
```

**Savings:** 60-90% token reduction on coding/review steps

---

### 3. Pre-Flight Validation (Zero LLM Cost)

Run local checks before invoking LLM. Skip LLM if issues are obvious.

**Implementation:**
```yaml
steps:
  - id: build_check
    type: local_script           # New step type - no LLM
    script: scripts/check_build.sh
    skip_next_if: success        # Skip LLM step if this passes

  - id: coding_fix
    agent: coding
    needs: [build_check]
    skip_if_preflight_passed: true
```

**Use Cases:**
- `dotnet build` fails with clear error → parse locally, no LLM needed
- Linter finds obvious issues → fix automatically
- Tests pass → skip test-fixing agent

**Savings:** 20-40% by avoiding unnecessary LLM calls

---

### 4. Token Tracking & Reporting

Add visibility into token usage per step/run/workflow.

**Implementation:**
```python
# In run report
{
  "metrics": {
    "tokens_input": 15420,
    "tokens_output": 3200,
    "estimated_cost_usd": 0.47,
    "model_used": "haiku"
  }
}
```

**CLI Output:**
```
Step: code_review (haiku)
  Tokens: 15,420 in / 3,200 out
  Cost: $0.47

Run Total: $4.23 (saved $12.50 vs all-opus)
```

**Savings:** Visibility enables optimization decisions

---

### 5. Cost Guardrails

Hard limits to prevent runaway spending.

**Implementation:**
```yaml
# In workflow or CLI
cost_limits:
  per_step_max_usd: 1.00
  per_run_max_usd: 10.00
  per_day_max_usd: 100.00
  action_on_limit: pause_for_approval  # or "fail" or "downgrade_model"
```

**CLI:**
```bash
python -m agent_orchestrator.cli run \
  --max-cost-per-run 10.00 \
  --cost-limit-action pause
```

**Savings:** Protection against unexpected costs

---

## Medium-Impact

### 6. Result Caching & Memoization

Cache LLM responses for identical inputs.

**Implementation:**
```python
# Cache key: hash(prompt + relevant_files + step_config + model)
class ResponseCache:
    def __init__(self, ttl_hours: int = 24):
        self.cache_dir = Path(".agents/cache")

    def get(self, prompt_hash: str) -> Optional[str]:
        cache_file = self.cache_dir / f"{prompt_hash}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
            if not self._is_expired(data):
                return data["response"]
        return None
```

**Configuration:**
```yaml
caching:
  enabled: true
  ttl_hours: 24
  scope: per_repo          # or "global"
  invalidate_on_file_change: true
```

**Savings:** 30-50% on repeated workflow runs

---

### 7. Incremental Processing

Only process changed files, skip unchanged.

**Implementation:**
```python
def get_changed_files(since_commit: str) -> List[Path]:
    """Get files changed since last successful run."""
    result = subprocess.run(
        ["git", "diff", "--name-only", since_commit],
        capture_output=True
    )
    return [Path(f) for f in result.stdout.decode().splitlines()]

# In code review step:
# Only review files in changed_files list
# Reuse previous analysis for unchanged files
```

**Savings:** 30-70% on incremental runs

---

### 8. Smart Retry Logic

Don't waste tokens retrying deterministic failures.

**Implementation:**
```yaml
retry:
  max_attempts: 2
  skip_retry_on:
    - "file not found"
    - "permission denied"
    - "syntax error"
    - "module not found"
  retry_with_cheaper_model: true  # Use haiku for retries
  exponential_backoff: true
```

**Savings:** 10-20% by avoiding futile retries

---

### 9. Batch Similar Tasks

Combine multiple small tasks into one LLM call.

**Implementation:**
```yaml
steps:
  - id: review_batch
    agent: code_review
    batch_mode: true
    batch_size: 5           # Review 5 files per LLM call
    batch_source: changed_files
```

**Benefits:**
- Amortize system prompt tokens across multiple items
- Reduce API round-trips
- Better context for related changes

**Savings:** 20-40% on multi-file operations

---

### 10. Local Model Fallback

Use local LLMs (Ollama, llama.cpp) for simple tasks.

**Implementation:**
```yaml
model_routing:
  local_first:
    - linting
    - formatting
    - simple_docs
    - commit_messages
  models:
    local: ollama/codellama:13b
    cloud: claude-opus
  fallback_to_cloud_on_failure: true
```

**Wrapper Support:**
```python
# New wrapper: ollama_wrapper.py
def build_ollama_command(args, prompt):
    return [
        "ollama", "run", args.model,
        "--prompt", prompt
    ]
```

**Savings:** 40-60% for simple tasks (zero API cost)

---

## Lower Priority / Future

### 11. Prompt Compression

Automatically compress prompts while preserving meaning.

**Techniques:**
- Remove redundant whitespace and comments
- Summarize long code blocks
- Use abbreviations for common patterns
- Extract only relevant code sections

**Savings:** 10-30% token reduction

---

### 12. Response Streaming with Early Exit

Stop generation early when answer is sufficient.

**Implementation:**
- Stream response tokens
- Detect completion patterns (e.g., run report found)
- Cancel remaining generation

**Savings:** 5-15% on verbose responses

---

### 13. Embedding-Based Code Search

Use embeddings instead of sending full codebase to LLM.

**Implementation:**
```python
# Pre-compute embeddings for codebase
embeddings = compute_embeddings(repo_files)

# At query time, find relevant files
relevant_files = semantic_search(query, embeddings, top_k=10)

# Only send relevant files to LLM
prompt = build_prompt_with_context(query, relevant_files)
```

**Savings:** 50-80% context reduction for large codebases

---

### 14. Multi-Model Ensemble

Use cheap model first, escalate to expensive only if needed.

**Implementation:**
```yaml
steps:
  - id: code_review
    model_strategy: escalation
    models:
      - haiku      # Try first
      - sonnet     # If haiku uncertain
      - opus       # If sonnet uncertain
    escalation_trigger: "confidence < 0.8"
```

**Savings:** 30-50% by using expensive models only when necessary

---

## Implementation Priority

| Priority | Feature | Effort | Savings |
|----------|---------|--------|---------|
| **P0** | ~~Tiered Model Routing~~ | ✅ Done | 50-80% |
| **P0** | ~~Token Tracking~~ | ✅ Done | Visibility |
| **P0** | ~~Cost Guardrails~~ | ✅ Done | Protection |
| **P1** | Diff-Only Context | Medium | 60-90% |
| **P1** | Pre-Flight Validation | Medium | 20-40% |
| **P1** | Result Caching | Medium | 30-50% |
| **P2** | Smart Retry Logic | Low | 10-20% |
| **P2** | Incremental Processing | Medium | 30-70% |
| **P2** | Local Model Fallback | High | 40-60% |
| **P3** | Batch Similar Tasks | Medium | 20-40% |
| **P3** | Prompt Compression | Medium | 10-30% |
| **P3** | Embedding Search | High | 50-80% |

---

## Quick Wins Checklist

- [x] Tiered model routing (PR #75)
- [x] Add token counting to run reports
- [x] Add `--daily-cost-limit` CLI flag
- [x] Add daily stats tracking and `stats` command
- [ ] Add `type: local_script` step support
- [ ] Implement response caching with TTL
- [ ] Add `--model` default in workflow-level config

---

## Estimated Total Savings

With full implementation:
- **Conservative:** 40-50% cost reduction
- **Optimistic:** 70-80% cost reduction

Key factors:
- Workflow composition (simple vs complex steps)
- Codebase size (larger = more savings from diff-only)
- Run frequency (more runs = more caching benefit)
