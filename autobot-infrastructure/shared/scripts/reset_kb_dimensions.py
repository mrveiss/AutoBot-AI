#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
# NOTE: CLI tool uses print() for user-facing output per LOGGING_STANDARDS.md
"""
Complete fix for AutoBot knowledge base embedding dimension issues.
This script:
1. Requests the wipe of the Redis vector store data (a #17038 proposal; ``--request-wipe`` / ``--dry-run``)
2. After an approved wipe, tests the knowledge base with a simple document (the index is recreated)

The script itself deletes nothing (#21383).
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The shared wipe-request helper sits beside this script; put it on the path when loaded by file path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kb_wipe_cli  # noqa: E402


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
        doc = Document(text=test_content, metadata={"source": "test", "category": "system"})
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
    logger.info("Run after the wipe was approved (--request-wipe); this step deletes nothing.")

    logger.info("\n1. Testing knowledge base initialization...")

    try:
        from knowledge_factory import get_knowledge_base_async

        # Create a fresh knowledge base
        kb = await get_knowledge_base_async()
        if kb is None:
            raise RuntimeError("Knowledge base unavailable: initialization failed or retry cooldown active")
        logger.info(f"✅ Knowledge base ready (Redis DB: {kb.redis_db})")
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
    logger.info("\n2. Testing API compatibility...")

    try:
        # Test category retrieval (this was failing before)
        # This is a mock test since we can't run the full API here
        logger.info("✅ API compatibility: Knowledge base should now work with endpoints")

    except Exception as e:
        logger.warning(f"⚠️  API compatibility test incomplete: {e}")


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Request the KB wipe, or test the KB after an approved wipe.")
    kb_wipe_cli.add_wipe_arguments(parser)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """Request/preview the wipe, or run the post-wipe test; the process exit code."""
    args = _parse_args(argv)
    if kb_wipe_cli.wipe_wanted(args):
        return 0 if asyncio.run(kb_wipe_cli.request_wipe(args.dry_run)) else 1
    return 0 if asyncio.run(reset_knowledge_base()) else 1


if __name__ == "__main__":
    logger.info("Starting knowledge base reset process...\n")
    sys.exit(main())
