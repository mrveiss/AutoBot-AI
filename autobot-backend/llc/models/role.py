# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company-scoped role SQLAlchemy model (#14221 step 1).

A role is the **durable** thing in an organisation. Owner framing:

    people get promoted or leave the company, but the role stays — and so do
    the tools and workflows attached to the role.

Before this, a role was three approximations of one concept and none of them
was an object anything could attach to:

* ``AgentOrgNode.org_role`` — a ``String(50)``,
* ``MembershipRole`` — an **RBAC enum** for authorising claim/unclaim, not an
  org role,
* ``OrgChartNode.title`` — a display string.

Because the role was a string, everything attached to the *occupant* instead:
``LLCSecret.created_by_agent_id`` keys a secret to one agent, and neither
``controls_service.terminate`` nor ``membership_service`` reassigns anything on
departure. So when an agent is terminated or a person leaves, their work items
point at someone gone, the secrets they created reference nobody active, and the
next holder of the same role starts from nothing.

This table is the anchor those attachments need. Steps 3-5 of #14221 hang tools,
credential *references* and workflows off it, and make offboarding transfer to
the role rather than orphan.

Scoping, not tenant isolation: companies inside AutoBot are organisational units
of one installation, not customer isolation boundaries (owner correction on
#13935). Every role belongs to exactly one ``company_id``, mirroring
``LLCContact``, ``LLCCompanyMembership`` and ``LLCSecret``.

Deliberately NOT ``MembershipRole``. That enum is an authorisation gate with a
fixed five-member vocabulary (``owner/admin/member/guest/lead``) and cannot
express "this role may reach these tools and these credentials". Conflating a
display concept with an access gate is #13250's defect shape. Whether role-based
access eventually subsumes ``MembershipRole`` or sits above it is an open owner
decision recorded on #14221 — something must keep gating claim/unclaim either
way, so this step deliberately adds no access semantics at all.
"""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCRole(Base):
    """A named role within a company — the thing an occupant holds, not is.

    ``name`` is the role as the organisation says it ("Head of Sales", "SRE"),
    and is unique per company so two rows cannot describe the same role. It is
    free text on purpose: an organisation's role names are its own vocabulary,
    not one this codebase should enumerate — and #14263 records what happens
    when we mint vocabularies without need.

    This step carries no occupancy. Who *holds* a role is #14221 step 2, and it
    must not be modelled as a column here: a role outliving its occupant is the
    entire point, so occupancy is a relationship with its own lifetime, not a
    field on the role.
    """

    __tablename__ = "llc_roles"

    # Client-side default rather than server_default=gen_random_uuid(), matching
    # LLCContact and LLCSecret — keeps the model creatable against a plain
    # SQLite test engine with no Postgres function support.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (
        # Per company, not global: two companies may each have a "Head of Sales"
        # and they are different roles.
        sa.UniqueConstraint("company_id", "name", name="uq_llc_roles_company_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LLCRole id={self.id} company={self.company_id} name={self.name!r}>"
