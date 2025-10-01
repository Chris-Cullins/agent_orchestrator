# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Replace deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` for Python 3.13+ compatibility
  - Updated `src/agent_orchestrator/models.py`
  - Updated `src/agent_orchestrator/wrappers/claude_wrapper.py`
  - Updated `src/agent_orchestrator/wrappers/codex_wrapper.py`
- Update wrapper file references in documentation
  - Fixed all references from `codex_exec_wrapper.py` to `codex_wrapper.py` in `README.md`
  - Fixed all references from `real_codex_wrapper.py` to `codex_wrapper.py` in `README.md`
  - Updated wrapper paths and filenames in `sdlc_agents_orchestrator_guide.md`
  - Added wrapper selection guidance section in `README.md` explaining when to use each wrapper
  - **BREAKING CHANGE**: All CLI examples now use full paths to wrapper scripts (e.g., `src/agent_orchestrator/wrappers/codex_wrapper.py`)
  - Added "Wrapper Path Resolution" section documenting how the CLI resolves wrapper paths

### Migration Guide
If you have existing scripts or commands using the old wrapper references:
- Change `--wrapper codex_exec_wrapper.py` → `--wrapper src/agent_orchestrator/wrappers/codex_wrapper.py`
- Change `--wrapper claude_wrapper.py` → `--wrapper src/agent_orchestrator/wrappers/claude_wrapper.py`
- The CLI requires full or relative paths to wrapper scripts; it does not search in default directories
