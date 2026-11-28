# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical file-type extension sets (single home, #19339).

Companion to ``utils.file_categorization`` (which owns ``HTML_EXTENSIONS``,
``ALL_CODE_EXTENSIONS`` and ``SKIP_DIRS``). Kept in its own module because
``file_categorization`` is over the file-size ceiling and may not grow.
Readers import these names; none may re-declare a literal copy
(``repo_tests/file_type_sets_one_home_19339_test.py``).
"""

from typing import FrozenSet

# Plain-text formats the knowledge pipelines can read as UTF-8 text.
TEXT_FILE_EXTENSIONS: FrozenSet[str] = frozenset(
    {
        ".md",
        ".rst",
        ".txt",
        ".py",
        ".js",
        ".ts",
        ".go",
        ".rb",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".php",
        ".sh",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".html",
        ".htm",
        ".xml",
        ".csv",
        ".sql",
        ".kt",
        ".swift",
        ".rs",
        ".scala",
        ".ex",
        ".exs",
        ".css",
        ".jsx",
        ".tsx",
    }
)

# Legacy ``.doc`` is NOT docx: python-docx cannot read it.
DOCX_EXTENSIONS: FrozenSet[str] = frozenset({".docx"})
