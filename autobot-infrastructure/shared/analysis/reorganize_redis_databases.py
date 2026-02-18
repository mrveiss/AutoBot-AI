#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Reorganize Redis databases for optimal separation and search support

Current state:
- DB 0: Mix of facts, workflow rules, and other data (10 keys)
- DB 1: All 14,047 vectors (can't use Redis search here)

Target state:
- DB 0: Vectors only (enables Redis search index support)
- DB 1: Knowledge facts and metadata
- DB 2: Workflow rules and classification data
- DB 3: Other system data
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use canonical Redis client utility
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


def _connect_all_databases():
    """Connect to all 4 Redis databases.

    Helper for main (#825).

    Returns:
        Dict mapping DB index to connection.
    """
    connections = {}
    db_names = ["main", "knowledge", "cache", "sessions"]
    for db_idx, db_name in enumerate(db_names):
        connections[db_idx] = get_redis_client(async_client=False, database=db_name)
        logger.info(
            "Connected to DB%s (%s): %s",
            db_idx,
            db_name,
            connections[db_idx].ping(),
        )
    return connections


def _analyze_databases(connections):
    """Analyze current database contents.

    Helper for main (#825).
    """
    logger.info("\nCurrent database analysis:")
    for db in range(4):
        keys = connections[db].keys("*")
        logger.info("  DB%s: %s keys", db, len(keys))
        if len(keys) <= 20:
            key_examples = [
                k.decode("utf-8", errors="ignore") if isinstance(k, bytes) else str(k)
                for k in keys[:10]
            ]
            logger.info("    Examples: %s", key_examples)


def _backup_key(connections, key):
    """Backup a single key from DB0, handling all Redis data types.

    Helper for main (#825).

    Returns:
        Tuple of (data_type, data) or None on failure.
    """
    key_str = (
        key.decode("utf-8", errors="ignore") if isinstance(key, bytes) else str(key)
    )
    try:
        data_type = connections[0].type(key).decode("utf-8")
        type_handlers = {
            "hash": lambda: connections[0].hgetall(key),
            "string": lambda: connections[0].get(key),
            "list": lambda: connections[0].lrange(key, 0, -1),
            "set": lambda: connections[0].smembers(key),
            "stream": lambda: connections[0].xrange(key),
        }

        handler = type_handlers.get(data_type)
        if handler:
            data = handler()
            logger.info("  Backed up %s (%s)", key_str, data_type)
            return data_type, data

        logger.warning("Unknown type %s for key %s", data_type, key_str)
        return None
    except Exception as e:
        logger.error("Failed to backup key %s: %s", key, e)
        return None


def _backup_db0_data(connections):
    """Backup all data from DB0 before clearing it.

    Helper for main (#825).

    Returns:
        Dict mapping key to (data_type, data) tuples.
    """
    logger.error("\nBacking up critical data from DB0...")
    db0_keys = connections[0].keys("*")
    backup_data = {}

    for key in db0_keys:
        result = _backup_key(connections, key)
        if result:
            backup_data[key] = result

    return backup_data


def _move_vectors_to_db0(connections):
    """Move vectors from DB1 to DB0 in batches.

    Helper for main (#825).

    Returns:
        List of vector keys that were moved.
    """
    logger.info("\nMoving vectors from DB1 to DB0...")
    vector_keys = connections[1].keys(b"llama_index/vector_*")
    logger.info("Found %s vectors to move", len(vector_keys))

    logger.info("Clearing DB0...")
    connections[0].flushdb()

    batch_size = 100
    moved_count = 0

    for i in range(0, len(vector_keys), batch_size):
        batch = vector_keys[i : i + batch_size]

        pipe_db1 = connections[1].pipeline()
        for key in batch:
            pipe_db1.hgetall(key)
        batch_data = pipe_db1.execute()

        pipe_db0 = connections[0].pipeline()
        for key, data in zip(batch, batch_data):
            if data:
                pipe_db0.hset(key, mapping=data)
                moved_count += 1
        pipe_db0.execute()

        logger.info(
            "Moved batch %s: %s vectors (Total: %s)",
            i // batch_size + 1,
            len(batch),
            moved_count,
        )

    return vector_keys


def _determine_target_db(key_str):
    """Determine target database based on key pattern.

    Helper for main (#825).
    """
    if key_str.startswith("fact:") or "fact" in key_str:
        return 1  # Knowledge facts
    elif "workflow" in key_str or "classification" in key_str:
        return 2  # Workflow rules
    return 3  # Other system data


def _restore_key_to_db(connections, key, data_type, data, target_db):
    """Restore a single key to the appropriate target database.

    Helper for main (#825).
    """
    key_str = (
        key.decode("utf-8", errors="ignore") if isinstance(key, bytes) else str(key)
    )
    try:
        restore_handlers = {
            "hash": lambda: connections[target_db].hset(key, mapping=data),
            "string": lambda: connections[target_db].set(key, data),
            "list": lambda: connections[target_db].rpush(key, *data) if data else None,
            "set": lambda: connections[target_db].sadd(key, *data) if data else None,
            "stream": lambda: [
                connections[target_db].xadd(key, entry[1]) for entry in data
            ],
        }
        handler = restore_handlers.get(data_type)
        if handler:
            handler()
        logger.info("  Restored %s to DB%s (%s)", key_str, target_db, data_type)
    except Exception as e:
        logger.error("Failed to restore %s: %s", key_str, e)


def _restore_backup_data(connections, backup_data):
    """Restore non-vector data to appropriate databases.

    Helper for main (#825).
    """
    logger.info("\nRestoring non-vector data to appropriate databases...")
    for key, (data_type, data) in backup_data.items():
        key_str = (
            key.decode("utf-8", errors="ignore") if isinstance(key, bytes) else str(key)
        )
        target_db = _determine_target_db(key_str)
        _restore_key_to_db(connections, key, data_type, data, target_db)


def _create_search_index(connections):
    """Create Redis search index on DB0.

    Helper for main (#825).
    """
    logger.info("\nCreating Redis search index on DB0...")
    try:
        result = connections[0].execute_command(*SEARCH_INDEX_CREATE_COMMAND)
        logger.info("Search index created: %s", result)
    except Exception as e:
        if "Index already exists" in str(e):
            logger.info("Search index already exists")
        else:
            logger.error("Failed to create search index: %s", e)


def _verify_final_state(connections):
    """Verify final database state after reorganization.

    Helper for main (#825).
    """
    logger.info("\nFinal database state:")
    for db in range(4):
        keys = connections[db].keys("*")
        vkeys = connections[db].keys(b"llama_index/vector_*")
        logger.info(
            "  DB%s: %s total keys, %s vectors",
            db,
            len(keys),
            len(vkeys),
        )


async def _verify_search_index(connections):
    """Test the search index after reorganization.

    Helper for main (#825).
    """
    logger.info("\nTesting search index...")
    await asyncio.sleep(3)

    try:
        index_info = connections[0].execute_command("FT.INFO", "llama_index")
        for i in range(0, len(index_info), 2):
            if index_info[i].decode("utf-8") in ["num_docs", "percent_indexed"]:
                logger.info(
                    "%s: %s",
                    index_info[i].decode("utf-8"),
                    index_info[i + 1],
                )
    except Exception as e:
        logger.warning("Could not get index info: %s", e)


async def main():
    try:
        logger.info("Reorganizing Redis databases for optimal separation...")

        connections = _connect_all_databases()
        _analyze_databases(connections)

        # Step 1: Backup DB0 data
        backup_data = _backup_db0_data(connections)

        # Step 2: Move vectors from DB1 to DB0
        vector_keys = _move_vectors_to_db0(connections)

        # Step 3: Restore non-vector data to appropriate databases
        _restore_backup_data(connections, backup_data)

        # Step 4: Clean up vectors from DB1
        logger.info("\nCleaning up vectors from DB1...")
        connections[1].delete(*vector_keys)
        logger.info("Removed %s vectors from DB1", len(vector_keys))

        # Step 5: Create search index
        _create_search_index(connections)

        # Step 6: Verify
        _verify_final_state(connections)
        await _verify_search_index(connections)

        logger.info("\nDatabase reorganization completed!")
        logger.info("New structure:")
        logger.info("  - DB0: Vectors with Redis search index support")
        logger.info("  - DB1: Knowledge facts and metadata")
        logger.info("  - DB2: Workflow rules and classification data")
        logger.info("  - DB3: Other system data")

    except Exception as e:
        logger.error("Error: %s", e)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
