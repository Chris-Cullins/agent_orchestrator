# API Documentation Guide

This document provides guidance for generating API documentation from the agent orchestrator's docstrings.

## Docstring Format

The codebase uses **Google-style docstrings** throughout all public modules, classes, and functions. This format includes:

- Module-level docstrings explaining purpose and key concepts
- Class docstrings with descriptions and attribute documentation
- Method/function docstrings with Args, Returns, and Raises sections

## Documentation Generation Options

### Option 1: MkDocs with mkdocstrings (Recommended)

**Pros:**
- Simpler configuration and Markdown-native
- Modern, clean output with material theme
- Excellent live-reload development experience
- Easy GitHub Pages deployment

**Cons:**
- Less mature than Sphinx for complex API docs

**Quick Start:**
```bash
pip install mkdocs mkdocs-material mkdocstrings[python]

# Create mkdocs.yml:
# site_name: Agent Orchestrator API
# theme:
#   name: material
# plugins:
#   - mkdocstrings

mkdocs serve  # Development preview
mkdocs build  # Build static site
```

### Option 2: Sphinx with autodoc

**Pros:**
- Industry standard for Python documentation
- Very mature with extensive customization options
- Built-in support for cross-references

**Cons:**
- ReStructuredText-based (though MyST-parser adds Markdown support)
- More complex configuration
- Steeper learning curve

**Quick Start:**
```bash
pip install sphinx sphinx-rtd-theme

sphinx-quickstart docs/
# Add 'sphinx.ext.autodoc' and 'sphinx.ext.napoleon' to extensions
sphinx-build -b html docs/ docs/_build/html
```

## Recommendation

For this project, **MkDocs with mkdocstrings** is recommended because:

1. The existing documentation is in Markdown format
2. The codebase is moderately sized (not requiring Sphinx's advanced features)
3. Simpler setup reduces maintenance burden
4. Material theme provides excellent developer experience

## Verification with pydoc

The docstrings can be verified using Python's built-in pydoc:

```bash
# View module documentation
PYTHONPATH=src python -m pydoc agent_orchestrator

# View specific class
PYTHONPATH=src python -m pydoc agent_orchestrator.orchestrator.Orchestrator

# Generate HTML documentation
PYTHONPATH=src python -m pydoc -w agent_orchestrator
```

## Coverage Summary

All public modules now have comprehensive docstrings:

- `orchestrator.py` - Core workflow execution engine
- `models.py` - Data structures (Step, Workflow, RunState, etc.)
- `runner.py` - Agent subprocess management
- `workflow.py` - Workflow loading and validation
- `state.py` - State persistence
- `reporting.py` - Run report parsing
- `gating.py` - Conditional step execution
- `git_worktree.py` - Git worktree isolation
- `cli.py` - Command-line interface
- `notifications/` - Notification services
- `wrappers/claude_wrapper.py` - Claude CLI adapter
