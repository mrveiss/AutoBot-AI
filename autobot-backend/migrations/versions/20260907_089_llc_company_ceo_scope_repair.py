# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Undo the CEO rows 088 provisioned for things that are not companies (#15892).

``20260906_088`` scoped its backfill with ``WHERE o.llc_status IS NOT NULL``.
That column is ``NOT NULL`` with a client-side default, so the predicate is true
for every row: the backfill provisioned a CEO for **every organization**, not
for every company.

``088`` is already on base, so the predicate cannot be corrected in place --
every installation that has run ``alembic upgrade head`` has already
over-provisioned. This repairs forward instead, and ``088`` keeps
over-provisioning on a fresh install until this runs after it.

**What a company is, from the code rather than from a vote.**
``llc/services/company.py:144`` selects ``parent_org_id IS NULL AND deleted_at
IS NULL``, with no LLC predicate at all; the same pair recurs at ``:155``,
``:335`` and ``:346``, and ``:170`` states it in prose. A top-level, non-deleted
organization *is* a company. ``llc_status`` is the lifecycle of something
already known to be one, which is why ``LLCAgentStatus``'s company analogue has
no "not a company" member -- the column was never the discriminator.

**Archived companies keep their CEO.** Scope is structural (top-level, not
deleted) and deliberately says nothing about ``llc_status``: the designation is
a structural fact and liveness is controlled by status elsewhere. Un-archiving
into a silently headless company is the harder failure to notice.

**The two rows are different kinds of thing, so they are treated differently.**

``llc_company_ceos`` is a *claim* -- "this company has a CEO" -- and it is false
for something that was never a company. There is no inactive state for a false
claim, so the row is deleted.

``agent_org_nodes`` is an *entity*, and entities acquire references:
``agent_scorecard.py`` and ``work_item_service.py`` both resolve org nodes by
id. Deleting one converts a wrong row into a dangling one. It is deactivated
instead, which removes liveness and keeps referential integrity.

An inactive node with no CEO designation is not an orphan. It is what a
non-company should have: no CEO, and a dormant node nothing schedules.

**Only rows still in the exact shape the backfill created are touched**:
``holder_type = 'agent'`` and the agent's slug equal to ``ceo-<company id>``.
Anything edited since is a human decision. An owner who has chosen a human CEO
for a sub-organization must not lose that choice to a cleanup for a bug they
never saw -- that constraint governs both statements and is asserted by a test,
not only by a ``WHERE`` clause.

``NO DATA LOSS`` for anything that was ever correct: every deleted row asserted
a CEO for a record that is not a company, and no agent row is removed.

Postgres only, like the backfill it repairs, and for the same reason -- the
SQLite path exists so unit tests can create the schema, and there is nothing to
repair in an in-memory database.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_089"
down_revision: Union[str, None] = "20260906_088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Table names are string literals at every ``op.*`` call site, never these
# constants: ``migrations/baseline.py`` AST-extracts each revision's artifacts
# and that extraction is only sound while the names are literal.
_TABLE = "llc_company_ceos"
_AGENTS = "agent_org_nodes"
_ORGS = "organizations"

#: An agent that is not working. ``LLCAgentStatus`` has no "retired" or
#: "inactive" member, and adding one to repair a backfill would be a vocabulary
#: change riding a data fix. ``on_leave`` is the existing member meaning "not
#: working"; if a dedicated state is wanted later, this is one predicate.
_DORMANT_STATUS = "on_leave"

#: Rows the backfill created and nobody has touched since. Shared by both
#: statements so they cannot drift apart and repair different sets.
_UNTOUCHED_BACKFILL_ROW = """
    c.holder_type = 'agent'
    AND a.id = c.holder_agent_id
    AND a.agent_id = 'ceo-' || c.company_id::text
"""

#: An organization that is not a company: not top-level, or soft-deleted.
_NOT_A_COMPANY = "(o.parent_org_id IS NOT NULL OR o.deleted_at IS NOT NULL)"


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if not all(_has_table(inspector, t) for t in (_TABLE, _AGENTS, _ORGS)):
        return

    # Deactivate first, then delete. The agent is identified *through* the CEO
    # row, so removing the claim first would leave nothing to join on and the
    # nodes would stay live.
    bind.execute(
        sa.text(f"""
            UPDATE agent_org_nodes AS a
            SET status = :dormant, heartbeat_enabled = false
            FROM llc_company_ceos AS c
            JOIN organizations AS o ON o.id = c.company_id
            WHERE {_UNTOUCHED_BACKFILL_ROW}
              AND {_NOT_A_COMPANY}
            """),
        {"dormant": _DORMANT_STATUS},
    )

    bind.execute(sa.text(f"""
            DELETE FROM llc_company_ceos AS c
            USING organizations AS o, agent_org_nodes AS a
            WHERE o.id = c.company_id
              AND {_UNTOUCHED_BACKFILL_ROW}
              AND {_NOT_A_COMPANY}
            """))


def downgrade() -> None:
    # Deliberately empty, and not an oversight. Reinstating the deleted rows
    # would re-assert that a sub-organization has a CEO, which was never true;
    # re-activating the agents would schedule nodes that should not run. There
    # is no state worth returning to.
    pass
