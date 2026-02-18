#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analyze what's stored in Redis database 0 to understand the full scope
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Tuple

import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Issue #338: Key pattern dispatch table for categorization
KEY_PATTERN_PREFIXES = [
    ("llama_index/vector", "llama_index/vector"),
    ("llama_index", "llama_index/other"),
    ("fact:", "fact"),
    ("chat:", "chat"),
    ("session:", "session"),
    ("config:", "config"),
    ("cache:", "cache"),
]


def _categorize_key(key_str: str) -> str:
    """Categorize a Redis key by pattern (Issue #338 - extracted helper)."""
    for prefix, category in KEY_PATTERN_PREFIXES:
        if key_str.startswith(prefix):
            return category
    return "other"


def _decode_bytes(data: Any) -> str:
    """Decode bytes to string (Issue #338 - extracted helper)."""
    return data.decode("utf-8") if isinstance(data, bytes) else str(data)


def _scan_keys(
    client: redis.Redis, max_scan: int = 10000
) -> Tuple[Dict[str, int], Dict[str, List[str]], int]:
    """Scan and categorize Redis keys (Issue #338 - extracted helper)."""
    key_patterns: Dict[str, int] = defaultdict(int)
    key_samples: Dict[str, List[str]] = defaultdict(list)
    cursor = 0
    total_keys = 0

    while total_keys < max_scan:
        cursor, keys = client.scan(cursor, count=100)
        for key in keys:
            total_keys += 1
            try:
                key_str = _decode_bytes(key)
                pattern = _categorize_key(key_str)
                key_patterns[pattern] += 1
                if len(key_samples[pattern]) < 3:
                    key_samples[pattern].append(key_str)
            except Exception:
                key_patterns["decode_error"] += 1

        if cursor == 0:
            break

    return dict(key_patterns), dict(key_samples), total_keys


def _analyze_search_indices(client: redis.Redis) -> None:
    """Analyze Redis search indices (Issue #338 - extracted helper)."""
    logger.info("\n=== REDIS SEARCH INDICES ===")
    try:
        indices = client.execute_command("FT._LIST")
        logger.info("Search indices found: %s", indices)
        for index in indices:
            _analyze_single_index(client, index)
    except Exception as e:
        logger.warning("Could not list FT indices: %s", e)


def _analyze_single_index(client: redis.Redis, index: Any) -> None:
    """Analyze a single search index (Issue #338 - extracted helper)."""
    try:
        index_name = _decode_bytes(index)
        ft_info = client.execute_command("FT.INFO", index_name)
        num_docs = _extract_num_docs(ft_info)
        logger.info("  Index '%s': %s documents", index_name, num_docs)
    except Exception as e:
        logger.warning("  Could not analyze index %s: %s", index, e)


def _extract_num_docs(ft_info: List) -> int:
    """Extract num_docs from FT.INFO response (Issue #338 - extracted helper)."""
    for i in range(len(ft_info)):
        if ft_info[i] == b"num_docs" or ft_info[i] == "num_docs":
            return ft_info[i + 1]
    return 0


def _analyze_hash_key(client: redis.Redis, sample_key: str) -> None:
    """Analyze a hash key (Issue #338 - extracted helper)."""
    hash_data = client.hgetall(sample_key)
    hash_fields = []
    for field, value in hash_data.items():
        field_str = _decode_bytes(field)
        value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
        hash_fields.append(f"{field_str}: {value_str}")
    logger.info("    Hash fields: %s", hash_fields[:3])


def _analyze_string_key(client: redis.Redis, sample_key: str) -> None:
    """Analyze a string key (Issue #338 - extracted helper)."""
    value = client.get(sample_key)
    value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
    logger.info("    Value: %s", value_str)


def _analyze_sample_key(client: redis.Redis, sample_key: str) -> None:
    """Analyze a single sample key (Issue #338 - extracted helper)."""
    try:
        key_type = client.type(sample_key)
        key_type_str = _decode_bytes(key_type)
        logger.info("  Key: %s (type: %s)", sample_key, key_type_str)

        if key_type_str == "hash":
            _analyze_hash_key(client, sample_key)
        elif key_type_str == "string":
            _analyze_string_key(client, sample_key)
    except Exception as e:
        logger.warning("    Could not analyze key %s: %s", sample_key, e)


def _log_sample_data(client: redis.Redis, key_samples: Dict[str, List[str]]) -> None:
    """Log sample non-vector data (Issue #338 - extracted helper)."""
    logger.info("\n=== SAMPLE NON-VECTOR DATA ===")
    for pattern, samples in key_samples.items():
        if pattern != "llama_index/vector" and samples:
            logger.info("\nPattern: %s", pattern)
            for sample_key in samples[:2]:
                _analyze_sample_key(client, sample_key)


def _log_impact_assessment(key_patterns: Dict[str, int]) -> None:
    """Log impact assessment (Issue #338 - extracted helper)."""
    logger.info("\n=== IMPACT ASSESSMENT ===")
    vector_keys = key_patterns.get("llama_index/vector", 0)
    total_other_keys = sum(
        count
        for pattern, count in key_patterns.items()
        if pattern != "llama_index/vector"
    )

    logger.info(f"Vector keys: {vector_keys:,}")
    logger.info(f"Non-vector keys: {total_other_keys:,}")

    if total_other_keys == 0:
        logger.info("✅ Database 0 appears to be EXCLUSIVELY for vectors")
        logger.info("💥 DROPPING DB 0 = Complete knowledge base data loss")
    elif total_other_keys < vector_keys * 0.1:
        logger.info("⚠️ Database 0 is PRIMARILY vectors with minimal other data")
        logger.info("💥 DROPPING DB 0 = Mostly knowledge base loss + some other data")
    else:
        logger.info(
            "🔄 Database 0 contains MIXED data - vectors + significant other data"
        )
        logger.info("💥 DROPPING DB 0 = Knowledge base + other system data loss")


def analyze_redis_db0():
    """Analyze what's in Redis database 0"""
    # Issue #338: Refactored to use extracted helpers, reducing depth from 11 to 2
    try:
        client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=False)

        logger.info("=== ANALYZING REDIS DATABASE 0 ===")

        # Get overall info
        info = client.info()
        logger.info("Database 0 Keys: %s", info.get("db0", {}).get("keys", "No data"))
        logger.info("Total Memory Used: %s", info.get("used_memory_human", "Unknown"))

        # Analyze key patterns using helper
        logger.info("\n=== KEY PATTERN ANALYSIS ===")
        key_patterns, key_samples, total_keys = _scan_keys(client)

        logger.info("Total keys scanned: %s", total_keys)
        logger.info("\nKey patterns found:")
        for pattern, count in sorted(
            key_patterns.items(), key=lambda x: x[1], reverse=True
        ):
            logger.info(f"  {pattern}: {count:,} keys")
            if pattern in key_samples and key_samples[pattern]:
                logger.info("    Samples: %s", key_samples[pattern])

        # Check FT indices using helper
        _analyze_search_indices(client)

        # Sample non-vector data using helper
        _log_sample_data(client, key_samples)

        # Impact assessment using helper
        _log_impact_assessment(key_patterns)

    except Exception as e:
        logger.error("Analysis failed: %s", e)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    analyze_redis_db0()
