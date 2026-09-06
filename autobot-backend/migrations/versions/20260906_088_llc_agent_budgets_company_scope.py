# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Scope the agent budget slug to its company (#15812).

``llc_agent_budgets.agent_id`` was globally unique. The slug is a per-company
name, so global uniqueness made "is this slug taken?" answerable across the
tenant boundary by anyone permitted to create a budget: a free slug succeeded,
a slug held by an invisible company failed. The bit leaks regardless of the
status code chosen, because the two outcomes have to differ.

``NO DATA LOSS`` — this only *relaxes* uniqueness, so every existing row stays
valid. Nothing is rewritten and nothing is dropped: a namespace that was unique
globally is still unique within each company, and the rows that were legal
before are exactly the rows that are legal after.

``company_id`` is already ``NOT NULL`` on this table (revision 025), which is
what makes the composite constraint meaningful here and is the whole reason this
half was separated from ``agent_org_nodes`` (#15858). There, ``company_id`` is
nullable, and ``NULL != NULL`` under SQL unique semantics would leave every
unscoped row free to duplicate — a constraint that migrates cleanly and
constrains nothing.

The unique constraint being dropped is **unnamed**: revision 025 declared it as
``sa.Column("agent_id", ..., unique=True)``, so each backend generated its own
name. Neither dialect can drop it by a name written here, hence the two paths
below — PostgreSQL discovers the real name by reflection, SQLite recreates the
table under a naming convention that gives the constraint a deterministic name
first.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_088"
down_revision: Union[str, None] = "20260827_087"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Table names are string literals at every ``op.*`` call site, never these
# constants: ``migrations/baseline.py`` AST-extracts each revision's artifacts
# and that extraction is only sound while the names are literal.
_COMPOSITE = "uq_llc_agent_budgets_company_id_agent_id"
_SQLITE_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
_SQLITE_LEGACY_NAME = "uq_llc_agent_budgets_agent_id"


def _unique_on(inspector: sa.Inspector, columns: list[str]) -> list[str]:
    """Names of unique constraints covering exactly *columns*."""
    return [
        uc["name"]
        for uc in inspector.get_unique_constraints("llc_agent_budgets")
        if uc.get("name") and list(uc["column_names"]) == columns
    ]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _unique_on(inspector, ["company_id", "agent_id"]):
        return  # already scoped

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(
            "llc_agent_budgets", naming_convention=_SQLITE_CONVENTION
        ) as batch_op:
            batch_op.drop_constraint(_SQLITE_LEGACY_NAME, type_="unique")
            batch_op.create_unique_constraint(_COMPOSITE, ["company_id", "agent_id"])
        return

    for name in _unique_on(inspector, ["agent_id"]):
        op.drop_constraint(name, "llc_agent_budgets", type_="unique")
    op.create_unique_constraint(_COMPOSITE, "llc_agent_budgets", ["company_id", "agent_id"])


def downgrade() -> None:
    """Restore global uniqueness.

    This can legitimately fail: once two companies hold the same slug — which is
    the point of the upgrade — no global unique constraint can be built over the
    data. Failing loudly is correct; the alternative is deleting somebody's
    budget row to make a constraint fit.
    """
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(
            "llc_agent_budgets", naming_convention=_SQLITE_CONVENTION
        ) as batch_op:
            batch_op.drop_constraint(_COMPOSITE, type_="unique")
            batch_op.create_unique_constraint(_SQLITE_LEGACY_NAME, ["agent_id"])
        return

    op.drop_constraint(_COMPOSITE, "llc_agent_budgets", type_="unique")
    op.create_unique_constraint("uq_llc_agent_budgets_agent_id", "llc_agent_budgets", ["agent_id"])
