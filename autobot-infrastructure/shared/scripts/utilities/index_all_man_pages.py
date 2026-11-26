#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Index ALL Available Man Pages on AutoBot Machines
Indexes every command with a man page for comprehensive CLI tool awareness
Enhanced with OS/Machine context for deduplication and agent awareness

The ingestion itself lives in ``services.man_page_ingestion`` (#22272); this is its CLI entry,
also run by the Celery refresh task. Do not add a second writer here.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from services.man_page_ingestion import get_all_available_commands, index_commands_in_batches
from utils.system_context import get_compatible_os_list, get_system_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def _log_system_context(system_ctx: dict):
    """
    Log system context information.

    Helper for main (#825).

    Args:
        system_ctx: System context dictionary
    """
    logger.info("\n3. Detecting system context...")
    logger.info("✓ Machine: %s (%s)", system_ctx["machine_id"], system_ctx["machine_ip"])
    logger.info("✓ OS: %s %s", system_ctx["os_name"], system_ctx["os_version"])
    logger.info("✓ Architecture: %s", system_ctx["architecture"])
    logger.info(
        "✓ Compatible with: %s",
        ", ".join(get_compatible_os_list(system_ctx["os_name"])),
    )


async def main():
    """Main indexing function"""
    logger.info("=" * 80)
    logger.info("COMPREHENSIVE MAN PAGE INDEXING")
    logger.info("=" * 80)

    kb_v2 = None
    try:
        # Initialize Knowledge Base V2
        from knowledge_factory import get_knowledge_base_async

        logger.info("\n1. Initializing Knowledge Base V2...")
        kb_v2 = await get_knowledge_base_async()
        if kb_v2 is None:
            raise RuntimeError("Knowledge base unavailable: initialization failed or retry cooldown active")

        if not kb_v2.initialized:
            logger.error("✗ Knowledge Base V2 initialization failed")
            return 1

        logger.info("✓ Knowledge Base V2 initialized")

        # Get all available commands
        logger.info("\n2. Scanning for all available commands...")
        all_commands = await get_all_available_commands()

        if not all_commands:
            logger.error("✗ No commands found")
            return 1

        logger.info("✓ Found %s commands to index", len(all_commands))

        # Get system context for indexing
        system_ctx = get_system_context()
        await _log_system_context(system_ctx)

        logger.info("\n4. Indexing man pages...")
        total_indexed = await index_commands_in_batches(kb_v2, all_commands, system_ctx)

        # Get final stats
        stats = await kb_v2.get_stats()

        logger.info("\n" + "=" * 80)
        logger.info("INDEXING COMPLETE")
        logger.info("=" * 80)
        logger.info("✓ Commands scanned: %s", len(all_commands))
        logger.info("✓ Successfully indexed: %s", total_indexed)
        logger.info("✓ Total facts in KB: %s", stats.get("total_facts", 0))
        logger.info("✓ Total vectors: %s", stats.get("total_vectors", 0))
        logger.info("=" * 80)

        return 0

    except Exception as e:
        logger.error("✗ Indexing failed: %s", e)
        import traceback

        traceback.print_exc()
        return 1

    finally:
        # Facts stored before a failure still count; this process's loop would cancel a waiting recompute (#19726).
        if kb_v2 is not None:
            await kb_v2._get_keyword_searcher().flush_refresh()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
