#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Quick test - Check if OS context is properly stored in metadata
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.system_context import generate_unique_key, get_system_context

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def _verify_stored_metadata(kb, fact_id: str) -> int:
    """
    Verify stored metadata has all required OS context fields.

    Helper for main (#825).

    Args:
        kb: KnowledgeBase instance
        fact_id: Fact ID to verify

    Returns:
        0 on success, 1 on failure
    """
    logger.info("\n4. Verifying Stored Metadata...")
    fact = await kb.get_fact(fact_id)

    if fact:
        meta = fact.get("metadata", {})
        logger.info(f"   ✓ Machine ID: {meta.get('machine_id')}")
        logger.info(f"   ✓ OS Name: {meta.get('os_name')}")
        logger.info(f"   ✓ Unique Key: {meta.get('unique_key')}")

        # Verify all OS fields are present
        required_fields = [
            "machine_id",
            "machine_ip",
            "os_name",
            "os_version",
            "os_type",
            "architecture",
            "kernel_version",
            "unique_key",
        ]

        missing = [f for f in required_fields if f not in meta]

        if missing:
            logger.error(f"   ✗ Missing fields: {missing}")
            return 1
        else:
            logger.info("   ✓ All OS context fields present")
            return 0

    else:
        logger.error("   ✗ Could not retrieve fact")
        return 1


async def main():
    """Quick test of OS context system"""
    logger.info("=" * 80)
    logger.info("Quick OS Context Test")
    logger.info("=" * 80)

    # Test system context detection
    logger.info("\n1. Testing OS Detection...")
    ctx = get_system_context()

    logger.info(f"   ✓ Machine: {ctx['machine_id']} @ {ctx['machine_ip']}")
    logger.info(f"   ✓ OS: {ctx['os_name']} {ctx['os_version']}")
    logger.info(f"   ✓ Platform: {ctx['os_type']} / {ctx['architecture']}")

    # Test unique key generation
    logger.info("\n2. Testing Unique Key Generation...")
    test_key = generate_unique_key(ctx["machine_id"], ctx["os_name"], "ls", "1")
    logger.info(f"   ✓ Unique Key: {test_key}")

    # Store a simple test fact with OS context
    logger.info("\n3. Testing Fact Storage with OS Context...")

    from knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    await kb.initialize()

    if not kb.initialized:
        logger.error("   ✗ KB init failed")
        return 1

    # Store test fact
    test_metadata = {
        "type": "test_man_page",
        "command": "ls",
        "section": "1",
        "title": "test man ls(1)",
        **ctx,
        "unique_key": test_key,
        "category": "test",
        "source": "quick_test",
    }

    result = await kb.store_fact(
        content="Test man page with OS context", metadata=test_metadata
    )

    if result.get("status") == "success":
        fact_id = result.get("fact_id")
        logger.info(f"   ✓ Stored fact: {fact_id}")

        # Retrieve and verify
        verify_result = await _verify_stored_metadata(kb, fact_id)
        if verify_result != 0:
            return 1

    else:
        logger.error(f"   ✗ Failed to store fact: {result}")
        return 1

    logger.info("\n" + "=" * 80)
    logger.info("✅ OS CONTEXT SYSTEM TEST PASSED")
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
