# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One envelope secret per (owner_vault, name) (#17850).

``NO DATA REWRITE``: this adds one unique constraint. No row or column is touched. The create path used to
insert a second secret for every repeated first-time save, so an installation may hold several rows under one
``(owner_vault, name)``. Choosing which one survives is a decision about stored credentials: the migration
NEVER makes it. If any duplicate exists the migration FAILS, naming each group by vault and secret ids (never
a name or a value), and changes nothing. The fix is a person's: raise the proposals
(``POST /api/admin/secret-duplicates/requests``), each copy is verified against its target, a human approves the
removal of the losing copies in the Approvals inbox, then run the upgrade again.

Legacy rows (``owner_vault IS NULL``) are not constrained: SQL treats NULLs as distinct.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_table

revision: str = "20261120_117"
down_revision: Union[str, None] = "20261118_115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "secrets"
_CONSTRAINT = "uq_secrets_owner_vault_name"
_DUPLICATES = (
    "SELECT owner_vault, array_agg(id::text ORDER BY id::text) AS ids FROM secrets "
    "WHERE owner_vault IS NOT NULL GROUP BY owner_vault, name HAVING count(*) > 1 "
    "ORDER BY owner_vault, min(id::text) LIMIT 20"
)


def _has_constraint() -> bool:
    inspector = sa.inspect(op.get_bind())
    return _CONSTRAINT in {c["name"] for c in inspector.get_unique_constraints(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE) or _has_constraint():
        return
    duplicates = bind.execute(sa.text(_DUPLICATES)).all()
    if duplicates:
        listed = "; ".join(f"vault {row.owner_vault}: secrets {', '.join(row.ids)}" for row in duplicates)
        raise RuntimeError(
            f"cannot create {_CONSTRAINT}: several secrets share one (owner_vault, name) (first 20 groups): "
            f"{listed}. Nothing was changed and no copy was chosen. Verify and resolve them through the "
            "Approvals inbox (POST /api/admin/secret-duplicates/requests), then run the upgrade again."
        )
    op.create_unique_constraint(_CONSTRAINT, _TABLE, ["owner_vault", "name"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and has_table(_TABLE) and _has_constraint():
        op.drop_constraint(_CONSTRAINT, _TABLE, type_="unique")
