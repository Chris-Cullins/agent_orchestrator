# SDLC Agents Orchestrator

A production-ready, file-driven orchestrator for chaining SDLC agents via run report files. This system automates software development workflows by orchestrating AI agents that handle planning, coding, testing, review, documentation, and deployment tasks.

## How to Use This Application on Your Code Repository

### Prerequisites

1. **Python Environment**: Python 3.10+ (Python 3.13+ fully supported) with virtual environment support
2. **AI Agent Platform**: Access to `codex exec` or similar AI agent execution platform
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

# Configure PATH for codex (if using Homebrew installation)
export PATH="/opt/homebrew/bin:/opt/homebrew/Cellar/node/24.5.0/bin:$PATH"
```

### Step 2: Choose Your Workflow

Select one of the predefined workflows or create your own:

**Available Workflows:**
- `src/agent_orchestrator/workflows/workflow.yaml` - Complete SDLC pipeline (planning → coding → testing → review → docs → merge)
- `src/agent_orchestrator/workflows/workflow_backlog_miner.yaml` - Architecture review and tech debt analysis

### Step 3: Configure Your AI Agent Platform

The orchestrator supports multiple AI agent platforms through different wrappers:

#### Claude CLI (Anthropic) - Recommended
```bash
# Ensure Claude CLI is installed and authenticated
claude --version

# Run with Claude (recommended for quality)
python -m agent_orchestrator run \
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
python -m agent_orchestrator run \
  --repo /path/to/your/target/repository \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py
```

#### Mock Wrapper (For Testing)
```bash
# Note: mock_wrapper.py is not currently included in this repository
# Use claude_wrapper.py or codex_wrapper.py instead
python -m agent_orchestrator run \
  --repo /path/to/your/target/repository \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py
```

#### Custom Command Template
```bash
python -m agent_orchestrator run \
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
- `--wrapper PATH` - Path to agent wrapper script (default: claude_wrapper.py)
- `--help` - Show help message

#### Manual Execution: Complete SDLC Pipeline
```bash
# Full development workflow on your repository using Claude
python -m agent_orchestrator run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
  --pause-for-human-input \
  --log-level INFO
```

#### Manual Execution: Architecture and Tech Debt Analysis
```bash
# Analyze your codebase for technical debt and architecture misalignments
python -m agent_orchestrator run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow_backlog_miner.yaml \
  --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py
```

#### Run with Custom Environment and Configuration
```bash
python -m agent_orchestrator run \
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

#### Run with Automated Git Worktree Isolation
```bash
python -m agent_orchestrator run \
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

### Step 5: Understanding Output and Artifacts

When you run the orchestrator, it creates a structured output in your target repository:

```
your-target-repo/
├── .agents/                          # Orchestrator working directory
│   ├── run_state.json               # Current execution state
│   ├── run_reports/                 # Agent execution reports
│   │   └── {run_id}__{step_id}.json
│   ├── logs/                        # Agent stdout/stderr logs
│   │   └── {run_id}__{step_id}__attempt{N}.log
│   ├── plan/                        # Planning artifacts
│   │   └── tasks.yaml
│   ├── manual/                      # Manual testing plans
│   │   └── MANUAL_TEST_PLAN.md
│   ├── review/                      # Code review reports
│   │   └── REVIEW.md
│   ├── pr/                          # PR metadata
│   │   └── metadata.json
│   └── runs/                        # Archived runs when worktrees are cleaned up
│       └── <run_id>/                # Copied logs and reports from the run
├── backlog/                         # Strategic planning outputs
│   ├── architecture_alignment.md
│   └── tech_debt.md
├── PLAN.md                          # High-level project plan
├── CHANGELOG.md                     # Updated with new features
└── (your existing code...)
```

### Step 6: Advanced Configuration

#### Human-in-the-Loop Integration
Enable manual steps that require human input:
```bash
python -m agent_orchestrator run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --pause-for-human-input
```

When a manual step is reached, provide input via:
```bash
# The orchestrator will wait for this file
echo '{"approved": true, "comments": "LGTM"}' > \
  /path/to/your/project/.agents/run_inputs/{run_id}__{step_id}.json
```

#### CI/CD Integration with Gates
Use gate conditions to control workflow progression:
```bash
# Create gate state file
echo '{"ci.tests": true, "security.scan": true}' > gates.json

python -m agent_orchestrator run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper codex_wrapper.py \
  --gate-state-file gates.json
```

#### Custom Working Directory and Logs
```bash
python -m agent_orchestrator run \
  --repo /path/to/your/project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --workdir /tmp/agent-workspace \
  --logs-dir /var/log/agents \
  --state-file custom_state.json
```

### Step 7: Creating Custom Workflows

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

### Step 8: Monitoring and Debugging

#### View Execution Status
```bash
# Check current run state
cat /path/to/your/project/.agents/run_state.json

# Monitor logs in real-time
tail -f /path/to/your/project/.agents/logs/*.log
```

#### Common Command-Line Options
- `--log-level DEBUG` - Verbose logging for troubleshooting
- `--max-attempts 3` - Retry failed steps up to 3 times
- `--poll-interval 0.5` - Check for completion every 0.5 seconds
- `--schema path/to/schema.json` - Validate run reports against JSON schema

### Troubleshooting

**Common Issues:**
1. **Missing Agent Binary**: Ensure `codex exec` or your agent runner is in PATH
2. **Permission Errors**: Check write permissions on target repository
3. **Failed Steps**: Review logs in `.agents/logs/` directory
4. **Workflow Validation**: Verify YAML syntax and step dependencies

**Getting Help:**
```bash
python -m agent_orchestrator --help
python -m agent_orchestrator run --help
```

## Technical Architecture

### Core Components

- **Orchestrator**: Manages workflow execution, dependencies, and state persistence
- **Runner**: Handles agent process execution with configurable templates
- **State Manager**: Tracks execution progress and enables resume/retry capabilities  
- **Report Reader**: Validates and processes agent output reports
- **Gate Evaluator**: Controls workflow progression based on external conditions

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
    next_on_success: [successor_step_ids]
    gates: [optional_gate_conditions]
    human_in_the_loop: true/false
    metadata:
      key: value
```

## Project Layout

- `src/agent_orchestrator/` — Main package code
  - `orchestrator.py` — Core workflow execution engine
  - `runner.py` — Agent process management
  - `cli.py` — Command-line interface
  - `models.py` — Data structures and contracts
  - `workflow.py` — Workflow loading and validation
  - `state.py` — Execution state persistence
  - `reporting.py` — Run report validation and parsing
  - `gating.py` — Conditional workflow progression
  - `prompts/` — Standard agent prompt templates
  - `wrappers/` — Agent execution adapters
  - `scripts/` — Utility scripts
    - `run_workflow.sh` — Convenience script for running workflows
- `src/agent_orchestrator/workflows/workflow.yaml` — Complete SDLC pipeline definition
- `src/agent_orchestrator/workflows/workflow_backlog_miner.yaml` — Architecture and tech debt analysis workflow
- `requirements.txt` — Python dependencies
- `README.md` — This comprehensive guide

## Getting Started with Real Projects

### Example: E-commerce Website Analysis
```bash
# Analyze an e-commerce repository for technical debt
git clone https://github.com/yourorg/ecommerce-site.git
cd path/to/agent_orchestrator

python -m agent_orchestrator run \
  --repo ../ecommerce-site \
  --workflow src/agent_orchestrator/workflows/workflow_backlog_miner.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --log-level INFO
```

### Example: Feature Development Pipeline
```bash
# Run complete development workflow on a new feature branch
cd your-project
git checkout -b feature/user-authentication

cd path/to/agent_orchestrator
python -m agent_orchestrator run \
  --repo ../your-project \
  --workflow src/agent_orchestrator/workflows/workflow.yaml \
  --wrapper src/agent_orchestrator/wrappers/codex_wrapper.py \
  --pause-for-human-input \
  --env FEATURE_DESCRIPTION="Add OAuth2 user authentication"
```

For detailed architecture documentation and contracts, see `sdlc_agents_orchestrator_guide.md`.
