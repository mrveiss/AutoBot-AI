# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Storage utilities for codebase analytics (Redis and ChromaDB)
"""

import logging
import re
from pathlib import Path

from src.utils.chromadb_client import get_chromadb_client

logger = logging.getLogger(__name__)


async def get_redis_connection():
    """
    Get Redis connection for codebase analytics using canonical utility

    This follows CLAUDE.md "🔴 REDIS CLIENT USAGE" policy.
    Uses DB 11 (analytics) for codebase indexing and analysis.
    """
    # Use canonical Redis utility instead of direct instantiation
    from src.utils.redis_client import get_redis_client

    redis_client = get_redis_client(database="analytics")
    if redis_client is None:
        logger.warning(
            "Redis client initialization returned None, using in-memory storage"
        )
        return None

    return redis_client


def get_code_collection():
    """Get ChromaDB client and autobot_code collection"""
    try:
        # Get project root
        project_root = Path(__file__).parent.parent.parent.parent
        chroma_path = project_root / "data" / "chromadb"

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
        logger.error(f"ChromaDB connection failed: {e}")
        return None


class InMemoryStorage:
    """In-memory storage fallback when Redis is unavailable"""

    def __init__(self):
        self.data = {}

    def set(self, key: str, value: str):
        self.data[key] = value

    def get(self, key: str):
        return self.data.get(key)

    def hset(self, key: str, mapping: dict):
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)

    def hgetall(self, key: str):
        return self.data.get(key, {})

    def sadd(self, key: str, value: str):
        if key not in self.data:
            self.data[key] = set()
        self.data[key].add(value)

    def smembers(self, key: str):
        return self.data.get(key, set())

    def scan_iter(self, match: str):
        pattern = match.replace("*", ".*")
        for key in self.data.keys():
            if re.match(pattern, key):
                yield key

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
        return len(keys)

    def exists(self, key: str):
        return key in self.data
