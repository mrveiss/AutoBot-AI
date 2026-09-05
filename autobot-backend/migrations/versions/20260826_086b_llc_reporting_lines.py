# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One reporting relation across people and agents (#15763).

Creates ``llc_reporting_lines`` and migrates the existing agent hierarchy into
it. Before this, ``agent_org_nodes.reports_to`` was the only reporting edge in
the system and it could only name another agent, while human members joined the
org chart as roots — two disjoint forests, with an agent reporting to its CEO
unrepresentable in either direction.

``NO DATA LOSS``, and the interesting half is *why that needs saying*. The old
column stores an agent **slug** (``agent_org_nodes.agent_id``, the keyspace used
by budgets, runs and controls). The new table stores the **UUID primary key**,
which is the assignment keyspace that ``assignee_agent_id`` and
``holder_agent_id`` already use (#10032). So this is not a copy: every slug is
resolved to its node's id through a self-join, and:

* a slug that resolves becomes a row in the new table;
* a slug that does **not** resolve — a dangling manager reference, which the
  old column had no foreign key to prevent — is left exactly where it is.

Nothing is lost by that, and the reason is structural rather than a promise:
the old column is not dropped, so every edge, resolved or not, is still in
``agent_org_nodes.reports_to`` afterwards and remains inspectable there. The
guarantee comes from retaining the source, not from a log line — which is why
this migration emits none.

No tree-convergence step is needed and none is attempted. An absent reporting
line resolves to the company's CEO at read time (#15763), so the agent forest
this carries over becomes a tree without any row being invented — every agent
that had no ``reports_to`` simply defaults to the CEO like everyone else.

The old column is **not** dropped here. Retiring it is a separate step, after
the org chart reads the new table (#15763's remaining scope): dropping the only
existing store in the same migration that introduces its replacement leaves no
way back if the new read path is wrong.

Ordering note: this chains from ``20260825_085`` because #15753's
``20260826_086`` is not merged yet. Whichever lands second must renumber onto
the other, or alembic ends up with two heads off 085 — the single-head check
will catch it.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_086b"
down_revision: Union[str, None] = "20260825_085"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Table names are string literals at every ``op.*`` call site, never these
# constants: ``migrations/baseline.py`` AST-extracts each revision's artifacts
# and that extraction is only sound while the names are literal.
_TABLE = "llc_reporting_lines"
_SOURCE = "agent_org_nodes"

_HOLDER_TYPE_LENGTH = 16


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, _TABLE):
        op.create_table(
            "llc_reporting_lines",
            sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("company_id", sa.UUID(as_uuid=True), nullable=False),
            sa.Column("subject_type", sa.String(_HOLDER_TYPE_LENGTH), nullable=False),
            sa.Column("subject_user_id", sa.UUID(as_uuid=True), nullable=True),
            sa.Column("subject_agent_id", sa.UUID(as_uuid=True), nullable=True),
            sa.Column("manager_type", sa.String(_HOLDER_TYPE_LENGTH), nullable=False),
            sa.Column("manager_user_id", sa.UUID(as_uuid=True), nullable=True),
            sa.Column("manager_agent_id", sa.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_llc_reporting_lines_company_id", "llc_reporting_lines", ["company_id"])
        op.create_index("ix_llc_reporting_lines_subject_user_id", "llc_reporting_lines", ["subject_user_id"])
        op.create_index("ix_llc_reporting_lines_subject_agent_id", "llc_reporting_lines", ["subject_agent_id"])
        op.create_index("ix_llc_reporting_lines_manager_user_id", "llc_reporting_lines", ["manager_user_id"])
        op.create_index("ix_llc_reporting_lines_manager_agent_id", "llc_reporting_lines", ["manager_agent_id"])

        # One line manager per subject. Partial, per discriminator: a plain
        # unique constraint spanning both id columns would not enforce this,
        # because SQL treats NULLs as distinct and two rows for the same user
        # (each with subject_agent_id NULL) would not collide.
        op.create_index(
            "uq_llc_reporting_lines_user_subject",
            "llc_reporting_lines",
            ["company_id", "subject_user_id"],
            unique=True,
            postgresql_where=sa.text("subject_type = 'user'"),
            sqlite_where=sa.text("subject_type = 'user'"),
        )
        op.create_index(
            "uq_llc_reporting_lines_agent_subject",
            "llc_reporting_lines",
            ["company_id", "subject_agent_id"],
            unique=True,
            postgresql_where=sa.text("subject_type = 'agent'"),
            sqlite_where=sa.text("subject_type = 'agent'"),
        )

    _backfill_agent_edges(bind, inspector)


def _backfill_agent_edges(bind: sa.engine.Connection, inspector: sa.Inspector) -> None:
    """Carry the existing agent hierarchy over, translating slug -> UUID.

    Postgres only. The statement uses ``gen_random_uuid()`` and ``now()``, which
    SQLite has neither of, and the SQLite path exists solely so unit tests can
    create the schema — there is no agent hierarchy in an in-memory test database
    to carry over. Guarding on the dialect keeps a test run from failing on a
    backfill that would have nothing to do.
    """
    if bind.dialect.name != "postgresql":
        return
    if not _has_table(inspector, _SOURCE):
        return

    # Only rows whose manager slug resolves to a real node in the SAME company.
    # Unresolved ones are deliberately left alone rather than coerced: the old
    # column had no foreign key, so a manager slug naming a node that no longer
    # exists is possible, and inventing a parent for it would be worse than
    # leaving it where it is.
    bind.execute(
        sa.text(
            """
            INSERT INTO llc_reporting_lines (
                id, company_id, subject_type, subject_agent_id,
                manager_type, manager_agent_id, created_at, updated_at
            )
            SELECT
                gen_random_uuid(), child.company_id, 'agent', child.id,
                'agent', parent.id, now(), now()
            FROM agent_org_nodes AS child
            JOIN agent_org_nodes AS parent
              ON parent.agent_id = child.reports_to
             AND parent.company_id = child.company_id
            WHERE child.reports_to IS NOT NULL
              AND child.company_id IS NOT NULL
              AND parent.id <> child.id
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # The source column was never dropped, so the agent hierarchy still lives
    # in agent_org_nodes.reports_to and nothing is lost by removing this table.
    if _has_table(inspector, _TABLE):
        op.drop_index("uq_llc_reporting_lines_agent_subject", table_name="llc_reporting_lines")
        op.drop_index("uq_llc_reporting_lines_user_subject", table_name="llc_reporting_lines")
        op.drop_index("ix_llc_reporting_lines_manager_agent_id", table_name="llc_reporting_lines")
        op.drop_index("ix_llc_reporting_lines_manager_user_id", table_name="llc_reporting_lines")
        op.drop_index("ix_llc_reporting_lines_subject_agent_id", table_name="llc_reporting_lines")
        op.drop_index("ix_llc_reporting_lines_subject_user_id", table_name="llc_reporting_lines")
        op.drop_index("ix_llc_reporting_lines_company_id", table_name="llc_reporting_lines")
        op.drop_table("llc_reporting_lines")
