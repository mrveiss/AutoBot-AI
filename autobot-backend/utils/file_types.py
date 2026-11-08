# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical file-type extension sets (single home, #19339).

Companion to ``utils.file_categorization`` (which owns ``HTML_EXTENSIONS`` and
``ALL_CODE_EXTENSIONS``; ``SKIP_DIRS`` lives here and is re-exported there, #21004).
Kept in its own module because ``file_categorization`` is over the file-size
ceiling and may not grow.
Readers import these names; none may re-declare a literal copy
(``repo_tests/file_type_sets_one_home_19339_test.py``).
"""

from typing import FrozenSet

# Archived, backup, tool-cache and vendored-code trees (#21004): part of ``SKIP_DIRS``
# (no analysis value), but the knowledge file connector still reads them because
# they can hold user documents (``SKIP_DIRS - NON_CODE_ARCHIVE_DIRS``).
NON_CODE_ARCHIVE_DIRS: FrozenSet[str] = frozenset(
    {"archive", "archives", "backup", "backups", ".mypy_cache", "third_party"}
)

# Directories to completely skip (no analysis value)
SKIP_DIRS: FrozenSet[str] = (
    frozenset(
        {
            "node_modules",
            ".git",
            "__pycache__",
            ".pytest_cache",
            "dist",
            "build",
            ".venv",
            "venv",
            ".DS_Store",
            "temp",
            ".next",
            ".nuxt",
            ".svelte-kit",
            ".cache",
            ".parcel-cache",
            "coverage",
            ".nyc_output",
            "htmlcov",
            ".tox",
            ".idea",
            ".vscode",
            ".vs",
            "vendor",
            "bower_components",
            "target",  # Rust/Java build output
            "bin",
            "obj",  # .NET build output
            ".gradle",
            ".m2",  # Java build caches
            # #13602: git worktrees are near-complete copies of the repo. Measured on a
            # working checkout, 160,105 of 167,072 code files (96%) lived under these two
            # directories — every analytics walk was scanning the repo ~26 times over.
            # `duplicate_detector._get_files_to_scan` already documented `.worktrees/` as
            # pruned; it never was, because the name was missing from this set.
            ".worktrees",
            "worktrees",  # .claude/worktrees — same content, different parent
        }
    )
    | NON_CODE_ARCHIVE_DIRS
)  # #21004: the one analysis exclusion set

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
