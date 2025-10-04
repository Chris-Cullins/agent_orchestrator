#!/usr/bin/env bash
set -euo pipefail

SYSTEMCTL_BIN=${SYSTEMCTL_BIN:-systemctl}
SKIP_SYSTEMCTL=${SKIP_SYSTEMCTL:-0}
DEFAULT_CALENDAR=${DEFAULT_CALENDAR:-'*:0/30'}
DEFAULT_RANDOMIZED_DELAY=${DEFAULT_RANDOMIZED_DELAY:-'0'}
DEFAULT_LOG_LEVEL=${DEFAULT_LOG_LEVEL:-'INFO'}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_WRAPPER="${SCRIPT_DIR}/../wrappers/codex_wrapper.py"

PYTHON_HELPER="${PYTHON_HELPER:-$(command -v python3 || command -v python || true)}"

if [[ -z "${PYTHON_HELPER}" ]]; then
    echo "Error: python3 or python is required to run this installer" >&2
    exit 1
fi

usage() {
    cat <<'EOF'
Usage: install_systemd_timer.sh <command> [options]

Commands:
  install     Generate and enable user-level systemd units for a workflow timer
  uninstall   Disable and remove previously installed units
  help        Show this help message

Common options:
  --unit-name NAME           Override the base name for generated service/timer units
  --skip-systemctl           Skip systemctl invocations (useful for dry-runs/tests)

Install options:
  --repo PATH                (required) Target repository for orchestrator runs
  --workflow PATH            (required) Workflow YAML to execute
  --wrapper PATH             Wrapper script path (default: codex wrapper)
  --python PATH              Python interpreter to embed (default: python3 on PATH)
  --calendar EXPRESSION      systemd OnCalendar schedule (default: *:0/30)
  --randomized-delay SEC     RandomizedDelaySec value (default: 0 = disabled)
  --log-dir PATH             Directory for stdout/stderr capture (default: <repo>/.agents/systemd-logs/<unit>)
  --wrapper-arg VALUE        Additional --wrapper-arg passed through (repeatable)
  --env KEY=VALUE            Environment override exported before launch (repeatable)
  --no-enable                Do not enable/start the timer after installation
  --start-now                Trigger the service immediately after enabling

Uninstall options:
  --repo PATH                (required) Repository path used during install (removes helper script)

Examples:
  # Install a timer that runs every 15 minutes
  ./install_systemd_timer.sh install \
      --repo /repos/customer-api \
      --workflow src/agent_orchestrator/workflows/workflow_pr_review_fix.yaml \
      --wrapper src/agent_orchestrator/wrappers/claude_wrapper.py \
      --calendar '*/15:00' \
      --unit-name customer-api-pr

  # Remove the timer later on
  ./install_systemd_timer.sh uninstall --repo /repos/customer-api --unit-name customer-api-pr
EOF
}

error() {
    echo "Error: $*" >&2
    exit 1
}

escape_for_double_quotes() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '%s' "$value"
}

quote_for_systemd() {
    "${PYTHON_HELPER}" -c 'import os, sys, shlex; print(shlex.quote(os.path.expanduser(sys.argv[1])))' "$1"
}

resolve_path() {
    "${PYTHON_HELPER}" -c 'import os, sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$1"
}

sanitize_unit_name() {
    local raw="$1"
    local value
    value="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
    value="${value//[^a-z0-9]/-}"
    while [[ "$value" == *--* ]]; do
        value="${value//--/-}"
    done
    while [[ "$value" == -* ]]; do
        value="${value#-}"
    done
    while [[ "$value" == *- ]]; do
        value="${value%-}"
    done
    if [[ -z "$value" ]]; then
        value="agent-orchestrator"
    fi
    printf '%s' "$value"
}

run_systemctl() {
    if [[ "$SKIP_SYSTEMCTL" == "1" ]]; then
        echo "[skip] ${SYSTEMCTL_BIN} --user $*"
        return 0
    fi

    if ! command -v "$SYSTEMCTL_BIN" >/dev/null 2>&1; then
        local missing_msg
        missing_msg="systemctl binary not found; expected '${SYSTEMCTL_BIN}'. Set SYSTEMCTL_BIN or install systemd."
        error "$missing_msg"
    fi

    if ! "$SYSTEMCTL_BIN" --user "$@"; then
        local failure_msg
        failure_msg="systemctl --user $* failed. Ensure a user systemd instance is active. For example, run: loginctl enable-linger <username>"
        error "$failure_msg"
    fi
}

install_units() {
    local repo_path=""
    local workflow_path=""
    local wrapper_path=""
    local python_bin=""
    local unit_name=""
    local calendar="${DEFAULT_CALENDAR}"
    local randomized_delay="${DEFAULT_RANDOMIZED_DELAY}"
    local log_dir=""
    local skip_enable=0
    local start_now=0
    local wrapper_args=()
    local env_pairs=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo)
                [[ $# -ge 2 ]] || error "--repo requires a value"
                repo_path="$2"
                shift 2
                ;;
            --workflow)
                [[ $# -ge 2 ]] || error "--workflow requires a value"
                workflow_path="$2"
                shift 2
                ;;
            --wrapper)
                [[ $# -ge 2 ]] || error "--wrapper requires a value"
                wrapper_path="$2"
                shift 2
                ;;
            --python)
                [[ $# -ge 2 ]] || error "--python requires a value"
                python_bin="$2"
                shift 2
                ;;
            --unit-name)
                [[ $# -ge 2 ]] || error "--unit-name requires a value"
                unit_name="$2"
                shift 2
                ;;
            --calendar)
                [[ $# -ge 2 ]] || error "--calendar requires a value"
                calendar="$2"
                shift 2
                ;;
            --randomized-delay)
                [[ $# -ge 2 ]] || error "--randomized-delay requires a value"
                randomized_delay="$2"
                shift 2
                ;;
            --log-dir)
                [[ $# -ge 2 ]] || error "--log-dir requires a value"
                log_dir="$2"
                shift 2
                ;;
            --wrapper-arg)
                [[ $# -ge 2 ]] || error "--wrapper-arg requires a value"
                wrapper_args+=("$2")
                shift 2
                ;;
            --env)
                [[ $# -ge 2 ]] || error "--env requires KEY=VALUE"
                env_pairs+=("$2")
                shift 2
                ;;
            --no-enable)
                skip_enable=1
                shift
                ;;
            --start-now)
                start_now=1
                shift
                ;;
            --skip-systemctl)
                SKIP_SYSTEMCTL=1
                shift
                ;;
            --repo=*)
                repo_path="${1#*=}"
                shift
                ;;
            --workflow=*)
                workflow_path="${1#*=}"
                shift
                ;;
            --wrapper=*)
                wrapper_path="${1#*=}"
                shift
                ;;
            --python=*)
                python_bin="${1#*=}"
                shift
                ;;
            --unit-name=*)
                unit_name="${1#*=}"
                shift
                ;;
            --calendar=*)
                calendar="${1#*=}"
                shift
                ;;
            --randomized-delay=*)
                randomized_delay="${1#*=}"
                shift
                ;;
            --log-dir=*)
                log_dir="${1#*=}"
                shift
                ;;
            --wrapper-arg=*)
                wrapper_args+=("${1#*=}")
                shift
                ;;
            --env=*)
                env_pairs+=("${1#*=}")
                shift
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                error "Unknown option for install: $1"
                ;;
        esac
    done

    [[ -n "$repo_path" ]] || error "--repo is required"
    [[ -n "$workflow_path" ]] || error "--workflow is required"

    repo_path="$(resolve_path "$repo_path")"
    [[ -d "$repo_path" ]] || error "Repository not found: $repo_path"

    workflow_path="$(resolve_path "$workflow_path")"
    [[ -f "$workflow_path" ]] || error "Workflow file not found: $workflow_path"

    if [[ -z "$wrapper_path" ]]; then
        wrapper_path="$DEFAULT_WRAPPER"
    fi
    wrapper_path="$(resolve_path "$wrapper_path")"
    [[ -f "$wrapper_path" ]] || error "Wrapper file not found: $wrapper_path"

    if [[ -z "$python_bin" ]]; then
        python_bin="$(command -v python3 || command -v python || true)"
    else
        python_bin="$(resolve_path "$python_bin")"
    fi
    [[ -n "$python_bin" ]] || error "Python interpreter not found; pass --python"
    [[ -x "$python_bin" ]] || error "Python interpreter is not executable: $python_bin"

    local flock_bin=""
    local use_flock=1

    if [[ -n "${FLOCK_BIN:-}" ]]; then
        if command -v "${FLOCK_BIN}" >/dev/null 2>&1; then
            flock_bin="$(command -v "${FLOCK_BIN}")"
        elif [[ -x "${FLOCK_BIN}" ]]; then
            flock_bin="$(resolve_path "${FLOCK_BIN}")"
        else
            error "flock binary specified via FLOCK_BIN not found or not executable: ${FLOCK_BIN}"
        fi
    else
        flock_bin="$(command -v flock || true)"
        if [[ -z "$flock_bin" ]]; then
            use_flock=0
        fi
    fi

    if [[ -z "$unit_name" ]]; then
        local repo_base workflow_base
        repo_base="$(basename "$repo_path")"
        workflow_base="$(basename "$workflow_path")"
        workflow_base="${workflow_base%.yaml}"
        unit_name="agent-orchestrator-${repo_base}-${workflow_base}"
    fi
    unit_name="$(sanitize_unit_name "$unit_name")"

    local config_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
    local agents_dir="$repo_path/.agents"
    local runner_dir="$agents_dir/systemd"
    local lock_dir="$agents_dir/locks"
    local default_log_dir="$agents_dir/systemd-logs/$unit_name"
    if [[ -z "$log_dir" ]]; then
        log_dir="$default_log_dir"
    fi
    log_dir="$(resolve_path "$log_dir")"

    local runner_script="$runner_dir/$unit_name.sh"
    local lock_file="$lock_dir/$unit_name.lock"
    local service_unit="$config_dir/$unit_name.service"
    local timer_unit="$config_dir/$unit_name.timer"
    local log_file="$log_dir/$unit_name.log"

    mkdir -p "$config_dir" "$runner_dir" "$log_dir" "$lock_dir"

    local escaped_log="$(escape_for_double_quotes "$log_file")"
    local escaped_log_dir="$(escape_for_double_quotes "$log_dir")"
    local escaped_repo="$(escape_for_double_quotes "$repo_path")"
    local escaped_workflow="$(escape_for_double_quotes "$workflow_path")"
    local escaped_wrapper="$(escape_for_double_quotes "$wrapper_path")"
    local escaped_python="$(escape_for_double_quotes "$python_bin")"
    local escaped_lock="$(escape_for_double_quotes "$lock_file")"
    local escaped_flock=""
    if (( use_flock )); then
        escaped_flock="$(escape_for_double_quotes "$flock_bin")"
    fi

    {
        printf '#!/usr/bin/env bash
'
        printf 'set -euo pipefail

'
        printf 'LOG_FILE="%s"
' "$escaped_log"
        printf 'mkdir -p "%s"
' "$escaped_log_dir"
        printf 'touch "%s"
' "$escaped_log"
        printf 'exec >>"%s" 2>&1

' "$escaped_log"

        if (( ${#env_pairs[@]} > 0 )); then
            for env_entry in "${env_pairs[@]}"; do
                [[ "$env_entry" == *=* ]] || error "Invalid --env entry: expected KEY=VALUE but got $env_entry"
                local key="${env_entry%%=*}"
                local value="${env_entry#*=}"
                local escaped_value="$(escape_for_double_quotes "$value")"
                printf 'export %s="%s"
' "$key" "$escaped_value"
            done
            printf '
'
        fi

        printf 'cd "%s"

' "$escaped_repo"

        if (( use_flock )); then
            printf 'exec "%s" -n "%s" -- "%s" -m agent_orchestrator.cli \
' "$escaped_flock" "$escaped_lock" "$escaped_python"
            printf '  --log-level "%s" \
' "$DEFAULT_LOG_LEVEL"
            printf '  run \
'
            printf '  --repo "%s" \
' "$escaped_repo"
            printf '  --workflow "%s" \
' "$escaped_workflow"
            printf '  --wrapper "%s" \
' "$escaped_wrapper"
            printf '  --logs-dir "%s"' "$escaped_log_dir"
            if (( ${#wrapper_args[@]} > 0 || ${#env_pairs[@]} > 0 )); then
                printf ' \
'
            else
                printf '
'
            fi

            if (( ${#wrapper_args[@]} > 0 )); then
                local idx=0
                for arg in "${wrapper_args[@]}"; do
                    local escaped_arg="$(escape_for_double_quotes "$arg")"
                    printf '  --wrapper-arg "%s"' "$escaped_arg"
                    (( idx++ ))
                    if (( idx < ${#wrapper_args[@]} || ${#env_pairs[@]} > 0 )); then
                        printf ' \
'
                    else
                        printf '
'
                    fi
                done
            fi

            if (( ${#env_pairs[@]} > 0 )); then
                local env_idx=0
                for env_entry in "${env_pairs[@]}"; do
                    local escaped_env="$(escape_for_double_quotes "$env_entry")"
                    printf '  --env "%s"' "$escaped_env"
                    (( env_idx++ ))
                    if (( env_idx < ${#env_pairs[@]} )); then
                        printf ' \
'
                    else
                        printf '
'
                    fi
                done
            fi
        else
            printf 'LOCK_FILE="%s"
' "$escaped_lock"
            printf 'PYTHON_BIN="%s"
' "$escaped_python"
            printf 'COMMAND=(
'
            printf '  "%s"
' "$escaped_python"
            printf '  "-m"
'
            printf '  "agent_orchestrator.cli"
'
            printf '  "--log-level"
'
            printf '  "%s"
' "$DEFAULT_LOG_LEVEL"
            printf '  "run"
'
            printf '  "--repo"
'
            printf '  "%s"
' "$escaped_repo"
            printf '  "--workflow"
'
            printf '  "%s"
' "$escaped_workflow"
            printf '  "--wrapper"
'
            printf '  "%s"
' "$escaped_wrapper"
            printf '  "--logs-dir"
'
            printf '  "%s"
' "$escaped_log_dir"

            if (( ${#wrapper_args[@]} > 0 )); then
                for arg in "${wrapper_args[@]}"; do
                    local escaped_arg="$(escape_for_double_quotes "$arg")"
                    printf '  "--wrapper-arg"
'
                    printf '  "%s"
' "$escaped_arg"
                done
            fi

            if (( ${#env_pairs[@]} > 0 )); then
                for env_entry in "${env_pairs[@]}"; do
                    local escaped_env="$(escape_for_double_quotes "$env_entry")"
                    printf '  "--env"
'
                    printf '  "%s"
' "$escaped_env"
                done
            fi

            printf ')

'
            printf '"$PYTHON_BIN" - "$LOCK_FILE" "${COMMAND[@]}" <<'''PYLOCK'''
'
            printf 'import errno
'
            printf 'import fcntl
'
            printf 'import os
'
            printf 'import subprocess
'
            printf 'import sys

'
            printf 'if len(sys.argv) < 3:
'
            printf '    sys.exit("lock path and command required")

'
            printf 'lock_path = sys.argv[1]
'
            printf 'command = sys.argv[2:]
'
            printf 'fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
'
            printf 'try:
'
            printf '    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
'
            printf 'except OSError as exc:
'
            printf '    if exc.errno in (errno.EACCES, errno.EAGAIN):
'
            printf '        print(f"Lock busy at {lock_path}, skipping run.")
'
            printf '        os.close(fd)
'
            printf '        sys.exit(0)
'
            printf '    os.close(fd)
'
            printf '    raise
'
            printf 'try:
'
            printf '    result = subprocess.run(command, check=False)
'
            printf '    sys.exit(result.returncode)
'
            printf 'finally:
'
            printf '    os.close(fd)
'
            printf 'PYLOCK
'
            printf 'exit $?
'
        fi

    } >"$runner_script"

    chmod +x "$runner_script"
    touch "$log_file"

    local working_dir="$(resolve_path "$repo_path")"
    local quoted_runner="$(quote_for_systemd "$runner_script")"

    {
        echo "[Unit]"
        echo "Description=Agent orchestrator workflow (${unit_name})"
        echo "After=default.target"
        echo ""
        echo "[Service]"
        echo "Type=oneshot"
        echo "WorkingDirectory=$working_dir"
        echo "ExecStart=$quoted_runner"
        echo "TimeoutStartSec=0"
        echo ""
        echo "[Install]"
        echo "WantedBy=default.target"
    } >"$service_unit"

    {
        echo "[Unit]"
        echo "Description=Agent orchestrator scheduler (${unit_name})"
        echo ""
        echo "[Timer]"
        echo "OnCalendar=$calendar"
        echo "AccuracySec=1min"
        echo "Persistent=true"
        if [[ -n "$randomized_delay" && "$randomized_delay" != "0" ]]; then
            echo "RandomizedDelaySec=$randomized_delay"
        fi
        echo "Unit=${unit_name}.service"
        echo ""
        echo "[Install]"
        echo "WantedBy=timers.target"
    } >"$timer_unit"

    run_systemctl daemon-reload

    if (( skip_enable )); then
        echo "Generated $service_unit and $timer_unit. Enable manually with: systemctl --user enable --now ${unit_name}.timer"
    else
        run_systemctl enable --now "${unit_name}.timer"
        if (( start_now )); then
            run_systemctl start "${unit_name}.service"
        fi
        echo "Installed systemd units ${unit_name}.service and ${unit_name}.timer"
    fi

    echo "Runner script: $runner_script"
    echo "Logs captured to: $log_file"
    echo "Lock file: $lock_file"
}

uninstall_units() {
    local repo_path=""
    local unit_name=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo)
                [[ $# -ge 2 ]] || error "--repo requires a value"
                repo_path="$2"
                shift 2
                ;;
            --unit-name)
                [[ $# -ge 2 ]] || error "--unit-name requires a value"
                unit_name="$2"
                shift 2
                ;;
            --skip-systemctl)
                SKIP_SYSTEMCTL=1
                shift
                ;;
            --repo=*)
                repo_path="${1#*=}"
                shift
                ;;
            --unit-name=*)
                unit_name="${1#*=}"
                shift
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                error "Unknown option for uninstall: $1"
                ;;
        esac
    done

    [[ -n "$repo_path" ]] || error "--repo is required for uninstall"
    [[ -n "$unit_name" ]] || error "--unit-name is required for uninstall"

    repo_path="$(resolve_path "$repo_path")"
    unit_name="$(sanitize_unit_name "$unit_name")"

    local config_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
    local service_unit="$config_dir/$unit_name.service"
    local timer_unit="$config_dir/$unit_name.timer"
    local runner_script="$repo_path/.agents/systemd/$unit_name.sh"
    local lock_file="$repo_path/.agents/locks/$unit_name.lock"

    if [[ -f "$timer_unit" ]]; then
        run_systemctl disable --now "${unit_name}.timer"
    fi
    if [[ -f "$service_unit" ]]; then
        run_systemctl disable "${unit_name}.service" || true
    fi

    rm -f "$service_unit" "$timer_unit" "$runner_script" "$lock_file"
    echo "Removed systemd units and helper script for ${unit_name}"
}

main() {
    if [[ $# -eq 0 ]]; then
        usage
        exit 1
    fi

    local command="$1"
    shift

    case "$command" in
        install)
            install_units "$@"
            ;;
        uninstall)
            uninstall_units "$@"
            ;;
        help|-h|--help)
            usage
            ;;
        *)
            error "Unknown command: $command"
            ;;
    esac
}

main "$@"
