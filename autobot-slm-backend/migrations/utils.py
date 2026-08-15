# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration Utilities - PostgreSQL helper functions.

Provides utility functions for migrations to check table/column existence
and safely modify schemas (Issue #786).
"""

import logging
from typing import Set

import psycopg2

logger = logging.getLogger(__name__)


def get_connection(db_url: str, timeout: int = 10) -> psycopg2.extensions.connection:
    """Get a PostgreSQL connection from URL (#786)."""
    from urllib.parse import urlparse

    # Convert async URL to sync URL if needed
    url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(url)

    params = {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/") if parsed.path else "slm",
        "user": parsed.username or "slm_app",
        "connect_timeout": timeout,
    }
    if parsed.password:
        params["password"] = parsed.password

    return psycopg2.connect(**params)


def table_exists(cursor, table_name: str) -> bool:
    """Check if a table exists in the database (#786)."""
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = %s
        )
        """,
        (table_name,),
    )
    return cursor.fetchone()[0]


def get_table_columns(cursor, table_name: str) -> Set[str]:
    """Get set of column names for a table (#786)."""
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = %s
        """,
        (table_name,),
    )
    return {row[0] for row in cursor.fetchall()}


def index_exists(cursor, index_name: str) -> bool:
    """Check if an index exists (#786)."""
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname = %s
        )
        """,
        (index_name,),
    )
    return cursor.fetchone()[0]



# Operations skipped because their table was not present. The runner clears
# this before each migration and consults it after, so a migration that did
# nothing is not recorded as done (#14300).
_DEFERRED: list = []


def reset_deferrals() -> None:
    """Clear the deferral record. Called by the runner before each migration."""
    _DEFERRED.clear()


def deferrals() -> list:
    """Operations the last migration skipped for a missing table."""
    return list(_DEFERRED)


def add_column_if_not_exists(
    cursor,
    table_name: str,
    column_name: str,
    column_def: str,
) -> bool:
    """Add a column to a table if it doesn't exist. Returns True if added (#786).

    On a fresh DB the target table may not exist yet (migration ordering); skip
    cleanly rather than issue an ALTER that errors with 'relation does not
    exist' (#9785).
    """
    if not table_exists(cursor, table_name):
        # #9785 made this skip rather than ALTER a missing table, which was
        # right. #14300 is what the skip grew into: the runner then marks the
        # migration applied, permanently, so the column is never added once the
        # table does appear — or, as on the live host, when the table lives in
        # a different database than the one the runner connects to.
        #
        # Recording the deferral lets the runner decline to mark it applied, so
        # it is retried on the next boot. WARNING rather than DEBUG because a
        # skipped schema change that looks like a completed one is exactly the
        # thing nobody goes looking for.
        _DEFERRED.append(f"{table_name}.{column_name}")
        logger.warning(
            "Deferring add column %s.%s: table does not exist in this database yet (#14300)",
            table_name,
            column_name,
        )
        return False
    existing = get_table_columns(cursor, table_name)
    if column_name.lower() not in {c.lower() for c in existing}:
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"
        logger.info("Adding column: %s.%s", table_name, column_name)
        cursor.execute(sql)
        return True
    logger.info("Column already exists: %s.%s", table_name, column_name)
    return False


def create_index_if_not_exists(
    cursor,
    index_name: str,
    table_name: str,
    columns: str,
) -> bool:
    """Create an index if it doesn't exist. Returns True if created (#786).

    Skip cleanly when the target table does not exist yet on a fresh DB so a
    later create-all converges the schema without a Postgres ERROR (#9785).
    """
    if not table_exists(cursor, table_name):
        logger.debug(
            "Skipping index %s: table %s does not exist yet",
            index_name,
            table_name,
        )
        return False
    if not index_exists(cursor, index_name):
        sql = f"CREATE INDEX {index_name} ON {table_name}({columns})"
        logger.info("Creating index: %s", index_name)
        cursor.execute(sql)
        return True
    logger.info("Index already exists: %s", index_name)
    return False
