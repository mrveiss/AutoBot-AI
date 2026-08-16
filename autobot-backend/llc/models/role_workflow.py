# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflows attached to a role, not to whoever currently holds it (#14221 step 5).

Owner framing:

    people get promoted or leave the company, but the role stays — and so do
    the tools and workflows attached to the role

That is the whole reason this table hangs off the canonical ``roles`` row and not off an
agent, a user or an org node. When the holder changes, nothing here moves: the
next occupant of "Head of Sales" inherits the same workflows because the
attachment was never theirs to begin with.

``workflow_id`` is ``String(255)``, matching ``Workflow.workflow_id`` — the
workflows table is keyed by a string id, not a UUID, so this column mirrors it
rather than converting at the boundary. (``llc_secrets`` and three other LLC
models diverge on ``company_id`` in exactly that way, which is #14312.)
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCRoleWorkflow(Base):
    """One workflow attached to one role."""

    __tablename__ = "llc_role_workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Carried on the attachment itself so every query pins scope without
    # depending on a join to llc_roles — a lost join condition cannot widen the
    # result. Same reasoning as llc_role_assignments.
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    workflow_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)

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
        # Attaching the same workflow twice is a no-op the caller should hear
        # about, not a second row.
        sa.UniqueConstraint("role_id", "workflow_id", name="uq_llc_role_workflows_role_workflow"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LLCRoleWorkflow role={self.role_id} workflow={self.workflow_id!r}>"
