#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session User Attribution Migration Script

Migrates existing chat sessions to add user attribution:
- Adds owner_id to sessions (inferred from first message sender)
- Adds created_at timestamps if missing
- Registers ownership in Redis indices

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SessionMigrator:
    """Migrates sessions to add user attribution and ownership"""

    def __init__(self, dry_run: bool = False):
        """Initialize migrator.

        Args:
            dry_run: If True, report changes without applying them
        """
        self.dry_run = dry_run
        self.redis_client = None
        self.rollback_sql: List[str] = []
        self.stats = {
            "total_sessions": 0,
            "migrated": 0,
            "skipped": 0,
            "failed": 0,
            "empty_sessions": 0
        }

    async def connect_redis(self) -> None:
        """Connect to Redis database"""
        try:
            self.redis_client = await get_redis_client(
                async_client=True,
                database="main"
            )
            await self.redis_client.ping()
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def get_all_sessions(self) -> List[str]:
        """Get all session IDs from Redis.

        Returns:
            List of session IDs
        """
        try:
            # Sessions are stored with key pattern: chat:session:{session_id}
            keys = await self.redis_client.keys("chat:session:*")
            session_ids = [
                key.decode('utf-8').split(':', 2)[2]
                for key in keys
            ]
            logger.info(f"Found {len(session_ids)} sessions")
            return session_ids
        except Exception as e:
            logger.error(f"Failed to get sessions: {e}")
            return []

    async def get_session_data(self, session_id: str) -> Optional[Dict]:
        """Get session data from Redis.

        Args:
            session_id: Session ID to retrieve

        Returns:
            Session data dictionary or None
        """
        try:
            key = f"chat:session:{session_id}"
            data = await self.redis_client.get(key)
            if not data:
                return None

            if isinstance(data, bytes):
                data = data.decode('utf-8')

            return json.loads(data)
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    async def get_first_message_sender(self, session_id: str) -> Optional[str]:
        """Get the user who sent the first message in a session.

        Args:
            session_id: Session ID to check

        Returns:
            User ID/username of first message sender
        """
        try:
            # Get messages from Redis (stored in list)
            messages_key = f"chat:messages:{session_id}"
            messages_data = await self.redis_client.lrange(messages_key, 0, 0)

            if not messages_data:
                return None

            first_message = json.loads(messages_data[0])
            # Look for user_id, username, or role=user
            if first_message.get('user_id'):
                return first_message['user_id']
            elif first_message.get('username'):
                return first_message['username']
            elif first_message.get('role') == 'user':
                # If no explicit user, default to 'admin'
                return 'admin'

            return None
        except Exception as e:
            logger.debug(f"Could not get first message for {session_id}: {e}")
            return None

    async def migrate_session(self, session_id: str) -> bool:
        """Migrate a single session to add user attribution.

        Args:
            session_id: Session ID to migrate

        Returns:
            True if migrated successfully
        """
        try:
            self.stats["total_sessions"] += 1

            # Get session data
            session_data = await self.get_session_data(session_id)
            if not session_data:
                logger.warning(f"Session {session_id} not found or empty")
                self.stats["empty_sessions"] += 1
                return False

            # Check if already has owner_id
            metadata = session_data.get('metadata', {})
            if metadata.get('owner') or metadata.get('user_id'):
                logger.debug(f"Session {session_id} already has owner")
                self.stats["skipped"] += 1
                return True

            # Infer owner from first message
            owner_id = await self.get_first_message_sender(session_id)
            if not owner_id:
                logger.warning(
                    f"Session {session_id} has no messages, "
                    f"defaulting to 'admin'"
                )
                owner_id = 'admin'

            # Add owner and timestamp
            if 'metadata' not in session_data:
                session_data['metadata'] = {}

            session_data['metadata']['owner'] = owner_id
            session_data['metadata']['user_id'] = owner_id
            session_data['metadata']['migrated_at'] = (
                datetime.utcnow().isoformat()
            )

            if 'created_at' not in session_data:
                # Use lastModified if available, else now
                created_at = session_data.get(
                    'lastModified',
                    datetime.utcnow().isoformat()
                )
                session_data['created_at'] = created_at

            # Generate rollback SQL
            self.rollback_sql.append(
                f"-- Rollback session {session_id}\n"
                f"-- Remove owner: {owner_id}\n"
            )

            if self.dry_run:
                logger.info(
                    f"[DRY RUN] Would migrate session {session_id} "
                    f"with owner: {owner_id}"
                )
                self.stats["migrated"] += 1
                return True

            # Save updated session
            key = f"chat:session:{session_id}"
            await self.redis_client.set(
                key,
                json.dumps(session_data)
            )

            # Register ownership in Redis indices
            await self._register_ownership(session_id, owner_id, metadata)

            logger.info(
                f"Migrated session {session_id} with owner: {owner_id}"
            )
            self.stats["migrated"] += 1
            return True

        except Exception as e:
            logger.error(f"Failed to migrate session {session_id}: {e}")
            self.stats["failed"] += 1
            return False

    async def _register_ownership(
        self,
        session_id: str,
        owner_id: str,
        metadata: Dict
    ) -> None:
        """Register session ownership in Redis indices.

        Args:
            session_id: Session ID
            owner_id: User ID who owns the session
            metadata: Session metadata (may contain org_id, team_id)
        """
        try:
            # Add to user's sessions set
            user_sessions_key = f"user:sessions:{owner_id}"
            await self.redis_client.sadd(user_sessions_key, session_id)

            # Add to org sessions if org_id present
            if metadata.get('org_id'):
                org_sessions_key = f"org:sessions:{metadata['org_id']}"
                await self.redis_client.sadd(org_sessions_key, session_id)

            # Add to team sessions if team_id present
            if metadata.get('team_id'):
                team_sessions_key = f"team:sessions:{metadata['team_id']}"
                await self.redis_client.sadd(team_sessions_key, session_id)

            logger.debug(
                f"Registered ownership for {session_id}: {owner_id}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to register ownership for {session_id}: {e}"
            )

    async def run(self) -> None:
        """Run the migration"""
        logger.info("Starting session user attribution migration")
        logger.info(f"Dry run: {self.dry_run}")

        await self.connect_redis()

        # Get all sessions
        session_ids = await self.get_all_sessions()

        # Migrate each session
        for session_id in session_ids:
            await self.migrate_session(session_id)

        # Save rollback SQL
        if not self.dry_run:
            rollback_file = Path("/tmp/session_migration_rollback.sql")
            rollback_file.write_text('\n'.join(self.rollback_sql))
            logger.info(f"Rollback SQL saved to: {rollback_file}")

        # Print statistics
        logger.info("\n" + "=" * 60)
        logger.info("Migration Statistics:")
        logger.info(f"  Total sessions: {self.stats['total_sessions']}")
        logger.info(f"  Migrated: {self.stats['migrated']}")
        logger.info(f"  Skipped (already had owner): {self.stats['skipped']}")
        logger.info(f"  Empty sessions: {self.stats['empty_sessions']}")
        logger.info(f"  Failed: {self.stats['failed']}")
        logger.info("=" * 60)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Migrate sessions to add user attribution"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Report changes without applying them'
    )
    args = parser.parse_args()

    migrator = SessionMigrator(dry_run=args.dry_run)
    await migrator.run()


if __name__ == '__main__':
    asyncio.run(main())
