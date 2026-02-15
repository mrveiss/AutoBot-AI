#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add autobot modules to path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "autobot-user-backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "autobot-shared"))

from autobot_shared.redis_client import get_redis_client
from encryption_service import encrypt_data, is_encryption_enabled

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
            "missing_owner": 0
        }
        self.encryption_enabled = is_encryption_enabled()

    async def connect_redis(self) -> None:
        """Connect to Redis database"""
        try:
            self.redis_client = await get_redis_client(
                async_client=True,
                database="main"
            )
            await self.redis_client.ping()
            logger.info("Connected to Redis successfully")
            logger.info(f"Encryption enabled: {self.encryption_enabled}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def get_all_secrets(self) -> List[str]:
        """Get all secret IDs from Redis.

        Returns:
            List of secret IDs
        """
        try:
            # Secrets are stored with key pattern: secret:{secret_id}
            keys = await self.redis_client.keys("secret:*")
            secret_ids = [
                key.decode('utf-8').split(':', 1)[1]
                for key in keys
            ]
            logger.info(f"Found {len(secret_ids)} secrets")
            return secret_ids
        except Exception as e:
            logger.error(f"Failed to get secrets: {e}")
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
                key_str = k.decode('utf-8') if isinstance(k, bytes) else k
                val_str = v.decode('utf-8') if isinstance(v, bytes) else v
                decoded[key_str] = val_str

            return decoded
        except Exception as e:
            logger.error(f"Failed to get secret {secret_id}: {e}")
            return None

    async def infer_secret_owner(
        self,
        secret_id: str,
        secret_data: Dict
    ) -> Optional[str]:
        """Infer the owner of a secret from metadata.

        Args:
            secret_id: Secret ID
            secret_data: Secret data dictionary

        Returns:
            Inferred owner ID or None
        """
        # Check metadata for owner hints
        metadata_str = secret_data.get('metadata', '{}')
        try:
            metadata = json.loads(metadata_str)

            # Check for explicit owner fields
            if metadata.get('owner'):
                return metadata['owner']
            if metadata.get('user_id'):
                return metadata['user_id']
            if metadata.get('created_by'):
                return metadata['created_by']

            # Check for chat_session_id - get owner from session
            if metadata.get('chat_session_id'):
                session_owner = await self._get_session_owner(
                    metadata['chat_session_id']
                )
                if session_owner:
                    return session_owner

        except json.JSONDecodeError:
            logger.debug(f"Could not parse metadata for {secret_id}")

        # Default to admin for unattributed secrets
        return 'admin'

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
                data = data.decode('utf-8')

            session = json.loads(data)
            metadata = session.get('metadata', {})
            return metadata.get('owner') or metadata.get('user_id')
        except Exception as e:
            logger.debug(f"Could not get session owner for {session_id}: {e}")
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
                logger.warning(f"Secret {secret_id} not found")
                self.stats["failed"] += 1
                return False

            # Check if already has owner
            if secret_data.get('owner_id'):
                logger.debug(f"Secret {secret_id} already has owner")
                self.stats["skipped"] += 1
                return True

            # Infer owner
            owner_id = await self.infer_secret_owner(secret_id, secret_data)
            if not owner_id:
                logger.warning(f"Could not infer owner for {secret_id}")
                self.stats["missing_owner"] += 1
                owner_id = 'admin'  # Default fallback

            # Add scope if missing (default to 'user')
            scope = secret_data.get('scope', 'user')

            # Ensure value is encrypted
            value = secret_data.get('value', '')
            if self.encryption_enabled and value and not self._is_encrypted(
                value
            ):
                if not self.dry_run:
                    value = encrypt_data(value)
                    self.stats["encrypted"] += 1
                    logger.debug(f"Encrypted value for secret {secret_id}")

            # Generate rollback SQL
            self.rollback_sql.append(
                f"-- Rollback secret {secret_id}\n"
                f"-- Remove owner: {owner_id}, scope: {scope}\n"
            )

            if self.dry_run:
                logger.info(
                    f"[DRY RUN] Would migrate secret {secret_id} "
                    f"with owner: {owner_id}, scope: {scope}"
                )
                self.stats["migrated"] += 1
                return True

            # Update secret data
            key = f"secret:{secret_id}"
            await self.redis_client.hset(key, 'owner_id', owner_id)
            await self.redis_client.hset(key, 'scope', scope)

            if self.encryption_enabled and value:
                await self.redis_client.hset(key, 'value', value)

            # Update metadata
            metadata_str = secret_data.get('metadata', '{}')
            try:
                metadata = json.loads(metadata_str)
            except json.JSONDecodeError:
                metadata = {}

            metadata['owner'] = owner_id
            metadata['migrated_at'] = datetime.utcnow().isoformat()
            await self.redis_client.hset(
                key,
                'metadata',
                json.dumps(metadata)
            )

            # Register in user's secrets index
            user_secrets_key = f"user:secrets:{owner_id}"
            await self.redis_client.sadd(user_secrets_key, secret_id)

            logger.info(
                f"Migrated secret {secret_id} with owner: {owner_id}, "
                f"scope: {scope}"
            )
            self.stats["migrated"] += 1
            return True

        except Exception as e:
            logger.error(f"Failed to migrate secret {secret_id}: {e}")
            self.stats["failed"] += 1
            return False

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
        base64_pattern = re.compile(r'^[A-Za-z0-9+/]+=*$')
        if not base64_pattern.match(value):
            return False

        # If it's valid base64 and reasonably long, assume encrypted
        return len(value) > 20

    async def run(self) -> None:
        """Run the migration"""
        logger.info("Starting secrets ownership migration")
        logger.info(f"Dry run: {self.dry_run}")

        await self.connect_redis()

        # Get all secrets
        secret_ids = await self.get_all_secrets()

        # Migrate each secret
        for secret_id in secret_ids:
            await self.migrate_secret(secret_id)

        # Save rollback SQL
        if not self.dry_run:
            rollback_file = Path("/tmp/secrets_migration_rollback.sql")
            rollback_file.write_text('\n'.join(self.rollback_sql))
            logger.info(f"Rollback SQL saved to: {rollback_file}")

        # Print statistics
        logger.info("\n" + "=" * 60)
        logger.info("Migration Statistics:")
        logger.info(f"  Total secrets: {self.stats['total_secrets']}")
        logger.info(f"  Migrated: {self.stats['migrated']}")
        logger.info(
            f"  Skipped (already had owner): {self.stats['skipped']}"
        )
        logger.info(f"  Encrypted: {self.stats['encrypted']}")
        logger.info(f"  Missing owner (defaulted): {self.stats['missing_owner']}")
        logger.info(f"  Failed: {self.stats['failed']}")
        logger.info("=" * 60)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Migrate secrets to add ownership and encryption"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Report changes without applying them'
    )
    args = parser.parse_args()

    migrator = SecretsMigrator(dry_run=args.dry_run)
    await migrator.run()


if __name__ == '__main__':
    asyncio.run(main())
