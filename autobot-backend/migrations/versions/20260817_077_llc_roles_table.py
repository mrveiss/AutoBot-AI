# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add llc_roles — the durable anchor an occupant holds (#14221 step 1).

A role outlives its occupant: people are promoted or leave, and the role keeps
its responsibilities, tools and workflows. Until now a role was a ``String(50)``
on ``AgentOrgNode`` plus a display ``title``, so nothing could attach to it and
everything attached to the occupant instead.

Drift-safe, following 20260629_063 / 20260630_064 / 20260812_073: ``IF NOT
EXISTS`` throughout, so it is correct whether or not the table already exists on
a given database.

**Ordering:** this chains off ``20260816_076`` (the workflows table, #14229),
which is open but not yet merged. That is deliberate — chaining off ``075``
instead would put this and ``076`` on the same parent and fork the graph, which
is exactly the defect fixed on #14229 today and tracked as #14292. **#14229 must
merge before this PR.**

Revision ID: 20260817_077
Revises: 20260816_076
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260817_077"
down_revision: Union[str, None] = "20260816_076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS llc_roles (
            id UUID PRIMARY KEY,
            company_id UUID NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_llc_roles_company_name UNIQUE (company_id, name)
        )
        """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_llc_roles_company_id ON llc_roles (company_id)")


def downgrade() -> None:
    """Reverse of upgrade. Guarded so a downgrade cannot fail on a database
    where the table was never created."""
    op.execute("DROP INDEX IF EXISTS ix_llc_roles_company_id")
    op.execute("DROP TABLE IF EXISTS llc_roles")
