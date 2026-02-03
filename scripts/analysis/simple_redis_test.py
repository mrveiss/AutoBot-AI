#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Simple Redis hash test
"""

import redis


def simple_redis_test():
    client = redis.Redis(host='localhost', port=6379, db=2, decode_responses=True)

    # Get first key directly from FT.SEARCH
    result = client.execute_command('FT.SEARCH', 'llama_index', '*', 'LIMIT', '0', '1')

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
