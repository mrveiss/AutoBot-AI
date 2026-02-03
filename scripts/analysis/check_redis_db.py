#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Check Redis databases for vector data
"""

import redis


def check_redis_databases():
    # Check different databases
    for db in [0, 1, 2]:
        print(f"\n=== Checking Database {db} ===")
        try:
            client = redis.Redis(host='localhost', port=6379, db=db, decode_responses=True)

            # Try FT.INFO
            try:
                ft_info = client.execute_command('FT.INFO', 'llama_index')
                num_docs = None
                for i in range(len(ft_info)):
                    if ft_info[i] == 'num_docs':
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

        except Exception as e:
            print(f"Database {db} error: {e}")


if __name__ == "__main__":
    check_redis_databases()
