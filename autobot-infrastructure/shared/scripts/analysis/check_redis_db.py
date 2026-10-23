#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Check Redis databases for vector data
"""

import sys
from pathlib import Path

# Runs from any directory with no PYTHONPATH: put the repository root on the path for
# `autobot_shared` (#18289).
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from autobot_shared.redis_client import RedisDatabase, require_redis_client  # noqa: E402

# DB 0, 1 and 2 (main, knowledge, prompts), each through the canonical client (#18553).
_CHECKED_DATABASES = (RedisDatabase.MAIN, RedisDatabase.KNOWLEDGE, RedisDatabase.PROMPTS)


def check_redis_databases():
    """Report the llama_index search index and vector keys in each checked database."""
    for database in _CHECKED_DATABASES:
        db = database.value
        print(f"\n=== Checking Database {db} ===")
        try:
            _check_database(require_redis_client(database=database, decode_responses=True))
        except Exception as e:
            print(f"Database {db} error: {e}")


def _check_database(client):
    """Print the FT.INFO document count and the first vector key's fields for *client*."""
    # Try FT.INFO
    try:
        ft_info = client.execute_command("FT.INFO", "llama_index")
        num_docs = None
        for i in range(len(ft_info)):
            if ft_info[i] == "num_docs":
                num_docs = ft_info[i + 1]
                break
        print(f"FT.INFO found: {num_docs} documents")
    except Exception as e:
        print(f"FT.INFO failed: {e}")

    # Check for keys
    keys = list(client.scan_iter(match="llama_index/vector*", count=3))
    print(f"Vector keys found: {len(keys)}")

    if keys:
        # Check first key
        key = keys[0]
        hash_data = client.hgetall(key)
        print(f"First key {key} has fields: {list(hash_data.keys())}")

        if hash_data:
            # Show first few fields
            for field, value in list(hash_data.items())[:3]:
                print(f"  {field}: {str(value)[:50]}...")


if __name__ == "__main__":
    check_redis_databases()
