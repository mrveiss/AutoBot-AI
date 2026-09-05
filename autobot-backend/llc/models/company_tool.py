# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What one company knows about one tool that the registry cannot (#14852).

The tool registry (``autobot_shared.tool_sdk.registry``) is the authority for a
tool's **identity**: its name, its description, and the ``tags`` it groups
under. ``llc_role_tools.tool_name`` is a reference into it, validated on every
attachment by ``RoleToolService._require_registered_tool`` — which is why a
misspelled tool has never been attachable and there is nothing to reconcile.

This table does not repeat any of that. Duplicating name or description here
would fork tool identity into two stores with no rule for which one wins.

What it carries is the part that is **per company** and therefore cannot live
in a process-wide registry:

* ``url`` — this company's own account or workspace for the tool. Two companies
  using the same registered tool reach different addresses.
* ``logo_url`` — the mark this company recognises it by.

The row is an *overlay*: its absence is normal and means "nothing company-
specific is known yet", not "no such tool". Every read left-joins it, so a tool
with no row still appears with its registry metadata intact. That is what makes
it safe to add cost and renewal here for #14847 — a tool nobody has priced
keeps working rather than vanishing from the catalogue.

Scoping mirrors ``llc_role_tools``: ``company_id`` sits on the row so a query
pins its scope without a join, and a lost join condition cannot widen a result
across companies.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

#: Matches ``llc_role_tools.tool_name``. The two columns hold the same registry
#: key, so a narrower column here would make some attachable tools un-overlayable.
TOOL_NAME_LENGTH = 255

#: Comfortably past the ~2000-character ceiling browsers and proxies impose in
#: practice. Stored, never fetched by the backend: rendering these is the
#: frontend's job, and outbound HTTP would need the guarded fetch (rule 8).
URL_LENGTH = 2048


class LLCCompanyTool(Base):
    """One company's own facts about one registered tool."""

    __tablename__ = "llc_company_tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    #: A registry key, not free text. Validated by the service on write, for the
    #: same reason ``llc_role_tools`` is: the authority for "is this a real
    #: tool" is the registry, and a foreign key cannot reach it.
    tool_name: Mapped[str] = mapped_column(
        sa.String(TOOL_NAME_LENGTH), nullable=False, index=True
    )

    url: Mapped[str | None] = mapped_column(sa.String(URL_LENGTH), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(sa.String(URL_LENGTH), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    #: One overlay per tool per company. Without this a second row would shadow
    #: the first and which one won would depend on row order.
    __table_args__ = (
        sa.UniqueConstraint(
            "company_id", "tool_name", name="uq_llc_company_tools_company_tool"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LLCCompanyTool company={self.company_id} tool={self.tool_name!r}>"
