# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Docstring Parser Module

Parses Google-style docstrings to extract parameter, return, and exception
documentation. Extracted from DocGenerator as part of Issue #394.

Part of god class refactoring initiative.
"""

import re
from typing import Dict, List, Optional, Pattern

from backend.code_intelligence.doc_generation.models import FunctionDoc
from backend.code_intelligence.doc_generation.types import (
    ExampleDoc,
    ExceptionDoc,
    ReturnDoc,
)


class DocstringParser:
    """
    Parser for Google-style docstrings.

    Extracts parameter descriptions, return documentation, exceptions,
    and examples from docstrings.

    Example:
        >>> parser = DocstringParser()
        >>> parser.enhance_function_doc(func_doc)
    """

    # Google-style docstring patterns
    SECTION_PATTERNS: Dict[str, Pattern[str]] = {
        "args": re.compile(r"^\s*(Args?|Arguments?|Parameters?):\s*$", re.IGNORECASE),
        "returns": re.compile(r"^\s*(Returns?|Yields?):\s*$", re.IGNORECASE),
        "raises": re.compile(r"^\s*(Raises?|Exceptions?|Throws?):\s*$", re.IGNORECASE),
        "examples": re.compile(r"^\s*(Examples?|Usage):\s*$", re.IGNORECASE),
        "notes": re.compile(r"^\s*(Notes?|See Also|Warning|Todo):\s*$", re.IGNORECASE),
        "attributes": re.compile(r"^\s*(Attributes?|Properties):\s*$", re.IGNORECASE),
    }

    # Type annotation extraction patterns
    TYPE_PATTERNS: Dict[str, Pattern[str]] = {
        "param": re.compile(r"(\w+)\s*\(([^)]+)\):\s*(.*)"),
        "simple": re.compile(r"(\w+):\s*(.*)"),
        "type_only": re.compile(r"([^:]+):\s*(.*)"),
    }

    def enhance_function_doc(self, func_doc: FunctionDoc) -> None:
        """
        Parse Google-style docstring to enhance parameter/return documentation.

        Args:
            func_doc: Function documentation to enhance
        """
        if not func_doc.docstring:
            return

        lines = func_doc.docstring.split("\n")
        current_section: Optional[str] = None
        current_content: List[str] = []

        for line in lines:
            # Check for section headers
            section_found = False
            for section_name, pattern in self.SECTION_PATTERNS.items():
                if pattern.match(line):
                    # Process previous section
                    self._process_section(func_doc, current_section, current_content)
                    current_section = section_name
                    current_content = []
                    section_found = True
                    break

            if not section_found and current_section:
                current_content.append(line)

        # Process final section
        self._process_section(func_doc, current_section, current_content)

    def _process_section(
        self, func_doc: FunctionDoc, section: Optional[str], content: List[str]
    ) -> None:
        """
        Process a docstring section and update function documentation.

        Args:
            func_doc: Function documentation to update
            section: Section name
            content: Lines in the section
        """
        if not section or not content:
            return

        if section == "args":
            self._parse_args_section(func_doc, content)
        elif section == "returns":
            self._parse_returns_section(func_doc, content)
        elif section == "raises":
            self._parse_raises_section(func_doc, content)
        elif section == "examples":
            self._parse_examples_section(func_doc, content)

    def _parse_args_section(self, func_doc: FunctionDoc, lines: List[str]) -> None:
        """
        Parse Args section of docstring.

        Args:
            func_doc: Function documentation to update
            lines: Lines in the Args section
        """
        current_param: Optional[str] = None
        current_desc: List[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check for new parameter with type annotation
            match = self.TYPE_PATTERNS["param"].match(stripped)
            if match:
                if current_param:
                    func_doc.update_parameter_description(
                        current_param, " ".join(current_desc)
                    )
                current_param = match.group(1)
                current_desc = [match.group(3)]
                continue

            # Check for simple parameter without type
            match = self.TYPE_PATTERNS["simple"].match(stripped)
            if match and not stripped.startswith(" "):
                if current_param:
                    func_doc.update_parameter_description(
                        current_param, " ".join(current_desc)
                    )
                current_param = match.group(1)
                current_desc = [match.group(2)]
                continue

            # Continuation of description
            if current_param:
                current_desc.append(stripped)

        # Save last parameter
        if current_param:
            func_doc.update_parameter_description(current_param, " ".join(current_desc))

    def _parse_returns_section(self, func_doc: FunctionDoc, lines: List[str]) -> None:
        """
        Parse Returns section of docstring.

        Args:
            func_doc: Function documentation to update
            lines: Lines in the Returns section
        """
        description = " ".join(line.strip() for line in lines if line.strip())
        if description:
            if func_doc.returns:
                func_doc.returns.description = description
            else:
                func_doc.returns = ReturnDoc(description=description)

    def _parse_raises_section(self, func_doc: FunctionDoc, lines: List[str]) -> None:
        """
        Parse Raises section of docstring.

        Args:
            func_doc: Function documentation to update
            lines: Lines in the Raises section
        """
        current_exc: Optional[str] = None
        current_desc: List[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            match = self.TYPE_PATTERNS["type_only"].match(stripped)
            if match:
                if current_exc:
                    func_doc.exceptions.append(
                        ExceptionDoc(
                            exception_type=current_exc,
                            description=" ".join(current_desc),
                        )
                    )
                current_exc = match.group(1).strip()
                current_desc = [match.group(2)]
            elif current_exc:
                current_desc.append(stripped)

        if current_exc:
            func_doc.exceptions.append(
                ExceptionDoc(
                    exception_type=current_exc,
                    description=" ".join(current_desc),
                )
            )

    def _parse_examples_section(self, func_doc: FunctionDoc, lines: List[str]) -> None:
        """
        Parse Examples section of docstring.

        Args:
            func_doc: Function documentation to update
            lines: Lines in the Examples section
        """
        code_lines: List[str] = []
        in_code_block = False

        for line in lines:
            stripped = line.strip()
            if self._is_code_start(stripped):
                in_code_block = True
                code_lines.append(self._extract_code_content(stripped))
            elif in_code_block:
                if stripped.startswith("    "):
                    code_lines.append(stripped)
                elif not stripped:
                    code_lines = self._finalize_code_block(func_doc, code_lines)
                    in_code_block = False

        self._finalize_code_block(func_doc, code_lines)

    def _is_code_start(self, stripped: str) -> bool:
        """Check if line starts a code example."""
        return stripped.startswith(">>>") or stripped.startswith("...")

    def _extract_code_content(self, stripped: str) -> str:
        """Extract code content from doctest line."""
        return stripped[4:] if len(stripped) > 4 else ""

    def _finalize_code_block(
        self, func_doc: FunctionDoc, code_lines: List[str]
    ) -> List[str]:
        """Add code block to examples and reset."""
        if code_lines:
            func_doc.examples.append(ExampleDoc(code="\n".join(code_lines)))
        return []


# Module-level instance for convenience
_parser = DocstringParser()


def enhance_function_doc(func_doc: FunctionDoc) -> None:
    """
    Convenience function to enhance function documentation from docstring.

    Args:
        func_doc: Function documentation to enhance
    """
    _parser.enhance_function_doc(func_doc)


__all__ = [
    "DocstringParser",
    "enhance_function_doc",
]
