# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every company gets a CEO, including the ones that already exist (#15770).

Creates ``llc_company_ceos`` and provisions a default agent CEO for every
company that does not have one. The second half is the point of the split: a
creation-only implementation passes every test written against a freshly made
company and changes nothing for any company that exists today -- and today,
every company is in the broken state, because nothing has ever designated a CEO.

``NO DATA LOSS``. This migration only inserts: one ``agent_org_nodes`` row and
one ``llc_company_ceos`` row per company that lacks a CEO. Nothing is updated,
nothing is dropped, and no existing reporting edge is touched. A company that
somehow already has a CEO row is skipped rather than overwritten.

**Idempotent by predicate, not by luck.** ``upgrade`` creates the table only
when absent but always reaches the backfill, so a re-run must not double-insert.
Both statements are guarded by ``NOT EXISTS`` on the CEO row, and the agent
insert is additionally guarded on the slug, so re-running is a no-op rather than
a unique-violation.

**The slug is derived from the company id.** ``agent_org_nodes.agent_id`` is
globally unique -- not unique per company (#15812) -- so a fixed slug like
``agent-ceo`` would collide on the second company and abort the whole backfill.
``ceo-<company uuid>`` is unique by construction.

Postgres only, like #15763's backfill and for the same reason: the statements
use ``gen_random_uuid()``, which SQLite does not have, and the SQLite path
exists so unit tests can create the schema. There are no pre-existing companies
in an in-memory test database to provision for.

The default holder is an **agent**, which is the owner's decision and matches
the researched reference design. It is a default and not a definition: the
column shape is the ``holder_type`` + ``holder_*_id`` keyspace, so a person can
hold the position without a migration.
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
_TABLE = "llc_company_ceos"
_AGENTS = "agent_org_nodes"
_ORGS = "organizations"

_HOLDER_TYPE_LENGTH = 16

#: Title and role of a provisioned default CEO. ``manager`` is the only
#: ``OrgRole`` that denotes authority over other agents; there is no dedicated
#: "ceo" role and adding one would put the position in two places at once.
_CEO_ORG_ROLE = "manager"
_CEO_NAME = "CEO"
_CEO_TITLE = "Chief Executive Officer"


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, _TABLE):
        op.create_table(
            "llc_company_ceos",
            sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
            # UNIQUE, not merely indexed: at most one CEO per company is the
            # invariant the default reporting chain walks on.
            sa.Column("company_id", sa.UUID(as_uuid=True), nullable=False, unique=True),
            sa.Column("holder_type", sa.String(_HOLDER_TYPE_LENGTH), nullable=False),
            sa.Column("holder_user_id", sa.UUID(as_uuid=True), nullable=True),
            sa.Column("holder_agent_id", sa.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_llc_company_ceos_holder_user_id", "llc_company_ceos", ["holder_user_id"])
        op.create_index("ix_llc_company_ceos_holder_agent_id", "llc_company_ceos", ["holder_agent_id"])

    _provision_missing_ceos(bind, inspector)


def _provision_missing_ceos(bind: sa.engine.Connection, inspector: sa.Inspector) -> None:
    """Give every company without a CEO a default agent one.

    Two statements rather than one CTE so the agent insert and the designation
    are separately re-runnable: if the first has already run, the second still
    finds the agent by slug and designates it.
    """
    if bind.dialect.name != "postgresql":
        return
    if not (_has_table(inspector, _AGENTS) and _has_table(inspector, _ORGS)):
        return

    bind.execute(
        sa.text("""
            INSERT INTO agent_org_nodes (id, agent_id, name, org_role, title, company_id)
            SELECT gen_random_uuid(), 'ceo-' || o.id::text, :ceo_name, :org_role, :ceo_title, o.id
            FROM organizations o
            WHERE o.llc_status IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM llc_company_ceos c WHERE c.company_id = o.id)
              AND NOT EXISTS (SELECT 1 FROM agent_org_nodes a WHERE a.agent_id = 'ceo-' || o.id::text)
            """),
        {"ceo_name": _CEO_NAME, "org_role": _CEO_ORG_ROLE, "ceo_title": _CEO_TITLE},
    )

    bind.execute(sa.text("""
            INSERT INTO llc_company_ceos (id, company_id, holder_type, holder_agent_id)
            SELECT gen_random_uuid(), o.id, 'agent', a.id
            FROM organizations o
            JOIN agent_org_nodes a ON a.agent_id = 'ceo-' || o.id::text
            WHERE o.llc_status IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM llc_company_ceos c WHERE c.company_id = o.id)
            """))


def downgrade() -> None:
    # The provisioned agents are deliberately left in place. Dropping the
    # designation table is reversible; deleting agent rows that may since have
    # acquired budgets, runs or reporting edges is not.
    op.drop_table("llc_company_ceos")
