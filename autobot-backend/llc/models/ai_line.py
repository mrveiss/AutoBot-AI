# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One company's line for AI on one tool action (#18430).

``line`` is one of ``autonomous`` / ``draft_then_send`` / ``never``
(``autobot_shared.ai_lines.AiLine``). A missing row is NORMAL and means "not set", which the
enforcement point reads as line 2 -- it is never an absent-means-allowed.

Nothing but the post-approval handler (``services.ai_line_change_action``) writes this table:
agents never change a line, and a person changes one through Approvals. The store has no
other writer, and ``repo_tests/ai_line_single_policy_18430_test.py`` fails if one appears.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

#: ``<tool>`` or ``<tool>:<action>`` -- wider than ``llc_role_tools.tool_name`` by the action.
ACTION_KEY_LENGTH = 320


class LLCAiLine(Base):
    """The line set for one tool action in one company."""

    __tablename__ = "llc_ai_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: The scope's id: the company's id when ``scope_kind`` is ``company``, the user's id when it is ``user``
    #: (a user with no company has personal lines, same store). The name predates the personal scope.
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    scope_kind: Mapped[str] = mapped_column(sa.String(10), nullable=False, default="company", server_default="company")
    action_key: Mapped[str] = mapped_column(sa.String(ACTION_KEY_LENGTH), nullable=False)
    line: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    #: The approval that authorised this value -- the paper trail for every change.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("scope_kind", "company_id", "action_key", name="uq_llc_ai_lines_scope_action"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LLCAiLine company={self.company_id} action={self.action_key!r} line={self.line!r}>"
