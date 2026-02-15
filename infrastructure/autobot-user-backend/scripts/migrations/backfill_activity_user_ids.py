#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Activity User ID Backfill Script

Backfills user_id for existing chat messages and activities:
- Adds user_id to chat messages (from message metadata or session owner)
- Links activities to users where possible
- Updates memory graph entities with user associations

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


class ActivityBackfiller:
    """Backfills user_id for messages and activities"""

    def __init__(self, dry_run: bool = False):
        """Initialize backfiller.

        Args:
            dry_run: If True, report changes without applying them
        """
        self.dry_run = dry_run
        self.redis_client = None
        self.stats = {
            "total_sessions": 0,
            "total_messages": 0,
            "messages_updated": 0,
            "messages_skipped": 0,
            "messages_failed": 0,
            "activities_updated": 0,
            "activities_failed": 0
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

    async def get_session_owner(self, session_id: str) -> Optional[str]:
        """Get the owner of a session.

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

    async def backfill_message_user_ids(
        self,
        session_id: str,
        session_owner: str
    ) -> int:
        """Backfill user_id for messages in a session.

        Args:
            session_id: Session ID to process
            session_owner: Session owner ID (fallback)

        Returns:
            Number of messages updated
        """
        try:
            messages_key = f"chat:messages:{session_id}"
            message_count = await self.redis_client.llen(messages_key)

            if message_count == 0:
                return 0

            self.stats["total_messages"] += message_count
            updated_count = 0

            # Process messages in batches
            batch_size = 100
            for start in range(0, message_count, batch_size):
                end = min(start + batch_size - 1, message_count - 1)
                messages_data = await self.redis_client.lrange(
                    messages_key,
                    start,
                    end
                )

                for idx, msg_data in enumerate(messages_data):
                    try:
                        message = json.loads(msg_data)

                        # Skip if already has user_id
                        if message.get('user_id'):
                            self.stats["messages_skipped"] += 1
                            continue

                        # Infer user_id from message
                        user_id = self._infer_message_user_id(
                            message,
                            session_owner
                        )

                        if not user_id:
                            logger.debug(
                                f"Could not infer user_id for message "
                                f"in {session_id}"
                            )
                            self.stats["messages_failed"] += 1
                            continue

                        # Update message
                        message['user_id'] = user_id
                        message['backfilled_at'] = (
                            datetime.utcnow().isoformat()
                        )

                        if self.dry_run:
                            logger.debug(
                                f"[DRY RUN] Would update message in "
                                f"{session_id} with user_id: {user_id}"
                            )
                            updated_count += 1
                            continue

                        # Update in Redis
                        list_idx = start + idx
                        await self.redis_client.lset(
                            messages_key,
                            list_idx,
                            json.dumps(message)
                        )
                        updated_count += 1

                    except Exception as e:
                        logger.warning(
                            f"Failed to process message in {session_id}: {e}"
                        )
                        self.stats["messages_failed"] += 1

            self.stats["messages_updated"] += updated_count
            return updated_count

        except Exception as e:
            logger.error(
                f"Failed to backfill messages for {session_id}: {e}"
            )
            return 0

    def _infer_message_user_id(
        self,
        message: Dict,
        session_owner: str
    ) -> Optional[str]:
        """Infer user_id from message data.

        Args:
            message: Message dictionary
            session_owner: Session owner ID (fallback)

        Returns:
            Inferred user_id or None
        """
        # Check metadata first
        metadata = message.get('metadata', {})
        if metadata.get('user_id'):
            return metadata['user_id']
        if metadata.get('username'):
            return metadata['username']

        # Check message-level fields
        if message.get('username'):
            return message['username']

        # Check role - if user role, use session owner
        if message.get('role') == 'user':
            return session_owner

        # If assistant/system role, no user attribution needed
        if message.get('role') in ('assistant', 'system'):
            return None

        # Default to session owner for unattributed user messages
        return session_owner

    async def backfill_session_activities(
        self,
        session_id: str,
        session_owner: str
    ) -> int:
        """Backfill user_id for activities in a session.

        Args:
            session_id: Session ID to process
            session_owner: Session owner ID (fallback)

        Returns:
            Number of activities updated
        """
        try:
            # Get activity keys for this session
            activity_keys = await self.redis_client.keys(
                f"activity:{session_id}:*"
            )

            if not activity_keys:
                return 0

            updated_count = 0

            for activity_key in activity_keys:
                try:
                    # Get activity data (stored as hash)
                    activity_data = await self.redis_client.hgetall(
                        activity_key
                    )

                    if not activity_data:
                        continue

                    # Decode activity data
                    decoded = {}
                    for k, v in activity_data.items():
                        key_str = (
                            k.decode('utf-8') if isinstance(k, bytes) else k
                        )
                        val_str = (
                            v.decode('utf-8') if isinstance(v, bytes) else v
                        )
                        decoded[key_str] = val_str

                    # Skip if already has user_id
                    if decoded.get('user_id'):
                        continue

                    # Use session owner as user_id
                    if self.dry_run:
                        logger.debug(
                            f"[DRY RUN] Would update activity "
                            f"{activity_key} with user_id: {session_owner}"
                        )
                        updated_count += 1
                        continue

                    # Update activity
                    await self.redis_client.hset(
                        activity_key,
                        'user_id',
                        session_owner
                    )
                    await self.redis_client.hset(
                        activity_key,
                        'backfilled_at',
                        datetime.utcnow().isoformat()
                    )
                    updated_count += 1

                except Exception as e:
                    logger.warning(
                        f"Failed to process activity {activity_key}: {e}"
                    )
                    self.stats["activities_failed"] += 1

            self.stats["activities_updated"] += updated_count
            return updated_count

        except Exception as e:
            logger.error(
                f"Failed to backfill activities for {session_id}: {e}"
            )
            return 0

    async def run(self) -> None:
        """Run the backfill process"""
        logger.info("Starting activity user_id backfill")
        logger.info(f"Dry run: {self.dry_run}")

        await self.connect_redis()

        # Get all sessions
        session_ids = await self.get_all_sessions()

        # Process each session
        for session_id in session_ids:
            self.stats["total_sessions"] += 1

            # Get session owner
            session_owner = await self.get_session_owner(session_id)
            if not session_owner:
                logger.warning(
                    f"Session {session_id} has no owner, skipping"
                )
                continue

            # Backfill messages
            msg_count = await self.backfill_message_user_ids(
                session_id,
                session_owner
            )

            # Backfill activities
            act_count = await self.backfill_session_activities(
                session_id,
                session_owner
            )

            if msg_count > 0 or act_count > 0:
                logger.info(
                    f"Session {session_id}: updated {msg_count} messages, "
                    f"{act_count} activities"
                )

        # Print statistics
        logger.info("\n" + "=" * 60)
        logger.info("Backfill Statistics:")
        logger.info(f"  Total sessions: {self.stats['total_sessions']}")
        logger.info(f"  Total messages: {self.stats['total_messages']}")
        logger.info(f"  Messages updated: {self.stats['messages_updated']}")
        logger.info(f"  Messages skipped: {self.stats['messages_skipped']}")
        logger.info(f"  Messages failed: {self.stats['messages_failed']}")
        logger.info(f"  Activities updated: {self.stats['activities_updated']}")
        logger.info(f"  Activities failed: {self.stats['activities_failed']}")
        logger.info("=" * 60)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Backfill user_id for messages and activities"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Report changes without applying them'
    )
    args = parser.parse_args()

    backfiller = ActivityBackfiller(dry_run=args.dry_run)
    await backfiller.run()


if __name__ == '__main__':
    asyncio.run(main())
