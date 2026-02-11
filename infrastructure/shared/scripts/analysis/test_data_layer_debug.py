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

logger = logging.getLogger(__name__)

import aioredis
import redis
import logging


def test_redis_basic():
    """Test basic Redis connectivity to all databases"""
    logger.info("=== REDIS BASIC CONNECTIVITY TEST ===")

    try:
        # Test direct connection
        client = redis.Redis(
            host="localhost", port=6379, decode_responses=True, socket_timeout=2
        )
        response = client.ping()
        logger.info("✅ Basic Redis connection: %s", response)

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
                    logger.info("✅ DB {db_num}: %s keys", key_count)
                    # Show sample keys
                    keys = db_client.keys("*")[:5]
                    for key in keys:
                        key_type = db_client.type(key)
                        logger.info("    - {key} (%s)", key_type)
                else:
                    logger.info("⚪ DB %s: empty", db_num)
            except Exception as e:
                logger.error("❌ DB {db_num}: %s", e)

    except Exception as e:
        logger.error("❌ Redis connection failed: %s", e)
        logger.info(traceback.format_exc())


def test_vector_database():
    """Test vector database in Redis DB 8"""
    logger.info("\n=== VECTOR DATABASE TEST (Redis DB 8) ===")

    try:
        client = redis.Redis(
            host="localhost", port=6379, db=8, decode_responses=False, socket_timeout=2
        )

        # Check for LlamaIndex keys
        keys = client.keys("llama_index:*")
        logger.info("LlamaIndex keys found: %s", len(keys))

        # Check for FT indexes
        try:
            indexes = client.execute_command("FT._LIST")
            logger.info("RedisSearch indexes: %s", indexes)

            # Get index info if any exist
            for index_name in indexes:
                try:
                    info = client.execute_command("FT.INFO", index_name)
                    logger.info("Index {index_name} info: %s", info)
                except Exception as e:
                    logger.info("Could not get info for index {index_name}: %s", e)

        except Exception as e:
            logger.info("No RedisSearch indexes found: %s", e)

        # Check for any vector-like keys
        all_keys = client.keys("*")
        logger.info("Total keys in DB 8: %s", len(all_keys))
        for key in all_keys[:10]:  # Show first 10
            key_type = client.type(key)
            logger.info("    - {key} (%s)", key_type)

    except Exception as e:
        logger.error("❌ Vector database test failed: %s", e)
        logger.info(traceback.format_exc())


def test_sqlite_databases():
    """Test SQLite database files"""
    logger.info("\n=== SQLITE DATABASES TEST ===")

    data_dir = Path("data")
    if not data_dir.exists():
        logger.error("❌ Data directory doesn't exist")
        return

    sqlite_files = list(data_dir.glob("*.db"))
    logger.info("Found %s SQLite files:", len(sqlite_files))

    for db_file in sqlite_files:
        logger.info("\n--- %s ---", db_file.name)
        try:
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()

            # Get tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()

            logger.info("Tables: %s", [t[0] for t in tables])

            # Get row counts for each table
            for (table_name,) in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    logger.info("  {table_name}: %s rows", count)
                except Exception as e:
                    logger.error("  {table_name}: Error counting - %s", e)

            conn.close()

        except Exception as e:
            logger.error("❌ Error reading {db_file}: %s", e)


def _inspect_sqlite_file(file: Path) -> None:
    """Inspect a SQLite file and print tables (Issue #315: extracted helper)."""
    try:
        conn = sqlite3.connect(str(file))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        logger.info("    SQLite tables: %s", [t[0] for t in tables])
        conn.close()
    except Exception as e:
        logger.error("    SQLite error: %s", e)


def _process_chromadb_file(file: Path, chroma_path: Path) -> None:
    """Process a single ChromaDB file (Issue #315: extracted helper)."""
    size_mb = file.stat().st_size / 1024 / 1024
    logger.info("  %s: %.1f MB", file.relative_to(chroma_path), size_mb)

    if file.name.endswith(".sqlite3"):
        _inspect_sqlite_file(file)


def test_chromadb():
    """Test ChromaDB files (Issue #315: refactored)."""
    logger.info("\n=== CHROMADB TEST ===")

    chromadb_dirs = ["data/chromadb", "data/chromadb_kb"]

    for chroma_dir in chromadb_dirs:
        path = Path(chroma_dir)
        if not path.exists():
            logger.info("⚪ %s doesn't exist", chroma_dir)
            continue

        logger.info("\n--- %s ---", chroma_dir)
        files = list(path.rglob("*"))
        for file in files:
            if file.is_file():
                _process_chromadb_file(file, path)


def test_backend_errors():
    """Test for backend configuration errors"""
    logger.info("\n=== BACKEND CONFIGURATION TEST ===")

    try:
        # Test Redis database manager import
        import sys

        sys.path.append("/home/kali/Desktop/AutoBot")

        from utils.redis_database_manager import RedisDatabaseManager

        manager = RedisDatabaseManager()
        logger.info("✅ RedisDatabaseManager imported successfully")

        # Test database validation
        validation = manager.validate_database_separation()
        logger.error("Database separation validation: %s", '✅' if validation else '❌')

        # Test connections
        try:
            manager.get_connection("main")
            logger.info("✅ Main connection works")
        except Exception as e:
            logger.error("❌ Main connection failed: %s", e)

        try:
            manager.get_connection("vectors")
            logger.info("✅ Vectors connection works")
        except Exception as e:
            logger.error("❌ Vectors connection failed: %s", e)

        # Show database mapping
        db_info = manager.get_database_info()
        logger.info("\nDatabase mapping:")
        for name, config in db_info.items():
            logger.info("  {name}: DB {config.get('db')} - %s", config.get('description'))

    except Exception as e:
        logger.error("❌ Backend configuration test failed: %s", e)
        logger.info(traceback.format_exc())


async def test_async_redis():
    """Test async Redis connections"""
    logger.info("\n=== ASYNC REDIS TEST ===")

    try:
        # Test async connection
        redis_client = aioredis.from_url(
            "redis://localhost:6379/0", decode_responses=True
        )
        result = await redis_client.ping()
        logger.info("✅ Async Redis ping: %s", result)

        # Test different databases async
        for db_num in [0, 1, 8]:
            try:
                db_client = aioredis.from_url(
                    f"redis://localhost:6379/{db_num}", decode_responses=True
                )
                key_count = await db_client.dbsize()
                logger.info("✅ Async DB {db_num}: %s keys", key_count)
                await db_client.close()
            except Exception as e:
                logger.error("❌ Async DB {db_num}: %s", e)

        await redis_client.close()

    except Exception as e:
        logger.error("❌ Async Redis test failed: %s", e)
        logger.info(traceback.format_exc())


def test_environment_variables():
    """Test environment variables affecting database connections"""
    logger.info("\n=== ENVIRONMENT VARIABLES TEST ===")

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
            logger.info("✅ {var}=%s", value)
        else:
            logger.info("⚪ %s not set", var)

    # Check docker environment detection
    if os.path.exists("/.dockerenv"):
        logger.info("🐳 Running inside Docker container")
    else:
        logger.info("🖥️ Running on host system")


def main():
    """Run all diagnostic tests"""
    logger.info("AutoBot Data Layer Diagnostic Report")
    logger.info("=" * 50)

    test_redis_basic()
    test_vector_database()
    test_sqlite_databases()
    test_chromadb()
    test_backend_errors()
    test_environment_variables()

    # Run async tests
    asyncio.run(test_async_redis())

    logger.info("\n" + "=" * 50)
    logger.info("DIAGNOSIS COMPLETE")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
