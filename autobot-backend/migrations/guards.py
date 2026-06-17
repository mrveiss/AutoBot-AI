# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared schema-existence guards for Alembic version scripts (#10027).

Every guard wraps the same two primitives the version scripts used to
inline — ``sa.inspect(op.get_bind())`` lookups and the
``postgresql.ENUM(create_type=False)`` + ``create(checkfirst=True)`` pair —
so the emitted DDL is identical to the hand-written forms it replaces.

Enum values stay literal inside each version script: a migration is frozen
history, so it must never read a value list that later revisions (or model
code) can change underneath it. ``pg_enum`` only removes the boilerplate of
saying "this column references a type that op.create_table must not try to
create" (generic ``sa.Enum`` silently ignores ``create_type`` and re-emitted
unconditional ``CREATE TYPE``, aborting fresh-database upgrades — #9759).

Usage in a version script::

    from migrations.guards import ensure_pg_enum, has_table, pg_enum

    _status = pg_enum("approvalstatus", "pending", "approved")

    def upgrade() -> None:
        ensure_pg_enum(_status)
        if not has_table("approvals"):
            ...

Importable as ``migrations.guards`` because ``autobot-backend`` is on
``sys.path`` both at Alembic runtime (env.py inserts it) and under pytest
(``pythonpath`` in pytest.ini); ``migrations`` resolves as a namespace
package, so no ``__init__.py`` is required.

The SLM's psycopg2-based ``autobot-slm-backend/migrations/utils.py`` is a
deliberate non-target: different driver and lifecycle (#10027, #9785).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM


def _inspector() -> sa.engine.reflection.Inspector:
    """Inspector bound to the in-flight migration connection."""
    return sa.inspect(op.get_bind())


def has_table(name: str) -> bool:
    """True when ``name`` exists in the connected database."""
    return _inspector().has_table(name)


def has_column(table: str, column: str) -> bool:
    """True when ``table`` exists and carries ``column``."""
    inspector = _inspector()
    if not inspector.has_table(table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def existing_columns(table: str) -> set[str]:
    """Column names of ``table`` (empty set when the table is absent)."""
    inspector = _inspector()
    if not inspector.has_table(table):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def has_index(table: str, index: str) -> bool:
    """True when ``table`` exists and carries an index named ``index``."""
    inspector = _inspector()
    if not inspector.has_table(table):
        return False
    return index in {i["name"] for i in inspector.get_indexes(table)}


def pg_enum(name: str, *values: str) -> ENUM:
    """A ``postgresql.ENUM`` reference that ``op.create_table`` never creates.

    Use the returned object both in column definitions and as the argument
    to :func:`ensure_pg_enum` / :func:`drop_pg_enum`. Values must be the
    literal strings the migration historically wrote — never derived from
    model code.
    """
    return ENUM(*values, name=name, create_type=False)


def ensure_pg_enum(enum_type: ENUM) -> None:
    """Emit ``CREATE TYPE`` for ``enum_type`` only when it does not exist."""
    enum_type.create(op.get_bind(), checkfirst=True)


def drop_pg_enum(enum_type: ENUM) -> None:
    """Emit ``DROP TYPE`` for ``enum_type`` only when it exists."""
    enum_type.drop(op.get_bind(), checkfirst=True)
