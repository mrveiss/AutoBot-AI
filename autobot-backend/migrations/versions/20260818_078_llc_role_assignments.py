# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add llc_role_assignments — who holds a role, and for how long (#14221 step 2).

``ended_at IS NULL`` means the holder holds it now; a set ``ended_at`` means the
tenure is over and the row stays. Ending a tenure is an UPDATE, never a DELETE,
because work left behind still has to belong to the role.

Drift-safe, following 20260817_077: ``IF NOT EXISTS`` throughout.

Revision ID: 20260818_078
Revises: 20260817_077
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260818_078"
down_revision: Union[str, None] = "20260817_077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llc_role_assignments (
            id UUID PRIMARY KEY,
            company_id UUID NOT NULL,
            role_id UUID NOT NULL,
            holder_type VARCHAR(16) NOT NULL,
            holder_agent_id UUID,
            holder_user_id UUID,
            holder_contact_id UUID,
            started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            ended_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    for column in (
        "company_id",
        "role_id",
        "ended_at",
        "holder_agent_id",
        "holder_user_id",
        "holder_contact_id",
    ):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_llc_role_assignments_{column} "
            f"ON llc_role_assignments ({column})"
        )

    # Partial unique index: one *open* tenure per holder per role. Ended tenures
    # are excluded so returning to a role you once held stays legal, which a
    # plain UNIQUE over the same columns would forbid.
    for kind in ("agent", "user", "contact"):
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_llc_role_assignments_open_{kind} "
            f"ON llc_role_assignments (role_id, holder_{kind}_id) "
            f"WHERE ended_at IS NULL AND holder_{kind}_id IS NOT NULL"
        )


def downgrade() -> None:
    """Reverse of upgrade, guarded so it cannot fail where nothing was created."""
    for kind in ("agent", "user", "contact"):
        op.execute(f"DROP INDEX IF EXISTS uq_llc_role_assignments_open_{kind}")
    for column in (
        "company_id",
        "role_id",
        "ended_at",
        "holder_agent_id",
        "holder_user_id",
        "holder_contact_id",
    ):
        op.execute(f"DROP INDEX IF EXISTS ix_llc_role_assignments_{column}")
    op.execute("DROP TABLE IF EXISTS llc_role_assignments")
