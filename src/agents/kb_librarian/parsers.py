# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Instruction parsers for KB Librarian.

Extracted from enhanced_kb_librarian.py as part of Issue #381 god class refactoring.
"""

from typing import Any, Dict, List, Optional

from .types import TEXT_SECTIONS


class InstructionParser:
    """Helper class for parsing and extracting instructions from content."""

    @classmethod
    def extract_instructions(
        cls, results: List[Dict], tool_name: str
    ) -> Optional[Dict[str, Any]]:
        """Extract installation and usage instructions from KB results."""
        for result in results:
            content = result.get("content", "")
            if cls.content_contains_tool(content, tool_name):
                instructions = cls.initialize_instructions(tool_name)
                lines = content.split("\n")
                cls.parse_content_sections(lines, instructions)

                if cls.has_valid_instructions(instructions):
                    return instructions

        return None

    @classmethod
    def content_contains_tool(cls, content: str, tool_name: str) -> bool:
        """Check if content contains the specified tool name."""
        return tool_name.lower() in content.lower()

    @classmethod
    def initialize_instructions(cls, tool_name: str) -> Dict[str, Any]:
        """Initialize empty instructions structure."""
        return {
            "name": tool_name,
            "installation": "",
            "usage": "",
            "commands": [],
        }

    @classmethod
    def parse_content_sections(
        cls, lines: List[str], instructions: Dict[str, Any]
    ) -> None:
        """Parse content lines into instruction sections."""
        current_section = None

        for line in lines:
            line = line.strip()
            section = cls.identify_section(line)

            if section:
                current_section = section
            elif current_section and line:
                cls.add_content_to_section(current_section, line, instructions)

    @classmethod
    def identify_section(cls, line: str) -> Optional[str]:
        """Identify which section a line belongs to."""
        if line.startswith("Installation:"):
            return "installation"
        elif line.startswith("Basic Usage:") or line.startswith("Usage:"):
            return "usage"
        elif line.startswith("Common Commands:"):
            return "commands"
        return None

    @classmethod
    def _is_command_list_item(cls, line: str) -> bool:
        """Check if line is a command list item (Issue #315 - extracted helper)."""
        return line.startswith("-") or line.startswith("*")

    @classmethod
    def add_content_to_section(
        cls, section: str, line: str, instructions: Dict[str, Any]
    ) -> None:
        """Add content line to the appropriate instruction section."""
        # Handle text sections with simple append
        if section in TEXT_SECTIONS:
            instructions[section] += line + "\n"
            return

        # Handle commands section with list item detection
        if section == "commands" and cls._is_command_list_item(line):
            instructions["commands"].append(line[1:].strip())

    @classmethod
    def has_valid_instructions(cls, instructions: Dict[str, Any]) -> bool:
        """Check if instructions contain valid content."""
        return bool(instructions["installation"] or instructions["usage"])


__all__ = ["InstructionParser"]
