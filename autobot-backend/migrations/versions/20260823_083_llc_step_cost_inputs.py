# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Step cost inputs: per-step time and frequency, per-role hourly rate (#14598, #14607).

Adds the two inputs a process step needs to be costed, and the rate the cost is
derived from:

1. ``llc_role_workflows.estimated_minutes`` / ``runs_per_month`` — how long one
   run takes and how often it runs. Both nullable, and NULL means *not
   recorded*, never zero: a step nobody has measured must not total as free.
2. ``llc_role_rates`` — one hourly rate per role, with an explicit currency.

No cost column anywhere, by design. Cost is derived from time x frequency x
rate at read time. A stored cost goes stale the moment a rate changes, and a
stale total is indistinguishable from a current one by looking at it.

The rate hangs off the role rather than the person holding it, for the reason
the workflows and tools already do (#14221): people leave, the role stays. It
lives in its own LLC table rather than as a column on ``roles`` because that
row is the canonical RBAC role shared by every ``user_management`` consumer,
and an hourly rate is an organisational fact rather than an authorisation one.

``NO DATA LOSS``: this migration only adds nullable columns and a new table.
Nothing existing is altered, rewritten or dropped, and ``downgrade`` removes
only what ``upgrade`` created.

Guarded with ``has_table`` / ``has_column`` throughout (the 20260812_073 idiom)
so a database that already carries this shape does not hard-fail.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_083"
down_revision: Union[str, None] = "20260822_082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ATTACH_TABLE = "llc_role_workflows"
_RATE_TABLE = "llc_role_rates"
_RATE_UNIQUE = "uq_llc_role_rates_role"


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Per-step inputs. Nullable: an existing attachment has never been
    #    measured, and backfilling a 0 would assert it costs nothing.
    if _has_table(inspector, _ATTACH_TABLE):
        for column in ("estimated_minutes", "runs_per_month"):
            if not _has_column(inspector, _ATTACH_TABLE, column):
                op.add_column(_ATTACH_TABLE, sa.Column(column, sa.Integer(), nullable=True))

    # 2. The rate the cost derives from.
    if not _has_table(inspector, _RATE_TABLE):
        op.create_table(
            _RATE_TABLE,
            sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("company_id", sa.UUID(as_uuid=True), nullable=False),
            sa.Column("role_id", sa.UUID(as_uuid=True), nullable=False),
            # Numeric, not Float: this feeds a total people are meant to trust,
            # and binary floating point drifts when summed.
            sa.Column("hourly_rate", sa.Numeric(15, 6), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("role_id", name=_RATE_UNIQUE),
        )
        op.create_index("ix_llc_role_rates_company_id", _RATE_TABLE, ["company_id"])
        op.create_index("ix_llc_role_rates_role_id", _RATE_TABLE, ["role_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _RATE_TABLE):
        op.drop_index("ix_llc_role_rates_role_id", table_name=_RATE_TABLE)
        op.drop_index("ix_llc_role_rates_company_id", table_name=_RATE_TABLE)
        op.drop_table(_RATE_TABLE)

    if _has_table(inspector, _ATTACH_TABLE):
        for column in ("runs_per_month", "estimated_minutes"):
            if _has_column(inspector, _ATTACH_TABLE, column):
                op.drop_column(_ATTACH_TABLE, column)
