import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "src" / "agent_orchestrator" / "scripts" / "install_systemd_timer.sh"
WORKFLOW_PATH = REPO_ROOT / "src" / "agent_orchestrator" / "workflows" / "workflow_backlog_miner.yaml"
WRAPPER_PATH = REPO_ROOT / "src" / "agent_orchestrator" / "wrappers" / "codex_wrapper.py"


def run_installer(tmp_path, args):
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["SKIP_SYSTEMCTL"] = "1"
    # Provide a dummy flock for macOS where it's not available by default
    if "FLOCK_BIN" not in env:
        env["FLOCK_BIN"] = "/usr/bin/true"
    command = ["bash", str(SCRIPT_PATH)] + args
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )


def test_install_writes_units_and_runner(tmp_path):
    target_repo = tmp_path / "repo"
    target_repo.mkdir()

    log_dir = tmp_path / "logs"
    unit_name = "nightly-review"

    run_installer(
        tmp_path,
        [
            "install",
            "--repo",
            str(target_repo),
            "--workflow",
            str(WORKFLOW_PATH),
            "--wrapper",
            str(WRAPPER_PATH),
            "--python",
            sys.executable,
            "--unit-name",
            unit_name,
            "--calendar",
            "*:0/15",
            "--randomized-delay",
            "90",
            "--log-dir",
            str(log_dir),
            "--wrapper-arg",
            "--foo",
            "--wrapper-arg",
            "bar",
            "--env",
            "CODEX_EXEC_BIN=/usr/bin/codex",
        ],
    )

    config_dir = tmp_path / "config" / "systemd" / "user"
    service_unit = config_dir / f"{unit_name}.service"
    timer_unit = config_dir / f"{unit_name}.timer"
    runner_script = target_repo / ".agents" / "systemd" / f"{unit_name}.sh"
    log_file = log_dir / f"{unit_name}.log"

    assert service_unit.exists()
    assert timer_unit.exists()
    assert runner_script.exists()
    assert log_file.exists()

    service_text = service_unit.read_text()
    runner_quote = shlex.quote(str(runner_script))
    assert f"ExecStart={runner_quote}" in service_text
    assert "WorkingDirectory=" in service_text
    assert "WantedBy=default.target" in service_text

    timer_text = timer_unit.read_text()
    assert "OnCalendar=*:0/15" in timer_text
    assert "RandomizedDelaySec=90" in timer_text
    assert f"Unit={unit_name}.service" in timer_text

    runner_text = runner_script.read_text()
    assert f'cd "{target_repo}"' in runner_text
    assert f'--repo "{target_repo}"' in runner_text
    assert f'--workflow "{WORKFLOW_PATH}"' in runner_text
    assert 'agent_orchestrator.cli \\' in runner_text
    assert '--log-level "INFO"' in runner_text
    assert 'run \\' in runner_text
    assert '--wrapper-arg "--foo"' in runner_text
    assert '--wrapper-arg "bar"' in runner_text
    assert 'export CODEX_EXEC_BIN="/usr/bin/codex"' in runner_text

    mode = runner_script.stat().st_mode
    assert mode & stat.S_IXUSR

    # Running install twice should succeed without modifying content
    before = runner_script.read_text()
    run_installer(
        tmp_path,
        [
            "install",
            "--repo",
            str(target_repo),
            "--workflow",
            str(WORKFLOW_PATH),
            "--wrapper",
            str(WRAPPER_PATH),
            "--python",
            sys.executable,
            "--unit-name",
            unit_name,
            "--calendar",
            "*:0/15",
            "--randomized-delay",
            "90",
            "--log-dir",
            str(log_dir),
            "--wrapper-arg",
            "--foo",
            "--wrapper-arg",
            "bar",
            "--env",
            "CODEX_EXEC_BIN=/usr/bin/codex",
            "--no-enable",
        ],
    )
    after = runner_script.read_text()
    assert before == after


def test_uninstall_removes_units(tmp_path):
    target_repo = tmp_path / "repo"
    target_repo.mkdir()

    unit_name = "cleanup"
    run_installer(
        tmp_path,
        [
            "install",
            "--repo",
            str(target_repo),
            "--workflow",
            str(WORKFLOW_PATH),
            "--wrapper",
            str(WRAPPER_PATH),
            "--python",
            sys.executable,
            "--unit-name",
            unit_name,
            "--no-enable",
        ],
    )

    run_installer(
        tmp_path,
        [
            "uninstall",
            "--repo",
            str(target_repo),
            "--unit-name",
            unit_name,
        ],
    )

    config_dir = tmp_path / "config" / "systemd" / "user"
    assert not (config_dir / f"{unit_name}.service").exists()
    assert not (config_dir / f"{unit_name}.timer").exists()
    assert not (target_repo / ".agents" / "systemd" / f"{unit_name}.sh").exists()
