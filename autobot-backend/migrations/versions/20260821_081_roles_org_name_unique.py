# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A company cannot hold two roles of the same name (#14325).

``roles`` carried no uniqueness on ``(org_id, name)``, so one company could hold
two "Head of Sales" rows. That matters more since #14221 hung occupancy,
workflow attachments and **permissions** off a role: two roles sharing a name
with different permission sets are indistinguishable in any UI listing them by
name, and an admin granting to "the" Head of Sales has no way to know which one
they picked.

Three things make this more than a one-line ``create_index``.

**The index is PARTIAL.** System roles carry ``org_id IS NULL``, and Postgres
treats NULLs as distinct for uniqueness — a plain ``UNIQUE(org_id, name)`` would
permit any number of identically named system roles while reading as though it
forbade them. ``WHERE org_id IS NOT NULL`` states what is actually meant.

**Existing duplicates are found before the index, not by it.** Creating a unique
index over duplicate rows fails with a Postgres error naming one arbitrary
conflicting key, which tells an operator nothing about the scale or shape of the
problem. ``upgrade`` therefore scans first and raises with the full list —
company, name and row count — so the data decision is made with the data in
hand. The issue asked for that audit as a prerequisite step; running it inside
the migration means it cannot be skipped or go stale between audit and deploy.

**The application check stays.** ``LLCRoleService.create`` / ``.update`` already
refuse a duplicate name within a company, and that remains the friendly error;
this index closes direct writes and every other caller of the shared table. A
constraint surfaces as ``IntegrityError``, which is not a usable message on its
own — belt and braces, deliberately.

Revision ID: 20260821_081
Revises: 20260820_080
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_081"
down_revision: Union[str, None] = "20260820_080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_roles_org_id_name"

# Rows that would violate the index, grouped so the report names every offending
# (company, role name) pair rather than the single key Postgres would surface.
_DUPLICATE_SCAN = """
    SELECT org_id, name, COUNT(*) AS occurrences
    FROM roles
    WHERE org_id IS NOT NULL
    GROUP BY org_id, name
    HAVING COUNT(*) > 1
    ORDER BY occurrences DESC, name
"""


def upgrade() -> None:
    connection = op.get_bind()
    duplicates = list(connection.exec_driver_sql(_DUPLICATE_SCAN))

    if duplicates:
        listed = "\n".join(
            f"  org_id={row[0]} name={row[1]!r} occurrences={row[2]}" for row in duplicates
        )
        raise RuntimeError(
            f"#14325: cannot add {INDEX_NAME} — {len(duplicates)} (org_id, name) group(s) "
            f"already hold more than one role:\n{listed}\n"
            "Each group needs a resolution decision (rename, merge permissions, or delete the "
            "redundant row) before this migration can apply. The scan runs here rather than as a "
            "manual prerequisite so it cannot go stale between audit and deploy."
        )

    op.create_index(
        INDEX_NAME,
        "roles",
        ["org_id", "name"],
        unique=True,
        postgresql_where=sa.text("org_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="roles")
