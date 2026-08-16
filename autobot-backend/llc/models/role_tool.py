# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tools carried by a role (#14221 step 4).

The other half of "tools and workflows attached to the role". A change of holder
moves nothing here: the next occupant of a role reaches the same tools because
the attachment was never the previous occupant's.

``tool_name`` is a plain string because tools have **no database table** — they
register in-process by name via ``autobot_shared.tool_sdk.registry``. That
asymmetry with permissions (which resolve against the ``permissions`` table) is
deliberate and is why validation lives in the service rather than in a foreign
key: the authority for "is this a real tool" is the registry, not the schema.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCRoleTool(Base):
    """One tool made available to the holders of one role."""

    __tablename__ = "llc_role_tools"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (sa.UniqueConstraint("role_id", "tool_name", name="uq_llc_role_tools_role_tool"),)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LLCRoleTool role={self.role_id} tool={self.tool_name!r}>"
