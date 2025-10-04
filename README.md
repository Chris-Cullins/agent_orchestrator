# SDLC Agents Orchestrator

A production-ready, file-driven orchestrator for chaining SDLC agents via run report files. This system automates software development workflows by orchestrating AI agents that handle planning, coding, testing, review, documentation, and deployment tasks.

## How to Use This Application on Your Code Repository

### Prerequisites

1. **Python Environment**: Python 3.10+ (Python 3.13+ fully supported) with virtual environment support
2. **AI Agent Platform**: Access to a supported agent binary such as `codex` (OpenAI Codex Exec) or the Anthropic `claude` CLI
3. **Target Repository**: A Git repository where you want to run the SDLC pipeline

### Step 1: Installation

```bash
# Clone this orchestrator repository
git clone <this-repo-url>
cd agent_orchestrator

# Set up Python environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install the agent_orchestrator package
pip install -e .
```

If you skip the editable install, prefix orchestrator commands with `PYTHONPATH=src` so Python can resolve the package.

**Note**: If your AI agent binaries (`claude` or `codex`) are not in your system PATH, you can either:
- Add them to your PATH: `export PATH="/path/to/binaries:$PATH"`
- Use the `--claude-bin` or `--codex-bin` wrapper arguments to specify the binary location
- Set the `CLAUDE_CLI_BIN` or `CODEX_EXEC_BIN` environment variables

```bash
# Example: Using environment variables
export CLAUDE_CLI_BIN=/path/to/claude
export CODEX_EXEC_BIN=/path/to/codex

# Example: Using wrapper arguments
python -m agent_orchestrator.cli run \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --wrapper-arg --claude-bin \
  --wrapper-arg /path/to/claude
```

```bash
# Verify your agent binaries are available
codex --version  # Codex wrapper
claude --version # Claude wrapper
```

### Step 2: Choose Your Workflow

Select one of the predefined workflows or create your own:

**Available Workflows:**
- `src/agent_orchestrator/workflows/workflow.yaml` - Complete SDLC pipeline (planning → coding → testing → review → docs → merge)
- `src/agent_orchestrator/workflows/workflow_backlog_miner.yaml` - Architecture review and tech debt analysis
- `src/agent_orchestrator/workflows/workflow_large_work.yaml` - Large task decomposition with loop-based story implementation

### Step 3: Configure Your AI Agent Platform

The orchestrator supports multiple AI agent platforms through different wrappers:

#### Claude CLI (Anthropic) - Recommended
```bash
# Ensure Claude CLI is installed and authenticated
claude --version

# Run with Claude (recommended for quality)
python -m agent_orchestrator.cli run \
  --repo /path/to/your/target/repository \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --wrapper-arg --model \
  --wrapper-arg sonnet
```

#### Codex Exec (OpenAI)
```bash
# Ensure codex exec is available and authenticated
codex --version

# Run with Codex
python -m agent_orchestrator.cli run \
  --repo /path/to/your/target/repository \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py
```

#### Mock Wrapper (For Testing)
```bash
# Note: mock_wrapper.py is not currently included in this repository
# Use src/agent_orchestrator/wrappers/claude_wrapper.py or src/agent_orchestrator/wrappers/codex_wrapper.py instead
python -m agent_orchestrator.cli run \
  --repo /path/to/your/target/repository \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py
```

#### Custom Command Template
```bash
python -m agent_orchestrator.cli run \
  --repo /path/to/your/target/repository \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --command-template "your-agent-runner --agent {agent} --prompt {prompt} --repo {repo} --output {report}"
```

#### Choosing the Right Wrapper

The orchestrator includes several wrapper scripts located in `src/agent_orchestrator/wrappers/`:

- **`claude_wrapper.py`** (Recommended): For Anthropic Claude CLI integration. Provides high-quality code generation and reasoning. Use with `--wrapper-arg --model` and `--wrapper-arg sonnet|opus|haiku` to specify the model.

- **`codex_wrapper.py`**: For OpenAI Codex integration via `codex exec`. Use this if you have access to OpenAI's Codex platform.

Choose your wrapper based on which AI platform you have access to and your quality/cost requirements.

#### Wrapper Path Resolution

The `--wrapper` argument accepts file paths that are resolved relative to your current working directory:

- **Full path from orchestrator root** (recommended): `src/agent_orchestrator/wrappers/claude_wrapper.py`
- **Absolute path**: `/full/path/to/src/agent_orchestrator/wrappers/claude_wrapper.py`
- **Relative path**: If running from a different directory, adjust the path accordingly (e.g., `../agent_orchestrator/src/agent_orchestrator/wrappers/claude_wrapper.py`)

**Important:** The CLI does not automatically search in `src/agent_orchestrator/wrappers/` - you must provide the full or relative path to the wrapper script. Simple filenames like `claude_wrapper.py` will only work if the file exists in your current directory.

### Step 4: Basic Usage Examples

#### Quick Start: Use the Convenience Script

For easy workflow execution, use the provided bash script:

```bash
# Run on current directory with default workflow (backlog_miner)
./src/agent_orchestrator/scripts/run_workflow.sh

# Run on a specific repository
./src/agent_orchestrator/scripts/run_workflow.sh --repo /path/to/your/project

# Use a different workflow
./src/agent_orchestrator/scripts/run_workflow.sh --workflow src/agent_orchestrator/workflows/workflow.yaml

# All options
./src/agent_orchestrator/scripts/run_workflow.sh \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py
```

**Script Options:**
- `--repo PATH` - Path to target repository (default: current directory)
- `--workflow PATH` - Path to workflow YAML file (default: src/agent_orchestrator/workflows/workflow_backlog_miner.yaml)
- `--wrapper PATH` - Path to agent wrapper script (default: src/agent_orchestrator/wrappers/claude_wrapper.py)
- `--help` - Show help message

#### Manual Execution: Complete SDLC Pipeline
```bash
# Full development workflow on your repository using Claude
python -m agent_orchestrator.cli --log-level INFO run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --pause-for-human-input
```

#### Manual Execution: Architecture and Tech Debt Analysis
```bash
# Analyze your codebase for technical debt and architecture misalignments
python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow_backlog_miner.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py
```

#### Run with Custom Environment and Configuration
```bash
python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --env OPENAI_API_KEY=your-key \
  --env ENVIRONMENT=production \
  --wrapper-arg --model \
  --wrapper-arg opus \
  --max-attempts 3 \
  --poll-interval 2.0
```

```bash
# GitHub issue workflow (inject the issue ID, receive Markdown paths back)
python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow_github_issue.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --env ISSUE_NUMBER=12345
```

## Email Notifications

The orchestrator can dispatch email alerts whenever a workflow step fails or pauses awaiting human approval.

- Configure alerts in `config/email_notifications.yaml`. The file ships with `enabled: false` so runs keep their current behaviour until you opt in.
- Populate `sender`, `recipients`, and the `smtp` block (host/port plus optional `username`/`password`, TLS, timeout). Invalid configurations halt CLI execution with a helpful error message.
- When enabled, the orchestrator starts the notification service at run launch and sends:
  - Failure alerts summarising the run, step, attempt, and recent log lines
  - Pause alerts that point operators at the generated `.agents/runs/<run_id>/manual_inputs/...` file
- Use `subject_prefix` to brand the subject line (defaults to `[Agent Orchestrator]`).
- Leave `enabled: false` or remove sensitive credentials if you commit this repository template—operators can override the file in their fork or deployment environment.

When `ISSUE_NUMBER` is provided, the orchestrator populates `ISSUE_MARKDOWN_PATH`, `ISSUE_MARKDOWN_DIR`, and `ISSUE_MARKDOWN_FILENAME` so subsequent steps can load the generated GitHub issue summary without hard-coding paths.

#### Run with Automated Git Worktree Isolation
```bash
python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --git-worktree \
  --git-worktree-ref main \
  --git-worktree-keep
```

**Git worktree flags:**
- `--git-worktree` – create an isolated worktree under `<repo>/.agents/worktrees/` for the run.
- `--git-worktree-ref` – optional ref to base the worktree on (defaults to `HEAD`).
- `--git-worktree-branch` – override the auto-generated branch name.
- `--git-worktree-root` – place worktrees somewhere other than `.agents/worktrees`.
- `--git-worktree-keep` – keep the worktree instead of deleting it after the run.

When cleanup is enabled (the default), run artifacts are copied to `<repo>/.agents/runs/<run_id>/` before the temporary worktree is removed so you can still review outputs.

### Automate Recurring Runs with systemd timers

#### CLI essentials for unattended runs
- Minimum command: `python -m agent_orchestrator.cli run --repo <repo> --workflow <workflow> --wrapper <wrapper>`
- Always provide absolute paths so the service keeps working after reboots
- Wrapper binaries can come from `PATH`, `--wrapper-arg --codex-bin/--claude-bin`, or `CODEX_EXEC_BIN` / `CLAUDE_CLI_BIN`
- Pass `--logs-dir` when you want stable log locations; the installer defaults to `<repo>/.agents/systemd-logs/<unit>`
- The orchestrator runs from the repo root (`--workdir` defaults to the repo), ensuring prompt overrides under `.agents/prompts/` resolve

#### Install script quick tour
- Command: `src/agent_orchestrator/scripts/install_systemd_timer.sh install ...`
- Generated assets:
  - `~/.config/systemd/user/<unit>.service`
  - `~/.config/systemd/user/<unit>.timer`
  - `<repo>/.agents/systemd/<unit>.sh` helper that handles locking and logging
- Unit naming: omit `--unit-name` to auto-generate `agent-orchestrator-<repo>-<workflow>`; values are lowercased and non-alphanumerics collapse to single hyphens so the service/timer names stay systemd-safe
- Service details:
  - `WorkingDirectory` is set to the repo
  - `ExecStart` runs the helper, which executes `flock -n <repo>/.agents/locks/<unit>.lock -- python -m agent_orchestrator.cli run ...`
  - Stdout/stderr append to `<repo>/.agents/systemd-logs/<unit>/<unit>.log`
  - `TimeoutStartSec=0` keeps long workflows from being aborted
- Timer details:
  - Default `OnCalendar=*:0/30` (top and half of every hour)
  - `Persistent=true` so missed runs execute after downtime
  - Optional `--randomized-delay` reduces thundering herd restarts

#### Usage examples
```bash
# Install a weekday timer and trigger an immediate run
./src/agent_orchestrator/scripts/install_systemd_timer.sh install \
  --repo /absolute/path/to/target/repo \
  --workflow src/agent_orchestrator/workflows/workflow_pr_review_fix.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --unit-name pr-review \
  --calendar 'Mon..Fri *-*-* 09,13,17:00' \
  --wrapper-arg --claude-bin \
  --wrapper-arg /usr/local/bin/claude \
  --env CLAUDE_CLI_BIN=/usr/local/bin/claude \
  --randomized-delay 300 \
  --start-now

# Regenerate units in CI without touching systemctl
SKIP_SYSTEMCTL=1 ./src/agent_orchestrator/scripts/install_systemd_timer.sh install \
  --repo /tmp/repo \
  --workflow src/agent_orchestrator/workflows/workflow_backlog_miner.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --no-enable

# Uninstall a timer
./src/agent_orchestrator/scripts/install_systemd_timer.sh uninstall \
  --repo /absolute/path/to/target/repo \
  --unit-name pr-review
```

#### Verification and troubleshooting
- Status: `systemctl --user status pr-review.timer` and `systemctl --user list-timers pr-review*`
- Logs: `tail -f <repo>/.agents/systemd-logs/pr-review/pr-review.log`
- Outputs: inspect `<repo>/.agents/runs/<run_id>/reports/` and `logs/` for per-attempt details
- Prerequisites:
  - User systemd instance running (`loginctl enable-linger $(whoami)` on headless nodes)
  - Wrapper binaries available on `PATH` or supplied via `--wrapper-arg` / env vars
  - Stable Python interpreter path (pass `--python` if your virtualenv moves)
- Clean rerun: disable the timer, remove `.agents/systemd-logs/<unit>` if desired, then reinstall with new settings
- Smoke test: run the installer with `SKIP_SYSTEMCTL=1 --start-now` to confirm files and command lines without enabling timers

#### Resume a Failed Workflow Run

If a workflow fails at a specific step, you can resume it from that step without re-running completed steps:

```bash
# Resume from a specific step (e.g., code_review)
python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --start-at-step code_review
```

**How it works:**
- The orchestrator locates the most recent `.agents/runs/<run_id>/run_state.json` and loads its state
- Resets the specified step and all downstream dependent steps to `PENDING`
- Preserves all completed upstream steps (e.g., `fetch_github_issue`, `github_issue_plan`, `coding_impl`)
- Resumes execution from the specified step with a fresh attempt counter

**Use cases:**
- A step failed due to a transient error (network issue, API timeout)
- You fixed code that was causing an agent to fail
- You want to retry a step after making manual changes to the repository
- Testing workflow changes without re-running expensive upstream steps

**Example scenario:**
```bash
# Initial run fails at code_review step
python -m agent_orchestrator.cli run --repo . \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py
# ... workflow runs: fetch_github_issue (✓), github_issue_plan (✓), coding_impl (✓), code_review (✗)

# Fix the issue that caused code_review to fail, then resume
python -m agent_orchestrator.cli run --repo . \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --start-at-step code_review
# ... workflow resumes: code_review (attempt 1), docs_update, merge_pr, cleanup
```

**Note:** The `--start-at-step` flag requires an existing run state file. If you want to start a completely new run, omit this flag.

### Step 5: Understanding Output and Artifacts

When you run the orchestrator, it creates structured output under `.agents/` inside your target repository:

```
your-target-repo/
└── .agents/                         # Orchestrator working directory
    ├── prompts/                    # Optional prompt overrides
    └── runs/                       # One folder per workflow run
        └── <run_id>/               # e.g., f8c1a491
            ├── reports/            # JSON run reports per step
            │   └── <run_id>__<step_id>.json
            ├── logs/               # stdout/stderr captured for each attempt
            │   └── <run_id>__<step_id>__attemptN.log
            ├── artifacts/          # Files emitted via $ARTIFACTS_DIR (diffs, docs, etc.)
            ├── manual_inputs/      # Created when --pause-for-human-input is enabled
            └── run_state.json      # Persisted workflow state for --start-at-step resumes
```

Per-run folders under `.agents/runs/<run_id>/` are created for every workflow launch, even without git worktrees, so you can safely inspect `reports/`, `logs/`, `artifacts/`, and the persisted `run_state.json` without interfering with a live run. The `manual_inputs/` directory appears only when you pass `--pause-for-human-input` and serves as the drop location for approval files. Agent-generated artifacts (like planning inventories, review notes, or GitHub issue files) are stored under `artifacts/` using per-step subdirectories. For example, when running a GitHub issue workflow, the fetcher writes `gh_issue_${ISSUE_NUMBER}.md` to the artifacts directory, keeping the repository root clean.

Key takeaways:
- Review `reports/` for per-step summaries and `logs/` for raw stdout/stderr before debugging a failure.
- GitHub issue workflows now publish their Markdown handoff to `artifacts/gh_issue_<ISSUE_NUMBER>.md` and export `ISSUE_MARKDOWN_PATH`, `ISSUE_MARKDOWN_DIR`, and `ISSUE_MARKDOWN_FILENAME` so downstream steps and prompts can link to it reliably.
- Use `run_state.json` together with `--start-at-step` to resume a workflow without re-running completed steps.
- Prefer deleting the entire `.agents/runs/<run_id>/` folder (or starting a new `--run-id`) to reset state instead of editing `run_state.json` in place.

### Step 6: Customizing Agent Behavior with Prompt Overrides

The orchestrator supports repository-level prompt customization, allowing you to tailor agent behavior without modifying the orchestrator codebase or workflow definitions.

#### How Prompt Overrides Work

When executing a workflow, the orchestrator resolves prompts in this order:

1. **Repository-level overrides** (highest priority): `.agents/prompts/` in your target repository
2. **Default prompts** (fallback): `src/agent_orchestrator/prompts/` in the orchestrator

This enables you to customize agent instructions on a per-repository basis.

#### Setting Up Prompt Overrides

Create custom prompt files in your target repository:

```bash
# In your target repository
mkdir -p .agents/prompts

# Override the coding agent prompt
cat > .agents/prompts/02_coding.md << 'EOF'
# Custom Coding Agent

Your task: Implement the feature following our team's coding standards.

Requirements:
- Use TypeScript strict mode
- Add JSDoc comments for all public APIs
- Follow our company's error handling patterns
- Write unit tests for all new functions

[Rest of your custom instructions...]
EOF
```

#### Example: Custom Documentation Standards

```bash
# Override documentation agent to enforce your style guide
cat > .agents/prompts/05_docs.md << 'EOF'
# Documentation Agent - Company Style

Update documentation following our standards:
- Use present tense ("returns" not "will return")
- Include code examples for all public APIs
- Add cross-references to related modules
- Update both README.md and inline code comments
EOF
```

When you run the orchestrator, it will automatically use your custom prompts when they exist:

```bash
python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py
# The orchestrator will use .agents/prompts/05_docs.md if it exists,
# otherwise falls back to src/agent_orchestrator/prompts/05_docs.md
```

#### Available Prompts to Override

You can override any of these standard prompts:
- `01_planning.md` - Initial task planning
- `02_coding.md` - Code implementation
- `03_e2e.md` - End-to-end testing
- `04_manual.md` - Manual test plan generation
- `05_docs.md` - Documentation updates
- `06_code_review.md` - Code review
- `07_pr_manager.md` - Pull request management
- `08_cleanup.md` - Cleanup tasks
- And more in `src/agent_orchestrator/prompts/`

### Step 7: Advanced Configuration

#### Human-in-the-Loop Integration
Enable manual steps that require human input:
```bash
python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --pause-for-human-input
```

When a manual step is reached, provide input via:
```bash
# The orchestrator will wait for this file
echo '{"approved": true, "comments": "LGTM"}' > \
  /path/to/your/project/.agents/runs/<run_id>/manual_inputs/<run_id>__<step_id>.json
```

#### CI/CD Integration with Gates
Use gate conditions to control workflow progression:
```bash
# Create gate state file
echo '{"ci.tests": true, "security.scan": true}' > gates.json

python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --gate-state-file gates.json
```

#### Custom Working Directory and Logs
```bash
python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --workdir /tmp/agent-workspace \
  --logs-dir /var/log/agents \
  --state-file custom_state.json
```

### Step 8: Creating Custom Workflows

Create your own workflow by defining a YAML file:

```yaml
name: my_custom_workflow
description: Custom SDLC pipeline for my project
steps:
  - id: planning
    agent: planner
    prompt: src/agent_orchestrator/prompts/01_planning.md
    needs: []
    next_on_success: [implementation]

  - id: implementation
    agent: coder
    prompt: src/agent_orchestrator/prompts/02_coding.md
    needs: [planning]
    next_on_success: [testing]

  - id: testing
    agent: tester
    prompt: src/agent_orchestrator/prompts/03_e2e.md
    needs: [implementation]
    next_on_success: []
```

#### Advanced Feature: Loop Control for Iterating Over Collections

The orchestrator supports **loop control** functionality, allowing steps to iterate over collections of items. This is useful for processing multiple stories, features, or data items sequentially.

**How Loop Control Works:**

1. A step can be configured with a `loop` field that specifies the source of items
2. The step executes once for each item in the collection
3. Loop context (current item and index) is passed to the agent via environment variables
4. The step proceeds to the next item until all items are processed

**Loop Configuration Options:**

```yaml
loop:
  items: [item1, item2, item3]              # Static list
  items_from_step: previous_step_id          # Output from previous step
  items_from_artifact: path/to/items.json    # Path to artifact file
  item_var: story                            # Variable name (default: "item")
  index_var: story_index                     # Index variable (default: "index")
  max_iterations: 10                         # Optional limit
```

**Example: Multi-Story Development Workflow:**

```yaml
name: large_work_pipeline
description: Break down large tasks into stories and implement each story
steps:
  - id: story_breakdown
    agent: story_breakdown
    prompt: src/agent_orchestrator/prompts/24_story_breakdown.md
    needs: []
    next_on_success: [story_implementation]

  - id: story_implementation
    agent: coding
    prompt: src/agent_orchestrator/prompts/02_coding.md
    needs: [story_breakdown]
    loop:
      items_from_step: story_breakdown
      item_var: story
      index_var: story_index
    next_on_success: [story_review]

  - id: story_review
    agent: code_review
    prompt: src/agent_orchestrator/prompts/06_code_review.md
    needs: [story_implementation]
    loop:
      items_from_step: story_breakdown
      item_var: story
      index_var: story_index
    loop_back_to: story_implementation
    next_on_success: [final_docs]
```

**Accessing Loop Context in Agent Prompts:**

Agents receive loop information through environment variables:
- `LOOP_INDEX` - Current iteration index (0-based)
- `LOOP_ITEM` - Current item being processed (JSON-encoded if complex)

**Example Use Cases:**
- Breaking large features into stories and implementing each story
- Processing multiple issues from a backlog
- Running tests across multiple configurations
- Generating documentation for multiple modules

**Loop Sources:**

1. **Static list** (`items`): Define items directly in the workflow YAML
2. **Previous step output** (`items_from_step`): Use output from a previous step that generates a list
3. **Artifact file** (`items_from_artifact`): Read items from a JSON artifact file

**Best Practices:**
1. Use `max_iterations` to prevent runaway loops
2. Combine loops with `loop_back_to` for iterative refinement per item
3. Ensure the source step outputs a valid JSON array when using `items_from_step`
4. Use descriptive variable names (`item_var`, `index_var`) for clarity in prompts

#### Advanced Feature: Loop-Back for Iterative Refinement

The orchestrator supports **loop-back** functionality, allowing steps to send work back to previous steps for iterative refinement. This is particularly useful for quality gates like code review that may need multiple iterations.

**How Loop-Back Works:**

1. A step (e.g., code review) completes and sets `gate_failure: true` in its run report
2. If the step has a `loop_back_to` field defined, the orchestrator resets the target step and all downstream steps
3. The workflow continues from the loop-back target step
4. This process repeats until either:
   - The gate passes (`gate_failure: false`)
   - Max iterations is reached (default: 4)

**Example Workflow with Loop-Back:**

```yaml
name: code_review_loop_workflow
description: Iterative development with automated code review feedback
steps:
  - id: coding
    agent: coding
    prompt: src/agent_orchestrator/prompts/02_coding.md
    needs: []
    next_on_success: [code_review]
    
  - id: code_review
    agent: code_review
    prompt: src/agent_orchestrator/prompts/06_code_review.md
    needs: [coding]
    loop_back_to: coding  # Send back to coding if critical issues found
    next_on_success: [testing]
    
  - id: testing
    agent: manual_testing
    prompt: src/agent_orchestrator/prompts/04_manual.md
    needs: [code_review]
    next_on_success: []
```

**Agent Run Report with Gate Failure:**

When your code review agent detects critical issues, it should return:

```json
{
  "schema": "run_report_v1",
  "run_id": "abc123",
  "step_id": "code_review",
  "agent": "code_review",
  "status": "COMPLETED",
  "started_at": "2025-01-01T10:00:00Z",
  "ended_at": "2025-01-01T10:05:00Z",
  "gate_failure": true,
  "logs": [
    "Found 3 P0 issues that must be fixed",
    "Security vulnerability in authentication logic",
    "Missing input validation in user endpoint"
  ]
}
```

**Configuring Loop-Back Behavior:**

```bash
# Run with custom max iterations (default: 4)
python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow_code_review_loop.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --max-iterations 3  # Allow up to 3 loop-back iterations

# Combine with max attempts for resilience
python -m agent_orchestrator.cli run \
  --repo /path/to/your/project \
  --workflow workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --max-iterations 5 \
  --max-attempts 2  # Each step can retry twice on failure
```

**Key Parameters:**
- `--max-iterations N` - Maximum number of times a loop-back can occur before marking the step as failed (default: 4)
- `--max-attempts N` - Maximum retry attempts per step for transient failures (default: 2)

**Loop-Back vs. Retry:**
- **Retry** (`--max-attempts`): For transient failures (network issues, temporary errors). The same step re-runs.
- **Loop-Back** (`loop_back_to`): For quality gates. Returns to an earlier step to fix identified issues.

**Best Practices:**
1. Use loop-back for quality gates (code review, testing validation)
2. Set reasonable iteration limits (3-5) to prevent infinite loops
3. Ensure your agent provides clear feedback in logs when setting `gate_failure: true`
4. Use loop-back sparingly - only for steps that genuinely need iterative refinement

**Example Use Cases:**
- Code review finding P0/P1 issues → loop back to coding
- E2E tests failing → loop back to implementation
- Documentation quality check failing → loop back to docs update
- Security scan finding vulnerabilities → loop back to code fixes

### Step 9: Monitoring and Debugging

#### View Execution Status
```bash
# Check current run state
ls /path/to/your/project/.agents/runs
cat /path/to/your/project/.agents/runs/<run_id>/run_state.json

# Monitor logs in real-time
tail -f /path/to/your/project/.agents/runs/<run_id>/logs/*.log
```

Inspect the persisted `run_state.json` when debugging loop-backs. Each step now tracks an `iteration_count` that increments every time the orchestrator sends execution back to that step:

```json
{
  "steps": {
    "coding": {
      "status": "RUNNING",
      "iteration_count": 2,
      "last_error": null
    }
  }
}
```

Use `iteration_count` together with the per-run reports to understand how many times a quality gate has fired. When the count reaches the `--max-iterations` limit (default `4`), the orchestrator marks the step `FAILED` and records the gate failure reason in the logs.

#### Common Command-Line Options
- `--log-level DEBUG` - Verbose logging for troubleshooting
- `--max-attempts 3` - Retry failed steps up to 3 times
- `--poll-interval 0.5` - Check for completion every 0.5 seconds
- `--max-iterations 4` - Cap loop-back iterations before marking a step failed
- `--schema path/to/schema.json` - Validate run reports against JSON schema

### Troubleshooting

**Common Issues:**
1. **Missing Agent Binary**: Ensure `codex exec` or your agent runner is in PATH
2. **Permission Errors**: Check write permissions on target repository
3. **Failed Steps**: Review logs in `.agents/runs/<run_id>/logs/`
4. **Workflow Validation**: Verify YAML syntax and step dependencies
5. **Run Report JSON Errors**: Transient parse failures are retried automatically; persistent issues raise `RunReportError` with the offending file path—inspect the JSON in `.agents/runs/<run_id>/reports/` to fix formatting.

**Getting Help:**
```bash
python -m agent_orchestrator.cli --help
python -m agent_orchestrator.cli run --help
```

## Technical Architecture

### Core Components

- **Orchestrator**: Manages workflow execution, dependencies, and state persistence. Supports repository-level prompt overrides via `.agents/prompts/` for per-repository customization
- **Runner**: Handles agent process execution with configurable templates
- **State Manager**: Tracks execution progress and enables resume/retry capabilities
- **Report Reader**: Validates and processes agent output reports, retries transient JSON parse failures, and surfaces consistent `RunReportError`s when ingestion ultimately fails
- **Gate Evaluator**: Controls workflow progression based on external conditions
- **Time Utilities**: `time_utils.utc_now()` provides a single, timezone-aware timestamp source for run reports and wrapper logs (Python 3.13+ safe)

### Agent Contracts

Each agent must:
1. Read the assigned prompt file
2. Perform its designated task on the target repository
3. Produce artifacts in standardized locations
4. Write a compliant run report to `${REPORT_PATH}`

### Workflow Definition Format

```yaml
name: workflow_name
description: Workflow description
steps:
  - id: step_identifier
    agent: agent_name
    prompt: path/to/prompt.md
    needs: [prerequisite_step_ids]
    loop_back_to: optional_previous_step_id  # optional
    next_on_success: [successor_step_ids]
    gates: [optional_gate_conditions]
    human_in_the_loop: true/false
    loop:  # optional - for iterating over collections
      items: [...]                      # static list
      items_from_step: step_id          # or reference to previous step
      items_from_artifact: path         # or path to artifact file
      item_var: item                    # variable name (default: "item")
      index_var: index                  # index variable (default: "index")
      max_iterations: 10                # optional limit
    metadata:
      key: value
```

## Project Layout

- `src/agent_orchestrator/` — Main package code
  - `orchestrator.py` — Core workflow execution engine with loop control support
  - `runner.py` — Agent process management
  - `cli.py` — Command-line interface
  - `models.py` — Data structures and contracts (includes LoopConfig)
  - `workflow.py` — Workflow loading and validation
  - `state.py` — Execution state persistence
  - `reporting.py` — Run report validation and parsing
  - `time_utils.py` — Timezone-aware timestamp helpers shared across the orchestrator
  - `gating.py` — Conditional workflow progression
  - `prompts/` — Standard agent prompt templates
    - `24_story_breakdown.md` — Story decomposition for large tasks
    - `25_story_detail_planner.md` — Detailed planning for individual stories
  - `wrappers/` — Agent execution adapters
  - `scripts/` — Utility scripts
    - `run_workflow.sh` — Convenience script for running workflows
- `src/agent_orchestrator/workflows/workflow.yaml` — Complete SDLC pipeline definition
- `src/agent_orchestrator/workflows/workflow_backlog_miner.yaml` — Architecture and tech debt analysis workflow
- `src/agent_orchestrator/workflows/workflow_large_work.yaml` — Multi-story development with loop control
- `requirements.txt` — Python dependencies
- `README.md` — This comprehensive guide

## Getting Started with Real Projects

### Example: E-commerce Website Analysis
```bash
# Analyze an e-commerce repository for technical debt
git clone https://github.com/yourorg/ecommerce-site.git
cd path/to/agent_orchestrator

python -m agent_orchestrator.cli --log-level INFO run \
  --repo ../ecommerce-site \
  --workflow src/agent_orchestrator/workflows/workflow_backlog_miner.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py
```

### Example: Feature Development Pipeline
```bash
# Run complete development workflow on a new feature branch
cd your-project
git checkout -b feature/user-authentication

cd path/to/agent_orchestrator
python -m agent_orchestrator.cli run \
  --repo ../your-project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --pause-for-human-input \
  --env FEATURE_DESCRIPTION="Add OAuth2 user authentication"
```

For detailed architecture documentation and contracts, see `sdlc_agents_orchestrator_guide.md`.
