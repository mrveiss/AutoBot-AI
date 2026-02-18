#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Fresh knowledge base setup - let llama_index create everything from scratch.
"""

import asyncio
import logging
import os
import sys
import logging

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import centralized Redis client
from utils.redis_client import get_redis_client


def _clean_redis_indexes(r) -> None:
    """Clean Redis indexes.

    Helper for fresh_setup (Issue #825).
    """
    try:
        indexes = r.execute_command("FT._LIST")
        for idx in indexes:
            idx_name = idx.decode() if isinstance(idx, bytes) else idx
            r.execute_command("FT.DROPINDEX", idx_name, "DD")
            logger.info(f"   Dropped index: {idx_name}")
    except Exception as e:
        logger.info(f"   No indexes to drop: {e}")


def _clean_redis_databases() -> None:
    """Clean Redis databases.

    Helper for fresh_setup (Issue #825).
    """
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
            if r_db is not None:
                r_db.flushdb()
                logger.info(f"   Flushed {db_name} database")
        except Exception as e:
            logger.info(f"   Could not flush {db_name}: {e}")


def _create_test_document() -> str:
    """Create a test document for knowledge base.

    Helper for fresh_setup (Issue #825).
    """
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
    return test_file


async def _test_knowledge_base(kb, r) -> bool:
    """Test knowledge base with sample document.

    Helper for fresh_setup (Issue #825).
    """
    logger.info("\n3. Testing with sample document...")

    test_file = _create_test_document()

    result = await kb.add_file(
        file_path=test_file,
        file_type="txt",
        metadata={"source": "test", "category": "documentation"},
    )

    logger.info(f"   Add result: {result}")

    if result["status"] == "success":
        results = await kb.search("AutoBot features", n_results=2)
        logger.info(f"\n4. Search test results: {len(results)} found")
        if results:
            logger.info(f"   First result score: {results[0].get('score', 0)}")
            logger.info(f"   Content preview: {results[0].get('content', '')[:100]}...")

        logger.info("\n5. Checking created index...")
        indexes = r.execute_command("FT._LIST")
        logger.info(f"   Indexes: {indexes}")

        if indexes:
            idx_name = (
                indexes[0].decode() if isinstance(indexes[0], bytes) else indexes[0]
            )
            info = r.execute_command("FT.INFO", idx_name)
            attrs_idx = info.index(b"attributes")
            attrs = info[attrs_idx + 1]
            for attr in attrs:
                if b"vector" in attr:
                    for i, item in enumerate(attr):
                        if item == b"dim":
                            logger.info(f"   Vector dimension: {attr[i+1]}")
                            break

        return True
    else:
        logger.error(f"\n   Error: {result.get('message', 'Unknown error')}")
        return False


async def fresh_setup():
    """Complete fresh setup of knowledge base."""

    logger.info("=== Fresh Knowledge Base Setup ===")

    logger.info("\n1. Cleaning Redis...")
    r = get_redis_client(database="main")

    _clean_redis_indexes(r)
    _clean_redis_databases()

    logger.info("   Redis cleaned!")

    logger.info("\n2. Initializing fresh knowledge base...")

    from knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    logger.info(f"   Will use embedding model: {kb.embedding_model_name}")
    logger.info(f"   Will use Redis DB: {kb.redis_db}")
    logger.info(f"   Will use index name: {kb.redis_index_name}")

    await kb.ainit()
    logger.info("   Knowledge base initialized!")

    return await _test_knowledge_base(kb, r)


if __name__ == "__main__":
    success = asyncio.run(fresh_setup())
    if success:
        logger.info("\n✓ Knowledge base setup successful!")
        logger.info("You can now run populate_knowledge_base.py")
    else:
        logger.error("\n✗ Knowledge base setup failed!")
