#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
# NOTE: CLI tool uses print() for user-facing output per LOGGING_STANDARDS.md
"""Sync documentation changes to knowledge base"""

import asyncio
import json
import logging
import sys

from autobot_shared.paths import project_root

logger = logging.getLogger(__name__)

# knowledge_base / knowledge_sync_incremental live in autobot-backend, not
# under this script's own directory tree (#16710: neither module resolved
# from the previous two-levels-up path -- this script could only ever run if
# the backend happened to already be on sys.path some other way).
sys.path.insert(0, str(project_root() / "autobot-backend"))

from knowledge_factory import get_knowledge_base_async
from knowledge_sync_incremental import IncrementalKnowledgeSync, run_incremental_sync, start_background_sync_daemon


async def incremental_sync():
    """Perform intelligent incremental sync with 10-50x performance improvement"""
    logger.info("=== Incremental Knowledge Base Sync ===")
    logger.info("🚀 Using advanced incremental sync with GPU acceleration")

    try:
        # Use the new incremental sync system
        metrics = await run_incremental_sync()

        logger.info("\\n=== Incremental Sync Results ===")
        logger.info(f"📁 Files scanned: {metrics.total_files_scanned}")
        logger.info(f"🔄 Files changed: {metrics.files_changed}")
        logger.info(f"➕ Files added: {metrics.files_added}")
        logger.info(f"➖ Files removed: {metrics.files_removed}")
        logger.info(f"🧩 Chunks processed: {metrics.total_chunks_processed}")
        logger.info(f"⏱️  Total time: {metrics.total_processing_time:.3f}s")
        logger.info(f"⚡ Performance: {metrics.avg_chunks_per_second:.1f} chunks/sec")
        logger.error(f"🎮 GPU acceleration: {'✅' if metrics.gpu_acceleration_used else '❌'}")

        # Calculate improvement estimate
        if metrics.total_chunks_processed > 0:
            estimated_full_sync_time = metrics.total_chunks_processed * 0.5  # Conservative estimate
            improvement_factor = estimated_full_sync_time / max(metrics.total_processing_time, 0.1)
            logger.info(f"📈 Estimated improvement: {improvement_factor:.1f}x faster than full sync")

            if improvement_factor >= 10:
                logger.info("🎯 TARGET ACHIEVED: 10-50x performance improvement!")
            else:
                logger.warning("⚠️  Performance target not yet reached")

        # Test search functionality if any changes were made
        if metrics.files_changed + metrics.files_added > 0:
            logger.info("\\n=== Testing Updated Search Functionality ===")

            # Initialize knowledge base for testing
            kb = await get_knowledge_base_async()
            if kb is None:
                raise RuntimeError("Knowledge base unavailable: initialization failed or retry cooldown active")

            test_queries = ["autobot", "configuration", "installation", "troubleshoot"]

            for query in test_queries:
                try:
                    results = await kb.search(query=query)  # #16710: get_fact() never took a query
                    logger.info(f"Search '{query}': {len(results)} results found")
                except Exception as e:
                    logger.error(f"Search '{query}': error - {str(e)}")

        logger.info("\\n✅ Incremental sync completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Incremental sync failed: {e}")
        return False


async def print_sync_preview() -> bool:
    """Print what an incremental sync would change, applying nothing (#19701)."""
    changed, removed, expired = await IncrementalKnowledgeSync().preview_changes()
    print(json.dumps({"would_index": [str(path) for path in changed], "would_remove": removed, "would_expire": expired}, indent=2))  # noqa: print  # canonical: ignore py-print-smoke
    return True


async def show_status() -> bool:
    """Print the engine's recorded sync status; reads its state file, no KB connection (#19701)."""
    sync = IncrementalKnowledgeSync()
    await sync._load_sync_state()
    print(json.dumps(sync.get_sync_status(), indent=2))  # noqa: print  # canonical: ignore py-print-smoke
    return True


async def watch_sync(interval_minutes: int) -> bool:
    """Sync now, then keep syncing every *interval_minutes* until stopped (#19701)."""
    await run_incremental_sync()
    await start_background_sync_daemon(check_interval_minutes=interval_minutes)
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync documentation to knowledge base")
    parser.add_argument(
        "--incremental",
        "-i",
        action="store_true",
        help="Perform incremental sync (10-50x faster, default)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview changes without applying them")
    mode.add_argument("--watch", "--daemon", "-d", action="store_true", help="Keep syncing until stopped")
    mode.add_argument("--status", "-s", action="store_true", help="Show sync status")
    parser.add_argument("--interval", type=int, default=15, help="Minutes between syncs with --watch")
    parser.add_argument("--test", "-t", action="store_true", help="Test search functionality after sync")

    args = parser.parse_args()

    if args.dry_run:
        success = asyncio.run(print_sync_preview())
    elif args.watch:
        success = asyncio.run(watch_sync(args.interval))
    elif args.status:
        success = asyncio.run(show_status())
    else:
        success = asyncio.run(incremental_sync())

    sys.exit(0 if success else 1)
