#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# NOTE: CLI tool uses print() for user-facing output per LOGGING_STANDARDS.md
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

    # Connect to Redis (main database)
    try:
        redis_client = get_redis_client(database="main", async_client=True)
        if asyncio.iscoroutine(redis_client):
            redis_client = await redis_client

        if not redis_client:
            logger.error("Failed to connect to Redis")
            results["errors"].append("Redis connection failed")
            return results
    except Exception as e:
        logger.error(f"Redis connection error: {e}")
        results["errors"].append(str(e))
        return results

    # Also check knowledge database
    try:
        kb_redis_client = get_redis_client(database="knowledge", async_client=True)
        if asyncio.iscoroutine(kb_redis_client):
            kb_redis_client = await kb_redis_client
    except Exception:
        kb_redis_client = None
        logger.warning("Knowledge database not available, skipping")

    print("\n" + "=" * 70)
    print("Redis Metrics Cleanup - Phase 5 (Issue #348)")
    print("=" * 70)

    if dry_run:
        print("\n[DRY RUN] Scanning for legacy metric keys...\n")
    else:
        print("\n[CLEANUP] Scanning and deleting legacy metric keys...\n")

    all_keys = []

    # Scan each pattern
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
                print(f"  {pattern}: {len(keys)} keys found")
            else:
                print(f"  {pattern}: 0 keys")

        except Exception as e:
            logger.warning(f"Error scanning pattern {pattern}: {e}")
            results["errors"].append(f"Pattern {pattern}: {e}")

    results["keys_found"] = len(all_keys)

    print(f"\nTotal keys found: {len(all_keys)}")

    if not all_keys:
        print("\n✅ No legacy metric keys found. Redis is already clean!")
        return results

    # Show sample of keys to be deleted
    if all_keys:
        print("\nSample keys to delete:")
        for key in all_keys[:10]:
            print(f"  - {key}")
        if len(all_keys) > 10:
            print(f"  ... and {len(all_keys) - 10} more")

    # Dry run stops here
    if dry_run:
        print("\n[DRY RUN] No keys were deleted. Run without --dry-run to delete.")
        return results

    # Confirm deletion
    if not force:
        print(f"\n⚠️  This will DELETE {len(all_keys)} keys from Redis!")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return results

    # Delete keys
    print("\nDeleting keys...")
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
            logger.warning(f"Failed to delete {key}: {e}")
            results["errors"].append(f"Delete {key}: {e}")

    results["keys_deleted"] = deleted_count
    print(f"\n✅ Deleted {deleted_count}/{len(all_keys)} keys")

    if results["errors"]:
        print(f"\n⚠️  {len(results['errors'])} errors occurred:")
        for error in results["errors"][:5]:
            print(f"  - {error}")

    return results


async def main():
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
        print("Note: Run with --dry-run first to preview changes.")

    results = await cleanup_redis_metrics(
        dry_run=args.dry_run,
        force=args.force,
    )

    print("\n" + "=" * 70)
    print("Cleanup Summary")
    print("=" * 70)
    print(f"Patterns scanned: {results['patterns_scanned']}")
    print(f"Keys found: {results['keys_found']}")
    print(f"Keys deleted: {results['keys_deleted']}")
    print(f"Errors: {len(results['errors'])}")
    print("=" * 70)

    if args.dry_run:
        print("\nTo actually delete keys, run without --dry-run flag")
    else:
        print("\n✅ Redis metrics cleanup complete!")
        print("Prometheus is now the sole metrics store.")


if __name__ == "__main__":
    asyncio.run(main())
