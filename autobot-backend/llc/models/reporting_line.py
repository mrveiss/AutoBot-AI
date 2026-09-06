# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who reports to whom, across people and agents (#15763).

Before this there was no such relation. ``agent_org_nodes.reports_to`` is a
``String(255)`` holding another **agent id**, so it could express an agent's
manager only if that manager was itself an agent, and human members were
attached to the org chart as roots with no edge at all
(``llc/api/companies.py``: *"People join the forest as roots — memberships
carry no reports_to edge"*). The result was two disjoint forests: agents had a
hierarchy among themselves, people had none, and an agent reporting to its CEO
was unrepresentable in either direction.

Owner framing, which this table exists to satisfy:

    a person usually has one manager, but can report on a project basis to
    someone else · ai agents also report to someone, its project manager or
    ceo · technically a person might report to an agent

**One stored direction.** "Reports to" and "manages" are the same relation seen
from opposite ends — many-to-one going up, one-to-many coming back. Only the
upward edge is stored. "Manages" is derived by asking who names me, and is
never a second column, table or cached list: two stores of one fact can
disagree, and nothing in a schema makes that disagreement visible.

**Line management only.** This is the solid line, and it is single-valued
because it is what makes the org chart a tree. Project-basis reporting (#15766)
is a separate, many-to-many, project-scoped relation that is *additive* — it
never replaces or inverts what is here, because organisation relations always
win. Putting both in this table would make "who is this person's manager"
multi-valued, which destroys the layout and turns the bounded two-level
authority walk (#15765) into a fan-out over an unbounded set.

**An absent row means "reports to the CEO".** Only *explicit* lines are stored.
A subject with no row here reports to the company's CEO, resolved at read time
and never written down — materialising the default would be a second copy of a
fact the rule already fixes, and it would go stale the moment the CEO changed,
leaving a chart where everyone reports to the previous one and every row is
individually valid. Changing the CEO re-roots the whole tree with no writes.

The default chain has two steps, not one: an absent row resolves to the CEO,
and the **CEO resolves to the owner**. An *owner's* absent row is the
terminator. Applied without that exception the rule makes each level report to
itself — a one-node cycle, and the first thing an upward walk hits.

A company may have **several owners, and they are equals with identical
permissions**; there is no primary owner and none should be inferred.
``llc_company_memberships`` already allows this — it constrains one membership
per ``(company, user)`` and says nothing about how many are ``owner`` — so the
top of the hierarchy is a set of peers rather than a single node.

That is not a return to the forest ``get_org_chart`` builds today. The forest
problem is N *unconnected* subtrees; this is N equals at one level, with
everything below connected to them. The property to hold is **connectivity** —
every node reaches the owner layer, no cycles, and no detached roots, since a
node with no row is not a root but a defaulted one.

A company with no CEO designated has nothing for the middle step to resolve to.
That is a visible, reported state rather than a crash or an arbitrarily
promoted root, and it is the state every company is in until one is set.

**Which agent keyspace.** There are two, and they are not interchangeable
(#10032). ``agent_org_nodes.agent_id`` is a logical **slug** used for budgets,
runs and controls, and it is what the old ``reports_to`` column referenced.
``AgentOrgNode.id`` is the UUID primary key, and it is the *assignment*
keyspace — what ``LLCWorkItem.assignee_agent_id`` and
``LLCRoleAssignment.holder_agent_id`` point at. This table uses the **UUID PK**,
because the authority walk (#15765) has to line these edges up against role
assignments and cards, and a relation in the other keyspace would need a
translating join at every hop.

That choice is why the migration cannot be a straight copy: every existing
``reports_to`` slug has to be resolved to its node's UUID, and a slug that does
not resolve must be reported rather than dropped, or reporting lines disappear
silently.

**No type constraint between the ends.** person -> person, person -> agent,
agent -> person and agent -> agent are all legitimate. A guard rejecting "a
human cannot report to an agent" reads as sensible and is wrong here: agents
hold roles and lead work in this product, so the owner confirmed a person may
technically report to one. Authority follows the edge, not the kind of thing at
either end.
"""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

#: Matches ``LLCRoleAssignment.holder_type`` and ``LLCWorkItem.assignee_type``.
#: The discriminator is validated at every write site rather than by a database
#: type, so widening the vocabulary needs no migration.
HOLDER_TYPE_LENGTH = 16


class LLCReportingLine(Base):
    """One line-management edge: ``subject`` reports to ``manager``."""

    __tablename__ = "llc_reporting_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Carried on the row so every query pins its scope without a join — a lost
    # join condition cannot then widen a result across companies. Both ends of
    # the edge are inside this company; there are no cross-company managers.
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # The one who reports. `RoleHolderType` member; see the discriminator note.
    subject_type: Mapped[str] = mapped_column(sa.String(HOLDER_TYPE_LENGTH), nullable=False)
    subject_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    subject_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    # The one reported to.
    manager_type: Mapped[str] = mapped_column(sa.String(HOLDER_TYPE_LENGTH), nullable=False)
    manager_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    manager_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    # One line manager per subject, enforced per discriminator.
    #
    # A plain UniqueConstraint over (company_id, subject_type, subject_user_id,
    # subject_agent_id) would NOT do this: SQL treats NULLs as distinct, so two
    # rows for the same user — each with subject_agent_id NULL — do not collide,
    # and the single-valuedness the tree depends on quietly does not hold.
    # Partial indexes compare only the column that is populated for that type.
    __table_args__ = (
        sa.Index(
            "uq_llc_reporting_lines_user_subject",
            "company_id",
            "subject_user_id",
            unique=True,
            postgresql_where=sa.text("subject_type = 'user'"),
            sqlite_where=sa.text("subject_type = 'user'"),
        ),
        sa.Index(
            "uq_llc_reporting_lines_agent_subject",
            "company_id",
            "subject_agent_id",
            unique=True,
            postgresql_where=sa.text("subject_type = 'agent'"),
            sqlite_where=sa.text("subject_type = 'agent'"),
        ),
    )

    @property
    def subject_id(self) -> Optional[uuid.UUID]:
        """The populated subject column, chosen by ``subject_type``.

        ``None`` for a discriminator that does not match a populated column,
        rather than returning whichever id happens to be set. A row whose type
        disagrees with its ids is corrupt, and guessing hides that — the same
        contract as ``LLCRoleAssignment.holder_id``.
        """
        return {"user": self.subject_user_id, "agent": self.subject_agent_id}.get(self.subject_type)

    @property
    def manager_id(self) -> Optional[uuid.UUID]:
        """The populated manager column, chosen by ``manager_type``."""
        return {"user": self.manager_user_id, "agent": self.manager_agent_id}.get(self.manager_type)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LLCReportingLine {self.subject_type}:{self.subject_id} -> {self.manager_type}:{self.manager_id}>"
