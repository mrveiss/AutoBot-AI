# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Migrate SSO secrets to SystemSecret encrypted storage

Moves client_secret and bind_password from plaintext JSONB config
to encrypted SystemSecret table. Addresses security vulnerability MVA-1737.
"""

import json
import logging
import os
import sys

from migrations.utils import get_connection

logger = logging.getLogger(__name__)

# Same env vars EncryptionService._load_master_key() reads. Validated up front so
# the migration fails before any DB changes rather than mid-loop on the first encrypt.
_ENCRYPTION_KEY_ENV_VARS = ("SLM_ENCRYPTION_KEY", "SLM_SECRET_KEY")


def _require_encryption_key() -> None:
    """Abort before touching the database if no encryption key is configured."""
    if not any(os.getenv(var) for var in _ENCRYPTION_KEY_ENV_VARS):
        raise RuntimeError(
            "No encryption key configured: set one of "
            f"{', '.join(_ENCRYPTION_KEY_ENV_VARS)} before running the SSO secret "
            "migration. Aborting before any database changes."
        )


def migrate(db_url: str) -> None:
    """
    Migrate SSO provider secrets from plaintext config to SystemSecret table.

    For each SSO provider:
    1. Extract client_secret and bind_password from config JSONB
    2. Store them encrypted in system_secrets table
    3. Remove plaintext values from config and add references
    """
    from services.encryption import encrypt_data

    # Fail fast with a clear message before opening a connection or mutating data.
    _require_encryption_key()

    conn = get_connection(db_url)
    cursor = conn.cursor()

    # Tracks the provider/field in flight so a failure can be reported with context.
    current_provider_id = None
    current_field = None

    try:
        # Get all SSO providers
        cursor.execute("SELECT id, config FROM sso_providers")
        providers = cursor.fetchall()

        logger.info("Found %d SSO providers to migrate", len(providers))

        migrated_count = 0
        for provider_id, config_json in providers:
            current_provider_id = provider_id
            current_field = None
            config = json.loads(config_json) if isinstance(config_json, str) else config_json

            secrets_to_migrate = {}
            updated_config = config.copy()

            # Extract sensitive fields
            for field in ["client_secret", "bind_password"]:
                if field in config:
                    value = config[field]
                    if value:
                        current_field = field
                        secrets_to_migrate[field] = value

                        # Create SystemSecret entry
                        secret_key = f"sso:provider:{provider_id}:{field}"
                        encrypted_value = encrypt_data(value)

                        # Check if secret already exists
                        cursor.execute(
                            "SELECT id FROM system_secrets WHERE key = %s",
                            (secret_key,),
                        )
                        existing = cursor.fetchone()

                        if existing:
                            # Update existing
                            cursor.execute(
                                """
                                UPDATE system_secrets
                                SET encrypted_value = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE key = %s
                                """,
                                (encrypted_value, secret_key),
                            )
                        else:
                            # Create new
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

                        # Replace with reference in config
                        updated_config[f"{field}_ref"] = secret_key
                        del updated_config[field]

            # Update provider config if any secrets were migrated
            if secrets_to_migrate:
                updated_config_json = json.dumps(updated_config)
                cursor.execute(
                    "UPDATE sso_providers SET config = %s WHERE id = %s",
                    (updated_config_json, provider_id),
                )
                migrated_count += 1
                logger.info(
                    "Migrated %d secrets for provider %s",
                    len(secrets_to_migrate),
                    provider_id,
                )

        conn.commit()
        logger.info(
            "Migration completed successfully! Migrated secrets for %d providers",
            migrated_count,
        )

    except Exception as e:
        conn.rollback()
        logger.error(
            "Migration failed (provider=%s, field=%s): %s — rolled back, no changes committed",
            current_provider_id,
            current_field,
            type(e).__name__,
        )
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Starting SSO secrets migration")
    migrate(db_url)
