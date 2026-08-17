# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Make ``workflows`` company-scoped, not globally unique, by id (#14271).

20260816_076 gave ``workflows.workflow_id`` a *globally* unique primary key,
while every route and service above it (``llc/api/workflows.py``,
``llc/services/workflow.py``) treats the identity as company-scoped — every
read and write filters on ``company_id`` in the query itself. The mismatch
meant two companies could never independently pick the same human-readable
id, a same-company duplicate raced an unhandled ``IntegrityError`` into a
500 instead of the route's documented 409, and the 201-vs-500 split on
create was a cross-tenant presence oracle driven by a field the caller
controls (#14271).

This migration:

1. Adds a surrogate ``id`` (UUID) primary key, backfilled with
   ``gen_random_uuid()`` for every existing row — no row is touched or
   dropped, including the ``company_id IS NULL`` rows written by
   ``services/workflow_redis_backfill.py`` (source =
   ``legacy_redis_unattributed``). ``NO DATA LOSS``: this step only *adds* a
   column and a value to it; nothing existing is altered or removed.
2. Drops the primary key on ``workflow_id`` and makes ``id`` the primary key
   instead. ``workflow_id`` keeps its ``NOT NULL`` (a side effect of having
   been a PK column, which Postgres does not clear on dropping the PK
   constraint) and gains an explicit index, since queries still filter on it.
3. Adds ``UNIQUE (company_id, workflow_id)`` so the constraint finally
   matches the scoping claim. Standard SQL unique-constraint semantics treat
   NULL as distinct from every other value (including another NULL), so the
   pre-existing ``company_id IS NULL`` legacy rows are unaffected by this
   constraint even if two of them happened to share a ``workflow_id`` — they
   were never distinguishable by that column anyway, and nothing about them
   changes here.

Guarded with ``has_table`` / ``has_column`` throughout (20260812_073 idiom):
a database that already carries this shape from an out-of-band path, or one
that skipped 076 entirely, must not hard-fail this migration.

Revision ID: 20260822_082
Revises: 20260821_081
Create Date: 2026-08-22 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from migrations.guards import has_column, has_table

revision: str = "20260822_082"
down_revision: Union[str, None] = "20260821_081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UNIQUE_NAME = "uq_workflows_company_workflow"
_INDEX_NAME = "ix_workflows_workflow_id"


def upgrade() -> None:
    if not has_table("workflows"):
        return

    if not has_column("workflows", "id"):
        # Nullable while it back-fills; every existing row (including the
        # NULL-company legacy ones) gets a fresh value, then the column is
        # tightened to NOT NULL. No row is dropped or altered otherwise.
        op.add_column("workflows", sa.Column("id", UUID(as_uuid=True), nullable=True))
        op.execute('UPDATE "workflows" SET id = gen_random_uuid() WHERE id IS NULL')
        op.alter_column("workflows", "id", nullable=False)

    inspector = sa.inspect(op.get_bind())
    pk = inspector.get_pk_constraint("workflows")
    if pk.get("constrained_columns") == ["workflow_id"]:
        pk_name = pk.get("name") or "workflows_pkey"
        op.drop_constraint(pk_name, "workflows", type_="primary")
        op.create_primary_key("pk_workflows", "workflows", ["id"])

    existing_indexes = {i["name"] for i in inspector.get_indexes("workflows")}
    if _INDEX_NAME not in existing_indexes:
        op.create_index(_INDEX_NAME, "workflows", ["workflow_id"])

    existing_unique = {c["name"] for c in inspector.get_unique_constraints("workflows")}
    if _UNIQUE_NAME not in existing_unique:
        op.create_unique_constraint(_UNIQUE_NAME, "workflows", ["company_id", "workflow_id"])


def downgrade() -> None:
    if not has_table("workflows"):
        return

    inspector = sa.inspect(op.get_bind())

    existing_unique = {c["name"] for c in inspector.get_unique_constraints("workflows")}
    if _UNIQUE_NAME in existing_unique:
        op.drop_constraint(_UNIQUE_NAME, "workflows", type_="unique")

    existing_indexes = {i["name"] for i in inspector.get_indexes("workflows")}
    if _INDEX_NAME in existing_indexes:
        op.drop_index(_INDEX_NAME, table_name="workflows")

    pk = inspector.get_pk_constraint("workflows")
    if pk.get("constrained_columns") == ["id"]:
        # This fails loudly (integrity error) if two rows now share a
        # workflow_id across companies — that is the entire point of this
        # migration, so a downgrade past it cannot silently succeed on data
        # the composite constraint was created to allow.
        pk_name = pk.get("name") or "pk_workflows"
        op.drop_constraint(pk_name, "workflows", type_="primary")
        op.create_primary_key("workflows_pkey", "workflows", ["workflow_id"])

    if has_column("workflows", "id"):
        op.drop_column("workflows", "id")
