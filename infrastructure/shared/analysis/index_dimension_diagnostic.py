#!/usr/bin/env python3
"""
Fix Redis index dimensions to match existing vector data
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

# Redis FT.CREATE command for llama_index with 384-dim vectors
LLAMA_INDEX_CREATE_COMMAND = [
    "FT.CREATE", "llama_index",
    "ON", "HASH",
    "PREFIX", "1", "llama_index/vector_",
    "SCHEMA",
    "id", "TEXT",
    "doc_id", "TEXT",
    "text", "TEXT",
    "vector", "VECTOR", "HNSW", "6",
    "TYPE", "FLOAT32",
    "DIM", "384",
    "DISTANCE_METRIC", "COSINE",
]


def _log_index_info(redis_client, label, fields):
    """Log selected fields from FT.INFO output.

    Helper for main (#825).
    """
    try:
        info = redis_client.execute_command("FT.INFO", "llama_index")
        logger.info(f"📊 {label}:")
        for i in range(0, len(info), 2):
            if info[i] in fields:
                logger.info(f"  {info[i]}: {info[i+1]}")
    except Exception as e:
        logger.info(f"ℹ️ Could not get index info: {e}")


def _drop_existing_index(redis_client):
    """Drop existing llama_index if present.

    Helper for main (#825).
    """
    logger.info("🗑️ Dropping existing index...")
    try:
        redis_client.execute_command("FT.DROPINDEX", "llama_index")
        logger.info("✅ Index dropped successfully")
    except Exception as e:
        logger.info(f"ℹ️ Could not drop index (might not exist): {e}")


def _create_new_index(redis_client):
    """Create new llama_index with 384 dimensions.

    Helper for main (#825).

    Returns:
        True on success, False on failure.
    """
    logger.info("🔨 Creating new index with 384 dimensions...")
    try:
        result = redis_client.execute_command(
            *LLAMA_INDEX_CREATE_COMMAND
        )
        logger.info(f"✅ Index created successfully: {result}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create index: {e}")
        return False


async def main():
    """Fix Redis index dimensions to match existing vector data."""
    try:
        logger.info(
            "🔧 Fixing Redis index dimensions to match "
            "existing vectors..."
        )

        redis_client = get_redis_client(
            database="knowledge", async_client=False
        )
        logger.info(f"✅ Connected to Redis: {redis_client.ping()}")

        _log_index_info(
            redis_client, "Current index info", ["num_docs", "dim"]
        )
        _drop_existing_index(redis_client)

        if not _create_new_index(redis_client):
            return

        await asyncio.sleep(2)

        _log_index_info(
            redis_client, "New index info",
            ["num_docs", "dim", "percent_indexed"],
        )

        vector_count = len(redis_client.keys("llama_index/vector_*"))
        logger.info(f"📦 Total vectors in Redis: {vector_count}")

        logger.info("✅ Index dimension fix completed!")
        logger.info(
            "⏳ Note: It may take a few minutes for all vectors "
            "to be indexed."
        )

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
