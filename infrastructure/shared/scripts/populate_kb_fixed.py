#!/usr/bin/env python3
"""
Populate knowledge base with ChromaDB to avoid Redis dimension issues.
"""

import asyncio
import glob
import os
import sys
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_DOC_PATTERNS = ["README.md", "CLAUDE.md", "docs/**/*.md", "*.md"]

_EXCLUDE_PATTERNS = [
    "**/node_modules/**",
    "**/venv/**",
    "**/test-results/**",
    "**/playwright-report/**",
    "**/.pytest_cache/**",
]


def _find_documentation_files(project_root: Path) -> list:
    """Find and filter documentation files from project root.

    Helper for populate_knowledge_base_chromadb (#825).
    """
    all_files = []
    for pattern in _DOC_PATTERNS:
        files = glob.glob(str(project_root / pattern), recursive=True)
        all_files.extend(files)

    filtered_files = []
    for file_path in set(all_files):
        should_exclude = any(
            glob.fnmatch.fnmatch(file_path, exc)
            for exc in _EXCLUDE_PATTERNS
        )
        if not should_exclude and os.path.isfile(file_path):
            filtered_files.append(file_path)

    return sorted(filtered_files)


def _categorize_document(rel_path: str) -> str:
    """Determine document category from relative path.

    Helper for populate_knowledge_base_chromadb (#825).
    """
    category_map = [
        ("docs/guides", "user-guide"),
        ("docs/development", "developer-docs"),
        ("docs/reports", "reports"),
    ]
    for path_fragment, category in category_map:
        if path_fragment in rel_path:
            return category
    if rel_path in ["README.md", "CLAUDE.md"]:
        return "project-overview"
    return "documentation"


async def _test_kb_search(kb):
    """Test knowledge base search functionality.

    Helper for populate_knowledge_base_chromadb (#825).
    """
    logger.info("=== Testing Search ===")
    test_queries = ["installation", "configuration", "autobot", "debian"]
    for query in test_queries:
        try:
            results = await kb.search(query, n_results=2)
            logger.info("Query '%s': %s results", query, len(results))
            if results:
                filename = results[0].get(
                    "metadata", {}
                ).get("filename", "Unknown")
                logger.info("  Top result: %s", filename)
        except Exception as e:
            logger.error("  Search failed: %s", e)


async def populate_knowledge_base_chromadb():
    """Populate knowledge base using ChromaDB."""
    logger.info("=== Populating Knowledge Base with ChromaDB ===")
    os.environ["AUTOBOT_VECTOR_STORE_TYPE"] = "chroma"

    from knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    logger.info("Vector store type: %s", kb.vector_store_type)
    await kb.ainit()

    if kb.vector_store is None:
        logger.error("Failed to initialize vector store")
        return False

    logger.info("Knowledge base initialized with ChromaDB")
    project_root = Path("/home/kali/Desktop/AutoBot")
    filtered_files = _find_documentation_files(project_root)
    logger.info("Found %s documentation files", len(filtered_files))

    success_count = 0
    error_count = 0

    for file_path in filtered_files:
        try:
            rel_path = os.path.relpath(file_path, project_root)
            category = _categorize_document(rel_path)
            metadata = {
                "source": "project-docs",
                "category": category,
                "relative_path": rel_path,
                "filename": os.path.basename(file_path),
            }
            logger.info("Adding: %s [%s]", rel_path, category)
            result = await kb.add_file(
                file_path=file_path, file_type="txt", metadata=metadata
            )
            if result["status"] == "success":
                success_count += 1
            else:
                error_count += 1
                logger.error("  %s", result["message"])
        except Exception as e:
            error_count += 1
            logger.error("  Error adding %s: %s", file_path, e)

    logger.info("=== Results ===")
    logger.info("Successfully added: %s documents", success_count)
    logger.info("Errors: %s", error_count)

    if success_count > 0:
        await _test_kb_search(kb)

    return success_count > 0


if __name__ == "__main__":
    success = asyncio.run(populate_knowledge_base_chromadb())
    if success:
        logger.info("\n🎉 Knowledge base population completed!")
    else:
        logger.error("\n💥 Knowledge base population failed!")
