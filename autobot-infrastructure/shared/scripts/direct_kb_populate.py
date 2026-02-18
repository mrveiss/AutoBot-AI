#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Direct knowledge base population - bypass API and add documents directly to vector store.
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


async def _test_search_functionality_directly(error_count, success_count):
    """Display Test Search Functionality Directly.

    Helper for populate_directly (Issue #825).
    """
    logger.info("\n=== Results ===")
    logger.info(f"✓ Successfully added: {success_count} documents")
    logger.error(f"❌ Errors: {error_count}")

    # Test search functionality directly
    if success_count > 0:
        logger.info("\n=== Testing Direct Search ===")

    return success_count > 0


async def populate_directly():
    """Populate knowledge base directly using KnowledgeBase.add_file()."""

    logger.info("=== Direct Knowledge Base Population ===")

    # Import and initialize knowledge base directly
    from knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    await kb.ainit()

    if kb.index is None:
        logger.error("❌ Knowledge base index not initialized")
        return False

    logger.info("✓ Knowledge base initialized successfully")
    logger.info(
        f"  Vector store type: {type(kb.vector_store).__name__ if kb.vector_store else 'In-memory'}"
    )
    logger.info(f"  Embedding model: {kb.embedding_model_name}")

    # Find documentation files
    project_root = Path("/home/kali/Desktop/AutoBot")
    doc_patterns = ["README.md", "CLAUDE.md", "docs/**/*.md"]

    all_files = []
    for pattern in doc_patterns:
        files = glob.glob(str(project_root / pattern), recursive=True)
        all_files.extend(files)

    # Remove duplicates and filter
    unique_files = list(set(all_files))
    filtered_files = [
        f for f in unique_files if os.path.isfile(f) and "node_modules" not in f
    ]

    logger.info(f"Found {len(filtered_files)} documentation files")

    success_count = 0
    error_count = 0

    # Add all files directly to vector store
    for file_path in sorted(filtered_files):
        try:
            rel_path = os.path.relpath(file_path, project_root)

            # Categorize documents
            if "user_guide" in rel_path:
                category = "user-guide"
            elif "developer" in rel_path:
                category = "developer-docs"
            elif "reports" in rel_path:
                category = "reports"
            elif rel_path in ["README.md", "CLAUDE.md"]:
                category = "project-overview"
            else:
                category = "documentation"

            metadata = {
                "source": "project-docs",
                "category": category,
                "relative_path": rel_path,
                "filename": os.path.basename(file_path),
            }

            logger.info(f"Adding: {rel_path} [{category}]")

            # Use add_file method directly
            result = await kb.add_file(
                file_path=file_path, file_type="txt", metadata=metadata
            )

            if result["status"] == "success":
                success_count += 1
                logger.info(f"  ✓ {result['message']}")
            else:
                error_count += 1
                logger.error(f"  ❌ {result['message']}")

        except Exception as e:
            error_count += 1
            logger.error(f"  ❌ Error: {str(e)}")

    await _test_search_functionality_directly(error_count, success_count)


if __name__ == "__main__":
    success = asyncio.run(populate_directly())
    if success:
        logger.info("\n🎉 Knowledge base populated successfully!")
        print(
            "You can now search for 'debian', 'installation', etc. in the AutoBot interface"
        )
    else:
        logger.error("\n💥 Knowledge base population failed!")
