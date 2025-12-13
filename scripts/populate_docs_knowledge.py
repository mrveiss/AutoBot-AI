#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Populate knowledge base with AutoBot documentation from docs/ folder.
This script indexes all the documentation in the docs folder to make it
searchable through the knowledge interface.
"""

import asyncio
import os
import sys
import glob
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Issue #338: Path prefix to category mapping
PATH_CATEGORY_MAP = {
    "docs/api/": "api_documentation",
    "docs/architecture/": "architecture_documentation",
    "docs/developer/": "developer_documentation",
    "docs/features/": "feature_documentation",
    "docs/security/": "security_documentation",
    "docs/troubleshooting/": "troubleshooting_documentation",
    "docs/agents/": "agent_documentation",
}

# Issue #338: Exact file to category mapping
FILE_CATEGORY_MAP = {
    "CLAUDE.md": "project_instructions",
    "README.md": "project_overview",
}


def _get_document_category(rel_path: str) -> str:
    """Determine document category from relative path (Issue #338 - extracted helper)."""
    # Check exact file matches first
    if rel_path in FILE_CATEGORY_MAP:
        return FILE_CATEGORY_MAP[rel_path]

    # Check path prefixes
    for prefix, category in PATH_CATEGORY_MAP.items():
        if rel_path.startswith(prefix):
            return category

    return "general_documentation"


def _should_exclude_file(file_path: str, exclude_patterns: list) -> bool:
    """Check if file should be excluded (Issue #338 - extracted helper)."""
    for exclude in exclude_patterns:
        if glob.fnmatch.fnmatch(file_path, exclude):
            return True
    return False


async def populate_docs_knowledge():
    """Populate knowledge base with documentation from docs/ folder."""

    logger.info("=== Populating Knowledge Base with AutoBot Documentation ===")

    # Import knowledge base (will use current Redis setup)
    from src.knowledge_base import KnowledgeBase

    try:
        kb = KnowledgeBase()
        logger.info("✓ Knowledge base initialized")

        # Wait for initialization
        await asyncio.sleep(2)

        # Find all documentation files in docs folder
        project_root = Path("/home/kali/Desktop/AutoBot")
        docs_patterns = [
            "docs/**/*.md",
            "CLAUDE.md",
            "README.md"
        ]

        exclude_patterns = [
            "**/node_modules/**",
            "**/venv/**",
            "**/test-results/**",
            "**/playwright-report/**",
            "**/.pytest_cache/**",
            "**/system-state.md"  # Skip this as it's status updates, not docs
        ]

        all_files = []
        for pattern in docs_patterns:
            files = glob.glob(str(project_root / pattern), recursive=True)
            all_files.extend(files)

        unique_files = set(all_files)
        # Issue #338: Use helper for file exclusion check
        filtered_files = [
            fp for fp in unique_files
            if not _should_exclude_file(fp, exclude_patterns) and os.path.isfile(fp)
        ]

        logger.info(f"Found {len(filtered_files)} documentation files to index")

        # Process each documentation file
        successful_adds = 0
        failed_adds = 0

        for file_path in sorted(filtered_files):
            try:
                # Read file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                if not content.strip():
                    logger.warning(f"Skipping empty file: {file_path}")
                    continue

                # Issue #338: Use helper for category determination
                rel_path = os.path.relpath(file_path, project_root)
                category = _get_document_category(rel_path)

                # Add to knowledge base
                await kb.add_document(
                    content=content,
                    metadata={
                        "source": rel_path,
                        "category": category,
                        "file_type": "markdown",
                        "indexed_by": "populate_docs_knowledge.py"
                    }
                )

                logger.info(f"✓ Added: {rel_path} (category: {category})")
                successful_adds += 1

            except Exception as e:
                logger.error(f"Failed to add {file_path}: {e}")
                failed_adds += 1

        logger.info("=== Documentation Population Complete ===")
        logger.info(f"✓ Successfully added: {successful_adds} documents")
        if failed_adds > 0:
            logger.error(f"Failed to add: {failed_adds} documents")

        # Get updated stats
        stats = await kb.get_stats()
        logger.info(f"Total documents in knowledge base: {stats.get('total_documents', 'unknown')}")

        return {
            "success": True,
            "documents_added": successful_adds,
            "documents_failed": failed_adds,
            "total_documents": stats.get('total_documents', 0)
        }

    except Exception as e:
        logger.error(f"Error during documentation population: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def main():
    """Main entry point"""
    result = await populate_docs_knowledge()

    if result["success"]:
        logger.info("Documentation population completed successfully!")
        logger.info(f"Added {result['documents_added']} documents to knowledge base")
    else:
        logger.error(f"Documentation population failed: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
