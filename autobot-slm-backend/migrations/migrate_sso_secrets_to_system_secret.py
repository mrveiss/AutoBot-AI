# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Migrate SSO secrets to SystemSecret encrypted storage

Moves client_secret and bind_password from plaintext JSONB config
to encrypted SystemSecret table. Addresses security vulnerability MVA-1737.

HARDENED VERSION:
- Validates encryption key before starting
- Uses absolute imports
- Two-phase migration (copy then verify before removal)
- Per-secret error handling with detailed logging
- Safely retryable on failure
"""

import json
import logging
import os
import sys
from typing import Any

# Absolute import from services package
from autobot_slm_backend.services.encryption import decrypt_data, encrypt_data

from migrations.utils import get_connection

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Custom exception for migration failures."""


def validate_encryption_key() -> None:
    """
    Validate that encryption key is set before migration starts.

    Raises:
        ValueError: If no encryption key is configured
    """
    key = os.getenv("SLM_ENCRYPTION_KEY") or os.getenv("SLM_SECRET_KEY")
    if not key:
        raise ValueError(
            "No encryption key found. Set SLM_ENCRYPTION_KEY or SLM_SECRET_KEY "
            "environment variable before running migration."
        )

    if len(key) < 32:
        logger.warning(
            "Encryption key is shorter than recommended 32 characters. "
            "Migration will continue but consider using a stronger key."
        )

    logger.info("✓ Encryption key validated")


def verify_secret_encryption(
    cursor: Any,
    secret_key: str,
    original_value: str,
    provider_id: int,
    field: str,
) -> bool:
    """
    Verify that an encrypted secret can be decrypted correctly.

    Args:
        cursor: Database cursor
        secret_key: Key used to store the secret
        original_value: Original plaintext value
        provider_id: SSO provider ID
        field: Field name (client_secret or bind_password)

    Returns:
        True if verification passed, False otherwise
    """
    try:
        cursor.execute(
            "SELECT encrypted_value FROM system_secrets WHERE key = %s",
            (secret_key,),
        )
        result = cursor.fetchone()

        if not result:
            logger.error(
                "Verification failed for provider %d field %s: secret not found",
                provider_id,
                field,
            )
            return False

        encrypted_value = result[0]
        decrypted_value = decrypt_data(encrypted_value)

        if decrypted_value != original_value:
            logger.error(
                "Verification failed for provider %d field %s: " "decrypted value does not match original",
                provider_id,
                field,
            )
            return False

        logger.debug(
            "✓ Verified encryption for provider %d field %s",
            provider_id,
            field,
        )
        return True

    except Exception as e:
        logger.error(
            "Verification exception for provider %d field %s: %s",
            provider_id,
            field,
            e,
            exc_info=True,
        )
        return False


def migrate_provider_secrets(
    cursor: Any,
    provider_id: int,
    config: dict,
) -> tuple[dict, int]:
    """
    Migrate secrets for a single SSO provider.

    Phase 1: Copy secrets to SystemSecret table (keep originals)
    Phase 2: Verify all secrets can be decrypted
    Phase 3: Update config to remove plaintext (called by main migrate function)

    Args:
        cursor: Database cursor
        provider_id: SSO provider ID
        config: Provider configuration dict

    Returns:
        Tuple of (updated_config, secrets_migrated_count)

    Raises:
        MigrationError: If migration fails for this provider
    """
    secrets_to_migrate = {}
    updated_config = config.copy()

    # Phase 1: Copy secrets to encrypted storage (non-destructive)
    logger.info("Phase 1: Copying secrets for provider %d", provider_id)

    for field in ["client_secret", "bind_password"]:
        if field not in config:
            continue

        value = config[field]
        if not value:
            logger.debug(
                "Skipping empty field %s for provider %d",
                field,
                provider_id,
            )
            continue

        try:
            secret_key = f"sso:provider:{provider_id}:{field}"

            # Check if already encrypted (migration retry case)
            cursor.execute(
                "SELECT id FROM system_secrets WHERE key = %s",
                (secret_key,),
            )
            existing = cursor.fetchone()

            if existing:
                logger.info(
                    "Secret %s already exists (retry detected), updating",
                    secret_key,
                )

            # Encrypt the value
            encrypted_value = encrypt_data(value)

            if existing:
                # Update existing secret
                cursor.execute(
                    """
                    UPDATE system_secrets
                    SET encrypted_value = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE key = %s
                    """,
                    (encrypted_value, secret_key),
                )
                logger.info("✓ Updated encrypted secret: %s", secret_key)
            else:
                # Create new secret
                cursor.execute(
                    """
                    INSERT INTO system_secrets
                    (key, encrypted_value, category, description, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        secret_key,
                        encrypted_value,
                        "sso",
                        f"SSO {field} for provider {provider_id}",
                    ),
                )
                logger.info("✓ Created encrypted secret: %s", secret_key)

            secrets_to_migrate[field] = {
                "key": secret_key,
                "original_value": value,
            }

        except Exception as e:
            error_msg = f"Failed to encrypt provider {provider_id} field {field}: {e}"
            logger.error(error_msg, exc_info=True)
            raise MigrationError(error_msg) from e

    if not secrets_to_migrate:
        logger.info("No secrets to migrate for provider %d", provider_id)
        return config, 0

    # Phase 2: Verify all encrypted secrets can be decrypted
    logger.info(
        "Phase 2: Verifying %d encrypted secrets for provider %d",
        len(secrets_to_migrate),
        provider_id,
    )

    for field, secret_info in secrets_to_migrate.items():
        if not verify_secret_encryption(
            cursor,
            secret_info["key"],
            secret_info["original_value"],
            provider_id,
            field,
        ):
            error_msg = f"Verification failed for provider {provider_id} field {field}"
            raise MigrationError(error_msg)

    logger.info(
        "✓ All %d secrets verified for provider %d",
        len(secrets_to_migrate),
        provider_id,
    )

    # Phase 3 preparation: Build updated config (plaintext removal happens in main)
    for field, secret_info in secrets_to_migrate.items():
        updated_config[f"{field}_ref"] = secret_info["key"]
        # Mark for deletion but don't delete yet (caller does this after commit)
        updated_config[f"_migrate_delete_{field}"] = True

    return updated_config, len(secrets_to_migrate)


def migrate(db_url: str, dry_run: bool = False) -> None:
    """
    Migrate SSO provider secrets from plaintext config to SystemSecret table.

    Two-phase migration:
    1. Copy secrets to encrypted storage (keep originals)
    2. Verify all secrets can be decrypted
    3. Remove plaintext values only after verification passes

    Args:
        db_url: Database connection URL
        dry_run: If True, rollback changes after verification (for testing)

    Raises:
        MigrationError: If migration fails
    """
    # Pre-flight check: validate encryption key
    try:
        validate_encryption_key()
    except ValueError as e:
        logger.error("Pre-flight check failed: %s", e)
        raise MigrationError(f"Encryption key validation failed: {e}") from e

    conn = get_connection(db_url)
    cursor = conn.cursor()

    try:
        # Get all SSO providers
        cursor.execute("SELECT id, config FROM sso_providers ORDER BY id")
        providers = cursor.fetchall()

        if not providers:
            logger.info("No SSO providers found, migration not needed")
            return

        logger.info("Found %d SSO providers to migrate", len(providers))

        migrated_providers = []
        total_secrets = 0

        # Phase 1 & 2: Encrypt and verify (keep originals)
        for provider_id, config_json in providers:
            logger.info("\n=== Processing provider %d ===", provider_id)

            config = json.loads(config_json) if isinstance(config_json, str) else config_json

            try:
                updated_config, secrets_count = migrate_provider_secrets(
                    cursor,
                    provider_id,
                    config,
                )

                if secrets_count > 0:
                    migrated_providers.append(
                        {
                            "id": provider_id,
                            "config": updated_config,
                            "secrets_count": secrets_count,
                        }
                    )
                    total_secrets += secrets_count

            except MigrationError as e:
                conn.rollback()
                logger.error(
                    "Migration failed for provider %d: %s",
                    provider_id,
                    e,
                )
                raise

        # Phase 3: Update configs to remove plaintext (only after all verified)
        logger.info(
            "\nPhase 3: Updating %d provider configs to remove plaintext",
            len(migrated_providers),
        )

        for provider in migrated_providers:
            provider_id = provider["id"]
            updated_config = provider["config"].copy()

            # Remove plaintext fields and migration markers
            for field in ["client_secret", "bind_password"]:
                if f"_migrate_delete_{field}" in updated_config:
                    if field in updated_config:
                        del updated_config[field]
                    del updated_config[f"_migrate_delete_{field}"]

            updated_config_json = json.dumps(updated_config)
            cursor.execute(
                "UPDATE sso_providers SET config = %s WHERE id = %s",
                (updated_config_json, provider_id),
            )
            logger.info(
                "✓ Updated config for provider %d (removed %d plaintext fields)",
                provider_id,
                provider["secrets_count"],
            )

        if dry_run:
            conn.rollback()
            logger.info(
                "\n✓ DRY RUN: Migration verified successfully! "
                "Would migrate %d secrets for %d providers. Changes rolled back.",
                total_secrets,
                len(migrated_providers),
            )
        else:
            conn.commit()
            logger.info(
                "\n✓ Migration completed successfully! " "Migrated %d secrets for %d providers.",
                total_secrets,
                len(migrated_providers),
            )

    except Exception as e:
        conn.rollback()
        logger.error("Migration failed: %s", e, exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    from migrations.runner import get_db_url

    # Support --dry-run flag for testing
    dry_run = "--dry-run" in sys.argv
    db_url = None

    for arg in sys.argv[1:]:
        if arg != "--dry-run":
            db_url = arg
            break

    if not db_url:
        db_url = get_db_url()

    logger.info("Migrating SSO secrets for database: %s", db_url)
    if dry_run:
        logger.info("DRY RUN MODE: Changes will be rolled back")

    try:
        migrate(db_url, dry_run=dry_run)
    except MigrationError as e:
        logger.error("Migration failed: %s", e)
        sys.exit(1)
