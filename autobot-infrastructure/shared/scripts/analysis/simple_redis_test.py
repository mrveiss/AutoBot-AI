#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Simple Redis hash test
"""

import os

import redis

# DB number from redis-databases.yaml SSOT (#2806): knowledge = 1
_DB_KNOWLEDGE = int(os.getenv("AUTOBOT_REDIS_DB_KNOWLEDGE", "1"))


def simple_redis_test():
    client = redis.Redis(host="localhost", port=6379, db=_DB_KNOWLEDGE, decode_responses=True)

    # Get first key directly from FT.SEARCH
    result = client.execute_command("FT.SEARCH", "llama_index", "*", "LIMIT", "0", "1")

    if len(result) > 1:
        key = result[1]  # First document key
        print(f"Testing key: {key}")

        # Get hash data
        hash_data = client.hgetall(key)
        print(f"Hash fields: {list(hash_data.keys())}")

        for field, value in hash_data.items():
            print(f"{field}: {str(value)[:100]}...")


if __name__ == "__main__":
    simple_redis_test()
