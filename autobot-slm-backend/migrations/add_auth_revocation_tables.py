# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Add the SLM's token-revocation tables (#18663).

The jti denylist and the password epoch move from Redis to the SLM's own
PostgreSQL, so the SLM works without the Redis it deploys. Idempotent: each
table is skipped when it exists. Reversible: DROP TABLE removes them; nothing
references them, and dropping them only forgets revocations (see
models/auth_revocation.py).
"""

import logging

from migrations.utils import get_connection, table_exists

logger = logging.getLogger(__name__)

_TABLES = {
    "slm_revoked_tokens": (
        "CREATE TABLE slm_revoked_tokens (jti VARCHAR(64) PRIMARY KEY, expires_at TIMESTAMPTZ NOT NULL)",
        "CREATE INDEX ix_slm_revoked_tokens_expires_at ON slm_revoked_tokens (expires_at)",
    ),
    "slm_password_epochs": (
        "CREATE TABLE slm_password_epochs (subject VARCHAR(255) PRIMARY KEY, epoch BIGINT NOT NULL)",
    ),
}


def migrate(db_url: str) -> None:
    """Add slm_revoked_tokens and slm_password_epochs (#18663)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()
    for table, statements in _TABLES.items():
        if table_exists(cursor, table):
            logger.info("%s table already exists", table)
            continue
        for statement in statements:
            cursor.execute(statement)
        logger.info("Created %s table", table)
    conn.commit()
    conn.close()
