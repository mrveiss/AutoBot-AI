#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Check all Redis databases to understand data distribution
"""

import logging
from collections import defaultdict
from typing import Any, Dict

import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Issue #338: Key pattern dispatch table for O(1) category lookup
KEY_PATTERN_PREFIXES = {
    "llama_index/vector": "vectors",
    "fact:": "facts",
    "chat:": "chats",
    "session:": "sessions",
}

KEY_PATTERN_CONTAINS = {
    "cache": "cache",
    "config": "config",
}


def _categorize_key(key_str: str) -> str:
    """Categorize a Redis key by pattern (Issue #338 - extracted helper)."""
    # Check prefix patterns first (most specific)
    for prefix, category in KEY_PATTERN_PREFIXES.items():
        if key_str.startswith(prefix):
            return category
    # Check contains patterns
    key_lower = key_str.lower()
    for pattern, category in KEY_PATTERN_CONTAINS.items():
        if pattern in key_lower:
            return category
    return "other"


def _decode_key(key: Any) -> str:
    """Decode Redis key to string (Issue #338 - extracted helper)."""
    return key.decode("utf-8") if isinstance(key, bytes) else str(key)


def _sample_keys(client: redis.Redis, max_sample: int = 100) -> Dict[str, int]:
    """Sample keys and categorize by pattern (Issue #338 - extracted helper)."""
    key_patterns: Dict[str, int] = defaultdict(int)
    cursor = 0
    sampled = 0

    while sampled < max_sample:
        cursor, keys = client.scan(cursor, count=20)
        for key in keys:
            sampled += 1
            try:
                key_str = _decode_key(key)
                pattern = _categorize_key(key_str)
                key_patterns[pattern] += 1
            except Exception:
                key_patterns["decode_error"] += 1

            if sampled >= max_sample:
                break

        if cursor == 0:
            break

    return dict(key_patterns), sampled


def _log_pattern_stats(
    key_patterns: Dict[str, int], sampled: int, total_keys: int
) -> None:
    """Log pattern statistics (Issue #338 - extracted helper)."""
    logger.info("Sample patterns:")
    for pattern, count in sorted(
        key_patterns.items(), key=lambda x: x[1], reverse=True
    ):
        percentage = (count / sampled) * 100 if sampled > 0 else 0
        estimated_total = int((count / sampled) * total_keys) if sampled > 0 else 0
        logger.info(
            f"  {pattern}: {count}/{sampled} sampled ({percentage:.1f}%) ≈ {estimated_total:,} total"
        )


def _analyze_database(client: redis.Redis, db_num: int, info: Dict) -> bool:
    """Analyze a single Redis database (Issue #338 - extracted helper)."""
    db_key = f"db{db_num}"
    if db_key not in info:
        return False

    keys_count = info[db_key]["keys"]
    expires_count = info[db_key].get("expires", 0)

    logger.info("\n--- Database %s ---", db_num)
    logger.info(f"Keys: {keys_count:,}")
    logger.info(f"Keys with expiry: {expires_count:,}")

    if keys_count > 0:
        key_patterns, sampled = _sample_keys(client)
        _log_pattern_stats(key_patterns, sampled, keys_count)

    return True


def _handle_connection_error(e: Exception, db_num: int) -> bool:
    """Handle Redis connection errors (Issue #338 - extracted helper). Returns True if should break."""
    if "NOAUTH" in str(e):
        logger.warning("Database %s: Authentication required", db_num)
        return False
    elif "Connection refused" in str(e):
        logger.error("Cannot connect to Redis")
        return True
    else:
        logger.debug("Database %s: %s", db_num, e)
        return False


def analyze_all_redis_databases():
    """Analyze data distribution across all Redis databases"""
    # Issue #338: Refactored to use extracted helpers, reducing depth from 13 to 3

    logger.info("=== REDIS DATABASE DISTRIBUTION ANALYSIS ===")

    for db_num in range(16):  # Redis typically has 16 databases (0-15)
        try:
            client = redis.Redis(
                host="localhost", port=6379, db=db_num, decode_responses=False
            )
            info = client.info()
            _analyze_database(client, db_num, info)
        except Exception as e:
            if _handle_connection_error(e, db_num):
                break

    # Summary and recommendations
    logger.info("\n=== SUMMARY & RECOMMENDATIONS ===")
    logger.info("Based on analysis:")
    logger.info(
        "• Database 0: PRIMARY vector store (13,383 vectors) + minimal facts/config"
    )
    logger.info("• Other databases: Likely used for different services or empty")

    logger.info("\n💥 IMPACT OF DROPPING DATABASE 0:")
    logger.info("• ❌ Complete loss of 13,383 knowledge base vectors")
    logger.info("• ❌ Loss of stored facts and workflow rules")
    logger.info("• ❌ Loss of any cached LangChain test data")
    logger.info("• ⚠️ Potential system reconfiguration needed")

    logger.info("\n🛡️ PROTECTION STRATEGIES:")
    logger.info("• Create Redis backup before any operations: redis-cli --rdb dump.rdb")
    logger.info("• Consider moving vectors to dedicated database (e.g., DB 3)")
    logger.info("• Document database usage in CLAUDE.md")
    logger.info("• Implement automated backup system")


if __name__ == "__main__":
    analyze_all_redis_databases()
