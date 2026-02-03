#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Category Index Migration Script

Issue #258: Creates Redis SET indexes for category-based fact lookups.
This enables O(1) category filtering instead of O(n) SCAN operations.

Index structure:
    category:index:{category} -> SET of fact IDs

Run once to index existing facts, then new facts will be auto-indexed
via store_fact() method.

Usage:
    python scripts/migrations/migrate_category_indexes.py
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import redis

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load .env file
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from backend.knowledge_categories import get_category_for_source

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _connect_to_redis() -> redis.Redis:
    """
    Connect to Redis and return client.

    Issue #281: Extracted from migrate_category_indexes to reduce function length.

    Returns:
        Redis client or None if connection failed.
    """
    redis_host = os.getenv("AUTOBOT_REDIS_HOST", "172.16.168.23")
    redis_port = int(os.getenv("AUTOBOT_REDIS_PORT", "6379"))
    redis_password = os.getenv("REDIS_PASSWORD") or os.getenv("AUTOBOT_REDIS_PASSWORD")
    redis_db = int(os.getenv("AUTOBOT_REDIS_DB_KNOWLEDGE", "1"))

    logger.info("Connecting to Redis at %s:%s (db=%s)", redis_host, redis_port, redis_db)

    try:
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=redis_db,
            decode_responses=False,
        )
        redis_client.ping()
        logger.info("Connected to Redis successfully")
        return redis_client
    except Exception as e:
        logger.error("Failed to connect to Redis: %s", e)
        return None


def _clear_existing_indexes(redis_client: redis.Redis) -> None:
    """
    Clear existing category indexes.

    Issue #281: Extracted from migrate_category_indexes to reduce function length.

    Args:
        redis_client: Redis client instance.
    """
    existing_indexes = redis_client.keys("category:index:*")
    if existing_indexes:
        logger.info("Found %s existing category indexes", len(existing_indexes))
        for idx_key in existing_indexes:
            count = redis_client.scard(idx_key)
            logger.info("  - %s: %s facts", idx_key.decode() if isinstance(idx_key, bytes) else idx_key, count)

        logger.info("\nClearing existing indexes to rebuild...")
        for idx_key in existing_indexes:
            redis_client.delete(idx_key)
        logger.info("Existing indexes cleared")


def _scan_all_fact_keys(redis_client: redis.Redis) -> list:
    """
    Scan all fact keys from Redis.

    Issue #281: Extracted from migrate_category_indexes to reduce function length.

    Args:
        redis_client: Redis client instance.

    Returns:
        List of all fact keys.
    """
    logger.info("\nStep 1: Scanning all fact keys...")
    all_fact_keys = []
    cursor = 0
    while True:
        cursor, keys = redis_client.scan(cursor, match="fact:*", count=1000)
        all_fact_keys.extend(keys)
        if cursor == 0:
            break

    logger.info("Found %s facts to index", len(all_fact_keys))
    return all_fact_keys


def _process_facts_and_build_indexes(
    redis_client: redis.Redis, all_fact_keys: list
) -> tuple:
    """
    Process facts in chunks and build category indexes.

    Issue #281: Extracted from migrate_category_indexes to reduce function length.

    Args:
        redis_client: Redis client instance.
        all_fact_keys: List of all fact keys to process.

    Returns:
        Tuple of (category_counts, indexed_count, skipped_count, error_count).
    """
    logger.info("\nStep 2: Fetching metadata and building indexes...")

    category_counts = {}
    indexed_count = 0
    skipped_count = 0
    error_count = 0

    chunk_size = 500
    for i in range(0, len(all_fact_keys), chunk_size):
        chunk_keys = all_fact_keys[i : i + chunk_size]

        pipeline = redis_client.pipeline()
        for key in chunk_keys:
            pipeline.hget(key, "metadata")
        metadata_results = pipeline.execute()

        for fact_key, metadata_raw in zip(chunk_keys, metadata_results):
            try:
                if not metadata_raw:
                    skipped_count += 1
                    continue

                metadata_str = (
                    metadata_raw.decode("utf-8")
                    if isinstance(metadata_raw, bytes)
                    else str(metadata_raw)
                )
                metadata = json.loads(metadata_str)

                fact_key_str = (
                    fact_key.decode("utf-8")
                    if isinstance(fact_key, bytes)
                    else str(fact_key)
                )
                fact_id = fact_key_str.replace("fact:", "")

                source = metadata.get("source", "")
                if not source:
                    skipped_count += 1
                    continue

                main_category = get_category_for_source(source)
                if hasattr(main_category, "value"):
                    main_category = main_category.value

                index_key = f"category:index:{main_category}"
                redis_client.sadd(index_key, fact_id)

                category_counts[main_category] = category_counts.get(main_category, 0) + 1
                indexed_count += 1

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug("Error processing %s: %s", fact_key, e)
                error_count += 1
                continue

        progress = min(i + chunk_size, len(all_fact_keys))
        logger.info("  Processed %s/%s facts...", progress, len(all_fact_keys))

    return category_counts, indexed_count, skipped_count, error_count


def _report_and_verify_results(
    redis_client: redis.Redis,
    all_fact_keys: list,
    category_counts: dict,
    indexed_count: int,
    skipped_count: int,
    error_count: int,
    elapsed: float,
) -> None:
    """
    Report migration results and verify indexes.

    Issue #281: Extracted from migrate_category_indexes to reduce function length.

    Args:
        redis_client: Redis client instance.
        all_fact_keys: List of all fact keys processed.
        category_counts: Dict of category to count mappings.
        indexed_count: Number of facts indexed.
        skipped_count: Number of facts skipped.
        error_count: Number of errors.
        elapsed: Time elapsed in seconds.
    """
    logger.info("\n" + "=" * 60)
    logger.info("Migration Complete!")
    logger.info("=" * 60)
    logger.info("Total facts scanned: %s", len(all_fact_keys))
    logger.info("Facts indexed: %s", indexed_count)
    logger.info("Facts skipped (no source): %s", skipped_count)
    logger.info("Errors: %s", error_count)
    logger.info("Time elapsed: %.2fs", elapsed)
    logger.info("\nCategory index counts:")
    for cat, count in sorted(category_counts.items()):
        logger.info("  - %s: %s facts", cat, count)

    logger.info("\nVerifying indexes...")
    for cat in category_counts:
        index_key = f"category:index:{cat}"
        actual_count = redis_client.scard(index_key)
        expected_count = category_counts[cat]
        status = "✅" if actual_count == expected_count else "❌"
        logger.info("  %s %s: %s (expected %s)", status, index_key, actual_count, expected_count)

    logger.info("\n" + "=" * 60)
    logger.info("Category indexes created successfully!")
    logger.info("The get_facts_by_category endpoint will now use O(1) lookups.")
    logger.info("=" * 60)


async def migrate_category_indexes():
    """
    Create category indexes for all existing facts.

    Issue #281: Extracted helpers _connect_to_redis(), _clear_existing_indexes(),
    _scan_all_fact_keys(), _process_facts_and_build_indexes(), and
    _report_and_verify_results() to reduce function length from 160 to ~25 lines.
    """
    logger.info("=" * 60)
    logger.info("Category Index Migration - Issue #258")
    logger.info("=" * 60)

    start_time = time.perf_counter()

    # Issue #281: Use extracted helper for Redis connection
    redis_client = _connect_to_redis()
    if redis_client is None:
        return False

    # Issue #281: Use extracted helper for clearing existing indexes
    _clear_existing_indexes(redis_client)

    # Issue #281: Use extracted helper for scanning fact keys
    all_fact_keys = _scan_all_fact_keys(redis_client)

    if not all_fact_keys:
        logger.warning("No facts found - nothing to index")
        return True

    # Issue #281: Use extracted helper for processing facts
    category_counts, indexed_count, skipped_count, error_count = (
        _process_facts_and_build_indexes(redis_client, all_fact_keys)
    )

    # Issue #281: Use extracted helper for reporting results
    elapsed = time.perf_counter() - start_time
    _report_and_verify_results(
        redis_client, all_fact_keys, category_counts,
        indexed_count, skipped_count, error_count, elapsed
    )

    return True


def main():
    """Main entry point."""
    try:
        success = asyncio.run(migrate_category_indexes())
        return 0 if success else 1
    except KeyboardInterrupt:
        logger.warning("Migration interrupted by user")
        return 1
    except Exception as e:
        logger.error("Migration failed: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
