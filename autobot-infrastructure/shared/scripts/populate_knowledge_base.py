#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Script to populate the knowledge base with all project documentation.

#14405: an automated function-length pass (Issue #825) sliced the single
``add_documentation_to_kb`` coroutine into eight ``_add_documentation_to_kb_block_N``
helpers that took no arguments and returned nothing, then left the caller reading
the locals those helpers had carried away with them -- ``doc_patterns``,
``exclude_patterns``, ``filtered_files``, ``determine_category``,
``add_single_file``, ``all_files``, ``project_root``, ``kb``, ``test_queries``
and ``error_count`` were all undefined at their point of use (13 x F821), so the
script raised NameError on its first statement of real work. The blocks are
reassembled below as helpers that take what they read and return what they
produce, keeping every step the extraction had preserved.
"""

import asyncio
import fnmatch
import glob
import logging
import os
import sys
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base import KnowledgeBase

# Documentation patterns to include.
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
]

# Queries used to smoke-test retrieval once the base has been populated.
SEARCH_SMOKE_QUERIES = [
    "installation",
    "configuration",
    "embedding",
    "redis",
    "ollama",
    "vue",
    "debian",
]

# Category mapping for path prefixes (Issue #315: use lookup instead of elif chain)
CATEGORY_PREFIXES = [
    ("docs/developer", "developer-docs"),
    ("docs/user_guide", "user-guide"),
    ("docs/reports", "reports"),
    ("autobot-backend/resources/prompts", "prompts"),
]

# Default deployment root, matching the ``${AUTOBOT_PROJECT_ROOT:-...}`` shell
# fallback a sweep left embedded in a Python string literal (#14405).
DEFAULT_PROJECT_ROOT = "/opt/autobot/code_source"


def project_root() -> Path:
    """Resolve the documentation root, honouring AUTOBOT_PROJECT_ROOT."""
    return Path(os.environ.get("AUTOBOT_PROJECT_ROOT") or DEFAULT_PROJECT_ROOT)


def should_exclude_file(file_path: str, exclude_patterns: list) -> bool:
    """Check if file matches any exclude pattern (Issue #315: extracted helper)."""
    for exclude in exclude_patterns:
        if fnmatch.fnmatch(file_path, exclude):
            return True
    return False


def determine_category(rel_path: str) -> str:
    """Determine doc category from relative path (Issue #315: extracted helper)."""
    # Check exact matches first
    if rel_path == "README.md":
        return "main-readme"
    if rel_path == "CLAUDE.md":
        return "claude-instructions"
    # Check prefix matches
    for prefix, category in CATEGORY_PREFIXES:
        if rel_path.startswith(prefix):
            return category
    return "documentation"


def collect_documentation_files(root: Path) -> List[str]:
    """Expand DOC_PATTERNS under *root*, de-duplicate, and drop excluded paths."""
    all_files: List[str] = []
    for pattern in DOC_PATTERNS:
        all_files.extend(glob.glob(str(root / pattern), recursive=True))

    unique_files = set(all_files)
    return [fp for fp in unique_files if os.path.isfile(fp) and not should_exclude_file(fp, EXCLUDE_PATTERNS)]


async def add_single_file(fp: str, root: Path, kb) -> tuple:
    """Add a single file to KB (Issue #315: extracted helper)."""
    rel_path = os.path.relpath(fp, root)
    category = determine_category(rel_path)
    metadata = {
        "source": "project-docs",
        "category": category,
        "relative_path": rel_path,
        "doc_type": "markdown",
    }
    logger.info(f"Adding: {rel_path} [{category}]")
    result = await kb.add_file(file_path=fp, file_type="txt", metadata=metadata)
    return result["status"] == "success", result


async def add_files_to_kb(files: List[str], root: Path, kb) -> Tuple[int, int]:
    """Add every file to the knowledge base, returning (successes, errors)."""
    success_count = 0
    error_count = 0
    for file_path in sorted(files):
        try:
            success, result = await add_single_file(file_path, root, kb)
            if success:
                success_count += 1
            else:
                error_count += 1
                logger.error(f"  Error: {result.get('message', 'Unknown error')}")
        except Exception as e:
            error_count += 1
            logger.info(f"  Exception adding {file_path}: {str(e)}")
    return success_count, error_count


async def run_search_smoke_tests(kb) -> None:
    """Query the populated base so an empty or unindexed collection is visible."""
    logger.info("\nTesting search functionality...")
    for query in SEARCH_SMOKE_QUERIES:
        results = await kb.search(query, n_results=2)
        logger.info(f"\nSearch for '{query}': {len(results)} results")
        if results:
            logger.info(f"  First result: {results[0].get('metadata', {}).get('relative_path', 'Unknown')}")


async def add_documentation_to_kb():
    """Add all project documentation to the knowledge base."""
    kb = KnowledgeBase()
    await kb.ainit()

    root = project_root()
    filtered_files = collect_documentation_files(root)
    logger.info(f"Found {len(filtered_files)} documentation files to add to knowledge base")

    success_count, error_count = await add_files_to_kb(filtered_files, root, kb)

    logger.info("\nKnowledge base population complete!")
    logger.info(f"Successfully added: {success_count} files")
    logger.error(f"Errors: {error_count} files")

    await run_search_smoke_tests(kb)


if __name__ == "__main__":
    asyncio.run(add_documentation_to_kb())
