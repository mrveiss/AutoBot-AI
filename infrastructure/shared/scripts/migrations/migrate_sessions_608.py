#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session Migration Script for Issue #608

Migrates existing chat sessions to the new user-centric structure:
1. Adds owner information to sessions without owners
2. Creates memory graph entities for orphaned sessions
3. Removes empty/orphaned sessions (optional)
4. Updates session mode (single_user vs collaborative)

Usage:
    python scripts/migrations/migrate_sessions_608.py [--dry-run] [--cleanup]

Options:
    --dry-run   Show what would be changed without making changes
    --cleanup   Remove empty sessions (those with 0 messages)
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.autobot_memory_graph import AutoBotMemoryGraph
from src.chat_history import ChatHistoryManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SessionMigrator:
    """Migrates existing sessions to Issue #608 structure."""

    def __init__(self, dry_run: bool = False, cleanup: bool = False):
        self.dry_run = dry_run
        self.cleanup = cleanup
        self.chat_manager: Optional[ChatHistoryManager] = None
        self.memory_graph: Optional[AutoBotMemoryGraph] = None
        self.stats = {
            "total_sessions": 0,
            "sessions_with_owner": 0,
            "sessions_without_owner": 0,
            "empty_sessions": 0,
            "migrated": 0,
            "entities_created": 0,
            "cleaned_up": 0,
            "errors": 0,
        }

    async def initialize(self) -> bool:
        """Initialize required components."""
        try:
            self.chat_manager = ChatHistoryManager()
            self.memory_graph = AutoBotMemoryGraph()
            logger.info("Initialized ChatHistoryManager and AutoBotMemoryGraph")
            return True
        except Exception as e:
            logger.error("Failed to initialize components: %s", e)
            return False

    async def run(self) -> dict:
        """Run the migration."""
        logger.info("=" * 60)
        logger.info("Issue #608 Session Migration")
        logger.info("Dry run: %s | Cleanup: %s", self.dry_run, self.cleanup)
        logger.info("=" * 60)

        if not await self.initialize():
            return self.stats

        # Get all sessions
        sessions = await self._get_all_sessions()
        self.stats["total_sessions"] = len(sessions)
        logger.info("Found %d total sessions", len(sessions))

        for session in sessions:
            await self._process_session(session)

        self._print_summary()
        return self.stats

    async def _get_all_sessions(self) -> list:
        """Get all sessions from storage."""
        try:
            if hasattr(self.chat_manager, "list_sessions_fast"):
                return await self.chat_manager.list_sessions_fast()
            elif hasattr(self.chat_manager, "list_sessions"):
                return self.chat_manager.list_sessions()
            else:
                logger.warning("No list_sessions method found")
                return []
        except Exception as e:
            logger.error("Failed to list sessions: %s", e)
            return []

    async def _process_session(self, session: dict) -> None:
        """Process a single session for migration."""
        session_id = session.get("id") or session.get("session_id")
        if not session_id:
            logger.warning("Session without ID found, skipping")
            return

        try:
            # Check message count
            message_count = session.get("message_count", 0)
            if message_count == 0:
                self.stats["empty_sessions"] += 1
                if self.cleanup:
                    await self._cleanup_session(session_id)
                return

            # Check if session has owner
            owner = session.get("owner") or session.get("owner_id")
            if owner:
                self.stats["sessions_with_owner"] += 1
            else:
                self.stats["sessions_without_owner"] += 1
                await self._migrate_session(session_id, session)

        except Exception as e:
            logger.error("Error processing session %s: %s", session_id, e)
            self.stats["errors"] += 1

    async def _migrate_session(self, session_id: str, session: dict) -> None:
        """Migrate a session without owner to new structure."""
        logger.info("Migrating session: %s", session_id)

        # Default owner for orphaned sessions
        default_owner_id = "system"
        default_owner_name = "System"

        if self.dry_run:
            logger.info("[DRY RUN] Would add owner to session %s", session_id)
            logger.info(
                "[DRY RUN] Would create memory graph entity for session %s", session_id
            )
            self.stats["migrated"] += 1
            return

        try:
            # Create memory graph entity for session
            if self.memory_graph:
                metadata = {
                    "session_id": session_id,
                    "name": session.get("name")
                    or session.get("title")
                    or "Unnamed Session",
                    "owner_id": default_owner_id,
                    "mode": "single_user",
                    "migrated": True,
                    "migrated_at": datetime.now().isoformat(),
                }
                await self.memory_graph.create_chat_session_entity(
                    session_id=session_id,
                    user_id=default_owner_id,
                    metadata=metadata,
                )
                self.stats["entities_created"] += 1
                logger.info("Created memory graph entity for session %s", session_id)

            # Update session with owner info
            if hasattr(self.chat_manager, "update_session"):
                update_data = {
                    "owner": {
                        "id": default_owner_id,
                        "username": default_owner_name,
                        "role": "owner",
                    },
                    "mode": "single_user",
                }
                await self.chat_manager.update_session(session_id, update_data)
                logger.info("Updated session %s with owner info", session_id)

            self.stats["migrated"] += 1

        except Exception as e:
            logger.error("Failed to migrate session %s: %s", session_id, e)
            self.stats["errors"] += 1

    async def _cleanup_session(self, session_id: str) -> None:
        """Remove an empty session."""
        if self.dry_run:
            logger.info("[DRY RUN] Would delete empty session: %s", session_id)
            self.stats["cleaned_up"] += 1
            return

        try:
            if hasattr(self.chat_manager, "delete_session"):
                self.chat_manager.delete_session(session_id)
                logger.info("Deleted empty session: %s", session_id)
                self.stats["cleaned_up"] += 1
        except Exception as e:
            logger.error("Failed to delete session %s: %s", session_id, e)
            self.stats["errors"] += 1

    def _print_summary(self) -> None:
        """Print migration summary."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info("Total sessions:         %d", self.stats["total_sessions"])
        logger.info("With owner:             %d", self.stats["sessions_with_owner"])
        logger.info("Without owner:          %d", self.stats["sessions_without_owner"])
        logger.info("Empty sessions:         %d", self.stats["empty_sessions"])
        logger.info("-" * 40)
        logger.info("Migrated:               %d", self.stats["migrated"])
        logger.info("Entities created:       %d", self.stats["entities_created"])
        logger.info("Cleaned up:             %d", self.stats["cleaned_up"])
        logger.info("Errors:                 %d", self.stats["errors"])
        logger.info("=" * 60)

        if self.dry_run:
            logger.info("")
            logger.info("This was a DRY RUN. No changes were made.")
            logger.info("Run without --dry-run to apply changes.")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate sessions to Issue #608 user-centric structure"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove empty sessions (those with 0 messages)",
    )

    args = parser.parse_args()

    migrator = SessionMigrator(dry_run=args.dry_run, cleanup=args.cleanup)
    stats = await migrator.run()

    # Exit with error code if there were errors
    sys.exit(1 if stats["errors"] > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
