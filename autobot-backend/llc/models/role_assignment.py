# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who holds a company role, and for how long (#14221 step 2).

The role itself is the canonical ``roles`` row (``Role.org_id`` = the company);
step 1 added no table of its own. Occupancy is a **relationship with its own
lifetime**, so it gets one:

* ``ended_at IS NULL`` — the holder holds it *now*.
* ``ended_at`` set — the holder held it *then*, and the row stays.

That second property is the owner's requirement, stated directly:

    work items do not go anywhere, they remain behind when an employee leaves;
    they still need someone to work on them

Ending an assignment must therefore never delete anything. The role keeps its
identity, its history keeps who held it, and step 4 hangs the transfer of tools
and workflows off this table rather than off the departing occupant.

Several holders may hold one role at once — three people can all be "SRE" — so
there is no "one current holder" constraint. What *is* constrained is the same
holder holding the same role twice concurrently, which is a double-assignment
bug rather than a legitimate state.

The polymorphic holder mirrors ``LLCWorkItem``'s existing assignee pattern
(``String(16)`` discriminator + one nullable UUID column per holder kind)
rather than inventing a second convention for the same idea.
"""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCRoleAssignment(Base):
    """One holder's tenure in one role.

    ``holder_type`` is a :class:`~llc.models.enums.RoleHolderType` value and
    selects which of the three ``holder_*_id`` columns is populated. The column
    stays ``String(16)`` to match ``LLCWorkItem.assignee_type`` — the enum is
    enforced at every write site rather than by a database type, so widening the
    vocabulary later needs no migration.
    """

    __tablename__ = "llc_role_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Denormalised from the role's org_id on purpose: every query in this module carries
    # its own WHERE company_id rather than reaching it through a join, so a lost
    # join condition cannot widen the scope. That predicate has had to be pinned
    # independently five times here (#13936, #13969, #13942, #14222, #14210).
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    holder_type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    holder_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    holder_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    holder_contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    # NULL means "still holds it". This is the column the whole design turns on,
    # so ending a tenure is an UPDATE here and never a DELETE of the row.
    ended_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        state = "current" if self.ended_at is None else "ended"
        return f"<LLCRoleAssignment role={self.role_id} {self.holder_type} {state}>"

    @property
    def holder_id(self) -> Optional[uuid.UUID]:
        """The populated holder column, chosen by ``holder_type``.

        Returns ``None`` for an unrecognised discriminator rather than guessing
        a column — a row whose ``holder_type`` does not match its populated id
        is corrupt, and silently returning "some id that happens to be set"
        would hide that.
        """
        return {
            "agent": self.holder_agent_id,
            "user": self.holder_user_id,
            "contact": self.holder_contact_id,
        }.get(self.holder_type)
