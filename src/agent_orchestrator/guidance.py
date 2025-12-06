"""
Guidance system for architectural constraints and design documents.

Provides a lightweight way to point agents to relevant guidance documents
without bloating every prompt with their full contents. Agents read the
docs on-demand when their task involves the relevant domain.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class GuidanceDoc:
    """A single guidance document with its metadata."""

    path: Path  # Absolute path to the document
    name: str  # Filename without extension (e.g., "DATABASE")
    title: str  # Human-readable title from frontmatter or derived from name
    consult_when: list[str]  # When agents should read this doc
    description: str  # Brief description of what the doc covers

    @property
    def relative_path(self) -> str:
        """Return the path relative to .agents/guidance/."""
        return self.path.name


@dataclass
class GuidanceContext:
    """Collected guidance context for injection into agent prompts."""

    docs: list[GuidanceDoc] = field(default_factory=list)
    guidance_dir: Optional[Path] = None

    def to_prompt_section(self) -> str:
        """
        Format guidance as a lightweight lookup table for agent prompts.

        Does NOT include doc contents - just tells agents where to look.
        """
        if not self.docs:
            return ""

        lines = [
            "## Architectural Guidance",
            "",
            "This repository has architectural guidance documents you MUST consult",
            "before making certain changes. Read the relevant document(s) BEFORE",
            "implementing changes in that domain.",
            "",
            f"**Location**: `{self.guidance_dir}`" if self.guidance_dir else "",
            "",
            "| Document | Consult When |",
            "|----------|--------------|",
        ]

        for doc in self.docs:
            # Combine consult_when into a readable string
            when_text = "; ".join(doc.consult_when) if doc.consult_when else doc.description
            # Truncate if too long for table
            if len(when_text) > 80:
                when_text = when_text[:77] + "..."
            lines.append(f"| {doc.name}.md | {when_text} |")

        lines.extend([
            "",
            "**IMPORTANT**: Before implementing changes in these areas, READ the",
            "relevant doc first and follow its constraints. Do not deviate without",
            "explicit user approval.",
        ])

        return "\n".join(lines)


class GuidanceManager:
    """
    Manages reading of architectural guidance documents.

    Guidance documents are markdown files with optional YAML frontmatter
    that specify when agents should consult them.

    Directory structure:
        .agents/
        └── guidance/
            ├── DATABASE.md
            ├── API.md
            └── REPO_LAYOUT.md

    Frontmatter format:
        ---
        title: Database Design
        description: Schema design and naming conventions
        consult_when:
          - creating or modifying database tables
          - writing migrations
          - changing schemas
        ---
        # Database Design
        ...
    """

    GUIDANCE_DIR = ".agents/guidance"

    def __init__(
        self,
        repo_dir: Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self._repo_dir = repo_dir.resolve()
        self._guidance_dir = self._repo_dir / self.GUIDANCE_DIR
        self._log = logger or logging.getLogger(__name__)

    @property
    def guidance_dir(self) -> Path:
        """Return the guidance directory path."""
        return self._guidance_dir

    def exists(self) -> bool:
        """Check if the guidance directory exists and has documents."""
        return self._guidance_dir.exists() and any(self._guidance_dir.glob("*.md"))

    def find_guidance_files(self) -> list[Path]:
        """Find all guidance markdown files in the guidance directory."""
        if not self._guidance_dir.exists():
            return []

        files = sorted(self._guidance_dir.glob("*.md"))
        return files

    def parse_frontmatter(self, content: str) -> tuple[dict, str]:
        """
        Parse YAML frontmatter from markdown content.

        Returns (frontmatter_dict, remaining_content).
        If no frontmatter, returns ({}, original_content).
        """
        # Check for frontmatter delimiter
        if not content.startswith("---"):
            return {}, content

        # Find closing delimiter
        end_match = re.search(r"\n---\s*\n", content[3:])
        if not end_match:
            return {}, content

        frontmatter_text = content[3 : 3 + end_match.start()]
        remaining = content[3 + end_match.end() :]

        try:
            frontmatter = yaml.safe_load(frontmatter_text) or {}
        except yaml.YAMLError as exc:
            self._log.warning("Failed to parse frontmatter: %s", exc)
            return {}, content

        return frontmatter, remaining

    def read_guidance_doc(self, file_path: Path) -> Optional[GuidanceDoc]:
        """Read and parse a single guidance document."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._log.warning("Failed to read %s: %s", file_path, exc)
            return None

        frontmatter, _ = self.parse_frontmatter(content)

        # Extract name from filename
        name = file_path.stem  # e.g., "DATABASE" from "DATABASE.md"

        # Get title from frontmatter or derive from name
        title = frontmatter.get("title", name.replace("_", " ").title())

        # Get consult_when rules
        consult_when = frontmatter.get("consult_when", [])
        if isinstance(consult_when, str):
            consult_when = [consult_when]

        # Get description
        description = frontmatter.get("description", f"Guidance for {title.lower()}")

        return GuidanceDoc(
            path=file_path,
            name=name,
            title=title,
            consult_when=consult_when,
            description=description,
        )

    def read_all_guidance(self) -> GuidanceContext:
        """
        Read all guidance documents and return a context for prompt injection.
        """
        files = self.find_guidance_files()
        docs = []

        for file_path in files:
            doc = self.read_guidance_doc(file_path)
            if doc:
                docs.append(doc)

        # Calculate relative path for display
        try:
            rel_guidance_dir = self._guidance_dir.relative_to(self._repo_dir)
        except ValueError:
            rel_guidance_dir = self._guidance_dir

        return GuidanceContext(docs=docs, guidance_dir=rel_guidance_dir)

    def get_stats(self) -> dict[str, object]:
        """Get statistics about guidance documents."""
        files = self.find_guidance_files()
        docs_with_frontmatter = 0
        total_consult_rules = 0

        for f in files:
            doc = self.read_guidance_doc(f)
            if doc:
                if doc.consult_when:
                    docs_with_frontmatter += 1
                    total_consult_rules += len(doc.consult_when)

        return {
            "doc_count": len(files),
            "docs_with_frontmatter": docs_with_frontmatter,
            "total_consult_rules": total_consult_rules,
            "files": [str(f.relative_to(self._repo_dir)) for f in files],
        }
