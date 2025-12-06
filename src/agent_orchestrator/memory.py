"""
Memory system for persistent agent knowledge via AGENTS.md files.

Provides directory-scoped memory that agents can read and update.
Memory is stored in AGENTS.md files throughout the repository tree,
with each file covering its directory and descendants.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class MemoryUpdate:
    """A single memory update from an agent."""

    scope: str  # relative path to target directory (e.g., "src/api")
    section: str  # section name (e.g., "Gotchas", "Patterns")
    entry: str  # the content to add

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryUpdate":
        return cls(
            scope=str(data.get("scope", ".")),
            section=str(data.get("section", "Notes")),
            entry=str(data.get("entry", "")),
        )


@dataclass
class MemoryContext:
    """Collected memory context for an agent."""

    memories: list[tuple[Path, str]]  # (file_path, content) pairs
    total_lines: int

    def to_prompt_section(self) -> str:
        """Format memories for injection into agent prompt."""
        if not self.memories:
            return ""

        sections = []
        for file_path, content in self.memories:
            rel_path = file_path.parent.name or "root"
            sections.append(f"### Memory: {rel_path}/AGENTS.md\n{content}")

        return (
            "## Repository Memory\n"
            "The following AGENTS.md files contain learned knowledge about this codebase.\n"
            "Use this context to inform your work. If you learn something valuable,\n"
            "include it in your run report's `memory_updates` field.\n\n"
            + "\n\n".join(sections)
        )


class MemoryManager:
    """
    Manages reading and writing of AGENTS.md memory files.

    Memory files are markdown documents with sections containing
    concise, actionable knowledge about the codebase.
    """

    FILENAME = "AGENTS.md"
    MAX_LINES_PER_FILE = 30  # aggressive limit - less is more
    DEFAULT_TEMPLATE = """# AGENTS.md

## Gotchas
"""

    # Patterns that indicate low-value entries (reject these)
    LOW_VALUE_PATTERNS = [
        # Line number references (fragile)
        r"line \d+",
        r":\d+\b",  # file.py:123
        # Describing what code does (obvious from reading)
        r"^this (?:file|module|class|function) (?:is|does|handles|manages|contains)",
        r"^handles? ",
        r"^manages? ",
        r"^contains? ",
        r"^defines? ",
        r"^implements? ",
        r"^provides? ",
        # File/directory descriptions
        r"^main (?:entry|file|module)",
        r"directory (?:for|contains|holds)",
        # Architecture fluff
        r"^the \w+ (?:is|are) responsible for",
        r"^used (?:for|to) ",
        # Standard patterns anyone knows
        r"uses? (?:dataclass|enum|typing|logging|json)",
        r"follows? (?:the )?\w+ pattern",
        # Vague statements
        r"^important",
        r"^note:",
        r"^key ",
        r"^core ",
        r"^central ",
    ]

    def __init__(
        self,
        repo_dir: Path,
        logger: logging.Logger | None = None,
        strict_quality: bool = True,
    ) -> None:
        self._repo_dir = repo_dir.resolve()
        self._log = logger or logging.getLogger(__name__)
        self._strict_quality = strict_quality
        # Compile patterns for efficiency
        self._low_value_regex = [
            re.compile(p, re.IGNORECASE) for p in self.LOW_VALUE_PATTERNS
        ]

    def find_memory_files(self, from_path: Path) -> list[Path]:
        """
        Find all AGENTS.md files in the ancestry chain from a path up to repo root.

        Returns files ordered from most specific (deepest) to most general (repo root).
        """
        files = []
        current = from_path.resolve()

        # Ensure we're within repo
        try:
            current.relative_to(self._repo_dir)
        except ValueError:
            self._log.warning(
                "Path %s is outside repo %s", from_path, self._repo_dir
            )
            return files

        # If current is a file, start from its parent
        if current.is_file():
            current = current.parent

        # Walk up to repo root
        while True:
            agents_md = current / self.FILENAME
            if agents_md.exists() and agents_md.is_file():
                files.append(agents_md)

            if current == self._repo_dir:
                break

            parent = current.parent
            if parent == current:  # filesystem root
                break
            current = parent

        return files

    def read_memories(self, from_path: Path) -> MemoryContext:
        """
        Read all relevant AGENTS.md files for a given path.

        Returns a MemoryContext with the collected content.
        """
        files = self.find_memory_files(from_path)
        memories = []
        total_lines = 0

        # Reverse to get root-first order (general -> specific)
        for file_path in reversed(files):
            try:
                content = file_path.read_text(encoding="utf-8")
                # Strip HTML comments (template placeholders)
                content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
                content = content.strip()
                if content:
                    memories.append((file_path, content))
                    total_lines += content.count("\n") + 1
            except OSError as exc:
                self._log.warning("Failed to read %s: %s", file_path, exc)

        return MemoryContext(memories=memories, total_lines=total_lines)

    def is_low_value_entry(self, entry: str) -> tuple[bool, str]:
        """
        Check if an entry matches low-value patterns.

        Returns (is_low_value, reason).
        """
        normalized = entry.strip().lower()

        # Remove bullet prefix for checking
        if normalized.startswith("- "):
            normalized = normalized[2:]

        # Check against patterns
        for pattern in self._low_value_regex:
            if pattern.search(normalized):
                return True, f"matches low-value pattern: {pattern.pattern}"

        # Too short to be useful
        if len(normalized) < 15:
            return True, "too short to be actionable"

        # Too long suggests documentation, not memory
        if len(normalized) > 150:
            return True, "too long - consider if this belongs in docs"

        return False, ""

    def apply_update(self, update: MemoryUpdate) -> bool:
        """
        Apply a memory update to the appropriate AGENTS.md file.

        Creates the file if it doesn't exist. Returns True on success.
        Rejects low-value entries if strict_quality is enabled.
        """
        # Quality gate - reject low-value entries
        if self._strict_quality:
            is_low_value, reason = self.is_low_value_entry(update.entry)
            if is_low_value:
                self._log.info(
                    "Rejected low-value memory update: %s (%s)",
                    update.entry[:50] + "..." if len(update.entry) > 50 else update.entry,
                    reason,
                )
                return False

        # Resolve target directory
        if update.scope in (".", "", None):
            target_dir = self._repo_dir
        else:
            target_dir = (self._repo_dir / update.scope).resolve()

        # Security check
        try:
            target_dir.relative_to(self._repo_dir)
        except ValueError:
            self._log.error(
                "Memory update scope %s escapes repo root", update.scope
            )
            return False

        # Ensure directory exists
        if not target_dir.exists():
            self._log.warning(
                "Memory update target directory does not exist: %s", target_dir
            )
            return False

        agents_md = target_dir / self.FILENAME
        return self._add_entry_to_file(agents_md, update.section, update.entry)

    def _add_entry_to_file(
        self, file_path: Path, section: str, entry: str
    ) -> bool:
        """Add an entry to a specific section in an AGENTS.md file."""
        # Create file with template if it doesn't exist
        if not file_path.exists():
            self._log.info("Creating new memory file: %s", file_path)
            file_path.write_text(self.DEFAULT_TEMPLATE, encoding="utf-8")

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._log.error("Failed to read %s: %s", file_path, exc)
            return False

        # Normalize entry (single line, no leading bullet)
        entry = entry.strip()
        if not entry:
            return False

        # Add bullet if not present
        if not entry.startswith("- "):
            entry = f"- {entry}"

        # Find or create section
        section_pattern = rf"^##\s+{re.escape(section)}\s*$"
        section_match = re.search(section_pattern, content, re.MULTILINE)

        if section_match:
            # Find the end of this section (next ## or end of file)
            section_start = section_match.end()
            next_section = re.search(r"^##\s+", content[section_start:], re.MULTILINE)

            if next_section:
                insert_pos = section_start + next_section.start()
                # Insert before the next section, with blank line
                new_content = (
                    content[:insert_pos].rstrip()
                    + "\n"
                    + entry
                    + "\n\n"
                    + content[insert_pos:]
                )
            else:
                # Append to end of file
                new_content = content.rstrip() + "\n" + entry + "\n"
        else:
            # Create new section at end
            new_content = (
                content.rstrip() + f"\n\n## {section}\n{entry}\n"
            )

        # Check for duplicate entries
        if entry in content:
            self._log.debug("Entry already exists in %s, skipping", file_path)
            return True

        try:
            file_path.write_text(new_content, encoding="utf-8")
            self._log.info(
                "Added memory entry to %s [%s]: %s",
                file_path,
                section,
                entry[:50] + "..." if len(entry) > 50 else entry,
            )
            return True
        except OSError as exc:
            self._log.error("Failed to write %s: %s", file_path, exc)
            return False

    def apply_updates(self, updates: list[MemoryUpdate]) -> int:
        """
        Apply multiple memory updates. Returns count of successful updates.
        """
        success_count = 0
        for update in updates:
            if self.apply_update(update):
                success_count += 1
        return success_count

    def get_stats(self) -> dict[str, object]:
        """Get statistics about memory files in the repo."""
        files = list(self._repo_dir.rglob(self.FILENAME))
        total_lines = 0
        total_entries = 0

        for f in files:
            try:
                content = f.read_text(encoding="utf-8")
                total_lines += content.count("\n") + 1
                # Count bullet points as entries
                total_entries += len(re.findall(r"^- ", content, re.MULTILINE))
            except OSError:
                pass

        return {
            "file_count": len(files),
            "total_lines": total_lines,
            "total_entries": total_entries,
            "files": [str(f.relative_to(self._repo_dir)) for f in files],
        }


def parse_memory_updates(raw: list[dict] | None) -> list[MemoryUpdate]:
    """Parse memory updates from run report data."""
    if not raw:
        return []
    updates = []
    for item in raw:
        if isinstance(item, dict):
            try:
                updates.append(MemoryUpdate.from_dict(item))
            except (KeyError, TypeError):
                pass
    return updates
