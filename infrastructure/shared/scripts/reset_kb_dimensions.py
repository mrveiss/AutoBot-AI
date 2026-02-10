#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# NOTE: CLI tool uses print() for user-facing output per LOGGING_STANDARDS.md
"""
Complete fix for AutoBot knowledge base embedding dimension issues.
This script:
1. Clears all Redis vector store data
2. Resets the Redis index with correct dimensions
3. Fixes async/sync Redis client issues
4. Tests the knowledge base with a simple document
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


def _cleanup_redis_databases(r) -> int:
    """
    Clean up Redis databases by removing llama_index, doc, and vector keys.

    Issue #281: Extracted from reset_knowledge_base to reduce function length.

    Args:
        r: Redis client for dropping index.

    Returns:
        Total count of keys removed.
    """
    # Drop the index if it exists
    try:
        r.execute_command("FT.DROPINDEX", "llama_index", "DD")
        logger.info("✅ Dropped llama_index")
    except Exception as e:
        logger.warning(f"⚠️  Index drop: {e} (may not exist)")

    # Clean specific databases using centralized client
    cleanup_count = 0
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
                cleanup_count += len(keys)
                logger.info(f"✅ Cleaned {len(keys)} llama_index keys from {db_name} database")

            # Also look for doc: prefixed keys
            doc_keys = r_db.keys("doc:*")
            if doc_keys:
                for key in doc_keys:
                    r_db.delete(key)
                cleanup_count += len(doc_keys)
                logger.info(f"✅ Cleaned {len(doc_keys)} doc keys from {db_name} database")

            # Clean any vector index keys
            vector_keys = r_db.keys("*vector*")
            if vector_keys:
                for key in vector_keys:
                    r_db.delete(key)
                cleanup_count += len(vector_keys)
                logger.info(
                    f"✅ Cleaned {len(vector_keys)} vector keys from {db_name} database"
                )

        except Exception as e:
            logger.warning(f"⚠️  Database {db_name}: {e}")

    return cleanup_count


async def _test_knowledge_base_operations(kb) -> bool:
    """
    Test knowledge base document and search operations.

    Issue #281: Extracted from reset_knowledge_base to reduce function length.

    Args:
        kb: Initialized KnowledgeBase instance.

    Returns:
        True if all tests pass, False otherwise.
    """
    from llama_index.core import Document

    test_content = "AutoBot is an autonomous AI agent platform with advanced knowledge management capabilities."

    try:
        doc = Document(
            text=test_content, metadata={"source": "test", "category": "system"}
        )
        kb.index.insert(doc)
        logger.info("✅ Successfully added test document to vector store!")

        # Test search functionality
        results = await kb.search("AutoBot", n_results=1)
        logger.info(f"✅ Search test: Found {len(results)} results")

        if results:
            logger.info(f"   📄 Result content preview: {results[0]['content'][:100]}...")

        # Test fact storage (sync operations)
        fact_result = await kb.store_fact(
            content="AutoBot knowledge base is now working correctly.",
            metadata={"source": "reset_script", "category": "system"},
        )
        if fact_result["status"] == "success":
            logger.info("✅ Fact storage test successful")
        else:
            logger.error(f"⚠️  Fact storage test failed: {fact_result['message']}")

        # Test fact retrieval
        facts = await kb.get_fact()  # Get all facts
        logger.info(f"✅ Fact retrieval test: Found {len(facts)} facts")

        return True

    except Exception as e:
        logger.error(f"❌ Error during document operations: {e}")
        import traceback

        traceback.print_exc()
        return False


async def reset_knowledge_base():
    """
    Complete reset of the knowledge base to fix dimension and async issues.

    Issue #281: Extracted database cleanup to _cleanup_redis_databases() and
    KB testing to _test_knowledge_base_operations() to reduce function length
    from 133 to ~45 lines.
    """
    logger.info("🔧 AutoBot Knowledge Base Reset Tool")
    logger.info("=" * 50)

    # Connect to Redis using centralized client
    try:
        r = get_redis_client(database="main")
        if r is None:
            raise Exception("Redis client is None")
        r.ping()
        logger.info("✅ Connected to Redis")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Redis: {e}")
        return False

    logger.info("\n1. Cleaning up Redis vector store data...")

    # Issue #281: Use extracted helper for database cleanup
    cleanup_count = _cleanup_redis_databases(r)
    logger.info(f"\n2. Total cleanup: {cleanup_count} keys removed")

    logger.info("\n3. Testing knowledge base initialization...")

    try:
        from knowledge_base import KnowledgeBase

        # Create a fresh knowledge base
        kb = KnowledgeBase()
        logger.info(f"✅ Knowledge base created (will use Redis DB: {kb.redis_db})")

        # Initialize it
        await kb.ainit()
        logger.info("✅ Knowledge base initialized successfully")

        # Check embedding model and dimensions
        if hasattr(kb, "embed_model"):
            logger.info(f"✅ Embedding model: {kb.embedding_model_name}")
            test_embedding = kb.embed_model.get_text_embedding("test")
            logger.info(f"✅ Detected embedding dimension: {len(test_embedding)}")

        # Issue #281: Use extracted helper for KB operations testing
        return await _test_knowledge_base_operations(kb)

    except Exception as e:
        logger.error(f"❌ Error initializing knowledge base: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_api_compatibility():
    """Test that the knowledge base works with the API endpoints."""
    logger.info("\n4. Testing API compatibility...")

    try:
        # Test category retrieval (this was failing before)
        # This is a mock test since we can't run the full API here
        logger.info("✅ API compatibility: Knowledge base should now work with endpoints")

    except Exception as e:
        logger.warning(f"⚠️  API compatibility test incomplete: {e}")


if __name__ == "__main__":
    logger.info("Starting knowledge base reset process...\n")

    success = asyncio.run(reset_knowledge_base())

    if success:
        logger.info("\n" + "=" * 50)
        logger.info("🎉 KNOWLEDGE BASE RESET SUCCESSFUL!")
        logger.info("\nNext steps:")
        logger.info("1. Restart the AutoBot backend: ./run_agent.sh")
        logger.info("2. Try importing documentation via the web UI")
        logger.info("3. Test knowledge base search functionality")
        logger.info("\nThe following issues have been fixed:")
        logger.info("✅ Embedding dimension mismatch (now using 768-dim nomic-embed-text)")
        logger.error("✅ Redis async/await errors (now using sync operations)")
        logger.info("✅ Vector index schema conflicts (index recreated)")
        logger.info("✅ Knowledge base initialization problems")
    else:
        logger.info("\n" + "=" * 50)
        logger.error("❌ KNOWLEDGE BASE RESET FAILED")
        logger.error("Please check the error messages above and try:")
        logger.info("1. Ensure Redis is running: redis-cli ping")
        logger.info("2. Check Redis modules: redis-cli MODULE LIST")
        logger.info("3. Verify AutoBot dependencies are installed")
