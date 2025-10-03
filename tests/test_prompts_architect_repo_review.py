from __future__ import annotations

from pathlib import Path

from agent_orchestrator.run_report_format import build_run_report_instructions


def test_architect_prompt_includes_standard_run_report_block() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    prompt_path = repo_root / "src" / "agent_orchestrator" / "prompts" / "08_architect_repo_review.md"
    prompt_content = prompt_path.read_text(encoding="utf-8")

    expected_block = build_run_report_instructions(
        run_id="${RUN_ID}",
        step_id="${STEP_ID}",
        agent="backlog_architect",
        started_at="${STARTED_AT}",
    ).strip()

    assert expected_block in prompt_content
    assert prompt_content.strip().endswith(expected_block)
