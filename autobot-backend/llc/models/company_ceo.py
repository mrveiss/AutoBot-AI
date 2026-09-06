# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which agent or person holds the CEO position of a company (#15770).

Nothing designated one before this. ``MembershipRole`` is authority over the
company (``owner``/``admin``/``member``/...), not a position in its hierarchy;
``OrgRole`` on agents is ``manager``/``coordinator``/``specialist``/``worker``
and says nothing about which manager is *the* one at the top. The string
``agent-ceo`` appeared once in the whole backend, as a test fixture.

**Why the position needs a row at all.** #15763 resolves an absent reporting
line through a default chain -- anyone with no explicit manager reports to the
CEO, the CEO reports to the owners, and an owner terminates the walk. The CEO
is the middle step, so without a designation the chain has nothing to resolve
to and every company stays the disconnected forest #15763 exists to fix.

**An agent by default, not an agent by definition.** The owner's decision is
that a new company gets an agent CEO; the reference design this Company OS
follows arrives at the same default independently. "Default" means changeable:
a human CEO stays expressible, so this uses the ``holder_type`` +
``holder_*_id`` keyspace of :class:`~llc.models.role_assignment.LLCRoleAssignment`
rather than a bare ``ceo_agent_id``. Code that reads an agent column directly
breaks the moment a person holds the position, which is why there is no such
column to read.

**One CEO per company, enforced by the schema.** ``company_id`` is UNIQUE
outright. This table can afford what
:class:`~llc.models.reporting_line.LLCReportingLine` could not: there, the
subject spans two nullable id columns and SQL's NULL-distinctness means a
constraint over both enforces nothing, so partial indexes per discriminator
were required. Here the *company* is the single non-null key, so a plain unique
constraint says exactly what is meant.

**No row is a legal state, not a broken one.** A company whose CEO agent was
deleted has to keep rendering. The absence is reported (``ChainEnd.NO_CEO``)
rather than repaired by promoting whichever node happens to be nearby -- an
arbitrary promotion is a silent, wrong answer to "who runs this company".
"""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

#: Matches ``LLCReportingLine.HOLDER_TYPE_LENGTH`` and ``LLCRoleAssignment``.
HOLDER_TYPE_LENGTH = 16


class LLCCompanyCEO(Base):
    """The company's CEO: an agent or a person, at most one."""

    __tablename__ = "llc_company_ceos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # UNIQUE rather than merely indexed: "at most one CEO" is the invariant the
    # default chain walks on, and a rule enforced only in service code is a rule
    # that holds until the second writer.
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)

    # `RoleHolderType` member -- 'user' or 'agent'. Validated at the write site,
    # as everywhere else in this keyspace.
    holder_type: Mapped[str] = mapped_column(sa.String(HOLDER_TYPE_LENGTH), nullable=False)
    holder_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    holder_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    @property
    def holder_id(self) -> Optional[uuid.UUID]:
        """The populated holder column, chosen by ``holder_type``.

        ``None`` when the discriminator does not match a populated column,
        rather than whichever id happens to be set. A row whose type disagrees
        with its ids is corrupt, and guessing hides that -- the same contract as
        ``LLCRoleAssignment.holder_id`` and ``LLCReportingLine.subject_id``.
        """
        return {"user": self.holder_user_id, "agent": self.holder_agent_id}.get(self.holder_type)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<LLCCompanyCEO company={self.company_id} {self.holder_type}={self.holder_id}>"
