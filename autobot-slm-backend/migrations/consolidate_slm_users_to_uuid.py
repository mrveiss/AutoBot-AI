# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Consolidate slm_users (integer PK) into users (UUID PK) (#1900).

The slm_users table (formerly the legacy integer-PK 'users' table, renamed by
the rename_users_to_slm_users migration for issue #1854) is no longer backed by
a SQLAlchemy model.  All SLM admin authentication now flows through the
user_management User model with UUID primary key in the 'users' table.

This migration:
1. Reads any existing rows from slm_users (if the table exists).
2. Inserts them into the users table (UUID PK) using a derived email address.
3. Drops the slm_users table.

Safe to re-run: checks whether slm_users table exists before acting.
"""

import logging
import uuid

logger = logging.getLogger(__name__)


def _get_slm_users_db_url() -> str:
    """Get the slm_users database URL (sync) from environment.

    The slm_users table was in the main SLM database (renamed from 'users').
    The target users (UUID PK) table lives in the slm_users database,
    configured via SLM_USERS_DATABASE_URL.

    Returns the sync URL for psycopg2 (strips asyncpg prefix).
    """
    import os

    url = os.getenv("SLM_USERS_DATABASE_URL", "")
    if url:
        return url.replace("postgresql+asyncpg://", "postgresql://")

    # Fall back to component env vars matching user_management/config.py
    host = os.getenv("SLM_POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("SLM_POSTGRES_PORT", "5432")
    database = os.getenv("SLM_POSTGRES_DB", "slm_users")
    user = os.getenv("SLM_POSTGRES_USER", "slm_app")
    password = os.getenv("SLM_POSTGRES_PASSWORD", "")
    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql://{user}@{host}:{port}/{database}"


def migrate(db_url: str) -> None:
    """Migrate slm_users rows into UUID-PK users table and drop slm_users.

    slm_users lives in the main SLM database (db_url).
    users (UUID PK) lives in the separate slm_users database.
    Two connections are required — one per database.

    Args:
        db_url: Main SLM PostgreSQL sync URL (from migration runner).
    """
    import psycopg2

    from migrations.runner import _parse_db_url

    # Connection to main SLM database (contains slm_users table)
    main_params = _parse_db_url(db_url)
    if main_params.get("password") is None:
        main_params.pop("password", None)

    # Connection to slm_users database (contains users UUID table)
    slm_users_db_url = _get_slm_users_db_url()
    slm_params = _parse_db_url(slm_users_db_url)
    if slm_params.get("password") is None:
        slm_params.pop("password", None)

    main_conn = psycopg2.connect(**main_params)
    try:
        with main_conn.cursor() as cur:
            if not _table_exists(cur, "slm_users"):
                logger.info(
                    "Table 'slm_users' not found in main SLM database — "
                    "nothing to migrate (fresh install or already done)"
                )
                return

            cur.execute(
                "SELECT id, username, password_hash, is_active, is_admin, " "created_at, last_login FROM slm_users"
            )
            rows = cur.fetchall()

        if not rows:
            logger.info("No rows in slm_users — dropping empty table")
            _drop_slm_users(main_conn)
            return

        # Migrate rows into the slm_users database
        slm_conn = psycopg2.connect(**slm_params)
        try:
            with slm_conn.cursor() as cur:
                if not _table_exists(cur, "users"):
                    logger.warning(
                        "Table 'users' not found in slm_users database — "
                        "user_management tables may not be initialised yet. "
                        "Skipping row migration; slm_users table retained."
                    )
                    return
                for row in rows:
                    _migrate_row(cur, row)
            slm_conn.commit()
        finally:
            slm_conn.close()

        _drop_slm_users(main_conn)
        logger.info("Migration consolidate_slm_users_to_uuid completed")
    finally:
        main_conn.close()


def _table_exists(cur, table_name: str) -> bool:
    """Return True if the named table exists in the current database."""
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_name = %s AND table_schema = 'public'
        """,
        (table_name,),
    )
    return cur.fetchone() is not None


def _drop_slm_users(conn) -> None:
    """Drop slm_users table from the main SLM database."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS slm_users CASCADE")
    conn.commit()
    logger.info("Dropped table 'slm_users' from main SLM database")


def _migrate_row(cur, row: tuple) -> None:
    """Insert a single slm_users row into the users table.

    Args:
        cur: psycopg2 cursor pointing at slm_users database.
        row: (id, username, password_hash, is_active, is_admin, created_at, last_login)
    """
    _, username, password_hash, is_active, is_admin, created_at, last_login = row

    # Check if a user with this username already exists in users table.
    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
    if cur.fetchone():
        logger.info("User '%s' already exists in users table — skipping", username)
        return

    new_id = str(uuid.uuid4())
    email = f"{username}@slm.local"

    cur.execute(
        """
        INSERT INTO users (
            id, email, username, password_hash,
            is_active, is_verified, mfa_enabled, is_platform_admin,
            preferences, created_at, updated_at, last_login_at
        ) VALUES (
            %s, %s, %s, %s,
            %s, false, false, %s,
            '{}', COALESCE(%s, NOW()), NOW(), %s
        )
        """,
        (
            new_id,
            email,
            username,
            password_hash,
            is_active,
            is_admin,  # maps to is_platform_admin
            created_at,
            last_login,
        ),
    )
    logger.info("Migrated user '%s' from slm_users to users (new id=%s)", username, new_id)
