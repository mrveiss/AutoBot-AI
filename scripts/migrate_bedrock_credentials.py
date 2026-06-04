#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration script for Bedrock AWS credentials to SecretsService.

Migrates plain-text AWS credentials from environment variables to encrypted
storage in SecretsService. This is a security-critical migration that ensures
credentials are stored encrypted and all access is audited.

Usage:
    python scripts/migrate_bedrock_credentials.py [--dry-run] [--force]

Options:
    --dry-run   Show what would be migrated without making changes
    --force     Overwrite existing credentials in SecretsService
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autobot_shared.logging_manager import get_logger
from services.secrets_service import get_secrets_service

logger = get_logger(__name__)


def get_env_credentials() -> dict | None:
    """
    Read AWS credentials from environment variables.

    Returns:
        dict with aws_access_key_id, aws_secret_access_key, region, or None if not found.
    """
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    if not access_key or not secret_key:
        return None

    return {
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
        "region": region,
    }


def migrate_credentials(dry_run: bool = False, force: bool = False) -> bool:
    """
    Migrate AWS Bedrock credentials to SecretsService.

    Args:
        dry_run: If True, show what would be done without making changes.
        force: If True, overwrite existing credentials.

    Returns:
        True if migration succeeded, False otherwise.
    """
    logger.info("Starting Bedrock credentials migration to SecretsService")

    # 1. Read credentials from environment
    env_creds = get_env_credentials()
    if not env_creds:
        logger.error("No AWS credentials found in environment variables")
        logger.error("Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY before running migration")
        return False

    logger.info("Found AWS credentials in environment variables:")
    logger.info("  - AWS_ACCESS_KEY_ID: %s", env_creds["aws_access_key_id"][:8] + "..." if env_creds["aws_access_key_id"] else "None")
    logger.info("  - AWS_SECRET_ACCESS_KEY: [REDACTED]")
    logger.info("  - AWS_DEFAULT_REGION: %s", env_creds["region"])

    if dry_run:
        logger.info("[DRY RUN] Would store credentials in SecretsService with:")
        logger.info("  - name: bedrock_aws_credentials")
        logger.info("  - secret_type: aws_bedrock_credentials")
        logger.info("  - scope: general")
        return True

    # 2. Check if credentials already exist in SecretsService
    try:
        secrets_service = get_secrets_service()
        existing = secrets_service.get_secret(
            name="bedrock_aws_credentials",
            secret_type="aws_bedrock_credentials",
            scope="general",
        )

        if existing and not force:
            logger.error("Credentials already exist in SecretsService")
            logger.error("Use --force to overwrite existing credentials")
            return False

        # 3. Store credentials in SecretsService
        credentials_json = json.dumps(env_creds)

        if existing:
            logger.info("Updating existing credentials in SecretsService (--force enabled)")
            success = secrets_service.update_secret(
                secret_id=existing["id"],
                value=credentials_json,
                updated_by="migrate_bedrock_credentials.py",
            )
            if not success:
                logger.error("Failed to update credentials in SecretsService")
                return False
        else:
            logger.info("Creating new encrypted credentials in SecretsService")
            secrets_service.create_secret(
                name="bedrock_aws_credentials",
                secret_type="aws_bedrock_credentials",
                value=credentials_json,
                scope="general",
                description="AWS Bedrock credentials (access key, secret key, region)",
                created_by="migrate_bedrock_credentials.py",
            )

        logger.info("✓ Successfully migrated Bedrock credentials to SecretsService")
        logger.info("✓ Credentials are now stored encrypted")
        logger.info("✓ All credential access will be audited")

        # 4. Verify retrieval works
        logger.info("Verifying credential retrieval...")
        retrieved = secrets_service.get_secret(
            name="bedrock_aws_credentials",
            secret_type="aws_bedrock_credentials",
            scope="general",
            include_value=True,
            accessed_by="migrate_bedrock_credentials.py",
        )

        if not retrieved or "value" not in retrieved:
            logger.error("Failed to retrieve credentials after migration")
            return False

        retrieved_creds = json.loads(retrieved["value"])
        if (
            retrieved_creds["aws_access_key_id"] != env_creds["aws_access_key_id"]
            or retrieved_creds["aws_secret_access_key"] != env_creds["aws_secret_access_key"]
        ):
            logger.error("Retrieved credentials do not match original")
            return False

        logger.info("✓ Credential retrieval verified successfully")

        # 5. Provide next steps
        logger.info("")
        logger.info("=== Migration Complete ===")
        logger.info("Next steps:")
        logger.info("1. Test Bedrock provider to ensure it can access credentials")
        logger.info("2. Remove AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY from environment")
        logger.info("3. Update deployment configs to remove plain-text credentials")
        logger.info("")
        logger.info("The Bedrock provider will now use encrypted credentials from SecretsService")

        return True

    except Exception as exc:
        logger.error("Migration failed: %s", exc, exc_info=True)
        return False


def main():
    """Main entry point for the migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate Bedrock AWS credentials to SecretsService",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing credentials in SecretsService",
    )

    args = parser.parse_args()

    success = migrate_credentials(dry_run=args.dry_run, force=args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
