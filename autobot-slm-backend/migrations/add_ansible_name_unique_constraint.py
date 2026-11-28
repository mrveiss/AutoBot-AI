# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Add unique constraint on nodes.ansible_name (#2011).

Prevents two nodes from sharing the same ansible_name, which would
cause silent misrouting of Ansible --limit targeting.

NULL values are permitted (not all nodes have an ansible_name set),
and PostgreSQL's partial unique index correctly allows multiple NULLs.
"""

import logging

from migrations import utils as _migration_utils
from migrations.utils import get_connection, table_exists

logger = logging.getLogger(__name__)

INDEX_NAME = "uq_nodes_ansible_name"

# A fixed DDL statement: no value reaches it at run time, so it is built once
# here rather than formatted at the execute call.
_CREATE_INDEX_SQL = "CREATE UNIQUE INDEX " + INDEX_NAME + " ON nodes (ansible_name) WHERE ansible_name IS NOT NULL"

# Any single-column unique index on nodes.ansible_name: this migration's own
# partial index, or the ``nodes_ansible_name_key`` constraint create_all builds
# from the model's ``unique=True``. Either one already enforces #2011, so a
# second would only duplicate it.
_UNIQUE_INDEX_SQL = """
    SELECT EXISTS (
        SELECT 1
        FROM pg_index i
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = i.indkey[0]
        WHERE t.relname = 'nodes'
          AND i.indisunique
          AND i.indnatts = 1
          AND a.attname = 'ansible_name'
    )
"""


def _has_unique_ansible_name(cursor) -> bool:
    """True when nodes.ansible_name is already covered by a unique index."""
    cursor.execute(_UNIQUE_INDEX_SQL)
    return bool(cursor.fetchone()[0])


def _apply(cursor) -> None:
    """Create the partial unique index, deferring when nodes is absent."""
    if not table_exists(cursor, "nodes"):
        # A fresh DB runs migrations before create_all builds nodes. The CREATE
        # INDEX would fail with 'relation "nodes" does not exist', which the
        # entrypoint now treats as fatal (#19371). Defer so the runner retries
        # on the next boot instead of recording a no-op as applied (#14300).
        _migration_utils.defer(f"nodes.{INDEX_NAME}")
        logger.warning("Deferring index %s: nodes table does not exist in this database yet (#14300)", INDEX_NAME)
        return
    if _has_unique_ansible_name(cursor):
        logger.info("Migration: nodes.ansible_name already has a unique index, skipping")
        return
    cursor.execute(_CREATE_INDEX_SQL)
    logger.info("Migration: created unique index %s on nodes.ansible_name", INDEX_NAME)


def migrate(db_url: str) -> None:
    """Add unique index on nodes.ansible_name (#2011)."""
    conn = get_connection(db_url)
    try:
        _apply(conn.cursor())
        conn.commit()
    finally:
        conn.close()
