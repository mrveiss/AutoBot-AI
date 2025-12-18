# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Text Extraction utilities for KB Librarian.

Extracted from enhanced_kb_librarian.py as part of Issue #381 god class refactoring.
"""

from typing import Dict, List, Optional

from .types import (
    ADVANCED_FEATURE_KEYWORDS,
    COMMAND_OPERATORS,
    COMMON_CLI_TOOLS,
    ERROR_CODE_PATTERNS,
    FEATURE_INDICATORS,
    INSTALLATION_COMMANDS,
    OUTPUT_FORMAT_KEYWORDS,
    PROBLEM_KEYWORDS,
    REQUIREMENT_KEYWORDS,
    SECURITY_KEYWORDS,
    SOLUTION_KEYWORDS,
    SYNTAX_PATTERNS,
    TOOL_NAME_CHARS,
)


class TextExtractor:
    """Helper class for extracting information from text content."""

    @classmethod
    def extract_requirements(cls, text: str) -> str:
        """Extract system requirements from installation text."""
        lines = text.split("\n")
        requirements = []

        for line in lines:
            line_lower = line.lower()
            if any(word in line_lower for word in REQUIREMENT_KEYWORDS):
                requirements.append(line.strip())

        return "\n".join(requirements) if requirements else "Standard Linux system"

    @classmethod
    def extract_command_syntax(cls, text: str) -> str:
        """Extract command syntax patterns."""
        lines = text.split("\n")
        syntax_lines = []

        for line in lines:
            if any(pattern in line for pattern in SYNTAX_PATTERNS):
                syntax_lines.append(line.strip())

        return "\n".join(syntax_lines) if syntax_lines else "See man page for syntax"

    @classmethod
    def is_command_line(cls, line: str) -> bool:
        """Check if line is a command (Issue #334 - extracted helper)."""
        return line.startswith("$") or line.startswith("#")

    @classmethod
    def update_example_metadata(cls, example: Dict[str, str], line: str) -> None:
        """Update example with description or output (Issue #334 - extracted helper)."""
        if not example["description"]:
            example["description"] = line
        elif line.startswith("Output:") or "output" in line.lower():
            example["expected_output"] = line

    @classmethod
    def extract_detailed_examples(cls, text: str) -> List[Dict[str, str]]:
        """Extract detailed command examples with descriptions."""
        examples = []
        lines = text.split("\n")

        current_example = None
        for line in lines:
            line = line.strip()
            if cls.is_command_line(line):
                if current_example:
                    examples.append(current_example)
                current_example = {
                    "command": line[1:].strip(),
                    "description": "",
                    "expected_output": "",
                }
            elif current_example and line and not cls.is_command_line(line):
                cls.update_example_metadata(current_example, line)

        if current_example:
            examples.append(current_example)

        return examples

    @classmethod
    def extract_output_formats(cls, text: str) -> str:
        """Extract information about output formats."""
        formats = []
        lines = text.split("\n")

        for line in lines:
            line_lower = line.lower()
            if any(word in line_lower for word in OUTPUT_FORMAT_KEYWORDS):
                formats.append(line.strip())

        return "\n".join(formats[:3]) if formats else "Standard text output"

    @classmethod
    def extract_advanced_features(cls, text: str) -> str:
        """Extract advanced features and capabilities."""
        features = []
        lines = text.split("\n")

        for line in lines:
            line_lower = line.lower()
            if any(word in line_lower for word in ADVANCED_FEATURE_KEYWORDS):
                features.append(line.strip())

        return (
            "\n".join(features[:5])
            if features
            else "See documentation for advanced features"
        )

    @classmethod
    def extract_error_codes(cls, text: str) -> str:
        """Extract error codes and their meanings."""
        error_info = []
        lines = text.split("\n")

        for line in lines:
            if any(pattern in line.lower() for pattern in ERROR_CODE_PATTERNS):
                error_info.append(line.strip())

        return "\n".join(error_info[:5]) if error_info else "Standard Unix exit codes"

    @classmethod
    def _is_problem_line(cls, line: str) -> bool:
        """Check if line contains problem keywords (Issue #315 - extracted helper)."""
        line_lower = line.lower()
        return any(word in line_lower for word in PROBLEM_KEYWORDS)

    @classmethod
    def _is_solution_line(cls, line: str) -> bool:
        """Check if line contains solution keywords (Issue #315 - extracted helper)."""
        line_lower = line.lower()
        return any(word in line_lower for word in SOLUTION_KEYWORDS)

    @classmethod
    def extract_common_issues(cls, text: str) -> List[Dict[str, str]]:
        """Extract common issues and solutions."""
        issues = []
        current_issue = None

        for line in text.split("\n"):
            line = line.strip()
            if cls._is_problem_line(line):
                if current_issue:
                    issues.append(current_issue)
                current_issue = {"problem": line, "solution": ""}
            elif current_issue and cls._is_solution_line(line):
                current_issue["solution"] = line

        if current_issue:
            issues.append(current_issue)

        return issues

    @classmethod
    def _is_potential_tool_name(cls, word: str) -> bool:
        """Check if word looks like a tool name (Issue #315 - extracted helper)."""
        if word in COMMON_CLI_TOOLS:
            return True
        if len(word) <= 2 or not word.islower() or word.isdigit():
            return False
        return any(char in word for char in TOOL_NAME_CHARS)

    @classmethod
    def extract_related_tools(cls, text: str) -> List[str]:
        """Extract names of related tools."""
        tools = []

        for line in text.split("\n"):
            for word in line.split():
                cleaned = word.strip(".,()[]{}")
                if cls._is_potential_tool_name(cleaned):
                    tools.append(cleaned)

        return list(set(tools))[:10]

    @classmethod
    def extract_security_practices(cls, text: str) -> List[str]:
        """Extract security best practices."""
        practices = []
        lines = text.split("\n")

        for line in lines:
            line_lower = line.lower()
            if any(word in line_lower for word in SECURITY_KEYWORDS):
                practices.append(line.strip())

        return practices[:5]

    @classmethod
    def extract_installation_commands(cls, text: str) -> str:
        """Extract installation commands from text."""
        lines = text.split("\n")
        install_commands = []

        for line in lines:
            line = line.strip()
            if any(cmd in line for cmd in INSTALLATION_COMMANDS):
                install_commands.append(line)

        if install_commands:
            return "\n".join(install_commands)
        else:
            for line in lines:
                if "install" in line.lower():
                    return line

        return "Installation method not found"

    @classmethod
    def _extract_prompt_command(cls, line: str) -> Optional[str]:
        """Extract command from $ or # prompt line (Issue #315 - extracted helper)."""
        if not (line.startswith("$") or line.startswith("#")):
            return None
        command = line[1:].strip()
        if command and len(command) < 200:
            return command
        return None

    @classmethod
    def _is_heuristic_command(cls, line: str) -> bool:
        """Check if line looks like a command by heuristics (Issue #315 - extracted helper)."""
        if not line or line[0].isupper() or " " not in line or len(line) >= 100:
            return False
        return any(cmd in line for cmd in COMMAND_OPERATORS)

    @classmethod
    def extract_command_examples(cls, text: str) -> List[str]:
        """Extract command examples from text."""
        commands = []

        for line in text.split("\n"):
            line = line.strip()
            prompt_cmd = cls._extract_prompt_command(line)
            if prompt_cmd:
                commands.append(prompt_cmd)
            elif cls._is_heuristic_command(line):
                commands.append(line)

        return commands[:10]

    @classmethod
    def extract_purpose(cls, text: str, tool_name: str) -> str:
        """Extract tool purpose from text."""
        sentences = text.split(".")
        for sentence in sentences:
            if tool_name.lower() in sentence.lower() and "is" in sentence:
                return sentence.strip()
        return "Tool for various system operations"

    @classmethod
    def extract_features(cls, text: str) -> str:
        """Extract tool features from text."""
        features = []
        lines = text.split("\n")

        for line in lines:
            if any(indicator in line.lower() for indicator in FEATURE_INDICATORS):
                features.append(line.strip())

        return (
            "\n".join(features[:5])
            if features
            else "Various features for system administration"
        )


__all__ = ["TextExtractor"]
