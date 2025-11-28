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


async def migrate_category_indexes():
    """Create category indexes for all existing facts."""
    logger.info("=" * 60)
    logger.info("Category Index Migration - Issue #258")
    logger.info("=" * 60)

    start_time = time.perf_counter()

    # Get Redis connection parameters from environment
    redis_host = os.getenv("AUTOBOT_REDIS_HOST", "172.16.168.23")
    redis_port = int(os.getenv("AUTOBOT_REDIS_PORT", "6379"))
    redis_password = os.getenv("REDIS_PASSWORD") or os.getenv("AUTOBOT_REDIS_PASSWORD")
    redis_db = int(os.getenv("AUTOBOT_REDIS_DB_KNOWLEDGE", "1"))

    logger.info(f"Connecting to Redis at {redis_host}:{redis_port} (db={redis_db})")

    # Create Redis client directly
    try:
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=redis_db,
            decode_responses=False,  # We'll decode manually
        )
        # Test connection
        redis_client.ping()
        logger.info("Connected to Redis successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return False

    # Check for existing indexes
    existing_indexes = redis_client.keys("category:index:*")
    if existing_indexes:
        logger.info(f"Found {len(existing_indexes)} existing category indexes")
        for idx_key in existing_indexes:
            count = redis_client.scard(idx_key)
            logger.info(f"  - {idx_key.decode() if isinstance(idx_key, bytes) else idx_key}: {count} facts")

        # Ask to delete existing indexes
        logger.info("\nClearing existing indexes to rebuild...")
        for idx_key in existing_indexes:
            redis_client.delete(idx_key)
        logger.info("Existing indexes cleared")

    # Step 1: Scan all fact keys
    logger.info("\nStep 1: Scanning all fact keys...")
    all_fact_keys = []
    cursor = 0
    while True:
        cursor, keys = redis_client.scan(cursor, match="fact:*", count=1000)
        all_fact_keys.extend(keys)
        if cursor == 0:
            break

    logger.info(f"Found {len(all_fact_keys)} facts to index")

    if not all_fact_keys:
        logger.warning("No facts found - nothing to index")
        return True

    # Step 2: Batch fetch metadata and build indexes
    logger.info("\nStep 2: Fetching metadata and building indexes...")

    category_counts = {}
    indexed_count = 0
    skipped_count = 0
    error_count = 0

    # Process in chunks
    chunk_size = 500
    for i in range(0, len(all_fact_keys), chunk_size):
        chunk_keys = all_fact_keys[i : i + chunk_size]

        # Pipeline fetch metadata
        pipeline = redis_client.pipeline()
        for key in chunk_keys:
            pipeline.hget(key, "metadata")
        metadata_results = pipeline.execute()

        # Process each fact
        for fact_key, metadata_raw in zip(chunk_keys, metadata_results):
            try:
                if not metadata_raw:
                    skipped_count += 1
                    continue

                # Parse metadata
                metadata_str = (
                    metadata_raw.decode("utf-8")
                    if isinstance(metadata_raw, bytes)
                    else str(metadata_raw)
                )
                metadata = json.loads(metadata_str)

                # Extract fact ID from key (fact:{uuid})
                fact_key_str = (
                    fact_key.decode("utf-8")
                    if isinstance(fact_key, bytes)
                    else str(fact_key)
                )
                fact_id = fact_key_str.replace("fact:", "")

                # Get source and map to main category
                source = metadata.get("source", "")
                if not source:
                    skipped_count += 1
                    continue

                main_category = get_category_for_source(source)
                if hasattr(main_category, "value"):
                    main_category = main_category.value

                # Add to category index
                index_key = f"category:index:{main_category}"
                redis_client.sadd(index_key, fact_id)

                # Track counts
                category_counts[main_category] = category_counts.get(main_category, 0) + 1
                indexed_count += 1

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"Error processing {fact_key}: {e}")
                error_count += 1
                continue

        # Progress update
        progress = min(i + chunk_size, len(all_fact_keys))
        logger.info(f"  Processed {progress}/{len(all_fact_keys)} facts...")

    # Step 3: Report results
    elapsed = time.perf_counter() - start_time
    logger.info("\n" + "=" * 60)
    logger.info("Migration Complete!")
    logger.info("=" * 60)
    logger.info(f"Total facts scanned: {len(all_fact_keys)}")
    logger.info(f"Facts indexed: {indexed_count}")
    logger.info(f"Facts skipped (no source): {skipped_count}")
    logger.info(f"Errors: {error_count}")
    logger.info(f"Time elapsed: {elapsed:.2f}s")
    logger.info("\nCategory index counts:")
    for cat, count in sorted(category_counts.items()):
        logger.info(f"  - {cat}: {count} facts")

    # Verify indexes
    logger.info("\nVerifying indexes...")
    for cat in category_counts:
        index_key = f"category:index:{cat}"
        actual_count = redis_client.scard(index_key)
        expected_count = category_counts[cat]
        status = "✅" if actual_count == expected_count else "❌"
        logger.info(f"  {status} {index_key}: {actual_count} (expected {expected_count})")

    logger.info("\n" + "=" * 60)
    logger.info("Category indexes created successfully!")
    logger.info("The get_facts_by_category endpoint will now use O(1) lookups.")
    logger.info("=" * 60)

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
        logger.error(f"Migration failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
