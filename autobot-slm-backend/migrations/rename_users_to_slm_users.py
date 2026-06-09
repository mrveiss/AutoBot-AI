# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Rename SLM admin 'users' table to 'slm_users' (#1854).

The 'users' table in models/database.py (INTEGER PK) collided with the
user_management 'users' table (UUID PK), causing the user_mfa FK constraint
to fail on fresh PostgreSQL databases:

    asyncpg.exceptions.DatatypeMismatchError: foreign key constraint
    "user_mfa_user_id_fkey" cannot be implemented

This migration renames the old INTEGER-PK 'users' table to 'slm_users'.
It is safe to re-run: it checks whether the old table exists before acting.
"""

import logging

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Rename the SLM admin users table from 'users' to 'slm_users'.

    Only renames if the legacy INTEGER-PK 'users' table still exists.
    On fresh installations the table is never created as 'users', so this
    migration is a no-op there.
    """
    import psycopg2

    from migrations.runner import _parse_db_url

    params = _parse_db_url(db_url)
    if params.get("password") is None:
        params.pop("password", None)

    conn = psycopg2.connect(**params)
    try:
        with conn.cursor() as cur:
            # Check whether a table named 'users' with an INTEGER PK exists.
            # If user_management has already created a UUID-PK 'users' table we
            # must not touch it.
            cur.execute("""
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'users'
                  AND column_name = 'id'
                  AND table_schema = 'public'
                """)
            row = cur.fetchone()

            if row is None:
                logger.info("Table 'users' not found — skipping rename " "(fresh install or already migrated)")
                return

            pk_type = row[0].lower()
            if pk_type not in ("integer", "bigint", "smallint"):
                logger.info(
                    "Table 'users' exists but has PK type '%s' (not integer) "
                    "— this is the user_management table, skipping rename",
                    pk_type,
                )
                return

            # Rename the INTEGER-PK users table.
            cur.execute("ALTER TABLE users RENAME TO slm_users")
            logger.info("Renamed table 'users' -> 'slm_users'")

            # Rename the associated sequence if it follows the default naming
            # convention (users_id_seq -> slm_users_id_seq).
            cur.execute("""
                SELECT relname FROM pg_class
                WHERE relname = 'users_id_seq' AND relkind = 'S'
                """)
            if cur.fetchone():
                cur.execute("ALTER SEQUENCE users_id_seq RENAME TO slm_users_id_seq")
                logger.info("Renamed sequence 'users_id_seq' -> 'slm_users_id_seq'")

        conn.commit()
        logger.info("Migration rename_users_to_slm_users completed")
    finally:
        conn.close()
