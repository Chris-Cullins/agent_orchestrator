#!/usr/bin/env bash
set -euo pipefail

# Script to run agent orchestrator workflows
# Usage: ./run_workflow.sh [--repo PATH] [--workflow PATH] [--wrapper PATH]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCHESTRATOR_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Default values
REPO_PATH="${PWD}"
WORKFLOW_PATH="${ORCHESTRATOR_ROOT}/src/agent_orchestrator/workflows/workflow_backlog_miner.yaml"
WRAPPER_PATH="${ORCHESTRATOR_ROOT}/src/agent_orchestrator/wrappers/claude_wrapper.py"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --repo)
            REPO_PATH="$2"
            shift 2
            ;;
        --workflow)
            WORKFLOW_PATH="$2"
            shift 2
            ;;
        --wrapper)
            WRAPPER_PATH="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --repo PATH       Path to target repository (default: current directory)"
            echo "  --workflow PATH   Path to workflow YAML file (default: src/agent_orchestrator/workflows/workflow_backlog_miner.yaml)"
            echo "  --wrapper PATH    Path to agent wrapper script (default: claude_wrapper.py)"
            echo "  -h, --help        Show this help message"
            exit 0
            ;;
        *)
            echo "Error: Unknown option $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate paths
if [[ ! -d "$REPO_PATH" ]]; then
    echo "Error: Repository path does not exist: $REPO_PATH"
    exit 1
fi

if [[ ! -f "$WORKFLOW_PATH" ]]; then
    echo "Error: Workflow file does not exist: $WORKFLOW_PATH"
    exit 1
fi

if [[ ! -f "$WRAPPER_PATH" ]]; then
    echo "Error: Wrapper script does not exist: $WRAPPER_PATH"
    exit 1
fi

# Convert to absolute paths
REPO_PATH="$(cd "$REPO_PATH" && pwd)"
WORKFLOW_PATH="$(cd "$(dirname "$WORKFLOW_PATH")" && pwd)/$(basename "$WORKFLOW_PATH")"
WRAPPER_PATH="$(cd "$(dirname "$WRAPPER_PATH")" && pwd)/$(basename "$WRAPPER_PATH")"

echo "========================================="
echo "Agent Orchestrator Workflow Runner"
echo "========================================="
echo "Repository:  $REPO_PATH"
echo "Workflow:    $WORKFLOW_PATH"
echo "Wrapper:     $WRAPPER_PATH"
echo "========================================="
echo ""

# Run the orchestrator
cd "$ORCHESTRATOR_ROOT"
python3 -m src.agent_orchestrator run \
    --repo "$REPO_PATH" \
    --workflow "$WORKFLOW_PATH" \
    --wrapper "$WRAPPER_PATH"

echo ""
echo "========================================="
echo "Workflow completed!"
echo "Check $REPO_PATH/.agents/ for outputs"
echo "========================================="
