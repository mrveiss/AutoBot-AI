# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Language detection and regex-based code-element extraction.

Extracted verbatim from ``npu_code_search_agent.py`` (#16173). That module sat
at its grandfathered size ceiling, so nothing could be added to it until
something came out -- and this is the part with no dependency on
``NPUCodeSearchAgent`` at all: per-language regex patterns and the pure
functions that apply them to source text.

``npu_code_search_agent.py`` keeps thin method wrappers over the two entry
points existing tests and call sites pin by name (``_get_language_patterns``,
``_extract_element_code``); everything else is called directly from here.
"""

import re
from typing import Dict, List

#: Per-language regex patterns for functions, classes, imports and variables.
LANGUAGE_PATTERNS: Dict[str, Dict[str, str]] = {
    "python": {
        "function": r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
        "class": r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[\(:]",
        "import": r"(?:from\s+\S+\s+)?import\s+([^#\n]+)",
        "variable": r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=",
    },
    "javascript": {
        "function": (
            r"(?:function\s+([a-zA-Z_][a-zA-Z0-9_]*)|"
            r"([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*function|"
            r"\bconst\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:\(.*?\)\s*=>|\bfunction))"
        ),
        "class": r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        "import": (r'(?:import|require)\s*\(\s*[\'"]([^\'"]+)[\'"]|' r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]'),
        "variable": r"(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    },
}

#: File-extension to language name, used to select a `LANGUAGE_PATTERNS` entry.
_LANGUAGE_BY_EXTENSION: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".cs": "csharp",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".ps1": "powershell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".md": "markdown",
}


def detect_language(file_ext: str) -> str:
    """Detect programming language from file extension"""
    return _LANGUAGE_BY_EXTENSION.get(file_ext.lower(), "unknown")


def extract_elements_by_pattern(
    lines: List[str],
    pattern: str,
    use_first_group: bool = False,
) -> List[Dict]:
    """
    Extract code elements matching a regex pattern from source lines.

    Issue #281: Extracted helper to reduce repetition in extract_code_elements.

    Args:
        lines: Source code lines to search
        pattern: Regex pattern to match
        use_first_group: If True, use first non-None group; otherwise use group(1)

    Returns:
        List of element dicts with name, line_number, and context
    """
    elements = []
    for i, line in enumerate(lines):
        matches = re.finditer(pattern, line)
        for match in matches:
            if use_first_group:
                name = next((g for g in match.groups() if g), None)
            else:
                name = match.group(1)
            if name:
                elements.append(
                    {
                        "name": name.strip(),
                        "line_number": i + 1,
                        "context": line.strip(),
                    }
                )
    return elements


def extract_code_elements(content: str, language: str, patterns: Dict[str, Dict[str, str]]) -> Dict[str, List[Dict]]:
    """Extract code elements (functions, classes, etc.) from content"""
    elements = {"functions": [], "classes": [], "imports": [], "variables": []}

    if language not in patterns:
        return elements

    language_patterns = patterns[language]
    lines = content.splitlines()

    # Issue #281: Use extracted helper for all element types
    if "function" in language_patterns:
        elements["functions"] = extract_elements_by_pattern(lines, language_patterns["function"], use_first_group=True)

    if "class" in language_patterns:
        elements["classes"] = extract_elements_by_pattern(lines, language_patterns["class"], use_first_group=False)

    if "import" in language_patterns:
        elements["imports"] = extract_elements_by_pattern(lines, language_patterns["import"], use_first_group=True)

    return elements


def extract_element_code(content: str, line_number: int, element_type: str, max_lines: int = 50) -> str:
    """
    Extract code for a specific element with context.

    Issue #207: Extract function/class code for embedding generation.

    Args:
        content: Full file content
        line_number: Starting line of the element
        element_type: 'function' or 'class'
        max_lines: Maximum lines to extract

    Returns:
        Code snippet for the element
    """
    lines = content.splitlines()
    if line_number < 1 or line_number > len(lines):
        return ""

    start_idx = line_number - 1
    end_idx = min(start_idx + max_lines, len(lines))

    start_line = lines[start_idx]
    base_indent = len(start_line) - len(start_line.lstrip())

    for i in range(start_idx + 1, end_idx):
        line = lines[i]
        if not line.strip():
            continue
        current_indent = len(line) - len(line.lstrip())
        if current_indent <= base_indent and line.strip():
            end_idx = i
            break

    return "\n".join(lines[start_idx:end_idx])
