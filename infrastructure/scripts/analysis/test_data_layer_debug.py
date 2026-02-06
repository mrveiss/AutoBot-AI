#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Data Layer Diagnostic Tool
Analyzes all database connections, data locations, and accessibility issues
"""
import asyncio
import os
import sqlite3
import traceback
from pathlib import Path

import aioredis
import redis


def test_redis_basic():
    """Test basic Redis connectivity to all databases"""
    print("=== REDIS BASIC CONNECTIVITY TEST ===")

    try:
        # Test direct connection
        client = redis.Redis(
            host="localhost", port=6379, decode_responses=True, socket_timeout=2
        )
        response = client.ping()
        print(f"✅ Basic Redis connection: {response}")

        # Check all 16 databases
        for db_num in range(16):
            try:
                db_client = redis.Redis(
                    host="localhost",
                    port=6379,
                    db=db_num,
                    decode_responses=True,
                    socket_timeout=2,
                )
                key_count = db_client.dbsize()
                if key_count > 0:
                    print(f"✅ DB {db_num}: {key_count} keys")
                    # Show sample keys
                    keys = db_client.keys("*")[:5]
                    for key in keys:
                        key_type = db_client.type(key)
                        print(f"    - {key} ({key_type})")
                else:
                    print(f"⚪ DB {db_num}: empty")
            except Exception as e:
                print(f"❌ DB {db_num}: {e}")

    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print(traceback.format_exc())


def test_vector_database():
    """Test vector database in Redis DB 8"""
    print("\n=== VECTOR DATABASE TEST (Redis DB 8) ===")

    try:
        client = redis.Redis(
            host="localhost", port=6379, db=8, decode_responses=False, socket_timeout=2
        )

        # Check for LlamaIndex keys
        keys = client.keys("llama_index:*")
        print(f"LlamaIndex keys found: {len(keys)}")

        # Check for FT indexes
        try:
            indexes = client.execute_command("FT._LIST")
            print(f"RedisSearch indexes: {indexes}")

            # Get index info if any exist
            for index_name in indexes:
                try:
                    info = client.execute_command("FT.INFO", index_name)
                    print(f"Index {index_name} info: {info}")
                except Exception as e:
                    print(f"Could not get info for index {index_name}: {e}")

        except Exception as e:
            print(f"No RedisSearch indexes found: {e}")

        # Check for any vector-like keys
        all_keys = client.keys("*")
        print(f"Total keys in DB 8: {len(all_keys)}")
        for key in all_keys[:10]:  # Show first 10
            key_type = client.type(key)
            print(f"    - {key} ({key_type})")

    except Exception as e:
        print(f"❌ Vector database test failed: {e}")
        print(traceback.format_exc())


def test_sqlite_databases():
    """Test SQLite database files"""
    print("\n=== SQLITE DATABASES TEST ===")

    data_dir = Path("data")
    if not data_dir.exists():
        print("❌ Data directory doesn't exist")
        return

    sqlite_files = list(data_dir.glob("*.db"))
    print(f"Found {len(sqlite_files)} SQLite files:")

    for db_file in sqlite_files:
        print(f"\n--- {db_file.name} ---")
        try:
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()

            # Get tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()

            print(f"Tables: {[t[0] for t in tables]}")

            # Get row counts for each table
            for (table_name,) in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    print(f"  {table_name}: {count} rows")
                except Exception as e:
                    print(f"  {table_name}: Error counting - {e}")

            conn.close()

        except Exception as e:
            print(f"❌ Error reading {db_file}: {e}")


def _inspect_sqlite_file(file: Path) -> None:
    """Inspect a SQLite file and print tables (Issue #315: extracted helper)."""
    try:
        conn = sqlite3.connect(str(file))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"    SQLite tables: {[t[0] for t in tables]}")
        conn.close()
    except Exception as e:
        print(f"    SQLite error: {e}")


def _process_chromadb_file(file: Path, chroma_path: Path) -> None:
    """Process a single ChromaDB file (Issue #315: extracted helper)."""
    size_mb = file.stat().st_size / 1024 / 1024
    print(f"  {file.relative_to(chroma_path)}: {size_mb:.1f} MB")

    if file.name.endswith(".sqlite3"):
        _inspect_sqlite_file(file)


def test_chromadb():
    """Test ChromaDB files (Issue #315: refactored)."""
    print("\n=== CHROMADB TEST ===")

    chromadb_dirs = ["data/chromadb", "data/chromadb_kb"]

    for chroma_dir in chromadb_dirs:
        path = Path(chroma_dir)
        if not path.exists():
            print(f"⚪ {chroma_dir} doesn't exist")
            continue

        print(f"\n--- {chroma_dir} ---")
        files = list(path.rglob("*"))
        for file in files:
            if file.is_file():
                _process_chromadb_file(file, path)


def test_backend_errors():
    """Test for backend configuration errors"""
    print("\n=== BACKEND CONFIGURATION TEST ===")

    try:
        # Test Redis database manager import
        import sys

        sys.path.append("/home/kali/Desktop/AutoBot")

        from src.utils.redis_database_manager import RedisDatabaseManager

        manager = RedisDatabaseManager()
        print("✅ RedisDatabaseManager imported successfully")

        # Test database validation
        validation = manager.validate_database_separation()
        print(f"Database separation validation: {'✅' if validation else '❌'}")

        # Test connections
        try:
            manager.get_connection("main")
            print("✅ Main connection works")
        except Exception as e:
            print(f"❌ Main connection failed: {e}")

        try:
            manager.get_connection("vectors")
            print("✅ Vectors connection works")
        except Exception as e:
            print(f"❌ Vectors connection failed: {e}")

        # Show database mapping
        db_info = manager.get_database_info()
        print("\nDatabase mapping:")
        for name, config in db_info.items():
            print(f"  {name}: DB {config.get('db')} - {config.get('description')}")

    except Exception as e:
        print(f"❌ Backend configuration test failed: {e}")
        print(traceback.format_exc())


async def test_async_redis():
    """Test async Redis connections"""
    print("\n=== ASYNC REDIS TEST ===")

    try:
        # Test async connection
        redis_client = aioredis.from_url(
            "redis://localhost:6379/0", decode_responses=True
        )
        result = await redis_client.ping()
        print(f"✅ Async Redis ping: {result}")

        # Test different databases async
        for db_num in [0, 1, 8]:
            try:
                db_client = aioredis.from_url(
                    f"redis://localhost:6379/{db_num}", decode_responses=True
                )
                key_count = await db_client.dbsize()
                print(f"✅ Async DB {db_num}: {key_count} keys")
                await db_client.close()
            except Exception as e:
                print(f"❌ Async DB {db_num}: {e}")

        await redis_client.close()

    except Exception as e:
        print(f"❌ Async Redis test failed: {e}")
        print(traceback.format_exc())


def test_environment_variables():
    """Test environment variables affecting database connections"""
    print("\n=== ENVIRONMENT VARIABLES TEST ===")

    redis_env_vars = [
        "AUTOBOT_REDIS_HOST",
        "AUTOBOT_REDIS_PORT",
        "AUTOBOT_REDIS_PASSWORD",
        "AUTOBOT_REDIS_DB_MAIN",
        "AUTOBOT_REDIS_DB_VECTORS",
        "AUTOBOT_REDIS_DB_KNOWLEDGE",
    ]

    for var in redis_env_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}={value}")
        else:
            print(f"⚪ {var} not set")

    # Check docker environment detection
    if os.path.exists("/.dockerenv"):
        print("🐳 Running inside Docker container")
    else:
        print("🖥️ Running on host system")


def main():
    """Run all diagnostic tests"""
    print("AutoBot Data Layer Diagnostic Report")
    print("=" * 50)

    test_redis_basic()
    test_vector_database()
    test_sqlite_databases()
    test_chromadb()
    test_backend_errors()
    test_environment_variables()

    # Run async tests
    asyncio.run(test_async_redis())

    print("\n" + "=" * 50)
    print("DIAGNOSIS COMPLETE")


if __name__ == "__main__":
    main()
