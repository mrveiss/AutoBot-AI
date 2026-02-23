# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Man Page Parser Module for Structured Content Extraction

This module provides comprehensive parsing of Linux man pages, extracting
structured content including NAME, SYNOPSIS, DESCRIPTION, OPTIONS, EXAMPLES,
and SEE ALSO sections.

Supports both direct file reading (.gz files) and subprocess-based parsing
using the system `man` command as a fallback.

GitHub Issue: #421
"""

import gzip
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Man page section descriptions for metadata
MAN_SECTION_DESCRIPTIONS = {
    "1": "User Commands",
    "2": "System Calls",
    "3": "Library Functions",
    "4": "Special Files",
    "5": "File Formats",
    "6": "Games",
    "7": "Miscellaneous",
    "8": "System Administration",
}


@dataclass
class ManPageContent:
    """Structured representation of a parsed man page."""

    command: str
    section: str
    file_path: Optional[str] = None

    # Core sections
    title: str = ""
    synopsis: str = ""
    description: str = ""
    options: str = ""
    examples: str = ""
    see_also: str = ""

    # Additional sections (less common but useful)
    author: str = ""
    bugs: str = ""
    environment: str = ""
    files: str = ""
    exit_status: str = ""
    return_value: str = ""
    notes: str = ""
    history: str = ""
    standards: str = ""

    # Raw content for fallback
    raw_content: str = ""

    # Metadata
    parse_method: str = "file"  # "file" or "subprocess"
    parse_success: bool = True
    error_message: str = ""

    # Computed fields
    section_description: str = field(init=False, default="")

    def __post_init__(self):
        """Set computed fields after initialization."""
        self.section_description = MAN_SECTION_DESCRIPTIONS.get(
            self.section, "Unknown Section"
        )

    def get_structured_content(self) -> str:
        """
        Get formatted structured content suitable for knowledge base storage.

        Returns:
            str: Formatted man page content with all sections
        """
        parts = [f"# {self.command}({self.section}) - {self.title}"]
        parts.append(f"\n**Section:** {self.section} ({self.section_description})")

        if self.synopsis:
            parts.append(f"\n## SYNOPSIS\n{self.synopsis}")

        if self.description:
            # Limit description to first 3000 chars to avoid huge documents
            desc = self.description[:3000]
            if len(self.description) > 3000:
                desc += "\n... (truncated)"
            parts.append(f"\n## DESCRIPTION\n{desc}")

        if self.options:
            # Limit options section
            opts = self.options[:2000]
            if len(self.options) > 2000:
                opts += "\n... (truncated)"
            parts.append(f"\n## OPTIONS\n{opts}")

        if self.examples:
            parts.append(f"\n## EXAMPLES\n{self.examples[:1500]}")

        if self.see_also:
            parts.append(f"\n## SEE ALSO\n{self.see_also}")

        if self.exit_status:
            parts.append(f"\n## EXIT STATUS\n{self.exit_status[:500]}")

        if self.environment:
            parts.append(f"\n## ENVIRONMENT\n{self.environment[:500]}")

        if self.files:
            parts.append(f"\n## FILES\n{self.files[:500]}")

        parts.append(f"\n---\n*Full manual: `man {self.section} {self.command}`*")

        return "\n".join(parts)

    def get_metadata_for_storage(self, system_context: Optional[dict] = None) -> dict:
        """
        Generate metadata dictionary for knowledge base storage.

        Args:
            system_context: Optional system context from system_context module

        Returns:
            dict: Metadata suitable for KnowledgeBase.store_fact()
        """
        metadata = {
            "type": "man_page",
            "command": self.command,
            "section": self.section,
            "section_description": self.section_description,
            "title": f"man {self.command}({self.section})",
            "category": "system_commands",
            "source": "man_page_parser",
            "parse_method": self.parse_method,
        }

        if self.file_path:
            metadata["file_path"] = self.file_path

        # Add system context if provided
        if system_context:
            metadata.update(
                {
                    "machine_id": system_context.get("machine_id", ""),
                    "machine_ip": system_context.get("machine_ip", ""),
                    "os_name": system_context.get("os_name", ""),
                    "os_version": system_context.get("os_version", ""),
                    "os_type": system_context.get("os_type", ""),
                    "architecture": system_context.get("architecture", ""),
                }
            )

        # Generate tags from command name and section
        tags = [
            self.command,
            f"section-{self.section}",
            self.section_description.lower().replace(" ", "-"),
        ]

        # Add related commands from SEE ALSO
        if self.see_also:
            related = re.findall(r"(\w+)\(\d\)", self.see_also)
            tags.extend(related[:5])  # Limit to 5 related commands

        metadata["tags"] = list(set(tags))

        return metadata


class ManPageParser:
    """
    Parser for Linux man pages with support for gzipped files and troff format.

    Provides two parsing methods:
    1. Direct file parsing (preferred) - reads .gz files directly
    2. Subprocess parsing (fallback) - uses system `man` command
    """

    # Section header patterns (troff/groff format)
    SECTION_PATTERNS = {
        "name": r"\.SH\s+NAME\s*\n(.*?)(?=\.SH|\Z)",
        "synopsis": r"\.SH\s+SYNOPSIS\s*\n(.*?)(?=\.SH|\Z)",
        "description": r"\.SH\s+DESCRIPTION\s*\n(.*?)(?=\.SH|\Z)",
        "options": r"\.SH\s+OPTIONS\s*\n(.*?)(?=\.SH|\Z)",
        "examples": r"\.SH\s+EXAMPLES?\s*\n(.*?)(?=\.SH|\Z)",
        "see_also": r"\.SH\s+SEE\s+ALSO\s*\n(.*?)(?=\.SH|\Z)",
        "author": r"\.SH\s+AUTHORS?\s*\n(.*?)(?=\.SH|\Z)",
        "bugs": r"\.SH\s+BUGS?\s*\n(.*?)(?=\.SH|\Z)",
        "environment": r"\.SH\s+ENVIRONMENT\s*\n(.*?)(?=\.SH|\Z)",
        "files": r"\.SH\s+FILES\s*\n(.*?)(?=\.SH|\Z)",
        "exit_status": r"\.SH\s+EXIT\s+STATUS\s*\n(.*?)(?=\.SH|\Z)",
        "return_value": r"\.SH\s+RETURN\s+VALUES?\s*\n(.*?)(?=\.SH|\Z)",
        "notes": r"\.SH\s+NOTES?\s*\n(.*?)(?=\.SH|\Z)",
        "history": r"\.SH\s+HISTORY\s*\n(.*?)(?=\.SH|\Z)",
        "standards": r"\.SH\s+STANDARDS?\s*\n(.*?)(?=\.SH|\Z)",
    }

    # Patterns for rendered man page output (from `man` command)
    RENDERED_SECTION_PATTERNS = {
        "name": r"^NAME\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "synopsis": r"^SYNOPSIS\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "description": r"^DESCRIPTION\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "options": r"^OPTIONS\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "examples": r"^EXAMPLES?\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "see_also": r"^SEE ALSO\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "author": r"^AUTHORS?\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "bugs": r"^BUGS?\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "environment": r"^ENVIRONMENT\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "files": r"^FILES\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "exit_status": r"^EXIT STATUS\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "return_value": r"^RETURN VALUES?\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "notes": r"^NOTES?\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "history": r"^HISTORY\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
        "standards": r"^STANDARDS?\s*\n(.*?)(?=^[A-Z]+\s*\n|\Z)",
    }

    def __init__(self):
        """Initialize the man page parser."""
        self._troff_cleanup_patterns = self._compile_troff_patterns()

    def _compile_troff_patterns(self) -> list:
        """Compile regex patterns for troff/groff cleanup."""
        return [
            (re.compile(r"\.\\\".*$", re.MULTILINE), ""),  # Comments
            (re.compile(r"\\fB(.*?)\\fR", re.DOTALL), r"\1"),  # Bold
            (re.compile(r"\\fI(.*?)\\fR", re.DOTALL), r"\1"),  # Italic
            (re.compile(r"\\fP", re.DOTALL), ""),  # Font reset
            (re.compile(r"\\-"), "-"),  # Escaped hyphen
            (re.compile(r"\\'"), "'"),  # Escaped apostrophe
            (re.compile(r"\\`"), "`"),  # Escaped backtick
            (re.compile(r"\\e"), r"\\"),  # Escaped backslash
            (re.compile(r"\\&"), ""),  # Zero-width space
            (re.compile(r"\\n\[.*?\]"), ""),  # Number registers
            (re.compile(r"\\s[+-]?\d+"), ""),  # Font size changes
            (re.compile(r"\.br\s*\n?"), "\n"),  # Line breaks
            (re.compile(r"\.PP\s*\n?"), "\n\n"),  # Paragraph
            (re.compile(r"\.TP\s*\n?"), "\n"),  # Tagged paragraph
            (re.compile(r"\.IP\s+.*?\n?"), "\n"),  # Indented paragraph
            (re.compile(r"\.RS\s*\n?"), ""),  # Right shift
            (re.compile(r"\.RE\s*\n?"), ""),  # Right shift end
            (re.compile(r"\.B\s+"), ""),  # Bold macro
            (re.compile(r"\.I\s+"), ""),  # Italic macro
            (re.compile(r"\.BI\s+"), ""),  # Bold-italic macro
            (re.compile(r"\.BR\s+"), ""),  # Bold-roman macro
            (re.compile(r"\.IR\s+"), ""),  # Italic-roman macro
            (re.compile(r"\.RB\s+"), ""),  # Roman-bold macro
            (re.compile(r"\.RI\s+"), ""),  # Roman-italic macro
            (re.compile(r"\.SM\s*"), ""),  # Small text
            (re.compile(r"\.sp\s*\n?"), "\n"),  # Vertical space
            (re.compile(r"\.nf\s*\n?"), ""),  # No-fill mode
            (re.compile(r"\.fi\s*\n?"), ""),  # Fill mode
            (re.compile(r"\.in\s+[+-]?\d+\w?\s*\n?"), ""),  # Indent
            (re.compile(r"\.TH\s+.*\n"), ""),  # Title header
            (re.compile(r"^\.\w+.*$", re.MULTILINE), ""),  # Other macros
        ]

    def _clean_troff(self, content: str) -> str:
        """
        Clean troff/groff formatting from content.

        Args:
            content: Raw troff content

        Returns:
            str: Cleaned plain text
        """
        for pattern, replacement in self._troff_cleanup_patterns:
            content = pattern.sub(replacement, content)

        # Clean up excessive whitespace
        content = re.sub(r"\n{3,}", "\n\n", content)
        content = re.sub(r"[ \t]+", " ", content)

        return content.strip()

    def read_man_page_file(self, file_path: Path) -> Optional[str]:
        """
        Read content from a man page file, handling gzip compression.

        Args:
            file_path: Path to the man page file (.gz or plain)

        Returns:
            Optional[str]: File content or None if read fails
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                logger.warning("Man page file not found: %s", file_path)
                return None

            if file_path.suffix == ".gz":
                with gzip.open(
                    file_path, "rt", encoding="utf-8", errors="replace"
                ) as f:
                    return f.read()
            else:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()

        except (OSError, gzip.BadGzipFile) as e:
            logger.error("Error reading man page %s: %s", file_path, e)
            return None

    def _extract_command_and_section(self, file_path: Path) -> tuple[str, str]:
        """
        Extract command name and section from file path.

        Args:
            file_path: Path to man page file

        Returns:
            tuple: (command_name, section_number)
        """
        file_path = Path(file_path)

        # Get section from parent directory (man1, man8, etc.)
        parent_dir = file_path.parent.name
        section_match = re.match(r"man(\d)", parent_dir)
        section = section_match.group(1) if section_match else "1"

        # Get command name from filename
        filename = file_path.name
        # Remove .gz extension if present
        if filename.endswith(".gz"):
            filename = filename[:-3]
        # Remove section extension (e.g., .1, .8)
        command = re.sub(r"\.\d+[a-z]*$", "", filename)

        return command, section

    def parse_man_page(self, file_path: Path) -> ManPageContent:
        """
        Parse a man page file into structured content.

        Args:
            file_path: Path to the man page file

        Returns:
            ManPageContent: Parsed man page content
        """
        file_path = Path(file_path)
        command, section = self._extract_command_and_section(file_path)

        result = ManPageContent(
            command=command,
            section=section,
            file_path=str(file_path),
            parse_method="file",
        )

        raw_content = self.read_man_page_file(file_path)

        if raw_content is None:
            result.parse_success = False
            result.error_message = "Failed to read file"
            return result

        result.raw_content = raw_content

        # Try to extract structured sections
        for section_name, pattern in self.SECTION_PATTERNS.items():
            match = re.search(pattern, raw_content, re.DOTALL | re.IGNORECASE)
            if match:
                cleaned = self._clean_troff(match.group(1))
                setattr(result, section_name, cleaned)

        # Extract title from NAME section
        if result.name:
            # NAME format is typically: command - description
            name_parts = result.name.split(" - ", 1)
            if len(name_parts) > 1:
                result.title = name_parts[1].strip()
            else:
                result.title = result.name.strip()
            # Clear the name field since we've extracted the title
            result.name = ""

        return result

    def _run_man_subprocess(
        self, command: str, section: str
    ) -> subprocess.CompletedProcess:
        """Helper for parse_man_page_with_subprocess. Ref: #1088."""
        cmd = ["man", section, command]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            env={"MANWIDTH": "80", "TERM": "dumb"},
        )

    def _extract_sections_from_rendered(
        self, result: ManPageContent, content: str
    ) -> None:
        """Helper for parse_man_page_with_subprocess. Ref: #1088."""
        for section_name, pattern in self.RENDERED_SECTION_PATTERNS.items():
            match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
            if match:
                cleaned = match.group(1).strip()
                # Remove backspace sequences from rendered output
                cleaned = re.sub(r".\x08", "", cleaned)
                setattr(result, section_name, cleaned)

        if result.name:
            name_parts = result.name.split(" - ", 1)
            if len(name_parts) > 1:
                result.title = name_parts[1].strip()
            else:
                result.title = result.name.strip()
            result.name = ""

    def parse_man_page_with_subprocess(
        self, command: str, section: Optional[str] = None
    ) -> ManPageContent:
        """
        Parse a man page using the system `man` command.

        This is a fallback method for when direct file parsing fails
        or when the file path is unknown.

        Args:
            command: Command name to look up
            section: Optional section number (1-8)

        Returns:
            ManPageContent: Parsed man page content
        """
        section = section or "1"

        result = ManPageContent(
            command=command,
            section=section,
            parse_method="subprocess",
        )

        try:
            proc = self._run_man_subprocess(command, section)

            if proc.returncode != 0:
                result.parse_success = False
                result.error_message = f"man command failed: {proc.stderr}"
                return result

            result.raw_content = proc.stdout
            self._extract_sections_from_rendered(result, proc.stdout)

        except subprocess.TimeoutExpired:
            result.parse_success = False
            result.error_message = "man command timed out"
        except Exception as e:
            result.parse_success = False
            result.error_message = str(e)

        return result

    def get_man_page_summary(self, command: str, section: Optional[str] = None) -> str:
        """
        Get a brief summary of a man page using `man -k`.

        Args:
            command: Command name
            section: Optional section number

        Returns:
            str: Brief description or empty string
        """
        try:
            cmd = ["man", "-k", f"^{command}$"]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if proc.returncode == 0:
                for line in proc.stdout.split("\n"):
                    if command in line and " - " in line:
                        return line.split(" - ", 1)[1].strip()

        except Exception as e:
            logger.debug("Failed to get summary for %s: %s", command, e)

        return ""


# Convenience functions for direct usage
def parse_man_page(file_path: Path) -> ManPageContent:
    """
    Parse a man page file into structured content.

    Args:
        file_path: Path to the man page file

    Returns:
        ManPageContent: Parsed content
    """
    parser = ManPageParser()
    return parser.parse_man_page(file_path)


def get_man_page_content(command: str, section: Optional[str] = None) -> ManPageContent:
    """
    Get parsed man page content for a command using subprocess.

    Args:
        command: Command name
        section: Optional section number

    Returns:
        ManPageContent: Parsed content
    """
    parser = ManPageParser()
    return parser.parse_man_page_with_subprocess(command, section)
