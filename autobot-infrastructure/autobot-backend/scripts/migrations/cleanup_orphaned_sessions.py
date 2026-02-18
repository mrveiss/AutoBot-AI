#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cleanup Orphaned Sessions Script

Identifies and removes orphaned/empty chat sessions:
- Sessions with no messages
- Sessions with no activities
- Sessions not linked to any user
- Sessions with corrupt metadata

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
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OrphanedSessionCleaner:
    """Identifies and cleans up orphaned chat sessions"""

    def __init__(self, dry_run: bool = False, min_age_days: int = 7):
        """Initialize cleaner.

        Args:
            dry_run: If True, report what would be deleted without deleting
            min_age_days: Only delete sessions older than this many days
        """
        self.dry_run = dry_run
        self.min_age_days = min_age_days
        self.redis_client = None
        self.deleted_sessions: List[str] = []
        self.stats = {
            "total_sessions": 0,
            "empty_sessions": 0,
            "no_messages": 0,
            "no_activities": 0,
            "no_owner": 0,
            "corrupt_metadata": 0,
            "too_recent": 0,
            "deleted": 0,
            "failed": 0,
        }

    async def connect_redis(self) -> None:
        """Connect to Redis database"""
        try:
            self.redis_client = await get_redis_client(
                async_client=True, database="main"
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
            session_ids = [key.decode("utf-8").split(":", 2)[2] for key in keys]
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
                data = data.decode("utf-8")

            return json.loads(data)
        except Exception as e:
            logger.debug(f"Failed to get session {session_id}: {e}")
            return None

    async def has_messages(self, session_id: str) -> bool:
        """Check if session has any messages.

        Args:
            session_id: Session ID to check

        Returns:
            True if session has messages
        """
        try:
            messages_key = f"chat:messages:{session_id}"
            count = await self.redis_client.llen(messages_key)
            return count > 0
        except Exception as e:
            logger.debug(f"Error checking messages for {session_id}: {e}")
            return False

    async def has_activities(self, session_id: str) -> bool:
        """Check if session has any activities in memory graph.

        Args:
            session_id: Session ID to check

        Returns:
            True if session has activities
        """
        try:
            # Check for activity keys
            activity_keys = await self.redis_client.keys(f"activity:{session_id}:*")
            return len(activity_keys) > 0
        except Exception as e:
            logger.debug(f"Error checking activities for {session_id}: {e}")
            return False

    async def get_session_age_days(self, session_data: Dict) -> Optional[int]:
        """Get the age of a session in days.

        Args:
            session_data: Session data dictionary

        Returns:
            Age in days or None if cannot determine
        """
        try:
            # Check created_at first, then lastModified
            timestamp_str = session_data.get("created_at") or session_data.get(
                "lastModified"
            )
            if not timestamp_str:
                return None

            # Parse ISO format timestamp
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            age = datetime.utcnow() - timestamp.replace(tzinfo=None)
            return age.days
        except Exception as e:
            logger.debug(f"Could not determine session age: {e}")
            return None

    async def is_orphaned(self, session_id: str) -> Dict[str, bool]:
        """Check if a session is orphaned and should be deleted.

        Args:
            session_id: Session ID to check

        Returns:
            Dictionary with orphan criteria
        """
        self.stats["total_sessions"] += 1

        # Get session data
        session_data = await self.get_session_data(session_id)
        if not session_data:
            self.stats["empty_sessions"] += 1
            return {"is_orphaned": True, "reason": "Session data not found"}

        # Check metadata validity
        metadata = session_data.get("metadata", {})
        if not isinstance(metadata, dict):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                self.stats["corrupt_metadata"] += 1
                return {"is_orphaned": True, "reason": "Corrupt metadata"}

        # Check if session is too recent
        age_days = await self.get_session_age_days(session_data)
        if age_days is not None and age_days < self.min_age_days:
            self.stats["too_recent"] += 1
            return {"is_orphaned": False, "reason": f"Too recent ({age_days} days)"}

        # Check for messages
        has_msgs = await self.has_messages(session_id)

        # Check for activities
        has_acts = await self.has_activities(session_id)

        # Check for owner
        has_owner = bool(metadata.get("owner") or metadata.get("user_id"))

        # Session is orphaned if:
        # 1. No messages AND no activities
        # 2. OR no owner and no messages
        reasons = []
        if not has_msgs:
            self.stats["no_messages"] += 1
            reasons.append("no messages")

        if not has_acts:
            self.stats["no_activities"] += 1
            reasons.append("no activities")

        if not has_owner:
            self.stats["no_owner"] += 1
            reasons.append("no owner")

        is_orphaned = (not has_msgs and not has_acts) or (
            not has_owner and not has_msgs
        )

        return {
            "is_orphaned": is_orphaned,
            "reason": ", ".join(reasons) if is_orphaned else "Active session",
            "age_days": age_days,
        }

    async def delete_session(self, session_id: str) -> bool:
        """Delete an orphaned session and all associated data.

        Args:
            session_id: Session ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            if self.dry_run:
                logger.info(f"[DRY RUN] Would delete session: {session_id}")
                self.stats["deleted"] += 1
                self.deleted_sessions.append(session_id)
                return True

            # Delete session data
            session_key = f"chat:session:{session_id}"
            await self.redis_client.delete(session_key)

            # Delete messages
            messages_key = f"chat:messages:{session_id}"
            await self.redis_client.delete(messages_key)

            # Delete activities
            activity_keys = await self.redis_client.keys(f"activity:{session_id}:*")
            if activity_keys:
                await self.redis_client.delete(*activity_keys)

            # Remove from user/org/team indices
            # (We don't know which user, so scan all)
            user_keys = await self.redis_client.keys("user:sessions:*")
            for user_key in user_keys:
                await self.redis_client.srem(user_key, session_id)

            org_keys = await self.redis_client.keys("org:sessions:*")
            for org_key in org_keys:
                await self.redis_client.srem(org_key, session_id)

            team_keys = await self.redis_client.keys("team:sessions:*")
            for team_key in team_keys:
                await self.redis_client.srem(team_key, session_id)

            logger.info(f"Deleted orphaned session: {session_id}")
            self.stats["deleted"] += 1
            self.deleted_sessions.append(session_id)
            return True

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            self.stats["failed"] += 1
            return False

    async def run(self) -> None:
        """Run the cleanup process"""
        logger.info("Starting orphaned session cleanup")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info(f"Minimum age: {self.min_age_days} days")

        await self.connect_redis()

        # Get all sessions
        session_ids = await self.get_all_sessions()

        # Check each session
        for session_id in session_ids:
            orphan_check = await self.is_orphaned(session_id)

            if orphan_check["is_orphaned"]:
                logger.info(
                    f"Found orphaned session {session_id}: " f"{orphan_check['reason']}"
                )
                await self.delete_session(session_id)

        # Save list of deleted sessions
        if not self.dry_run and self.deleted_sessions:
            deleted_file = Path("/tmp/deleted_sessions.txt")
            deleted_file.write_text("\n".join(self.deleted_sessions))
            logger.info(f"List of deleted sessions saved to: {deleted_file}")

        # Print statistics
        logger.info("\n" + "=" * 60)
        logger.info("Cleanup Statistics:")
        logger.info(f"  Total sessions checked: {self.stats['total_sessions']}")
        logger.info(f"  Empty sessions: {self.stats['empty_sessions']}")
        logger.info(f"  No messages: {self.stats['no_messages']}")
        logger.info(f"  No activities: {self.stats['no_activities']}")
        logger.info(f"  No owner: {self.stats['no_owner']}")
        logger.info(f"  Corrupt metadata: {self.stats['corrupt_metadata']}")
        logger.info(
            f"  Too recent (< {self.min_age_days} days): " f"{self.stats['too_recent']}"
        )
        logger.info(f"  Deleted: {self.stats['deleted']}")
        logger.info(f"  Failed: {self.stats['failed']}")
        logger.info("=" * 60)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Clean up orphaned chat sessions")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be deleted without deleting",
    )
    parser.add_argument(
        "--min-age-days",
        type=int,
        default=7,
        help="Only delete sessions older than this many days (default: 7)",
    )
    args = parser.parse_args()

    cleaner = OrphanedSessionCleaner(
        dry_run=args.dry_run, min_age_days=args.min_age_days
    )
    await cleaner.run()


if __name__ == "__main__":
    asyncio.run(main())
