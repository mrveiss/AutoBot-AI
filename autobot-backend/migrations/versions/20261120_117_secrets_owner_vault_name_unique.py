# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One envelope secret per (owner_vault, name) (#17850).

``NO DATA REWRITE``: this adds one unique constraint. No row or column is touched. The create path used to
insert a second secret for every repeated first-time save, so an installation may hold several rows under one
``(owner_vault, name)``. Choosing which one survives is a decision about stored credentials: the migration NEVER
makes it. It SELF-APPLIES: with no duplicate group it creates the constraint; with any it logs a counts-only warning
and completes, so the chain finishes on every update path. The app then creates the constraint itself, after the last
approved removal and at startup (``services/secret_unique_constraint.py``). The DDL has one home,
``migrations/secret_unique.py``.

Resolve duplicates with the proposals (``POST /api/admin/secret-duplicates/requests``): each copy is verified against
its target and a human approves the removal of the losing copies in the Approvals inbox. Where a type cannot be
verified, a person keeps the copy they choose and deletes the others with ``DELETE /api/v2/secrets/<id>``.

Legacy rows (``owner_vault IS NULL``) are not constrained: SQL treats NULLs as distinct.
"""

from typing import Sequence, Union

from alembic import op

from migrations.guards import has_table
from migrations.secret_unique import TABLE, ensure_secret_unique_constraint, has_constraint
from models.secret import SECRET_OWNER_VAULT_NAME_UNIQUE

revision: str = "20261120_117"
down_revision: Union[str, None] = "20261120_116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ensure_secret_unique_constraint(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and has_table(TABLE) and has_constraint(bind):
        op.drop_constraint(SECRET_OWNER_VAULT_NAME_UNIQUE, TABLE, type_="unique")
