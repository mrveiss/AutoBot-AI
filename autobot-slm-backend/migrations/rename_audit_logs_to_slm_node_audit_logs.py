# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration: Rename SLM node 'audit_logs' table to 'slm_node_audit_logs' (#10764).

Two ORM models both declared ``__tablename__ = 'audit_logs'`` on separate
``DeclarativeBase`` registries that bind to DIFFERENT PostgreSQL databases:

* ``user_management.models.audit.AuditLog`` — UUID PK, org-aware (outcome/details)
  → ``SLM_USERS_DATABASE_URL`` database (``slm_users``). **Canonical** owner of
  ``audit_logs``; left untouched.
* ``models.database.AuditLog`` — INTEGER PK (log_id/category/success/extra_data)
  → ``settings.database_url`` (``SLM_DATABASE_URL``) database (``slm``).

This was a LATENT name-clash (not a live single-table collision) because the two
tables live in different databases. The startup collision checker only warned; it
never raised. Reconciled by renaming the integer-PK SLM table.

This migration runs via ``migrations.runner``, which connects with
``settings.database_url`` — i.e. the ``slm`` database ONLY. It never touches the
``slm_users`` database, so the canonical UUID ``audit_logs`` table is untouched.

Safe to re-run: it only renames when an integer-PK ``audit_logs`` table is present
and ``slm_node_audit_logs`` does not yet exist.
"""

import logging

from migrations.runner import _parse_db_url

logger = logging.getLogger(__name__)

_OLD_NAME = "audit_logs"
_NEW_NAME = "slm_node_audit_logs"


def _connect(db_url: str):
    import psycopg2

    params = _parse_db_url(db_url)
    if params.get("password") is None:
        params.pop("password", None)
    return psycopg2.connect(**params)


def _audit_pk_type(cur, table: str) -> str | None:
    """Return the data_type of ``table.id`` in the public schema, or None."""
    cur.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = 'id'
        """,
        (table,),
    )
    row = cur.fetchone()
    return row[0].lower() if row else None


def migrate(db_url: str) -> None:
    """Rename the integer-PK SLM 'audit_logs' table to 'slm_node_audit_logs'.

    Guards:
    * Skip if the target 'slm_node_audit_logs' already exists (already migrated).
    * Skip if no 'audit_logs' table exists on this (slm) database.
    * Skip if the existing 'audit_logs' has a non-integer PK — that would be the
      user_management (UUID) table and must NOT be touched. (It should never be
      present on the slm database, but this is a belt-and-braces guard.)
    """
    conn = _connect(db_url)
    try:
        with conn.cursor() as cur:
            new_pk = _audit_pk_type(cur, _NEW_NAME)
            if new_pk is not None:
                logger.info(
                    "Table '%s' already exists — skipping rename (already migrated)",
                    _NEW_NAME,
                )
                return

            old_pk = _audit_pk_type(cur, _OLD_NAME)
            if old_pk is None:
                logger.info(
                    "Table '%s' not found on this database — skipping rename " "(fresh install or already migrated)",
                    _OLD_NAME,
                )
                return

            if old_pk not in ("integer", "bigint", "smallint"):
                logger.warning(
                    "Table '%s' has PK type '%s' (not integer) — this is NOT the "
                    "SLM node audit table; refusing to rename",
                    _OLD_NAME,
                    old_pk,
                )
                return

            cur.execute(f"ALTER TABLE {_OLD_NAME} RENAME TO {_NEW_NAME}")
            logger.info("Renamed table '%s' -> '%s'", _OLD_NAME, _NEW_NAME)

            # Rename the default PK sequence if it follows the standard naming.
            cur.execute(
                """
                SELECT relname FROM pg_class
                WHERE relname = %s AND relkind = 'S'
                """,
                (f"{_OLD_NAME}_id_seq",),
            )
            if cur.fetchone():
                cur.execute(f"ALTER SEQUENCE {_OLD_NAME}_id_seq RENAME TO {_NEW_NAME}_id_seq")
                logger.info("Renamed sequence '%s_id_seq' -> '%s_id_seq'", _OLD_NAME, _NEW_NAME)

        conn.commit()
        logger.info("Migration rename_audit_logs_to_slm_node_audit_logs completed")
    finally:
        conn.close()


def downgrade(db_url: str) -> None:
    """Reverse the rename: 'slm_node_audit_logs' -> 'audit_logs'.

    Only acts when 'slm_node_audit_logs' exists and 'audit_logs' does not, so it
    is safe to re-run and will not clobber a canonical UUID audit table (which,
    in any case, lives in the separate slm_users database).
    """
    conn = _connect(db_url)
    try:
        with conn.cursor() as cur:
            new_pk = _audit_pk_type(cur, _NEW_NAME)
            if new_pk is None:
                logger.info("Table '%s' not found — nothing to downgrade", _NEW_NAME)
                return

            old_pk = _audit_pk_type(cur, _OLD_NAME)
            if old_pk is not None:
                logger.warning(
                    "Table '%s' already exists — refusing to downgrade to avoid " "clobbering it",
                    _OLD_NAME,
                )
                return

            cur.execute(f"ALTER TABLE {_NEW_NAME} RENAME TO {_OLD_NAME}")
            logger.info("Renamed table '%s' -> '%s'", _NEW_NAME, _OLD_NAME)

            cur.execute(
                """
                SELECT relname FROM pg_class
                WHERE relname = %s AND relkind = 'S'
                """,
                (f"{_NEW_NAME}_id_seq",),
            )
            if cur.fetchone():
                cur.execute(f"ALTER SEQUENCE {_NEW_NAME}_id_seq RENAME TO {_OLD_NAME}_id_seq")
                logger.info("Renamed sequence '%s_id_seq' -> '%s_id_seq'", _NEW_NAME, _OLD_NAME)

        conn.commit()
        logger.info("Downgrade rename_audit_logs_to_slm_node_audit_logs completed")
    finally:
        conn.close()
