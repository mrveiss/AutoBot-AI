#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fresh knowledge base setup - let llama_index create everything from scratch.
"""

import asyncio
import sys
from pathlib import Path

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# #14507: this used to insert the script's own parent (``scripts/setup``) and
# then import ``knowledge_base``, which lives in ``autobot-backend`` -- a
# directory that was never on the path -- so the KB step died with
# ModuleNotFoundError. Same defect as ``populate_knowledge_base.py``, which
# this script's success message tells the operator to run next. Add the
# directory the way the other operator entry points in this tree do (#14129).
_BACKEND_DIR = Path(__file__).resolve().parents[5] / "autobot-backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Import centralized Redis client
from autobot_shared.redis_client import get_redis_client  # noqa: E402
from autobot_shared.redis_utils import decode_redis_list, decode_redis_value  # noqa: E402


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
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("""
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
""")
    return test_file


async def _test_knowledge_base(kb, r) -> bool:
    """Test knowledge base with sample document.

    Helper for fresh_setup (Issue #825).
    """
    logger.info("\n3. Testing with sample document...")

    test_file = _create_test_document()

    # #14507: ``add_file`` is defined nowhere in the KnowledgeBase mixin chain
    # and ``search`` takes ``top_k``, not ``n_results`` (#10666) -- both calls
    # raised before this smoke test could report anything.
    result = await kb.add_document_from_file(
        file_path=test_file,
        category="documentation",
        metadata={"source": "test"},
    )

    logger.info(f"   Add result: {result}")

    if result.get("status") == "success":
        results = await kb.search("AutoBot features", top_k=2)
        logger.info(f"\n4. Search test results: {len(results)} found")
        if results:
            logger.info(f"   First result score: {results[0].get('score', 0)}")
            logger.info(f"   Content preview: {results[0].get('content', '')[:100]}...")

        logger.info("\n5. Checking created index...")
        indexes = r.execute_command("FT._LIST")
        logger.info(f"   Indexes: {indexes}")

        if indexes:
            # get_redis_client returns a decode_responses=True client, so FT.INFO
            # elements arrive as str, not the bytes this used to index with
            # (#13290) — decode defensively for both wire shapes.
            idx_name = decode_redis_value(indexes[0])
            info = decode_redis_list(r.execute_command("FT.INFO", idx_name))
            attrs_idx = info.index("attributes")
            attrs = info[attrs_idx + 1]
            for attr in attrs:
                if "vector" in attr:
                    for i, item in enumerate(attr):
                        if item == "dim":
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

    # Deferred: ``knowledge/__init__`` loads the composed class lazily (#1514),
    # so a module-scope import would pull redis, chromadb and llama_index in
    # merely to inspect this script.
    from knowledge import KnowledgeBase

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
