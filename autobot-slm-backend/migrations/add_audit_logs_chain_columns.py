# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: the tamper-evident hash chain on audit_logs (#17219)

``autobot_shared/user_management/models/audit.py :: AuditLog`` gained ``chain_seq``,
``prev_hash``, ``row_hash``, ``row_mac``, ``key_id`` and ``org_ref``, and the shared package
gained the ``audit_chain_anchors`` table. The SLM maps that same model onto its ``slm_users``
database, which has its own chain. ``create_all`` never adds a column to an existing table, so
without this migration every SLM insert into ``audit_logs`` would name columns its table does
not have. Mirrors the backend's Alembic revision ``20261122_122``.

NO DATA REWRITE: six nullable columns with no default and one new table; no existing row is
read or changed. Rows from before the chain stay pre-chain (``chain_seq IS NULL``); the genesis
anchor is written by the first chained insert. Idempotent via ``add_column_if_not_exists`` and
``CREATE ... IF NOT EXISTS``.

The partial UNIQUE index on ``chain_seq`` is built ``CONCURRENTLY`` on an autocommit connection,
after the columns commit, so ``audit_logs`` keeps taking writes while it builds. An INVALID index
left by a failed concurrent build is dropped (an index, never row data) and built again.
Forward-only: there is no down path, and none may drop these columns -- that would delete
audit evidence (#17038).

TARGET_DB routes this to the user_management database (#14300), the only one that holds ``audit_logs``.

Run: python3 -m migrations.add_audit_logs_chain_columns
"""

import logging
import sys

from migrations.runner import TARGET_DB_USER_MANAGEMENT
from migrations.utils import add_column_if_not_exists, get_connection, table_exists

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

TARGET_DB = TARGET_DB_USER_MANAGEMENT

_COLUMNS = (
    ("chain_seq", "BIGINT"),
    ("prev_hash", "VARCHAR(64)"),
    ("row_hash", "VARCHAR(64)"),
    ("row_mac", "VARCHAR(64)"),
    ("key_id", "VARCHAR(32)"),
    ("org_ref", "VARCHAR(64)"),
)
_ANCHORS_SQL = """
CREATE TABLE IF NOT EXISTS audit_chain_anchors (
    kind VARCHAR(16) NOT NULL,
    seq BIGINT NOT NULL,
    hash VARCHAR(64) NOT NULL,
    mac VARCHAR(64) NOT NULL,
    key_id VARCHAR(32) NOT NULL,
    pre_chain_count BIGINT NOT NULL,
    pre_chain_max_created_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, seq)
)
"""
_INDEX_NAME = "uq_audit_logs_chain_seq"
_INDEX_SQL = (
    f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX_NAME} "
    "ON audit_logs (chain_seq) WHERE chain_seq IS NOT NULL"
)
_INVALID_INDEX_SQL = (
    "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = %s AND NOT i.indisvalid"
)


def build_index_concurrently(conn) -> None:
    """Build the index outside any transaction; CONCURRENTLY refuses to run inside one."""
    from psycopg2 import sql  # noqa: PLC0415 -- quoted identifier, as add_audit_logs_canonical_columns (#17225)

    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute(_INVALID_INDEX_SQL, (_INDEX_NAME,))
    if cursor.fetchone():
        cursor.execute(sql.SQL("DROP INDEX CONCURRENTLY IF EXISTS {}").format(sql.Identifier(_INDEX_NAME)))
    cursor.execute(_INDEX_SQL)


def migrate(db_url: str) -> None:
    """Add the six chain columns, the anchors table and the unique index (#17219)."""
    logger.info("Running migration: add_audit_logs_chain_columns")

    conn = get_connection(db_url)
    cursor = conn.cursor()

    has_table = table_exists(cursor, "audit_logs")  # a fresh DB gets all of it from create_all
    if has_table:
        for name, ddl in _COLUMNS:
            add_column_if_not_exists(cursor, "audit_logs", name, ddl)
        cursor.execute(_ANCHORS_SQL)
    conn.commit()
    if has_table:
        build_index_concurrently(conn)
    conn.close()

    logger.info("Migration complete: audit_logs carries the audit hash chain columns")


if __name__ == "__main__":
    from migrations.runner import get_user_management_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_user_management_db_url()
    migrate(db_url)
