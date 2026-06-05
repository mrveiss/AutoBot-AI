#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Migrate existing plaintext SSO provider secrets to AES-256-GCM encryption.

Run once after deploying the encrypted SSOProvider model. Safe to re-run:
rows whose sensitive fields already carry the ``enc:`` prefix are skipped.

Usage:
    AUTOBOT_FIELD_ENCRYPTION_KEY=<key> python scripts/encrypt_sso_secrets.py [--dry-run]

Exit codes:
    0  — success (all rows encrypted or already encrypted)
    1  — error
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Encrypt plaintext SSO provider secrets in-place.")
    p.add_argument("--dry-run", action="store_true", help="Report what would change without writing to DB.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        import json

        from sqlalchemy import create_engine, text

        from autobot_shared.field_encryption import encrypt_sso_config, is_sso_config_encrypted
        from config import get_db_url  # autobot-slm-backend config helper
    except ImportError as exc:
        logger.error("Import error: %s — run from autobot-slm-backend/ with its venv active.", exc)
        return 1

    engine = create_engine(get_db_url(), future=True)
    updated = 0
    skipped = 0
    errors = 0

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, config FROM sso_providers ORDER BY id")).fetchall()
        logger.info("Found %d SSO provider row(s) to inspect.", len(rows))

        for row in rows:
            provider_id, config = row
            if config is None:
                skipped += 1
                continue

            if is_sso_config_encrypted(config):
                logger.debug("Provider %s: already encrypted, skipping.", provider_id)
                skipped += 1
                continue

            try:
                encrypted = encrypt_sso_config(config)
            except Exception as exc:
                logger.error("Provider %s: encryption failed — %s", provider_id, exc)
                errors += 1
                continue

            if args.dry_run:
                logger.info("DRY-RUN provider %s: would encrypt sensitive fields.", provider_id)
            else:
                conn.execute(
                    text("UPDATE sso_providers SET config = :cfg WHERE id = :id"),
                    {"cfg": json.dumps(encrypted), "id": str(provider_id)},
                )
                logger.info("Provider %s: encrypted.", provider_id)
            updated += 1

    verb = "Would update" if args.dry_run else "Updated"
    logger.info("%s %d row(s), skipped %d, errors %d.", verb, updated, skipped, errors)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
