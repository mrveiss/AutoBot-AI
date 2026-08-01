#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Secrets Ownership Migration Script

Migrates existing secrets to add ownership and scope:
- Adds owner_id to secrets (inferred from creation metadata)
- Adds scope field (default: 'user')
- Ensures encryption on all secret values
- Registers ownership in memory graph

Part of Issue #875 - Session & Secret Data Migration (#608 Phase 7)
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add autobot modules to path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "autobot-user-backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "autobot_shared"))

from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import utc_timestamp
from encryption_service import encrypt_data, is_encryption_enabled

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SecretsMigrator:
    """Migrates secrets to add ownership and ensure encryption"""

    def __init__(self, dry_run: bool = False):
        """Initialize migrator.

        Args:
            dry_run: If True, report changes without applying them
        """
        self.dry_run = dry_run
        self.redis_client = None
        self.rollback_sql: List[str] = []
        self.stats = {
            "total_secrets": 0,
            "migrated": 0,
            "skipped": 0,
            "failed": 0,
            "encrypted": 0,
            "missing_owner": 0,
        }
        self.encryption_enabled = is_encryption_enabled()

    async def connect_redis(self) -> None:
        """Connect to Redis database"""
        try:
            self.redis_client = await get_async_redis_client(database="main")
            await self.redis_client.ping()
            logger.info("Connected to Redis successfully")
            logger.info("Encryption enabled: %s", self.encryption_enabled)
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            raise

    async def get_all_secrets(self) -> List[str]:
        """Get all secret IDs from Redis.

        Returns:
            List of secret IDs
        """
        try:
            # Secrets are stored with key pattern: secret:{secret_id}
            keys = await self.redis_client.keys("secret:*")
            secret_ids = [key.decode("utf-8").split(":", 1)[1] for key in keys]
            logger.info("Found %s secrets", len(secret_ids))
            return secret_ids
        except Exception as e:
            logger.error("Failed to get secrets: %s", e)
            return []

    async def get_secret_data(self, secret_id: str) -> Optional[Dict]:
        """Get secret data from Redis.

        Args:
            secret_id: Secret ID to retrieve

        Returns:
            Secret data dictionary or None
        """
        try:
            key = f"secret:{secret_id}"
            data = await self.redis_client.hgetall(key)
            if not data:
                return None

            # Decode Redis hash data
            decoded = {}
            for k, v in data.items():
                key_str = k.decode("utf-8") if isinstance(k, bytes) else k
                val_str = v.decode("utf-8") if isinstance(v, bytes) else v
                decoded[key_str] = val_str

            return decoded
        except Exception as e:
            logger.error("Failed to get secret %s...: %s", secret_id[:8], e)
            return None

    async def infer_secret_owner(self, secret_id: str, secret_data: Dict) -> Optional[str]:
        """Infer the owner of a secret from metadata.

        Args:
            secret_id: Secret ID
            secret_data: Secret data dictionary

        Returns:
            Inferred owner ID or None
        """
        # Check metadata for owner hints
        metadata_str = secret_data.get("metadata", "{}")
        try:
            metadata = json.loads(metadata_str)

            # Check for explicit owner fields
            if metadata.get("owner"):
                return metadata["owner"]
            if metadata.get("user_id"):
                return metadata["user_id"]
            if metadata.get("created_by"):
                return metadata["created_by"]

            # Check for chat_session_id - get owner from session
            if metadata.get("chat_session_id"):
                session_owner = await self._get_session_owner(metadata["chat_session_id"])
                if session_owner:
                    return session_owner

        except json.JSONDecodeError:
            logger.debug("Could not parse metadata for %s...", secret_id[:8])

        # Default to admin for unattributed secrets
        return "admin"

    async def _get_session_owner(self, session_id: str) -> Optional[str]:
        """Get the owner of a chat session.

        Args:
            session_id: Session ID to check

        Returns:
            Session owner ID or None
        """
        try:
            key = f"chat:session:{session_id}"
            data = await self.redis_client.get(key)
            if not data:
                return None

            if isinstance(data, bytes):
                data = data.decode("utf-8")

            session = json.loads(data)
            metadata = session.get("metadata", {})
            return metadata.get("owner") or metadata.get("user_id")
        except Exception as e:
            logger.debug("Could not get session owner for %s: %s", session_id, e)
            return None

    async def migrate_secret(self, secret_id: str) -> bool:
        """Migrate a single secret to add ownership and ensure encryption.

        Args:
            secret_id: Secret ID to migrate

        Returns:
            True if migrated successfully
        """
        try:
            self.stats["total_secrets"] += 1

            # Get secret data
            secret_data = await self.get_secret_data(secret_id)
            if not secret_data:
                logger.warning("Secret %s... not found", secret_id[:8])
                self.stats["failed"] += 1
                return False

            # Check if already has owner
            if secret_data.get("owner_id"):
                logger.debug("Secret %s... already has owner", secret_id[:8])
                self.stats["skipped"] += 1
                return True

            # Infer owner
            owner_id = await self.infer_secret_owner(secret_id, secret_data)
            if not owner_id:
                logger.warning("Could not infer owner for %s...", secret_id[:8])
                self.stats["missing_owner"] += 1
                owner_id = "admin"  # Default fallback

            # Add scope if missing (default to 'user')
            scope = secret_data.get("scope", "user")

            # Ensure value is encrypted
            value = secret_data.get("value", "")
            if self.encryption_enabled and value and not self._is_encrypted(value):
                if not self.dry_run:
                    value = encrypt_data(value)
                    self.stats["encrypted"] += 1
                    logger.debug(
                        "Encrypted value for secret %s...",
                        secret_id[:8],
                    )

            # Generate rollback SQL
            self.rollback_sql.append(
                f"-- Rollback secret {secret_id}\n" f"-- Remove owner: {owner_id}, scope: {scope}\n"
            )

            if self.dry_run:
                logger.info(
                    "[DRY RUN] Would migrate secret %s... " "with owner: [REDACTED], scope: %s",
                    secret_id[:8],
                    scope,
                )
                self.stats["migrated"] += 1
                return True

            await self._apply_secret_migration(secret_id, owner_id, scope, value, secret_data)
            self.stats["migrated"] += 1
            return True

        except Exception as e:
            logger.error(
                "Failed to migrate secret %s...: %s",
                secret_id[:8],
                e,
            )
            self.stats["failed"] += 1
            return False

    async def _apply_secret_migration(
        self,
        secret_id: str,
        owner_id: str,
        scope: str,
        value: str,
        secret_data: dict,
    ) -> None:
        """Apply migration updates to Redis for a single secret.

        See migrate_secret() for the parent workflow (#1721).
        """
        key = f"secret:{secret_id}"
        await self.redis_client.hset(key, "owner_id", owner_id)
        await self.redis_client.hset(key, "scope", scope)

        if self.encryption_enabled and value:
            await self.redis_client.hset(key, "value", value)

        # Update metadata
        metadata_str = secret_data.get("metadata", "{}")
        try:
            metadata = json.loads(metadata_str)
        except json.JSONDecodeError:
            metadata = {}

        metadata["owner"] = owner_id
        metadata["migrated_at"] = utc_timestamp()
        await self.redis_client.hset(key, "metadata", json.dumps(metadata))

        # Register in user's secrets index
        user_secrets_key = f"user:secrets:{owner_id}"
        await self.redis_client.sadd(user_secrets_key, secret_id)

        logger.info(
            "Migrated secret %s... " "with owner: [REDACTED], scope: %s",
            secret_id[:8],
            scope,
        )

    def _is_encrypted(self, value: str) -> bool:
        """Check if a value appears to be encrypted.

        Args:
            value: Value to check

        Returns:
            True if value looks encrypted
        """
        # Encrypted values are typically base64-encoded
        # and don't contain common plaintext patterns
        if not value:
            return False

        # Check for base64 pattern
        import re

        base64_pattern = re.compile(r"^[A-Za-z0-9+/]+=*$")
        if not base64_pattern.match(value):
            return False

        # If it's valid base64 and reasonably long, assume encrypted
        return len(value) > 20

    async def run(self) -> None:
        """Run the migration"""
        logger.info("Starting secrets ownership migration")
        logger.info("Dry run: %s", self.dry_run)

        await self.connect_redis()

        # Get all secrets
        secret_ids = await self.get_all_secrets()

        # Migrate each secret
        for secret_id in secret_ids:
            await self.migrate_secret(secret_id)

        # Save rollback SQL
        if not self.dry_run:
            # FP: rollback SQL contains only identifiers/metadata
            # (secret_id, owner_id, scope) — never the secret value itself
            # (see rollback_sql.append above). No sensitive material is stored.
            rollback_file = Path("/tmp/secrets_migration_rollback.sql")  # codeql[py/clear-text-storage-sensitive-data]
            rollback_file.write_text("\n".join(self.rollback_sql))
            logger.info("Rollback SQL saved to: %s", rollback_file)

        # Print statistics
        logger.info("\n" + "=" * 60)
        logger.info("Migration Statistics:")
        logger.info("  Total secrets: %s", self.stats["total_secrets"])
        logger.info("  Migrated: %s", self.stats["migrated"])
        logger.info(
            "  Skipped (already had owner): %s",
            self.stats["skipped"],
        )
        logger.info("  Encrypted: %s", self.stats["encrypted"])
        logger.info(
            "  Missing owner (defaulted): %s",
            self.stats["missing_owner"],
        )
        logger.info("  Failed: %s", self.stats["failed"])
        logger.info("=" * 60)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Migrate secrets to add ownership and encryption")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without applying them")
    args = parser.parse_args()

    migrator = SecretsMigrator(dry_run=args.dry_run)
    await migrator.run()


if __name__ == "__main__":
    asyncio.run(main())
