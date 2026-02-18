#!/usr/bin/env python3
"""
Fix knowledge base dimension mismatch by recreating with correct settings.
"""

import asyncio
import os
import sys

logger = logging.getLogger(__name__)


import redis

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def fix_dimensions():
    """Drop all llama_index traces and let it recreate properly."""

    # Connect to Redis
    r = redis.Redis(host="localhost", port=6379, db=0)

    logger.info("Cleaning up Redis...")

    # Drop the index if it exists
    try:
        r.execute_command("FT.DROPINDEX", "llama_index", "DD")
        logger.info("Dropped llama_index")
    except Exception as e:
        logger.info(f"Index drop: {e}")

    # Clean all databases
    for db in range(16):
        r_db = redis.Redis(host="localhost", port=6379, db=db)
        try:
            # Delete any llama_index related keys
            keys = r_db.keys("llama_index:*")
            if keys:
                for key in keys:
                    r_db.delete(key)
                logger.info(f"Cleaned {len(keys)} keys from DB {db}")

            # Also look for doc: prefixed keys
            doc_keys = r_db.keys("doc:*")
            if doc_keys:
                for key in doc_keys:
                    r_db.delete(key)
                logger.info(f"Cleaned {len(doc_keys)} doc keys from DB {db}")
        except Exception as e:
            logger.info(f"DB {db}: {e}")

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
        logger.info(
            "\nKnowledge base is now ready! You can run populate_knowledge_base.py"
        )
    else:
        logger.error("\nFailed to fix dimensions issue")
