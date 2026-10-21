#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fix knowledge base dimension mismatch by recreating with correct settings.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Runs from any directory with no PYTHONPATH: put the repository root on the path for
# `autobot_shared` (#18964).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Import centralized Redis client
from autobot_shared.redis_client import get_redis_client  # noqa: E402


async def fix_dimensions():
    """Drop all llama_index traces and let it recreate properly."""

    # The llama_index vector store lives in the knowledge DB (db 1, DATABASE_MAPPING["knowledge"];
    # KnowledgeBase.redis_db), the DB the pre-#18964 script dropped it from.
    r = get_redis_client(database="knowledge")
    if r is None:
        logger.error("No Redis client available for the knowledge database; aborting before any change")
        return False

    logger.info("Cleaning up Redis...")

    # Drop the index if it exists
    try:
        r.execute_command("FT.DROPINDEX", "llama_index", "DD")
        logger.info("Dropped llama_index")
    except Exception as e:
        logger.info(f"Index drop: {e}")

    # Clean specific databases using centralized client
    database_names = [
        "main",
        "knowledge",
        "prompts",
        "agents",
        "metrics",
        "logs",
        "sessions",
        "workflows",
        "vectors",
        "models",
    ]

    for db_name in database_names:
        try:
            r_db = get_redis_client(database=db_name)
            if r_db is None:
                logger.warning("Database %s: no Redis client available, skipping", db_name)
                continue

            # Delete any llama_index related keys
            keys = r_db.keys("llama_index:*")
            if keys:
                for key in keys:
                    r_db.delete(key)
                logger.info(f"Cleaned {len(keys)} keys from {db_name} database")

            # Also look for doc: prefixed keys
            doc_keys = r_db.keys("doc:*")
            if doc_keys:
                for key in doc_keys:
                    r_db.delete(key)
                logger.info(f"Cleaned {len(doc_keys)} doc keys from {db_name} database")
        except Exception as e:
            logger.info(f"Database {db_name}: {e}")

    logger.info("\nRedis cleanup complete!")
    logger.info("\nNow testing with correct embedding model...")

    from knowledge_base import KnowledgeBase

    # Create a fresh knowledge base
    kb = KnowledgeBase()
    logger.info(f"Knowledge base will use Redis DB: {kb.redis_db}")

    # Initialize it
    await kb.ainit()
    logger.info("Knowledge base initialized")

    # Test adding a simple document
    test_content = "AutoBot is an autonomous AI agent platform."
    from llama_index.core import Document

    try:
        doc = Document(text=test_content, metadata={"source": "test"})
        kb.index.insert(doc)
        logger.info("Successfully added test document!")

        # Test search
        results = await kb.search("AutoBot", n_results=1)
        logger.info(f"Search test: Found {len(results)} results")

        return True
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main() -> int:
    """Run the dimension fix; the process exit code: 0 on success, 1 on failure."""
    if asyncio.run(fix_dimensions()):
        logger.info("\nKnowledge base is now ready! You can run populate_knowledge_base.py")
        return 0
    logger.error("\nFailed to fix dimensions issue")
    return 1


if __name__ == "__main__":
    sys.exit(main())
