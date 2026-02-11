#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Fix knowledge base dimension mismatch by recreating with correct settings.
"""

import asyncio
import os
import sys
import logging

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import centralized Redis client
from utils.redis_client import get_redis_client


async def fix_dimensions():
    """Drop all llama_index traces and let it recreate properly."""

    # Connect to Redis using centralized client
    r = get_redis_client(database="main")

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


if __name__ == "__main__":
    success = asyncio.run(fix_dimensions())
    if success:
        logger.info("\nKnowledge base is now ready! You can run populate_knowledge_base.py")
    else:
        logger.error("\nFailed to fix dimensions issue")
