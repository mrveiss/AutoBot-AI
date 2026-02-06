#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Database Migration Script for AutoBot
Migrates data from database 0 to appropriate specialized databases
"""

import logging
import os
import sys

import redis

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.utils.redis_database_manager import RedisDatabase

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class RedisMigrator:
    def __init__(self):
        """Initialize Redis migrator with connection to all databases"""
        redis_host = os.getenv("AUTOBOT_REDIS_HOST", "localhost")
        redis_port = int(os.getenv("AUTOBOT_REDIS_PORT", "6379"))

        # Connect to each database
        self.connections = {}
        for db_enum in RedisDatabase:
            try:
                client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=db_enum.value,
                    decode_responses=False,  # Keep as bytes to handle binary data
                    socket_timeout=5,
                )
                # Test connection
                client.ping()
                self.connections[db_enum.name] = client
                logger.info(
                    "Connected to Redis database %s (%s)", db_enum.value, db_enum.name
                )
            except Exception as e:
                logger.error(
                    "Failed to connect to Redis database %s: %s", db_enum.value, e
                )

        self.source_db = self.connections.get("MAIN")  # Database 0

    def _migrate_string_key(self, key: bytes, target_db) -> bool:
        """Migrate a string-type key (Issue #315: extracted helper)."""
        value = self.source_db.get(key)
        ttl = self.source_db.ttl(key)
        target_db.set(key, value)
        if ttl > 0:
            target_db.expire(key, ttl)
        return True

    def _migrate_list_key(self, key: bytes, target_db) -> bool:
        """Migrate a list-type key (Issue #315: extracted helper)."""
        values = self.source_db.lrange(key, 0, -1)
        for value in values:
            target_db.lpush(key, value)
        ttl = self.source_db.ttl(key)
        if ttl > 0:
            target_db.expire(key, ttl)
        return True

    def _migrate_hash_key(self, key: bytes, target_db) -> bool:
        """Migrate a hash-type key (Issue #315: extracted helper)."""
        values = self.source_db.hgetall(key)
        target_db.hset(key, mapping=values)
        ttl = self.source_db.ttl(key)
        if ttl > 0:
            target_db.expire(key, ttl)
        return True

    def _migrate_set_key(self, key: bytes, target_db) -> bool:
        """Migrate a set-type key (Issue #315: extracted helper)."""
        values = self.source_db.smembers(key)
        for value in values:
            target_db.sadd(key, value)
        ttl = self.source_db.ttl(key)
        if ttl > 0:
            target_db.expire(key, ttl)
        return True

    def _migrate_zset_key(self, key: bytes, target_db) -> bool:
        """Migrate a sorted set key (Issue #315: extracted helper)."""
        values = self.source_db.zrange(key, 0, -1, withscores=True)
        for value, score in values:
            target_db.zadd(key, {value: score})
        ttl = self.source_db.ttl(key)
        if ttl > 0:
            target_db.expire(key, ttl)
        return True

    def analyze_current_data(self) -> dict:
        """Analyze data currently in database 0"""
        if not self.source_db:
            logger.error("Cannot connect to source database 0")
            return {}

        all_keys = self.source_db.keys("*")
        analysis = {
            "total_keys": len(all_keys),
            "vector_keys": [],
            "knowledge_keys": [],
            "workflow_keys": [],
            "session_keys": [],
            "other_keys": [],
        }

        for key in all_keys:
            # Decode byte keys to strings for pattern matching
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key

            if key_str.startswith("llama_index/vector_"):
                analysis["vector_keys"].append(key)
            elif key_str.startswith("fact:") or key_str == "fact_id_counter":
                analysis["knowledge_keys"].append(key)
            elif "workflow" in key_str.lower() or "classification" in key_str.lower():
                analysis["workflow_keys"].append(key)
            elif "session" in key_str.lower() or "chat" in key_str.lower():
                analysis["session_keys"].append(key)
            else:
                analysis["other_keys"].append(key)

        logger.info("Data analysis complete:")
        logger.info("  Total keys: %s", analysis["total_keys"])
        logger.info("  Vector embeddings: %s", len(analysis["vector_keys"]))
        logger.info("  Knowledge/Facts: %s", len(analysis["knowledge_keys"]))
        logger.info("  Workflow data: %s", len(analysis["workflow_keys"]))
        logger.info("  Session data: %s", len(analysis["session_keys"]))
        logger.info("  Other data: %s", len(analysis["other_keys"]))

        return analysis

    def migrate_keys(self, keys: list, target_db_name: str, description: str) -> bool:
        """Migrate keys to target database"""
        if not keys:
            logger.info("No %s keys to migrate", description)
            return True

        target_db = self.connections.get(target_db_name)
        if not target_db:
            logger.error("Target database %s not available", target_db_name)
            return False

        logger.info(
            "Migrating %s %s keys to database %s",
            len(keys),
            description,
            target_db_name,
        )

        # Type dispatch table (Issue #315: reduces nesting)
        type_handlers = {
            b"string": self._migrate_string_key,
            b"list": self._migrate_list_key,
            b"hash": self._migrate_hash_key,
            b"set": self._migrate_set_key,
            b"zset": self._migrate_zset_key,
        }

        for key in keys:
            try:
                key_type = self.source_db.type(key)
                handler = type_handlers.get(key_type)
                if handler:
                    handler(key, target_db)
                logger.debug("Migrated %s (%s) to %s", key, key_type, target_db_name)

            except Exception as e:
                logger.error("Failed to migrate key %s: %s", key, e)
                return False

        logger.info("Successfully migrated %s %s keys", len(keys), description)
        return True

    def cleanup_migrated_keys(self, keys: list, description: str) -> bool:
        """Remove migrated keys from source database"""
        if not keys:
            return True

        logger.info(
            "Cleaning up %s %s keys from source database", len(keys), description
        )

        try:
            self.source_db.delete(*keys)
            logger.info("Cleaned up %s %s keys", len(keys), description)
            return True
        except Exception as e:
            logger.error("Failed to cleanup keys: %s", e)
            return False

    def run_migration(self, cleanup: bool = False) -> bool:
        """Run the complete migration process"""
        logger.info("Starting Redis database migration...")

        # Analyze current data
        analysis = self.analyze_current_data()
        if analysis["total_keys"] == 0:
            logger.info("No data to migrate")
            return True

        # Migration plan
        migrations = [
            (analysis["vector_keys"], "VECTORS", "vector embeddings"),
            (analysis["knowledge_keys"], "KNOWLEDGE", "knowledge/facts"),
            (analysis["workflow_keys"], "WORKFLOWS", "workflow data"),
            (analysis["session_keys"], "SESSIONS", "session data"),
        ]

        # Execute migrations
        all_migrated_keys = []
        for keys, target_db, description in migrations:
            if self.migrate_keys(keys, target_db, description):
                all_migrated_keys.extend(keys)
            else:
                logger.error("Migration failed for %s", description)
                return False

        # Optional cleanup
        if cleanup and all_migrated_keys:
            return self.cleanup_migrated_keys(all_migrated_keys, "migrated")

        logger.info("Migration completed successfully!")
        return True

    def verify_migration(self) -> dict:
        """Verify migration results"""
        logger.info("Verifying migration results...")

        results = {}
        for db_enum in RedisDatabase:
            db_name = db_enum.name
            if db_name in self.connections:
                client = self.connections[db_name]
                key_count = client.dbsize()
                results[f"db_{db_enum.value}_{db_name}"] = key_count
                logger.info(
                    "Database %s (%s): %s keys", db_enum.value, db_name, key_count
                )

        return results


def main():
    """Main migration function"""
    migrator = RedisMigrator()

    # Get command line arguments
    cleanup = "--cleanup" in sys.argv
    verify_only = "--verify" in sys.argv

    if verify_only:
        # Just verify current state
        results = migrator.verify_migration()
        print("\nCurrent Redis database distribution:")
        for db_info, count in results.items():
            print(f"  {db_info}: {count} keys")
        return

    # Run migration
    success = migrator.run_migration(cleanup=cleanup)

    if success:
        print("\n✅ Migration completed successfully!")
        # Show results
        results = migrator.verify_migration()
        print("\nFinal Redis database distribution:")
        for db_info, count in results.items():
            print(f"  {db_info}: {count} keys")
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
