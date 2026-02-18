#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Script to populate the knowledge base with all project documentation.
"""

import asyncio
import glob
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base import KnowledgeBase


async def _add_documentation_to_kb_block_5():
    """Define documentation patterns to include.

    Helper for add_documentation_to_kb (Issue #825).
    """
    # Define documentation patterns to include
    doc_patterns = [
        "README.md",
        "CLAUDE.md",
        "docs/**/*.md",
        "prompts/**/*.md",
        "*.md",  # Any markdown files in root
    ]


async def _add_documentation_to_kb_block_6():
    """Files to exclude (e.g., test results, node_modules).

    Helper for add_documentation_to_kb (Issue #825).
    """
    # Files to exclude (e.g., test results, node_modules)
    exclude_patterns = [
        "**/node_modules/**",
        "**/venv/**",
        "**/test-results/**",
        "**/playwright-report/**",
        "**/.pytest_cache/**",
    ]


async def _add_documentation_to_kb_block_8():
    """unique_files = set(all_files).

    Helper for add_documentation_to_kb (Issue #825).
    """
    unique_files = set(all_files)
    filtered_files = [
        fp
        for fp in unique_files
        if os.path.isfile(fp) and not should_exclude_file(fp, exclude_patterns)
    ]


async def _add_documentation_to_kb_block_1():
    """Category mapping for path prefixes (Issue #315: use lookup i.

    Helper for add_documentation_to_kb (Issue #825).
    """

    # Category mapping for path prefixes (Issue #315: use lookup instead of elif chain)
    def determine_category(rel_path: str) -> str:
        """Determine doc category from relative path (Issue #315: extracted helper)."""
        category_map = [
            ("docs/developer", "developer-docs"),
            ("docs/user_guide", "user-guide"),
            ("docs/reports", "reports"),
            ("prompts", "prompts"),
        ]
        # Check exact matches first
        if rel_path == "README.md":
            return "main-readme"
        if rel_path == "CLAUDE.md":
            return "claude-instructions"
        # Check prefix matches
        for prefix, cat in category_map:
            if rel_path.startswith(prefix):
                return cat
        return "documentation"


async def _add_documentation_to_kb_block_2():
    """async def add_single_file(fp: str, project_root: Path, kb) -.

    Helper for add_documentation_to_kb (Issue #825).
    """

    async def add_single_file(fp: str, project_root: Path, kb) -> tuple:
        """Add a single file to KB (Issue #315: extracted helper)."""
        rel_path = os.path.relpath(fp, project_root)
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


async def _add_documentation_to_kb_block_3():
    """for file_path in sorted(filtered_files):.

    Helper for add_documentation_to_kb (Issue #825).
    """
    for file_path in sorted(filtered_files):
        try:
            success, result = await add_single_file(file_path, project_root, kb)
            if success:
                pass
            else:
                error_count += 1
                logger.error(f"  Error: {result.get('message', 'Unknown error')}")
        except Exception as e:
            error_count += 1
            logger.info(f"  Exception adding {file_path}: {str(e)}")


async def _add_documentation_to_kb_block_4():
    """Test search functionality.

    Helper for add_documentation_to_kb (Issue #825).
    """
    # Test search functionality
    logger.info("\nTesting search functionality...")
    test_queries = [
        "installation",
        "configuration",
        "embedding",
        "redis",
        "ollama",
        "vue",
        "debian",
    ]


async def _add_documentation_to_kb_block_7():
    """for query in test_queries:.

    Helper for add_documentation_to_kb (Issue #825).
    """
    for query in test_queries:
        results = await kb.search(query, n_results=2)
        logger.info(f"\nSearch for '{query}': {len(results)} results")
        if results:
            logger.info(
                f"  First result: {results[0].get('metadata', {}).get('relative_path', 'Unknown')}"
            )


async def add_documentation_to_kb():
    """Add all project documentation to the knowledge base."""
    kb = KnowledgeBase()
    await kb.ainit()

    # Base paths for documentation
    project_root = Path("/home/kali/Desktop/AutoBot")

    await _add_documentation_to_kb_block_5()

    await _add_documentation_to_kb_block_6()

    all_files = []

    # Collect all documentation files
    for pattern in doc_patterns:
        files = glob.glob(str(project_root / pattern), recursive=True)
        all_files.extend(files)

    # Remove duplicates and filter out excluded patterns (Issue #315: extracted logic)
    def should_exclude_file(file_path: str, exclude_patterns: list) -> bool:
        """Check if file matches any exclude pattern (Issue #315: extracted helper)."""
        for exclude in exclude_patterns:
            if glob.fnmatch.fnmatch(file_path, exclude):
                return True
        return False

    await _add_documentation_to_kb_block_8()

    logger.info(
        f"Found {len(filtered_files)} documentation files to add to knowledge base"
    )

    await _add_documentation_to_kb_block_1()

    await _add_documentation_to_kb_block_2()

    # Add each file to the knowledge base
    success_count = 0
    error_count = 0

    await _add_documentation_to_kb_block_3()

    logger.info("\nKnowledge base population complete!")
    logger.info(f"Successfully added: {success_count} files")
    logger.error(f"Errors: {error_count} files")

    await _add_documentation_to_kb_block_4()

    await _add_documentation_to_kb_block_7()


if __name__ == "__main__":
    asyncio.run(add_documentation_to_kb())
