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

NOTE: main() function (~175 lines) is an ACCEPTABLE EXCEPTION per Issue #490 -
standalone one-time migration script with sequential operations. Low priority.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging

# Use canonical Redis client utility
from src.utils.redis_client import get_redis_client

logging.basicConfig(level=logging.INFO)


async def main():
    try:
        print("🗂️ Reorganizing Redis databases for optimal separation...")

        # Connect to all databases using canonical get_redis_client()
        connections = {}
        db_names = ["main", "knowledge", "cache", "sessions"]  # Named databases 0-3
        for db_idx, db_name in enumerate(db_names):
            connections[db_idx] = get_redis_client(async_client=False, database=db_name)
            print(
                f"✅ Connected to DB{db_idx} ({db_name}): {connections[db_idx].ping()}"
            )

        # Analysis phase - see what's where
        print("\n📊 Current database analysis:")
        for db in range(4):
            keys = connections[db].keys("*")
            print(f"  DB{db}: {len(keys)} keys")
            if len(keys) <= 20:  # Show details for small databases
                key_examples = [
                    k.decode("utf-8", errors="ignore")
                    if isinstance(k, bytes)
                    else str(k)
                    for k in keys[:10]
                ]
                print(f"    Examples: {key_examples}")

        # Step 1: Backup critical data from DB0
        print("\n💾 Backing up critical data from DB0...")
        db0_keys = connections[0].keys("*")
        backup_data = {}

        for key in db0_keys:
            try:
                key_str = (
                    key.decode("utf-8", errors="ignore")
                    if isinstance(key, bytes)
                    else str(key)
                )
                data_type = connections[0].type(key).decode("utf-8")

                if data_type == "hash":
                    backup_data[key] = ("hash", connections[0].hgetall(key))
                elif data_type == "string":
                    backup_data[key] = ("string", connections[0].get(key))
                elif data_type == "list":
                    backup_data[key] = ("list", connections[0].lrange(key, 0, -1))
                elif data_type == "set":
                    backup_data[key] = ("set", connections[0].smembers(key))
                elif data_type == "stream":
                    backup_data[key] = ("stream", connections[0].xrange(key))
                else:
                    print(f"⚠️ Unknown type {data_type} for key {key_str}")

                print(f"  📦 Backed up {key_str} ({data_type})")
            except Exception as e:
                print(f"❌ Failed to backup key {key}: {e}")

        # Step 2: Move vectors from DB1 to DB0
        print("\n🚚 Moving vectors from DB1 to DB0...")
        vector_keys = connections[1].keys(b"llama_index/vector_*")
        print(f"📦 Found {len(vector_keys)} vectors to move")

        # Clear DB0 first
        print("🧹 Clearing DB0...")
        connections[0].flushdb()

        # Move vectors in batches
        batch_size = 100
        moved_count = 0

        for i in range(0, len(vector_keys), batch_size):
            batch = vector_keys[i : i + batch_size]

            # Read batch from DB1
            pipe_db1 = connections[1].pipeline()
            for key in batch:
                pipe_db1.hgetall(key)
            batch_data = pipe_db1.execute()

            # Write batch to DB0
            pipe_db0 = connections[0].pipeline()
            for key, data in zip(batch, batch_data):
                if data:
                    pipe_db0.hset(key, mapping=data)
                    moved_count += 1
            pipe_db0.execute()

            print(
                f"✅ Moved batch {i//batch_size + 1}: {len(batch)} vectors (Total: {moved_count})"
            )

        # Step 3: Restore non-vector data to appropriate databases
        print("\n📥 Restoring non-vector data to appropriate databases...")

        for key, (data_type, data) in backup_data.items():
            key_str = (
                key.decode("utf-8", errors="ignore")
                if isinstance(key, bytes)
                else str(key)
            )

            # Determine target database based on key pattern
            if key_str.startswith("fact:") or "fact" in key_str:
                target_db = 1  # Knowledge facts
            elif "workflow" in key_str or "classification" in key_str:
                target_db = 2  # Workflow rules
            else:
                target_db = 3  # Other system data

            try:
                if data_type == "hash":
                    connections[target_db].hset(key, mapping=data)
                elif data_type == "string":
                    connections[target_db].set(key, data)
                elif data_type == "list":
                    if data:  # Only if list has items
                        connections[target_db].rpush(key, *data)
                elif data_type == "set":
                    if data:  # Only if set has items
                        connections[target_db].sadd(key, *data)
                elif data_type == "stream":
                    for stream_data in data:
                        connections[target_db].xadd(key, stream_data[1])

                print(f"  📁 Restored {key_str} to DB{target_db} ({data_type})")
            except Exception as e:
                print(f"❌ Failed to restore {key_str}: {e}")

        # Step 4: Clean up vectors from DB1
        print("\n🧹 Cleaning up vectors from DB1...")
        connections[1].delete(*vector_keys)
        print(f"✅ Removed {len(vector_keys)} vectors from DB1")

        # Step 5: Create Redis search index on DB0
        print("\n🔨 Creating Redis search index on DB0...")
        create_command = [
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

        try:
            result = connections[0].execute_command(*create_command)
            print(f"✅ Search index created: {result}")
        except Exception as e:
            if "Index already exists" in str(e):
                print("ℹ️ Search index already exists")
            else:
                print(f"❌ Failed to create search index: {e}")

        # Step 6: Final verification
        print("\n📊 Final database state:")
        for db in range(4):
            keys = connections[db].keys("*")
            vector_keys = connections[db].keys(b"llama_index/vector_*")
            print(f"  DB{db}: {len(keys)} total keys, {len(vector_keys)} vectors")

        # Test the search index
        print("\n🔍 Testing search index...")
        await asyncio.sleep(3)  # Wait for indexing

        try:
            index_info = connections[0].execute_command("FT.INFO", "llama_index")
            for i in range(0, len(index_info), 2):
                if index_info[i].decode("utf-8") in ["num_docs", "percent_indexed"]:
                    print(f"📊 {index_info[i].decode('utf-8')}: {index_info[i+1]}")
        except Exception as e:
            print(f"⚠️ Could not get index info: {e}")

        print("\n✅ Database reorganization completed!")
        print("📋 New structure:")
        print("  - DB0: Vectors with Redis search index support")
        print("  - DB1: Knowledge facts and metadata")
        print("  - DB2: Workflow rules and classification data")
        print("  - DB3: Other system data")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
