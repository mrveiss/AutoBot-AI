#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Encryption Migration Script

This script migrates existing unencrypted chat history files to encrypted format
when the encryption feature is enabled.

Usage:
    python scripts/utilities/migrate_encryption.py [--dry-run] [--backup]
"""

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import AutoBot modules after path setup
from chat_history_manager import ChatHistoryManager  # noqa: E402
from config import config as global_config_manager  # noqa: E402
from encryption_service import (  # noqa: E402
    get_encryption_service,
    is_encryption_enabled,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ChatEncryptionMigrator:
    """Handles migration of chat history to encrypted format."""

    def __init__(self, dry_run: bool = False, create_backup: bool = True):
        """Initialize the migrator.

        Args:
            dry_run: If True, only simulate migration without making changes
            create_backup: If True, create backup of original files
        """
        self.dry_run = dry_run
        self.create_backup = create_backup
        self.stats = {"total_files": 0, "migrated": 0, "skipped": 0, "errors": 0}

    def get_chats_directory(self) -> str:
        """Get the chats directory path from configuration."""
        data_config = global_config_manager.get("data", {})
        return data_config.get(
            "chats_directory",
            os.getenv("AUTOBOT_CHATS_DIRECTORY", "data/chats"),
        )

    def backup_file(self, file_path: str) -> str:
        """Create backup of original file.

        Args:
            file_path: Path to file to backup

        Returns:
            Path to backup file
        """
        backup_dir = (
            f"{os.path.dirname(file_path)}/backup_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        os.makedirs(backup_dir, exist_ok=True)

        backup_path = f"{backup_dir}/{os.path.basename(file_path)}"
        shutil.copy2(file_path, backup_path)
        return backup_path

    def is_file_encrypted(self, file_path: str) -> bool:
        """Check if a file is already encrypted.

        Args:
            file_path: Path to file to check

        Returns:
            True if file appears to be encrypted
        """
        try:
            with open(file_path, "r") as f:
                content = f.read().strip()

            # Try to parse as JSON first
            try:
                json.loads(content)
                return False  # Valid JSON = unencrypted
            except json.JSONDecodeError:
                # Not JSON, check if it looks like encrypted data
                encryption_service = get_encryption_service()
                return encryption_service.is_encrypted(content)

        except Exception as e:
            logger.error("Error checking encryption status of %s: %s", file_path, e)
            return False

    def migrate_file(self, file_path: str) -> bool:
        """Migrate a single chat file to encrypted format.

        Args:
            file_path: Path to chat file to migrate

        Returns:
            True if migration was successful
        """
        try:
            logger.info("Processing file: %s", file_path)

            # Check if already encrypted
            if self.is_file_encrypted(file_path):
                logger.info("File %s is already encrypted, skipping", file_path)
                self.stats["skipped"] += 1
                return True

            # Load unencrypted data
            with open(file_path, "r") as f:
                chat_data = json.load(f)

            if self.dry_run:
                logger.info("DRY RUN: Would encrypt %s", file_path)
                self.stats["migrated"] += 1
                return True

            # Create backup if requested
            if self.create_backup:
                backup_path = self.backup_file(file_path)
                logger.info("Created backup: %s", backup_path)

            # Encrypt and save
            chat_manager = ChatHistoryManager()
            encrypted_data = chat_manager._encrypt_data(chat_data)

            with open(file_path, "w") as f:
                f.write(encrypted_data)

            logger.info("Successfully encrypted %s", file_path)
            self.stats["migrated"] += 1
            return True

        except Exception as e:
            logger.error("Failed to migrate %s: %s", file_path, e)
            self.stats["errors"] += 1
            return False

    def migrate_all_chats(self) -> bool:
        """Migrate all chat files to encrypted format.

        Returns:
            True if all migrations were successful
        """
        chats_dir = self.get_chats_directory()

        if not os.path.exists(chats_dir):
            logger.warning("Chats directory %s does not exist", chats_dir)
            return True

        logger.info("Migrating chat files in: %s", chats_dir)

        # Find all chat files
        chat_files = []
        for filename in os.listdir(chats_dir):
            if filename.startswith("chat_") and filename.endswith(".json"):
                chat_files.append(os.path.join(chats_dir, filename))

        self.stats["total_files"] = len(chat_files)
        logger.info("Found %s chat files to process", len(chat_files))

        if len(chat_files) == 0:
            logger.info("No chat files found to migrate")
            return True

        # Process each file
        success = True
        for chat_file in chat_files:
            if not self.migrate_file(chat_file):
                success = False

        return success

    def print_statistics(self):
        """Print migration statistics."""
        logger.info("\n" + "=" * 60)
        logger.info("CHAT HISTORY ENCRYPTION MIGRATION RESULTS")
        logger.info("=" * 60)
        logger.info(f"Total files found: {self.stats['total_files']}")
        logger.info(f"Successfully migrated: {self.stats['migrated']}")
        logger.info(f"Skipped (already encrypted): {self.stats['skipped']}")
        logger.error(f"Errors: {self.stats['errors']}")

        if self.stats["total_files"] > 0:
            success_rate = (
                (self.stats["migrated"] + self.stats["skipped"])
                / self.stats["total_files"]
            ) * 100
            logger.info(f"Success rate: {success_rate:.1f}%")

        if self.dry_run:
            logger.info("\nNOTE: This was a DRY RUN - no files were actually modified")
        elif self.create_backup:
            logger.info("\nOriginal files have been backed up")

        logger.info("=" * 60)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Migrate chat history to encrypted format"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without making changes",
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="Skip creating backup files"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force migration even if encryption is disabled",
    )

    args = parser.parse_args()

    # Check if encryption is enabled
    if not is_encryption_enabled() and not args.force:
        logger.error("❌ Encryption is not enabled in configuration")
        logger.info("To enable encryption:")
        logger.info("1. Set AUTOBOT_ENCRYPTION_KEY environment variable")
        logger.info("2. Set security.enable_encryption to true in config")
        logger.info("3. Or use --force to migrate anyway")
        sys.exit(1)

    # Check if encryption key is available
    try:
        encryption_service = get_encryption_service()
        key_info = encryption_service.get_key_info()
        logger.info(f"✅ Encryption service available: {key_info['algorithm']}")
    except Exception as e:
        logger.error(f"❌ Encryption service not available: {e}")
        if not args.force:
            logger.info("Use --force to proceed anyway (not recommended)")
            sys.exit(1)

    # Initialize migrator
    migrator = ChatEncryptionMigrator(
        dry_run=args.dry_run, create_backup=not args.no_backup
    )

    # Perform migration
    logger.info("🔒 Starting chat history encryption migration...")

    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No files will be modified")

    success = migrator.migrate_all_chats()
    migrator.print_statistics()

    if success:
        logger.info("✅ Migration completed successfully!")
        sys.exit(0)
    else:
        logger.error("❌ Migration completed with errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
