#!/usr/bin/env python3
"""
Fresh knowledge base setup - let llama_index create everything from scratch.
"""

import asyncio
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _clean_redis() -> None:
    """Clean all Redis databases and indexes.

    Helper for fresh_setup (Issue #825).
    """
    logger.info("\n1. Cleaning Redis...")
    r = redis.Redis(host="localhost", port=6379, db=0)

    try:
        indexes = r.execute_command("FT._LIST")
        for idx in indexes:
            idx_name = idx.decode() if isinstance(idx, bytes) else idx
            r.execute_command("FT.DROPINDEX", idx_name, "DD")
            logger.info(f"   Dropped index: {idx_name}")
    except Exception as e:
        logger.info(f"   No indexes to drop: {e}")

    for db in range(16):
        r_db = redis.Redis(host="localhost", port=6379, db=db)
        r_db.flushdb()
        logger.info(f"   Flushed database {db}")

    logger.info("   Redis cleaned!")


async def _initialize_kb():
    """Initialize fresh knowledge base.

    Helper for fresh_setup (Issue #825).
    """
    logger.info("\n2. Initializing fresh knowledge base...")

    from knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    logger.info(f"   Will use embedding model: {kb.embedding_model_name}")
    logger.info(f"   Will use Redis DB: {kb.redis_db}")
    logger.info(f"   Will use index name: {kb.redis_index_name}")

    await kb.ainit()
    logger.info("   Knowledge base initialized!")

    return kb


async def _test_sample_document(kb):
    """Test with sample document and search.

    Helper for fresh_setup (Issue #825).
    """
    logger.info("\n3. Testing with sample document...")

    test_file = "/tmp/test_kb_doc.md"
    with open(test_file, "w") as f:
        f.write(
            """
# AutoBot Documentation Test

AutoBot is an autonomous AI agent platform designed for enterprise use.

## Features
- Multi-agent orchestration
- Redis-based memory
- Knowledge base with vector search
- Vue.js frontend
- FastAPI backend

## Installation
To install AutoBot, follow the setup guide in the README.
"""
        )

    result = await kb.add_file(
        file_path=test_file,
        file_type="txt",
        metadata={"source": "test", "category": "documentation"},
    )

    logger.info(f"   Add result: {result}")

    return result


def _verify_index() -> None:
    """Verify created index.

    Helper for fresh_setup (Issue #825).
    """
    logger.info("\n5. Checking created index...")
    r = redis.Redis(host="localhost", port=6379, db=0)

    indexes = r.execute_command("FT._LIST")
    logger.info(f"   Indexes: {indexes}")

    if indexes:
        idx_name = indexes[0].decode() if isinstance(indexes[0], bytes) else indexes[0]
        info = r.execute_command("FT.INFO", idx_name)
        attrs_idx = info.index(b"attributes")
        attrs = info[attrs_idx + 1]
        for attr in attrs:
            if b"vector" in attr:
                for i, item in enumerate(attr):
                    if item == b"dim":
                        logger.info(f"   Vector dimension: {attr[i+1]}")
                        break


async def fresh_setup():
    """Complete fresh setup of knowledge base."""

    logger.info("=== Fresh Knowledge Base Setup ===")

    _clean_redis()
    kb = await _initialize_kb()
    result = await _test_sample_document(kb)

    if result["status"] == "success":
        results = await kb.search("AutoBot features", n_results=2)
        logger.info(f"\n4. Search test results: {len(results)} found")
        if results:
            logger.info(f"   First result score: {results[0].get('score', 0)}")
            logger.info(f"   Content preview: {results[0].get('content', '')[:100]}...")

        _verify_index()

        return True
    else:
        logger.error(f"\n   Error: {result.get('message', 'Unknown error')}")
        return False


if __name__ == "__main__":
    success = asyncio.run(fresh_setup())
    if success:
        logger.info("\n✓ Knowledge base setup successful!")
        logger.info("You can now run populate_knowledge_base.py")
    else:
        logger.error("\n✗ Knowledge base setup failed!")
