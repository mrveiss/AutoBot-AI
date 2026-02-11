#!/usr/bin/env python3
"""
Migrate vectors from database 1 to database 0 to enable Redis search
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import canonical Redis client utility
from utils.redis_client import get_redis_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Search index creation command (#825)
SEARCH_INDEX_CREATE_COMMAND = [
    "FT.CREATE",
    "llama_index",
    "ON",
    "HASH",
    "PREFIX",
    "1",
    "llama_index/vector_",
    "SCHEMA",
    "id",
    "TEXT",
    "doc_id",
    "TEXT",
    "text",
    "TEXT",
    "vector",
    "VECTOR",
    "HNSW",
    "6",
    "TYPE",
    "FLOAT32",
    "DIM",
    "384",  # Match existing vector dimensions
    "DISTANCE_METRIC",
    "COSINE",
]


def _connect_databases():
    """Connect to source and target Redis databases.

    Helper for main (#825).
    """
    redis_db0 = get_redis_client(
        database="main",
        async_client=False,
    )
    redis_db1 = get_redis_client(
        database="knowledge",
        async_client=False,
    )
    logger.info("Connected to DB0: %s", redis_db0.ping())
    logger.info("Connected to DB1: %s", redis_db1.ping())
    return redis_db0, redis_db1


def _check_existing_vectors(redis_db0):
    """Check if vectors already exist in target DB and prompt user.

    Helper for main (#825).

    Returns:
        True if safe to proceed, False if user cancelled.
    """
    existing_vectors = redis_db0.keys("llama_index/vector_*")
    if existing_vectors:
        logger.warning(
            "Found %s existing vectors in database 0",
            len(existing_vectors),
        )
        response = input(
            "Do you want to proceed and potentially overwrite? (y/N): "
        )
        if response.lower() != "y":
            logger.error("Migration cancelled by user")
            return False
    return True


def _migrate_vector_batch(redis_db1, redis_db0, batch):
    """Migrate a single batch of vectors from DB1 to DB0.

    Helper for main (#825).

    Returns:
        Number of vectors migrated in this batch.
    """
    pipe_db1 = redis_db1.pipeline()
    for key in batch:
        pipe_db1.hgetall(key)
    batch_data = pipe_db1.execute()

    pipe_db0 = redis_db0.pipeline()
    migrated = 0
    for key, data in zip(batch, batch_data):
        if data:
            pipe_db0.hset(key, mapping=data)
            migrated += 1
    pipe_db0.execute()
    return migrated


def _create_search_index(redis_db0):
    """Create Redis search index on database 0.

    Helper for main (#825).
    """
    try:
        result = redis_db0.execute_command(*SEARCH_INDEX_CREATE_COMMAND)
        logger.info("Search index created successfully: %s", result)
    except Exception as e:
        logger.error("Failed to create search index: %s", e)


async def _verify_index(redis_db0):
    """Wait for indexing and verify index status.

    Helper for main (#825).
    """
    logger.info("Waiting for vectors to be indexed...")
    await asyncio.sleep(5)

    try:
        index_info = redis_db0.execute_command("FT.INFO", "llama_index")
        for i in range(0, len(index_info), 2):
            if index_info[i] in ["num_docs", "percent_indexed"]:
                logger.info("%s: %s", index_info[i], index_info[i + 1])
    except Exception as e:
        logger.warning("Could not get index info: %s", e)


async def main():
    try:
        logger.info("Migrating vectors from database 1 to database 0...")

        redis_db0, redis_db1 = _connect_databases()

        vector_keys = redis_db1.keys("llama_index/vector_*")
        logger.info("Found %s vectors in database 1", len(vector_keys))

        if len(vector_keys) == 0:
            logger.error("No vectors found in database 1!")
            return

        if not _check_existing_vectors(redis_db0):
            return

        # Migrate vectors in batches
        batch_size = 100
        migrated_count = 0

        for i in range(0, len(vector_keys), batch_size):
            batch = vector_keys[i: i + batch_size]
            batch_num = i // batch_size + 1
            logger.info("Migrating batch %s (%s vectors)...", batch_num, len(batch))
            migrated_count += _migrate_vector_batch(redis_db1, redis_db0, batch)
            logger.info("Migrated %s vectors (Total: %s)", len(batch), migrated_count)

        logger.info(
            "Migration completed! Migrated %s vectors to database 0",
            migrated_count,
        )

        # Verify migration
        db0_vectors = redis_db0.keys("llama_index/vector_*")
        logger.info("Verification: Database 0 now has %s vectors", len(db0_vectors))

        # Create search index and verify
        logger.info("Creating search index on database 0...")
        _create_search_index(redis_db0)
        await _verify_index(redis_db0)

        logger.info("Vector migration and indexing completed!")

    except Exception as e:
        logger.error("Error: %s", e)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
