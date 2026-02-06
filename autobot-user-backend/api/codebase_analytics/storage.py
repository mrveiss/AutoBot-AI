# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Storage utilities for codebase analytics (Redis and ChromaDB)

Issue #369: Added async ChromaDB operations to prevent event loop blocking.
"""

import logging
import re
from pathlib import Path

from src.utils.chromadb_client import get_async_chromadb_client, get_chromadb_client

logger = logging.getLogger(__name__)

# Module-level project root constant (Issue #380 - avoid repeated Path computation)
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


async def get_redis_connection():
    """
    Get Redis connection for codebase analytics using canonical utility.

    This follows CLAUDE.md "🔴 REDIS CLIENT USAGE" policy.
    Uses DB 11 (analytics) for codebase indexing and analysis.

    Returns a SYNC Redis client for use with asyncio.to_thread().
    For async operations, use get_redis_connection_async() instead.
    """
    # Use canonical Redis utility - returns sync client
    from src.utils.redis_client import get_redis_client

    redis_client = get_redis_client(database="analytics", async_client=False)
    if redis_client is None:
        logger.warning(
            "Redis client initialization returned None, using in-memory storage"
        )
        return None

    return redis_client


async def get_redis_connection_async():
    """
    Get async Redis connection for codebase analytics.

    This follows CLAUDE.md "🔴 REDIS CLIENT USAGE" policy.
    Uses DB 11 (analytics) for codebase indexing and analysis.

    Returns an ASYNC Redis client for native async operations.
    Use this when you want to avoid thread pool blocking.
    """
    from src.utils.redis_client import get_redis_client

    redis_client = await get_redis_client(database="analytics", async_client=True)
    if redis_client is None:
        logger.warning("Async Redis client initialization returned None")
        return None

    return redis_client


def get_code_collection():
    """Get ChromaDB client and autobot_code collection (sync version).

    Note: This function is synchronous and may block the event loop.
    For async contexts, use get_code_collection_async() instead.
    """
    try:
        # Use module-level constant
        chroma_path = _PROJECT_ROOT / "data" / "chromadb"

        # Create persistent client with telemetry disabled using shared utility
        chroma_client = get_chromadb_client(
            db_path=str(chroma_path), allow_reset=False, anonymized_telemetry=False
        )

        # Get or create the code collection
        code_collection = chroma_client.get_or_create_collection(
            name="autobot_code",
            metadata={
                "description": (
                    "Codebase analytics: functions, classes, problems, duplicates"
                )
            },
        )

        logger.info(
            f"ChromaDB autobot_code collection ready ({code_collection.count()} items)"
        )
        return code_collection

    except Exception as e:
        logger.error("ChromaDB connection failed: %s", e)
        return None


async def get_code_collection_async():
    """Get ChromaDB client and autobot_code collection (async version).

    Issue #369: Non-blocking async version that prevents event loop blocking
    in FastAPI endpoints and other async contexts.

    Returns:
        AsyncChromaCollection wrapper or None on failure
    """
    try:
        # Use module-level constant
        chroma_path = _PROJECT_ROOT / "data" / "chromadb"

        # Get async ChromaDB client
        async_client = await get_async_chromadb_client(
            db_path=str(chroma_path), allow_reset=False, anonymized_telemetry=False
        )

        # Get or create the code collection (async)
        async_collection = await async_client.get_or_create_collection(
            name="autobot_code",
            metadata={
                "description": (
                    "Codebase analytics: functions, classes, problems, duplicates"
                )
            },
        )

        # Get count asynchronously
        count = await async_collection.count()
        logger.info("ChromaDB autobot_code collection ready (%s items)", count)
        return async_collection

    except Exception as e:
        logger.error("ChromaDB async connection failed: %s", e)
        return None


class InMemoryStorage:
    """In-memory storage fallback when Redis is unavailable"""

    def __init__(self):
        """Initialize empty in-memory data store."""
        self.data = {}

    def set(self, key: str, value: str):
        """Store a string value at the given key."""
        self.data[key] = value

    def get(self, key: str):
        """Retrieve a value by key, returns None if not found."""
        return self.data.get(key)

    def hset(self, key: str, mapping: dict):
        """Set hash fields from a dictionary mapping."""
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)

    def hgetall(self, key: str):
        """Get all hash fields and values for a key."""
        return self.data.get(key, {})

    def sadd(self, key: str, value: str):
        """Add a member to a set stored at key."""
        if key not in self.data:
            self.data[key] = set()
        self.data[key].add(value)

    def smembers(self, key: str):
        """Get all members of the set stored at key."""
        return self.data.get(key, set())

    def scan_iter(self, match: str):
        """Iterate over keys matching a glob-style pattern."""
        pattern = match.replace("*", ".*")
        for key in self.data:
            if re.match(pattern, key):
                yield key

    def delete(self, *keys):
        """Delete one or more keys from storage."""
        for key in keys:
            self.data.pop(key, None)
        return len(keys)

    def exists(self, key: str):
        """Check if a key exists in storage."""
        return key in self.data
