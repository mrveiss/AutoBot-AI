#!/usr/bin/env python3
"""
Migrate vectors from database 1 to database 0 to enable Redis search
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging

logging.basicConfig(level=logging.INFO)

# Import canonical Redis client utility
from src.utils.redis_client import get_redis_client


async def main():
    try:
        print("🚚 Migrating vectors from database 1 to database 0...")

        # Connect to both databases using canonical pattern
        redis_db0 = get_redis_client(
            database="main",  # Target database (supports search indexes)
            async_client=False,
        )

        redis_db1 = get_redis_client(
            database="knowledge",  # Source database (has the vectors)
            async_client=False,
        )

        # Test connections
        print(f"✅ Connected to DB0: {redis_db0.ping()}")
        print(f"✅ Connected to DB1: {redis_db1.ping()}")

        # Get all vector keys from database 1
        vector_keys = redis_db1.keys("llama_index/vector_*")
        print(f"📦 Found {len(vector_keys)} vectors in database 1")

        if len(vector_keys) == 0:
            print("❌ No vectors found in database 1!")
            return

        # Check if any vectors already exist in database 0
        existing_vectors = redis_db0.keys("llama_index/vector_*")
        if existing_vectors:
            print(f"⚠️ Found {len(existing_vectors)} existing vectors in database 0")
            response = input(
                "Do you want to proceed and potentially overwrite? (y/N): "
            )
            if response.lower() != "y":
                print("❌ Migration cancelled by user")
                return

        # Migrate vectors in batches
        batch_size = 100
        migrated_count = 0

        for i in range(0, len(vector_keys), batch_size):
            batch = vector_keys[i : i + batch_size]
            print(f"🔄 Migrating batch {i//batch_size + 1} ({len(batch)} vectors)...")

            # Use pipeline for better performance
            pipe_db1 = redis_db1.pipeline()
            for key in batch:
                pipe_db1.hgetall(key)
            batch_data = pipe_db1.execute()

            # Write to database 0
            pipe_db0 = redis_db0.pipeline()
            for key, data in zip(batch, batch_data):
                if data:  # Only migrate if data exists
                    pipe_db0.hset(key, mapping=data)
                    migrated_count += 1
            pipe_db0.execute()

            print(f"✅ Migrated {len(batch)} vectors (Total: {migrated_count})")

        print(f"✅ Migration completed! Migrated {migrated_count} vectors to database 0")

        # Verify migration
        db0_vectors = redis_db0.keys("llama_index/vector_*")
        print(f"📊 Verification: Database 0 now has {len(db0_vectors)} vectors")

        # Now create the search index on database 0
        print("🔨 Creating search index on database 0...")
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
            result = redis_db0.execute_command(*create_command)
            print(f"✅ Search index created successfully: {result}")
        except Exception as e:
            print(f"❌ Failed to create search index: {e}")

        # Wait for indexing
        print("⏳ Waiting for vectors to be indexed...")
        await asyncio.sleep(5)

        # Check index status
        try:
            index_info = redis_db0.execute_command("FT.INFO", "llama_index")
            for i in range(0, len(index_info), 2):
                if index_info[i] in ["num_docs", "percent_indexed"]:
                    print(f"📊 {index_info[i]}: {index_info[i+1]}")
        except Exception as e:
            print(f"⚠️ Could not get index info: {e}")

        print("✅ Vector migration and indexing completed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
