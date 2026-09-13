# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: widen roles.systemd_service from VARCHAR(100) to JSON.

Issue #16025 -- a role can own more than one systemd unit (the backend role's
autobot-backend + autobot-celery), so ``role_registry.DEFAULT_ROLES`` now
declares ``systemd_service`` as a sequence. An existing single-unit value
(e.g. ``"postgresql"``) becomes a one-element JSON array (``["postgresql"]``)
rather than being discarded -- the next ``seed_default_roles`` run then
refreshes it to whatever the manifest-derived registry declares.
"""

import logging

from migrations.utils import get_connection, get_table_columns, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Widen roles.systemd_service to JSON, wrapping any existing value (#16025)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if not table_exists(cursor, "roles"):
        logger.info("roles table does not exist yet -- nothing to widen.")
        conn.close()
        return

    if "systemd_service" not in get_table_columns(cursor, "roles"):
        logger.info("roles.systemd_service column does not exist -- nothing to widen.")
        conn.close()
        return

    cursor.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'roles' AND column_name = 'systemd_service'
        """)
    (data_type,) = cursor.fetchone()
    if data_type == "json":
        logger.info("roles.systemd_service is already JSON -- nothing to widen.")
        conn.close()
        return

    cursor.execute("""
        ALTER TABLE roles ALTER COLUMN systemd_service TYPE JSON
        USING CASE WHEN systemd_service IS NULL THEN NULL ELSE to_json(ARRAY[systemd_service]) END
        """)

    conn.commit()
    conn.close()
    logger.info("Widened roles.systemd_service to JSON (existing values wrapped as one-element arrays)")
