# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The one set of documentation the knowledge base holds (#19339, #19701).

Here rather than in ``populate_knowledge_base`` because the backend's sync engine reads it too, and
the backend cannot import from ``autobot-infrastructure``.
"""

from __future__ import annotations

import fnmatch
import re

DOC_PATTERNS = [
    "README.md",
    "CLAUDE.md",
    "docs/**/*.md",
    "autobot-backend/resources/prompts/**/*.md",
    "*.md",  # Any markdown files in root
]

# Files to exclude (e.g., test results, node_modules).
EXCLUDE_PATTERNS = [
    "**/node_modules/**",
    "**/venv/**",
    "**/test-results/**",
    "**/playwright-report/**",
    "**/.pytest_cache/**",
    "**/system-state.md",  # generated run state, not documentation
]


def should_exclude_file(file_path: str, exclude_patterns: list) -> bool:
    """Check if file matches any exclude pattern (Issue #315: extracted helper)."""
    return any(fnmatch.fnmatch(file_path, exclude) for exclude in exclude_patterns)


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    """*pattern* with ``glob.glob(recursive=True)``'s reading: ``*`` stays inside one directory."""
    return re.compile(re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*", "[^/]*"))


def in_doc_set(relative_path: str) -> bool:
    """Is this repo-relative path in the set, for a caller holding one path rather than scanning?"""
    if should_exclude_file(f"/{relative_path}", EXCLUDE_PATTERNS):
        return False
    return any(_pattern_regex(pattern).fullmatch(relative_path) for pattern in DOC_PATTERNS)
