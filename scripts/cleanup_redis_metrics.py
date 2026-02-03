#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# Converted to logger.info() for pre-commit compliance
"""
Redis Metrics Cleanup Script - Phase 5 (Issue #348)

Removes legacy metric keys from Redis that are no longer needed now that
Prometheus is the primary metrics store. This script cleans up:

1. System metrics: metrics:system:*, metrics:performance:*, metrics:knowledge_base:*
2. Error metrics: error_metrics:*
3. Cache stats: kb_cache_stats
4. Legacy monitoring data: autobot_metrics:*, monitoring:*

IMPORTANT: Run this script AFTER verifying Prometheus/Grafana integration is working.
This is a destructive operation - backup Redis first if needed.

Usage:
    python scripts/cleanup_redis_metrics.py --dry-run    # Preview what will be deleted
    python scripts/cleanup_redis_metrics.py              # Actually delete keys
    python scripts/cleanup_redis_metrics.py --force      # Skip confirmation
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.redis_client import get_redis_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Key patterns to clean up
LEGACY_KEY_PATTERNS = [
    # System metrics (from SystemMetricsCollector.store_metrics)
    "metrics:system:*",
    "metrics:performance:*",
    "metrics:services:*",
    "metrics:knowledge_base:*",
    "metrics:llm:*",
    # Error metrics (from ErrorMetricsCollector._persist_metric)
    "error_metrics:*",
    # Cache stats
    "kb_cache_stats",
    # Legacy monitoring patterns
    "autobot_metrics:*",
    "monitoring:*",
    # Old time series data
    "ts:metrics:*",
]


async def _connect_redis_clients(results: dict) -> tuple:
    """
    Connect to Redis main and knowledge databases.

    Issue #281: Extracted from cleanup_redis_metrics to reduce function length.

    Args:
        results: Results dictionary to update with errors.

    Returns:
        Tuple of (redis_client, kb_redis_client). Either may be None on failure.
    """
    redis_client = None
    kb_redis_client = None

    # Connect to Redis (main database)
    try:
        redis_client = get_redis_client(database="main", async_client=True)
        if asyncio.iscoroutine(redis_client):
            redis_client = await redis_client

        if not redis_client:
            logger.error("Failed to connect to Redis")
            results["errors"].append("Redis connection failed")
    except Exception as e:
        logger.error("Redis connection error: %s", e)
        results["errors"].append(str(e))

    # Also check knowledge database
    try:
        kb_redis_client = get_redis_client(database="knowledge", async_client=True)
        if asyncio.iscoroutine(kb_redis_client):
            kb_redis_client = await kb_redis_client
    except Exception:
        kb_redis_client = None
        logger.warning("Knowledge database not available, skipping")

    return redis_client, kb_redis_client


async def _scan_all_patterns(redis_client, kb_redis_client, results: dict) -> list:
    """
    Scan all legacy key patterns and collect matching keys.

    Issue #281: Extracted from cleanup_redis_metrics to reduce function length.

    Args:
        redis_client: Main Redis client.
        kb_redis_client: Knowledge database Redis client (may be None).
        results: Results dictionary to update.

    Returns:
        List of all keys found across all patterns.
    """
    all_keys = []

    for pattern in LEGACY_KEY_PATTERNS:
        try:
            # Scan main database
            keys = await scan_keys(redis_client, pattern)

            # Also scan knowledge database for kb_cache_stats
            if kb_redis_client and "kb_cache" in pattern:
                kb_keys = await scan_keys(kb_redis_client, pattern)
                keys.extend([f"[knowledge]{k}" for k in kb_keys])

            results["keys_by_pattern"][pattern] = len(keys)
            all_keys.extend(keys)

            if keys:
                logger.info("  %s: %d keys found", pattern, len(keys))
            else:
                logger.info("  %s: 0 keys", pattern)

        except Exception as e:
            logger.warning("Error scanning pattern %s: %s", pattern, e)
            results["errors"].append(f"Pattern {pattern}: {e}")

    return all_keys


async def _delete_keys(all_keys: list, redis_client, kb_redis_client, results: dict) -> int:
    """
    Delete all collected keys from Redis.

    Issue #281: Extracted from cleanup_redis_metrics to reduce function length.

    Args:
        all_keys: List of keys to delete.
        redis_client: Main Redis client.
        kb_redis_client: Knowledge database Redis client (may be None).
        results: Results dictionary to update with errors.

    Returns:
        Count of successfully deleted keys.
    """
    deleted_count = 0

    for key in all_keys:
        try:
            # Handle knowledge database keys
            if key.startswith("[knowledge]"):
                actual_key = key.replace("[knowledge]", "")
                if kb_redis_client:
                    await kb_redis_client.delete(actual_key)
            else:
                await redis_client.delete(key)
            deleted_count += 1
        except Exception as e:
            logger.warning("Failed to delete %s: %s", key, e)
            results["errors"].append(f"Delete {key}: {e}")

    return deleted_count


async def scan_keys(redis_client, pattern: str) -> list:
    """Scan for keys matching a pattern."""
    keys = []
    async for key in redis_client.scan_iter(match=pattern):
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        keys.append(key)
    return keys


async def cleanup_redis_metrics(dry_run: bool = True, force: bool = False) -> dict:
    """
    Clean up legacy metric keys from Redis.

    Issue #281: Extracted connection logic to _connect_redis_clients(),
    pattern scanning to _scan_all_patterns(), and key deletion to _delete_keys()
    to reduce function length from 133 to ~55 lines.

    Args:
        dry_run: If True, only show what would be deleted
        force: If True, skip confirmation prompt

    Returns:
        Dictionary with cleanup results
    """
    results = {
        "patterns_scanned": len(LEGACY_KEY_PATTERNS),
        "keys_found": 0,
        "keys_deleted": 0,
        "keys_by_pattern": {},
        "errors": [],
    }

    # Issue #281: Use extracted helper for connection
    redis_client, kb_redis_client = await _connect_redis_clients(results)
    if not redis_client:
        return results

    logger.info("=" * 70)
    logger.info("Redis Metrics Cleanup - Phase 5 (Issue #348)")
    logger.info("=" * 70)

    if dry_run:
        logger.info("[DRY RUN] Scanning for legacy metric keys...")
    else:
        logger.info("[CLEANUP] Scanning and deleting legacy metric keys...")

    # Issue #281: Use extracted helper for pattern scanning
    all_keys = await _scan_all_patterns(redis_client, kb_redis_client, results)
    results["keys_found"] = len(all_keys)

    logger.info("Total keys found: %d", len(all_keys))

    if not all_keys:
        logger.info("No legacy metric keys found. Redis is already clean!")
        return results

    # Show sample of keys to be deleted
    logger.info("Sample keys to delete:")
    for key in all_keys[:10]:
        logger.info("  - %s", key)
    if len(all_keys) > 10:
        logger.info("  ... and %d more", len(all_keys) - 10)

    # Dry run stops here
    if dry_run:
        logger.info("[DRY RUN] No keys were deleted. Run without --dry-run to delete.")
        return results

    # Confirm deletion
    if not force:
        logger.warning("This will DELETE %d keys from Redis!", len(all_keys))
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            logger.info("Aborted.")
            return results

    # Issue #281: Use extracted helper for deletion
    logger.info("Deleting keys...")
    deleted_count = await _delete_keys(all_keys, redis_client, kb_redis_client, results)

    results["keys_deleted"] = deleted_count
    logger.info("Deleted %d/%d keys", deleted_count, len(all_keys))

    if results["errors"]:
        logger.warning("%d errors occurred:", len(results["errors"]))
        for error in results["errors"][:5]:
            logger.warning("  - %s", error)

    return results


async def main():
    """Entry point for Redis legacy metrics cleanup CLI."""
    parser = argparse.ArgumentParser(
        description="Clean up legacy metric keys from Redis (Phase 5)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    # Default to dry-run for safety
    if not args.dry_run and not args.force:
        logger.info("Note: Run with --dry-run first to preview changes.")

    results = await cleanup_redis_metrics(
        dry_run=args.dry_run,
        force=args.force,
    )

    logger.info("=" * 70)
    logger.info("Cleanup Summary")
    logger.info("=" * 70)
    logger.info("Patterns scanned: %d", results["patterns_scanned"])
    logger.info("Keys found: %d", results["keys_found"])
    logger.info("Keys deleted: %d", results["keys_deleted"])
    logger.info("Errors: %d", len(results["errors"]))
    logger.info("=" * 70)

    if args.dry_run:
        logger.info("To actually delete keys, run without --dry-run flag")
    else:
        logger.info("Redis metrics cleanup complete!")
        logger.info("Prometheus is now the sole metrics store.")


if __name__ == "__main__":
    asyncio.run(main())
