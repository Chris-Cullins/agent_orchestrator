"""Tests for the guidance system."""

import tempfile
from pathlib import Path

import pytest

from agent_orchestrator.guidance import GuidanceManager, GuidanceDoc, GuidanceContext


class TestGuidanceManager:
    """Tests for GuidanceManager class."""

    def test_exists_returns_false_when_no_guidance_dir(self, tmp_path):
        """Test that exists() returns False when guidance directory doesn't exist."""
        manager = GuidanceManager(repo_dir=tmp_path)
        assert not manager.exists()

    def test_exists_returns_false_when_dir_empty(self, tmp_path):
        """Test that exists() returns False when guidance directory has no .md files."""
        guidance_dir = tmp_path / ".agents" / "guidance"
        guidance_dir.mkdir(parents=True)
        manager = GuidanceManager(repo_dir=tmp_path)
        assert not manager.exists()

    def test_exists_returns_true_when_has_docs(self, tmp_path):
        """Test that exists() returns True when guidance directory has .md files."""
        guidance_dir = tmp_path / ".agents" / "guidance"
        guidance_dir.mkdir(parents=True)
        (guidance_dir / "TEST.md").write_text("# Test")

        manager = GuidanceManager(repo_dir=tmp_path)
        assert manager.exists()

    def test_find_guidance_files_empty_when_no_dir(self, tmp_path):
        """Test that find_guidance_files returns empty list when no guidance dir."""
        manager = GuidanceManager(repo_dir=tmp_path)
        assert manager.find_guidance_files() == []

    def test_find_guidance_files_returns_sorted(self, tmp_path):
        """Test that find_guidance_files returns files sorted alphabetically."""
        guidance_dir = tmp_path / ".agents" / "guidance"
        guidance_dir.mkdir(parents=True)
        (guidance_dir / "ZEBRA.md").write_text("# Zebra")
        (guidance_dir / "API.md").write_text("# API")
        (guidance_dir / "DATABASE.md").write_text("# Database")

        manager = GuidanceManager(repo_dir=tmp_path)
        files = manager.find_guidance_files()

        assert len(files) == 3
        assert files[0].name == "API.md"
        assert files[1].name == "DATABASE.md"
        assert files[2].name == "ZEBRA.md"


class TestFrontmatterParsing:
    """Tests for YAML frontmatter parsing."""

    def test_parse_frontmatter_no_frontmatter(self, tmp_path):
        """Test parsing content without frontmatter."""
        manager = GuidanceManager(repo_dir=tmp_path)
        content = "# Just a heading\n\nSome content."

        fm, remaining = manager.parse_frontmatter(content)

        assert fm == {}
        assert remaining == content

    def test_parse_frontmatter_with_valid_frontmatter(self, tmp_path):
        """Test parsing content with valid YAML frontmatter."""
        manager = GuidanceManager(repo_dir=tmp_path)
        content = """---
title: Test Document
description: A test description
consult_when:
  - doing thing A
  - doing thing B
---
# Heading

Content here.
"""
        fm, remaining = manager.parse_frontmatter(content)

        assert fm["title"] == "Test Document"
        assert fm["description"] == "A test description"
        assert fm["consult_when"] == ["doing thing A", "doing thing B"]
        assert remaining.strip().startswith("# Heading")

    def test_parse_frontmatter_missing_closing(self, tmp_path):
        """Test parsing content with missing closing delimiter."""
        manager = GuidanceManager(repo_dir=tmp_path)
        content = """---
title: Broken
# This has no closing ---
"""
        fm, remaining = manager.parse_frontmatter(content)

        assert fm == {}
        assert remaining == content

    def test_parse_frontmatter_invalid_yaml(self, tmp_path):
        """Test parsing content with invalid YAML."""
        manager = GuidanceManager(repo_dir=tmp_path)
        content = """---
title: [invalid: yaml: here
---
# Content
"""
        fm, remaining = manager.parse_frontmatter(content)

        # Should return empty dict and original content on parse error
        assert fm == {}
        assert remaining == content


class TestReadGuidanceDoc:
    """Tests for reading individual guidance documents."""

    def test_read_guidance_doc_with_frontmatter(self, tmp_path):
        """Test reading a guidance doc with frontmatter."""
        guidance_dir = tmp_path / ".agents" / "guidance"
        guidance_dir.mkdir(parents=True)

        doc_content = """---
title: Database Design
description: How to design database schemas
consult_when:
  - creating tables
  - writing migrations
---
# Database Design

Always use snake_case.
"""
        doc_path = guidance_dir / "DATABASE.md"
        doc_path.write_text(doc_content)

        manager = GuidanceManager(repo_dir=tmp_path)
        doc = manager.read_guidance_doc(doc_path)

        assert doc is not None
        assert doc.name == "DATABASE"
        assert doc.title == "Database Design"
        assert doc.description == "How to design database schemas"
        assert doc.consult_when == ["creating tables", "writing migrations"]

    def test_read_guidance_doc_without_frontmatter(self, tmp_path):
        """Test reading a guidance doc without frontmatter uses defaults."""
        guidance_dir = tmp_path / ".agents" / "guidance"
        guidance_dir.mkdir(parents=True)

        doc_content = """# API Design

Use RESTful patterns.
"""
        doc_path = guidance_dir / "API_DESIGN.md"
        doc_path.write_text(doc_content)

        manager = GuidanceManager(repo_dir=tmp_path)
        doc = manager.read_guidance_doc(doc_path)

        assert doc is not None
        assert doc.name == "API_DESIGN"
        assert doc.title == "Api Design"  # Title case from filename
        assert doc.consult_when == []
        assert "Api Design" in doc.description.lower() or "api design" in doc.description.lower()

    def test_read_guidance_doc_missing_file(self, tmp_path):
        """Test reading a non-existent file returns None."""
        manager = GuidanceManager(repo_dir=tmp_path)
        doc = manager.read_guidance_doc(tmp_path / "NONEXISTENT.md")

        assert doc is None

    def test_read_guidance_doc_consult_when_as_string(self, tmp_path):
        """Test that consult_when as string is converted to list."""
        guidance_dir = tmp_path / ".agents" / "guidance"
        guidance_dir.mkdir(parents=True)

        doc_content = """---
consult_when: just a string
---
# Content
"""
        doc_path = guidance_dir / "TEST.md"
        doc_path.write_text(doc_content)

        manager = GuidanceManager(repo_dir=tmp_path)
        doc = manager.read_guidance_doc(doc_path)

        assert doc.consult_when == ["just a string"]


class TestGuidanceContext:
    """Tests for GuidanceContext and prompt generation."""

    def test_empty_context_produces_empty_string(self):
        """Test that empty context produces no prompt section."""
        context = GuidanceContext(docs=[], guidance_dir=None)
        assert context.to_prompt_section() == ""

    def test_context_produces_table(self, tmp_path):
        """Test that context with docs produces a markdown table."""
        docs = [
            GuidanceDoc(
                path=tmp_path / "DATABASE.md",
                name="DATABASE",
                title="Database Design",
                consult_when=["creating tables", "writing migrations"],
                description="Schema design guide",
            ),
            GuidanceDoc(
                path=tmp_path / "API.md",
                name="API",
                title="API Design",
                consult_when=["adding endpoints"],
                description="API patterns",
            ),
        ]
        context = GuidanceContext(docs=docs, guidance_dir=Path(".agents/guidance"))

        section = context.to_prompt_section()

        assert "## Architectural Guidance" in section
        assert "| Document | Consult When |" in section
        assert "DATABASE.md" in section
        assert "API.md" in section
        assert "creating tables" in section
        assert "writing migrations" in section
        assert ".agents/guidance" in section

    def test_context_truncates_long_consult_when(self, tmp_path):
        """Test that very long consult_when entries are truncated."""
        long_text = "x" * 100
        docs = [
            GuidanceDoc(
                path=tmp_path / "TEST.md",
                name="TEST",
                title="Test",
                consult_when=[long_text],
                description="Test doc",
            ),
        ]
        context = GuidanceContext(docs=docs, guidance_dir=Path(".agents/guidance"))

        section = context.to_prompt_section()

        # Should be truncated with ...
        assert "..." in section
        assert long_text not in section  # Full text should not appear


class TestReadAllGuidance:
    """Integration tests for reading all guidance."""

    def test_read_all_guidance_empty_repo(self, tmp_path):
        """Test reading guidance from repo with no guidance dir."""
        manager = GuidanceManager(repo_dir=tmp_path)
        context = manager.read_all_guidance()

        assert context.docs == []
        assert context.to_prompt_section() == ""

    def test_read_all_guidance_multiple_docs(self, tmp_path):
        """Test reading multiple guidance documents."""
        guidance_dir = tmp_path / ".agents" / "guidance"
        guidance_dir.mkdir(parents=True)

        (guidance_dir / "DATABASE.md").write_text("""---
title: Database Design
consult_when:
  - creating tables
---
# Database
""")
        (guidance_dir / "API.md").write_text("""---
title: API Design
consult_when:
  - adding endpoints
---
# API
""")

        manager = GuidanceManager(repo_dir=tmp_path)
        context = manager.read_all_guidance()

        assert len(context.docs) == 2
        names = [d.name for d in context.docs]
        assert "DATABASE" in names
        assert "API" in names


class TestGetStats:
    """Tests for guidance statistics."""

    def test_get_stats_empty_repo(self, tmp_path):
        """Test stats for repo with no guidance."""
        manager = GuidanceManager(repo_dir=tmp_path)
        stats = manager.get_stats()

        assert stats["doc_count"] == 0
        assert stats["docs_with_frontmatter"] == 0
        assert stats["total_consult_rules"] == 0
        assert stats["files"] == []

    def test_get_stats_with_docs(self, tmp_path):
        """Test stats for repo with guidance docs."""
        guidance_dir = tmp_path / ".agents" / "guidance"
        guidance_dir.mkdir(parents=True)

        (guidance_dir / "DATABASE.md").write_text("""---
consult_when:
  - rule1
  - rule2
  - rule3
---
# DB
""")
        (guidance_dir / "API.md").write_text("""---
consult_when:
  - rule4
---
# API
""")
        (guidance_dir / "PLAIN.md").write_text("# No frontmatter")

        manager = GuidanceManager(repo_dir=tmp_path)
        stats = manager.get_stats()

        assert stats["doc_count"] == 3
        assert stats["docs_with_frontmatter"] == 2
        assert stats["total_consult_rules"] == 4
        assert len(stats["files"]) == 3
