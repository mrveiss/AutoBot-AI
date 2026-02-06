#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session Ownership Backfill Script for AutoBot

Migrates existing chat sessions to ownership model for access control.
Safe to run multiple times (idempotent).

Usage:
    python scripts/security/backfill_session_ownership.py [options]

Options:
    --dry-run              Show what would be done without making changes
    --default-owner USER   Assign all sessions to specific user (default: admin)
    --verbose              Show detailed progress
    --force                Skip confirmation prompts

Examples:
    # Dry run to see what would happen
    python scripts/security/backfill_session_ownership.py --dry-run

    # Assign all sessions to 'admin' user
    python scripts/security/backfill_session_ownership.py --default-owner admin

    # Verbose output with confirmation
    python scripts/security/backfill_session_ownership.py --verbose
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import List, Optional

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.security.session_ownership import SessionOwnershipValidator
from src.utils.redis_client import get_redis_client

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SessionOwnershipBackfill:
    """Backfill session ownership for existing chat sessions"""

    def __init__(
        self, default_owner: str = "admin", dry_run: bool = False, verbose: bool = False
    ):
        """Initialize backfill tool with owner defaults and operational flags."""
        self.default_owner = default_owner
        self.dry_run = dry_run
        self.verbose = verbose
        self.validator: Optional[SessionOwnershipValidator] = None
        self.redis = None

        # Statistics
        self.total_sessions = 0
        self.already_owned = 0
        self.newly_assigned = 0
        self.errors = 0

    async def initialize(self):
        """Initialize Redis connections"""
        logger.info("Initializing Redis connections...")
        self.redis = await get_redis_client(async_client=True, database="main")
        self.validator = SessionOwnershipValidator(self.redis)
        logger.info("✓ Connected to Redis")

    async def get_all_sessions(self) -> List[str]:
        """
        Get all chat session IDs from Redis

        Returns:
            List of session IDs
        """
        logger.info("Scanning for chat sessions...")

        sessions = []
        cursor = 0

        while True:
            cursor, keys = await self.redis.scan(
                cursor, match="chat_session:*", count=100
            )

            # Extract session IDs
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode()

                # Extract session ID from key
                if key.startswith("chat_session:"):
                    session_id = key.replace("chat_session:", "")
                    sessions.append(session_id)

            if cursor == 0:
                break

        logger.info("✓ Found %s chat sessions", len(sessions))
        return sessions

    async def check_session_owner(self, session_id: str) -> Optional[str]:
        """
        Check if session already has an owner

        Args:
            session_id: Session ID to check

        Returns:
            Owner username if exists, None otherwise
        """
        return await self.validator.get_session_owner(session_id)

    async def assign_session_owner(self, session_id: str, owner: str) -> bool:
        """
        Assign owner to session

        Args:
            session_id: Session ID
            owner: Owner username

        Returns:
            True if successful
        """
        if self.dry_run:
            logger.info("[DRY RUN] Would assign %s... to %s", session_id[:16], owner)
            return True

        success = await self.validator.set_session_owner(session_id, owner)

        if success:
            if self.verbose:
                logger.info("✓ Assigned %s... to %s", session_id[:16], owner)
        else:
            logger.error("✗ Failed to assign %s...", session_id[:16])

        return success

    async def backfill_all_sessions(self):
        """Backfill ownership for all sessions"""
        logger.info("=" * 60)
        logger.info("Session Ownership Backfill")
        logger.info("=" * 60)
        logger.info("Default Owner: %s", self.default_owner)
        logger.info("Dry Run: %s", self.dry_run)
        logger.info("=" * 60)

        # Get all sessions
        sessions = await self.get_all_sessions()
        self.total_sessions = len(sessions)

        if self.total_sessions == 0:
            logger.warning("No chat sessions found in Redis DB 0")
            return

        logger.info("Processing %s sessions...", self.total_sessions)
        logger.info("")

        # Process each session
        for idx, session_id in enumerate(sessions, 1):
            try:
                # Check if already owned
                existing_owner = await self.check_session_owner(session_id)

                if existing_owner:
                    self.already_owned += 1
                    if self.verbose:
                        logger.info(
                            f"[{idx}/{self.total_sessions}] {session_id[:16]}... "
                            f"already owned by {existing_owner}"
                        )
                else:
                    # Assign to default owner
                    success = await self.assign_session_owner(
                        session_id, self.default_owner
                    )

                    if success:
                        self.newly_assigned += 1
                    else:
                        self.errors += 1

                # Progress indicator
                if not self.verbose and idx % 10 == 0:
                    logger.info("Progress: %s/%s", idx, self.total_sessions)

            except Exception as e:
                logger.error("Error processing %s...: %s", session_id[:16], e)
                self.errors += 1

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print backfill summary"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("Backfill Summary")
        logger.info("=" * 60)
        logger.info("Total Sessions:       %s", self.total_sessions)
        logger.info("Already Owned:        %s", self.already_owned)
        logger.info("Newly Assigned:       %s", self.newly_assigned)
        logger.info("Errors:               %s", self.errors)
        logger.info("=" * 60)

        if self.dry_run:
            logger.info("✓ DRY RUN COMPLETE - No changes were made")
            logger.info("  Run without --dry-run to apply changes")
        elif self.errors == 0:
            logger.info("✓ BACKFILL COMPLETE - All sessions have ownership")
        else:
            logger.warning("⚠ BACKFILL COMPLETED WITH %s ERRORS", self.errors)
            logger.warning("  Review errors above and retry if needed")

        logger.info("=" * 60)

    async def verify_backfill(self) -> bool:
        """
        Verify all sessions have ownership

        Returns:
            True if all sessions have owners
        """
        logger.info("Verifying ownership coverage...")

        sessions = await self.get_all_sessions()
        unowned = 0

        for session_id in sessions:
            owner = await self.check_session_owner(session_id)
            if not owner:
                logger.error("✗ Session %s... has no owner!", session_id[:16])
                unowned += 1

        if unowned == 0:
            logger.info("✓ All sessions have ownership assigned")
            return True
        else:
            logger.error("✗ %s sessions still lack ownership", unowned)
            return False


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Backfill session ownership for AutoBot chat sessions"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--default-owner",
        type=str,
        default="admin",
        help="Default owner for unowned sessions (default: admin)",
    )
    parser.add_argument("--verbose", action="store_true", help="Show detailed progress")
    parser.add_argument(
        "--force", action="store_true", help="Skip confirmation prompts"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify ownership coverage, don't backfill",
    )

    args = parser.parse_args()

    # Create backfill instance
    backfill = SessionOwnershipBackfill(
        default_owner=args.default_owner, dry_run=args.dry_run, verbose=args.verbose
    )

    try:
        # Initialize
        await backfill.initialize()

        # Verify-only mode
        if args.verify_only:
            success = await backfill.verify_backfill()
            sys.exit(0 if success else 1)

        # Confirmation prompt (unless forced or dry-run)
        if not args.force and not args.dry_run:
            print()
            print("⚠️  WARNING: This will modify session ownership in Redis DB 0")
            print(f"   All unowned sessions will be assigned to: {args.default_owner}")
            print()
            response = input("Continue? [y/N]: ")
            if response.lower() not in ("y", "yes"):
                print("Cancelled by user")
                sys.exit(0)
            print()

        # Run backfill
        await backfill.backfill_all_sessions()

        # Verify if not dry-run
        if not args.dry_run:
            print()
            success = await backfill.verify_backfill()
            sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
